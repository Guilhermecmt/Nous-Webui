# -*- coding: utf-8 -*-
"""
Habilidades do Nous: receitas de "como fazer" que o Nous aprende e reutiliza.

Cada habilidade e' um arquivo Markdown legivel em
<DATA_DIR>/skills/<user_id>/<id>.md, no estilo SKILL.md:

    ---
    nome: Cobrar cliente com educacao
    quando_usar: quando o usuario pedir para cobrar um pagamento atrasado
    origem: conversa | manual | importada
    criado: 2026-10-16
    ---
    1. Cumprimente pelo nome...

O filtro nous_skills.py le estes mesmos arquivos (formato e' o contrato).

<id>.md.bak e' a versao anterior a uma atualizacao. propostas/<id>.json sao regras
tiradas de correcoes: so' viram habilidade quando a pessoa aprova aqui.
"""
import os
import re
import sys
import json
import shutil
import datetime
import unicodedata

_UTIL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utilidades")
if _UTIL not in sys.path:
    sys.path.append(_UTIL)

import ameacas  # noqa: E402

FIELDS = ("nome", "quando_usar", "origem", "criado", "fonte")
MAX_BODY = 12000


def data_dir():
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def _safe(s):
    return re.sub(r"[^A-Za-z0-9_-]", "", s or "")[:64]


def user_dir(user_id):
    uid = _safe(user_id)
    if not uid:
        raise ValueError("user_id ausente")
    d = os.path.join(data_dir(), "skills", uid)
    os.makedirs(d, exist_ok=True)
    return d


def slugify(text):
    t = unicodedata.normalize("NFD", text or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:48] or "habilidade"


def parse(text):
    """-> dict(nome, quando_usar, origem, criado, fonte, corpo)."""
    meta, body = {}, text or ""
    m = re.match(r"﻿?---\s*\n(.*?)\n---\s*\n?(.*)\Z", body, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip().strip('"').strip("'")
        body = m.group(2)
    # SKILL.md do Claude usa name/description: aceita os dois
    out = {
        "nome": meta.get("nome") or meta.get("name") or "",
        "quando_usar": meta.get("quando_usar") or meta.get("description") or "",
        "origem": meta.get("origem") or "",
        "criado": meta.get("criado") or "",
        "fonte": meta.get("fonte") or "",
        "corpo": body.strip(),
    }
    if not out["nome"]:
        h = re.search(r"^#\s+(.+)$", out["corpo"], re.M)
        out["nome"] = h.group(1).strip() if h else ""
    return out


def render(s):
    one = lambda v: re.sub(r"\s+", " ", str(v or "")).strip()  # noqa: E731
    lines = ["---"] + [f"{k}: {one(s.get(k))}" for k in FIELDS if s.get(k)] + ["---", ""]
    return "\n".join(lines) + (s.get("corpo") or "").strip() + "\n"


def list_skills(user_id):
    d = user_dir(user_id)
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".md"):
            continue
        p = os.path.join(d, f)
        try:
            s = parse(open(p, encoding="utf-8").read())
        except Exception:
            continue
        s["id"] = f[:-3]
        s["atualizado"] = int(os.path.getmtime(p))
        out.append(s)
    out.sort(key=lambda s: s["nome"].lower())
    return out


def get_skill(user_id, sid):
    p = os.path.join(user_dir(user_id), _safe(sid) + ".md")
    if not os.path.isfile(p):
        return None
    s = parse(open(p, encoding="utf-8").read())
    s["id"] = _safe(sid)
    return s


