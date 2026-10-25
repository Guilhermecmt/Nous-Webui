# -*- coding: utf-8 -*-
"""
Nous - Portao do celular ("Usar no celular"). Existe so' enquanto o usuario deixa
ligado; quem liga e desliga e' o monitor (controle.py), pelo painel "Seu Nous".

Escuta na rede de casa (porta 8999) e repassa para o Nous, que continua so' em
127.0.0.1:
  /...                    -> o Open WebUI (127.0.0.1:8080): HTTP, streaming e WebSocket
  /_nous/<porta>/...      -> os servicos do Nous (8990, 8993, 8995, 8996, 8997), pela
                             MESMA origem do celular. O Nous Code (8998) fica de fora:
                             ele roda comandos no computador.

Regras, nesta ordem, para TODA conexao:
  1. IP de origem tem que ser da rede de casa (privado/link-local/ULA); senao, 403.
  2. O cabecalho Host tem que ser o IP do PC (ou o nome dele): barra DNS rebinding.
  3. Pedido que muda coisa (POST etc.) e WebSocket: o Origin tem que ser este mesmo
     endereco (CSRF). O cookie e' SameSite=Strict, uma segunda trava.
  4. Sem o cookie de aparelho pareado, so' a pagina de pareamento responde.

Rotas do proprio portao (prefixo /_portao/, nunca repassado):
  GET  /_portao/parear   pagina que explica e troca o codigo (o QR aponta para ca')
  POST /_portao/trocar   {codigo} -> Set-Cookie do aparelho (uso unico, com freio)
  GET  /_portao/saude    so' para o proprio computador (o monitor confere)

Uso: python nous_celular.py --data-dir <NousData> [--porta 8999]
Sem dependencia nova: aiohttp ja' vem no venv do Open WebUI.
"""
import argparse
import asyncio
import json
import logging
import logging.handlers
import os
import posixpath
import socket
import sys
import time
import urllib.parse

import aiohttp
import yarl
from aiohttp import WSMsgType, web

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import pareamento as par  # noqa: E402

PORTA = 8999
OWUI = 8080
# so' o que o Nous usa pelo navegador. O 8998 (Nous Code) NAO entra: tem terminal.
SERVICOS = (8990, 8993, 8995, 8996, 8997)
UPSTREAM_ORIGEM = "http://127.0.0.1:%d" % OWUI
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "host", "proxy-connection"}
SEGURO = {"GET", "HEAD", "OPTIONS"}

log = logging.getLogger("nous-celular")


