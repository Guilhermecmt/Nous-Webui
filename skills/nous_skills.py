# -*- coding: utf-8 -*-
"""
title: Nous Skills
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Habilidades: o Nous aprende COMO voce gosta que as coisas sejam feitas e
  reaplica sozinho. Depois de acertar algo numa conversa, diga "aprenda isso"
  (ou "salve como habilidade"): o modelo local resume o passo a passo num
  arquivo em NousData/skills. Nas proximas conversas, quando o pedido combinar
  com o "quando usar" de uma habilidade, ela entra no contexto.
  Complementa a Memoria (fatos sobre voce) com procedimentos.
"""
import os
import re
import json
import time
import asyncio
import hashlib
import datetime
import unicodedata
from typing import Optional

from pydantic import BaseModel, Field

# Mesmo num_ctx do chat (monitor/register_model_ctx.py): com outro valor o
# Ollama recarrega o modelo (no 0.30 o padrao chega a 256k e estoura a VRAM).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))

try:
    import numpy as np
except Exception:
    np = None

try:
    import requests
except Exception:
    requests = None

_LEARN = re.compile(
    r"\b(aprend[ae] (?:isso|isto|como|esse jeito|este jeito)|"
    r"salv[ae] (?:isso |isto )?como (?:uma )?habilidade|"
    r"guard[ae] (?:esse|este|o) (?:jeito|passo a passo|procedimento|m[eé]todo)|"
    r"memoriz[ae] (?:esse|este|o) (?:jeito|passo a passo|procedimento))\b|^/aprender\b", re.I)
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")
_STOP = {"como", "para", "por", "que", "qual", "quando", "onde", "uma", "uns", "com",
         "sem", "dos", "das", "nos", "nas", "isso", "essa", "esse", "este", "esta",
         "mais", "muito", "usuario", "pedir", "pede", "quer", "sobre", "fazer"}

_DISTILL = """Voce transforma uma conversa numa HABILIDADE reutilizavel: o jeito que o usuario
quer que uma tarefa seja feita, para o assistente repetir no futuro sem ele precisar explicar.

Conversa (a ultima mensagem e' o pedido para aprender):
\"\"\"{conversa}\"\"\"

Responda SO' com JSON:
{{"nome": "nome curto da habilidade (ate 6 palavras, em portugues normal)",
  "quando_usar": "uma frase: em que TIPO de pedido aplicar",
  "passos": ["regra ou passo 1", "regra ou passo 2", "..."]}}

Regras:
- GENERALIZE: a habilidade vale para pedidos parecidos no futuro. Nada de nomes de
  pessoas, valores ou datas da conversa em "nome" e "quando_usar"; nos passos, use
  [cliente], [valor], [data] no lugar deles.
- Copie EXATAMENTE os textos fixos que o usuario definiu (assinatura, saudacao, formato).
- Nao invente preferencias que nao aparecem na conversa. Escreva em portugues.

Exemplo: conversa sobre um relatorio de vendas de marco em que o usuario pediu tabela e 3
destaques ->
{{"nome": "Relatorio de vendas", "quando_usar": "quando o usuario pedir um relatorio ou resumo de vendas",
  "passos": ["Abrir com uma tabela Produto | Quantidade | Receita", "Terminar com 3 destaques em topicos",
             "Valores em R$ com duas casas decimais"]}}"""


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


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_-]", "", s or "")[:64]


def _slug(text):
    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:48] or "habilidade"


