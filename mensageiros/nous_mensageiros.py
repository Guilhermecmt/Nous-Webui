# -*- coding: utf-8 -*-
"""
Nous - o processo que atende Telegram e WhatsApp. Quem sobe e derruba e' o monitor
(mensageiros_controle.py); nada roda enquanto a pessoa nao ligar um canal.

Escuta em 127.0.0.1:8988 so' para dizer que esta' vivo e impedir dois ao mesmo tempo
(dois processos lendo o mesmo bot dariam 409 sem parar) e para o stop-nous achar.

USO: python mensageiros/nous_mensageiros.py --data-dir <NousData>
"""
import argparse
import asyncio
import os
import sys
import time

from aiohttp import web

_AQUI = os.path.dirname(os.path.abspath(__file__))
if _AQUI not in sys.path:
    sys.path.insert(0, _AQUI)

import ponte  # noqa: E402
import telegram  # noqa: E402
import whatsapp  # noqa: E402

PORTA = 8988


def porta():
    return int(os.environ.get("NOUS_MENSAGEIROS_PORT", PORTA))


class Estado:
    def __init__(self, data_dir):
        self.dd = data_dir
        self.d = {"pid": os.getpid(), "telegram": None, "whatsapp": None, "qr": None}

    def gravar(self):
        self.d["atualizado"] = time.time()
        ponte.escrever_json(os.path.join(ponte.pasta(self.dd), "estado.json"), self.d)

    def telegram(self, estado):
        if self.d["telegram"] != estado:
            self.d["telegram"] = estado
            self.gravar()

    def whatsapp(self, estado, qr=None):
        if self.d["whatsapp"] != estado or self.d["qr"] != qr:
            self.d["whatsapp"], self.d["qr"] = estado, qr
            self.gravar()


async def servir(data_dir):
    async def h_saude(request):
        return web.json_response({"ok": True, "pid": os.getpid()})

    app = web.Application()
    app.add_routes([web.get("/saude", h_saude)])
    corredor = web.AppRunner(app, access_log=None)
    await corredor.setup()
    await web.TCPSite(corredor, "127.0.0.1", porta()).start()

    est = Estado(data_dir)
    est.gravar()
    c = ponte.config(data_dir)
    atendente = ponte.Atendente(data_dir)
    tarefas = []
    wa = None
    tg = c.get("telegram") or {}
    if tg.get("token"):
        tarefas.append(asyncio.create_task(telegram.Telegram(data_dir, tg["token"], atendente, est.telegram).rodar()))
    zap = c.get("whatsapp") or {}
    if zap.get("ligado") and zap.get("user_id"):
        wa = whatsapp.WhatsApp(data_dir, zap["user_id"], atendente, est.whatsapp)
        tarefas.append(asyncio.create_task(wa.rodar()))
    try:
        await asyncio.gather(*tarefas)
        # canal parou por um motivo que so' a pessoa resolve (QR expirou, deslogou):
        # o estado fica na tela e o processo aguarda ser reiniciado pelo monitor
        await asyncio.Event().wait()
    finally:
        if wa:
            wa.parar()


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--data-dir", required=True)
    args = a.parse_args()
    try:
        asyncio.run(servir(args.data_dir))
    except OSError as e:
        # porta ocupada = ja' tem um rodando
        print("[Nous][mensageiros] nao subiu: %s" % type(e).__name__, flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
