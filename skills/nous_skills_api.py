# -*- coding: utf-8 -*-
"""
Nous Skills API - micro-servico REST local, porta 8997. Alimenta o painel
"Habilidades" (listar, editar, apagar, importar do GitHub).

Rotas:
  GET  /health
  GET  /skills?user_id=
  GET  /skills/get?user_id=&id=
  POST /skills          {user_id, id?, nome, quando_usar, corpo}
  POST /skills/delete   {user_id, id}
  POST /skills/fetch    {url} -> {nome, quando_usar, corpo} para REVISAR (nao salva)
  POST /skills/style    {user_id, textos:[...]} -> habilidade "Meu jeito de escrever"

CORS apenas de origem local (mesmo padrao do monitor).
"""
import os
import sys
import json
import urllib.parse

import requests
from aiohttp import web

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import skills_store as store  # noqa: E402

PORT = 8997


def _origin_ok(origin):
    if not origin:
        return True
    try:
        host = urllib.parse.urlparse(origin).hostname
    except Exception:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _host_ok(request):
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
    return host in ("localhost", "127.0.0.1", "::1")


def _cors_headers(origin):
    return {
        "Access-Control-Allow-Origin": origin if (origin and _origin_ok(origin)) else "null",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


@web.middleware
async def cors_mw(request, handler):
    origin = request.headers.get("Origin")
    if not _origin_ok(origin) or not _host_ok(request):
        return web.json_response({"error": "forbidden origin"}, status=403,
                                 headers=_cors_headers(origin))
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_cors_headers(origin))
    try:
        resp = await handler(request)
    except ValueError as e:
        resp = web.json_response({"error": str(e)}, status=400)
    resp.headers.update(_cors_headers(origin))
    return resp


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


async def h_health(request):
    return web.json_response({"ok": True})


async def h_list(request):
    return web.json_response({"skills": store.list_skills(request.query.get("user_id"))})


async def h_get(request):
    s = store.get_skill(request.query.get("user_id"), request.query.get("id"))
    if not s:
        raise ValueError("habilidade nao encontrada")
    return web.json_response({"skill": s})


async def h_save(request):
    d = await _body(request)
    return web.json_response({"skill": store.save_skill(d.get("user_id"), d, sid=d.get("id"))})


async def h_delete(request):
    d = await _body(request)
    store.delete_skill(d.get("user_id"), d.get("id"))
    return web.json_response({"ok": True})


async def h_fetch(request):
    d = await _body(request)
    url = store.raw_url(d.get("url"))
    if not url.lower().startswith("https://"):
        raise ValueError("cole um endereco https:// (ex.: link de um SKILL.md no GitHub)")
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Nous-Skills/1.0"})
        r.raise_for_status()
    except Exception:
        raise ValueError("nao consegui baixar esse endereco")
    if len(r.text) > 200000 or "<html" in r.text[:500].lower():
        raise ValueError("isso nao parece um arquivo de habilidade (.md)")
    s = store.parse(r.text)
    s["corpo"] = s["corpo"][:store.MAX_BODY]
    s["fonte"] = d.get("url")
    s["origem"] = "importada"
    return web.json_response({"skill": s})


# ---- "escreva como eu" --------------------------------------------------------
# Textos do usuario -> guia de estilo -> habilidade "Meu jeito de escrever", que o
# filtro Nous Skills aplica sozinho quando ele pede para escrever algo.

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")
STYLE_ID = "meu-jeito-de-escrever"
_STYLE_SCHEMA = {"type": "object", "required": ["tom", "regras"],
                 "properties": {"tom": {"type": "string"},
                                "regras": {"type": "array", "items": {"type": "string"}},
                                "saudacoes_e_despedidas": {"type": "array", "items": {"type": "string"}},
                                "expressoes_tipicas": {"type": "array", "items": {"type": "string"}}}}
_STYLE_PROMPT = """Abaixo estao textos escritos pelo usuario. Descreva o JEITO DE ESCREVER dele para que
um assistente escreva igual: tom (formal/informal, caloroso/direto), tamanho das frases, uso de
emojis e pontuacao, como cumprimenta e se despede, expressoes que repete. NAO copie o assunto
dos textos (nomes, valores, datas): so' o estilo. Em portugues.

TEXTOS:
{textos}"""


def _local_model():
    try:
        for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", []):
            n = m.get("name", "")
            if "/" not in n and not any(p in n.lower() for p in _EMBED):
                return n
    except Exception:
        pass
    return None


def _style(user_id, textos):
    model = _local_model()
    if not model:
        raise ValueError("nenhum modelo de conversa instalado")
    joined = "\n\n---\n\n".join(t.strip()[:3000] for t in textos if t.strip())
    r = requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": model, "prompt": _STYLE_PROMPT.format(textos=joined), "stream": False,
                            "think": False, "format": _STYLE_SCHEMA,
                            "options": {"temperature": 0.2, "num_ctx": NUM_CTX}}, timeout=300)
    r.raise_for_status()
    d = json.loads(r.json().get("response") or "{}")
    regras = [x for x in d.get("regras") or [] if isinstance(x, str) and x.strip()]
    if not regras:
        raise ValueError("nao consegui descrever o estilo; tente com textos maiores")
    corpo = [f"Tom: {d.get('tom', '').strip()}", "", "Ao escrever em nome do usuario:"]
    corpo += [f"{i + 1}. {x.strip()}" for i, x in enumerate(regras)]
    if d.get("saudacoes_e_despedidas"):
        corpo += ["", "Cumprimentos e despedidas que ele usa: " + "; ".join(d["saudacoes_e_despedidas"][:6])]
    if d.get("expressoes_tipicas"):
        corpo += ["Expressoes tipicas: " + "; ".join(d["expressoes_tipicas"][:8])]
    return store.save_skill(user_id, {
        "nome": "Meu jeito de escrever", "corpo": "\n".join(corpo), "origem": "estilo",
        "quando_usar": ("quando o usuario pedir para escrever, redigir ou responder um texto, "
                        "e-mail, mensagem ou post em nome dele")}, sid=STYLE_ID)


async def h_style(request):
    d = await _body(request)
    textos = [t for t in (d.get("textos") or []) if isinstance(t, str)]
    if sum(len(t.strip()) for t in textos) < 200:
        raise ValueError("cole pelo menos um ou dois textos seus (uns 3 paragrafos no total)")
    import asyncio
    skill = await asyncio.get_event_loop().run_in_executor(None, _style, d.get("user_id"), textos)
    return web.json_response({"skill": skill})


def build_app():
    app = web.Application(middlewares=[cors_mw])
    app.add_routes([
        web.get("/health", h_health),
        web.get("/skills", h_list),
        web.get("/skills/get", h_get),
        web.post("/skills", h_save),
        web.post("/skills/delete", h_delete),
        web.post("/skills/fetch", h_fetch),
        web.post("/skills/style", h_style),
    ])
    return app


if __name__ == "__main__":
    port = int(os.environ.get("NOUS_SKILLS_PORT", PORT))
    web.run_app(build_app(), host="127.0.0.1", port=port, print=None)
