# -*- coding: utf-8 -*-
"""Telegram e WhatsApp sem rede: Telegram de mentira, Open WebUI de mentira, ponte de
mentira. Nenhum token real, nenhum modelo real."""
import asyncio
import json
import os
import sys
import tempfile
import time
import unittest

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ponte  # noqa: E402
import telegram  # noqa: E402
import mensageiros_controle as controle  # noqa: E402

TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"


def rodar(coro):
    return asyncio.run(coro)


class NousFalso:
    """Responde como o Open WebUI responderia: ecoa a ultima mensagem."""

    def __init__(self):
        self.pedidos = []
        self.sem_modelo = False
        self.falha = False

    async def responder(self, user_id, mensagens, canal):
        self.pedidos.append((user_id, list(mensagens)))
        if self.sem_modelo:
            raise ponte.SemModelo()
        if self.falha:
            raise RuntimeError("fora do ar")
        return "## Resposta\n**eco:** " + mensagens[-1]["content"]

    async def transcrever(self, user_id, dados, nome):
        return "texto do audio" if dados else ""


class Pareamento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dd = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_codigo_vale_uma_vez_e_morre_depois_de_erros(self):
        cod, _ = ponte.novo_codigo(self.dd, "telegram", "u1")
        self.assertEqual(len(cod), 8)
        self.assertIsNone(ponte.usar_codigo(self.dd, "telegram", "ERRADO12"))
        self.assertEqual(ponte.usar_codigo(self.dd, "telegram", cod.lower()), "u1")
        self.assertIsNone(ponte.usar_codigo(self.dd, "telegram", cod))
        cod, _ = ponte.novo_codigo(self.dd, "telegram", "u1")
        for _ in range(ponte.MAX_TENTATIVAS):
            ponte.usar_codigo(self.dd, "telegram", "X")
        self.assertIsNone(ponte.usar_codigo(self.dd, "telegram", cod))
        self.assertIsNone(ponte.codigo_vigente(self.dd, "telegram"))

    def test_donos_por_canal(self):
        ponte.adicionar_dono(self.dd, "telegram", 42, "Ana", "u1")
        ponte.adicionar_dono(self.dd, "whatsapp", "55@s.whatsapp.net", "", "u1")
        self.assertEqual(ponte.dono_de(self.dd, "telegram", 42)["user_id"], "u1")
        self.assertIsNone(ponte.dono_de(self.dd, "telegram", 43))
        self.assertEqual([d["nome"] for d in ponte.listar_donos(self.dd, "telegram")], ["Ana"])
        ponte.remover_donos(self.dd, "telegram")
        self.assertEqual(ponte.listar_donos(self.dd, "telegram"), [])
        self.assertEqual(len(ponte.listar_donos(self.dd, "whatsapp")), 1)

    def test_texto_para_celular_e_divisao(self):
        self.assertEqual(ponte.para_celular("<think>x</think>## Oi\n**forte** fim"), "Oi\nforte fim")
        partes = ponte.dividir("a" * 10 + "\n" + "b" * 10, 12)
        self.assertEqual(partes, ["a" * 10, "b" * 10])
        self.assertEqual(len(ponte.dividir("x" * 100, 30)), 4)


class Atendente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dd = self.tmp.name
        self.nous = NousFalso()
        self.at = ponte.Atendente(self.dd, self.nous)
        self.saidas = []

    def tearDown(self):
        self.tmp.cleanup()

    async def enviar(self, t):
        self.saidas.append(t)

    def test_historico_e_comando_novo(self):
        rodar(self.at.atender("telegram", 1, "u1", "oi", self.enviar))
        rodar(self.at.atender("telegram", 1, "u1", "de novo", self.enviar))
        self.assertEqual(self.saidas[-1], "Resposta\neco: de novo")
        self.assertEqual(len(self.nous.pedidos[-1][1]), 3)   # oi, eco, de novo
        rodar(self.at.atender("telegram", 1, "u1", "/novo", self.enviar))
        rodar(self.at.atender("telegram", 1, "u1", "zero", self.enviar))
        self.assertEqual(len(self.nous.pedidos[-1][1]), 1)
        # outra pessoa nao ve a conversa desta
        rodar(self.at.atender("telegram", 2, "u1", "outro", self.enviar))
        self.assertEqual(len(self.nous.pedidos[-1][1]), 1)

    def test_erros_viram_mensagem_amigavel(self):
        self.nous.sem_modelo = True
        rodar(self.at.atender("telegram", 1, "u1", "oi", self.enviar))
        self.assertEqual(self.saidas[-1], ponte.SEM_MODELO)
        self.nous.sem_modelo, self.nous.falha = False, True
        rodar(self.at.atender("telegram", 1, "u1", "oi", self.enviar))
        self.assertEqual(self.saidas[-1], ponte.SEM_RESPOSTA)
        self.assertEqual(ponte.historico(self.dd, "telegram", 1), [])

    def test_audio_mostra_o_que_entendeu(self):
        rodar(self.at.atender_audio("telegram", 1, "u1", b"ogg", "a.ogg", self.enviar))
        self.assertEqual(self.saidas, ["🎤 texto do audio", "Resposta\neco: texto do audio"])
        rodar(self.at.atender_audio("telegram", 1, "u1", b"", "a.ogg", self.enviar))
        self.assertEqual(self.saidas[-1], ponte.AUDIO_FALHOU)


