# -*- coding: utf-8 -*-
"""
Nous Email API — micro-serviço REST local, porta 8995.

Rotas:
  GET  /health
  GET  /status              conta conectada? (sem expor senha)
  POST /connect             {imap, smtp, imap_port, smtp_port, user, app_password}
  POST /disconnect          apaga .email_account.json
  GET  /inbox               lista os 20 emails mais recentes + triagem LLM local
  GET  /message?uid=        corpo + resumo LLM local
  POST /draft?uid=          gera rascunho de resposta (LLM local); NÃO envia
  POST /send                {to, subject, body, in_reply_to?} → envia após confirmação

CORS apenas de origem local (mesmo padrão da Memory API).
Nenhum dado de email vai para modelos de nuvem — forçado aqui.
"""
import os
import json
import time
import urllib.parse
import requests as _req
from aiohttp import web

import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from nous_email import (
    load_account, save_account, delete_account,
    test_connection, list_recent, get_message, send_message,
    detect_servers,
)

PORT = 8995
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

# Cache simples em memória: uid → {category, summary, draft, ts}
_cache: dict = {}
_CACHE_TTL = 3600  # 1h


def _local_model() -> str:
    """Pega o primeiro modelo de chat local instalado. Nunca usa modelos de nuvem."""
    try:
        r = _req.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        models = r.json().get("models", [])
        _embed = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")
        for m in models:
            name = m.get("name", "")
            # id com '/' = modelo de nuvem — nunca usar aqui
            if "/" not in name and not any(p in name.lower() for p in _embed):
                return name
    except Exception:
        pass
    return os.environ.get("NOUS_MODEL", "gemma4:12b")


def _llm(prompt: str, timeout: int = 60) -> str:
    model = _local_model()
    try:
        r = _req.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.3}},
            timeout=timeout,
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    except Exception:
        return ""


def _triage(subject: str, sender: str, snippet: str) -> tuple[str, str]:
    prompt = (
        "Você é um assistente de triagem de email. Classifique o email abaixo em uma "
        "das categorias: Importante, Pode esperar, Promoção, Notificação, Spam.\n"
        f"De: {sender}\nAssunto: {subject}\nTrecho: {snippet[:300]}\n\n"
        "Responda com JSON: {\"categoria\": \"...\", \"resumo\": \"uma linha descrevendo o email\"}"
    )
    raw = _llm(prompt, timeout=30)
    try:
        m = __import__("re").search(r"\{.*?\}", raw, __import__("re").DOTALL)
        if m:
            data = json.loads(m.group())
            return data.get("categoria", "Não classificado"), data.get("resumo", "")
    except Exception:
        pass
    return "Não classificado", raw[:100] if raw else ""


def _summarize(body: str, subject: str) -> str:
    prompt = (
        f"Resuma o seguinte email com assunto '{subject}' em 3-5 frases em português, "
        f"destacando as ações necessárias, se houver:\n\n{body[:2000]}"
    )
    return _llm(prompt, timeout=45) or "Não foi possível gerar o resumo."


def _draft_reply(body: str, subject: str, sender: str) -> str:
    prompt = (
        f"Escreva uma resposta educada e profissional em português ao email abaixo.\n"
        f"De: {sender}\nAssunto: {subject}\n\nConteúdo do email:\n{body[:1500]}\n\n"
        "Escreva APENAS o corpo da resposta, sem saudação genérica, pronto para edição."
    )
    return _llm(prompt, timeout=60) or "Não foi possível gerar o rascunho."


# ---- CORS (idêntico à Memory API) -------------------------------------------

def _origin_ok(origin: str | None) -> bool:
    if not origin:
        return True
    try:
        host = urllib.parse.urlparse(origin).hostname
    except Exception:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _cors_headers(origin: str | None) -> dict:
    return {
        "Access-Control-Allow-Origin":  origin if (origin and _origin_ok(origin)) else "null",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


@web.middleware
async def cors_mw(request, handler):
    origin = request.headers.get("Origin")
    if not _origin_ok(origin):
        return web.json_response({"error": "forbidden origin"}, status=403,
                                 headers=_cors_headers(origin))
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_cors_headers(origin))
    resp = await handler(request)
    resp.headers.update(_cors_headers(origin))
    return resp


# ---- helpers -----------------------------------------------------------------

async def _json_body(request):
    try:
        return await request.json()
    except Exception:
        return None


# ---- handlers ---------------------------------------------------------------

async def h_health(request):
    return web.json_response({"ok": True})


async def h_status(request):
    acc = load_account()
    if not acc:
        return web.json_response({"connected": False})
    return web.json_response({
        "connected": True,
        "user": acc.get("user", ""),
        "imap": acc.get("imap", ""),
    })


