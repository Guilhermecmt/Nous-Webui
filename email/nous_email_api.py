# -*- coding: utf-8 -*-
"""
Nous Email API — micro-serviço REST local, porta 8995.

Rotas (todas aceitam ?account= / "account" para escolher a conta; sem ela,
vale a conta padrão):
  GET  /health
  GET  /status                  contas conectadas (sem expor senha)
  GET  /accounts                POST /accounts/default {account}
  POST /connect                 {imap, smtp, imap_port, smtp_port, user, app_password} -> adiciona conta
  POST /disconnect              {account?} -> remove uma conta (ou todas)
  GET  /inbox                   20 mais recentes + triagem LLM local (aprende contatos)
  GET  /message?uid=            corpo + resumo + anexos + convite
  POST /draft?uid=              gera rascunho de resposta (LLM local); NÃO envia
  POST /send                    {to, subject, body, in_reply_to?} → envia após confirmação
  GET  /attachment?uid=&idx=    baixa um anexo
  POST /attachment/read         {uid, idx} → texto + resumo do anexo (PDF, DOCX, planilha, imagem)
  POST /invite/add              {uid, user_id} → convite (.ics) vai para a Agenda do Nous
  GET  /newsletters             remetentes em massa com link de descadastro
  POST /unsubscribe             {sender, link} → descadastra (mailto: envia; http: devolve o link)
  GET  /drafts                  rascunhos esperando aprovação (o chat cria, o usuário envia)
  POST /drafts                  {to, subject, body, to_name?, origem?}
  POST /drafts/update | /drafts/send | /drafts/schedule {id, send_at} | /drafts/delete
  GET  /contacts?q=             POST /contacts | /contacts/update | /contacts/delete
  GET  /contacts/resolve?q=     melhor contato para um nome ("Maria")
  POST /contacts/import         {vcf}   GET /contacts/export

CORS apenas de origem local + checagem de Host (DNS rebinding).
Nenhum dado de email vai para modelos de nuvem — forçado aqui.
"""
import os
import re
import sys
import json
import time
import asyncio
import urllib.parse
import requests as _req
from aiohttp import web

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(os.path.dirname(_HERE), "utilidades")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from nous_email import (  # noqa: E402
    load_account, save_account, delete_account, list_accounts, set_default,
    test_connection, list_recent, get_message, get_attachment, send_message,
    detect_servers,
)
import contacts as ct  # noqa: E402
import drafts  # noqa: E402

PORT = 8995
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
# Mesmo num_ctx do chat (monitor/register_model_ctx.py): com outro valor o
# Ollama recarrega o modelo (no 0.30 o padrao chega a 256k = estoura a VRAM).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))
AGENDA_URL = "http://127.0.0.1:8996"

# Cache simples em memória: "conta|uid" → {category, summary, draft, ts}
_cache: dict = {}
_CACHE_TTL = 3600  # 1h
_TRIAGE_SCHEMA = {"type": "object", "required": ["categoria", "resumo"],
                  "properties": {"categoria": {"type": "string", "enum": [
                      "Importante", "Pode esperar", "Promoção", "Notificação", "Spam"]},
                      "resumo": {"type": "string"}}}


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


def _llm(prompt: str, timeout: int = 60, fmt=None) -> str:
    payload = {"model": _local_model(), "prompt": prompt, "stream": False,
               "options": {"temperature": 0.3, "num_ctx": NUM_CTX}}
    if fmt is not None:
        payload["format"] = fmt
        payload["think"] = False
    try:
        r = _req.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
        r.raise_for_status()
        return (r.json().get("response") or "").strip()
    except Exception:
        return ""


def _triage(subject: str, sender: str, snippet: str, bulk: bool = False) -> tuple[str, str]:
    prompt = (
        "Você é um assistente de triagem de email. Classifique o email abaixo em uma "
        "das categorias: Importante, Pode esperar, Promoção, Notificação, Spam.\n"
        f"De: {sender}\nAssunto: {subject}\nTrecho: {snippet[:300]}\n"
        + ("(Enviado em massa: lista/newsletter.)\n" if bulk else "")
        + "\nResponda com JSON: {\"categoria\": \"...\", \"resumo\": \"uma linha descrevendo o email\"}"
    )
    raw = _llm(prompt, timeout=60, fmt=_TRIAGE_SCHEMA)
    try:
        data = json.loads(raw)
        return data.get("categoria", "Não classificado"), data.get("resumo", "")
    except Exception:
        return "Não classificado", ""


