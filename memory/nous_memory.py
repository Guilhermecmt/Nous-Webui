"""
title: Nous Memory
author: Nous
version: 0.2.0
required_open_webui_version: 0.5.0
description: Memoria pessoal persistente, 100% local. O Nous lembra de voce entre conversas.
"""

# Como funciona (mesma ideia do pipe de imagem, mas como Filter global):
#   inlet  -> antes do modelo responder, injeta "o que o Nous ja sabe sobre voce".
#   outlet -> depois da resposta, extrai fatos duraveis com o Ollama local e salva.
# Tudo fica num SQLite dentro do DATA_DIR (NousData), que e' gitignored.

import os
import re
import json
import time
import datetime
import sqlite3
import aiohttp
from typing import Optional
from pydantic import BaseModel, Field


def _data_dir() -> str:
    """Mesma pasta de dados do Nous/Open WebUI (fora do site-packages, gitignored)."""
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def _get_active_persona(user_id: str) -> str:
    """Le a persona ativa do usuario em nous_active_persona.json (escrito pela API)."""
    try:
        path = os.path.join(_data_dir(), "nous_active_persona.json")
        with open(path, encoding="utf-8-sig") as f:
            return (json.load(f) or {}).get(user_id, "default")
    except Exception:
        return "default"


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga a memoria.")
        EXTRACT: bool = Field(default=True, description="Extrair novos fatos automaticamente.")
        CLOUD_MODELS_GET_MEMORY: bool = Field(
            default=False,
            description=(
                "Injetar memoria em modelos de nuvem (ids com '/'). "
                "Desativado por padrao: conversas em nuvem nao enviam dados pessoais para servidores externos."
            ),
        )
        OLLAMA_BASE: str = Field(default="http://127.0.0.1:11434")
        EXTRACT_MODEL: str = Field(
            default="gemma4:12b",
            description="Modelo local que extrai os fatos. Pode ser um menor/rapido p/ economizar GPU.",
        )
        MAX_MEMORIES: int = Field(default=200, description="Maximo de memorias injetadas por conversa.")
        MIN_USER_CHARS: int = Field(default=12, description="Ignora mensagens curtas demais.")
        MAX_FACTS_PER_TURN: int = Field(default=5, description="Maximo de fatos novos por mensagem.")

    def __init__(self):
        self.valves = self.Valves()
        self.db_path = os.path.join(_data_dir(), "nous_memory.sqlite3")
        self._init_db()

    # ------------------------------------------------------------------ storage
    def _conn(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        try:
            c = self._conn()
            c.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    TEXT    NOT NULL,
                    text       TEXT    NOT NULL,
                    norm       TEXT    NOT NULL,
                    created_at INTEGER NOT NULL
                )"""
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_user ON memories(user_id)")
            # Fase 5: coluna persona (migracao segura — falha silenciosamente se ja' existe)
            try:
                c.execute("ALTER TABLE memories ADD COLUMN persona TEXT DEFAULT 'default'")
            except Exception:
                pass
            c.commit()
            c.close()
        except Exception:
            pass

    def _get_memories(self, user_id: str, persona: str = "default"):
        try:
            c = self._conn()
            try:
                rows = c.execute(
                    "SELECT text FROM memories WHERE user_id=? "
                    "AND (persona=? OR persona IS NULL) "
                    "ORDER BY created_at DESC LIMIT ?",
                    (user_id, persona, int(self.valves.MAX_MEMORIES)),
                ).fetchall()
            except Exception:
                rows = c.execute(
                    "SELECT text FROM memories WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                    (user_id, int(self.valves.MAX_MEMORIES)),
                ).fetchall()
            c.close()
            return [r[0] for r in rows]
        except Exception:
            return []

    def _existing_norms(self, user_id: str, persona: str = "default"):
        try:
            c = self._conn()
            try:
                rows = c.execute(
                    "SELECT norm FROM memories WHERE user_id=? AND (persona=? OR persona IS NULL)",
                    (user_id, persona),
                ).fetchall()
            except Exception:
                rows = c.execute("SELECT norm FROM memories WHERE user_id=?", (user_id,)).fetchall()
            c.close()
            return {r[0] for r in rows}
        except Exception:
            return set()

    def _add_memories(self, user_id: str, facts, persona: str = "default") -> int:
        if not facts:
            return 0
        existing = self._existing_norms(user_id, persona)
        added = 0
        try:
            c = self._conn()
            now = int(time.time())
            for f in facts:
                f = (f or "").strip()
                norm = _normalize(f)
                if not norm or norm in existing:
                    continue
                try:
                    c.execute(
                        "INSERT INTO memories(user_id, text, norm, created_at, persona) VALUES(?,?,?,?,?)",
                        (user_id, f, norm, now, persona),
                    )
                except Exception:
                    c.execute(
                        "INSERT INTO memories(user_id, text, norm, created_at) VALUES(?,?,?,?)",
                        (user_id, f, norm, now),
                    )
                existing.add(norm)
                added += 1
            c.commit()
            c.close()
        except Exception:
            pass
        return added

    # -------------------------------------------------------------------- hooks
    async def inlet(self, body: dict, __user__: Optional[dict] = None, __event_emitter__=None) -> dict:
        if not self.valves.ENABLED:
            return body
        # Modelos de nuvem tem id com '/' (ex.: "deepseek-ai/deepseek-r1").
        # Por padrao nao injetamos dados pessoais em requisicoes externas.
        model_id = body.get("model", "")
        if "/" in model_id and not self.valves.CLOUD_MODELS_GET_MEMORY:
            return body
        user_id = (__user__ or {}).get("id") or "default"
        persona = _get_active_persona(user_id)
        mems = self._get_memories(user_id, persona)
        if not mems:
            return body

        block = (
            "[Memoria do Nous] Fatos conhecidos sobre o usuario, lembrados de "
            "conversas anteriores. Use-os naturalmente quando forem relevantes:\n"
            + "\n".join(f"- {m}" for m in mems)
        )
        messages = body.get("messages", [])
        # IMPORTANTE: mesclar no system message EXISTENTE (nao criar um 2o).
        # O Open WebUI/Ollama costuma manter apenas o primeiro system message;
        # um 2o seria descartado e a memoria se perderia.
        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + block) if base else block
        else:
            messages.insert(0, {"role": "system", "content": block})
        body["messages"] = messages

        if __event_emitter__:
            try:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": f"Nous lembrou de {len(mems)} detalhe(s) sobre voce.",
                             "done": True},
                })
            except Exception:
                pass
        return body

    async def outlet(self, body: dict, __user__: Optional[dict] = None, __event_emitter__=None) -> dict:
        if not (self.valves.ENABLED and self.valves.EXTRACT):
            return body
        user_id = (__user__ or {}).get("id") or "default"
        persona = _get_active_persona(user_id)
        user_text, assistant_text = _last_exchange(body.get("messages", []))
        if len(user_text) < int(self.valves.MIN_USER_CHARS):
            return body
        try:
            existing = self._get_memories(user_id, persona)
            facts = await self._extract(user_text, assistant_text, existing)
            added = self._add_memories(user_id, facts, persona)
            if added and __event_emitter__:
                await __event_emitter__(
                    {
                        "type": "status",
                        "data": {
                            "description": f"Nous memorizou {added} novo(s) detalhe(s) sobre voce.",
                            "done": True,
                        },
                    }
                )
        except Exception:
            pass
        return body

    # ----------------------------------------------------------------- extract
    async def _extract(self, user_text: str, assistant_text: str, existing=None):
        today = datetime.date.today().isoformat()
        known = ""
        if existing:
            known = ("Ja sei o seguinte sobre o usuario (NAO repita nem reescreva "
                     "com outras palavras):\n"
                     + "\n".join(f"- {m}" for m in existing[:50]) + "\n\n")
        prompt = (
            f"Hoje e' {today}. Leia a conversa e extraia o que vale a pena LEMBRAR "
            "sobre o usuario para conversas futuras:\n"
            "- fatos duraveis: nome, onde mora, trabalho, familia, gostos, metas, restricoes;\n"
            "- acontecimentos e planos que o usuario contou sobre a propria vida "
            f"(inclua a data quando fizer sentido, ex.: 'Em {today}, ...').\n"
            "NAO registre: perguntas, pedidos de tarefa (escrever/traduzir/gerar/codar), "
            "fatos gerais do mundo, nem falas do assistente.\n\n"
            f"{known}"
            "Responda APENAS com um array JSON de frases curtas em portugues "
            f"(no maximo {int(self.valves.MAX_FACTS_PER_TURN)}). "
            "Se nao houver nada util, responda [].\n\n"
            f"Usuario: {user_text}\n"
            f"Assistente: {assistant_text}\n\n"
            "JSON:"
        )
        payload = {
            "model": self.valves.EXTRACT_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
            # 5m para nao descarregar o modelo logo apos a extracao de memoria
            # (em geral e' o mesmo modelo da conversa; descarregar anularia o
            # keep_alive da conversa e forcaria um recarregamento lento).
            "keep_alive": "5m",
        }
        url = self.valves.OLLAMA_BASE.rstrip("/") + "/api/generate"
        async with aiohttp.ClientSession() as s:
            async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as r:
                data = await r.json()
        return _parse_facts((data or {}).get("response", ""))[: int(self.valves.MAX_FACTS_PER_TURN)]


# --------------------------------------------------------------------- helpers
def _normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[.;:!?]+$", "", s)
    return s


def _flatten(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for p in content or []:
        if isinstance(p, dict) and p.get("type") == "text":
            parts.append(p.get("text", ""))
    return " ".join(parts)


def _last_exchange(messages):
    user_text, assistant_text = "", ""
    for m in reversed(messages or []):
        role, content = m.get("role"), _flatten(m.get("content", ""))
        if role == "assistant" and not assistant_text:
            assistant_text = content
        elif role == "user" and not user_text:
            user_text = content
        if user_text and assistant_text:
            break
    return user_text.strip(), assistant_text.strip()


def _parse_facts(raw: str):
    raw = (raw or "").strip()
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    try:
        arr = json.loads(raw)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    return []
