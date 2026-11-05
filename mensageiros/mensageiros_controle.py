# -*- coding: utf-8 -*-
"""
Nous - Telegram e WhatsApp: o lado do computador (rotas /mensageiros/* do monitor, 8990).

  GET  /mensageiros/estado
  POST /mensageiros/telegram/conectar     {token, user_id}  confere o token e sobe
  POST /mensageiros/telegram/codigo       {user_id}         codigo de uso unico + link + QR
  POST /mensageiros/telegram/remover      {id}              tira uma pessoa
  POST /mensageiros/telegram/desconectar                    apaga o token e as pessoas
  POST /mensageiros/whatsapp/ligar        {user_id, aceito} exige o aceite do aviso
  POST /mensageiros/whatsapp/desligar                       desliga e apaga a sessao

O monitor ja' recusa pagina de fora (cors_mw). O celular fica de fora daqui: quem
abriu o Nous pelo portao nao pode ligar canal nem ler o token.
"""
import asyncio
import base64
import io
import os
import shutil
import socket
import subprocess
import sys
import time

import aiohttp
from aiohttp import web

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import ponte  # noqa: E402
import telegram  # noqa: E402
import whatsapp  # noqa: E402
import nous_mensageiros as servico  # noqa: E402

SEM_JANELA = 0x08000000
DESANEXADO = 0x00000008
NOVO_GRUPO = 0x00000200
_trava = None


def _lock():
    global _trava
    if _trava is None:
        _trava = asyncio.Lock()
    return _trava


def _responde():
    try:
        socket.create_connection(("127.0.0.1", servico.porta()), timeout=0.6).close()
        return True
    except OSError:
        return False


def _estado(dd):
    return ponte.ler_json(os.path.join(ponte.pasta(dd), "estado.json")) or {}


def _matar(pid):
    try:
        import psutil
        p = psutil.Process(int(pid))
        if "nous_mensageiros" not in " ".join(p.cmdline()):
            return
        for filho in p.children(recursive=True):
            filho.kill()
        p.terminate()
        p.wait(5)
    except Exception:  # noqa: BLE001
        pass


def tem_canal(dd):
    c = ponte.config(dd)
    return bool((c.get("telegram") or {}).get("token") or (c.get("whatsapp") or {}).get("ligado"))


def parar(dd):
    st = _estado(dd)
    if st.get("pid"):
        _matar(st["pid"])
    ponte.apagar(os.path.join(ponte.pasta(dd), "estado.json"))


def subir(dd):
    if _responde():
        return
    os.makedirs(ponte.pasta(dd), exist_ok=True)
    subprocess.Popen([sys.executable, os.path.join(_AQUI, "nous_mensageiros.py"), "--data-dir", str(dd)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=SEM_JANELA | NOVO_GRUPO | DESANEXADO, close_fds=True)


async def reiniciar(dd):
    """Le' a configuracao de novo. Sem canal ligado, nada fica rodando."""
    parar(dd)
    for _ in range(20):
        if not _responde():
            break
        await asyncio.sleep(0.25)
    if tem_canal(dd):
        subir(dd)
        for _ in range(40):
            if _responde():
                break
            await asyncio.sleep(0.25)


def qr_base64(texto):
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, border=2,
                      error_correction=qrcode.constants.ERROR_CORRECT_M)
    buf = io.BytesIO()
    img.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _estado_completo(dd):
    c = ponte.config(dd)
    st = _estado(dd) if _responde() else {}
    tg = c.get("telegram") or {}
    zap = c.get("whatsapp") or {}
    qr = None
    if st.get("qr"):
        try:
            qr = qr_base64(st["qr"])
        except Exception:  # noqa: BLE001
            qr = None
    return {
        "agora": time.time(),
        "telegram": {"conectado": bool(tg.get("token")), "bot": tg.get("bot") or "", "estado": st.get("telegram"),
                     "pessoas": ponte.listar_donos(dd, telegram.CANAL), "codigo_expira": ponte.codigo_vigente(dd, telegram.CANAL)},
        "whatsapp": {"ligado": bool(zap.get("ligado")), "estado": st.get("whatsapp"), "qr": qr,
                     "pareado": whatsapp.pareado(dd), "tem_node": bool(whatsapp.achar_node())},
    }


