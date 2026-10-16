# -*- coding: utf-8 -*-
"""
title: Nous Agenda
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Agenda pelo chat: "me lembre de pagar a luz sexta as 9h", "anota: ideia
  para o projeto...", "marca dentista dia 20 as 14h", "o que eu tenho amanha?".
  Quando a mensagem parece um pedido de agenda, o modelo LOCAL extrai os dados
  (titulo, data, repeticao) e o filtro grava no servico da agenda (porta 8996).
  O modelo do chat so' confirma. Tudo fica na maquina.
"""
import re
import json
import time
import asyncio
import hashlib
import datetime
from typing import Optional

from pydantic import BaseModel, Field

try:
    import requests
except Exception:
    requests = None

_CREATE = re.compile(
    r"\b(me lembr[ae]|lembr[ae]-me|me avis[ae]|lembrete|anot[ae]|anotar|"
    r"(?:cri[ae]|salv[ae]|fa[cz]a?) (?:uma |um )?(?:nota|lembrete|evento|compromisso)|"
    r"agend[ae]|agendar|marc[ae] (?:um|uma|na|no|pra|para|dia)|marcar|"
    # "marca dentista dia 20" sim; "a marca do carro" nao: exige data/hora perto
    r"marc[ae]\b.{0,60}?(?:\bdia \d+|amanh[aã]|\bhoje\b|segunda|ter[cç]a|quarta|quinta|sexta|"
    r"s[aá]bado|domingo|\b[aà]s \d+|\b\d{1,2}h|\b\d{1,2}/\d{1,2})|"
    r"(?:coloc|p[oõ]e|bot)[ae]? (?:isso )?na (?:minha )?agenda|"
    r"adicion[ae] (?:na|ao|no) (?:minha |meu )?(?:agenda|calend[aá]rio))\b", re.I)
_QUERY = re.compile(
    r"\b((?:o que|quais?|que) (?:eu )?(?:tenho|tem|h[aá]) (?:marcado|agendado|na agenda|hoje|"
    r"amanh[aã]|essa semana|esta semana|pra|para)|minha agenda|meus compromissos|"
    r"meus lembretes|minhas notas|estou livre|t[oô] livre)\b", re.I)

_DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")

_PROMPT = """Voce extrai pedidos de agenda de mensagens em portugues. Agora e' {agora} ({dia}).
Mensagem do usuario: \"\"\"{msg}\"\"\"

Responda SO' com um JSON neste formato:
{{"acao": "lembrete" | "nota" | "evento" | "consulta" | "nenhuma",
  "titulo": "curto, sem a data",
  "detalhes": "resto do conteudo (pode ser vazio)",
  "quando": "AAAA-MM-DDTHH:MM ou AAAA-MM-DD ou vazio",
  "fim": "AAAA-MM-DDTHH:MM ou vazio",
  "dia_inteiro": true | false,
  "repetir": "nenhum" | "diario" | "dias_uteis" | "semanal" | "mensal" | "anual",
  "avisar_min_antes": numero ou null,
  "periodo_dias": numero}}

Regras:
- "lembrete": o usuario quer ser AVISADO de algo numa hora (me lembre, me avise).
- "evento": compromisso com hora marcada (consulta, reuniao, aniversario, viagem).
- "nota": guardar uma informacao/ideia, sem aviso.
- "consulta": quer SABER o que tem na agenda; periodo_dias = quantos dias olhar (hoje=1, amanha=2, semana=7).
- "nenhuma": a mensagem nao e' um pedido de agenda (ex.: pergunta geral que so' cita a palavra).
- Datas relativas (amanha, sexta, dia 20, semana que vem) viram datas absolutas a partir de agora.
- Se o usuario disser so' o dia de um lembrete, use 09:00."""


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _fmt(ts, all_day=False):
    d = datetime.datetime.fromtimestamp(ts)
    s = f"{_DIAS[d.weekday()]} {d.strftime('%d/%m/%Y')}"
    return s if all_day else s + d.strftime(" as %H:%M")