# ------------------------------------------------------------------ paginas
PAGINA_PAREAR = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><title>Nous - ligar este celular</title>
<style>
:root{color-scheme:dark light;--fundo:#141210;--card:#1c1916;--txt:#ddd5c6;--mut:#958a76;--ouro:#c8962e;--ouro2:#e7c069;--erro:#e58b7a}
@media (prefers-color-scheme:light){:root{--fundo:#faf6ee;--card:#fff;--txt:#2a251e;--mut:#7a6f5d;--ouro:#a87a1c;--ouro2:#8a6414;--erro:#b3402c}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--fundo);color:var(--txt);
font:16px/1.55 Inter,system-ui,sans-serif;padding:16px}
main{width:100%;max-width:420px;background:var(--card);border:1px solid rgba(200,150,46,.3);border-radius:16px;padding:22px 20px}
h1{margin:0 0 4px;font:600 22px Cinzel,Georgia,serif;letter-spacing:.06em;color:var(--ouro2)}
p{margin:.6em 0}ol{padding-left:1.2em;margin:.6em 0}li{margin:.35em 0}.mut{color:var(--mut);font-size:14px}
input{width:100%;font:600 22px ui-monospace,Consolas,monospace;letter-spacing:.18em;text-transform:uppercase;text-align:center;
padding:12px;border-radius:12px;border:1px solid var(--ouro);background:transparent;color:var(--txt)}
button{width:100%;margin-top:12px;padding:13px;border-radius:12px;border:0;background:var(--ouro);color:#fff;font:600 16px system-ui,sans-serif;cursor:pointer}
button:disabled{opacity:.5}#msg{min-height:1.4em;margin-top:10px;color:var(--erro);font-size:14px}
</style></head><body><main>
<h1>Nous</h1>
<p><b>Este celular ainda n&atilde;o est&aacute; ligado ao seu Nous.</b></p>
<ol><li>No computador, abra o Nous.</li><li>No painel <b>Seu Nous</b>, toque em <b>Usar no celular</b>.</li>
<li>Leia o QR com a c&acirc;mera deste celular, ou digite o c&oacute;digo aqui:</li></ol>
<form id="f" autocomplete="off"><input id="c" inputmode="text" maxlength="12" autocapitalize="characters" spellcheck="false"
placeholder="XXXX-XXXX" aria-label="C&oacute;digo do computador"><button id="b" type="submit">Ligar este celular</button></form>
<div id="msg" role="alert"></div>
<p class="mut">O c&oacute;digo vale uma vez s&oacute; e vence em poucos minutos. Quem entra por aqui usa o seu Nous inteiro:
conversas, documentos, agenda e e-mail.</p></main>
<script>
(function(){
var c=document.getElementById('c'),b=document.getElementById('b'),m=document.getElementById('msg'),f=document.getElementById('f');
var h=(location.hash||'').replace(/^#/,'');
if(h){c.value=decodeURIComponent(h).slice(0,12);history.replaceState(null,'',location.pathname);}
function enviar(){
 var v=c.value.trim(); if(!v)return; b.disabled=true; m.textContent='';
 fetch('/_portao/trocar',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Nous-Portao':'1'},body:JSON.stringify({codigo:v})})
 .then(function(r){return r.json().then(function(j){return[r.status,j];});})
 .then(function(x){ if(x[0]===200){m.style.color='inherit';m.textContent='Pronto! Abrindo o Nous...';location.replace('/');}
   else{m.textContent=x[1].erro||'Nao deu certo.';b.disabled=false;} })
 .catch(function(){m.textContent='Sem conexao com o computador.';b.disabled=false;});
}
f.addEventListener('submit',function(e){e.preventDefault();enviar();});
if(h)enviar();
})();
</script></body></html>"""

PAGINA_ERRO = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nous</title><style>body{font:16px/1.55 system-ui,sans-serif;margin:0;display:grid;place-items:center;min-height:100vh;padding:16px;
background:#141210;color:#ddd5c6}main{max-width:420px}h1{font:600 20px Georgia,serif;color:#e7c069}</style></head><body><main>
<h1>%(titulo)s</h1><p>%(texto)s</p></main></body></html>"""


def _erro_html(status, titulo, texto):
    return web.Response(status=status, content_type="text/html", charset="utf-8",
                        text=PAGINA_ERRO % {"titulo": titulo, "texto": texto},
                        headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ quem e' o cliente
def ip_do_cliente(request):
    app = request.app
    if app["teste"]:                       # so' com --modo-teste: injeta o IP de origem
        falso = request.headers.get("X-Teste-Ip")
        if falso:
            return falso
    peer = request.transport.get_extra_info("peername") if request.transport else None
    return peer[0] if peer else ""


def _origem_ok(request):
    """O Origin (se vier) tem que ser o proprio endereco do portao."""
    o = request.headers.get("Origin")
    if o is None:
        # navegadores sempre mandam Origin em POST e WebSocket; sem ele so' passa se o
        # proprio navegador garantir que e' o mesmo site
        return request.headers.get("Sec-Fetch-Site") in ("same-origin", "none")
    try:
        u = urllib.parse.urlparse(o)
    except ValueError:
        return False
    return u.scheme == "http" and u.netloc.lower() == (request.host or "").lower()


def _limpa(request, nome):
    """Os cookies da requisicao sem o do portao (o Open WebUI nao precisa saber dele)."""
    c = request.headers.get("Cookie", "")
    partes = [p for p in (x.strip() for x in c.split(";")) if p and not p.startswith(nome + "=")]
    return "; ".join(partes)


# ------------------------------------------------------------------ middlewares
@web.middleware
async def seguranca_mw(request, handler):
    app = request.app
    ip = ip_do_cliente(request)
    request["ip"] = ip
    loopback_saude = request.path == "/_portao/saude" and ip in ("127.0.0.1", "::1")
    if not loopback_saude:
        if not par.ip_permitido(ip):
            log.warning("recusado (IP fora da rede de casa): %s", ip)
            return web.Response(status=403, text="Acesso negado.", headers={"Cache-Control": "no-store"})
        if not par.host_permitido(request.host, app["nomes"]):
            log.warning("recusado (Host invalido %r) de %s", request.host, ip)
            return web.Response(status=403, text="Acesso negado.", headers={"Cache-Control": "no-store"})
    ws = request.headers.get("Upgrade", "").lower() == "websocket"
    if (request.method not in SEGURO or ws) and not loopback_saude and not _origem_ok(request):
        log.warning("recusado (Origin %r) de %s", request.headers.get("Origin"), ip)
        return web.json_response({"erro": "Origem nao permitida."}, status=403)
    resp = await handler(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    return resp


def _autenticado(request):
    return par.aparelho_do_cookie(request.app["data_dir"], request.cookies.get(par.COOKIE))


@web.middleware
async def entrada_mw(request, handler):
    if request.path.startswith("/_portao/"):
        return await handler(request)
    achou = _autenticado(request)
    if not achou:
        quer_html = "text/html" in request.headers.get("Accept", "") and request.method == "GET"
        if quer_html:
            return web.Response(status=401, content_type="text/html", charset="utf-8", text=PAGINA_PAREAR,
                                headers={"Cache-Control": "no-store"})
        return web.json_response({"erro": "Aparelho nao pareado."}, status=401, headers={"Cache-Control": "no-store"})
    d, caminho = achou
    par.marcar_uso(caminho, d, request["ip"])
    return await handler(request)


# ------------------------------------------------------------------ rotas do portao
async def h_parear(request):
    return web.Response(status=200, content_type="text/html", charset="utf-8", text=PAGINA_PAREAR,
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


async def h_saude(request):
    return web.json_response({"ok": True, "portao": "nous-celular"})


async def h_nada(request):
    raise web.HTTPNotFound()


async def h_trocar(request):
    app = request.app
    ip = request["ip"]
    espera = app["freio"].bloqueado(ip)
    if espera:
        return web.json_response({"erro": "Muitas tentativas. Espere %d minuto(s) e tente de novo." % max(1, (espera + 59) // 60)},
                                 status=429, headers={"Retry-After": str(espera)})
    if request.headers.get("X-Nous-Portao") != "1" or "json" not in request.content_type:
        return web.json_response({"erro": "Pedido invalido."}, status=400)
    try:
        corpo = await request.json()
    except Exception:
        corpo = {}
    cod = corpo.get("codigo") if isinstance(corpo, dict) else None
    cookie = par.trocar_codigo(app["data_dir"], str(cod or "")[:32], request.headers.get("User-Agent", ""), ip)
    if not cookie:
        queimou = app["freio"].falhou(ip)
        log.warning("codigo recusado de %s", ip)
        if queimou:
            par.queimar_codigo(app["data_dir"])
            log.warning("muitas tentativas erradas: codigo queimado")
        return web.json_response({"erro": "Codigo errado ou vencido. Gere um novo no computador."}, status=400)
    app["freio"].acertou(ip)
    log.info("aparelho pareado: %s (%s)", cookie.split(".")[0], ip)
    resp = web.json_response({"ok": True})
    resp.set_cookie(par.COOKIE, cookie, max_age=par.COOKIE_VALIDADE, path="/", httponly=True, samesite="Strict")
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ------------------------------------------------------------------ repasse
def _cabecalhos_ida(request, porta, servico):
    h = {}
    for k, v in request.headers.items():
        kl = k.lower()
        if kl in HOP or kl in ("cookie", "content-length", "x-teste-ip", "x-forwarded-for", "x-forwarded-host", "x-real-ip",
                               "forwarded", "x-nous-portao"):
            continue
        h[k] = v
    cl = request.headers.get("Content-Length")
    if cl is not None:
        h["Content-Length"] = cl
    h["Host"] = "127.0.0.1:%d" % porta
    if "Origin" in request.headers:
        # o servidor so' aceita "o proprio Nous" como origem; aqui a origem ja' foi conferida
        if servico:
            h.pop("Origin", None)
        else:
            h["Origin"] = UPSTREAM_ORIGEM
    if "Referer" in request.headers:
        h["Referer"] = UPSTREAM_ORIGEM + urllib.parse.urlparse(request.headers["Referer"]).path
    if not servico:
        c = _limpa(request, par.COOKIE)
        if c:
            h["Cookie"] = c
    if servico:
        h["X-Nous-Portao"] = "1"           # o monitor recusa /celular/* vindo daqui
    return h


def _relativo(valor):
    """Location absoluto do servidor de tras vira relativo (fica na origem do celular)."""
    for base in (UPSTREAM_ORIGEM, "http://localhost:%d" % OWUI):
        if valor.startswith(base):
            return valor[len(base):] or "/"
    return valor


async def repassar(request, porta, caminho_qs, servico):
    sess = request.app["sess"]
    url = yarl.URL("http://127.0.0.1:%d%s" % (porta, caminho_qs), encoded=True)
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await repassar_ws(request, porta, url, servico)
    corpo = request.content if request.can_read_body else None
    resp = None
    try:
        async with sess.request(request.method, url, headers=_cabecalhos_ida(request, porta, servico), data=corpo,
                                allow_redirects=False) as up:
            resp = web.StreamResponse(status=up.status, reason=up.reason)
            for k, v in up.headers.items():
                kl = k.lower()
                if kl in HOP:
                    continue
                if kl == "location":
                    v = _relativo(v)
                resp.headers.add(k, v)
            resp.headers["Cache-Control"] = resp.headers.get("Cache-Control", "no-store")
            await resp.prepare(request)
            async for pedaco in up.content.iter_any():
                await resp.write(pedaco)
            await resp.write_eof()
            return resp
    except (aiohttp.ClientConnectorError, asyncio.TimeoutError):
        if resp is not None and resp.prepared:
            return resp
        return _erro_html(502, "O Nous nao esta respondendo",
                          "O Nous parece estar fechado no computador. Abra o Nous la e atualize esta pagina.")
    except (ConnectionResetError, aiohttp.ClientError) as e:
        log.info("repasse interrompido: %s", e)
        if resp is not None and resp.prepared:
            return resp
        raise web.HTTPBadGateway()


async def repassar_ws(request, porta, url, servico):
    sess = request.app["sess"]
    pedidos = [p.strip() for p in request.headers.get("Sec-WebSocket-Protocol", "").split(",") if p.strip()]
    h = {k: v for k, v in _cabecalhos_ida(request, porta, servico).items()
         if k.lower() in ("origin", "cookie", "user-agent", "authorization", "accept-language")}
    try:
        up = await sess.ws_connect(url, headers=h, protocols=pedidos, max_msg_size=0, heartbeat=None, autoping=True)
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return web.Response(status=502, text="Sem resposta do Nous.")
    cli = web.WebSocketResponse(max_msg_size=0, protocols=[up.protocol] if up.protocol else (), autoping=True)
    await cli.prepare(request)

    async def para_servidor():
        async for m in cli:
            if m.type == WSMsgType.TEXT:
                await up.send_str(m.data)
            elif m.type == WSMsgType.BINARY:
                await up.send_bytes(m.data)
            else:
                break

    async def para_cliente():
        async for m in up:
            if m.type == WSMsgType.TEXT:
                await cli.send_str(m.data)
            elif m.type == WSMsgType.BINARY:
                await cli.send_bytes(m.data)
            else:
                break

    tarefas = [asyncio.ensure_future(para_servidor()), asyncio.ensure_future(para_cliente())]
    try:
        await asyncio.wait(tarefas, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tarefas:
            t.cancel()
        await up.close()
        await cli.close()
    return cli


async def h_servico(request):
    try:
        porta = int(request.match_info["porta"])
    except ValueError:
        raise web.HTTPNotFound()
    if porta not in SERVICOS:
        return web.json_response({"erro": "Este servico nao esta disponivel pelo celular."}, status=404)
    # O controle do celular (ligar, QR, aparelhos) so' vale no computador. Confere o
    # caminho ja' decodificado e normalizado (//celular, /./celular, %63elular...).
    limpo = "/" + posixpath.normpath("/" + urllib.parse.unquote(request.match_info.get("resto", "").split("?", 1)[0])).lstrip("/")
    if porta == 8990 and limpo.lower().startswith("/celular"):
        return web.json_response({"erro": "Isto so' funciona no computador."}, status=403)
    raw = request.raw_path
    inicio = raw.index("/_nous/%d" % porta) + len("/_nous/%d" % porta)
    return await repassar(request, porta, raw[inicio:] or "/", True)


async def h_owui(request):
    return await repassar(request, OWUI, request.raw_path, False)


# ------------------------------------------------------------------ aplicacao
def nomes_do_pc():
    n = socket.gethostname().lower()
    return {n, n.split(".")[0]}


def build_app(data_dir, teste=False):
    app = web.Application(middlewares=[seguranca_mw, entrada_mw], client_max_size=0)
    app["data_dir"] = str(data_dir)
    app["teste"] = teste
    app["freio"] = par.Freio()
    app["nomes"] = nomes_do_pc()

    async def abre(a):
        a["sess"] = aiohttp.ClientSession(auto_decompress=False, timeout=aiohttp.ClientTimeout(total=None, sock_connect=5),
                                          cookie_jar=aiohttp.DummyCookieJar(), connector=aiohttp.TCPConnector(limit=0))

    async def fecha(a):
        await a["sess"].close()

    app.on_startup.append(abre)
    app.on_cleanup.append(fecha)
    app.add_routes([
        web.get("/_portao/parear", h_parear),
        web.get("/_portao/saude", h_saude),
        web.post("/_portao/trocar", h_trocar),
        web.route("*", "/_portao/{x:.*}", h_nada),
        web.route("*", "/_nous/{porta}", h_servico),
        web.route("*", "/_nous/{porta}/{resto:.*}", h_servico),
        web.route("*", "/{tail:.*}", h_owui),
    ])
    return app


def _estado(data_dir, porta, ip=None):
    caminho = os.path.join(par.pasta(data_dir), "estado.json")
    par._escrever(caminho, {"pid": os.getpid(), "porta": porta, "iniciado": time.time(), "ip": ip})
    return caminho


async def servir(args):
    app = build_app(args.data_dir, args.modo_teste)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    hosts = [args.host] if args.host else ["0.0.0.0", "::"]
    ouvindo = []
    for h in hosts:
        try:
            await web.TCPSite(runner, h, args.porta).start()
            ouvindo.append(h)
        except OSError as e:
            log.warning("nao consegui escutar em %s:%s (%s)", h, args.porta, e)
    if not ouvindo:
        raise SystemExit("nao consegui abrir a porta %s" % args.porta)
    caminho = _estado(args.data_dir, args.porta)
    log.info("portao ligado em %s porta %s%s", ouvindo, args.porta, " (MODO TESTE)" if args.modo_teste else "")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        try:
            os.remove(caminho)
        except OSError:
            pass
        await runner.cleanup()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.environ.get("DATA_DIR") or os.path.join(os.path.expanduser("~"), "NousData"))
    ap.add_argument("--porta", type=int, default=int(os.environ.get("NOUS_CELULAR_PORT", PORTA)))
    ap.add_argument("--host", default=None, help="so' para teste; sem isto escuta em 0.0.0.0 e ::")
    ap.add_argument("--modo-teste", action="store_true", help="so' para teste: aceita o IP de origem no cabecalho X-Teste-Ip")
    args = ap.parse_args()
    os.makedirs(par.pasta(args.data_dir), exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    arq = logging.handlers.RotatingFileHandler(os.path.join(par.pasta(args.data_dir), "portao.log"),
                                               maxBytes=200000, backupCount=1, encoding="utf-8")
    arq.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[arq])
    try:
        asyncio.run(servir(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
