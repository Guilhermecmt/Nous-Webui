# -*- coding: utf-8 -*-
"""
title: Nous History
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Recupera contexto de conversas anteriores do usuario. A cada pergunta,
  busca nos dialogos passados (busca HIBRIDA: semantica + palavra-chave,
  fundidas por Reciprocal Rank Fusion) e injeta os trechos mais relevantes
  no contexto — para o Nous lembrar "o que a gente discutiu" sem precisar
  resumir manualmente. 100% local; nada sai da maquina.

  O indice e' mantido por history/index_history.py (processo em segundo plano).
  Este filtro so' LE o indice (nous_history.sqlite3 no NousData).
  Complementa a Memoria Pessoal (fatos) e os Arquivos (notas).
"""
import os
import re
import json
import asyncio
import sqlite3
import datetime
from typing import Optional

from pydantic import BaseModel, Field

try:
    import numpy as np
except Exception:
    np = None

try:
    import requests
except Exception:
    requests = None

DB_NAME = "nous_history.sqlite3"

_avisos_pendentes: set = set()


async def _aviso_rapido(emit, texto: str, segundos: float = 2.0) -> None:
    """Mostra o aviso enquanto o pedido sai e some logo depois: nao fica em
    cima da resposta. O status "hidden" esconde o bloco no Open WebUI 0.12."""
    try:
        await emit({"type": "status", "data": {"description": texto, "done": False}})
    except Exception:
        return

    async def _some():
        await asyncio.sleep(segundos)
        try:
            await emit({"type": "status", "data": {"description": texto, "done": True, "hidden": True}})
        except Exception:
            pass

    t = asyncio.create_task(_some())
    _avisos_pendentes.add(t)  # sem referencia o asyncio pode descartar a tarefa
    t.add_done_callback(_avisos_pendentes.discard)

_CACHE = {
    "key":        None,   # (mtime, user_id)
    "ids":        [],
    "user_msgs":  [],
    "asst_msgs":  [],
    "chats":      [],
    "timestamps": [],
    "mat":        None,
}

_STOP = {
    "como", "para", "por", "porque", "que", "qual", "quais", "quando", "onde",
    "quem", "uso", "usar", "meu", "minha", "meus", "minhas", "seu", "sua", "suas",
    "com", "sem", "dos", "das", "nos", "nas", "num", "numa", "isso", "essa",
    "esse", "este", "esta", "isto", "aqui", "ali", "mais", "menos", "muito",
    "tem", "ter", "foi", "ser", "sao", "esta", "estao", "ele", "ela", "eles",
    "elas", "voce", "nao", "sim", "fazer", "faco", "sobre", "me", "mi",
    "the", "and", "for", "you", "your", "are", "was", "with", "from", "this",
    "that", "what", "how", "when", "where", "can", "not", "have",
}


def _data_dir():
    for v in (os.environ.get("DATA_DIR"), os.environ.get("NOUS_DATA_DIR")):
        if v:
            return v
    try:
        from open_webui.env import DATA_DIR as D
        if D:
            return str(D)
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "NousData")


def _db_path():
    return os.path.join(_data_dir(), DB_NAME)


def _db_sig(db):
    """Assinatura que muda a cada commit, MESMO em modo WAL — onde o mtime do
    arquivo principal nao muda (a escrita vai para o -wal). Sem isto, o cache do
    filtro nunca enxergaria os dialogos recem-indexados ate um checkpoint."""
    try:
        main = os.path.getmtime(db)
    except OSError:
        return None
    wal = None
    try:
        st = os.stat(db + "-wal")
        wal = (st.st_mtime, st.st_size)
    except OSError:
        pass
    return (main, wal)


def _tokens(text):
    toks = re.findall(r"[0-9A-Za-zÀ-ÿ]{3,}", (text or "").lower())
    seen, out = set(), []
    for t in toks:
        if t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:12]


