# -*- coding: utf-8 -*-
"""
Instala/atualiza o filtro 'Nous Agenda' DIRETO no banco do Open WebUI (Filter
global e ativo). Mesmo padrao do register_utilidades.py: idempotente, sem
login, e respeita o filtro desligado pelo usuario no painel de admin.

USO:
    python agenda/register_agenda.py [--data-dir <DATA_DIR>]
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

FUNC_ID, FUNC_NAME = "nous_agenda", "Nous Agenda"
DESC = ("Agenda pelo chat: lembretes, notas e compromissos ditos em portugues "
        "('me lembre de...', 'o que tenho amanha?'). Grava no servico local 8996.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()
    db = resolve_db(a.data_dir)
    if not db or not os.path.isfile(db):
        print("webui.db ainda nao existe. A agenda sera registrada na proxima inicializacao.")
        return
    cx = sqlite3.connect(db, timeout=15)
    try:
        if not table_exists(cx, "function"):
            print("Tabela 'function' ainda nao criada pelo servidor. Tentarei no proximo boot.")
            return
        content = open(os.path.join(HERE, "nous_agenda.py"), encoding="utf-8").read()
        action = upsert(cx, FUNC_ID, FUNC_NAME, content, DESC, pick_creator(cx), int(time.time()))
        cx.commit()
        print(f"{FUNC_NAME} {action} (id='{FUNC_ID}').")
    finally:
        cx.close()


if __name__ == "__main__":
    main()
