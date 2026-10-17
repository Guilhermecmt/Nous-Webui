# -*- coding: utf-8 -*-
"""
Rascunhos de e-mail esperando aprovacao (NousData/.email_drafts.json).

Regra do Nous: o chat NUNCA envia e-mail. Ele cria um rascunho aqui; o usuario
revisa no painel e clica Enviar (ou agenda o envio). Rascunhos agendados sao
enviados pelo relogio do servico de e-mail.
"""
import os
import json
import time
import uuid
import threading

FILE = ".email_drafts.json"
_lock = threading.Lock()


def _path():
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return os.path.join(v, FILE)
    return os.path.join(os.path.expanduser("~"), "NousData", FILE)


def _read():
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(items):
    p = _path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def list_drafts(include_done=False):
    items = _read()
    cutoff = time.time() - 7 * 86400  # enviados ficam visiveis por uma semana
    if not include_done:
        items = [d for d in items if d["status"] != "enviado" or d.get("sent_at", 0) > cutoff]
    return sorted(items, key=lambda d: d.get("created", 0), reverse=True)


def create(to, subject, body, account=None, to_name="", in_reply_to=None, origem="painel"):
    if "@" not in (to or ""):
        raise ValueError("endereco de destino invalido")
    d = {"id": uuid.uuid4().hex[:12], "to": to.strip(), "to_name": to_name or "", "subject": subject or "",
         "body": body or "", "account": account, "in_reply_to": in_reply_to, "origem": origem,
         "created": int(time.time()), "send_at": None, "status": "pendente", "error": None}
    with _lock:
        items = _read()
        items.append(d)
        _write(items)
    return d


def update(did, fields):
    allowed = {"to", "subject", "body", "account", "send_at", "status", "error", "sent_at"}
    with _lock:
        items = _read()
        for d in items:
            if d["id"] == did:
                d.update({k: v for k, v in fields.items() if k in allowed})
                _write(items)
                return d
    return None


def delete(did):
    with _lock:
        items = [d for d in _read() if d["id"] != did]
        _write(items)


def get(did):
    return next((d for d in _read() if d["id"] == did), None)


def due(now=None):
    now = now or time.time()
    return [d for d in _read() if d["status"] == "agendado" and d.get("send_at") and d["send_at"] <= now]
