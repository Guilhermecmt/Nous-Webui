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
  Aprender de novo algo parecido atualiza a habilidade (com copia .bak), nao duplica.
  Correcoes como "de agora em diante..." viram uma PROPOSTA pendente, gerada com o
  computador ocioso; so' vira habilidade se voce aprovar.
  Complementa a Memoria (fatos sobre voce) com procedimentos.
"""
import os
import re
import json
import time
import asyncio
import shutil
import hashlib
import datetime
import threading
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
# Correcao que pode valer para sempre. Roda sobre o texto sem acento (_fold)
_CORRECAO = re.compile(
    r"\b(?:nao (?:faca|use|coloque|ponha|escreva|responda|mande|repita|invente|comece|termine|inclua)|"
    r"nunca (?:mais )?(?:faca|use|coloque|ponha|escreva|responda|mande|comece|termine)|par[ae] de|"
    r"de agora em diante|daqui (?:em|pra|para) (?:diante|frente)|a partir de agora|"
    r"da proxima vez|sempre que (?:eu|voce)|prefiro que)\b")
# Pedido unico nao vira preferencia
_SO_DESTA_VEZ = re.compile(
    r"\b(?:desta|dessa|esta|essa) vez\b|\bso (?:hoje|agora|aqui)\b|"
    r"\b(?:nesta|nessa) (?:resposta|mensagem)\b|\b(?:neste|nesse) (?:caso|texto|e-?mail)\b")
# Falha de ambiente nao vira licao: quem conserta e' a pessoa, e a regra ficaria para sempre
_FALHA_AMBIENTE = re.compile(
    r"\bnao (?:funciona|funcionou|esta funcionando|abre|abriu|conecta|conectou|carrega|carregou|"
    r"consegue|conseguiu|tem acesso)\b|\bnao (?:esta )?instalad|\bcommand not found\b|"
    r"\bcomando nao encontrado\b|\bsem (?:internet|conexao|acesso)\b|\bfora do ar\b|\bquebrad[ao]\b|"
    r"\bdeu erro\b|\bpermissao negada\b|\btravou\b|\bcaiu\b")
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


_JUNTAR = """Voce atualiza uma HABILIDADE do assistente com um aprendizado novo.

Habilidade salva: {nome}
Usar: {quando}
Passos:
{antigos}

Aprendizado novo: {novo_nome}
Usar: {novo_quando}
Passos:
{novos}

Responda SO' com JSON: {{"mesma_tarefa": true ou false, "passos": ["passo 1", "passo 2", "..."]}}

Regras:
- mesma_tarefa: false se forem tarefas diferentes (ex.: relatorio de vendas e relatorio de compras);
  nesse caso devolva "passos": [].
- Mantenha TODOS os passos salvos que continuam valendo. Troque so' o que o aprendizado novo
  contradiz e acrescente o que falta, sem repetir.
- Copie EXATAMENTE os textos fixos (assinatura, saudacao, formato). Nao numere os passos."""

_JUNTAR_SCHEMA = {"type": "object", "required": ["mesma_tarefa", "passos"],
                  "properties": {"mesma_tarefa": {"type": "boolean"},
                                 "passos": {"type": "array", "items": {"type": "string"}}}}

_REVISAR = """O usuario corrigiu o assistente nesta conversa. Decida se a correcao ensina uma REGRA
DURADOURA, que deve valer em conversas futuras.

Conversa:
\"\"\"{conversa}\"\"\"

Responda SO' com JSON:
{{"aprender": true ou false, "geral": true ou false, "falha_de_ambiente": true ou false,
  "trecho": "as palavras exatas do usuario que pedem a regra",
  "nome": "nome curto da regra", "quando_usar": "em que tipo de pedido aplicar",
  "passos": ["regra 1", "..."]}}

