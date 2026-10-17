# -*- coding: utf-8 -*-
"""RAG simples: pega os 5 melhores resultados, monta um contexto e responde
via Ollama (gemma4:12b por padrao), citando as fontes com [n] (estilo Perplexity).
"""
import os
import re
import requests
from .search import search_web

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
NOUS_MODEL = os.environ.get("NOUS_MODEL", "gemma4:12b")
# Mesmo num_ctx do chat (monitor/register_model_ctx.py): com outro valor o
# Ollama recarrega o modelo (no 0.30 o padrao chega a 256k e estoura a VRAM).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))

SYSTEM_PROMPT = (
    "Voce e o Nous, um assistente de pesquisa. Responda em portugues, de forma "
    "clara e objetiva, USANDO SOMENTE o contexto fornecido. Cite as fontes com "
    "marcadores no formato [n] ao longo do texto. Se o contexto nao responder a "
    "pergunta, diga isso honestamente em vez de inventar."
)

PROMPT_TEMPLATE = """# Pergunta
{query}

# Contexto (fontes numeradas)
{context}

# Instrucoes
Responda usando apenas o contexto acima e cite as fontes como [n].
"""


def build_context(results):
    """Formata os resultados em fontes numeradas [1], [2], ... para o LLM."""
    blocks = []
    for i, r in enumerate(results, 1):
        body = r.get("text") or r.get("content") or ""
        blocks.append(
            f"[{i}] {r.get('title', '(sem titulo)')}\n"
            f"URL: {r.get('url', '')}\n"
            f"{body}".strip()
        )
    return "\n\n".join(blocks)


def fetch_page(url, *, max_chars=4000, timeout=15):
    """Baixa e limpa o texto de uma pagina (modo deep). Best-effort, nunca quebra.

    Usa BeautifulSoup se disponivel; senao, faz um strip de tags por regex.
    """
    try:
        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": "Nous/1.0 (+local)"}
        )
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "form"]):
            tag.decompose()
        text = soup.get_text(" ")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    text = " ".join(text.split())
    return text[:max_chars]


def answer(query, k=5, *, model=None, deep=False, timeout=300):
    """Busca + RAG + resposta do LLM.

    Retorna {answer, sources, model}. Se `deep=True`, baixa o texto das paginas
    antes de montar o contexto (RAG mais rico, porem mais lento).
    """
    results = search_web(query, k=k)
    if not results:
        return {
            "answer": "Nenhum resultado encontrado (o SearXNG esta no ar?).",
            "sources": [],
            "model": model or NOUS_MODEL,
        }

    if deep:
        for r in results:
            page = fetch_page(r.get("url", ""))
            if page:
                r["text"] = page

    context = build_context(results)
    prompt = PROMPT_TEMPLATE.format(query=query, context=context)

    payload = {
        "model": model or NOUS_MODEL,
        "system": SYSTEM_PROMPT,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": NUM_CTX},
    }
    resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
    resp.raise_for_status()
    text = (resp.json().get("response") or "").strip()
    return {"answer": text, "sources": results, "model": payload["model"]}
