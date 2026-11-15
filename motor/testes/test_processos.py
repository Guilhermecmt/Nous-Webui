import asyncio
import dataclasses
import tempfile
import time
import unittest

import falsos
import registro
from processos import ErroMotor, Gerente


class TestProcessos(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        p = falsos.pasta_falsa(self._tmp.name)
        self.qwen = registro.achar(p, "qwen3:4b")
        self.emb = registro.achar(p, "granite-embedding:278m")
        self.fab = falsos.FabricaFalsa()

    async def asyncTearDown(self):
        for g in getattr(self, "_gerentes", []):
            await g.soltar_todos()
        self._tmp.cleanup()

    def gerente(self, **kw):
        g = Gerente("llama-server.exe", iniciar=self.fab, **kw)
        self._gerentes = getattr(self, "_gerentes", []) + [g]
        return g

    def outro(self, nome, contexto=40960):
        return dataclasses.replace(self.qwen, nome=nome, gguf={**self.qwen.gguf, "contexto": contexto})

    def vivos(self):
        return [p for p in self.fab.processos if p.returncode is None and not p.encerrado]

    async def test_argv(self):
        g = self.gerente()
        url = await g.garantir(self.qwen, None)
        a = self.fab.argvs[0]
        self.assertEqual(a[0], "llama-server.exe")
        self.assertEqual(a[a.index("-m") + 1], self.qwen.blob)
        self.assertEqual(a[a.index("-c") + 1], "16384")
        self.assertNotIn("-ngl", a)  # o llama-server decide quantas camadas cabem na placa (--fit)
        self.assertEqual(a[a.index("--host") + 1], "127.0.0.1")
        self.assertEqual(a[a.index("--reasoning-format") + 1], "deepseek")
        self.assertEqual(a[a.index("-np") + 1], "1")
        self.assertIn("--jinja", a)
        self.assertIn("--no-webui", a)
        self.assertNotIn("--embeddings", a)
        self.assertEqual(url, "http://127.0.0.1:" + a[a.index("--port") + 1])
        await g.garantir(self.emb, None)
        self.assertIn("--embeddings", self.fab.argvs[1])
        e = self.fab.argvs[1]
        self.assertEqual(e[e.index("-c") + 1], "512")
        self.assertEqual(e[e.index("-ub") + 1], "512")

    async def test_projetor_vai_no_argv(self):
        g = self.gerente()
        await g.garantir(dataclasses.replace(self.qwen, nome="vis:1b", projetor="C:/p.gguf"), None)
        a = self.fab.argvs[0]
        self.assertEqual(a[a.index("--mmproj") + 1], "C:/p.gguf")

    async def test_espera_health(self):
        self.fab.opcoes["health_503"] = 3
        g = self.gerente()
        await g.garantir(self.qwen, None)
        self.assertEqual(self.fab.processos[0].servidor.health_503, 0)

    async def test_reaproveita(self):
        g = self.gerente()
        u1 = await g.garantir(self.qwen, None)
        u2 = await g.garantir(self.qwen, 8192)
        self.assertEqual(u1, u2)
        self.assertEqual(len(self.fab.argvs), 1)

    async def test_pedidos_juntos_sobem_um_so(self):
        g = self.gerente()
        await asyncio.gather(g.garantir(self.qwen, None), g.garantir(self.qwen, None))
        self.assertEqual(len(self.fab.argvs), 1)

    async def test_contexto_maior_recarrega(self):
        g = self.gerente()
        await g.garantir(self.qwen, None)
        await g.garantir(self.qwen, 32768)
        self.assertEqual(len(self.fab.argvs), 2)
        self.assertTrue(self.fab.processos[0].encerrado)
        a = self.fab.argvs[1]
        self.assertEqual(a[a.index("-c") + 1], "32768")

    async def test_contexto_limitado_pelo_modelo(self):
        g = self.gerente()
        await g.garantir(self.outro("q14:x", 40960), 999999)
        a = self.fab.argvs[0]
        self.assertEqual(a[a.index("-c") + 1], "40960")

    async def test_limite_derruba_ocioso_mais_antigo(self):
        g = self.gerente(max_modelos=2)
        a, b, c = self.outro("a:1"), self.outro("b:1"), self.outro("c:1")
        await g.garantir(a, None)
        await g.garantir(b, None)
        await g.garantir(a, None)  # a usado por ultimo: b e' o mais antigo
        await g.garantir(c, None)
        nomes = sorted(x["name"] for x in g.ativos())
        self.assertEqual(nomes, ["a:1", "c:1"])

    async def test_nao_derruba_modelo_em_uso(self):
        g = self.gerente(max_modelos=1)
        a, b = self.outro("a:1"), self.outro("b:1")
        cm = g.usando(a, None, "5m")
        await cm.__aenter__()
        tarefa = asyncio.ensure_future(g.garantir(b, None))
        await asyncio.sleep(0.3)
        self.assertFalse(tarefa.done())
        self.assertEqual([x["name"] for x in g.ativos()], ["a:1"])
        await cm.__aexit__(None, None, None)
        await asyncio.wait_for(tarefa, 5)
        self.assertEqual([x["name"] for x in g.ativos()], ["b:1"])

    async def test_embedding_nao_conta_no_limite(self):
        g = self.gerente(max_modelos=1)
        await g.garantir(self.qwen, None)
        await g.garantir(self.emb, None)
        self.assertEqual(sorted(x["name"] for x in g.ativos()), ["granite-embedding:278m", "qwen3:4b"])

    async def test_keep_alive_zero_e_faxina(self):
        g = self.gerente()
        async with g.usando(self.qwen, None, 0):
            pass
        await g.faxina()
        self.assertEqual(g.ativos(), [])
        async with g.usando(self.emb, None, -1):
            pass
        await g.faxina()
        self.assertEqual([x["name"] for x in g.ativos()], ["granite-embedding:278m"])
        self.assertTrue(g.ativos()[0]["expires_at"].startswith("2318"))

    async def test_keep_alive_vence(self):
        g = self.gerente()
        async with g.usando(self.qwen, None, "5m"):
            pass
        await g.faxina()
        self.assertEqual(len(g.ativos()), 1)
        g._procs["qwen3:4b"].expira_em = time.time() - 1
        await g.faxina()
        self.assertEqual(g.ativos(), [])

    async def test_soltar(self):
        g = self.gerente()
        await g.garantir(self.qwen, None)
        self.assertTrue(await g.soltar("qwen3:4b"))
        self.assertFalse(await g.soltar("qwen3:4b"))
        self.assertEqual(g.ativos(), [])
        self.assertTrue(self.fab.processos[0].encerrado)

    async def test_processo_morre_no_carregamento(self):
        self.fab.morrer_ao_carregar = True
        g = self.gerente()
        t0 = time.monotonic()
        with self.assertRaises(ErroMotor) as e:
            await g.garantir(self.qwen, None)
        self.assertLess(time.monotonic() - t0, 5)
        self.assertIn("Device memory allocation failed", str(e.exception))
        self.assertIn("qwen3:4b", str(e.exception))
        self.assertEqual(g.ativos(), [])
        self.fab.morrer_ao_carregar = False
        await g.garantir(self.qwen, None)
        self.assertEqual(len(g.ativos()), 1)

    async def test_sem_memoria_libera_ociosos_e_tenta_de_novo(self):
        g = self.gerente(max_modelos=3)
        await g.garantir(self.outro("a:1"), None)
        await g.garantir(self.emb, None)
        self.fab.morrer_vezes = 1
        await g.garantir(self.outro("grande:14b"), None)
        self.assertEqual([x["name"] for x in g.ativos()], ["grande:14b"])

    async def test_sem_memoria_nao_derruba_quem_esta_em_uso(self):
        g = self.gerente(max_modelos=3)
        a = self.outro("a:1")
        cm = g.usando(a, None, "5m")
        await cm.__aenter__()
        self.fab.morrer_vezes = 2
        with self.assertRaises(ErroMotor):
            await g.garantir(self.outro("grande:14b"), None)
        self.assertEqual([x["name"] for x in g.ativos()], ["a:1"])
        await cm.__aexit__(None, None, None)

    async def test_demora_demais_para_ficar_pronto(self):
        self.fab.opcoes["health_503"] = 10 ** 6
        g = self.gerente(espera_pronto=0.5)
        with self.assertRaises(ErroMotor) as e:
            await g.garantir(self.qwen, None)
        self.assertIn("nao ficou pronto", str(e.exception))
        self.assertTrue(self.fab.processos[0].encerrado)

    async def test_processo_morre_depois(self):
        g = self.gerente()
        u1 = await g.garantir(self.qwen, None)
        await self.fab.processos[0].morrer()
        u2 = await g.garantir(self.qwen, None)
        self.assertEqual(len(self.fab.argvs), 2)
        self.assertNotEqual(u1, u2)

    async def test_ativos_formato(self):
        g = self.gerente()
        await g.garantir(self.qwen, None)
        x = g.ativos()[0]
        self.assertEqual(x["name"], "qwen3:4b")
        self.assertEqual(x["model"], "qwen3:4b")
        self.assertEqual(x["digest"], self.qwen.digest)
        self.assertEqual(x["context_length"], 16384)
        self.assertEqual(x["size"], self.qwen.tamanho)
        self.assertEqual(x["size_vram"], self.qwen.tamanho)
        self.assertTrue(x["expires_at"].endswith("Z"))
        self.assertEqual(x["details"]["family"], "qwen3")
        self.assertEqual(x["details"]["parameter_size"], "4.0B")


if __name__ == "__main__":
    unittest.main()
