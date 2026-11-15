"""Coisas de mentira para os testes do motor: GGUF sintetico e pasta de modelos no layout do Ollama."""
import hashlib
import json
import os
import struct
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
MOTOR = os.path.dirname(AQUI)
if MOTOR not in sys.path:
    sys.path.insert(0, MOTOR)


def _str(s):
    b = s.encode("utf-8")
    return struct.pack("<Q", len(b)) + b


def _valor(v):
    if isinstance(v, bool):
        return struct.pack("<I", 7) + struct.pack("<?", v)
    if isinstance(v, int):
        return struct.pack("<I", 4) + struct.pack("<I", v) if 0 <= v < 2 ** 32 else struct.pack("<I", 10) + struct.pack("<Q", v)
    if isinstance(v, float):
        return struct.pack("<I", 6) + struct.pack("<f", v)
    if isinstance(v, str):
        return struct.pack("<I", 8) + _str(v)
    if isinstance(v, list):
        if v and isinstance(v[0], str):
            return struct.pack("<I", 9) + struct.pack("<IQ", 8, len(v)) + b"".join(_str(x) for x in v)
        return struct.pack("<I", 9) + struct.pack("<IQ", 5, len(v)) + b"".join(struct.pack("<i", x) for x in v)
    raise TypeError(type(v))


def escrever_gguf(caminho, chaves, versao=3, resto=b"\0" * 64):
    """Grava um GGUF so' com cabecalho (sem tensores) e as chaves dadas."""
    corpo = b"GGUF" + struct.pack("<IQQ", versao, 0, len(chaves))
    for k, v in chaves.items():
        corpo += _str(k) + _valor(v)
    with open(caminho, "wb") as f:
        f.write(corpo + resto)
    return caminho


def _blob(pasta, dados):
    dig = "sha256:" + hashlib.sha256(dados).hexdigest()
    with open(os.path.join(pasta, "blobs", dig.replace(":", "-")), "wb") as f:
        f.write(dados)
    return dig, len(dados)


GGUF_QWEN = {"general.architecture": "qwen3", "general.parameter_count": 4022468096, "qwen3.context_length": 262144,
             "qwen3.block_count": 36, "tokenizer.ggml.tokens": ["a", "b", "c"],
             "tokenizer.chat_template": "{%- if tools %}...{%- endif %}<|im_start|>assistant\n<think>\n"}
GGUF_EMB = {"general.architecture": "bert", "bert.context_length": 512, "bert.pooling_type": 2}
TEMPLATE_QWEN = "{{- if .Tools }}<tools>{{ end }}{{ if .Thinking }}<think>{{ .Thinking }}</think>{{ end }}"
PARAMS_QWEN = {"temperature": 0.6, "top_k": 20, "top_p": 0.95, "stop": ["<|im_start|>", "<|im_end|>"]}


def pasta_falsa(tmp, modelos=None):
    """Monta tmp/manifests/registry.ollama.ai/<ns>/<nome>/<tag> e tmp/blobs.

    modelos: {"qwen3:4b": {"gguf": {...}, "config": {...}, "params": {...}, "template": "...", "projetor": True}}
    Sem modelos: qwen3:4b e granite-embedding:278m.
    """
    if modelos is None:
        modelos = {
            "qwen3:4b": {"gguf": GGUF_QWEN, "params": PARAMS_QWEN, "template": TEMPLATE_QWEN,
                         "config": {"model_family": "qwen3", "model_type": "4.0B", "file_type": "Q4_K_M"}},
            "granite-embedding:278m": {"gguf": GGUF_EMB,
                                       "config": {"model_family": "bert", "model_type": "278M", "file_type": "F16"}},
        }
    os.makedirs(os.path.join(tmp, "blobs"), exist_ok=True)
    for nome, m in modelos.items():
        base, _, tag = nome.partition(":")
        tag = tag or "latest"
        partes = base.split("/")
        ns = partes[0] if len(partes) == 2 else "library"
        modelo = partes[-1]
        caminho_gguf = os.path.join(tmp, "tmp.gguf")
        escrever_gguf(caminho_gguf, m.get("gguf", GGUF_QWEN))
        with open(caminho_gguf, "rb") as f:
            dados = f.read()
        os.remove(caminho_gguf)
        camadas = []
        dig, tam = _blob(tmp, dados)
        camadas.append({"mediaType": "application/vnd.ollama.image.model", "digest": dig, "size": tam})
        if m.get("template"):
            dig, tam = _blob(tmp, m["template"].encode("utf-8"))
            camadas.append({"mediaType": "application/vnd.ollama.image.template", "digest": dig, "size": tam})
        if m.get("params"):
            dig, tam = _blob(tmp, json.dumps(m["params"]).encode("utf-8"))
            camadas.append({"mediaType": "application/vnd.ollama.image.params", "digest": dig, "size": tam})
        if m.get("projetor"):
            dig, tam = _blob(tmp, b"projetor-" + nome.encode())
            camadas.append({"mediaType": "application/vnd.ollama.image.projector", "digest": dig, "size": tam})
        cfg = dict(m.get("config", {}))
        cfg.setdefault("model_format", "gguf")
        cdig, ctam = _blob(tmp, json.dumps(cfg).encode("utf-8"))
        man = {"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
               "config": {"mediaType": "application/vnd.docker.container.image.v1+json", "digest": cdig, "size": ctam},
               "layers": camadas}
        pasta_man = os.path.join(tmp, "manifests", "registry.ollama.ai", ns, modelo)
        os.makedirs(pasta_man, exist_ok=True)
        with open(os.path.join(pasta_man, tag), "w", encoding="utf-8") as f:
            json.dump(man, f)
    return tmp
