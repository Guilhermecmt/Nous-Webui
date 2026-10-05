# -*- coding: utf-8 -*-
"""
title: Nous Files
author: Guilherme (Nous)
version: 0.1.0
required_open_webui_version: 0.5.0
license: MIT
description: >
  Da' ao Nous acesso aos SEUS arquivos locais. A cada pergunta, busca os trechos
  mais relevantes da sua pasta (Obsidian, anotacoes...) e os injeta no contexto -
  busca HIBRIDA: semantica (embeddings via Ollama) + palavra-chave (FTS5),
  fundidas por Reciprocal Rank Fusion. 100% local; nada sai da maquina.

  O indice e' mantido por files/index_files.py (processo em segundo plano). Este
  filtro so' LE o indice (nous_files.sqlite3 no NousData) e cita o arquivo de
  origem. Funciona em par com a memoria pessoal (Nous Memory).
"""
import os
import re
import json
import sqlite3
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

DB_NAME = "nous_files.sqlite3"
CONFIG_NAME = "nous_files.json"

# cache de modulo: evita reler o indice inteiro a cada mensagem
_CACHE = {"mtime": None, "ids": [], "paths": [], "headings": [], "texts": [], "mat": None}


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
    filtro serviria um indice velho ate o proximo checkpoint do WAL."""
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


# palavras vazias (PT + algumas EN): nao servem para busca por palavra-chave e,
# se mantidas, batem em quase tudo (ex.: "como" em "Raspberry Pi como servidor").
_STOP = {
    "como", "para", "por", "porque", "que", "qual", "quais", "quando", "onde",
    "quem", "uso", "usar", "meu", "minha", "meus", "minhas", "seu", "sua", "suas",
    "com", "sem", "dos", "das", "nos", "nas", "num", "numa", "isso", "essa",
    "esse", "este", "esta", "isto", "aqui", "ali", "mais", "menos", "muito",
    "tem", "ter", "foi", "ser", "sao", "esta", "estao", "ele", "ela", "eles",
    "elas", "voce", "nao", "sim", "fazer", "faco", "sobre",
    "the", "and", "for", "you", "your", "are", "was", "with", "from", "this",
    "that", "what", "how", "when", "where",
}


def _tokens(text):
    toks = re.findall(r"[0-9A-Za-zÀ-ÿ]{3,}", (text or "").lower())
    seen, out = set(), []
    for t in toks:
        if t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:12]


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga o acesso aos arquivos.")
        FOLDER: str = Field(default="", description="Pasta a indexar (ex.: seu vault do Obsidian). Vazio = pasta padrao 'Nous' em Documentos.")
        TOP_K: int = Field(default=4, description="Quantos trechos injetar por pergunta.")
        MIN_SIM: float = Field(default=0.70, description="Similaridade minima (0-1) para considerar relevante. O nomic-embed-text da ~0.68 para quase qualquer texto PT-PT; abaixo de 0.70 entram notas irrelevantes em perguntas que nada tem a ver com seus arquivos.")
        MAX_CONTEXT_CHARS: int = Field(default=4000, description="Limite total de texto injetado.")
        RRF_K: int = Field(default=60, description="Constante do Reciprocal Rank Fusion.")
        EMBED_MODEL: str = Field(default="nomic-embed-text", description="Modelo de embeddings (Ollama).")
        OLLAMA_URL: str = Field(default="", description="URL do Ollama. Vazio = OLLAMA_BASE_URL ou 127.0.0.1:11434.")

    def __init__(self):
        self.valves = self.Valves()
        self._pending_srcs = {}  # user_id -> [src, ...]

    # ------- infra -------
    def _ollama(self):
        return (self.valves.OLLAMA_URL
                or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    def _sync_folder_config(self):
        """Se o usuario apontou uma pasta pelo valve, grava no config p/ o indexador."""
        folder = (self.valves.FOLDER or "").strip()
        if not folder:
            return
        cfg = os.path.join(_data_dir(), CONFIG_NAME)
        try:
            cur = {}
            if os.path.isfile(cfg):
                with open(cfg, encoding="utf-8-sig") as f:
                    cur = json.load(f) or {}
            if cur.get("folder") != folder:
                cur["folder"] = folder
                os.makedirs(_data_dir(), exist_ok=True)
                with open(cfg, "w", encoding="utf-8") as f:
                    json.dump(cur, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _embed(self, text):
        if requests is None:
            return None
        try:
            r = requests.post(
                f"{self._ollama()}/api/embeddings",
                json={"model": self.valves.EMBED_MODEL, "prompt": text[:8000]},
                timeout=30,
            )
            if r.status_code != 200:
                return None
            v = r.json().get("embedding")
            return v if v else None
        except Exception:
            return None

    def _load_index(self):
        """Carrega (com cache) ids/paths/headings/texts e a matriz de embeddings."""
        db = _db_path()
        if not os.path.isfile(db):
            return False
        mtime = _db_sig(db)
        if mtime is None:
            return False
        if _CACHE["mtime"] == mtime and (_CACHE["ids"] or _CACHE["mat"] is not None):
            return True
        ids, paths, headings, texts, vecs = [], [], [], [], []
        try:
            cx = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=15)
        except Exception:
            cx = sqlite3.connect(db, timeout=15)
        try:
            for cid, path, heading, text, emb in cx.execute(
                "SELECT id, path, heading, text, embedding FROM chunks"
            ):
                ids.append(cid); paths.append(path)
                headings.append(heading or ""); texts.append(text or "")
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
        _CACHE.update(mtime=mtime, ids=ids, paths=paths, headings=headings,
                      texts=texts, mat=mat)
        return bool(ids)

    def _keyword_ranks(self, query):
        """rowid -> rank por BM25 (FTS5). {} se nada."""
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
                "SELECT rowid, bm25(chunks_fts) FROM chunks_fts "
                "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT 25",
                (match,),
            ).fetchall()
        except Exception:
            return {}, set()
        finally:
            cx.close()
        ranks = {rowid: i for i, (rowid, _) in enumerate(rows)}
        return ranks, set(ranks.keys())

    def _retrieve(self, query):
        if not self._load_index():
            return [], []
        ids = _CACHE["ids"]
        id_pos = {cid: i for i, cid in enumerate(ids)}

        # ---- semantica ----
        sem_rank, cos_by_id = {}, {}
        best_sim = 0.0
        mat = _CACHE["mat"]
        if mat is not None:
            qv = self._embed("search_query: " + query)  # prefixo do nomic-embed-text
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
            return [], []  # nada relevante: nao polui o contexto

        # ---- qualifica (cosine >= MIN_SIM OU hit de palavra-chave) e funde (RRF) ----
        rk = self.valves.RRF_K
        fused = {}
        for cid in set(sem_rank) | set(kw_rank):
            if cos_by_id.get(cid, 0.0) < self.valves.MIN_SIM and cid not in kw_hits:
                continue  # nao relevante o bastante -> fora (evita ruido)
            s = 0.0
            if cid in sem_rank:
                s += 1.0 / (rk + sem_rank[cid])
            if cid in kw_rank:
                s += 1.0 / (rk + kw_rank[cid])
            fused[cid] = s
        ordered = sorted(fused, key=lambda c: fused[c], reverse=True)

        chosen, used = [], 0
        srcs = []
        for cid in ordered:
            if len(chosen) >= self.valves.TOP_K:
                break
            i = id_pos.get(cid)
            if i is None:
                continue
            text = _CACHE["texts"][i]
            if used + len(text) > self.valves.MAX_CONTEXT_CHARS:
                text = text[: max(0, self.valves.MAX_CONTEXT_CHARS - used)]
            if not text:
                continue
            name = os.path.basename(_CACHE["paths"][i])
            head = _CACHE["headings"][i]
            label = f"{name} > {head}" if head else name
            chosen.append((label, text))
            srcs.append(name)
            used += len(text)
        return chosen, srcs

    # ------- ciclo -------
    async def inlet(self, body: dict, __user__: Optional[dict] = None, __event_emitter__=None) -> dict:
        if not self.valves.ENABLED:
            return body
        self._sync_folder_config()

        messages = body.get("messages", [])
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    user_text = c
                elif isinstance(c, list):
                    user_text = " ".join(
                        p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"
                    )
                break
        if not user_text.strip():
            return body

        try:
            chunks, srcs = self._retrieve(user_text)
        except Exception:
            return body
        if not chunks:
            return body

        block = (
            "[Arquivos do Nous] Trechos relevantes dos arquivos locais do usuario. "
            "Use-os para responder quando ajudarem e cite o arquivo de origem:\n\n"
            + "\n\n".join(f"--- ({label}) ---\n{text}" for label, text in chunks)
        )
        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + block) if base else block
        else:
            messages.insert(0, {"role": "system", "content": block})
        body["messages"] = messages

        uniq = list(dict.fromkeys(srcs))
        uid = (__user__ or {}).get("id") or "_"
        self._pending_srcs[uid] = uniq

        if __event_emitter__:
            try:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": "Nous consultou seus arquivos: " + ", ".join(uniq),
                             "done": True},
                })
            except Exception:
                pass
        return body

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        uid = (__user__ or {}).get("id") or "_"
        self._pending_srcs.pop(uid, None)
        return body
