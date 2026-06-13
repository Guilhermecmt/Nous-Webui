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


def _llm_call(prompt: str, model: str, timeout: int = 90) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2},
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    except Exception:
        return ""


def _plan_subqueries(question: str, model: str, n: int = 3) -> list[str]:
    raw = _llm_call(PLAN_PROMPT.format(question=question, n=n), model, timeout=60)
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            subs = [s.strip() for s in data.get("subqueries", []) if s.strip()]
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
    raw = _llm_call(
        NEED_MORE_PROMPT.format(question=question, summaries=summaries), model, timeout=30
    )
    return raw.strip().upper().startswith("N")


def _dedup(existing: list, new: list) -> list:
    seen = {r["url"] for r in existing}
    merged = list(existing)
    for r in new:
        if r["url"] not in seen:
            seen.add(r["url"])
            merged.append(r)
    return merged


def _emit_sync(emit: Optional[Callable], msg: str):
    if emit:
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(
                    emit({"type": "status", "data": {"description": msg, "done": False}})
                )
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
    """Executa pesquisa profunda e retorna {report, sources}.

    `emit` é um callable async (ou None) que recebe dicts de status do Open WebUI.
    """
    _m = model or os.environ.get("NOUS_MODEL", NOUS_MODEL)
    if searxng_url:
        os.environ.setdefault("SEARXNG_URL", searxng_url)

    _emit_sync(emit, "🔍 Planejando pesquisa…")

    subqueries = _plan_subqueries(question, _m, n=3)
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

    sources_section = "\n\n## Fontes\n" + "\n".join(
        f"[{i+1}] {r.get('title', r.get('url',''))} — {r.get('url','')}"
        for i, r in enumerate(top)
    )
    if "## Fontes" not in report:
        report += sources_section

    return {"report": report, "sources": top}