def _iso_ok(s):
    try:
        datetime.datetime.fromisoformat(s)
        return True
    except Exception:
        return False


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga a agenda pelo chat.")
        AGENDA_URL: str = Field(default="http://127.0.0.1:8996", description="Servico da agenda do Nous.")
        OLLAMA_URL: str = Field(default="http://127.0.0.1:11434", description="Ollama local (extrai os dados do pedido).")
        AVISO_PADRAO_MIN: int = Field(default=30, description="Minutos de antecedencia do aviso de compromissos.")

    def __init__(self):
        self.valves = self.Valves()
        self._done = {}  # hash(usuario+mensagem) -> (quando, texto). Regenerar nao duplica.

    # ---------------------------------------------------------- modelo local
    def _model(self, chat_model):
        try:
            tags = requests.get(f"{self.valves.OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
        except Exception:
            return None
        names = [m.get("name", "") for m in tags]
        if chat_model in names or (chat_model + ":latest") in names:
            return chat_model  # o modelo do chat ja esta na VRAM: resposta rapida
        for n in names:
            if "/" not in n and not any(p in n.lower() for p in _EMBED):
                return n
        return None

    def _extract(self, msg, chat_model):
        model = self._model(chat_model)
        if not model:
            return None
        now = datetime.datetime.now()
        prompt = _PROMPT.format(agora=now.strftime("%Y-%m-%dT%H:%M"),
                                dia=_DIAS[now.weekday()], msg=msg[:2000])
        r = requests.post(f"{self.valves.OLLAMA_URL}/api/generate",
                          json={"model": model, "prompt": prompt, "stream": False,
                                "format": "json", "think": False,
                                "options": {"temperature": 0}}, timeout=120)
        r.raise_for_status()
        return json.loads(r.json().get("response") or "{}")

    # ---------------------------------------------------------- agenda
    def _api(self, method, path, **kw):
        r = requests.request(method, self.valves.AGENDA_URL + path, timeout=15, **kw)
        data = r.json()
        if r.status_code != 200:
            raise RuntimeError(data.get("error") or "erro na agenda")
        return data

    def _apply(self, d, uid):
        """Executa a acao e devolve o texto para o modelo confirmar (ou None)."""
        acao = (d.get("acao") or "nenhuma").lower()
        titulo = (d.get("titulo") or "").strip()[:200]
        detalhes = (d.get("detalhes") or "").strip()
        quando = (d.get("quando") or "").strip()
        repetir = d.get("repetir") if d.get("repetir") in (
            "diario", "dias_uteis", "semanal", "mensal", "anual") else None
        if quando and not _iso_ok(quando):
            quando = ""
        if quando and len(quando) == 10 and acao == "lembrete":
            quando += "T09:00"

        if acao == "consulta":
            dias = max(1, min(31, int(d.get("periodo_dias") or 1)))
            up = self._api("GET", "/today", params={"user_id": uid, "days": dias})
            lines = []
            for e in up["events"]:
                lines.append(f"- {_fmt(e['occ_start'], e['all_day'])}: {e['title']}"
                             + (f" ({e['location']})" if e["location"] else ""))
            for n in up["notes"]:
                ts = n["due_at"] or n["remind_at"]
                atraso = " [ATRASADO]" if ts < up["now"] else ""
                lines.append(f"- lembrete {_fmt(ts)}: {n['title'] or n['body'][:80]}{atraso}")
            corpo = "\n".join(lines) or "(nada marcado nesse periodo)"
            return (f"[Nous Agenda] Agenda do usuario nos proximos {dias} dia(s), lida "
                    f"agora do Nous:\n{corpo}\nResponda a pergunta com base nisso, de "
                    "forma organizada. Nao invente compromissos.")

        if acao == "nota" or (acao == "lembrete" and not quando):
            n = self._api("POST", "/notes", json={"user_id": uid, "title": titulo,
                                                  "body": detalhes})["note"]
            return (f"[Nous Agenda] Nota salva: \"{n['title'] or n['body'][:60]}\"."
                    + (" O usuario pediu um lembrete mas sem data; pergunte quando ele "
                       "quer ser avisado." if acao == "lembrete" else "")
                    + " Confirme em uma frase curta.")

        if acao == "lembrete":
            n = self._api("POST", "/notes", json={"user_id": uid, "title": titulo, "body": detalhes,
                                                  "remind_at": quando, "due_at": quando,
                                                  "repeat": repetir})["note"]
            rep = f", repetindo ({repetir.replace('_', ' ')})" if repetir else ""
            return (f"[Nous Agenda] Lembrete criado: \"{n['title']}\" para "
                    f"{_fmt(n['remind_at'])}{rep}. O Nous vai avisar no computador nessa "
                    "hora. Confirme ao usuario em uma frase curta, com a data por extenso.")

        if acao == "evento" and quando:
            dia_inteiro = bool(d.get("dia_inteiro")) or len(quando) == 10
            fim = (d.get("fim") or "").strip()
            aviso = d.get("avisar_min_antes")
            aviso = int(aviso) if isinstance(aviso, (int, float)) else self.valves.AVISO_PADRAO_MIN
            body = {"user_id": uid, "title": titulo, "description": detalhes,
                    "start_at": quando, "all_day": dia_inteiro, "remind_min": aviso}
            if fim and _iso_ok(fim):
                body["end_at"] = fim
            if repetir:
                body["repeat"] = repetir
            e = self._api("POST", "/events", json=body)["event"]
            return (f"[Nous Agenda] Compromisso salvo: \"{e['title']}\" em "
                    f"{_fmt(e['start_at'], e['all_day'])}"
                    + (f", com aviso {aviso} min antes" if not dia_inteiro and aviso else "")
                    + ". Confirme ao usuario em uma frase curta.")

        if acao == "evento":
            return ("[Nous Agenda] O usuario quer marcar um compromisso mas nao disse "
                    "quando. Pergunte o dia e a hora.")
        return None

    # ---------------------------------------------------------- ciclo
    async def inlet(self, body: dict, __user__: Optional[dict] = None,
                    __event_emitter__=None) -> dict:
        if not self.valves.ENABLED or requests is None:
            return body
        uid = (__user__ or {}).get("id")
        messages = body.get("messages", [])
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        msg = _text(last) if last else ""
        if not uid or not msg or not (_CREATE.search(msg) or _QUERY.search(msg)):
            return body

        async def status(desc, done):
            if __event_emitter__:
                try:
                    await __event_emitter__({"type": "status", "data": {"description": desc, "done": done}})
                except Exception:
                    pass

        key = hashlib.sha1(f"{uid}\n{msg}".encode("utf-8")).hexdigest()
        t = time.time()
        self._done = {k: v for k, v in self._done.items() if t - v[0] < 86400}
        if key in self._done and not _QUERY.search(msg):
            text = self._done[key][1]  # regenerou a resposta: ja foi gravado
        else:
            await status("Verificando a agenda...", False)
            try:
                data = await asyncio.to_thread(self._extract, msg, body.get("model") or "")
                text = await asyncio.to_thread(self._apply, data or {}, uid) if data else None
                if text:
                    self._done[key] = (t, text)  # so' sucesso: falha tenta de novo
            except requests.exceptions.ConnectionError:
                text = ("[Nous Agenda] O servico da agenda nao esta no ar, entao NADA foi "
                        "salvo. Avise o usuario e sugira abrir o Nous de novo pelo atalho.")
            except Exception as e:
                text = (f"[Nous Agenda] Nao consegui salvar na agenda ({e}). Avise o "
                        "usuario; nao diga que foi salvo.")
        await status("Agenda atualizada." if text else "Nada para a agenda.", True)
        if not text:
            return body

        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + text) if base else text
        else:
            messages.insert(0, {"role": "system", "content": text})
        body["messages"] = messages
        return body
