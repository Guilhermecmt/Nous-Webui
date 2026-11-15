import asyncio
import json
import os
import tempfile
import unittest
from unittest import mock

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

import falsos
import nous_motor
from processos import Gerente


async def linhas_ndjson(r):
    return [json.loads(l) for l in (await r.text()).splitlines() if l.strip()]


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.pasta = falsos.pasta_falsa(os.path.join(self._tmp.name, "modelos"))
        self.fab = falsos.FabricaFalsa()
        self.gerente = Gerente("llama-server.exe", iniciar=self.fab)
        self.app = nous_motor.criar_app("llama", self.pasta, self.gerente, "http://127.0.0.1:1")
        self.cli = TestClient(TestServer(self.app))
        await self.cli.start_server()

    async def asyncTearDown(self):
        await self.cli.close()
        await self.gerente.soltar_todos()
        self._tmp.cleanup()


class TestServidorLlama(Base):
    async def test_tags_e_show(self):
        r = await self.cli.get("/api/version")
        self.assertIn("version", await r.json())
        r = await self.cli.get("/")
        self.assertEqual(await r.text(), "Ollama is running")
        r = await self.cli.get("/api/tags")
        tags = (await r.json())["models"]
        self.assertEqual([m["name"] for m in tags], ["granite-embedding:278m", "qwen3:4b"])
        self.assertEqual(tags[1]["model"], "qwen3:4b")
        self.assertEqual(tags[1]["details"]["family"], "qwen3")
        self.assertTrue(tags[1]["modified_at"].endswith("Z") or "+" in tags[1]["modified_at"])
        r = await self.cli.post("/api/show", json={"model": "qwen3:4b"})
        s = await r.json()
        self.assertEqual(s["capabilities"], ["completion", "tools", "thinking"])
        self.assertEqual(s["details"]["family"], "qwen3")
        self.assertEqual(s["model_info"]["qwen3.context_length"], 262144)
        self.assertEqual(s["model_info"]["general.architecture"], "qwen3")
        self.assertIn("temperature", s["parameters"])
        self.assertIn(".Tools", s["template"])
        r = await self.cli.post("/api/show", json={"name": "qwen3:4b"})
        self.assertEqual(r.status, 200)

    async def test_chat_stream_ndjson(self):
        r = await self.cli.post("/api/chat", json={"model": "qwen3:4b", "messages": [{"role": "user", "content": "oi"}]})
        self.assertEqual(r.status, 200)
        self.assertTrue(r.headers["Content-Type"].startswith("application/x-ndjson"))
        ls = await linhas_ndjson(r)
        self.assertTrue(ls[-1]["done"])
        self.assertEqual(ls[-1]["done_reason"], "stop")
        self.assertEqual("".join(l["message"]["content"] for l in ls), "Oi")
        pedido = self.fab.processos[0].servidor.pedidos[0][1]
        self.assertTrue(pedido["stream"])
        self.assertEqual(pedido["top_k"], 20)

    async def test_chat_sem_stream(self):
        r = await self.cli.post("/api/chat", json={"model": "qwen3:4b", "stream": False, "think": False,
                                                   "messages": [{"role": "user", "content": "oi"}]})
        j = await r.json()
        self.assertEqual(j["message"]["content"], "Oi")
        self.assertNotIn("thinking", j["message"])
        self.assertTrue(j["done"])

    async def test_generate_json_schema(self):
        self.fab.opcoes["amostra"] = "chat_json_schema.json"
        esq = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
        r = await self.cli.post("/api/generate", json={"model": "qwen3:4b", "prompt": "ok?", "format": esq, "stream": False,
                                                       "options": {"num_ctx": 4096}})
        j = await r.json()
        self.assertEqual(json.loads(j["response"]), {"ok": True})
        pedido = self.fab.processos[0].servidor.pedidos[0][1]
        self.assertEqual(pedido["response_format"]["type"], "json_schema")
        a = self.fab.argvs[0]
        self.assertEqual(a[a.index("-c") + 1], "4096")

    async def test_generate_vazio_carrega_e_keep_alive_zero_descarrega(self):
        r = await self.cli.post("/api/generate", json={"model": "qwen3:4b"})
        j = (await linhas_ndjson(r))[-1]
        self.assertEqual(j["done_reason"], "load")
        r = await self.cli.get("/api/ps")
        self.assertEqual(len((await r.json())["models"]), 1)
        r = await self.cli.post("/api/generate", json={"model": "qwen3:4b", "keep_alive": 0})
        j = (await linhas_ndjson(r))[-1]
        self.assertEqual(j["done_reason"], "unload")
        r = await self.cli.get("/api/ps")
        self.assertEqual((await r.json())["models"], [])
        r = await self.cli.post("/api/chat", json={"model": "qwen3:4b", "messages": [], "stream": False})
        self.assertEqual((await r.json())["done_reason"], "load")

    async def test_embed_e_embeddings(self):
        r = await self.cli.post("/api/embed", json={"model": "granite-embedding:278m", "input": ["a", "b"]})
        j = await r.json()
        self.assertEqual(j["model"], "granite-embedding:278m")
        self.assertEqual(len(j["embeddings"]), 2)
        self.assertAlmostEqual(sum(x * x for x in j["embeddings"][0]), 1.0, places=6)
        r = await self.cli.post("/api/embed", json={"model": "granite-embedding:278m", "input": "a"})
        self.assertEqual(len((await r.json())["embeddings"]), 1)
        r = await self.cli.post("/api/embeddings", json={"model": "granite-embedding:278m", "prompt": "a"})
        self.assertEqual(await r.json(), {"embedding": [3.0, 4.0]})
        self.assertEqual(len(self.fab.argvs), 1)

    async def test_embed_texto_longo_e_cortado_como_no_ollama(self):
        self.fab.opcoes["limite_tokens"] = 10
        longo = " ".join("palavra%d" % i for i in range(30))
        r = await self.cli.post("/api/embed", json={"model": "granite-embedding:278m", "input": [longo, "curto"]})
        self.assertEqual(r.status, 200, await r.text())
        self.assertEqual(len((await r.json())["embeddings"]), 2)
        r = await self.cli.post("/api/embeddings", json={"model": "granite-embedding:278m", "prompt": longo})
        self.assertEqual(r.status, 200)
        enviados = [c["input"] for rota, c in self.fab.processos[0].servidor.pedidos if rota == "/v1/embeddings"]
        self.assertTrue(all(len(t.split()) <= 10 for lista in enviados[1::2] for t in lista))
        self.assertTrue(enviados[1][0].startswith("palavra0 palavra1"))

    async def test_embed_em_modelo_de_conversa(self):
        r = await self.cli.post("/api/embed", json={"model": "qwen3:4b", "input": "a"})
        self.assertEqual(r.status, 400)
        self.assertIn("embedding", (await r.json())["error"])

    async def test_chat_em_modelo_de_embedding(self):
        r = await self.cli.post("/api/chat", json={"model": "granite-embedding:278m", "messages": [{"role": "user", "content": "x"}]})
        self.assertEqual(r.status, 400)
        self.assertIn("error", await r.json())

    async def test_modelo_inexistente(self):
        r = await self.cli.post("/api/chat", json={"model": "x", "messages": [{"role": "user", "content": "oi"}]})
        self.assertEqual(r.status, 404)
        self.assertIn("modelo 'x' nao encontrado", (await r.json())["error"])
        r = await self.cli.post("/api/show", json={"model": "x"})
        self.assertEqual(r.status, 404)

    async def test_corpo_invalido(self):
        r = await self.cli.post("/api/chat", data=b"{nao json")
        self.assertEqual(r.status, 400)
        self.assertIn("error", await r.json())

    async def test_imagem_sem_projetor(self):
        r = await self.cli.post("/api/chat", json={"model": "qwen3:4b", "messages": [{"role": "user", "content": "x", "images": ["aGk="]}]})
        self.assertEqual(r.status, 400)
        self.assertIn("nao le imagens", (await r.json())["error"])

    async def test_falha_ao_carregar_vira_erro(self):
        self.fab.morrer_ao_carregar = True
        r = await self.cli.post("/api/chat", json={"model": "qwen3:4b", "messages": [{"role": "user", "content": "oi"}]})
        self.assertEqual(r.status, 500)
        self.assertIn("Device memory allocation failed", (await r.json())["error"])

    async def test_cliente_desiste_fecha_upstream(self):
        self.fab.opcoes["atraso_por_token"] = 0.05
        async with aiohttp.ClientSession() as s:
            url = str(self.cli.make_url("/api/chat"))
            async with s.post(url, json={"model": "qwen3:4b", "messages": [{"role": "user", "content": "oi"}]}) as r:
                await r.content.readline()
        falso = self.fab.processos[0].servidor
        for _ in range(100):
            if falso.fechou_antes_do_fim or falso.terminou_stream:
                break
            await asyncio.sleep(0.05)
        self.assertTrue(falso.fechou_antes_do_fim)
        self.assertFalse(falso.terminou_stream)

    async def test_cliente_desiste_sem_stream_fecha_upstream(self):
        # filtro com timeout (agenda 120 s) desiste: a placa nao pode seguir gerando
        self.fab.opcoes["atraso_por_token"] = 0.05
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=0.6)) as s:
            with self.assertRaises(asyncio.TimeoutError):
                async with s.post(str(self.cli.make_url("/api/chat")), json={"model": "qwen3:4b", "stream": False,
                                                                              "messages": [{"role": "user", "content": "oi"}]}) as r:
                    await r.read()
        falso = self.fab.processos[0].servidor
        for _ in range(100):
            if falso.fechou_antes_do_fim or falso.terminou_stream:
                break
            await asyncio.sleep(0.05)
        self.assertTrue(falso.fechou_antes_do_fim)

    async def test_pensamento_escondido_tambem_para(self):
        # think:false nao escreve nada enquanto o modelo pensa: o Parar tem que valer mesmo assim
        self.fab.opcoes["atraso_por_token"] = 0.05
        async with aiohttp.ClientSession() as s:
            r = await s.post(str(self.cli.make_url("/api/chat")), json={"model": "qwen3:4b", "think": False,
                                                                         "messages": [{"role": "user", "content": "oi"}]})
            await asyncio.sleep(0.5)
            r.close()
        falso = self.fab.processos[0].servidor
        for _ in range(100):
            if falso.fechou_antes_do_fim or falso.terminou_stream:
                break
            await asyncio.sleep(0.05)
        self.assertTrue(falso.fechou_antes_do_fim)

    async def test_llama_server_travado_nao_pendura_para_sempre(self):
        self.app[nous_motor.K_LEITURA] = 0.5
        self.fab.opcoes["atraso_por_token"] = 5
        r = await self.cli.post("/api/chat", json={"model": "qwen3:4b", "stream": False,
                                                   "messages": [{"role": "user", "content": "oi"}]})
        self.assertEqual(r.status, 504)
        self.assertIn("parou de responder", (await r.json())["error"])
        for _ in range(100):  # o servidor travado sai assim que o pedido solta
            if not self.gerente.ativos():
                break
            await asyncio.sleep(0.05)
        self.assertEqual(self.gerente.ativos(), [])
        self.assertTrue(self.fab.processos[0].encerrado)

    async def test_rotas_nao_suportadas(self):
        for rota in ("/api/create", "/api/copy", "/api/push"):
            r = await self.cli.post(rota, json={"model": "a"})
            self.assertEqual(r.status, 501)
            self.assertIn("error", await r.json())

    async def test_health(self):
        r = await self.cli.get("/health")
        self.assertEqual(await r.json(), {"ok": True, "motor": "llama"})


