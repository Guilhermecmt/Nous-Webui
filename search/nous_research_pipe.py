# -*- coding: utf-8 -*-
"""
title: Pesquisa Profunda (Nous)
author: Guilherme (Nous)
version: 1.0.0
required_open_webui_version: 0.5.0
license: MIT
description: >
  Pesquisa a web em múltiplas etapas (SearXNG local) e entrega um relatório
  em markdown com citações [n] e seção de Fontes. 100% local, sem API paga.
  Selecione este "modelo" no dropdown e faça sua pergunta normalmente.
"""
import os
import re
import sys
import asyncio
from typing import Optional

from pydantic import BaseModel, Field

# O Open WebUI executa este código a partir de um arquivo TEMPORÁRIO (o
# __file__ aponta para a pasta temp), então o pacote nous_search não estaria
# ao lado. O register_research_pipe.py grava aqui a pasta real do search/.
_SEARCH_DIR = r"__NOUS_SEARCH_DIR__"
for _d in (_SEARCH_DIR, os.path.dirname(os.path.abspath(__file__))):
    if os.path.isdir(os.path.join(_d, "nous_search")) and _d not in sys.path:
        sys.path.insert(0, _d)

MONITOR_URL = "http://127.0.0.1:8990"

_NEW_SEARCH = re.compile(r"^\s*(pesquis|investig|busque|procure|nova pesquisa|agora pesquis)", re.I)
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")
_SUGG_SCHEMA = {"type": "object", "required": ["sugestoes"],
                "properties": {"sugestoes": {"type": "array", "items": {"type": "string"}}}}

FOLLOWUP_PROMPT = """Abaixo esta um relatorio de pesquisa feito agora ha pouco. Responda a pergunta
do usuario em portugues usando SO' o relatorio, citando [n] quando ele citar. Se o
relatorio nao cobre a pergunta, diga isso em uma frase.

RELATORIO:
{report}

PERGUNTA: {question}"""

VAGUE_PROMPT = """Um usuario brasileiro pediu uma pesquisa sobre: "{question}". E' vago demais.
Sugira 3 perguntas de pesquisa mais especificas e uteis para o dia a dia dele, no Brasil,
em portugues do Brasil, curtas.
Responda em JSON: {{"sugestoes": ["...", "...", "..."]}}"""


def _pick_model(preferred: str) -> str:
    """O modelo da valve se estiver instalado; senao o primeiro modelo local de chat
    (o padrao gemma4:12b nem sempre foi baixado e a pesquisa falhava)."""
    try:
        import requests
        base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        names = [m.get("name", "") for m in requests.get(f"{base}/api/tags", timeout=5).json().get("models", [])]
    except Exception:
        return preferred
    if preferred in names or (preferred + ":latest") in names:
        return preferred
    return next((n for n in names if "/" not in n and not any(p in n.lower() for p in _EMBED)), preferred)


def _last_report(messages):
    """Texto da ultima resposta do assistente, se ela for um relatorio de pesquisa."""
    for m in reversed(messages[:-1] if messages else []):
        if m.get("role") == "assistant":
            c = m.get("content") or ""
            c = c if isinstance(c, str) else ""
            return c if ("## Fontes" in c or "relatório visual" in c or "**Fontes**" in c) else ""
    return ""


def _searxng_available(url: str, timeout: int = 5) -> bool:
    try:
        import requests
        r = requests.get(f"{url.rstrip('/')}/healthz", timeout=timeout)
        return r.status_code < 500
    except Exception:
        try:
            import requests
            r = requests.get(
                f"{url.rstrip('/')}/search",
                params={"q": "test", "format": "json"},
                timeout=timeout,
            )
            return r.status_code < 500
        except Exception:
            return False