def _summarize(body: str, subject: str) -> str:
    prompt = (
        f"Resuma o seguinte email com assunto '{subject}' em 3-5 frases em português, "
        f"destacando as ações necessárias, se houver:\n\n{body[:4000]}"
    )
    return _llm(prompt, timeout=90) or "Não foi possível gerar o resumo."


def _draft_reply(body: str, subject: str, sender: str) -> str:
    prompt = (
        f"Escreva uma resposta educada e profissional em português ao email abaixo.\n"
        f"De: {sender}\nAssunto: {subject}\n\nConteúdo do email:\n{body[:3000]}\n\n"
        "Escreva APENAS o corpo da resposta, sem saudação genérica, pronto para edição."
    )
    return _llm(prompt, timeout=120) or "Não foi possível gerar o rascunho."


# ---- CORS + Host (DNS rebinding) ---------------------------------------------

def _origin_ok(origin: str | None) -> bool:
    if not origin:
        return True
    try:
        host = urllib.parse.urlparse(origin).hostname
    except Exception:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _host_ok(request) -> bool:
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
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


# ---- helpers -----------------------------------------------------------------

async def _json_body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else None
    except Exception:
        return None


def _acct(request, body=None):
    return (body or {}).get("account") or request.rel_url.query.get("account") or None


def _run(fn, *a):
    return asyncio.get_event_loop().run_in_executor(None, lambda: fn(*a))


def _learn(msgs, own):
    cx = ct.connect()
    try:
        heads = []
        for m in msgs:
            if not m.get("bulk"):  # newsletter nao vira contato
                heads.append(("From", m.get("from", "")))
        ct.learn_from_headers(cx, heads, own)
    finally:
        cx.close()


# ---- handlers: contas ---------------------------------------------------------

async def h_health(request):
    return web.json_response({"ok": True})


async def h_status(request):
    accs = list_accounts()
    if not accs:
        return web.json_response({"connected": False, "accounts": []})
    padrao = next((a for a in accs if a["padrao"]), accs[0])
    return web.json_response({"connected": True, "user": padrao["user"], "imap": padrao["imap"],
                              "accounts": accs})


async def h_accounts(request):
    return web.json_response({"accounts": list_accounts()})


async def h_default(request):
    body = await _json_body(request) or {}
    if not set_default(body.get("account") or ""):
        return web.json_response({"error": "conta não encontrada"}, status=404)
    return web.json_response({"ok": True})


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

    ok, msg = await _run(test_connection, acc)
    if not ok:
        return web.json_response({"error": msg}, status=401)

    save_account(acc)
    return web.json_response({"ok": True, "user": user})


async def h_disconnect(request):
    body = await _json_body(request) or {}
    account = body.get("account")
    delete_account(account)
    for k in [k for k in _cache if not account or k.startswith(account + "|")]:
        _cache.pop(k, None)
    return web.json_response({"ok": True})


# ---- handlers: caixa de entrada -------------------------------------------------

async def h_inbox(request):
    account = _acct(request)
    acc = load_account(account)
    if not acc:
        return web.json_response({"error": "sem conta configurada"}, status=400)
    msgs = await _run(list_recent, 20, acc["user"])
    if msgs and "error" in msgs[0]:
        return web.json_response({"error": msgs[0]["error"]}, status=502)

    now = time.time()
    for m in msgs:
        key = f"{acc['user']}|{m.get('uid', '')}"
        cached = _cache.get(key)
        if cached and "category" in cached and (now - cached.get("ts", 0)) < _CACHE_TTL:
            m["category"] = cached["category"]
            m["summary"] = cached["summary"]
        else:
            cat, summ = await _run(_triage, m["subject"], m["from"], m["snippet"], m.get("bulk", False))
            m["category"] = cat
            m["summary"] = summ
            _cache.setdefault(key, {}).update(category=cat, summary=summ, ts=now)
    try:
        await _run(_learn, msgs, [a["user"] for a in list_accounts()])
    except Exception:
        pass
    return web.json_response(msgs)


