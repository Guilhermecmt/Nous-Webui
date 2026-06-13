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
import sys
import asyncio
from typing import Optional

from pydantic import BaseModel, Field

# Adiciona o diretório pai ao path para importar nous_search
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


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

        if not _searxng_available(self.valves.SEARXNG_URL):
            await emit({"type": "status", "data": {"description": "SearXNG indisponível", "done": True}})
            yield (
                "⚠️ A busca na web não está disponível agora.\n\n"
                "O SearXNG precisa estar rodando. "
                "Inicie-o com `docker-compose up -d` na pasta `search/`."
            )
            return

        await emit({"type": "status", "data": {"description": "🔍 Iniciando pesquisa profunda…", "done": False}})

        loop = asyncio.get_event_loop()

        def _run_research():
            from nous_search.deep_research import deep_research

            def _emit_sync(event):
                asyncio.run_coroutine_threadsafe(emit(event), loop)

            return deep_research(
                question,
                model=self.valves.OLLAMA_MODEL,
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

        await emit({"type": "status", "data": {"description": "Pesquisa concluída", "done": True}})
        yield result.get("report", "Não foi possível gerar o relatório.")