class TelegramFalso:
    """A Bot API: guarda o que foi enviado e entrega os updates do roteiro."""

    def __init__(self):
        self.updates = []
        self.enviados = []
        self.acoes = 0
        self.status = 200

    async def h(self, request):
        metodo = request.match_info["metodo"]
        if request.match_info["token"] != TOKEN:
            return web.json_response({"ok": False}, status=401)
        if self.status != 200:
            return web.json_response({"ok": False}, status=self.status)
        corpo = await request.json()
        if metodo == "getMe":
            return web.json_response({"ok": True, "result": {"username": "nous_teste_bot"}})
        if metodo == "getUpdates":
            off = corpo.get("offset") or 0
            novos = [u for u in self.updates if u["update_id"] >= off]
            if not novos:
                await asyncio.sleep(0.2)
            return web.json_response({"ok": True, "result": novos})
        if metodo == "sendMessage":
            self.enviados.append((corpo["chat_id"], corpo["text"]))
            return web.json_response({"ok": True, "result": {}})
        if metodo == "sendChatAction":
            self.acoes += 1
            return web.json_response({"ok": True, "result": True})
        if metodo == "getFile":
            return web.json_response({"ok": True, "result": {"file_path": "voice/1.oga", "file_size": 10}})
        return web.json_response({"ok": False}, status=404)

    async def arquivo(self, request):
        return web.Response(body=b"ogg-de-mentira")

    def mensagem(self, chat, texto=None, voz=False, tipo="private", nome="Ana"):
        u = {"update_id": len(self.updates) + 1, "message": {"chat": {"id": chat, "type": tipo}, "from": {"first_name": nome}}}
        if texto is not None:
            u["message"]["text"] = texto
        if voz:
            u["message"]["voice"] = {"file_id": "f1"}
        self.updates.append(u)


class TelegramCanal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dd = self.tmp.name
        self.api = TelegramFalso()
        self.nous = NousFalso()

    def tearDown(self):
        self.tmp.cleanup()

    async def _com_servidor(self, corpo):
        app = web.Application()
        app.add_routes([web.post("/bot{token}/{metodo}", self.api.h), web.get("/file/bot{token}/{resto:.*}", self.api.arquivo)])
        srv = TestServer(app)
        await srv.start_server()
        os.environ["NOUS_TELEGRAM_API"] = "http://127.0.0.1:%d" % srv.port
        try:
            return await corpo()
        finally:
            await srv.close()

    async def _rodar_ate(self, canal, condicao, tempo=8):
        tarefa = asyncio.create_task(canal.rodar())
        fim = time.time() + tempo
        try:
            while time.time() < fim and not condicao():
                await asyncio.sleep(0.1)
        finally:
            tarefa.cancel()
            try:
                await tarefa
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    def test_validar(self):
        async def corpo():
            self.assertEqual(await telegram.validar(TOKEN), "nous_teste_bot")
            with self.assertRaises(telegram.TokenInvalido):
                await telegram.validar("1:errado")
        rodar(self._com_servidor(corpo))

    def test_estranho_e_silencio_e_pareado_conversa(self):
        estados = []

        async def corpo():
            canal = telegram.Telegram(self.dd, TOKEN, ponte.Atendente(self.dd, self.nous), estados.append)
            self.api.mensagem(7, "oi, quem é você?")                 # estranho
            self.api.mensagem(7, "/start CODIGOERRADO")               # codigo errado
            self.api.mensagem(99, "oi", tipo="group")                 # grupo
            cod, _ = ponte.novo_codigo(self.dd, "telegram", "u1")
            self.api.mensagem(7, "/start " + cod)                     # pareia
            self.api.mensagem(7, "qual a capital da Bahia?")
            self.api.mensagem(7, None, voz=True)
            await self._rodar_ate(canal, lambda: len(self.api.enviados) >= 4)
        rodar(self._com_servidor(corpo))
        chats = [c for c, _ in self.api.enviados]
        self.assertEqual(chats, [7, 7, 7, 7])
        self.assertIn("conectado ao seu Nous", self.api.enviados[0][1])
        self.assertEqual(self.api.enviados[1][1], "Resposta\neco: qual a capital da Bahia?")
        self.assertEqual(self.api.enviados[2][1], "🎤 texto do audio")
        self.assertEqual(ponte.dono_de(self.dd, "telegram", 7)["nome"], "Ana")
        self.assertIn("conectado", estados)
        self.assertGreater(self.api.acoes, 0)
        # a pergunta do estranho e do grupo nunca chegaram ao modelo
        self.assertFalse(any("quem é você" in str(p) or p[1][-1]["content"] == "oi" for p in self.nous.pedidos))

    def test_token_invalido_e_sem_internet_viram_estado(self):
        estados = []

        async def corpo():
            self.api.status = 401
            canal = telegram.Telegram(self.dd, TOKEN, ponte.Atendente(self.dd, self.nous), estados.append)
            await self._rodar_ate(canal, lambda: "token_invalido" in estados, tempo=4)
            self.api.status = 500
            canal2 = telegram.Telegram(self.dd, TOKEN, ponte.Atendente(self.dd, self.nous), estados.append)
            await self._rodar_ate(canal2, lambda: "sem_internet" in estados, tempo=4)
        rodar(self._com_servidor(corpo))
        self.assertIn("token_invalido", estados)
        self.assertIn("sem_internet", estados)