class Pipe:
    class Valves(BaseModel):
        OLLAMA_MODEL: str = Field(
            default_factory=lambda: os.environ.get("NOUS_MODEL", "gemma4:12b"),
            description="Modelo Ollama para planejamento e síntese.",
        )
        SEARXNG_URL: str = Field(
            default_factory=lambda: os.environ.get("SEARXNG_URL", "http://localhost:8888"),
            description="URL do SearXNG local.",
        )
        MAX_ITERATIONS: int = Field(default=2, description="Máximo de rodadas de busca.")
        MAX_PAGES: int = Field(default=5, description="Máximo de páginas baixadas para contexto.")
        RESULTS_PER_QUERY: int = Field(default=4, description="Resultados por sub-pergunta.")

    def __init__(self):
        self.type = "pipe"
        self.valves = self.Valves()

    def pipes(self):
        return [{"id": "nous_research", "name": "Pesquisa Profunda (Nous)"}]

    async def pipe(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __event_emitter__=None,
        **_kwargs,
    ):
        messages = body.get("messages", [])
        question = ""
        for m in reversed(messages or []):
            if m.get("role") == "user":
                c = m.get("content", "")
                if isinstance(c, list):
                    c = " ".join(
                        p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                question = (c or "").strip()
                break

        if not question:
            yield "Por favor, escreva uma pergunta para pesquisar."
            return

        async def emit(event):
            if __event_emitter__:
                try:
                    await __event_emitter__(event)
                except Exception:
                    pass

        loop = asyncio.get_event_loop()
        from nous_search import deep_research as dr
        model = await loop.run_in_executor(None, _pick_model, self.valves.OLLAMA_MODEL)

        # Pergunta sobre o relatorio que acabou de sair ("e o preco?"): responde
        # com base nele, sem disparar outra pesquisa inteira (minutos de espera).
        report_prev = _last_report(messages)
        if report_prev and not _NEW_SEARCH.search(question):
            await emit({"type": "status", "data": {"description": "Consultando o relatório anterior…", "done": False}})
            answer = await loop.run_in_executor(None, lambda: dr._llm_call(
                FOLLOWUP_PROMPT.format(report=report_prev[:20000], question=question), model, timeout=300))
            await emit({"type": "status", "data": {"description": "Resposta baseada no relatório", "done": True}})
            yield (answer or "Não consegui responder agora.") + (
                "\n\n*Para uma pesquisa nova na web, comece com \"pesquise ...\".*")
            return

        # Pergunta vaga demais ("carros"): sugere angulos antes de gastar minutos
        if len(question.split()) <= 2 and not dr.is_simple(question):
            raw = await loop.run_in_executor(None, lambda: dr._llm_call(
                VAGUE_PROMPT.format(question=question), model, timeout=60, fmt=_SUGG_SCHEMA))
            try:
                import json
                sugg = [s for s in json.loads(raw).get("sugestoes", []) if isinstance(s, str)][:3]
            except Exception:
                sugg = []
            lines = "\n".join(f"- {s}" for s in sugg) or f"- O que é {question} e como funciona?"
            yield (f"Sua pergunta sobre **{question}** está bem curta, e uma pesquisa profunda leva alguns "
                   f"minutos. Sobre o que exatamente você quer saber? Por exemplo:\n\n{lines}\n\n"
                   "Escreva a pergunta completa que eu pesquiso.")
            return

        if not _searxng_available(self.valves.SEARXNG_URL):
            await emit({"type": "status", "data": {"description": "SearXNG indisponível", "done": True}})
            yield (
                "⚠️ A busca na web não está disponível agora.\n\n"
                "O SearXNG precisa estar rodando. "
                "Inicie-o com `docker-compose up -d` na pasta `search/`."
            )
            return

        await emit({"type": "status", "data": {"description": "🔍 Iniciando pesquisa profunda…", "done": False}})

        def _run_research():
            from nous_search.deep_research import deep_research

            def _emit_sync(event):
                asyncio.run_coroutine_threadsafe(emit(event), loop)

            return deep_research(
                question,
                model=model,
                searxng_url=self.valves.SEARXNG_URL,
                max_iterations=self.valves.MAX_ITERATIONS,
                max_pages=self.valves.MAX_PAGES,
                results_per_query=self.valves.RESULTS_PER_QUERY,
                emit=_emit_sync,
            )

        try:
            result = await loop.run_in_executor(None, _run_research)
        except Exception as e:
            await emit({"type": "status", "data": {"description": "Erro na pesquisa", "done": True}})
            yield f"*(Erro durante a pesquisa: {e})*"
            return

        report = result.get("report", "Não foi possível gerar o relatório.")
        link = ""
        if result.get("sources") and not result.get("curta") and not result.get("parcial"):
            try:
                from nous_search.report import save
                rid = save(question, report, result["sources"], model)
                link = (f"\n\n---\n📄 [Abrir o relatório visual]({MONITOR_URL}/research/view?id={rid})"
                        " · também fica em Recursos > Relatórios")
            except Exception:
                pass
        await emit({"type": "status", "data": {"description": "Pesquisa concluída", "done": True}})
        yield report + link
