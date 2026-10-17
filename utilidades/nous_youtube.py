# -*- coding: utf-8 -*-
"""
title: Nous YouTube
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Cole um link do YouTube no chat e peca "resuma", "quais os pontos principais"
  ou qualquer pergunta sobre o video: este filtro baixa a legenda (transcricao)
  do video e a entrega ao modelo junto com a sua pergunta. Prefere a legenda em
  portugues; sem ela, usa a original. Precisa de internet so' para buscar a
  legenda - o resumo e' feito pelo modelo local.
"""
import re
from typing import Optional

from pydantic import BaseModel, Field

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except Exception:
    YouTubeTranscriptApi = None

_YT_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?"
    r"(?:youtube\.com/(?:watch\?(?:[^\s]*?&)?v=|shorts/|live/|embed/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})")


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _video_ids(messages):
    """Links de TODAS as mensagens do usuario, do mais recente ao mais antigo:
    a injecao nao fica salva no chat, entao a pergunta seguinte sobre o mesmo
    video ("e o que ele fala no final?") precisa da transcricao de novo."""
    ids = []
    for m in reversed(messages):
        if m.get("role") == "user":
            ids.extend(_YT_RE.findall(_text(m)))
    return list(dict.fromkeys(ids))


def _fmt_ts(sec):
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _fetch_transcript(video_id, langs):
    """(idioma, [(inicio_s, texto)]) ou levanta excecao com o motivo."""
    tl = YouTubeTranscriptApi().list(video_id)
    try:
        tr = tl.find_transcript(langs)
    except Exception:
        # sem PT/EN: a primeira que existir (manual antes de automatica)
        tr = next(iter(tl))
    data = tr.fetch()
    return tr.language_code, [(s.start, s.text.replace("\n", " ")) for s in data]


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga a leitura de videos do YouTube.")
        LANGS: str = Field(default="pt,pt-BR,en", description="Idiomas preferidos da legenda, em ordem.")
        MAX_CHARS: int = Field(default=24000, description="Limite de texto da transcricao entregue ao modelo.")
        MAX_VIDEOS: int = Field(default=2, description="Quantos links por mensagem processar.")

    def __init__(self):
        self.valves = self.Valves()
        self._cache = {}  # video_id -> bloco pronto (o link volta a cada turno da conversa)

    def _block(self, video_id, budget):
        if video_id in self._cache:
            if self._cache[video_id] is None:
                raise LookupError("sem legenda (ja tentado)")
            return self._cache[video_id]
        langs = [x.strip() for x in self.valves.LANGS.split(",") if x.strip()]
        lang, parts = _fetch_transcript(video_id, langs)
        lines, used = [], 0
        # marca de tempo a cada ~30 s: o modelo consegue citar "aos 4:30"
        last_mark = -999
        for start, text in parts:
            prefix = ""
            if start - last_mark >= 30:
                prefix = f"[{_fmt_ts(start)}] "
                last_mark = start
            piece = prefix + text
            if used + len(piece) > budget:
                lines.append("[... transcricao cortada por tamanho ...]")
                break
            lines.append(piece)
            used += len(piece) + 1
        block = (f"[Video do YouTube {video_id} - transcricao ({lang})]\n" + " ".join(lines))
        self._cache[video_id] = block
        return block

    async def inlet(self, body: dict, __user__: Optional[dict] = None,
                    __event_emitter__=None) -> dict:
        if not self.valves.ENABLED or YouTubeTranscriptApi is None:
            return body
        messages = body.get("messages", [])
        ids = _video_ids(messages)
        if not ids:
            return body
        ids = ids[: self.valves.MAX_VIDEOS]

        async def status(desc, done):
            if __event_emitter__:
                try:
                    await __event_emitter__({"type": "status",
                                             "data": {"description": desc, "done": done}})
                except Exception:
                    pass

        fresh = any(v not in self._cache for v in ids)
        if fresh:
            await status("Lendo a legenda do video...", False)
        blocks = []
        budget = self.valves.MAX_CHARS // len(ids)
        for vid in ids:
            try:
                blocks.append(self._block(vid, budget))
            except Exception:
                self._cache.setdefault(vid, None)  # nao tenta de novo a cada turno

        if blocks:
            text = ("[Nous YouTube] O usuario enviou link(s) de video. Abaixo esta a "
                    "transcricao. Responda com base nela, em portugues, e cite os "
                    "minutos quando ajudar.\n\n" + "\n\n".join(blocks))
        else:
            text = ("[Nous YouTube] O usuario enviou um link do YouTube, mas o video "
                    "nao tem legenda disponivel (ou o YouTube bloqueou o acesso). "
                    "Diga isso a ele com gentileza; nao invente o conteudo do video.")
        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + text) if base else text
        else:
            messages.insert(0, {"role": "system", "content": text})
        body["messages"] = messages

        if not fresh:
            return body
        if blocks:
            await status(f"Legenda de {len(blocks)} video(s) lida.", True)
        else:
            await status("Este video nao tem legenda disponivel.", True)
        return body
