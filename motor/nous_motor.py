"""nous-motor: o pedaco da API do Ollama que o Nous usa, servido sem o Ollama.

Modo "llama": cada pedido vai para um llama-server (llama.cpp) que o proprio motor
sobe e derruba (processos.Gerente). Modo "ollama": repassa tudo para o Ollama.
So' escuta em 127.0.0.1. Desenho em docs/PLANO-MOTOR-PROPRIO.md.

Ambiente lido pelo main():
  DATA_DIR                 pasta de dados do Nous (PID, ajustes, lista de processos)
  NOUS_MOTOR               llama | ollama (senao DATA_DIR/motor/ajustes.json, senao pelo binario)
  NOUS_LLAMA_SERVER        caminho do llama-server.exe (senao <app>/motor/bin/llama-server.exe)
  NOUS_MOTOR_PORT          porta (8989)
  NOUS_OLLAMA_REAL         onde esta' o Ollama no modo repasse (http://127.0.0.1:11434)
  NOUS_MOTOR_MAX_MODELOS   modelos de conversa carregados ao mesmo tempo (2)
  OLLAMA_CONTEXT_LENGTH    contexto padrao (16384)
  OLLAMA_KEEP_ALIVE        tempo na memoria depois do ultimo pedido (5m)
  OLLAMA_MODELS            pasta de modelos (senao ~/.ollama/models, senao DATA_DIR/modelos)
"""
import asyncio
import json
import os
import subprocess
import sys

import aiohttp
from aiohttp import web

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

import registro  # noqa: E402
import traduz  # noqa: E402
from processos import ErroMotor, Gerente  # noqa: E402

VERSAO = "0.0.0-nous-motor"
NDJSON = "application/x-ndjson"
K_PASTA = web.AppKey("pasta", str)
K_GERENTE = web.AppKey("gerente", object)
K_MOTOR = web.AppKey("motor", str)
K_OLLAMA = web.AppKey("ollama", str)
K_SESSAO = web.AppKey("sessao", object)
K_PUXAR = web.AppKey("puxar", object)
K_FAXINA = web.AppKey("faxina", object)


