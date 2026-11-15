"""
title: Nous Comandos
author: Nous
version: 0.2.0
required_open_webui_version: 0.5.0
description: >
  Controlar o Nous pelo chat: "abre minha agenda", "mostra meus e-mails",
  "abre o editor de fotos", "tema claro", "libera a memoria da placa de video".
  O filtro reconhece o pedido (sem IA, por palavras) e poe um marcador na
  resposta; o loader do Nous abre o painel ou aplica a acao na hora.
  Pedidos para fazer algo no computador ("no computador: organiza meus
  Downloads", "/pc ...") vao para o Nous Code, ja' escritos.
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

# Pedido para FAZER algo no computador: o chat nao tem ferramentas (os modelos
# pequenos nao usam direito), entao o pedido vai para o Nous Code, que tem
# terminal e arquivos com as permissoes que a pessoa escolheu.
#  - explicito ("no computador: ...", "/pc ...", "manda pro Nous Code ..."): abre sozinho;
#  - so' parece ("organiza minha pasta Downloads"): vira um botao, sem abrir nada.
_TAREFA_EXPLICITA = re.compile(
    r"^\s*(?:/(?:pc|computador)\b|"
    r"(?:nous,?\s+)?(?:no|pelo)\s+(?:meu\s+)?(?:computador|pc)\s*[:,\-]|"
    r"(?:manda|mande|passa|passe|pede|pe[cç]a|envia|envie|leva|leve)\s+(?:isso\s+|isto\s+)?(?:pr[oa]|para\s+o|ao)\s+nous\s+code\s*[:,\-]?|"
    r"nous\s+code\s*[:,\-])\s*(?P<resto>.*)$", re.I | re.S)
_ACAO = (r"organiz[ae]r?|arrum[ae]r?|limp[ae]r?|apag[ae]r?|exclu[ia]r?|delet[ae]r?|mov[ae]r?|mova|copi[ae]r?|renomei[ae]|renomear|"
         r"compact[ae]r?|descompact[ae]r?|extrai[ar]?|instal[ae]r?|desinstal[ae]r?|rod[ae]r?|execut[ae]r?|cri[ae]r?|"
         r"separ[ae]r?|junt[ae]r?|convert[ae]r?|procur[ae]r? (?:no|em) (?:meu )?(?:computador|pc|disco)")
_ALVO = (r"pastas?|arquivos?|downloads|documentos|[aá]rea de trabalho|desktop|imagens|fotos|v[ií]deos|m[uú]sicas|"
         r"disco|hd|ssd|programas?|aplicativos?|apps?|computador|pc|\b[a-z]:\\|\.(?:zip|rar|7z|exe|msi|pdf|docx?|xlsx?|csv|txt|py|ps1|bat)\b")
_TAREFA_PARECE = re.compile(rf"^\s*(?:por favor,?\s*)?(?:voc[eê] (?:pode|consegue)\s+|d[aá] (?:pra|para) )?(?:{_ACAO})\b.{{0,160}}?(?:{_ALVO})", re.I | re.S)


def detectar_tarefa(msg):
    """("auto"|"botao", texto do pedido) para o Nous Code, ou None."""
    msg = (msg or "").strip()
    if not msg or len(msg) > 4000:
        return None
    m = _TAREFA_EXPLICITA.match(msg)
    if m:
        resto = (m.group("resto") or "").strip()
        return ("auto", resto) if len(resto) >= 3 else None
    if _TAREFA_PARECE.search(msg):
        return "botao", msg
    return None


def marcador_tarefa(modo, texto):
    # em hexadecimal: o Markdown nao mexe (nem _ nem * nem quebras de linha)
    return f"⟦tarefa:{modo}:{texto.encode('utf-8').hex()}⟧"


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
        pedido = _text(last) if last else ""
        hit = detectar(pedido)
        tarefa = None if hit else detectar_tarefa(pedido)
        if not uid or not (hit or tarefa):
            return body
        if hit:
            self._pending[uid] = (time.time(), hit[0])
            text = (f"[Nous Comandos] O usuario pediu para {hit[1]}. O Nous faz isso sozinho assim que "
                    "voce responder. Responda SO' uma frase curta confirmando (ex.: \"Pronto, abrindo.\").")
        elif tarefa[0] == "auto":
            self._pending[uid] = (time.time(), marcador_tarefa(*tarefa))
            text = ("[Nous Comandos] O usuario pediu para fazer algo no computador. Quem faz e' o Nous Code "
                    "(o agente com terminal e arquivos), que o Nous abre agora com o pedido ja' escrito. "
                    "Voce NAO executa nada e NAO diz que fez. Responda SO' uma frase curta, por exemplo: "
                    "\"Abrindo o Nous Code com o seu pedido: confira as permissoes e aperte Enter.\"")
        else:
            self._pending[uid] = (time.time(), marcador_tarefa(*tarefa))
            text = ("[Nous Comandos] Este pedido parece ser para mexer no computador (arquivos, pastas, programas). "
                    "Voce, no chat, nao tem acesso ao computador: nao diga que fez nada nem invente o resultado. "
                    "Responda normalmente, ajudando no que der por texto, e termine dizendo em uma frase que o botao "
                    "abaixo leva o pedido ao Nous Code, que consegue fazer isso no computador.")
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
