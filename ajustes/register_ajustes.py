# -*- coding: utf-8 -*-
"""
Ajustes do Nous sobre os padroes do Open WebUI 0.9.6, gravados na tabela config.

Cada ajuste roda UMA vez por instalacao (marcador em NousData/.ajustes_nous.json):
se o admin mudar depois pelo painel, o Nous nao desfaz. Ajuste novo = versao nova
na lista abaixo.

  1  ui.default_locale = pt-BR (so' se estiver vazio)
  1  rag.youtube_loader_language = pt, pt-BR, en (o padrao 'en' pegava a legenda
     em ingles do video)
  1  calendar.enable / automations.enable = False: o Nous tem a Agenda propria
     (lembretes com aviso do Windows, iCal, tarefas). Duas agendas confundem.
  1  Embeddings de documentos multilingues (paraphrase-multilingual-MiniLM-L12-v2)
     no lugar do all-MiniLM-L6-v2 (so' ingles), SO' se ainda nao ha nenhum
     arquivo/conhecimento indexado (trocar o modelo invalida os vetores antigos).

Os mesmos valores vao como variavel de ambiente no launcher, para instalacoes
novas (onde a tabela config ainda nao tem a chave).

USO:
    python ajustes/register_ajustes.py [--data-dir <DATA_DIR>]
"""
import os
import sys
import json
import argparse
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "evaluation"))
from register_arena import _resolve_db, _read_config, _write_config, _set_nested  # noqa: E402

MULTI_EMBED = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
OLD_EMBED = "sentence-transformers/all-MiniLM-L6-v2"


def _get(data, path, default=None):
    for k in path.split("."):
        if not isinstance(data, dict) or k not in data:
            return default
        data = data[k]
    return data


def _count(cx, table):
    try:
        return cx.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        return 0


def ajuste_1(cx, data, log):
    if not _get(data, "ui.default_locale"):
        _set_nested(data, "ui.default_locale", "pt-BR")
        log.append("idioma padrao pt-BR")
    if _get(data, "rag.youtube_loader_language") in (None, ["en"]):
        _set_nested(data, "rag.youtube_loader_language", ["pt", "pt-BR", "en"])
        log.append("legendas do YouTube em portugues")
    _set_nested(data, "calendar.enable", False)
    _set_nested(data, "automations.enable", False)
    log.append("calendario/automacoes nativos escondidos (o Nous usa a Agenda propria)")
    engine = _get(data, "rag.embedding_engine", "")
    model = _get(data, "rag.embedding_model", OLD_EMBED)
    if engine in ("", None) and model in (OLD_EMBED, None):
        if _count(cx, "file") == 0 and _count(cx, "knowledge") == 0:
            _set_nested(data, "rag.embedding_model", MULTI_EMBED)
            log.append("embeddings de documentos multilingues")
        else:
            log.append("embeddings mantidos (ja ha documentos indexados)")


AJUSTES = [(1, ajuste_1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()
    db = _resolve_db(a.data_dir)
    if not db or not os.path.isfile(db):
        print("webui.db ainda nao existe. Ajustes na proxima inicializacao.")
        return
    marker = os.path.join(os.path.dirname(db), ".ajustes_nous.json")
    try:
        done = json.load(open(marker, encoding="utf-8")).get("versao", 0)
    except Exception:
        done = 0
    pending = [(v, f) for v, f in AJUSTES if v > done]
    if not pending:
        return
    cx = sqlite3.connect(db, timeout=15)
    try:
        if not cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'").fetchone():
            print("Tabela 'config' ainda nao criada. Tentarei no proximo boot.")
            return
        data = _read_config(cx)
        log = []
        for _v, f in pending:
            f(cx, data, log)
        _write_config(cx, data)
        cx.commit()
    finally:
        cx.close()
    with open(marker, "w", encoding="utf-8") as fh:
        json.dump({"versao": pending[-1][0]}, fh)
    print("Ajustes do Nous: " + "; ".join(log) + ". Valem a partir do proximo inicio do Nous.")


if __name__ == "__main__":
    main()
