"""Pasta de modelos no layout do Ollama: manifestos, cabecalho GGUF e capacidades.

Le' so' o que precisa para o nous-motor responder /api/tags e /api/show e subir o
llama-server com o arquivo certo. Nunca escreve nada na pasta.
"""
import dataclasses
import hashlib
import json
import os
import struct

REGISTRY = "registry.ollama.ai"
ARQ_EMBEDDING = {"bert", "nomic-bert", "nomic-bert-moe", "xlm-roberta", "jina-bert-v2", "jina-bert-v3", "gte",
                 "modern-bert", "neo-bert", "t5encoder"}
_TAM = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_FMT = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}


def pasta_modelos():
    """OLLAMA_MODELS; senao ~/.ollama/models se existir; senao DATA_DIR/modelos."""
    if os.environ.get("OLLAMA_MODELS"):
        return os.environ["OLLAMA_MODELS"]
    casa = os.environ.get("USERPROFILE") or os.environ.get("HOME") or os.path.expanduser("~")
    ollama = os.path.join(casa, ".ollama", "models")
    if os.path.isdir(ollama):
        return ollama
    dados = os.environ.get("DATA_DIR") or os.environ.get("NOUS_DATA_DIR") or os.path.join(casa, "NousData")
    return os.path.join(dados, "modelos")


def ler_gguf(caminho):
    """Le' so' o cabecalho chave-valor do GGUF (v2/v3); arrays sao pulados sem carregar."""
    info = {}
    with open(caminho, "rb") as f:
        if f.read(4) != b"GGUF":
            raise ValueError("nao e' um arquivo GGUF: " + caminho)
        versao, = struct.unpack("<I", f.read(4))
        if versao < 2:
            raise ValueError("GGUF v1 nao suportado")
        _, n = struct.unpack("<QQ", f.read(16))

        def texto():
            t, = struct.unpack("<Q", f.read(8))
            return f.read(t).decode("utf-8", "replace")

        def pular_array():
            tipo, qtd = struct.unpack("<IQ", f.read(12))
            if tipo == 8:
                for _ in range(qtd):
                    t, = struct.unpack("<Q", f.read(8))
                    f.seek(t, 1)
            elif tipo == 9:
                for _ in range(qtd):
                    pular_array()
            else:
                f.seek(_TAM[tipo] * qtd, 1)

        for _ in range(n):
            chave = texto()
            tipo, = struct.unpack("<I", f.read(4))
            if tipo == 8:
                info[chave] = texto()
            elif tipo == 9:
                pular_array()
            elif tipo in _FMT:
                info[chave] = struct.unpack("<" + _FMT[tipo], f.read(_TAM[tipo]))[0]
            else:
                raise ValueError("tipo GGUF desconhecido %d em %s" % (tipo, chave))
    arq = info.get("general.architecture", "")
    template = info.pop("tokenizer.chat_template", "")
    return {
        "arquitetura": arq,
        "contexto": int(info.get(arq + ".context_length") or 0),
        "template": template,
        "parametros": int(info.get("general.parameter_count") or 0),
        "embedding": arq in ARQ_EMBEDDING or (arq + ".pooling_type") in info,
        "info": info,
    }


@dataclasses.dataclass
class Modelo:
    nome: str
    blob: str
    tamanho: int
    digest: str
    familia: str
    tamanho_param: str
    quantizacao: str
    params: dict
    projetor: "str | None"
    template_ollama: str
    gguf: dict
    modificado: float = 0.0
    manifesto: str = ""


def normalizar_nome(nome):
    """'registry.ollama.ai/library/Qwen3' -> 'qwen3:latest'; 'fulano/x' -> 'fulano/x:latest'."""
    n = (nome or "").strip().lower()
    for prefixo in (REGISTRY + "/", "library/"):
        if n.startswith(prefixo):
            n = n[len(prefixo):]
    if n.startswith("library/"):
        n = n[len("library/"):]
    ultimo = n.rsplit("/", 1)[-1]
    if ":" not in ultimo:
        n += ":latest"
    return n


def _nome_do_caminho(host, ns, modelo, tag):
    base = modelo if (host == REGISTRY and ns == "library") else (ns + "/" + modelo if host == REGISTRY else host + "/" + ns + "/" + modelo)
    return (base + ":" + tag).lower()


