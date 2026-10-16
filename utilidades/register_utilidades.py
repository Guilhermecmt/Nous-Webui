# -*- coding: utf-8 -*-
"""
Instala/atualiza os filtros de utilidades (YouTube e Clima) DIRETO no banco do
Open WebUI, como Filters GLOBAIS e ATIVOS. Mesmo padrao do register_history.py:
idempotente, sem login, o arquivo em disco e' a fonte da verdade.

Um filtro que o usuario DESLIGOU no painel de admin continua desligado: so' o
codigo e a descricao sao re-sincronizados num registro ja existente.

USO:
    python utilidades/register_utilidades.py [--data-dir <DATA_DIR>]
"""
import os
import sys
import time
import json
import argparse
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))

FILTERS = [
    ("nous_youtube", "Nous YouTube", "nous_youtube.py",
     "Le a legenda de links do YouTube colados no chat para o modelo resumir "
     "ou responder sobre o video."),
    ("nous_clima", "Nous Clima", "nous_clima.py",
     "Previsao do tempo no chat via Open-Meteo (gratuito, sem chave)."),
]

sys.path.insert(0, os.path.join(HERE, "..", "history"))
from register_history import resolve_db, table_exists, pick_creator  # noqa: E402


def upsert(cx, func_id, name, content, desc, creator, now):
    meta = json.dumps({"description": desc, "manifest": {}})
    row = cx.execute("SELECT user_id FROM function WHERE id=?", (func_id,)).fetchone()
    if row:
        user_id = row[0]
        if (user_id in (None, "", "nous-system")) and creator != "nous-system":
            user_id = creator
        cx.execute(
            """UPDATE function SET name=?, type='filter', content=?, meta=?,
                   user_id=?, updated_at=? WHERE id=?""",
            (name, content, meta, user_id, now, func_id))
        return "atualizado"
    cx.execute(
        """INSERT INTO function
           (id, user_id, name, type, content, meta, valves,
            is_active, is_global, updated_at, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (func_id, creator, name, "filter", content, meta, None, 1, 1, now, now))
    return "instalado"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()

    db = resolve_db(a.data_dir)
    if not db or not os.path.isfile(db):
        print("webui.db ainda nao existe. As utilidades serao registradas na proxima inicializacao.")
        return
    cx = sqlite3.connect(db, timeout=15)
    try:
        if not table_exists(cx, "function"):
            print("Tabela 'function' ainda nao criada pelo servidor. Tentarei no proximo boot.")
            return
        now, creator = int(time.time()), pick_creator(cx)
        for func_id, name, fname, desc in FILTERS:
            path = os.path.join(HERE, fname)
            if not os.path.isfile(path):
                continue
            content = open(path, encoding="utf-8").read()
            print(f"{name} {upsert(cx, func_id, name, content, desc, creator, now)} (id='{func_id}').")
        cx.commit()
    finally:
        cx.close()


if __name__ == "__main__":
    main()
