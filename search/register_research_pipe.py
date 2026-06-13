# -*- coding: utf-8 -*-
"""
Instala/atualiza o Pipe 'Pesquisa Profunda (Nous)' direto no banco do Open WebUI.

Idempotente: pode rodar a cada inicialização do Nous.
Ativo apenas se o SearXNG estiver respondendo (auto-cura se o container cair).

USO:
    python search/register_research_pipe.py [--data-dir <DATA_DIR>]
"""
import os
import sys
import time
import json
import argparse
import sqlite3

FUNC_ID = "nous_research"
FUNC_NAME = "Pesquisa Profunda (Nous)"
DESC = (
    "Pesquisa a web em múltiplas etapas e entrega um relatório em markdown com "
    "citações [n] e lista de fontes. 100% local, sem API paga."
)
SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://localhost:8888")


def searxng_available(url: str = SEARXNG_URL, timeout: int = 5) -> bool:
    try:
        import requests
        r = requests.get(f"{url.rstrip('/')}/healthz", timeout=timeout)
        if r.status_code < 500:
            return True
    except Exception:
        pass
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


def resolve_db(data_dir):
    candidates = []
    if data_dir:
        candidates.append(data_dir)
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            candidates.append(v)
    for d in candidates:
        p = os.path.join(d, "webui.db")
        if os.path.isfile(p):
            return p
    return os.path.join(candidates[0], "webui.db") if candidates else None


def table_exists(cx, name):
    row = cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def pick_creator(cx):
    try:
        row = cx.execute(
            "SELECT id FROM user WHERE role='admin' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row:
            return row[0]
        row = cx.execute("SELECT id FROM user ORDER BY created_at LIMIT 1").fetchone()
        if row:
            return row[0]
    except Exception:
        pass
    return "nous-system"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--pipe", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "nous_research_pipe.py"))
    a = ap.parse_args()

    if not os.path.isfile(a.pipe):
        print(f"Pipe não encontrado: {a.pipe}")
        return

    content = open(a.pipe, encoding="utf-8").read()

    db = resolve_db(a.data_dir)
    if not db or not os.path.isfile(db):
        print("webui.db ainda não existe. Registrarei no próximo boot.")
        return

    cx = sqlite3.connect(db, timeout=15)
    try:
        if not table_exists(cx, "function"):
            print("Tabela 'function' ainda não criada. Tentarei no próximo boot.")
            return

        now = int(time.time())
        meta = json.dumps({"description": DESC, "manifest": {}})
        creator = pick_creator(cx)

        # Só ativa se o SearXNG estiver no ar — auto-cura quando o container subir.
        active = 1 if searxng_available() else 0

        row = cx.execute("SELECT user_id FROM function WHERE id=?", (FUNC_ID,)).fetchone()

        if row:
            user_id = row[0]
            if (user_id in (None, "", "nous-system")) and creator != "nous-system":
                user_id = creator
            cx.execute(
                """UPDATE function
                   SET name=?, type='pipe', content=?, meta=?,
                       is_active=?, is_global=0, user_id=?, updated_at=?
                   WHERE id=?""",
                (FUNC_NAME, content, meta, active, user_id, now, FUNC_ID),
            )
            action = "atualizado"
        else:
            cx.execute(
                """INSERT INTO function
                   (id, user_id, name, type, content, meta, valves,
                    is_active, is_global, updated_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (FUNC_ID, creator, FUNC_NAME, "pipe", content, meta, None,
                 active, 0, now, now),
            )
            action = "instalado"

        cx.commit()
        estado = "ativo" if active else "inativo (SearXNG não está rodando)"
        print(f"Pipe '{FUNC_NAME}' {action} — {estado} (id='{FUNC_ID}').")
    finally:
        cx.close()


if __name__ == "__main__":
    main()
