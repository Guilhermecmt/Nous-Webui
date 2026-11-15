"""Baixa um modelo pelo nous-motor (ou por qualquer servidor com a API do Ollama).

Uso: python motor/puxar.py <modelo> [--url http://127.0.0.1:8989] [--silencioso]
Sai com 0 quando o modelo esta' pronto; 1 com a mensagem de erro.
Substitui o "ollama pull" nos launchers e no instalador.
"""
import argparse
import json
import os
import sys

import requests


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("modelo")
    ap.add_argument("--url", default=os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:8989")
    ap.add_argument("--silencioso", action="store_true")
    a = ap.parse_args(argv)
    ultimo_pct = -1
    try:
        with requests.post(a.url.rstrip("/") + "/api/pull", json={"model": a.modelo, "stream": True},
                           stream=True, timeout=(10, 600)) as r:
            for linha in r.iter_lines():
                if not linha:
                    continue
                ev = json.loads(linha)
                if ev.get("error"):
                    print("erro: " + ev["error"], file=sys.stderr)
                    return 1
                if ev.get("status") == "success":
                    if not a.silencioso:
                        print("pronto: " + a.modelo)
                    return 0
                if not a.silencioso and ev.get("total"):
                    pct = int(100 * (ev.get("completed") or 0) / ev["total"])
                    if pct != ultimo_pct and pct % 5 == 0:
                        ultimo_pct = pct
                        print("%s %d%%" % (ev.get("status", ""), pct), flush=True)
    except (requests.RequestException, ValueError) as e:
        print("erro: nao consegui falar com %s: %s" % (a.url, e), file=sys.stderr)
        return 1
    print("erro: a conexao fechou antes do fim", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
