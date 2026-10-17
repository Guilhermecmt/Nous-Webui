# -*- coding: utf-8 -*-
"""
Contatos do Nous (NousData/nous_contacts.sqlite3).

Aprendidos sozinhos dos e-mails (remetentes e destinatarios) e editaveis no
painel. Servem para "manda um e-mail pra Maria": resolve_contact acha o
endereco pelo nome. Fatos sobre OUTRAS pessoas vivem aqui; fatos sobre o
usuario vivem na Memoria.
"""
import os
import re
import time
import sqlite3
import unicodedata
from email.utils import getaddresses

DB_NAME = "nous_contacts.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'manual', seen INTEGER NOT NULL DEFAULT 0,
    last_seen INTEGER, created_at INTEGER NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS contacts_email ON contacts(email) WHERE email != '';
"""

# Remetentes automaticos nao viram contato
_ROBOT = re.compile(r"(no-?reply|nao-?responda|naoresponda|mailer-daemon|notifica|newsletter|"
                    r"marketing|bounce|postmaster|^info@|^news@|^promo)", re.I)


def _data_dir():
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def connect():
    os.makedirs(_data_dir(), exist_ok=True)
    cx = sqlite3.connect(os.path.join(_data_dir(), DB_NAME), timeout=15)
    cx.row_factory = sqlite3.Row
    cx.executescript(_SCHEMA)
    return cx


def _norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _clean_email(e):
    e = (e or "").strip().strip("<>").lower()
    return e if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) else ""


def upsert(cx, name, email_addr, phone="", notes="", source="manual", seen=0):
    email_addr = _clean_email(email_addr)
    name = (name or "").strip().strip('"')
    if not email_addr and not name:
        raise ValueError("o contato precisa de nome ou e-mail")
    now = int(time.time())
    row = cx.execute("SELECT * FROM contacts WHERE email=?", (email_addr,)).fetchone() if email_addr else None
    if row:
        cx.execute("""UPDATE contacts SET name=CASE WHEN ?!='' AND (name='' OR source='email') THEN ? ELSE name END,
                          phone=CASE WHEN ?!='' THEN ? ELSE phone END,
                          notes=CASE WHEN ?!='' THEN ? ELSE notes END,
                          seen=seen+?, last_seen=? WHERE id=?""",
                   (name, name, phone, phone, notes, notes, seen, now if seen else row["last_seen"], row["id"]))
        cid = row["id"]
    else:
        cur = cx.execute("INSERT INTO contacts (name, email, phone, notes, source, seen, last_seen, created_at) "
                         "VALUES (?,?,?,?,?,?,?,?)",
                         (name, email_addr, phone or "", notes or "", source, seen, now if seen else None, now))
        cid = cur.lastrowid
    cx.commit()
    return dict(cx.execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone())


def update(cx, cid, d):
    fields = {k: (d.get(k) or "").strip() for k in ("name", "email", "phone", "notes") if k in d}
    if "email" in fields:
        fields["email"] = _clean_email(fields["email"])
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        cx.execute(f"UPDATE contacts SET {sets}, source='manual' WHERE id=?", (*fields.values(), cid))
        cx.commit()
    r = cx.execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone()
    return dict(r) if r else None


def delete(cx, cid):
    cx.execute("DELETE FROM contacts WHERE id=?", (cid,))
    cx.commit()


def list_contacts(cx, q=None, limit=500):
    rows = [dict(r) for r in cx.execute(
        "SELECT * FROM contacts ORDER BY seen DESC, name COLLATE NOCASE LIMIT ?", (limit,))]
    if q:
        nq = _norm(q)
        rows = [r for r in rows if nq in _norm(r["name"]) or nq in r["email"] or nq in _norm(r["notes"])]
    return rows


def learn_from_headers(cx, headers, own=()):
    """Aprende contatos de [(campo, valor)] como ("From", "Maria <m@x.com>")."""
    own = {o.lower() for o in own}
    n = 0
    for name, addr in getaddresses([v for _k, v in headers if v]):
        addr = _clean_email(addr)
        if not addr or addr in own or _ROBOT.search(addr):
            continue
        upsert(cx, name, addr, source="email", seen=1)
        n += 1
    return n


def resolve(cx, query):
    """Contatos que combinam com um nome/apelido/e-mail, melhores primeiro."""
    q = _norm(query).strip()
    if not q:
        return []
    if "@" in q:
        r = cx.execute("SELECT * FROM contacts WHERE email=?", (_clean_email(q),)).fetchone()
        return [dict(r)] if r else [{"id": None, "name": "", "email": _clean_email(q), "seen": 0}]
    toks = q.split()
    out = []
    for r in cx.execute("SELECT * FROM contacts WHERE email != ''"):
        name = _norm(r["name"])
        local = r["email"].split("@")[0]
        words = re.findall(r"\w+", name) + re.findall(r"[a-z]+", local)
        if all(any(w.startswith(t) for w in words) for t in toks):
            exact = name == q or (name.split() or [""])[0] == q
            out.append((0 if exact else 1, -r["seen"], dict(r)))
    out.sort(key=lambda x: (x[0], x[1]))
    return [r for _a, _b, r in out[:5]]


# ------------------------------------------------------------------ vCard

def _vesc(v):
    return (v or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def export_vcf(cx):
    out = []
    for r in list_contacts(cx, limit=100000):
        out += ["BEGIN:VCARD", "VERSION:3.0", "FN:" + _vesc(r["name"] or r["email"])]
        if r["email"]:
            out.append("EMAIL;TYPE=INTERNET:" + r["email"])
        if r["phone"]:
            out.append("TEL:" + _vesc(r["phone"]))
        if r["notes"]:
            out.append("NOTE:" + _vesc(r["notes"]))
        out.append("END:VCARD")
    return "\r\n".join(out) + "\r\n"


def import_vcf(cx, text):
    n, cur = 0, None
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):  # desdobra linhas continuadas
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    for line in lines:
        up = line.upper()
        if up.startswith("BEGIN:VCARD"):
            cur = {"name": "", "email": "", "phone": "", "notes": ""}
        elif up.startswith("END:VCARD") and cur is not None:
            if cur["email"] or cur["name"]:
                try:
                    upsert(cx, cur["name"], cur["email"], cur["phone"], cur["notes"], source="manual")
                    n += 1
                except ValueError:
                    pass
            cur = None
        elif cur is not None and ":" in line:
            key, val = line.split(":", 1)
            key = key.split(";")[0].upper()
            val = val.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")
            if key == "FN":
                cur["name"] = val
            elif key == "N" and not cur["name"]:
                p = val.split(";")
                cur["name"] = " ".join(x for x in (p[1:2] + p[:1]) if x)
            elif key == "EMAIL" and not cur["email"]:
                cur["email"] = val
            elif key == "TEL" and not cur["phone"]:
                cur["phone"] = val
            elif key == "NOTE":
                cur["notes"] = val
    return n
