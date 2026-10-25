# -*- coding: utf-8 -*-
"""Controle do celular (rotas /celular/* do monitor), sempre em modo de simulacao:
nada muda no Windows; o firewall so' escreve o que EXECUTARIA em simulado.log."""
import asyncio
import json
import os
import socket
import sys
import tempfile
import unittest

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import controle  # noqa: E402
import pareamento as par  # noqa: E402

try:
    import psutil  # noqa: F401
    TEM_PSUTIL = True
except ImportError:
    TEM_PSUTIL = False


def porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipUnless(sys.platform == "win32", "o script de firewall e' do Windows")
@unittest.skipUnless(TEM_PSUTIL and controle.ip_da_rede(), "precisa de psutil e de uma rede privada")
class Controle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = self._t.name
        self._env = dict(os.environ)
        os.environ.update({"NOUS_CELULAR_SIMULAR": "1", "NOUS_CELULAR_PORT": str(porta_livre())})
        os.environ.pop("NOUS_CELULAR_PERFIL_SIMULADO", None)
        app = web.Application()
        controle.add_routes(app, lambda: self.d)
        self.cli = TestClient(TestServer(app))
        await self.cli.start_server()

    async def asyncTearDown(self):
        try:
            await self.cli.post("/celular/desligar", json={})
        finally:
            await self.cli.close()
            os.environ.clear()
            os.environ.update(self._env)
            self._t.cleanup()

    def log(self):
        p = os.path.join(par.pasta(self.d), "simulado.log")
        return open(p, encoding="utf-8").read() if os.path.exists(p) else ""

    async def test_rede_publica_nao_liga(self):
        os.environ["NOUS_CELULAR_PERFIL_SIMULADO"] = "Public"
        r = await self.cli.post("/celular/ligar", json={})
        j = await r.json()
        self.assertEqual((r.status, j["erro"]), (409, "rede_publica"))
        self.assertIn("Privada", j["texto"])
        self.assertEqual(self.log(), "", "nenhuma regra pode ser criada em rede publica")
        self.assertFalse((await (await self.cli.get("/celular/estado")).json())["ligado"])

    async def test_ligar_codigo_desligar(self):
        r = await self.cli.post("/celular/codigo", json={})
        self.assertEqual(r.status, 409, "sem ligar nao ha codigo")
        r = await self.cli.post("/celular/ligar", json={})
        e = await r.json()
        self.assertEqual(r.status, 200, e)
        self.assertTrue(e["ligado"] and e["regra"])
        self.assertIn("[SIMULADO] New-NetFirewallRule", self.log())
        for trecho in ("-Profile Private", "-RemoteAddress LocalSubnet", "-LocalPort %s" % e["porta"], "-Protocol TCP"):
            self.assertIn(trecho, self.log())
        c = await (await self.cli.post("/celular/codigo", json={})).json()
        self.assertRegex(c["codigo"], r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertTrue(c["qr"])
        # o QR leva ao portao, com o codigo no fragmento (nao vai para logs nem Referer)
        async with aiohttp.ClientSession() as s:
            u = "http://127.0.0.1:%d/_portao/saude" % e["porta"]
            self.assertEqual((await s.get(u)).status, 200)
        # pareia de verdade pelo portao (IP de origem da rede de casa nao se injeta aqui: so' confere a troca)
        self.assertIsNotNone(par.codigo_vigente(self.d))
        r = await self.cli.post("/celular/desligar", json={})
        j = await r.json()
        self.assertFalse(j["ligado"])
        self.assertFalse(j["regra"])
        self.assertIn("[SIMULADO] Remove-NetFirewallRule", self.log())
        await asyncio.sleep(0.5)
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", e["porta"]), timeout=1).close()

    async def test_so_o_computador(self):
        r = await self.cli.get("/celular/estado", headers={"X-Nous-Portao": "1"})
        self.assertEqual(r.status, 403)
        r = await self.cli.post("/celular/ligar", json={}, headers={"X-Nous-Portao": "1"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self.log(), "")

    async def test_remover_aparelhos(self):
        cod, _ = par.novo_codigo(self.d)
        ck = par.trocar_codigo(self.d, cod, "iPhone Safari/1", "192.168.1.9")
        e = await (await self.cli.get("/celular/estado")).json()
        self.assertEqual([a["nome"] for a in e["aparelhos"]], ["iPhone - Safari"])
        self.assertNotIn("hash", json.dumps(e), "o estado nunca mostra o segredo")
        r = await (await self.cli.post("/celular/aparelhos/remover", json={"id": ck.split(".")[0]})).json()
        self.assertEqual(r["aparelhos"], [])


if __name__ == "__main__":
    unittest.main()