class Recusa(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status


def erro(status, msg):
    return web.json_response({"error": msg}, status=status)


def escolher_motor(data_dir, binario):
    v = (os.environ.get("NOUS_MOTOR") or "").strip().lower()
    if v in ("llama", "ollama"):
        return v
    try:
        with open(os.path.join(data_dir, "motor", "ajustes.json"), encoding="utf-8") as f:
            v = str(json.load(f).get("motor", "")).lower()
        if v in ("llama", "ollama"):
            return v
    except (OSError, ValueError, AttributeError):
        pass
    return "llama" if os.path.isfile(binario) else "ollama"


# ---------------------------------------------------------------- detalhes
def _details(m):
    return {"parent_model": "", "format": "gguf", "family": m.familia, "families": [m.familia],
            "parameter_size": m.tamanho_param, "quantization_level": m.quantizacao}


def _iso(ts):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _parametros_texto(params):
    linhas = []
    for k, v in params.items():
        for x in (v if isinstance(v, list) else [v]):
            linhas.append("%-30s %s" % (k, json.dumps(x) if isinstance(x, str) else x))
    return "\n".join(linhas)


async def _corpo(req):
    try:
        c = await req.json()
    except (ValueError, UnicodeDecodeError):
        raise Recusa(400, "corpo do pedido nao e' JSON valido")
    if not isinstance(c, dict):
        raise Recusa(400, "corpo do pedido nao e' um objeto JSON")
    return c


def _modelo(req, corpo):
    nome = corpo.get("model") or corpo.get("name") or ""
    m = registro.achar(req.app[K_PASTA], nome) if nome else None
    if not m:
        raise Recusa(404, "modelo '%s' nao encontrado; baixe na Loja do Nous" % nome)
    return m


def _ctx(corpo):
    n = (corpo.get("options") or {}).get("num_ctx")
    return int(n) if isinstance(n, (int, float)) and n > 0 else None


# ------------------------------------------------------------- rotas simples
async def raiz(req):
    return web.Response(text="Ollama is running")


async def versao(req):
    return web.json_response({"version": VERSAO})


async def saude(req):
    return web.json_response({"ok": True, "motor": req.app[K_MOTOR]})


async def tags(req):
    pasta = req.app[K_PASTA]
    lista = await asyncio.get_running_loop().run_in_executor(None, registro.listar, pasta)
    return web.json_response({"models": [{"name": m.nome, "model": m.nome, "modified_at": _iso(m.modificado),
                                          "size": m.tamanho, "digest": m.digest, "details": _details(m)} for m in lista]})


async def show(req):
    corpo = await _corpo(req)
    m = _modelo(req, corpo)
    info = dict(m.gguf.get("info") or {})
    info.setdefault("general.architecture", m.gguf.get("arquitetura"))
    return web.json_response({
        "license": "", "modelfile": "", "parameters": _parametros_texto(m.params), "template": m.template_ollama,
        "details": _details(m), "model_info": info, "capabilities": registro.capacidades(m),
        "modified_at": _iso(m.modificado)})


async def ps(req):
    return web.json_response({"models": req.app[K_GERENTE].ativos()})


async def nao_suportado(req):
    return erro(501, "o motor do Nous nao faz %s; use o Ollama (modo ollama) para isso" % req.path)


# ------------------------------------------------------------ conversa
async def _sse(resp):
    """Le' o stream SSE do llama-server e devolve cada evento JSON."""
    async for linha in resp.content:
        t = linha.decode("utf-8", "replace").strip()
        if not t.startswith("data:"):
            continue
        t = t[5:].strip()
        if t == "[DONE]":
            return
        try:
            yield json.loads(t)
        except ValueError:
            continue


async def _erro_upstream(resp):
    try:
        j = await resp.json(content_type=None)
        e = j.get("error")
        msg = e.get("message") if isinstance(e, dict) else e
    except (ValueError, aiohttp.ClientError):
        msg = None
    return msg or ("llama-server respondeu %d" % resp.status)


def _resp_curta(m, tipo, motivo):
    l = {"model": m.nome, "created_at": traduz.agora_iso()}
    if tipo == "chat":
        l["message"] = {"role": "assistant", "content": ""}
    else:
        l["response"] = ""
    l.update({"done": True, "done_reason": motivo})
    return l


async def _responder(req, corpo, unico):
    stream = corpo.get("stream", True) is not False
    if stream:
        r = web.StreamResponse(headers={"Content-Type": NDJSON})
        await r.prepare(req)
        await r.write((json.dumps(unico) + "\n").encode())
        await r.write_eof()
        return r
    return web.json_response(unico)


async def _conversar(req, tipo):
    corpo = await _corpo(req)
    m = _modelo(req, corpo)
    g = req.app[K_GERENTE]
    vazio = (not corpo.get("messages")) if tipo == "chat" else (not corpo.get("prompt") and not corpo.get("images"))
    keep = corpo.get("keep_alive")
    if vazio:
        if traduz.keep_alive_segundos(keep, g.keep_padrao) == 0:
            await g.soltar(m.nome)
            return await _responder(req, corpo, _resp_curta(m, tipo, "unload"))
        async with g.usando(m, _ctx(corpo), keep):
            pass
        return await _responder(req, corpo, _resp_curta(m, tipo, "load"))
    if m.gguf.get("embedding"):
        raise Recusa(400, "o modelo %s so' gera embeddings, nao conversa" % m.nome)
    try:
        pedido = traduz.pedido_chat(corpo, m) if tipo == "chat" else traduz.pedido_generate(corpo, m)
    except ValueError as e:
        raise Recusa(400, str(e))
    junta = traduz.Juntador(m.nome, tipo, mostrar_pensamento=corpo.get("think") is not False)
    stream = corpo.get("stream", True) is not False
    sessao = req.app[K_SESSAO]
    async with g.usando(m, _ctx(corpo), keep) as url:
        async with sessao.post(url + "/v1/chat/completions", json=pedido) as up:
            if up.status != 200:
                raise Recusa(up.status if 400 <= up.status < 600 else 500, await _erro_upstream(up))
            if not stream:
                async for ev in _sse(up):
                    junta.pedaco(ev)
                return web.json_response(junta.inteiro())
            r = web.StreamResponse(headers={"Content-Type": NDJSON})
            await r.prepare(req)
            try:
                async for ev in _sse(up):
                    for l in junta.pedaco(ev):
                        await r.write((json.dumps(l, ensure_ascii=False) + "\n").encode())
                await r.write((json.dumps(junta.fim(), ensure_ascii=False) + "\n").encode())
            except (ConnectionResetError, aiohttp.ClientConnectionResetError):
                up.close()  # o cliente desistiu (Parar): fecha o llama-server, a placa para de gerar
                return r
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                await r.write((json.dumps({"error": "o llama-server parou no meio: %s" % e}) + "\n").encode())
            return r


async def chat(req):
    return await _conversar(req, "chat")


async def generate(req):
    return await _conversar(req, "generate")


async def _embeddings(req, corpo, entradas):
    m = _modelo(req, corpo)
    if not m.gguf.get("embedding"):
        raise Recusa(400, "o modelo %s nao gera embedding; use um modelo de embedding" % m.nome)
    g = req.app[K_GERENTE]
    async with g.usando(m, _ctx(corpo), corpo.get("keep_alive")) as url:
        async with req.app[K_SESSAO].post(url + "/v1/embeddings", json={"input": entradas, "model": m.nome}) as up:
            if up.status != 200:
                raise Recusa(up.status if 400 <= up.status < 600 else 500, await _erro_upstream(up))
            return m, await up.json()


async def embed(req):
    corpo = await _corpo(req)
    ent = corpo.get("input")
    ent = [ent] if isinstance(ent, str) else list(ent or [])
    m, dados = await _embeddings(req, corpo, ent)
    return web.json_response(traduz.resposta_embed(dados, m.nome))


async def embeddings(req):
    corpo = await _corpo(req)
    _, dados = await _embeddings(req, corpo, [corpo.get("prompt") or ""])
    return web.json_response(traduz.resposta_embeddings(dados))


# ------------------------------------------------------------ baixar/apagar
async def pull(req):
    corpo = await _corpo(req)
    puxar = req.app.get(K_PUXAR)
    if not puxar:
        return erro(501, "baixar modelos ainda nao esta' ligado no motor")
    nome = corpo.get("model") or corpo.get("name") or ""
    stream = corpo.get("stream", True) is not False
    if not stream:
        ultimo = {}
        async for ev in puxar.puxar(req.app[K_PASTA], nome):
            ultimo = ev
        return web.json_response(ultimo, status=500 if "error" in ultimo else 200)
    r = web.StreamResponse(headers={"Content-Type": NDJSON})
    await r.prepare(req)
    try:
        async for ev in puxar.puxar(req.app[K_PASTA], nome):
            await r.write((json.dumps(ev) + "\n").encode())
    except (ConnectionResetError, aiohttp.ClientConnectionResetError):
        pass
    return r


async def delete(req):
    corpo = await _corpo(req)
    puxar = req.app.get(K_PUXAR)
    if not puxar:
        return erro(501, "apagar modelos ainda nao esta' ligado no motor")
    nome = corpo.get("model") or corpo.get("name") or ""
    m = registro.achar(req.app[K_PASTA], nome)
    if m:
        await req.app[K_GERENTE].soltar(m.nome)
    if not puxar.apagar(req.app[K_PASTA], nome):
        return erro(404, "modelo '%s' nao encontrado" % nome)
    return web.Response(status=200)


# ------------------------------------------------------------ repasse
async def repassar(req):
    alvo = req.app[K_OLLAMA].rstrip("/") + req.path_qs
    corpo = await req.read()
    cab = {k: v for k, v in req.headers.items() if k.lower() in ("content-type", "accept", "authorization")}
    try:
        async with req.app[K_SESSAO].request(req.method, alvo, data=corpo or None, headers=cab) as up:
            r = web.StreamResponse(status=up.status, headers={"Content-Type": up.headers.get("Content-Type", "application/json")})
            await r.prepare(req)
            try:
                async for pedaco in up.content.iter_any():
                    await r.write(pedaco)
            except (ConnectionResetError, aiohttp.ClientConnectionResetError):
                up.close()
            return r
    except (aiohttp.ClientConnectorError, aiohttp.ServerDisconnectedError):
        return erro(502, "o Ollama nao respondeu em %s; ele esta' ligado?" % req.app[K_OLLAMA])


# ------------------------------------------------------------ app
@web.middleware
async def _erros(req, handler):
    try:
        return await handler(req)
    except Recusa as e:
        return erro(e.status, str(e))
    except ErroMotor as e:
        return erro(500, str(e))
    except web.HTTPException:
        raise
    except (ConnectionResetError, aiohttp.ClientConnectionResetError):
        raise
    except Exception as e:  # nunca deixa o cliente sem resposta
        return erro(500, "erro no motor: %s" % e)


async def _ao_subir(app):
    app[K_SESSAO] = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=10))
    g = app.get(K_GERENTE)
    if g is not None:
        async def faxina():
            while True:
                await asyncio.sleep(5)
                try:
                    await g.faxina()
                except Exception:
                    pass
        app[K_FAXINA] = asyncio.ensure_future(faxina())