class TestServidorOllama(unittest.IsolatedAsyncioTestCase):
    async def test_modo_ollama_repassa(self):
        ol = falsos.OllamaFalso()
        url = await ol.subir()
        cli = TestClient(TestServer(nous_motor.criar_app("ollama", "", None, url)))
        await cli.start_server()
        try:
            r = await cli.get("/api/tags")
            self.assertEqual(await r.json(), {"models": [{"name": "do-ollama:1b"}]})
            r = await cli.post("/api/chat", json={"model": "m", "messages": []})
            self.assertTrue(r.headers["Content-Type"].startswith("application/x-ndjson"))
            self.assertEqual([l["i"] for l in await linhas_ndjson(r)], [0, 1, 2])
            r = await cli.post("/api/pull", json={"model": "m"})
            self.assertEqual(len(await linhas_ndjson(r)), 3)
            r = await cli.delete("/api/delete", json={"model": "m"})
            self.assertEqual(r.status, 404)
            self.assertEqual(ol.pedidos[1][2], json.dumps({"model": "m", "messages": []}).encode())
            self.assertEqual(ol.pedidos[3][0], "DELETE")
            r = await cli.get("/health")
            self.assertEqual(await r.json(), {"ok": True, "motor": "ollama"})
        finally:
            await cli.close()
            await ol.parar()

    async def test_ollama_desligado(self):
        cli = TestClient(TestServer(nous_motor.criar_app("ollama", "", None, "http://127.0.0.1:9")))
        await cli.start_server()
        try:
            r = await cli.get("/api/tags")
            self.assertEqual(r.status, 502)
            self.assertIn("Ollama", (await r.json())["error"])
        finally:
            await cli.close()


