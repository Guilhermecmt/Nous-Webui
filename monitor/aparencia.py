# -*- coding: utf-8 -*-
"""
Nous - escolha da paleta de cores (Aparencia).

A escolha e' da instalacao inteira e fica em NousData/aparencia.json
({"paleta": "pitaya"}). A tela principal le' e grava por aqui (monitor, 8990); o
Nous Code, a pagina do celular e os relatorios leem o mesmo arquivo. As paletas
em si estao em branding/paletas.json (ver branding/gerar_paletas.py).

Rotas:
  GET  /aparencia      -> {"paleta": id, "paletas": [{"id", "nome", "tag"}]}
  POST /aparencia      {"paleta": id} -> o mesmo; 400 se a paleta nao existe
  GET  /aparencia.js   -> window.NOUS_PALETA="id";  (tela de carregamento: e' file://,
                          nao passa no CORS; uma tag <script> nao manda Origin)
"""
import json
import os
import re
from pathlib import Path

from aiohttp import web

ARQUIVO = "aparencia.json"
PALETAS_JSON = Path(__file__).resolve().parent.parent / "branding" / "paletas.json"
PADRAO = "ouro"


def _paletas():
    try:
        with open(PALETAS_JSON, encoding="utf-8") as f:
            return json.load(f).get("paletas", [])
    except (OSError, ValueError):
        return [{"id": PADRAO, "nome": "Ouro", "tag": ""}]


def ids():
    return [p["id"] for p in _paletas()]


def ler(data_dir):
    """Paleta escolhida; qualquer problema (sem arquivo, corrompido, id antigo) = ouro."""
    try:
        with open(Path(data_dir) / ARQUIVO, encoding="utf-8") as f:
            v = json.load(f)
        p = v.get("paleta") if isinstance(v, dict) else None
    except (OSError, ValueError):
        return PADRAO
    return p if isinstance(p, str) and p in ids() else PADRAO


def gravar(data_dir, paleta):
    if paleta not in ids():
        raise ValueError(f"paleta desconhecida: {paleta!r}")
    d = Path(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (ARQUIVO + ".tmp")
    tmp.write_text(json.dumps({"paleta": paleta}), encoding="utf-8")
    os.replace(tmp, d / ARQUIVO)
    return paleta


def marcar_html(html, paleta):
    """Poe data-nous-paleta no primeiro <html> (relatorios de pesquisa). Ouro e' o padrao
    e fica sem atributo; paleta desconhecida nao entra."""
    if paleta == PADRAO or paleta not in ids():
        return html
    return re.sub(r"<html\b", '<html data-nous-paleta="%s"' % paleta, html, count=1, flags=re.I)


def _resposta(data_dir):
    return {"paleta": ler(data_dir),
            "paletas": [{"id": p["id"], "nome": p.get("nome", p["id"]), "tag": p.get("tag", "")} for p in _paletas()]}


def add_routes(app, data_dir_fn):
    async def h_get(request):
        return web.json_response(_resposta(data_dir_fn()), headers={"Cache-Control": "no-store"})

    async def h_post(request):
        try:
            corpo = await request.json()
            gravar(data_dir_fn(), corpo.get("paleta") if isinstance(corpo, dict) else None)
        except (ValueError, TypeError):
            return web.json_response({"error": "paleta desconhecida"}, status=400)
        return web.json_response(_resposta(data_dir_fn()))

    async def h_js(request):
        return web.Response(text="window.NOUS_PALETA=" + json.dumps(ler(data_dir_fn())) + ";",
                            content_type="application/javascript", headers={"Cache-Control": "no-store"})

    app.add_routes([web.get("/aparencia", h_get), web.post("/aparencia", h_post),
                    web.get("/aparencia.js", h_js)])
