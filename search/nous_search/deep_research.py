# -*- coding: utf-8 -*-
"""
deep_research(question, ...) — laço de pesquisa multi-etapas em Python puro.

Fluxo:
  1. plan   — LLM decompõe a pergunta em 2–4 sub-perguntas (JSON; fallback: [question])
  2. search — search_web() para cada sub-pergunta; dedup por URL
  3. refine — (1 iteração extra) se menos de 3 fontes, gera 1–2 novas sub-perguntas
  4. fetch  — fetch_page() nas melhores fontes (modo deep)
  5. synthesize — monta contexto e pede ao Ollama o relatório final em PT-BR

Nenhuma dependência externa nova: usa apenas search.py, rag.py e requests.
"""
import json
import os
import re
import requests
from typing import Callable, Optional

from .search import search_web
from .rag import fetch_page, build_context, OLLAMA_URL, NOUS_MODEL, SYSTEM_PROMPT
from .rag import NUM_CTX

PLAN_PROMPT = """\
Você é um assistente de pesquisa. Decomponha a pergunta abaixo em {n} sub-perguntas
específicas que, respondidas juntas, cobrem completamente a pergunta original.
Responda APENAS com um JSON no formato:
{{"subqueries": ["sub-pergunta 1", "sub-pergunta 2", ...]}}

Pergunta: {question}
"""

NEED_MORE_PROMPT = """\
Você recebeu os seguintes resumos de fontes para responder a pergunta:

Pergunta: {question}

Fontes disponíveis:
{summaries}

As fontes acima são SUFICIENTES para dar uma resposta completa e confiável?
Responda com uma única palavra: SIM ou NÃO.
"""

SYNTHESIS_PROMPT = """\
# Pergunta principal
{question}

# Contexto (fontes numeradas)
{context}

# Instrução
Escreva um relatório completo em português, organizado com subtítulos em markdown.
Cite as fontes usando [n] ao longo do texto onde for pertinente.
Ao final, inclua uma seção "## Fontes" com a lista numerada e as URLs.
Use APENAS o contexto fornecido. Se algo não estiver coberto pelas fontes, diga isso.
"""


def _llm_call(prompt: str, model: str, timeout: int = 90, fmt=None) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": NUM_CTX},
    }
    if fmt is not None:
        # Saida estruturada: modelos pequenos (qwen3:4b) "pensam em voz alta"
        # antes do JSON e o parse falhava, caindo sempre em [question].
        payload["format"] = fmt
        payload["think"] = False
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    except Exception:
        return ""


_PLAN_SCHEMA = {"type": "object", "required": ["subqueries"],
                "properties": {"subqueries": {"type": "array", "items": {"type": "string"}}}}
_ENOUGH_SCHEMA = {"type": "object", "required": ["suficiente"],
                  "properties": {"suficiente": {"type": "boolean"}}}


def _plan_subqueries(question: str, model: str, n: int = 3) -> list[str]:
    raw = _llm_call(PLAN_PROMPT.format(question=question, n=n), model, timeout=60, fmt=_PLAN_SCHEMA)
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            subs = [s.strip() for s in data.get("subqueries", []) if isinstance(s, str) and s.strip()]
            if subs:
                return subs[:n]
    except Exception:
        pass
    return [question]


def _need_more(question: str, results: list, model: str) -> bool:
    summaries = "\n".join(
        f"[{i+1}] {r.get('title','')} — {(r.get('content') or r.get('text',''))[:200]}"
        for i, r in enumerate(results[:5])
    )
    raw = _llm_call(NEED_MORE_PROMPT.format(question=question, summaries=summaries)
                    + '\nResponda em JSON: {"suficiente": true|false}', model, timeout=30,
                    fmt=_ENOUGH_SCHEMA)
    try:
        return not json.loads(raw).get("suficiente", True)
    except Exception:
        return raw.strip().upper().startswith("N")


# ------------------------------------------------- modelos pequenos
_SIZE_CACHE: dict = {}


def model_size_b(model: str) -> float:
    """Bilhoes de parametros do modelo (Ollama /api/show); 0 se desconhecido."""
    if model in _SIZE_CACHE:
        return _SIZE_CACHE[model]
    size = 0.0
    try:
        r = requests.post(f"{OLLAMA_URL}/api/show", json={"model": model}, timeout=10)
        ps = (r.json().get("details") or {}).get("parameter_size") or ""
        m = re.match(r"([\d.]+)\s*([BM])", ps.upper())
        if m:
            size = float(m.group(1)) / (1000 if m.group(2) == "M" else 1)
    except Exception:
        pass
    if not size:
        m = re.search(r"(\d+(?:\.\d+)?)b\b", model.lower())
        size = float(m.group(1)) if m else 0.0
    _SIZE_CACHE[model] = size
    return size


_SIMPLE = re.compile(
    r"^\s*(o que (?:e|é|significa|sao|são)|quem (?:e|é|foi|foram)|onde (?:fica|e|é)|"
    r"quando (?:foi|e|é|nasceu|morreu|acontece)|qual (?:e|é) (?:a|o) (?:capital|populacao|população|"
    r"altura|idade|significado|definicao|definição)|quantos? )\b", re.I)

SHORT_PROMPT = """\
# Pergunta
{question}

# Fontes numeradas
{context}

# Instrucao
Responda em portugues, em 3 a 6 frases, so' com o que as fontes dizem, citando [n].
Se as fontes nao responderem, diga isso.
"""