async def _ao_parar(app):
    t = app.get(K_FAXINA)
    if t:
        t.cancel()
    g = app.get(K_GERENTE)
    if g is not None:
        await g.soltar_todos()
    await app[K_SESSAO].close()


def criar_app(motor, pasta, gerente, ollama_url, puxar=None):
    app = web.Application(middlewares=[_erros], client_max_size=1024 ** 3)
    app[K_MOTOR] = motor
    app[K_PASTA] = pasta
    app[K_OLLAMA] = ollama_url
    if gerente is not None:
        app[K_GERENTE] = gerente
    if puxar is not None:
        app[K_PUXAR] = puxar
    app.on_startup.append(_ao_subir)
    app.on_cleanup.append(_ao_parar)
    app.router.add_get("/health", saude)
    if motor == "ollama":
        app.router.add_route("*", "/{caminho:.*}", repassar)
        return app
    app.router.add_get("/", raiz)
    app.router.add_get("/api/version", versao)
    app.router.add_get("/api/tags", tags)
    app.router.add_post("/api/show", show)
    app.router.add_get("/api/ps", ps)
    app.router.add_post("/api/chat", chat)
    app.router.add_post("/api/generate", generate)
    app.router.add_post("/api/embed", embed)
    app.router.add_post("/api/embeddings", embeddings)
    app.router.add_post("/api/pull", pull)
    app.router.add_delete("/api/delete", delete)
    for rota in ("/api/create", "/api/copy", "/api/push"):
        app.router.add_post(rota, nao_suportado)
    return app


