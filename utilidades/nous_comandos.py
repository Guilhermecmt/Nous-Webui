"""
title: Nous Comandos
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Controlar o Nous pelo chat: "abre minha agenda", "mostra meus e-mails",
  "abre o editor de fotos", "tema claro", "libera a memoria da placa de video".
  O filtro reconhece o pedido (sem IA, por palavras) e poe um marcador na
  resposta; o loader do Nous abre o painel ou aplica a acao na hora.
"""
import re
import time
from typing import Optional

from pydantic import BaseModel, Field

# (alvo, rotulo, padrao). O marcador e' ⟦abrir:alvo⟧ / ⟦tema:x⟧ / ⟦acao:liberar⟧.
_PAINEIS = [
    ("agenda", "a Agenda", r"agenda|calend[aá]rio|compromissos|lembretes|minhas notas|notas|tarefas agendadas|tarefas"),
    ("email", "o Assistente de Email", r"e-?mails?|caixa de entrada|rascunhos|contatos"),
    ("habilidades", "as Habilidades", r"habilidades"),
    ("relatorios", "os Relatorios de pesquisa", r"relat[oó]rios?"),
    ("editor", "o Editor de fotos", r"editor(?: de fotos| de imagens)?"),
    ("galeria", "a Galeria", r"galeria(?: de imagens| de fotos)?|imagens(?: geradas)?"),
    ("pdf", "os Formularios PDF", r"formul[aá]rios?(?: pdf)?|preencher (?:um )?pdf"),
    ("documentos", "os Documentos", r"documentos?|meus textos|textos|editor de textos?"),
    ("codigo", "o Nous Code", r"c[oó]digo|nous code|programa[cç][aã]o|agente de c[oó]digo"),
    ("loja", "a Loja de modelos", r"loja(?: de modelos)?|baixar modelos"),
    ("memoria", "o painel 'O que o Nous sabe'", r"mem[oó]rias?|o que (?:voc[eê]|o nous) sabe (?:de|sobre) mim"),
    ("diagnostico", "o Diagnostico", r"diagn[oó]stico|o que (?:est[aá] )?funcionando|status do nous"),
    ("comparar", "a Comparacao de modelos", r"compara[cç][aã]o(?: de modelos)?|comparar(?: os)? modelos"),
    ("placar", "o Placar dos modelos", r"placar(?: dos modelos)?|ranking(?: dos modelos)?"),
]
_OPEN = re.compile(
    r"^\s*(?:por favor,?\s*)?(?:abr[ae]|abrir|abre a[ií]|mostr[ae]|mostrar|me mostra|v[eê]|ver|vai para|ir para|quero ver)"
    r"\s+(?:a |o |as |os |minha |meu |minhas |meus |a minha |o meu |as minhas |os meus )?(.{2,60}?)\s*[.!?]*\s*$", re.I)
_TEMA = re.compile(r"\b(?:tema|modo|fundo)\s+(claro|escuro|branco|preto)\b|\b(?:deixa|muda|coloca|p[oõ]e)\b.{0,20}\b(claro|escuro)\b", re.I)
_LIBERAR = re.compile(r"\b(?:libera|liberar|descarrega|descarregar|para|parar|fecha|fechar)\b.{0,25}"
                      r"\b(?:mem[oó]ria da placa|vram|placa de v[ií]deo|gpu|modelos? carregad|os modelos)\b", re.I)


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


def detectar(msg):
    """(marcador, descricao) do comando, ou None."""
    msg = (msg or "").strip()
    if not msg or len(msg.split()) > 12:
        return None  # frase longa: e' conversa, nao comando
    if _LIBERAR.search(msg):
        return "⟦acao:liberar⟧", "liberar a memoria da placa de video (descarregar os modelos)"
    m = _TEMA.search(msg)
    if m:
        cor = (m.group(1) or m.group(2)).lower()
        cor = "claro" if cor in ("claro", "branco") else "escuro"
        return f"⟦tema:{cor}⟧", f"mudar para o tema {cor}"
    m = _OPEN.match(msg)
    if m:
        alvo = m.group(1).lower()
        for key, rotulo, pat in _PAINEIS:
            if re.fullmatch(rf"(?:{pat})(?: do nous)?", alvo, re.I):
                return f"⟦abrir:{key}⟧", f"abrir {rotulo}"
    return None


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga os comandos pelo chat.")

    def __init__(self):
        self.valves = self.Valves()
        self._pending = {}  # usuario -> (quando, marcador)

    async def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.ENABLED:
            return body
        uid = (__user__ or {}).get("id")
        messages = body.get("messages", [])
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        hit = detectar(_text(last) if last else "")
        if not uid or not hit:
            return body
        self._pending[uid] = (time.time(), hit[0])
        text = (f"[Nous Comandos] O usuario pediu para {hit[1]}. O Nous faz isso sozinho assim que "
                "voce responder. Responda SO' uma frase curta confirmando (ex.: \"Pronto, abrindo.\").")
        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + text) if base else text
        else:
            messages.insert(0, {"role": "system", "content": text})
        body["messages"] = messages
        return body

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        uid = (__user__ or {}).get("id")
        pend = self._pending.pop(uid, None) if uid else None
        if not pend or time.time() - pend[0] > 600:
            return body
        asst = next((m for m in reversed(body.get("messages", [])) if m.get("role") == "assistant"), None)
        if asst and isinstance(asst.get("content"), str):
            asst["content"] += "\n\n" + pend[1]
        return body
