"""
title: Nous Leitura
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Le imagens e boletos no chat. Mande a foto de um recibo, nota ou print: o
  texto e' lido por OCR local (RapidOCR) e entregue ao modelo, inclusive aos
  que nao enxergam imagens. Linha digitavel de boleto (colada ou na foto) e'
  decodificada pelas regras FEBRABAN: banco, valor e vencimento saem dos
  digitos, sem "chute" do modelo, e digitos errados sao apontados.
"""
import os
import sys
import base64
import asyncio
import hashlib
from typing import Optional

from pydantic import BaseModel, Field

# O Open WebUI executa este codigo de um arquivo temporario: o
# register_utilidades.py grava aqui a pasta real de utilidades/ (leitura.py).
_UTIL_DIR = r"__NOUS_UTIL_DIR__"
if os.path.isdir(_UTIL_DIR) and _UTIL_DIR not in sys.path:
    sys.path.insert(0, _UTIL_DIR)

try:
    import leitura
except Exception:
    leitura = None


def _parts(m):
    c = m.get("content")
    if isinstance(c, str):
        return c, []
    texts, images = [], []
    for p in c or []:
        if not isinstance(p, dict):
            continue
        if p.get("type") == "text":
            texts.append(p.get("text", ""))
        elif p.get("type") == "image_url":
            url = (p.get("image_url") or {}).get("url", "")
            if url.startswith("data:image/") and "," in url:
                images.append(url.split(",", 1)[1])
    return " ".join(texts), images


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga a leitura de imagens e boletos.")
        OCR: bool = Field(default=True, description="Ler o texto das imagens com OCR local.")
        MAX_CHARS: int = Field(default=6000, description="Limite de texto lido entregue ao modelo.")

    def __init__(self):
        self.valves = self.Valves()
        self._ocr = {}     # sha1 da imagem -> texto (a mesma foto volta a cada turno)
        self._vision = {}  # modelo -> enxerga imagens?

    def _sees_images(self, model):
        """O modelo aceita imagens? (Ollama /api/show -> capabilities). Modelo de
        nuvem ou desconhecido: supoe que sim e deixa a imagem como esta."""
        if model in self._vision:
            return self._vision[model]
        ok = True
        try:
            import requests
            base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
            r = requests.post(f"{base}/api/show", json={"model": model}, timeout=10)
            if r.status_code == 200:
                ok = "vision" in (r.json().get("capabilities") or [])
        except Exception:
            pass
        self._vision[model] = ok
        return ok

    @staticmethod
    def _strip_images(messages):
        """Tira as imagens (o texto delas ja' foi lido): o Ollama recusa imagem
        em modelo sem visao ("model does not support multimodal")."""
        for m in messages:
            c = m.get("content")
            if isinstance(c, list):
                texts = [p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"]
                n_img = sum(1 for p in c if isinstance(p, dict) and p.get("type") == "image_url")
                extra = f"\n[{n_img} imagem(ns) enviada(s); o texto delas esta no contexto]" if n_img else ""
                m["content"] = " ".join(t for t in texts if t) + extra

    def _read(self, b64s):
        out = []
        for b in b64s[:4]:
            try:
                data = base64.b64decode(b)
            except Exception:
                continue
            k = hashlib.sha1(data).hexdigest()
            if k not in self._ocr:
                try:
                    self._ocr[k] = leitura.ocr_image(data)
                except Exception:
                    self._ocr[k] = ""
            out.append(self._ocr[k])
        return out

    async def inlet(self, body: dict, __user__: Optional[dict] = None, __event_emitter__=None) -> dict:
        if not self.valves.ENABLED or leitura is None:
            return body
        messages = body.get("messages", [])
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        if not last:
            return body
        text, images = _parts(last)
        boletos = leitura.find_boletos(text)
        if not images and not boletos and not any(_parts(m)[1] for m in messages if m.get("role") == "user"):
            return body

        ocr_texts = []
        if images and self.valves.OCR:
            if __event_emitter__:
                try:
                    await __event_emitter__({"type": "status", "data": {
                        "description": "Lendo o texto da imagem...", "done": False}})
                except Exception:
                    pass
            ocr_texts = await asyncio.to_thread(self._read, images)
            for t in ocr_texts:
                boletos += [b for b in leitura.find_boletos(t) if b not in boletos]

        blocks = []
        lidos = [t for t in ocr_texts if t.strip()]
        if lidos:
            joined = "\n\n".join(f"--- imagem {i + 1} ---\n{t}" for i, t in enumerate(lidos))
            blocks.append("[Nous Leitura] Texto lido das imagens por OCR local (pode ter pequenos erros, "
                          "sobretudo espacos entre palavras):\n" + joined[: int(self.valves.MAX_CHARS)])
        decoded = [leitura.decode_boleto(b) for b in boletos[:3]]
        descr = [leitura.describe_boleto(b) for b in decoded if b]
        if descr:
            bad = any(b.get("digitos_conferem") is False for b in decoded if b)
            # vai PRIMEIRO: modelo pequeno ignorava o aviso no fim e chamava a
            # linha digitavel de "codigo PIX"
            blocks.insert(0, "[Nous Leitura] IMPORTANTE: ha' LINHA DIGITAVEL DE BOLETO na mensagem. "
                             "Dados calculados pelos digitos (regras FEBRABAN, confiaveis; use-os e diga "
                             "que e' um boleto, nao um codigo PIX):\n" + "\n".join(f"- {d}" for d in descr)
                          + ("\nOs digitos verificadores NAO conferem: diga ao usuario que a linha parece "
                             "ter sido lida ou digitada errado e peca para conferir no boleto original "
                             "antes de pagar." if bad else ""))
        if __event_emitter__ and images:
            try:
                await __event_emitter__({"type": "status", "data": {
                    "description": "Imagem lida." + (" Boleto decodificado." if descr else ""), "done": True}})
            except Exception:
                pass
        # imagens em QUALQUER mensagem (fotos de turnos anteriores tambem voltam)
        any_images = any(_parts(m)[1] for m in messages if m.get("role") == "user")
        if any_images and not await asyncio.to_thread(self._sees_images, body.get("model") or ""):
            if not blocks:  # foto antiga, sem texto novo: le de novo do cache
                older = [t for m in messages if m.get("role") == "user"
                         for t in await asyncio.to_thread(self._read, _parts(m)[1]) if t.strip()]
                if older:
                    blocks.append("[Nous Leitura] Texto lido por OCR das imagens desta conversa:\n"
                                  + "\n\n".join(older)[: int(self.valves.MAX_CHARS)])
            self._strip_images(messages)
        if not blocks:
            body["messages"] = messages
            return body
        block = "\n\n".join(blocks)
        if messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + block) if base else block
        else:
            messages.insert(0, {"role": "system", "content": block})
        body["messages"] = messages
        return body
