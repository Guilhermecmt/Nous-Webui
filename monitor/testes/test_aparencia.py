# -*- coding: utf-8 -*-
"""Escolha da paleta de cores: arquivo em NousData e rotas do monitor."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import AioHTTPTestCase  # noqa: E402

import aparencia  # noqa: E402

SETE = ["ouro", "pitaya", "maracuja", "melancia", "ametista", "ceu", "mata"]


class TestArquivo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ids(self):
        self.assertEqual(aparencia.ids(), SETE)

    def test_padrao_sem_arquivo(self):
        self.assertEqual(aparencia.ler(self.dir), "ouro")

    def test_grava_e_le(self):
        self.assertEqual(aparencia.gravar(self.dir, "pitaya"), "pitaya")
        self.assertEqual(aparencia.ler(self.dir), "pitaya")
        self.assertEqual(json.loads((self.dir / "aparencia.json").read_text(encoding="utf-8")), {"paleta": "pitaya"})

    def test_grava_cria_a_pasta(self):
        sub = self.dir / "ainda-nao-existe"
        aparencia.gravar(sub, "ceu")
        self.assertEqual(aparencia.ler(sub), "ceu")

    def test_id_desconhecido_vira_ouro(self):
        (self.dir / "aparencia.json").write_text('{"paleta": "abacaxi"}', encoding="utf-8")
        self.assertEqual(aparencia.ler(self.dir), "ouro")

    def test_arquivo_corrompido_vira_ouro(self):
        (self.dir / "aparencia.json").write_text("{nao e json", encoding="utf-8")
        self.assertEqual(aparencia.ler(self.dir), "ouro")
        (self.dir / "aparencia.json").write_text('["pitaya"]', encoding="utf-8")
        self.assertEqual(aparencia.ler(self.dir), "ouro")

    def test_gravar_recusa_desconhecida(self):
        with self.assertRaises(ValueError):
            aparencia.gravar(self.dir, "abacaxi")
        self.assertFalse((self.dir / "aparencia.json").exists())


class TestRotas(AioHTTPTestCase):
    async def get_application(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        app = web.Application()
        aparencia.add_routes(app, lambda: d)
        return app

    async def asyncTearDown(self):
        await super().asyncTearDown()
        self.tmp.cleanup()

    async def test_get_lista_sete(self):
        r = await self.client.get("/aparencia")
        self.assertEqual(r.status, 200)
        j = await r.json()
        self.assertEqual(j["paleta"], "ouro")
        self.assertEqual([p["id"] for p in j["paletas"]], SETE)
        self.assertEqual(j["paletas"][5]["nome"], "Céu e Flamingo")
        self.assertIn("tag", j["paletas"][0])

    async def test_post_grava(self):
        r = await self.client.post("/aparencia", json={"paleta": "maracuja"})
        self.assertEqual(r.status, 200)
        self.assertEqual((await r.json())["paleta"], "maracuja")
        r = await self.client.get("/aparencia")
        self.assertEqual((await r.json())["paleta"], "maracuja")

    async def test_post_recusa_desconhecida(self):
        r = await self.client.post("/aparencia", json={"paleta": "abacaxi"})
        self.assertEqual(r.status, 400)
        r = await self.client.post("/aparencia", data="nao e json")
        self.assertEqual(r.status, 400)

    async def test_js(self):
        await self.client.post("/aparencia", json={"paleta": "mata"})
        r = await self.client.get("/aparencia.js")
        self.assertEqual(r.status, 200)
        self.assertIn("javascript", r.headers["Content-Type"])
        self.assertEqual(await r.text(), 'window.NOUS_PALETA="mata";')
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")


if __name__ == "__main__":
    unittest.main()