async def h_message(request):
    uid = request.rel_url.query.get("uid", "").strip()
    if not uid:
        return web.json_response({"error": "uid obrigatório"}, status=400)
    account = _acct(request)
    msg = await _run(get_message, uid, account)
    if "error" in msg:
        return web.json_response(msg, status=502)

    key = f"{account or ''}|{uid}"
    cached = _cache.get(key, {})
    if "summary_full" in cached:
        msg["summary"] = cached["summary_full"]
    else:
        msg["summary"] = await _run(_summarize, msg.get("body", ""), msg.get("subject", ""))
        _cache.setdefault(key, {})["summary_full"] = msg["summary"]
    return web.json_response(msg)


async def h_draft(request):
    uid = request.rel_url.query.get("uid", "").strip()
    if not uid:
        return web.json_response({"error": "uid obrigatório"}, status=400)
    account = _acct(request)
    msg = await _run(get_message, uid, account)
    if "error" in msg:
        return web.json_response(msg, status=502)

    key = f"{account or ''}|{uid}"
    cached = _cache.get(key, {})
    if "draft" in cached:
        return web.json_response({"draft": cached["draft"]})
    draft = await _run(_draft_reply, msg.get("body", ""), msg.get("subject", ""), msg.get("from", ""))
    _cache.setdefault(key, {})["draft"] = draft
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
    if "@" not in to:
        return web.json_response({"error": "Endereço de destino inválido."}, status=400)
    ok, msg = await _run(send_message, to, subject, text, body.get("in_reply_to"), _acct(request, body))
    if not ok:
        return web.json_response({"error": msg}, status=502)
    return web.json_response({"ok": True, "message": msg})


# ---- handlers: anexos e convites ----------------------------------------------