async def h_connect(request):
    body = await _json_body(request)
    if not body:
        return web.json_response({"error": "JSON inválido"}, status=400)
    user = (body.get("user") or "").strip()
    pwd = (body.get("app_password") or "").strip()
    if not user or not pwd:
        return web.json_response({"error": "user e app_password são obrigatórios"}, status=400)

    detected = detect_servers(user)
    acc = {
        "user": user,
        "app_password": pwd,
        "imap": body.get("imap") or detected.get("imap", ""),
        "smtp": body.get("smtp") or detected.get("smtp", ""),
        "imap_port": int(body.get("imap_port") or detected.get("imap_port", 993)),
        "smtp_port": int(body.get("smtp_port") or detected.get("smtp_port", 465)),
    }
    if not acc["imap"] or not acc["smtp"]:
        return web.json_response(
            {"error": "Não reconheço este provedor. Informe imap e smtp manualmente."},
            status=400,
        )

    ok, msg = test_connection(acc)
    if not ok:
        return web.json_response({"error": msg}, status=401)

    save_account(acc)
    _cache.clear()
    return web.json_response({"ok": True, "user": user})


async def h_disconnect(request):
    delete_account()
    _cache.clear()
    return web.json_response({"ok": True})


async def h_inbox(request):
    acc = load_account()
    if not acc:
        return web.json_response({"error": "sem conta configurada"}, status=400)

    import asyncio
    loop = asyncio.get_event_loop()
    msgs = await loop.run_in_executor(None, lambda: list_recent(20))

    if msgs and "error" in msgs[0]:
        return web.json_response({"error": msgs[0]["error"]}, status=502)

    now = time.time()
    for m in msgs:
        uid = m.get("uid", "")
        cached = _cache.get(uid)
        if cached and (now - cached.get("ts", 0)) < _CACHE_TTL:
            m["category"] = cached["category"]
            m["summary"] = cached["summary"]
        else:
            cat, summ = await loop.run_in_executor(
                None,
                lambda s=m["subject"], f=m["from"], sn=m["snippet"]: _triage(s, f, sn),
            )
            m["category"] = cat
            m["summary"] = summ
            _cache[uid] = {"category": cat, "summary": summ, "ts": now}

    return web.json_response(msgs)


async def h_message(request):
    uid = request.rel_url.query.get("uid", "").strip()
    if not uid:
        return web.json_response({"error": "uid obrigatório"}, status=400)

    import asyncio
    loop = asyncio.get_event_loop()
    msg = await loop.run_in_executor(None, lambda: get_message(uid))

    if "error" in msg:
        return web.json_response(msg, status=502)

    cached = _cache.get(uid, {})
    if "summary_full" in cached:
        msg["summary"] = cached["summary_full"]
    else:
        summary = await loop.run_in_executor(
            None,
            lambda b=msg.get("body",""), s=msg.get("subject",""): _summarize(b, s),
        )
        msg["summary"] = summary
        _cache.setdefault(uid, {})["summary_full"] = summary

    return web.json_response(msg)


async def h_draft(request):
    uid = request.rel_url.query.get("uid", "").strip()
    if not uid:
        return web.json_response({"error": "uid obrigatório"}, status=400)

    import asyncio
    loop = asyncio.get_event_loop()
    msg = await loop.run_in_executor(None, lambda: get_message(uid))
    if "error" in msg:
        return web.json_response(msg, status=502)

    cached = _cache.get(uid, {})
    if "draft" in cached:
        return web.json_response({"draft": cached["draft"]})

    draft = await loop.run_in_executor(
        None,
        lambda b=msg.get("body",""), s=msg.get("subject",""), f=msg.get("from",""): _draft_reply(b, s, f),
    )
    _cache.setdefault(uid, {})["draft"] = draft
    return web.json_response({"draft": draft})


async def h_send(request):
    body = await _json_body(request)
    if not body:
        return web.json_response({"error": "JSON inválido"}, status=400)
    to = (body.get("to") or "").strip()
    subject = (body.get("subject") or "").strip()
    text = (body.get("body") or "").strip()
    if not to or not subject or not text:
        return web.json_response({"error": "to, subject e body são obrigatórios"}, status=400)

    import asyncio
    loop = asyncio.get_event_loop()
    ok, msg = await loop.run_in_executor(
        None,
        lambda: send_message(to, subject, text, body.get("in_reply_to")),
    )
    if not ok:
        return web.json_response({"error": msg}, status=502)
    return web.json_response({"ok": True, "message": msg})


# ---- app --------------------------------------------------------------------

def build_app():
    app = web.Application(middlewares=[cors_mw])
    app.add_routes([
        web.get("/health",      h_health),
        web.get("/status",      h_status),
        web.post("/connect",    h_connect),
        web.post("/disconnect", h_disconnect),
        web.get("/inbox",       h_inbox),
        web.get("/message",     h_message),
        web.post("/draft",      h_draft),
        web.post("/send",       h_send),
    ])
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=PORT, print=None)