def _parse(text):
    meta, body = {}, text
    m = re.match(r"﻿?---\s*\n(.*?)\n---\s*\n?(.*)\Z", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip()
        body = m.group(2)
    return {"nome": meta.get("nome") or meta.get("name") or "",
            "quando_usar": meta.get("quando_usar") or meta.get("description") or "",
            "corpo": body.strip()}


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _tokens(s):
    t = unicodedata.normalize("NFD", (s or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return {w for w in re.findall(r"[a-z0-9]{4,}", t) if w not in _STOP}


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga as habilidades.")
        TOP_K: int = Field(default=1, description="Quantas habilidades injetar por pergunta.")
        MIN_SIM: float = Field(default=0.55, description="Similaridade minima (0-1) para uma habilidade virar candidata; o modelo confirma.")
        STRICT_SIM: float = Field(default=0.68, description="Sem modelo de chat para confirmar, so' usa acima desta similaridade.")
        EMBED_MODEL: str = Field(default="nomic-embed-text", description="Modelo de embeddings (Ollama).")
        OLLAMA_URL: str = Field(default="", description="URL do Ollama. Vazio = OLLAMA_BASE_URL ou 127.0.0.1:11434.")

    def __init__(self):
        self.valves = self.Valves()
        self._emb = {}    # caminho -> (mtime, vetor normalizado)
        self._learned = {}  # hash(usuario+conversa) -> (quando, texto): regenerar nao duplica

    def _ollama(self):
        return (self.valves.OLLAMA_URL
                or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    def _embed(self, text):
        if requests is None or np is None:
            return None
        try:
            r = requests.post(f"{self._ollama()}/api/embeddings",
                              json={"model": self.valves.EMBED_MODEL, "prompt": text[:4000]}, timeout=30)
            v = r.json().get("embedding") if r.status_code == 200 else None
            if not v:
                return None
            a = np.asarray(v, dtype="float32")
            return a / (np.linalg.norm(a) or 1.0)
        except Exception:
            return None

    def _dir(self, uid):
        return os.path.join(_data_dir(), "skills", _safe(uid))

    def _skills(self, uid):
        d = self._dir(uid)
        if not os.path.isdir(d):
            return []
        out = []
        for f in sorted(os.listdir(d)):
            if f.endswith(".md"):
                p = os.path.join(d, f)
                try:
                    s = _parse(open(p, encoding="utf-8").read())
                except Exception:
                    continue
                if s["quando_usar"] and s["corpo"]:
                    s["path"] = p
                    out.append(s)
        return out

    def _vec(self, s):
        mt = os.path.getmtime(s["path"])
        hit = self._emb.get(s["path"])
        if hit and hit[0] == mt:
            return hit[1]
        v = self._embed(f"search_document: {s['nome']}. {s['quando_usar']}")
        if v is not None:
            self._emb[s["path"]] = (mt, v)
        return v

    def _match(self, uid, msg, chat_model=""):
        skills = self._skills(uid)
        if not skills:
            return []
        q = self._embed("search_query: " + msg)
        scored = []
        for s in skills:
            v = self._vec(s) if q is not None else None
            if q is not None and v is not None and v.shape == q.shape:
                sim = float(v @ q)
                if sim >= self.valves.MIN_SIM:
                    scored.append((sim, s))
            else:  # sem embeddings: palavras em comum com o "quando usar"
                common = _tokens(msg) & _tokens(s["quando_usar"] + " " + s["nome"])
                if len(common) >= 2:
                    scored.append((0.6 + 0.05 * len(common), s))
        if not scored:
            return []
        scored.sort(key=lambda x: -x[0])
        cands = scored[:3]
        # Embeddings de frases curtas sao ruidosos ("capital da Australia" ~0.57 vs
        # uma habilidade de cobranca): o modelo do chat, ja carregado, confirma.
        ok = self._confirm(msg, [s for _, s in cands], chat_model)
        if ok is None:
            ok = [s for sim, s in cands if sim >= self.valves.STRICT_SIM]
        return ok[: max(1, self.valves.TOP_K)]

    def _confirm(self, msg, cands, chat_model):
        """Lista das candidatas que se aplicam, ou None se nao ha modelo para julgar."""
        model = self._model(chat_model)
        if not model:
            return None
        lista = "\n".join(f"{i + 1}) {s['nome']}: usar {s['quando_usar']}" for i, s in enumerate(cands))
        prompt = (f"Pedido do usuario: \"{msg[:600]}\"\n\nHabilidades salvas:\n{lista}\n\n"
                  "Quais habilidades se aplicam DIRETAMENTE a este pedido? Responda em JSON: "
                  "{\"aplicam\": [numeros]} (lista vazia se nenhuma).")
        # Saida estruturada: sem ela o qwen3 "pensa em voz alta" mesmo com think=false
        schema = {"type": "object", "required": ["aplicam"],
                  "properties": {"aplicam": {"type": "array", "items": {"type": "integer"}}}}
        try:
            r = requests.post(f"{self._ollama()}/api/generate",
                              json={"model": model, "prompt": prompt, "stream": False, "think": False,
                                    "format": schema,
                                    "options": {"temperature": 0, "num_predict": 40, "num_ctx": NUM_CTX}}, timeout=60)
            picks = json.loads(r.json().get("response") or "{}").get("aplicam") or []
        except Exception:
            return None
        picks = [int(n) for n in picks if isinstance(n, (int, float))]
        return [cands[n - 1] for n in picks if 1 <= n <= len(cands)]

    # ---------------------------------------------------------- aprender
    def _model(self, chat_model):
        try:
            names = [m.get("name", "") for m in
                     requests.get(f"{self._ollama()}/api/tags", timeout=5).json().get("models", [])]
        except Exception:
            return None
        if chat_model in names or (chat_model + ":latest") in names:
            return chat_model
        return next((n for n in names if "/" not in n and not any(p in n.lower() for p in _EMBED)), None)

    def _learn(self, uid, messages, chat_model):
        model = self._model(chat_model)
        if not model:
            return ("[Nous Skills] O usuario pediu para aprender, mas nao ha modelo local "
                    "instalado para resumir a habilidade. Avise que nada foi salvo.")
        parts = []
        for m in messages[-12:]:
            if m.get("role") in ("user", "assistant"):
                who = "Usuario" if m["role"] == "user" else "Assistente"
                parts.append(f"{who}: {_text(m)[:1500]}")
        r = requests.post(f"{self._ollama()}/api/generate",
                          json={"model": model, "prompt": _DISTILL.format(conversa="\n\n".join(parts)),
                                "stream": False, "format": "json", "think": False,
                                "options": {"temperature": 0.2, "num_ctx": NUM_CTX}}, timeout=180)
        r.raise_for_status()
        d = json.loads(r.json().get("response") or "{}")
        nome = re.sub(r"[_\s]+", " ", d.get("nome") or "").strip()[:80]
        nome = nome[:1].upper() + nome[1:]
        quando = (d.get("quando_usar") or "").strip()[:300]
        passos = d.get("passos")
        if isinstance(passos, str):
            passos = [p for p in passos.splitlines() if p.strip()]
        # numera de novo: modelos pequenos mandam "1. ..." dentro da lista ("1. 1. ...")
        passos = [re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", str(p)).strip() for p in (passos or [])]
        passos = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(p for p in passos if p))
        if not (nome and quando and passos):
            return ("[Nous Skills] Nao consegui resumir uma habilidade desta conversa. "
                    "Peca ao usuario para explicar em uma frase o que deve ser lembrado.")
        d_ = self._dir(uid)
        os.makedirs(d_, exist_ok=True)
        base, i = _slug(nome), 2
        sid = base
        while os.path.exists(os.path.join(d_, sid + ".md")):
            sid, i = f"{base}-{i}", i + 1
        one = lambda v: re.sub(r"\s+", " ", v).strip()  # noqa: E731
        with open(os.path.join(d_, sid + ".md"), "w", encoding="utf-8") as f:
            f.write(f"---\nnome: {one(nome)}\nquando_usar: {one(quando)}\norigem: conversa\n"
                    f"criado: {datetime.date.today().isoformat()}\n---\n\n{passos}\n")
        return (f"[Nous Skills] Habilidade salva: \"{nome}\" (usar {quando[0].lower() + quando[1:]}). "
                "Confirme ao usuario em uma ou duas frases e diga que ele pode revisar em "
                "Recursos > Habilidades.")

    # ---------------------------------------------------------- ciclo
    async def inlet(self, body: dict, __user__: Optional[dict] = None,
                    __event_emitter__=None) -> dict:
        if not self.valves.ENABLED or requests is None:
            return body
        uid = (__user__ or {}).get("id")
        messages = body.get("messages", [])
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        msg = _text(last) if last else ""
        if not uid or not msg.strip():
            return body

        async def status(desc, done=True):
            if __event_emitter__:
                try:
                    await __event_emitter__({"type": "status", "data": {"description": desc, "done": done}})
                except Exception:
                    pass

        if _LEARN.search(msg):
            convo = "\n".join(_text(m) for m in messages if m.get("role") in ("user", "assistant"))
            key = hashlib.sha1(f"{uid}\n{convo}".encode("utf-8")).hexdigest()
            t = time.time()
            self._learned = {k: v for k, v in self._learned.items() if t - v[0] < 86400}
            if key in self._learned:
                text = self._learned[key][1]
            else:
                await status("Aprendendo a habilidade...", False)
                try:
                    text = await asyncio.to_thread(self._learn, uid, messages, body.get("model") or "")
                    if text.startswith("[Nous Skills] Habilidade salva"):
                        self._learned[key] = (t, text)
                except Exception as e:
                    text = f"[Nous Skills] Falhou ao salvar a habilidade ({e}). Avise o usuario."
                await status("Habilidade salva." if "salva:" in text else "Nada foi salvo.")
        else:
            try:
                found = await asyncio.to_thread(self._match, uid, msg, body.get("model") or "")
            except Exception:
                found = []
            if not found:
                return body
            text = "\n\n".join(
                f"[Habilidade do Nous: {s['nome']}] O usuario ja ensinou ao Nous como fazer "
                f"isto ({s['quando_usar']}). Siga estes passos no que se aplicar ao pedido:\n{s['corpo']}"
                for s in found)
            await status("Usando a habilidade: " + ", ".join(s["nome"] for s in found))

        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + text) if base else text
        else:
            messages.insert(0, {"role": "system", "content": text})
        body["messages"] = messages
        return body
