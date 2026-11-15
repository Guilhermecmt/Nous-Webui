# -*- coding: utf-8 -*-
"""
Aponta o Open WebUI para o nous-motor (127.0.0.1:8989) em vez do Ollama (11434).

Desde a 0.10 o Open WebUI guarda no banco (tabela config) as URLs que viu no
primeiro inicio e depois ignora o OLLAMA_BASE_URL do ambiente. Por isso, a cada
inicio, este script troca as URLs LOCAIS do Ollama/motor pela URL pedida:
  ollama.base_urls     (conversa, lista de modelos, Loja)
  rag.ollama.base_url  (embeddings dos documentos)
Servidores de outra maquina que o usuario cadastrou ficam como estao. So' grava
se mudou (nao mexe no updated_at a toa).

USO:
    python ajustes/register_motor.py [--data-dir <DATA_DIR>] [--url http://127.0.0.1:8989]
    (--url http://127.0.0.1:11434 volta tudo para o Ollama direto)
"""
import argparse
import os
import sqlite3
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config_db import obter, definir, tem_config  # noqa: E402

MOTOR_URL = "http://127.0.0.1:8989"
_LOCAIS = {"127.0.0.1", "localhost", "0.0.0.0", "::1", "[::1]"}
_PORTAS = {11434, 8989}


def local(url):
    try:
        u = urlparse(str(url))
        return (u.hostname or "") in _LOCAIS and (u.port or 0) in _PORTAS
    except ValueError:
        return False


def novas_urls(atuais, alvo):
    saida = []
    for u in (atuais if isinstance(atuais, list) else []):
        u = alvo if local(u) else u
        if u not in saida:
            saida.append(u)
    if alvo not in saida:
        saida.insert(0, alvo)
    return saida


def aplicar(cx, alvo):
    mudou = {}
    urls = obter(cx, "ollama.base_urls")
    nova = novas_urls(urls, alvo)
    if nova != urls:
        mudou["ollama.base_urls"] = nova
    rag = obter(cx, "rag.ollama.base_url")
    if rag in (None, "") or local(rag):
        if rag != alvo:
            mudou["rag.ollama.base_url"] = alvo
    if mudou:
        definir(cx, mudou)
    return mudou


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--url", default=MOTOR_URL)
    a = ap.parse_args()
    d = a.data_dir or os.environ.get("DATA_DIR") or os.environ.get("NOUS_DATA_DIR")
    db = os.path.join(d, "webui.db") if d else None
    if not db or not os.path.isfile(db):
        print("[register_motor] sem webui.db ainda (o 1o inicio usa o OLLAMA_BASE_URL)")
        return
    cx = sqlite3.connect(db, timeout=15)
    try:
        if not cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'").fetchone() or not tem_config(cx):
            print("[register_motor] config ainda vazia")
            return
        mudou = aplicar(cx, a.url.rstrip("/"))
        cx.commit()
        print("[register_motor] " + (("trocado: " + ", ".join(mudou)) if mudou else "ja' aponta para " + a.url))
    finally:
        cx.close()


if __name__ == "__main__":
    main()