def _blob_caminho(pasta, digest):
    return os.path.join(pasta, "blobs", digest.replace(":", "-"))


def _ler_texto(pasta, digest):
    with open(_blob_caminho(pasta, digest), encoding="utf-8") as f:
        return f.read()


def _carregar(pasta, caminho_man, nome):
    with open(caminho_man, "rb") as f:
        bruto = f.read()
    man = json.loads(bruto)
    camadas = {}
    for c in man.get("layers", []):
        camadas.setdefault(c.get("mediaType", "").rsplit(".", 1)[-1], c)
    if "model" not in camadas:
        return None
    blob = _blob_caminho(pasta, camadas["model"]["digest"])
    if not os.path.isfile(blob):
        return None
    cfg = {}
    if man.get("config", {}).get("digest"):
        try:
            cfg = json.loads(_ler_texto(pasta, man["config"]["digest"]))
        except (OSError, ValueError):
            cfg = {}
    params = {}
    if "params" in camadas:
        try:
            params = json.loads(_ler_texto(pasta, camadas["params"]["digest"]))
        except (OSError, ValueError):
            params = {}
    template = ""
    if "template" in camadas:
        try:
            template = _ler_texto(pasta, camadas["template"]["digest"])
        except OSError:
            template = ""
    projetor = None
    if "projector" in camadas:
        p = _blob_caminho(pasta, camadas["projector"]["digest"])
        projetor = p if os.path.isfile(p) else None
    gguf = ler_gguf(blob)
    return Modelo(
        nome=nome, blob=blob, tamanho=sum(int(c.get("size", 0)) for c in man.get("layers", [])),
        digest=hashlib.sha256(bruto).hexdigest(),
        familia=cfg.get("model_family") or gguf["arquitetura"], tamanho_param=cfg.get("model_type", ""),
        quantizacao=cfg.get("file_type", ""), params=params, projetor=projetor, template_ollama=template,
        gguf=gguf, modificado=os.path.getmtime(caminho_man), manifesto=caminho_man)


def _manifestos(pasta):
    raiz = os.path.join(pasta, "manifests")
    if not os.path.isdir(raiz):
        return
    for host in sorted(os.listdir(raiz)):
        for ns in sorted(_dirs(os.path.join(raiz, host))):
            for modelo in sorted(_dirs(os.path.join(raiz, host, ns))):
                d = os.path.join(raiz, host, ns, modelo)
                for tag in sorted(os.listdir(d)):
                    c = os.path.join(d, tag)
                    if os.path.isfile(c):
                        yield _nome_do_caminho(host, ns, modelo, tag), c


def _dirs(p):
    try:
        return [x for x in os.listdir(p) if os.path.isdir(os.path.join(p, x))]
    except OSError:
        return []


def listar(pasta):
    saida = []
    for nome, c in _manifestos(pasta):
        try:
            m = _carregar(pasta, c, nome)
        except (OSError, ValueError, KeyError, struct.error):
            m = None
        if m:
            saida.append(m)
    return sorted(saida, key=lambda m: m.nome)


def caminho_manifesto(pasta, nome):
    """Onde fica (ou ficaria) o manifesto de um nome."""
    n = normalizar_nome(nome)
    base, _, tag = n.rpartition(":")
    partes = base.split("/")
    if len(partes) == 1:
        host, ns, modelo = REGISTRY, "library", partes[0]
    elif len(partes) == 2:
        host, ns, modelo = REGISTRY, partes[0], partes[1]
    else:
        host, ns, modelo = partes[0], "/".join(partes[1:-1]), partes[-1]
    return os.path.join(pasta, "manifests", host, ns, modelo, tag)


def achar(pasta, nome):
    n = normalizar_nome(nome)
    c = caminho_manifesto(pasta, n)
    if not os.path.isfile(c):
        return None
    try:
        return _carregar(pasta, c, n)
    except (OSError, ValueError, KeyError, struct.error):
        return None


def capacidades(m):
    if m.gguf.get("embedding"):
        return ["embedding"]
    caps = ["completion"]
    t = (m.template_ollama or "") + "\n" + (m.gguf.get("template") or "")
    if ".Tools" in t or "tools" in t:
        caps.append("tools")
    if ".Thinking" in t or "<think>" in t or "enable_thinking" in t or "reasoning_content" in t:
        caps.append("thinking")
    if m.projetor:
        caps.append("vision")
    return caps