def add_routes(app, data_dir_fn):
    def dd():
        return str(data_dir_fn())

    def so_computador(fn):
        async def h(request):
            if request.headers.get("X-Nous-Portao"):
                return web.json_response({"erro": "Isto so' funciona no computador."}, status=403)
            return await fn(request)
        return h

    async def corpo(request):
        try:
            b = await request.json()
            return b if isinstance(b, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def erro(texto, status=400):
        return web.json_response({"erro": texto}, status=status)

    async def h_estado(request):
        return web.json_response(_estado_completo(dd()))

    async def h_tg_conectar(request):
        b = await corpo(request)
        token = str(b.get("token") or "").strip()
        if ":" not in token or len(token) < 30:
            return erro("Isso não parece um token do BotFather. Ele tem um número, dois-pontos e uma sequência longa.")
        try:
            bot = await telegram.validar(token)
        except telegram.TokenInvalido:
            return erro("O Telegram não aceitou esse token. Copie de novo a mensagem do BotFather.")
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            return erro("Não consegui falar com o Telegram. Veja se o computador está com internet.", 502)
        d = dd()
        async with _lock():
            c = ponte.config(d)
            # token de outro bot: quem estava pareado era do bot antigo
            if (c.get("telegram") or {}).get("token") != token:
                ponte.remover_donos(d, telegram.CANAL)
            c["telegram"] = {"token": token, "bot": bot}
            ponte.salvar_config(d, c)
            await reiniciar(d)
        return web.json_response(_estado_completo(d))

    async def h_tg_codigo(request):
        b = await corpo(request)
        d = dd()
        bot = (ponte.config(d).get("telegram") or {}).get("bot")
        uid = str(b.get("user_id") or "")
        if not bot or not uid:
            return erro("Conecte o bot primeiro.", 409)
        cod, expira = ponte.novo_codigo(d, telegram.CANAL, uid)
        link = "https://t.me/%s?start=%s" % (bot, cod)
        try:
            qr = qr_base64(link)
        except Exception:  # noqa: BLE001
            qr = None
        return web.json_response({"link": link, "qr": qr, "expira": expira, "agora": time.time()})

    async def h_tg_remover(request):
        b = await corpo(request)
        d = dd()
        return web.json_response({"ok": ponte.remover_dono(d, b.get("id")), "pessoas": ponte.listar_donos(d, telegram.CANAL)})

    async def h_tg_desconectar(request):
        d = dd()
        async with _lock():
            c = ponte.config(d)
            c.pop("telegram", None)
            ponte.salvar_config(d, c)
            ponte.remover_donos(d, telegram.CANAL)
            ponte.apagar(os.path.join(ponte.pasta(d), "codigo_telegram.json"))
            await reiniciar(d)
        return web.json_response(_estado_completo(d))

    async def h_wa_ligar(request):
        b = await corpo(request)
        uid = str(b.get("user_id") or "")
        if b.get("aceito") is not True:
            return erro("Leia e aceite o aviso antes de ligar.", 409)
        if not uid:
            return erro("Não encontrei a sua conta do Nous.", 409)
        if not whatsapp.achar_node():
            return erro("O WhatsApp precisa do Node.js, que vem com o Nous Code. Instale o Nous Code e tente de novo.", 409)
        d = dd()
        async with _lock():
            c = ponte.config(d)
            c["whatsapp"] = {"ligado": True, "user_id": uid}
            ponte.salvar_config(d, c)
            await reiniciar(d)
        return web.json_response(_estado_completo(d))

    async def h_wa_desligar(request):
        d = dd()
        async with _lock():
            c = ponte.config(d)
            c.pop("whatsapp", None)
            ponte.salvar_config(d, c)
            await reiniciar(d)
            shutil.rmtree(os.path.dirname(whatsapp.sessao(d)), ignore_errors=True)
        return web.json_response(_estado_completo(d))

    app.add_routes([
        web.get("/mensageiros/estado", so_computador(h_estado)),
        web.post("/mensageiros/telegram/conectar", so_computador(h_tg_conectar)),
        web.post("/mensageiros/telegram/codigo", so_computador(h_tg_codigo)),
        web.post("/mensageiros/telegram/remover", so_computador(h_tg_remover)),
        web.post("/mensageiros/telegram/desconectar", so_computador(h_tg_desconectar)),
        web.post("/mensageiros/whatsapp/ligar", so_computador(h_wa_ligar)),
        web.post("/mensageiros/whatsapp/desligar", so_computador(h_wa_desligar)),
    ])

    async def ao_iniciar(_app):
        # o computador reiniciou: quem estava ligado volta sozinho
        try:
            if tem_canal(dd()):
                subir(dd())
        except Exception as e:  # noqa: BLE001
            print("[Nous][mensageiros] nao subiu: %s" % type(e).__name__, file=sys.stderr)

    app.on_startup.append(ao_iniciar)
