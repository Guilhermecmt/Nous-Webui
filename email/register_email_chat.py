# -*- coding: utf-8 -*-
"""
Instala/atualiza o filtro 'Nous Email' (e-mail pelo chat, sempre como rascunho)
DIRETO no banco do Open WebUI. Mesmo padrao do register_agenda.py.

USO:
    python email/register_email_chat.py [--data-dir <DATA_DIR>]
"""
import os
import sys
import time
import argparse
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "history"))
sys.path.insert(0, os.path.join(HERE, "..", "utilidades"))
from register_history import resolve_db, table_exists, pick_creator  # noqa: E402
from register_utilidades import upsert  # noqa: E402

FUNC_ID, FUNC_NAME = "nous_email_chat", "Nous Email"
DESC = ("E-mail pelo chat: 'manda um e-mail pra Maria...' vira rascunho para aprovar; "
        "'o que chegou de importante?' le a caixa de entrada.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()
    db = resolve_db(a.data_dir)
    if not db or not os.path.isfile(db):
        print("webui.db ainda nao existe. O e-mail pelo chat sera registrado na proxima inicializacao.")
        return
    cx = sqlite3.connect(db, timeout=15)
    try:
        if not table_exists(cx, "function"):
            print("Tabela 'function' ainda nao criada pelo servidor. Tentarei no proximo boot.")
            return
        content = open(os.path.join(HERE, "nous_email_chat.py"), encoding="utf-8").read()
        action = upsert(cx, FUNC_ID, FUNC_NAME, content, DESC, pick_creator(cx), int(time.time()))
        cx.commit()
        print(f"{FUNC_NAME} {action} (id='{FUNC_ID}').")
    finally:
        cx.close()


if __name__ == "__main__":
    main()
