"""Grava respostas reais do llama-server em motor/testes/amostras (roda a mao, nao entra no lint).

Uso: python gravar_amostras.py <llama-server.exe>
Sobe o llama-server com os blobs do qwen3:4b e do granite-embedding:278m da pasta do Ollama.
"""
import json
import os
import socket
import subprocess
import sys
import time

import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(AQUI, "amostras")
MODELOS = os.environ.get("OLLAMA_MODELS") or os.path.join(os.path.expanduser("~"), ".ollama", "models")


def blob(nome, tag):
    man = os.path.join(MODELOS, "manifests", "registry.ollama.ai", "library", nome, tag)
    with open(man, encoding="utf-8") as f:
        j = json.load(f)
    for camada in j["layers"]:
        if camada["mediaType"].endswith(".model"):
            return os.path.join(MODELOS, "blobs", camada["digest"].replace(":", "-"))
    raise SystemExit("sem camada de modelo em " + man)


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def subir(exe, caminho, ctx, extra=()):
    p = porta_livre()
    argv = [exe, "-m", caminho, "--host", "127.0.0.1", "--port", str(p), "-c", str(ctx), "-ngl", "999",
            "--jinja", "--reasoning-format", "deepseek", "-np", "1", "--no-webui", *extra]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{p}"
    for _ in range(240):
        try:
            r = requests.get(url + "/health", timeout=2)
            if r.status_code == 200:
                return proc, url, r.json()
        except requests.RequestException:
            pass
        if proc.poll() is not None:
            raise SystemExit("llama-server morreu: " + proc.stderr.read().decode("utf-8", "replace")[-2000:])
        time.sleep(0.5)
    raise SystemExit("llama-server nao ficou pronto")


def stream(url, corpo):
    linhas = []
    with requests.post(url + "/v1/chat/completions", json=corpo, stream=True, timeout=300) as r:
        r.raise_for_status()
        for linha in r.iter_lines():
            if not linha:
                continue
            t = linha.decode("utf-8")
            if t.startswith("data: "):
                t = t[6:]
                if t.strip() == "[DONE]":
                    break
                linhas.append(json.loads(t))
    return linhas


def gravar(nome, dados):
    with open(os.path.join(SAIDA, nome), "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    print("gravado", nome)


def main():
    exe = sys.argv[1]
    os.makedirs(SAIDA, exist_ok=True)
    base = {"model": "qwen3:4b", "stream": True, "stream_options": {"include_usage": True}}
    proc, url, saude = subir(exe, blob("qwen3", "4b"), 4096)
    try:
        gravar("health.json", saude)
        gravar("chat_stream.json", stream(url, {**base, "messages": [{"role": "user", "content": "Diga oi em uma palavra."}],
                                                "max_tokens": 3000}))
        gravar("chat_json_schema.json", stream(url, {**base, "messages": [{"role": "user", "content": "Responda ok verdadeiro."}],
                                                     "chat_template_kwargs": {"enable_thinking": False},
                                                     "response_format": {"type": "json_schema", "json_schema": {"name": "saida", "schema": {
                                                         "type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}}}}))
        ferramenta = {"type": "function", "function": {"name": "hora_atual", "description": "Devolve a hora atual",
                                                       "parameters": {"type": "object", "properties": {}}}}
        gravar("chat_tools.json", stream(url, {**base, "messages": [{"role": "user", "content": "que horas sao? use a ferramenta"}],
                                               "tools": [ferramenta], "max_tokens": 600}))
        t0 = time.time()
        sem = stream(url, {**base, "messages": [{"role": "user", "content": "Conte de 1 a 50 separado por virgulas."}],
                           "chat_template_kwargs": {"enable_thinking": False}, "max_tokens": 3000})
        gravar("chat_sem_pensar.json", sem)
        tim = next((x.get("timings") for x in reversed(sem) if x.get("timings")), None)
        print("timings:", json.dumps(tim), "parede", round(time.time() - t0, 2), "s")
        r = requests.post(url + "/v1/chat/completions", json={"model": "x", "messages": [{"role": "user", "content": "palavra " * 6000}],
                                                              "max_tokens": 5}, timeout=120)
        gravar("erro_ctx.json", {"status": r.status_code, "corpo": r.json()})
    finally:
        proc.terminate()
        proc.wait(10)
    proc, url, _ = subir(exe, blob("granite-embedding", "278m"), 512, ["--embeddings"])
    try:
        r = requests.post(url + "/v1/embeddings", json={"model": "x", "input": ["oi", "tudo bem"]}, timeout=60)
        gravar("embeddings.json", r.json())
    finally:
        proc.terminate()
        proc.wait(10)


if __name__ == "__main__":
    main()