class Controle(unittest.TestCase):
    """Rotas /mensageiros/* do monitor, sem subir o processo de verdade."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dd = self.tmp.name
        self.api = TelegramFalso()
        self.reinicios = []
        self._reiniciar = controle.reiniciar

        async def falso(dd):
            self.reinicios.append(controle.tem_canal(dd))
        controle.reiniciar = falso

    def tearDown(self):
        controle.reiniciar = self._reiniciar
        self.tmp.cleanup()

    async def _cliente(self, corpo):
        api = web.Application()
        api.add_routes([web.post("/bot{token}/{metodo}", self.api.h)])
        srv = TestServer(api)
        await srv.start_server()
        os.environ["NOUS_TELEGRAM_API"] = "http://127.0.0.1:%d" % srv.port
        app = web.Application()
        controle.add_routes(app, lambda: self.dd)
        app.on_startup.clear()
        mon = TestServer(app)
        await mon.start_server()
        base = "http://127.0.0.1:%d" % mon.port
        try:
            async with aiohttp.ClientSession() as s:
                async def post(caminho, **j):
                    async with s.post(base + caminho, json=j) as r:
                        return r.status, await r.json()
                async def get(caminho, **cab):
                    async with s.get(base + caminho, headers=cab) as r:
                        return r.status, await r.json()
                await corpo(post, get)
        finally:
            await mon.close()
            await srv.close()

    def test_fluxo_do_telegram(self):
        async def corpo(post, get):
            st, d = await post("/mensageiros/telegram/conectar", token="nada", user_id="u1")
            self.assertEqual(st, 400)
            st, d = await post("/mensageiros/telegram/conectar", token="1:" + "x" * 40, user_id="u1")
            self.assertEqual(st, 400)
            self.assertIn("não aceitou", d["erro"])
            st, d = await post("/mensageiros/telegram/conectar", token=TOKEN, user_id="u1")
            self.assertEqual(st, 200)
            self.assertEqual(d["telegram"]["bot"], "nous_teste_bot")
            self.assertEqual(self.reinicios, [True])
            self.assertEqual(ponte.config(self.dd)["telegram"]["token"], TOKEN)
            st, d = await post("/mensageiros/telegram/codigo", user_id="u1")
            self.assertEqual(st, 200)
            self.assertTrue(d["link"].startswith("https://t.me/nous_teste_bot?start="))
            self.assertTrue(ponte.codigo_vigente(self.dd, "telegram"))
            st, d = await get("/mensageiros/estado")
            self.assertEqual(d["telegram"]["conectado"], True)
            self.assertNotIn("token", json.dumps(d))      # o token nunca volta para a tela
            st, d = await get("/mensageiros/estado", **{"X-Nous-Portao": "1"})
            self.assertEqual(st, 403)                      # pelo celular, nada
            st, d = await post("/mensageiros/telegram/desconectar")
            self.assertEqual(d["telegram"]["conectado"], False)
            self.assertEqual(self.reinicios, [True, False])
            self.assertEqual(ponte.config(self.dd), {})
        rodar(self._cliente(corpo))

    def test_whatsapp_exige_aceite(self):
        async def corpo(post, get):
            st, d = await post("/mensageiros/whatsapp/ligar", user_id="u1")
            self.assertEqual(st, 409)
            self.assertEqual(self.reinicios, [])
        rodar(self._cliente(corpo))


if __name__ == "__main__":
    unittest.main()
