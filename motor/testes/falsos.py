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


# ---------------------------------------------------------------------------
# llama-server de mentira (aiohttp no mesmo loop do teste) e a fabrica de processos
# ---------------------------------------------------------------------------
import asyncio

from aiohttp import web

AMOSTRAS = os.path.join(AQUI, "amostras")


def ler_amostra(nome):
    with open(os.path.join(AMOSTRAS, nome), encoding="utf-8") as f:
        return json.load(f)


class LlamaFalso:
    """Responde /health, /v1/chat/completions (reproduz uma amostra em SSE) e /v1/embeddings."""

    def __init__(self, amostra="chat_stream.json", health_503=0, atraso_por_token=0.0):
        self.amostra = amostra
        self.health_503 = health_503
        self.atraso = atraso_por_token
        self.pedidos = []
        self.fechou_antes_do_fim = False
        self.terminou_stream = False
        self._runner = None

    def _app(self):
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_post("/v1/chat/completions", self._chat)
        app.router.add_post("/v1/embeddings", self._emb)
        return app

    async def subir(self, porta):
        self._runner = web.AppRunner(self._app())
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", porta).start()

    async def parar(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _health(self, req):
        if self.health_503 > 0:
            self.health_503 -= 1
            return web.json_response({"error": {"code": 503, "message": "Loading model"}}, status=503)
        return web.json_response({"status": "ok"})

    async def _chat(self, req):
        corpo = await req.json()
        self.pedidos.append(("/v1/chat/completions", corpo))
        eventos = ler_amostra(self.amostra)
        if not corpo.get("stream"):
            return web.json_response({"choices": [{"message": {"role": "assistant", "content": "oi"}, "finish_reason": "stop"}]})
        r = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await r.prepare(req)
        try:
            for e in eventos:
                await r.write(("data: " + json.dumps(e) + "\n\n").encode())
                if self.atraso:
                    await asyncio.sleep(self.atraso)
            await r.write(b"data: [DONE]\n\n")
            self.terminou_stream = True
        except (ConnectionResetError, asyncio.CancelledError):
            self.fechou_antes_do_fim = True
        return r

    async def _emb(self, req):
        corpo = await req.json()
        self.pedidos.append(("/v1/embeddings", corpo))
        ent = corpo.get("input")
        ent = [ent] if isinstance(ent, str) else ent
        return web.json_response({"object": "list", "usage": {"prompt_tokens": 3 * len(ent), "total_tokens": 3 * len(ent)},
                                  "data": [{"index": i, "embedding": [3.0, 4.0 + i]} for i in range(len(ent))]})


class ProcessoFalso:
    _pid = 50000

    def __init__(self, argv, servidor, morrer_ao_carregar=False):
        ProcessoFalso._pid += 1
        self.pid = ProcessoFalso._pid
        self.argv = argv
        self.servidor = servidor
        self.returncode = None
        self.stderr = asyncio.StreamReader()
        self.encerrado = False
        if morrer_ao_carregar:
            self.stderr.feed_data(b"carregando...\nggml_vulkan: Device memory allocation failed\n")
            self.stderr.feed_eof()
            asyncio.get_running_loop().call_later(0.2, self._morreu, 1)

    def _morreu(self, codigo):
        if self.returncode is None:
            self.returncode = codigo

    async def morrer(self):
        await self.servidor.parar()
        self.returncode = 1
        if not self.stderr.at_eof():
            self.stderr.feed_eof()

    def terminate(self):
        self.encerrado = True
        asyncio.ensure_future(self.morrer())

    kill = terminate

    async def wait(self):
        while self.returncode is None:
            await asyncio.sleep(0.01)
        return self.returncode


class FabricaFalsa:
    """Usada como Gerente(iniciar=FabricaFalsa()): sobe um LlamaFalso na porta do argv."""

    def __init__(self, **opcoes):
        self.opcoes = opcoes
        self.morrer_ao_carregar = False
        self.argvs = []
        self.processos = []

    async def __call__(self, argv):
        self.argvs.append(argv)
        srv = LlamaFalso(**self.opcoes)
        p = ProcessoFalso(argv, srv, self.morrer_ao_carregar)
        if not self.morrer_ao_carregar:
            await srv.subir(int(argv[argv.index("--port") + 1]))
        self.processos.append(p)
        return p


class OllamaFalso:
    """Ollama de mentira para o modo repasse: ecoa o pedido e manda um stream NDJSON."""

    def __init__(self):
        self.pedidos = []
        self._runner = None
        self.url = None

    async def subir(self):
        app = web.Application()
        app.router.add_route("*", "/{caminho:.*}", self._tudo)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        porta = site._server.sockets[0].getsockname()[1]
        self.url = "http://127.0.0.1:%d" % porta
        return self.url

    async def parar(self):
        if self._runner:
            await self._runner.cleanup()

    async def _tudo(self, req):
        corpo = await req.read()
        self.pedidos.append((req.method, req.path, corpo))
        if req.path == "/api/tags":
            return web.json_response({"models": [{"name": "do-ollama:1b"}]})
        if req.path in ("/api/chat", "/api/pull"):
            r = web.StreamResponse(headers={"Content-Type": "application/x-ndjson"})
            await r.prepare(req)
            for i in range(3):
                await r.write((json.dumps({"i": i, "done": i == 2}) + "\n").encode())
            return r
        return web.json_response({"erro": "rota falsa"}, status=404)


class RegistryFalso:
    """registry.ollama.ai de mentira: manifesto + blobs, com redirecionamento e Range."""

    def __init__(self, blobs=None, corromper=None):
        self.blobs = blobs or {}
        self.corromper = corromper or set()
        self.manifestos = {}
        self.gets = []
        self.ranges = []
        self._runner = None
        self.url = None

    def publicar(self, nome, tag, camadas, config=b'{"model_family":"x","model_type":"1B","file_type":"Q4_0"}'):
        def dig(b):
            return "sha256:" + hashlib.sha256(b).hexdigest()
        self.blobs[dig(config)] = config
        layers = []
        for tipo, dados in camadas:
            self.blobs[dig(dados)] = dados
            layers.append({"mediaType": "application/vnd.ollama.image." + tipo, "digest": dig(dados), "size": len(dados)})
        man = {"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
               "config": {"mediaType": "application/vnd.docker.container.image.v1+json", "digest": dig(config), "size": len(config)},
               "layers": layers}
        self.manifestos[(nome, tag)] = json.dumps(man).encode()
        return man

    async def subir(self):
        app = web.Application()
        app.router.add_get("/v2/{ns}/{modelo}/manifests/{tag}", self._man)
        app.router.add_get("/v2/{ns}/{modelo}/blobs/{dig}", self._redir)
        app.router.add_get("/cdn/{dig}", self._blob)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.url = "http://127.0.0.1:%d" % site._server.sockets[0].getsockname()[1]
        return self.url

    async def parar(self):
        if self._runner:
            await self._runner.cleanup()

    async def _man(self, req):
        m = req.match_info
        corpo = self.manifestos.get((m["ns"] + "/" + m["modelo"], m["tag"]))
        if corpo is None:
            return web.json_response({"errors": [{"code": "MANIFEST_UNKNOWN"}]}, status=404)
        return web.Response(body=corpo, content_type="application/vnd.docker.distribution.manifest.v2+json")

    async def _redir(self, req):
        raise web.HTTPTemporaryRedirect("/cdn/" + req.match_info["dig"])

    async def _blob(self, req):
        d = req.match_info["dig"]
        self.gets.append(d)
        dados = self.blobs[d]
        if d in self.corromper:
            dados = b"X" + dados[1:]
        rng = req.headers.get("Range")
        self.ranges.append(rng)
        if rng:
            ini = int(rng.split("=")[1].split("-")[0])
            return web.Response(body=dados[ini:], status=206)
        return web.Response(body=dados)