# ------------------------------------------------------------ main
def _matar_orfaos(arquivo):
    """Derruba llama-server que sobraram de um motor que morreu sem limpar."""
    try:
        with open(arquivo, encoding="utf-8") as f:
            pids = [int(p) for p in json.load(f)]
    except (OSError, ValueError, TypeError):
        return
    for pid in pids:
        try:
            out = subprocess.run(["tasklist", "/FI", "PID eq %d" % pid, "/FO", "CSV", "/NH"], capture_output=True,
                                 text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
            if "llama-server" in out.lower():
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            pass


def main():
    casa = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    data_dir = os.environ.get("DATA_DIR") or os.environ.get("NOUS_DATA_DIR") or os.path.join(casa, "NousData")
    binario = os.environ.get("NOUS_LLAMA_SERVER") or os.path.join(AQUI, "bin", "llama-server.exe")
    porta = int(os.environ.get("NOUS_MOTOR_PORT") or 8989)
    motor = escolher_motor(data_dir, binario)
    pasta_motor = os.path.join(data_dir, "motor")
    os.makedirs(pasta_motor, exist_ok=True)
    arquivo_pids = os.path.join(pasta_motor, "llama-pids.json")
    gerente = None
    puxar = None
    if motor == "llama":
        _matar_orfaos(arquivo_pids)
        gerente = Gerente(binario, max_modelos=int(os.environ.get("NOUS_MOTOR_MAX_MODELOS") or 2),
                          ctx_padrao=int(os.environ.get("OLLAMA_CONTEXT_LENGTH") or 16384),
                          keep_padrao=os.environ.get("OLLAMA_KEEP_ALIVE") or "5m", arquivo_pids=arquivo_pids)
        try:
            import baixar as puxar  # noqa: F811
        except ImportError:
            puxar = None
    app = criar_app(motor, registro.pasta_modelos(), gerente,
                    os.environ.get("NOUS_OLLAMA_REAL") or "http://127.0.0.1:11434", puxar)
    with open(os.path.join(pasta_motor, "motor.pid"), "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    print("nous-motor: modo %s em http://127.0.0.1:%d (modelos em %s)" % (motor, porta, registro.pasta_modelos()), flush=True)
    web.run_app(app, host="127.0.0.1", port=porta, print=None, access_log=None)


if __name__ == "__main__":
    main()