def is_simple(question: str) -> bool:
    """Pergunta de fato simples ("o que e X", "quem foi Y"): busca unica e resposta curta."""
    return bool(_SIMPLE.search(question)) and len(question.split()) <= 12


def _partial(question: str, top: list) -> str:
    """Relatorio parcial quando a sintese falha: as fontes encontradas nao se perdem."""
    lines = [f"Nao consegui escrever o relatorio completo sobre: {question}",
             "", "Estas sao as fontes que encontrei, com um trecho de cada:", ""]
    for i, r in enumerate(top, 1):
        snippet = re.sub(r"\s+", " ", (r.get("content") or r.get("text") or ""))[:240]
        lines.append(f"[{i}] **{r.get('title') or r.get('url', '')}** - {snippet}")
    return "\n".join(lines)


def _dedup(existing: list, new: list) -> list:
    seen = {r["url"] for r in existing}
    merged = list(existing)
    for r in new:
        if r["url"] not in seen:
            seen.add(r["url"])
            merged.append(r)
    return merged


def _emit_sync(emit: Optional[Callable], msg: str):
    """Status para o chat. deep_research roda numa THREAD (sem loop asyncio):
    o pipe passa uma funcao comum que agenda o envio no loop dele. Antes isto
    tentava usar o loop desta thread e nenhum status chegava."""
    if not emit:
        return
    try:
        import asyncio
        r = emit({"type": "status", "data": {"description": msg, "done": False}})
        if asyncio.iscoroutine(r):
            r.close()  # corrotina sem loop aqui: descarta em vez de vazar aviso
    except Exception:
        pass


def deep_research(
    question: str,
    *,
    model: Optional[str] = None,
    searxng_url: Optional[str] = None,
    max_iterations: int = 2,
    max_pages: int = 5,
    results_per_query: int = 4,
    emit=None,
) -> dict:
    """Executa pesquisa profunda e retorna {report, sources[, curta, parcial]}.

    `emit` é um callable async (ou None) que recebe dicts de status do Open WebUI.
    """
    _m = model or os.environ.get("NOUS_MODEL", NOUS_MODEL)
    if searxng_url:
        os.environ.setdefault("SEARXNG_URL", searxng_url)

    # Pergunta de fato simples: uma busca e resposta curta, sem relatorio
    if is_simple(question):
        _emit_sync(emit, f"🔎 Buscando: {question[:60]}…")
        found = search_web(question, k=4)
        if not found:
            return {"report": "A busca na web não está disponível agora. Verifique se o SearXNG está rodando.",
                    "sources": [], "curta": True}
        top = found[:3]
        for r in top[:2]:
            if not r.get("text"):
                page = fetch_page(r.get("url", ""))
                if page:
                    r["text"] = page
        answer = _llm_call(SHORT_PROMPT.format(question=question, context=build_context(top)), _m, timeout=300)
        if not answer:
            return {"report": _partial(question, top), "sources": top, "curta": True}
        fontes = "\n".join(f"[{i+1}] {r.get('title') or r.get('url','')} — {r.get('url','')}" for i, r in enumerate(top))
        return {"report": answer + "\n\n**Fontes**\n" + fontes, "sources": top, "curta": True}

    # Modelo pequeno (<= 10B): menos sub-perguntas e uma rodada so'. Mais que
    # isso estoura o contexto de 16k e o relatorio sai cortado ou vazio.
    small = 0 < model_size_b(_m) <= 10
    if small:
        max_iterations = 1
        max_pages = min(max_pages, 4)

    _emit_sync(emit, "🔍 Planejando pesquisa…")

    subqueries = _plan_subqueries(question, _m, n=2 if small else 3)
    results: list = []

    for iteration in range(max_iterations):
        for q in subqueries:
            _emit_sync(emit, f"🔎 Buscando: {q[:60]}…")
            found = search_web(q, k=results_per_query)
            results = _dedup(results, found)

        if not results:
            return {
                "report": "A busca na web não está disponível agora. Verifique se o SearXNG está rodando.",
                "sources": [],
            }

        if iteration < max_iterations - 1 and _need_more(question, results, _m):
            _emit_sync(emit, "↩ Refinando pesquisa…")
            extra = _plan_subqueries(
                f"Quais aspectos ainda faltam para responder: {question}", _m, n=2
            )
            subqueries = extra
        else:
            break

    top = results[:max_pages]
    _emit_sync(emit, f"📄 Lendo {len(top)} página(s)…")
    for r in top:
        if not r.get("text"):
            page = fetch_page(r.get("url", ""))
            if page:
                r["text"] = page

    _emit_sync(emit, "✍ Escrevendo o relatório…")
    context = build_context(top)
    prompt = SYNTHESIS_PROMPT.format(question=question, context=context)
    report = _llm_call(prompt, _m, timeout=600)
    if not report.strip():
        return {"report": _partial(question, top), "sources": top, "parcial": True}

    sources_section = "\n\n## Fontes\n" + "\n".join(
        f"[{i+1}] {r.get('title', r.get('url',''))} — {r.get('url','')}"
        for i, r in enumerate(top)
    )
    if "## Fontes" not in report:
        report += sources_section

    return {"report": report, "sources": top}