def save_skill(user_id, s, sid=None):
    nome = (s.get("nome") or "").strip()
    quando = (s.get("quando_usar") or "").strip()
    corpo = (s.get("corpo") or "").strip()
    if not nome or not corpo:
        raise ValueError("a habilidade precisa de nome e passos")
    if not quando:
        raise ValueError("diga quando o Nous deve usar esta habilidade")
    if len(corpo) > MAX_BODY:
        raise ValueError("passos longos demais (limite de 12 mil caracteres)")
    # o que a propria pessoa escreve passa; o que veio de um link pode ser armadilha
    if s.get("origem") == "importada" and ameacas.varrer("\n".join((nome, quando, corpo))):
        raise ValueError("esta habilidade tem trechos que tentam dar ordens escondidas para a IA e nao foi salva. "
                         "Se confia no texto, copie os passos para uma habilidade nova")
    d = user_dir(user_id)
    sid = _safe(sid) if sid else None
    if not sid:
        base = slugify(nome)
        sid, i = base, 2
        while os.path.exists(os.path.join(d, sid + ".md")):
            sid, i = f"{base}-{i}", i + 1
    rec = {"nome": nome, "quando_usar": quando, "corpo": corpo,
           "origem": s.get("origem") or "manual", "fonte": s.get("fonte") or "",
           "criado": s.get("criado") or datetime.date.today().isoformat()}
    with open(os.path.join(d, sid + ".md"), "w", encoding="utf-8") as f:
        f.write(render(rec))
    rec["id"] = sid
    return rec


def delete_skill(user_id, sid):
    p = os.path.join(user_dir(user_id), _safe(sid) + ".md")
    for f in (p, p + ".bak"):  # apagar e' apagar: a copia nao fica para tras
        if os.path.isfile(f):
            os.remove(f)


# ------------------------------------------------------------------ propostas

def _proposal_path(user_id, pid):
    pid = _safe(pid)
    if not pid:
        raise ValueError("proposta nao encontrada")
    return os.path.join(user_dir(user_id), "propostas", pid + ".json")


def list_proposals(user_id):
    d = os.path.join(user_dir(user_id), "propostas")
    if not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            try:
                with open(os.path.join(d, f), encoding="utf-8") as h:
                    p = json.load(h)
            except (OSError, ValueError):
                continue
            if isinstance(p, dict):
                p["id"] = f[:-5]
                out.append(p)
    return out


def reject_proposal(user_id, pid):
    p = _proposal_path(user_id, pid)
    if os.path.isfile(p):
        os.remove(p)


def _add_steps(corpo, passos):
    """Acrescenta ao fim o que ainda nao esta la', sem precisar do modelo."""
    linhas = corpo.strip().splitlines()
    ja = {re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", x).strip().casefold() for x in linhas}
    n = sum(1 for x in linhas if re.match(r"\s*\d+[.)]", x))
    for p in passos:
        if p.casefold() not in ja:
            n += 1
            linhas.append(f"{n}. {p}")
    return "\n".join(linhas)


def approve_proposal(user_id, pid):
    """Vira habilidade. Se ja' existe uma com esse nome, atualiza (com .bak) em vez de criar -2."""
    p = _proposal_path(user_id, pid)
    if not os.path.isfile(p):
        raise ValueError("proposta nao encontrada")
    with open(p, encoding="utf-8") as h:
        d = json.load(h)
    passos = [str(x).strip() for x in d.get("passos") or [] if str(x).strip()]
    nome, quando = str(d.get("nome") or ""), str(d.get("quando_usar") or "")
    # a conversa pode ter trazido texto da web: quem aprova nao ve ordem escondida
    if ameacas.varrer("\n".join([nome, quando, *passos])):
        raise ValueError("esta proposta tem trechos que tentam dar ordens escondidas para a IA e nao foi salva")
    sid = slugify(nome)
    atual = get_skill(user_id, sid)
    if atual:
        arq = os.path.join(user_dir(user_id), sid + ".md")
        shutil.copy2(arq, arq + ".bak")
        rec = save_skill(user_id, {**atual, "corpo": _add_steps(atual["corpo"], passos)}, sid=sid)
    else:
        corpo = "\n".join(f"{i + 1}. {x}" for i, x in enumerate(passos))
        rec = save_skill(user_id, {"nome": nome, "quando_usar": quando, "corpo": corpo, "origem": "conversa"})
    os.remove(p)
    return rec


def raw_url(url):
    """github.com/<u>/<r>/blob/<ref>/<path> -> raw.githubusercontent.com/..."""
    url = (url or "").strip()
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/blob/(.+)$", url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+?)/?$", url)
    if m:  # pasta de uma skill: pega o SKILL.md dela
        return (f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/"
                f"{m.group(3)}/{m.group(4)}/SKILL.md")
    return url
