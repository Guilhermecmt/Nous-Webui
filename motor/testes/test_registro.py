import os
import tempfile
import unittest
from unittest import mock

import falsos
import registro


class TestRegistro(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.p = falsos.pasta_falsa(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_lista_nome_e_tag(self):
        self.assertEqual([m.nome for m in registro.listar(self.p)], ["granite-embedding:278m", "qwen3:4b"])

    def test_achar_aceita_variantes(self):
        falsos.pasta_falsa(self.p, {"nomic:latest": {"gguf": falsos.GGUF_EMB}})
        self.assertEqual(registro.achar(self.p, "qwen3:4b").nome, "qwen3:4b")
        self.assertEqual(registro.achar(self.p, "registry.ollama.ai/library/qwen3:4b").nome, "qwen3:4b")
        self.assertEqual(registro.achar(self.p, "Qwen3:4B").nome, "qwen3:4b")
        self.assertEqual(registro.achar(self.p, "nomic").nome, "nomic:latest")
        self.assertIsNone(registro.achar(self.p, "nao-existe:1b"))

    def test_nome_com_dono(self):
        falsos.pasta_falsa(self.p, {"fulano/meu:7b": {"gguf": falsos.GGUF_QWEN}})
        self.assertEqual(registro.achar(self.p, "fulano/meu:7b").nome, "fulano/meu:7b")

    def test_details_do_config(self):
        m = registro.achar(self.p, "qwen3:4b")
        self.assertEqual((m.familia, m.tamanho_param, m.quantizacao), ("qwen3", "4.0B", "Q4_K_M"))
        self.assertTrue(m.digest and len(m.digest) == 64)
        self.assertTrue(os.path.isfile(m.blob))
        self.assertGreater(m.tamanho, 0)

    def test_params_do_manifesto(self):
        self.assertEqual(registro.achar(self.p, "qwen3:4b").params, falsos.PARAMS_QWEN)
        self.assertEqual(registro.achar(self.p, "granite-embedding:278m").params, {})

    def test_gguf(self):
        g = registro.achar(self.p, "qwen3:4b").gguf
        self.assertEqual(g["arquitetura"], "qwen3")
        self.assertEqual(g["contexto"], 262144)
        self.assertFalse(g["embedding"])
        self.assertEqual(g["parametros"], 4022468096)
        self.assertIn("<think>", g["template"])
        self.assertEqual(g["info"]["qwen3.block_count"], 36)
        self.assertNotIn("tokenizer.ggml.tokens", g["info"])
        e = registro.achar(self.p, "granite-embedding:278m").gguf
        self.assertTrue(e["embedding"])
        self.assertEqual(e["contexto"], 512)

    def test_gguf_v2_e_arquitetura_de_embedding_sem_pooling(self):
        c = os.path.join(self.p, "x.gguf")
        falsos.escrever_gguf(c, {"general.architecture": "nomic-bert", "nomic-bert.context_length": 2048}, versao=2)
        g = registro.ler_gguf(c)
        self.assertTrue(g["embedding"])
        self.assertEqual(g["contexto"], 2048)

    def test_capacidades(self):
        self.assertEqual(registro.capacidades(registro.achar(self.p, "qwen3:4b")), ["completion", "tools", "thinking"])
        self.assertEqual(registro.capacidades(registro.achar(self.p, "granite-embedding:278m")), ["embedding"])
        falsos.pasta_falsa(self.p, {"vis:1b": {"gguf": falsos.GGUF_QWEN, "projetor": True}})
        m = registro.achar(self.p, "vis:1b")
        self.assertIsNotNone(m.projetor)
        self.assertIn("vision", registro.capacidades(m))

    def test_normalizar_nome(self):
        self.assertEqual(registro.normalizar_nome("qwen3"), "qwen3:latest")
        self.assertEqual(registro.normalizar_nome("registry.ollama.ai/library/QWEN3:4b"), "qwen3:4b")
        self.assertEqual(registro.normalizar_nome("library/qwen3:4b"), "qwen3:4b")
        self.assertEqual(registro.normalizar_nome("fulano/meu"), "fulano/meu:latest")

    def test_pasta_modelos_regra(self):
        with tempfile.TemporaryDirectory() as casa, tempfile.TemporaryDirectory() as dados:
            with mock.patch.dict(os.environ, {"OLLAMA_MODELS": self.p, "USERPROFILE": casa, "HOME": casa, "DATA_DIR": dados}):
                self.assertEqual(registro.pasta_modelos(), self.p)
            amb = {k: v for k, v in os.environ.items() if k != "OLLAMA_MODELS"}
            amb.update({"USERPROFILE": casa, "HOME": casa, "DATA_DIR": dados})
            with mock.patch.dict(os.environ, amb, clear=True):
                self.assertEqual(registro.pasta_modelos(), os.path.join(dados, "modelos"))
                os.makedirs(os.path.join(casa, ".ollama", "models"))
                self.assertEqual(registro.pasta_modelos(), os.path.join(casa, ".ollama", "models"))

    def test_manifesto_quebrado_e_ignorado(self):
        ruim = os.path.join(self.p, "manifests", "registry.ollama.ai", "library", "ruim")
        os.makedirs(ruim)
        with open(os.path.join(ruim, "1b"), "w") as f:
            f.write("{nao e json")
        sem_blob = os.path.join(self.p, "manifests", "registry.ollama.ai", "library", "semblob")
        os.makedirs(sem_blob)
        with open(os.path.join(sem_blob, "1b"), "w") as f:
            f.write('{"layers": [{"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:' + "0" * 64 + '", "size": 1}]}')
        self.assertEqual([m.nome for m in registro.listar(self.p)], ["granite-embedding:278m", "qwen3:4b"])
        self.assertIsNone(registro.achar(self.p, "semblob:1b"))

    def test_pasta_inexistente(self):
        self.assertEqual(registro.listar(os.path.join(self.p, "nada")), [])


if __name__ == "__main__":
    unittest.main()
