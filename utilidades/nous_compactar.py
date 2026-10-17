"""
title: Nous Compactar
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Conversas longas nao estouram mais a memoria do modelo. Quando a conversa
  passa de ~60% do contexto (16k tokens nos modelos locais), o inicio vira um
  resumo (nomes, numeros, decisoes e pendencias) e so' as ultimas mensagens vao
  inteiras. Sem isto o Ollama corta o comeco em silencio e o modelo "esquece",
  ou a resposta sai vazia. O resumo fica em cache: nao e' refeito a cada mensagem.
"""
import os
import time
import asyncio
import hashlib
from typing import Optional

from pydantic import BaseModel, Field

try:
    import requests
except Exception:
    requests = None

# Mesmo num_ctx do chat (monitor/register_model_ctx.py).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")
CHARS_PER_TOKEN = 3.5  # portugues, aproximado

_PROMPT = """Resuma o INICIO de uma conversa entre um usuario e o assistente Nous, para o
assistente continuar a conversa sem perder o fio. Em ate 15 topicos curtos, em portugues:
- o que o usuario quer e o contexto dele;
- nomes, numeros, datas, valores e decisoes ja tomadas;
- o que ficou pendente ou combinado.
Nao invente nada. So' os topicos, sem introducao.

CONVERSA:
{conversa}"""


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=-10, description="Roda antes dos outros filtros (que acrescentam contexto).")
        ENABLED: bool = Field(default=True, description="Liga/desliga a compactacao de conversas longas.")
        LIMITE: float = Field(default=0.60, description="Fracao do contexto a partir da qual o inicio vira resumo.")
        MANTER: int = Field(default=6, description="Quantas mensagens recentes vao inteiras.")
        OLLAMA_URL: str = Field(default="", description="URL do Ollama. Vazio = OLLAMA_BASE_URL ou 127.0.0.1:11434.")

    def __init__(self):
        self.valves = self.Valves()
        self._cache = {}  # hash do trecho resumido -> (quando, resumo)

    def _ollama(self):
        return (self.valves.OLLAMA_URL or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    def _model(self, chat_model):
        try:
            names = [m.get("name", "") for m in
                     requests.get(f"{self._ollama()}/api/tags", timeout=5).json().get("models", [])]
        except Exception:
            return None
        if chat_model in names or (chat_model + ":latest") in names:
            return chat_model
        return next((n for n in names if "/" not in n and not any(p in n.lower() for p in _EMBED)), None)

    def _summarize(self, msgs, chat_model, previous=None):
        """Resume msgs; com `previous`, atualiza um resumo anterior so' com as
        mensagens novas (nao reprocessa a conversa inteira a cada turno)."""
        model = self._model(chat_model)
        if not model:
            return None
        parts = []
        for m in msgs:
            who = "Usuario" if m.get("role") == "user" else "Nous"
            parts.append(f"{who}: {_text(m)}")
        budget = int(NUM_CTX * 0.5 * CHARS_PER_TOKEN)
        convo = "\n\n".join(parts)
        if len(convo) > budget:
            # o COMECO costuma ter o contexto (quem e', o que quer): fica sempre,
            # junto com o final do trecho; o meio e' o que se perde
            head = "\n\n".join(parts[:2])[: budget // 3]
            convo = head + "\n\n(...)\n\n" + convo[-(budget - len(head)):]
        if previous:
            convo = f"RESUMO DO QUE VEIO ANTES:\n{previous}\n\nMENSAGENS SEGUINTES:\n{convo}"
        r = requests.post(f"{self._ollama()}/api/generate",
                          json={"model": model, "prompt": _PROMPT.format(conversa=convo), "stream": False,
                                "think": False, "options": {"temperature": 0.2, "num_ctx": NUM_CTX}},
                          timeout=300)
        r.raise_for_status()
        return (r.json().get("response") or "").strip() or None

    async def inlet(self, body: dict, __user__: Optional[dict] = None,
                    __event_emitter__=None) -> dict:
        if not self.valves.ENABLED or requests is None:
            return body
        messages = body.get("messages", [])
        system = messages[0] if messages and messages[0].get("role") == "system" else None
        convo = messages[1:] if system else messages[:]
        keep = max(2, int(self.valves.MANTER))
        total = sum(len(_text(m)) for m in messages) / CHARS_PER_TOKEN
        if total < NUM_CTX * float(self.valves.LIMITE) or len(convo) <= keep + 1:
            return body

        older, recent = convo[:-keep], convo[-keep:]
        # Identidade da conversa = sua primeira mensagem. O cache guarda quantas
        # mensagens ja' estao no resumo; nos turnos seguintes so' entram as novas.
        ident = hashlib.sha1(_text(older[0]).encode("utf-8")).hexdigest()
        now = time.time()
        self._cache = {k: v for k, v in self._cache.items() if now - v[0] < 86400}
        _t, done_n, summary = self._cache.get(ident, (0, 0, None))
        if summary is None or done_n != len(older):
            if __event_emitter__:
                try:
                    await __event_emitter__({"type": "status", "data": {
                        "description": "Conversa longa: resumindo o inicio...", "done": False}})
                except Exception:
                    pass
            try:
                if summary and done_n < len(older):
                    summary = await asyncio.to_thread(self._summarize, older[done_n:],
                                                      body.get("model") or "", summary)
                else:
                    summary = await asyncio.to_thread(self._summarize, older, body.get("model") or "")
            except Exception:
                summary = None
            if not summary:
                return body  # sem resumo, deixa como esta (o Ollama corta o excesso)
            self._cache[ident] = (now, len(older), summary)

        block = ("[Resumo do inicio desta conversa] As mensagens mais antigas foram resumidas "
                 "para caber na memoria do modelo:\n" + summary)
        if system:
            base = (system.get("content") or "").rstrip()
            system = dict(system, content=(base + "\n\n" + block) if base else block)
        else:
            system = {"role": "system", "content": block}
        body["messages"] = [system] + recent
        if __event_emitter__:
            try:
                await __event_emitter__({"type": "status", "data": {
                    "description": f"Conversa longa: {len(older)} mensagens antigas resumidas.", "done": True}})
            except Exception:
                pass
        return body