class TestMain(unittest.TestCase):
    def test_main_cancela_o_pedido_quando_o_cliente_some(self):
        # o TestServer dos testes ja' cancela; o run_app de producao so' com handler_cancellation=True
        with tempfile.TemporaryDirectory() as d,                 mock.patch.dict(os.environ, {"DATA_DIR": d, "NOUS_MOTOR": "ollama", "NOUS_MOTOR_PORT": "18999"}),                 mock.patch.object(nous_motor.web, "run_app") as run:
            nous_motor.main()
        self.assertTrue(run.call_args.kwargs.get("handler_cancellation"))
        self.assertEqual(run.call_args.kwargs.get("host"), "127.0.0.1")


class TestEscolherMotor(unittest.TestCase):
    def test_escolher_motor(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "llama-server.exe")
            amb = {k: v for k, v in os.environ.items() if k != "NOUS_MOTOR"}
            with mock.patch.dict(os.environ, amb, clear=True):
                self.assertEqual(nous_motor.escolher_motor(d, exe), "ollama")
                open(exe, "w").close()
                self.assertEqual(nous_motor.escolher_motor(d, exe), "llama")
                os.makedirs(os.path.join(d, "motor"))
                with open(os.path.join(d, "motor", "ajustes.json"), "w") as f:
                    json.dump({"motor": "ollama"}, f)
                self.assertEqual(nous_motor.escolher_motor(d, exe), "ollama")
            with mock.patch.dict(os.environ, {"NOUS_MOTOR": "llama"}):
                self.assertEqual(nous_motor.escolher_motor(d, exe), "llama")
            with mock.patch.dict(os.environ, {"NOUS_MOTOR": "lixo"}):
                self.assertEqual(nous_motor.escolher_motor(d, exe), "ollama")


if __name__ == "__main__":
    unittest.main()