async def h_attachment(request):
    q = request.rel_url.query
    try:
        name, ctype, data = await _run(get_attachment, q.get("uid", ""), int(q.get("idx", "-1")), _acct(request))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=404)
    safe = re.sub(r'[\r\n"]', "", name)
    return web.Response(body=data, content_type=ctype or "application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="{safe}"'})


async def h_attachment_read(request):
    import leitura
    body = await _json_body(request) or {}
    try:
        name, ctype, data = await _run(get_attachment, str(body.get("uid", "")), int(body.get("idx", -1)),
                                       _acct(request, body))
    except Exception as e:
        return web.json_response({"error": str(e)}, status=404)
    text, why = await _run(leitura.extract_text, name, ctype, data)
    if not text:
        return web.json_response({"error": f"Não consegui ler {name}: {why}."}, status=422)
    boletos = [leitura.describe_boleto(leitura.decode_boleto(b)) for b in leitura.find_boletos(text)]
    resumo = await _run(_llm, "Resuma em português, em até 6 tópicos, o documento abaixo. Destaque "
                              "valores, prazos e o que o leitor precisa fazer.\n\n" + text[:12000], 180)
    return web.json_response({"name": name, "text": text[:20000], "summary": resumo,
                              "boletos": [b for b in boletos if b]})


async def h_invite_add(request):
    body = await _json_body(request) or {}
    uid, user_id = str(body.get("uid", "")), body.get("user_id")
    if not user_id:
        return web.json_response({"error": "user_id obrigatório"}, status=400)
    msg = await _run(get_message, uid, _acct(request, body))
    if not msg.get("invite"):
        return web.json_response({"error": "este e-mail não tem convite de calendário"}, status=404)
    try:
        r = await _run(lambda: _req.post(f"{AGENDA_URL}/ics/import",
                                         json={"user_id": user_id, "ics": msg["invite"]}, timeout=20))
        data = r.json()
    except Exception:
        return web.json_response({"error": "a Agenda do Nous não está no ar"}, status=502)
    if r.status_code != 200:
        return web.json_response(data, status=r.status_code)
    return web.json_response({"ok": True, "imported": data.get("imported", 0)})


# ---- handlers: newsletters -----------------------------------------------------

def _unsub_links(header):
    """List-Unsubscribe: <mailto:...>, <https://...> -> {"mailto": .., "http": ..}"""
    out = {}
    for link in re.findall(r"<([^>]+)>", header or ""):
        if link.lower().startswith("mailto:") and "mailto" not in out:
            out["mailto"] = link
        elif link.lower().startswith(("https://", "http://")) and "http" not in out:
            out["http"] = link
    return out


async def h_newsletters(request):
    """Revisao: remetentes em massa com descadastro. Nada e' movido nem apagado."""
    account = _acct(request)
    if not load_account(account):
        return web.json_response({"error": "sem conta configurada"}, status=400)
    msgs = await _run(list_recent, 80, account)
    if msgs and "error" in msgs[0]:
        return web.json_response({"error": msgs[0]["error"]}, status=502)
    by = {}
    for m in msgs:
        links = _unsub_links(m.get("list_unsubscribe"))
        if not links:
            continue
        sender = m["from"]
        e = by.setdefault(sender, {"sender": sender, "count": 0, "last_subject": m["subject"], **links})
        e["count"] += 1
    return web.json_response({"newsletters": sorted(by.values(), key=lambda x: -x["count"])})


async def h_unsubscribe(request):
    body = await _json_body(request) or {}
    link = (body.get("link") or "").strip()
    if link.lower().startswith("mailto:"):
        u = urllib.parse.urlparse(link)
        to = urllib.parse.unquote(u.path)
        qs = urllib.parse.parse_qs(u.query)
        subject = (qs.get("subject") or ["unsubscribe"])[0]
        text = (qs.get("body") or ["Por favor, remova meu endereco desta lista. / Please unsubscribe me."])[0]
        ok, msg = await _run(send_message, to, subject, text, None, _acct(request, body))
        if not ok:
            return web.json_response({"error": msg}, status=502)
        return web.json_response({"ok": True, "how": "email", "message": "Pedido de descadastro enviado."})
    if link.lower().startswith(("https://", "http://")):
        # Link web: o usuario abre e confirma (alguns pedem clique; nao clicamos por ele)
        return web.json_response({"ok": True, "how": "link", "url": link})
    return web.json_response({"error": "link de descadastro inválido"}, status=400)


# ---- handlers: rascunhos (aprovacao) ---------------------------------------------

async def h_drafts(request):
    return web.json_response({"drafts": drafts.list_drafts()})


async def h_draft_create(request):
    b = await _json_body(request) or {}
    d = drafts.create(b.get("to"), b.get("subject"), b.get("body"), b.get("account"),
                      b.get("to_name", ""), b.get("in_reply_to"), b.get("origem", "painel"))
    return web.json_response({"draft": d})


async def h_draft_update(request):
    b = await _json_body(request) or {}
    d = drafts.update(b.get("id"), {k: b[k] for k in ("to", "subject", "body", "account") if k in b})
    return web.json_response({"draft": d}) if d else web.json_response({"error": "não encontrado"}, status=404)


def _send_draft(d):
    ok, msg = send_message(d["to"], d["subject"], d["body"], d.get("in_reply_to"), d.get("account"))
    drafts.update(d["id"], {"status": "enviado" if ok else "erro", "error": None if ok else msg,
                            "sent_at": int(time.time()) if ok else None})
    return ok, msg


async def h_draft_send(request):
    b = await _json_body(request) or {}
    d = drafts.get(b.get("id"))
    if not d:
        return web.json_response({"error": "rascunho não encontrado"}, status=404)
    ok, msg = await _run(_send_draft, d)
    return web.json_response({"ok": ok, "message": msg}, status=200 if ok else 502)


async def h_draft_schedule(request):
    b = await _json_body(request) or {}
    send_at = int(b.get("send_at") or 0)
    if send_at <= time.time():
        return web.json_response({"error": "escolha um horário no futuro"}, status=400)
    d = drafts.update(b.get("id"), {"status": "agendado", "send_at": send_at, "error": None})
    return web.json_response({"draft": d}) if d else web.json_response({"error": "não encontrado"}, status=404)


async def h_draft_delete(request):
    b = await _json_body(request) or {}
    drafts.delete(b.get("id"))
    return web.json_response({"ok": True})


async def scheduler(app):
    """Envia os rascunhos agendados (o usuario ja' aprovou ao agendar)."""
    while True:
        try:
            for d in drafts.due():
                await _run(_send_draft, d)
        except Exception as e:
            print(f"[Nous][email] agendador: {e}", file=sys.stderr)
        await asyncio.sleep(30)


async def _start(app):
    app["sched"] = asyncio.get_event_loop().create_task(scheduler(app))


async def _stop(app):
    app["sched"].cancel()


# ---- handlers: contatos -----------------------------------------------------------

async def h_contacts(request):
    cx = ct.connect()
    try:
        return web.json_response({"contacts": ct.list_contacts(cx, request.rel_url.query.get("q"))})
    finally:
        cx.close()


async def h_contact_save(request):
    b = await _json_body(request) or {}
    cx = ct.connect()
    try:
        return web.json_response({"contact": ct.upsert(cx, b.get("name"), b.get("email"), b.get("phone", ""),
                                                       b.get("notes", ""))})
    finally:
        cx.close()


async def h_contact_update(request):
    b = await _json_body(request) or {}
    cx = ct.connect()
    try:
        return web.json_response({"contact": ct.update(cx, int(b.get("id") or 0), b)})
    finally:
        cx.close()


async def h_contact_delete(request):
    b = await _json_body(request) or {}
    cx = ct.connect()
    try:
        ct.delete(cx, int(b.get("id") or 0))
        return web.json_response({"ok": True})
    finally:
        cx.close()


async def h_contact_resolve(request):
    cx = ct.connect()
    try:
        return web.json_response({"matches": ct.resolve(cx, request.rel_url.query.get("q", ""))})
    finally:
        cx.close()


async def h_contacts_import(request):
    b = await _json_body(request) or {}
    cx = ct.connect()
    try:
        return web.json_response({"imported": ct.import_vcf(cx, b.get("vcf") or "")})
    finally:
        cx.close()


async def h_contacts_export(request):
    cx = ct.connect()
    try:
        return web.Response(text=ct.export_vcf(cx), content_type="text/vcard",
                            headers={"Content-Disposition": 'attachment; filename="contatos-nous.vcf"'})
    finally:
        cx.close()


# ---- app --------------------------------------------------------------------

def build_app():
    app = web.Application(middlewares=[cors_mw], client_max_size=8 * 1024 * 1024)
    app.add_routes([
        web.get("/health",      h_health),
        web.get("/status",      h_status),
        web.get("/accounts",    h_accounts),
        web.post("/accounts/default", h_default),
        web.post("/connect",    h_connect),
        web.post("/disconnect", h_disconnect),
        web.get("/inbox",       h_inbox),
        web.get("/message",     h_message),
        web.post("/draft",      h_draft),
        web.post("/send",       h_send),
        web.get("/attachment",  h_attachment),
        web.post("/attachment/read", h_attachment_read),
        web.post("/invite/add", h_invite_add),
        web.get("/newsletters", h_newsletters),
        web.post("/unsubscribe", h_unsubscribe),
        web.get("/drafts",      h_drafts),
        web.post("/drafts",     h_draft_create),
        web.post("/drafts/update", h_draft_update),
        web.post("/drafts/send", h_draft_send),
        web.post("/drafts/schedule", h_draft_schedule),
        web.post("/drafts/delete", h_draft_delete),
        web.get("/contacts",    h_contacts),
        web.post("/contacts",   h_contact_save),
        web.post("/contacts/update", h_contact_update),
        web.post("/contacts/delete", h_contact_delete),
        web.get("/contacts/resolve", h_contact_resolve),
        web.post("/contacts/import", h_contacts_import),
        web.get("/contacts/export", h_contacts_export),
    ])
    app.on_startup.append(_start)
    app.on_cleanup.append(_stop)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("NOUS_EMAIL_PORT", PORT))
    web.run_app(build_app(), host="127.0.0.1", port=port, print=None)