def _fmt_date(ts):
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%d/%b/%Y")
    except Exception:
        return "?"


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga o historico de conversas.")
        TOP_K: int = Field(default=3, description="Quantos dialogos anteriores injetar por pergunta.")
        MIN_SIM: float = Field(default=0.62, description="Similaridade minima (0-1) para considerar relevante (calibrado para o granite-embedding:278m).")
        MAX_CONTEXT_CHARS: int = Field(default=3000, description="Limite total de texto injetado.")
        RRF_K: int = Field(default=60, description="Constante do Reciprocal Rank Fusion.")
        EMBED_MODEL: str = Field(default="granite-embedding:278m", description="Modelo de embeddings (Ollama). Igual ao do indexador (NOUS_EMBED_MODEL).")
        OLLAMA_URL: str = Field(default="", description="URL do Ollama. Vazio = OLLAMA_BASE_URL ou 127.0.0.1:11434.")

    def __init__(self):
        self.valves = self.Valves()
        self._pending_dates = {}  # user_id -> [date_str, ...]

    def _ollama(self):
        return (self.valves.OLLAMA_URL
                or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    def _embed(self, text):
        if requests is None:
            return None
        try:
            r = requests.post(
                f"{self._ollama()}/api/embeddings",
                json={"model": self.valves.EMBED_MODEL, "prompt": text[:6000]},
                timeout=30,
            )
            if r.status_code != 200:
                return None
            v = r.json().get("embedding")
            return v if v else None
        except Exception:
            return None

    def _load_index(self, user_id=None):
        """Carrega (com cache) matriz de embeddings filtrada por user_id."""
        db = _db_path()
        if not os.path.isfile(db):
            return False
        sig = _db_sig(db)
        if sig is None:
            return False

        cache_key = (sig, user_id)
        if _CACHE["key"] == cache_key and (_CACHE["ids"] or _CACHE["mat"] is not None):
            return True

        ids, user_msgs, asst_msgs, chats, timestamps, vecs = [], [], [], [], [], []
        try:
            cx = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=15)
        except Exception:
            cx = sqlite3.connect(db, timeout=15)
        try:
            if user_id:
                rows = cx.execute(
                    "SELECT id, chat_id, user_msg, asst_msg, created_at, embedding "
                    "FROM dialogues WHERE user_id=? ORDER BY created_at DESC",
                    (user_id,),
                ).fetchall()
            else:
                rows = cx.execute(
                    "SELECT id, chat_id, user_msg, asst_msg, created_at, embedding "
                    "FROM dialogues ORDER BY created_at DESC"
                ).fetchall()
            for id_, chat_id, user_msg, asst_msg, created_at, emb in rows:
                ids.append(id_)
                user_msgs.append(user_msg or "")
                asst_msgs.append(asst_msg or "")
                chats.append(chat_id)
                timestamps.append(created_at or 0)
                if emb is not None and np is not None:
                    vecs.append(np.frombuffer(emb, dtype="float32"))
                else:
                    vecs.append(None)
        finally:
            cx.close()

        mat = None
        if np is not None and vecs and any(v is not None for v in vecs):
            dim = next(v.shape[0] for v in vecs if v is not None)
            arr = np.zeros((len(vecs), dim), dtype="float32")
            for i, v in enumerate(vecs):
                if v is not None and v.shape[0] == dim:
                    arr[i] = v
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            mat = arr / norms

        _CACHE.update(
            key=cache_key, ids=ids, user_msgs=user_msgs, asst_msgs=asst_msgs,
            chats=chats, timestamps=timestamps, mat=mat,
        )
        return bool(ids)

    def _keyword_ranks(self, query):
        toks = _tokens(query)
        if not toks:
            return {}, set()
        match = " OR ".join(f'"{t}"' for t in toks)
        db = _db_path()
        try:
            cx = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=15)
        except Exception:
            return {}, set()
        try:
            rows = cx.execute(
                "SELECT rowid, bm25(dialogues_fts) FROM dialogues_fts "
                "WHERE dialogues_fts MATCH ? ORDER BY bm25(dialogues_fts) LIMIT 25",
                (match,),
            ).fetchall()
        except Exception:
            return {}, set()
        finally:
            cx.close()
        ranks = {rowid: i for i, (rowid, _) in enumerate(rows)}
        return ranks, set(ranks.keys())

    def _retrieve(self, query, user_id=None, exclude_chat=None):
        if not self._load_index(user_id):
            return [], []

        ids = _CACHE["ids"]
        id_pos = {cid: i for i, cid in enumerate(ids)}

        # ---- semantica ----
        sem_rank, cos_by_id = {}, {}
        best_sim = 0.0
        mat = _CACHE["mat"]
        if mat is not None:
            qv = self._embed(("search_query: " + query) if self.valves.EMBED_MODEL.startswith("nomic") else query)
            if qv is not None and np is not None:
                q = np.asarray(qv, dtype="float32")
                n = np.linalg.norm(q) or 1.0
                sims = mat @ (q / n)
                cos_by_id = {ids[i]: float(sims[i]) for i in range(len(ids))}
                order = np.argsort(-sims)[:25]
                best_sim = float(sims[order[0]]) if len(order) else 0.0
                for rank, idx in enumerate(order):
                    sem_rank[ids[idx]] = rank

        # ---- palavra-chave ----
        kw_rank, kw_hits = self._keyword_ranks(query)

        if best_sim < self.valves.MIN_SIM and not kw_hits:
            return [], []

        # ---- qualifica e funde por RRF ----
        rk = self.valves.RRF_K
        fused = {}
        for cid in set(sem_rank) | set(kw_rank):
            if cid not in id_pos:
                continue  # nao pertence ao user atual (filtrado no carregamento)
            if cos_by_id.get(cid, 0.0) < self.valves.MIN_SIM and cid not in kw_hits:
                continue
            s = 0.0
            if cid in sem_rank:
                s += 1.0 / (rk + sem_rank[cid])
            if cid in kw_rank:
                s += 1.0 / (rk + kw_rank[cid])
            fused[cid] = s

        ordered = sorted(fused, key=lambda c: fused[c], reverse=True)

        chosen, srcs, used = [], [], 0
        for cid in ordered:
            if len(chosen) >= self.valves.TOP_K:
                break
            i = id_pos.get(cid)
            if i is None:
                continue
            # Nao injeta a conversa atual (seria circular)
            if exclude_chat and _CACHE["chats"][i] == exclude_chat:
                continue
            user_msg = _CACHE["user_msgs"][i]
            asst_msg = _CACHE["asst_msgs"][i]
            ts = _CACHE["timestamps"][i]
            label = _fmt_date(ts)
            # Monta bloco do dialogo
            if asst_msg:
                block_text = f"Voce: {user_msg}\nNous: {asst_msg}"
            else:
                block_text = f"Voce: {user_msg}"
            # Trunca se necessario
            if used + len(block_text) > self.valves.MAX_CONTEXT_CHARS:
                remain = max(0, self.valves.MAX_CONTEXT_CHARS - used)
                block_text = block_text[:remain]
            if not block_text:
                continue
            chosen.append((label, block_text))
            srcs.append(_CACHE["chats"][i])
            used += len(block_text)

        return chosen, srcs

    # ---- ciclo --------------------------------------------------------------

    async def inlet(self, body: dict, __user__: Optional[dict] = None,
                    __event_emitter__=None, __metadata__: Optional[dict] = None) -> dict:
        if not self.valves.ENABLED:
            return body

        messages = body.get("messages", [])
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    user_text = c
                elif isinstance(c, list):
                    user_text = " ".join(
                        p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                break
        if not user_text.strip():
            return body

        user_id = (__user__ or {}).get("id") or None
        # No Open WebUI o chat_id chega por __metadata__, nao na raiz de body.
        current_chat = (__metadata__ or {}).get("chat_id") or body.get("chat_id") or None

        try:
            chunks, srcs = self._retrieve(user_text, user_id=user_id, exclude_chat=current_chat)
        except Exception:
            return body
        if not chunks:
            return body

        block = (
            "[Historico do Nous] Trechos de conversas anteriores que podem ser "
            "relevantes para a pergunta atual. Use-os se ajudarem a responder:\n\n"
            + "\n\n".join(f"--- ({label}) ---\n{text}" for label, text in chunks)
        )
        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + block) if base else block
        else:
            messages.insert(0, {"role": "system", "content": block})
        body["messages"] = messages

        uid = (__user__ or {}).get("id") or "_"
        dates = [label for label, _ in chunks]
        self._pending_dates[uid] = dates

        # So' na primeira mensagem da conversa: repetir a cada pergunta cansa.
        if __event_emitter__ and sum(1 for m in messages if m.get("role") == "user") == 1:
            await _aviso_rapido(__event_emitter__,
                                f"Nous encontrou contexto em {len(set(srcs))} conversa(s) anterior(es).")
        return body

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        uid = (__user__ or {}).get("id") or "_"
        self._pending_dates.pop(uid, None)
        return body
