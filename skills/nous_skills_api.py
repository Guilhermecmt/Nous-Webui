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

CORS apenas de origem local (mesmo padrao do monitor).
"""
import os
import sys
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


def build_app():
    app = web.Application(middlewares=[cors_mw])
    app.add_routes([
        web.get("/health", h_health),
        web.get("/skills", h_list),
        web.get("/skills/get", h_get),
        web.post("/skills", h_save),
        web.post("/skills/delete", h_delete),
        web.post("/skills/fetch", h_fetch),
    ])
    return app


if __name__ == "__main__":
    port = int(os.environ.get("NOUS_SKILLS_PORT", PORT))
    web.run_app(build_app(), host="127.0.0.1", port=port, print=None)