Regras:
- geral: true SO' se o usuario marcou que vale sempre ("sempre", "de agora em diante", "nunca",
  "lembre disso") ou disse algo que nao gosta ("pare de", "odeio"). Pedido para ESTA resposta e'
  false: pedido unico nao vira preferencia.
- falha_de_ambiente: true se o assunto e' algo quebrado ou faltando (programa nao instalado,
  sem internet, erro, ferramenta que nao funciona). Isso nao vira licao: quem conserta e' o usuario.
- Use so' o que esta na conversa. Nao adivinhe gostos, profissao ou humor do usuario.
- Na duvida, "aprender": false."""

_REVISAR_SCHEMA = {
    "type": "object",
    "required": ["aprender", "geral", "falha_de_ambiente", "trecho", "nome", "quando_usar", "passos"],
    "properties": {"aprender": {"type": "boolean"}, "geral": {"type": "boolean"},
                   "falha_de_ambiente": {"type": "boolean"}, "trecho": {"type": "string"},
                   "nome": {"type": "string"}, "quando_usar": {"type": "string"},
                   "passos": {"type": "array", "items": {"type": "string"}}}}

MAX_PROPOSTAS = 20
TURNO_ESQUECIDO_S = 600  # turno sem outlet (erro, aba fechada) nao segura a revisao para sempre


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
            "origem": meta.get("origem") or "",
            "corpo": body.strip()}


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _fold(s):
    t = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _tokens(s):
    return {w for w in re.findall(r"[a-z0-9]{4,}", _fold(s)) if w not in _STOP}


def _steps(passos):
    """Lista limpa de passos. Modelos pequenos mandam "1. ..." dentro da lista ("1. 1. ...")."""
    if isinstance(passos, str):
        passos = passos.splitlines()
    if not isinstance(passos, list):
        return []
    limpos = [re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", str(p)).strip() for p in passos]
    return [p for p in limpos if p]


def _numbered(passos):
    return "\n".join(f"{i + 1}. {p}" for i, p in enumerate(passos))


def _presente(passo, lista):
    t = _tokens(passo)
    return any(len(t & _tokens(p)) * 2 >= max(1, len(t)) for p in lista)


def _preservar(antigos, juntos, novos):
    """O que a pessoa ensinou nao some. No teste real, 4B e 7B devolveram so' os passos
    novos, mesmo com a regra no prompt, e 2 de 3 passos sumiram. Passo antigo so' sai se
    um passo novo fala do mesmo assunto (foi trocado); senao a lista do modelo e'
    descartada e os novos entram depois dos antigos."""
    perdidos = [a for a in antigos if not _presente(a, juntos) and not any(_tokens(a) & _tokens(n) for n in novos)]
    if not perdidos:
        return juntos
    return antigos + [n for n in novos if not _presente(n, antigos)]


def _is_correction(msg):
    """Correcao que pode virar regra. Pergunta e texto colado longo ficam de fora."""
    t = _fold(msg).strip()
    if not t or len(t) > 600 or t.endswith("?"):
        return False
    return bool(_CORRECAO.search(t)) and not _SO_DESTA_VEZ.search(t)


def _proposal(d, mark):
    """Resposta do modelo -> proposta, ou None. O modelo pequeno ignora regras do prompt:
    as mesmas regras sao conferidas aqui. Na duvida nao propoe (nada aqui e' urgente)."""
    if not isinstance(d, dict) or d.get("aprender") is not True or d.get("geral") is not True:
        return None
    if d.get("falha_de_ambiente") is not False:
        return None
    nome = re.sub(r"[_\s]+", " ", str(d.get("nome") or "")).strip()[:80]
    quando = re.sub(r"\s+", " ", str(d.get("quando_usar") or "")).strip()[:300]
    passos = _steps(d.get("passos"))
    if not (nome and quando and passos):
        return None
    if _FALHA_AMBIENTE.search(_fold(" ".join([nome, quando, *passos, mark["msg"]]))):
        return None
    # A regra tem que sair das palavras do usuario, nao da imaginacao do modelo
    trecho, usuario = str(d.get("trecho") or ""), mark["usuario"]
    pedidas = _tokens(trecho)
    ancorada = bool(trecho.strip()) and _fold(trecho).strip() in _fold(usuario)
    if not ancorada and (not pedidas or len(pedidas & _tokens(usuario)) * 5 < len(pedidas) * 3):
        return None
    return {"nome": nome[:1].upper() + nome[1:], "quando_usar": quando, "passos": passos,
            "criado": datetime.date.today().isoformat()}


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga as habilidades.")
        TOP_K: int = Field(default=1, description="Quantas habilidades injetar por pergunta.")
        MIN_SIM: float = Field(default=0.50, description="Similaridade minima (0-1) para uma habilidade virar candidata; o modelo confirma.")
        STRICT_SIM: float = Field(default=0.58, description="Sem modelo de chat para confirmar, so' usa acima desta similaridade.")
        MERGE_SIM: float = Field(default=0.80, description="Similaridade minima (0-1) para aprender algo como atualizacao de uma habilidade parecida; o modelo confirma.")
        MERGE_TEXT: float = Field(default=0.50, description="Sem embeddings: fracao de palavras em comum para a mesma decisao.")
        REVIEW: bool = Field(default=True, description="Gera propostas de habilidade a partir de correcoes; nada e' salvo sem aprovacao.")
        REVIEW_IDLE_S: float = Field(default=15, description="Segundos sem nenhum turno antes de chamar o modelo para revisar.")
        EMBED_MODEL: str = Field(default="granite-embedding:278m", description="Modelo de embeddings (Ollama).")
        OLLAMA_URL: str = Field(default="", description="URL do Ollama. Vazio = OLLAMA_BASE_URL ou 127.0.0.1:11434.")

    def __init__(self):
        self.valves = self.Valves()
        self._emb = {}    # caminho -> (mtime, vetor normalizado)
        self._learned = {}  # hash(usuario+conversa) -> (quando, texto): regenerar nao duplica
        self._marks = {}     # (usuario, conversa) -> correcao esperando a hora ociosa
        self._revisadas = {}  # hash(usuario+conversa+mensagem) -> quando: regenerar nao revisa de novo
        self._turnos = {}    # conversa -> quando comecou (turno em andamento usa a GPU)
        self._timer = None   # asyncio.Task da espera ociosa
        self._parar = None   # threading.Event da chamada em curso

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

    def _pre(self, prefix):
        """Prefixo de tarefa so' para o nomic-embed-text."""
        return prefix if self.valves.EMBED_MODEL.startswith("nomic") else ""

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
        if hit and hit[0] == (mt, self.valves.EMBED_MODEL):
            return hit[1]
        v = self._embed(self._pre("search_document: ") + f"{s['nome']}. {s['quando_usar']}")
        if v is not None:
            self._emb[s["path"]] = ((mt, self.valves.EMBED_MODEL), v)
        return v

    def _match(self, uid, msg, chat_model=""):
        skills = self._skills(uid)
        if not skills:
            return []
        q = self._embed(self._pre("search_query: ") + msg)
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

    def _neighbor(self, uid, nome, quando):
        """Habilidade parecida com esta: mesmo nome, embedding ou, sem ele, palavras em comum."""
        skills = [s for s in self._skills(uid) if s["origem"] != "estilo"]  # essa a tela refaz
        alvo = _slug(nome)
        for s in skills:
            if _slug(s["nome"]) == alvo or os.path.basename(s["path"])[:-3] == alvo:
                return s
        q = self._embed(self._pre("search_document: ") + f"{nome}. {quando}") if skills else None
        novo, best, best_sim = _tokens(f"{nome} {quando}"), None, 0.0
        for s in skills:
            v = self._vec(s) if q is not None else None
            if q is not None and v is not None and v.shape == q.shape:
                sim, corte = float(v @ q), self.valves.MERGE_SIM
            else:
                velho = _tokens(f"{s['nome']} {s['quando_usar']}")
                comum = novo & velho
                sim = len(comum) / len(novo | velho) if len(comum) >= 2 else 0.0
                corte = self.valves.MERGE_TEXT
            if sim >= corte and sim > best_sim:
                best, best_sim = s, sim
        return best

    def _merge(self, viz, nome, quando, passos, model):
        """Junta numa chamada. None = tarefas diferentes (segue e cria outra habilidade)."""
        antigos = _steps(viz["corpo"])
        prompt = _JUNTAR.format(nome=viz["nome"], quando=viz["quando_usar"], antigos=viz["corpo"],
                                novo_nome=nome, novo_quando=quando, novos=_numbered(passos))
        r = requests.post(f"{self._ollama()}/api/generate",
                          json={"model": model, "prompt": prompt, "stream": False, "format": _JUNTAR_SCHEMA,
                                "think": False, "options": {"temperature": 0.2, "num_ctx": NUM_CTX}}, timeout=180)
        r.raise_for_status()
        recusa = (f"[Nous Skills] Ja existe a habilidade \"{viz['nome']}\", parecida com esta, mas nao "
                  "consegui juntar as duas. Nada foi alterado. Avise o usuario e peca para tentar de novo.")
        try:
            m = json.loads(r.json().get("response") or "{}")
        except ValueError:
            return recusa
        if not isinstance(m, dict):
            return recusa
        if m.get("mesma_tarefa") is not True:
            return None
        juntos = _steps(m.get("passos"))
        if not juntos or len(juntos) * 2 < len(antigos):
            return recusa  # modelo pequeno que perde metade dos passos estragaria o que a pessoa ensinou
        juntos = _preservar(antigos, juntos, _steps(passos))
        path = viz["path"]
        texto = open(path, encoding="utf-8").read()
        topo = re.match(r"\ufeff?---\s*\n.*?\n---\s*\n?", texto, re.S)
        shutil.copy2(path, path + ".bak")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            f.write((topo.group(0).rstrip() + "\n\n" if topo else "") + _numbered(juntos) + "\n")
        os.replace(path + ".tmp", path)  # queda de energia no meio nao deixa arquivo pela metade
        return (f"[Nous Skills] Habilidade atualizada: \"{viz['nome']}\" ja existia e agora inclui o que "
                "foi aprendido; a versao anterior ficou guardada. Confirme ao usuario em uma ou duas "
                "frases e diga que ele pode revisar em Recursos > Habilidades.")

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
        lista = _steps(d.get("passos"))
        passos = _numbered(lista)
        if not (nome and quando and passos):
            return ("[Nous Skills] Nao consegui resumir uma habilidade desta conversa. "
                    "Peca ao usuario para explicar em uma frase o que deve ser lembrado.")
        viz = self._neighbor(uid, nome, quando)
        if viz:
            texto = self._merge(viz, nome, quando, lista, model)
            if texto:
                return texto
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

    # ---------------------------------------------------------- correcoes
    # A GPU e' uma so': a revisao espera 15 s sem turno, e qualquer turno novo cancela.
    def _busy(self):
        t = time.time()
        self._turnos = {k: v for k, v in self._turnos.items() if t - v < TURNO_ESQUECIDO_S}
        return bool(self._turnos)

    def _turn_begin(self, chat):
        self._turnos[chat] = time.time()
        if self._parar:
            self._parar.set()  # a chamada em curso fecha a conexao: o Ollama para de gerar
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _arm(self):
        if self._marks and not self._timer and not self._busy():
            self._timer = asyncio.create_task(self._idle())

    async def _idle(self):
        parar = None
        try:
            await asyncio.sleep(self.valves.REVIEW_IDLE_S)
            while self._marks and not self._busy():
                key, mark = next(iter(self._marks.items()))
                parar = self._parar = threading.Event()
                await asyncio.to_thread(self._review, mark, parar)
                if parar.is_set():
                    return  # turno novo: a marca fica e o proximo outlet arma de novo
                self._marks.pop(key, None)
        except asyncio.CancelledError:
            if parar:
                parar.set()
            raise
        except Exception:
            pass
        finally:
            self._parar = None
            if self._timer is asyncio.current_task():
                self._timer = None

    def _review(self, mark, parar):
        """UMA chamada com saida JSON. Em streaming para poder abortar no meio."""
        model = self._model(mark["model"])
        if not model or parar.is_set():
            return
        partes = []
        with requests.post(f"{self._ollama()}/api/generate", stream=True, timeout=(5, 120),
                           json={"model": model, "prompt": _REVISAR.format(conversa=mark["conversa"]),
                                 "stream": True, "format": _REVISAR_SCHEMA, "think": False,
                                 "options": {"temperature": 0, "num_predict": 400, "num_ctx": NUM_CTX}}) as r:
            r.raise_for_status()
            for linha in r.iter_lines():
                if parar.is_set():
                    return
                if linha:
                    partes.append(json.loads(linha).get("response") or "")
        try:
            d = json.loads("".join(partes))
        except ValueError:
            return
        prop = _proposal(d, mark)
        if prop and not parar.is_set():
            self._propose(mark["uid"], prop)

    def _propose(self, uid, prop):
        """Fica em propostas/, fora da lista de habilidades: sem aprovacao nao entra no contexto."""
        d = os.path.join(self._dir(uid), "propostas")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, _slug(prop["nome"]) + ".json")
        if os.path.exists(p) or len(os.listdir(d)) >= MAX_PROPOSTAS:
            return
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(prop, f, ensure_ascii=False)
        os.replace(p + ".tmp", p)

    def _mark(self, uid, chat, messages, model):
        usuario = [_text(m) for m in messages if m.get("role") == "user"]
        msg = usuario[-1] if usuario else ""
        if not _is_correction(msg) or _LEARN.search(msg):
            return
        t = time.time()
        self._revisadas = {k: v for k, v in self._revisadas.items() if t - v < 86400}
        key = hashlib.sha1(f"{uid}\n{chat}\n{msg}".encode("utf-8")).hexdigest()
        if key in self._revisadas:
            return
        self._revisadas[key] = t
        partes = [f"{'Usuario' if m['role'] == 'user' else 'Assistente'}: {_text(m)[:1000]}"
                  for m in messages[-8:] if m.get("role") in ("user", "assistant")]
        self._marks[(uid, chat)] = {"uid": uid, "msg": msg, "usuario": "\n".join(usuario[-8:]),
                                    "conversa": "\n\n".join(partes), "model": model}

    async def outlet(self, body: dict, __user__: Optional[dict] = None,
                     __metadata__: Optional[dict] = None) -> dict:
        chat = body.get("chat_id") or (__metadata__ or {}).get("chat_id") or "_"
        self._turnos.pop(chat, None)
        uid = (__user__ or {}).get("id")
        if self.valves.ENABLED and self.valves.REVIEW and requests is not None and uid:
            self._mark(uid, chat, body.get("messages") or [], body.get("model") or "")
        self._arm()
        return body

    # ---------------------------------------------------------- ciclo
    async def inlet(self, body: dict, __user__: Optional[dict] = None,
                    __event_emitter__=None, __metadata__: Optional[dict] = None) -> dict:
        self._turn_begin((__metadata__ or {}).get("chat_id") or body.get("chat_id") or "_")
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
                    if text.startswith(("[Nous Skills] Habilidade salva", "[Nous Skills] Habilidade atualizada")):
                        self._learned[key] = (t, text)
                except Exception as e:
                    text = f"[Nous Skills] Falhou ao salvar a habilidade ({e}). Avise o usuario."
                await status("Habilidade salva." if re.search(r"(?:salva|atualizada):", text) else "Nada foi salvo.")
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
