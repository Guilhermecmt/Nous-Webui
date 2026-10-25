# -*- coding: utf-8 -*-
"""
Conta o que ha' no webui.db (so' leitura) e imprime um JSON: contas, conversas,
memorias, arquivos, bases de conhecimento e funcoes. O atualizador do Open WebUI
(installer/atualizar-openwebui.ps1) roda antes e depois da atualizacao: se alguma
contagem cair, desfaz a atualizacao.

USO:
    python tools/contar-dados.py <caminho do webui.db>
"""
import sys
import json
import sqlite3

TABELAS = ("user", "chat", "memory", "file", "knowledge", "function", "model")


def main():
    caminho = sys.argv[1].replace("\\", "/")
    cx = sqlite3.connect("file:%s?mode=ro" % caminho, uri=True, timeout=15)
    out = {}
    try:
        for t in TABELAS:
            try:
                out[t] = cx.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
            except sqlite3.Error:
                out[t] = 0
    finally:
        cx.close()
    print(json.dumps(out))


if __name__ == "__main__":
    main()
