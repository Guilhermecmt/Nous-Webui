import hashlib
import json
import os
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

import falsos  # noqa: I001 (poe motor/ no sys.path)
import baixar
import nous_motor
import registro
from processos import Gerente

GGUF = None


def gguf_bytes(tmp):
    c = os.path.join(tmp, "g.gguf")
    falsos.escrever_gguf(c, falsos.GGUF_EMB, resto=b"\1" * 300000)
    with open(c, "rb") as f:
        dados = f.read()
    os.remove(c)
    return dados


class TestBaixar(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = os.path.join(self._tmp.name, "modelos")
        self.reg = falsos.RegistryFalso()
        self.modelo = gguf_bytes(self._tmp.name)
        self.man = self.reg.publicar("library/minilm", "22m", [("model", self.modelo), ("params", b'{"num_ctx": 256}')])
        await self.reg.subir()

    async def asyncTearDown(self):
        await self.reg.parar()
        self._tmp.cleanup()

    async def puxar(self, nome="minilm:22m"):
        return [e async for e in baixar.puxar(self.pasta, nome, self.reg.url)]

    async def test_puxa_e_aparece_no_tags(self):
        ev = await self.puxar()
        self.assertEqual(ev[-1], {"status": "success"})
        m = registro.achar(self.pasta, "minilm:22m")
        self.assertIsNotNone(m)
        self.assertEqual(m.params, {"num_ctx": 256})
        self.assertTrue(m.gguf["embedding"])
        with open(registro.caminho_manifesto(self.pasta, "minilm:22m"), "rb") as f:
            self.assertEqual(f.read(), self.reg.manifestos[("library/minilm", "22m")])
        self.assertEqual(os.listdir(os.path.join(self.pasta, "blobs")).__len__(), 3)
        self.assertFalse(any(n.endswith("-partial") for n in os.listdir(os.path.join(self.pasta, "blobs"))))

    async def test_eventos_iguais_ao_ollama(self):
        ev = await self.puxar()
        st = [e["status"] for e in ev]
        self.assertEqual(st[0], "pulling manifest")
        self.assertEqual(st[-3:], ["verifying sha256 digest", "writing manifest", "success"])
        dig = self.man["layers"][0]["digest"]
        do_modelo = [e for e in ev if e.get("digest") == dig]
        self.assertTrue(do_modelo)
        self.assertEqual(do_modelo[0]["status"], "pulling " + dig[7:19])
        self.assertEqual(do_modelo[0]["total"], len(self.modelo))
        comp = [e.get("completed", 0) for e in do_modelo]
        self.assertEqual(comp, sorted(comp))
        self.assertEqual(comp[-1], len(self.modelo))

    async def test_retoma_com_range(self):
        dig = self.man["layers"][0]["digest"]
        os.makedirs(os.path.join(self.pasta, "blobs"))
        with open(os.path.join(self.pasta, "blobs", dig.replace(":", "-") + "-partial"), "wb") as f:
            f.write(self.modelo[:1000])
        ev = await self.puxar()
        self.assertEqual(ev[-1], {"status": "success"})
        i = self.reg.gets.index(dig)
        self.assertEqual(self.reg.ranges[i], "bytes=1000-")
        with open(os.path.join(self.pasta, "blobs", dig.replace(":", "-")), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), dig[7:])

    async def test_sha_errado(self):
        self.reg.corromper.add(self.man["layers"][0]["digest"])
        ev = await self.puxar()
        self.assertIn("error", ev[-1])
        self.assertIn("sha256", ev[-1]["error"])
        self.assertFalse(os.path.exists(registro.caminho_manifesto(self.pasta, "minilm:22m")))
        self.assertFalse(any(self.man["layers"][0]["digest"][7:] in n for n in os.listdir(os.path.join(self.pasta, "blobs"))))

    async def test_blob_ja_existe_nao_baixa(self):
        await self.puxar()
        self.reg.gets.clear()
        ev = await self.puxar()
        self.assertEqual(ev[-1], {"status": "success"})
        self.assertEqual(self.reg.gets, [])

    async def test_modelo_que_nao_existe(self):
        ev = await self.puxar("nada:1b")
        self.assertIn("error", ev[-1])
        self.assertIn("nada:1b", ev[-1]["error"])

    async def test_nome_com_dono(self):
        self.reg.publicar("fulano/coisa", "latest", [("model", self.modelo)])
        ev = await self.puxar("fulano/coisa")
        self.assertEqual(ev[-1], {"status": "success"})
        self.assertIsNotNone(registro.achar(self.pasta, "fulano/coisa:latest"))

    async def test_apagar_mantem_blob_compartilhado(self):
        self.reg.publicar("library/minilm", "latest", [("model", self.modelo)])
        await self.puxar("minilm:22m")
        await self.puxar("minilm:latest")
        self.assertTrue(baixar.apagar(self.pasta, "minilm:22m"))
        self.assertIsNone(registro.achar(self.pasta, "minilm:22m"))
        self.assertIsNotNone(registro.achar(self.pasta, "minilm:latest"))
        blobs = os.listdir(os.path.join(self.pasta, "blobs"))
        self.assertIn(self.man["layers"][0]["digest"].replace(":", "-"), blobs)
        self.assertNotIn(self.man["layers"][1]["digest"].replace(":", "-"), blobs)
        self.assertFalse(baixar.apagar(self.pasta, "minilm:22m"))
        self.assertTrue(baixar.apagar(self.pasta, "minilm:latest"))
        self.assertEqual(os.listdir(os.path.join(self.pasta, "blobs")), [])

    async def test_apagar_nao_mexe_em_partial_de_outro(self):
        await self.puxar()
        outro = os.path.join(self.pasta, "blobs", "sha256-" + "a" * 64 + "-partial")
        with open(outro, "wb") as f:
            f.write(b"x")
        baixar.apagar(self.pasta, "minilm:22m")
        self.assertTrue(os.path.exists(outro))

    async def test_pull_pelo_servidor(self):
        g = Gerente("llama-server.exe", iniciar=falsos.FabricaFalsa())

        class Puxar:
            @staticmethod
            def puxar(pasta, nome):
                return baixar.puxar(pasta, nome, self.reg.url)
            apagar = staticmethod(baixar.apagar)

        cli = TestClient(TestServer(nous_motor.criar_app("llama", self.pasta, g, "", Puxar)))
        await cli.start_server()
        try:
            r = await cli.post("/api/pull", json={"model": "minilm:22m"})
            ls = [json.loads(l) for l in (await r.text()).splitlines() if l.strip()]
            self.assertEqual(ls[-1], {"status": "success"})
            r = await cli.get("/api/tags")
            self.assertEqual([m["name"] for m in (await r.json())["models"]], ["minilm:22m"])
            r = await cli.post("/api/pull", json={"model": "minilm:22m", "stream": False})
            self.assertEqual(await r.json(), {"status": "success"})
            r = await cli.delete("/api/delete", json={"model": "minilm:22m"})
            self.assertEqual(r.status, 200)
            r = await cli.delete("/api/delete", json={"model": "minilm:22m"})
            self.assertEqual(r.status, 404)
        finally:
            await cli.close()
            await g.soltar_todos()

    async def test_puxar_cli(self):
        import asyncio
        import sys
        g = Gerente("llama-server.exe", iniciar=falsos.FabricaFalsa())

        class Puxar:
            @staticmethod
            def puxar(pasta, nome):
                return baixar.puxar(pasta, nome, self.reg.url)
            apagar = staticmethod(baixar.apagar)

        cli = TestClient(TestServer(nous_motor.criar_app("llama", self.pasta, g, "", Puxar)))
        await cli.start_server()
        script = os.path.join(os.path.dirname(baixar.__file__), "puxar.py")
        try:
            async def rodar(nome):
                p = await asyncio.create_subprocess_exec(sys.executable, script, nome, "--url", str(cli.make_url("")),
                                                         stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                out, err = await p.communicate()
                return p.returncode, out.decode(), err.decode()
            cod, out, _ = await rodar("minilm:22m")
            self.assertEqual(cod, 0)
            self.assertIn("pronto: minilm:22m", out)
            self.assertIsNotNone(registro.achar(self.pasta, "minilm:22m"))
            cod, _, err = await rodar("nada:1b")
            self.assertEqual(cod, 1)
            self.assertIn("nao existe", err)
        finally:
            await cli.close()
            await g.soltar_todos()


if __name__ == "__main__":
    unittest.main()
