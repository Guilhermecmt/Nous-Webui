import dataclasses
import json
import math
import os
import tempfile
import unittest

import falsos
import registro
import traduz

AMOSTRAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "amostras")


def amostra(nome):
    with open(os.path.join(AMOSTRAS, nome), encoding="utf-8") as f:
        return json.load(f)


def texto_da_amostra(eventos, campo):
    return "".join((c.get("delta", {}).get(campo) or "") for e in eventos for c in e.get("choices", []))


class TestTraduz(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        p = falsos.pasta_falsa(cls._tmp.name)
        cls.qwen = registro.achar(p, "qwen3:4b")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_opcoes_padrao_por_baixo(self):
        self.assertEqual(traduz.opcoes_openai({"temperature": 0.1, "num_predict": 50}, {"temperature": 0.6, "top_k": 20}),
                         {"temperature": 0.1, "top_k": 20, "max_tokens": 50})
        self.assertEqual(traduz.opcoes_openai({"num_predict": -1, "num_ctx": 8192, "num_gpu": 99}, {}), {})
        self.assertEqual(traduz.opcoes_openai({"repeat_penalty": 1.1, "seed": 7, "stop": ["x"]}, {}),
                         {"repeat_penalty": 1.1, "seed": 7, "stop": ["x"]})

    def test_params_do_modelo_entram(self):
        c = traduz.pedido_chat({"model": "qwen3:4b", "messages": [{"role": "user", "content": "oi"}],
                                "options": {"temperature": 0.2}}, self.qwen)
        self.assertEqual(c["temperature"], 0.2)
        self.assertEqual(c["top_k"], 20)
        self.assertTrue(c["stream"])
        self.assertEqual(c["stream_options"], {"include_usage": True})

    def test_format_json_e_schema(self):
        base = {"model": "qwen3:4b", "messages": [{"role": "user", "content": "oi"}]}
        self.assertEqual(traduz.pedido_chat({**base, "format": "json"}, self.qwen)["response_format"], {"type": "json_object"})
        esq = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
        self.assertEqual(traduz.pedido_chat({**base, "format": esq}, self.qwen)["response_format"],
                         {"type": "json_schema", "json_schema": {"name": "saida", "schema": esq}})
        self.assertNotIn("response_format", traduz.pedido_chat(base, self.qwen))

    def test_think(self):
        base = {"model": "qwen3:4b", "messages": [{"role": "user", "content": "oi"}]}
        self.assertEqual(traduz.pedido_chat({**base, "think": True}, self.qwen)["chat_template_kwargs"], {"enable_thinking": True})
        self.assertEqual(traduz.pedido_chat({**base, "think": False}, self.qwen)["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(traduz.pedido_chat({**base, "think": "high"}, self.qwen)["chat_template_kwargs"], {"reasoning_effort": "high"})
        self.assertNotIn("chat_template_kwargs", traduz.pedido_chat(base, self.qwen))

    def test_generate_vira_mensagens(self):
        c = traduz.pedido_generate({"model": "qwen3:4b", "system": "seja breve", "prompt": "oi", "format": "json",
                                    "options": {"num_predict": 9}}, self.qwen)
        self.assertEqual(c["messages"], [{"role": "system", "content": "seja breve"}, {"role": "user", "content": "oi"}])
        self.assertEqual(c["response_format"], {"type": "json_object"})
        self.assertEqual(c["max_tokens"], 9)
        self.assertEqual(traduz.pedido_generate({"prompt": "oi"}, self.qwen)["messages"], [{"role": "user", "content": "oi"}])

    def test_tool_calls_ida_e_volta(self):
        hist = [{"role": "user", "content": "que horas sao"},
                {"role": "assistant", "content": "", "thinking": "vou ver",
                 "tool_calls": [{"function": {"name": "hora", "arguments": {"fuso": "BRT"}}},
                                {"function": {"name": "data", "arguments": {}}}]},
                {"role": "tool", "content": "10h", "tool_name": "hora"},
                {"role": "tool", "content": "15/11"}]
        ferr = [{"type": "function", "function": {"name": "hora", "parameters": {"type": "object"}}}]
        c = traduz.pedido_chat({"model": "qwen3:4b", "messages": hist, "tools": ferr}, self.qwen)
        a = c["messages"][1]
        self.assertEqual(a["tool_calls"][0], {"id": "call_0", "type": "function",
                                              "function": {"name": "hora", "arguments": '{"fuso": "BRT"}'}})
        self.assertEqual(a["tool_calls"][1]["id"], "call_1")
        self.assertEqual(a["reasoning_content"], "vou ver")
        self.assertEqual(c["messages"][2], {"role": "tool", "content": "10h", "tool_call_id": "call_0"})
        self.assertEqual(c["messages"][3]["tool_call_id"], "call_1")
        self.assertEqual(c["tools"], ferr)

    def test_stream_chat_amostra(self):
        ev = amostra("chat_stream.json")
        j = traduz.Juntador("qwen3:4b", "chat")
        linhas = [l for e in ev for l in j.pedaco(e)]
        fim = j.fim()
        self.assertTrue(all(l["done"] is False and l["model"] == "qwen3:4b" for l in linhas))
        pens = [i for i, l in enumerate(linhas) if l["message"].get("thinking")]
        cont = [i for i, l in enumerate(linhas) if l["message"].get("content")]
        self.assertTrue(pens and cont and max(pens) < min(cont))
        self.assertEqual("".join(l["message"].get("content", "") for l in linhas), texto_da_amostra(ev, "content"))
        self.assertEqual("".join(l["message"].get("thinking", "") for l in linhas), texto_da_amostra(ev, "reasoning_content"))
        uso = [e["usage"] for e in ev if e.get("usage")][-1]
        self.assertTrue(fim["done"])
        self.assertEqual(fim["done_reason"], "stop")
        self.assertEqual(fim["eval_count"], uso["completion_tokens"])
        self.assertEqual(fim["prompt_eval_count"], uso["prompt_tokens"])
        self.assertGreater(fim["eval_duration"], 0)
        self.assertGreater(fim["total_duration"], 0)
        self.assertEqual(fim["message"], {"role": "assistant", "content": ""})
        self.assertTrue(fim["created_at"].endswith("Z"))

    def test_think_false_esconde_pensamento(self):
        ev = amostra("chat_stream.json")
        j = traduz.Juntador("qwen3:4b", "chat", mostrar_pensamento=False)
        linhas = [l for e in ev for l in j.pedaco(e)]
        self.assertFalse(any("thinking" in l["message"] for l in linhas))
        self.assertEqual("".join(l["message"]["content"] for l in linhas), texto_da_amostra(ev, "content"))

    def test_stream_tools_amostra(self):
        j = traduz.Juntador("qwen3:4b", "chat")
        linhas = [l for e in amostra("chat_tools.json") for l in j.pedaco(e)]
        com = [l for l in linhas if l["message"].get("tool_calls")]
        self.assertEqual(len(com), 1)
        tc = com[0]["message"]["tool_calls"][0]["function"]
        self.assertEqual(tc["name"], "hora_atual")
        self.assertEqual(tc["arguments"], {})
        self.assertEqual(j.fim()["done_reason"], "stop")

    def test_generate_inteiro(self):
        ev = amostra("chat_stream.json")
        j = traduz.Juntador("qwen3:4b", "generate")
        for e in ev:
            j.pedaco(e)
        r = j.inteiro()
        self.assertEqual(r["response"], texto_da_amostra(ev, "content"))
        self.assertEqual(r["thinking"], texto_da_amostra(ev, "reasoning_content"))
        self.assertTrue(r["done"])
        self.assertEqual(r["done_reason"], "stop")
        self.assertNotIn("message", r)

    def test_chat_inteiro_com_tools(self):
        j = traduz.Juntador("qwen3:4b", "chat")
        for e in amostra("chat_tools.json"):
            j.pedaco(e)
        r = j.inteiro()
        self.assertEqual(r["message"]["role"], "assistant")
        self.assertEqual(r["message"]["tool_calls"][0]["function"]["name"], "hora_atual")

    def test_stream_generate_json(self):
        j = traduz.Juntador("qwen3:4b", "generate", mostrar_pensamento=False)
        linhas = [l for e in amostra("chat_json_schema.json") for l in j.pedaco(e)]
        self.assertEqual(json.loads("".join(l["response"] for l in linhas)), {"ok": True})
        self.assertFalse(any("thinking" in l for l in linhas))

    def test_limite_vira_length(self):
        j = traduz.Juntador("x", "chat")
        j.pedaco({"choices": [{"index": 0, "delta": {"content": "a"}, "finish_reason": None}]})
        j.pedaco({"choices": [{"index": 0, "delta": {}, "finish_reason": "length"}]})
        self.assertEqual(j.fim()["done_reason"], "length")

    def test_embed_normaliza(self):
        d = {"data": [{"index": 1, "embedding": [0.0, 2.0]}, {"index": 0, "embedding": [3.0, 4.0]}],
             "usage": {"prompt_tokens": 5}}
        r = traduz.resposta_embed(d, "granite-embedding:278m")
        self.assertEqual(r["model"], "granite-embedding:278m")
        self.assertEqual(r["prompt_eval_count"], 5)
        self.assertEqual(r["embeddings"][0], [0.6, 0.8])
        for v in r["embeddings"]:
            self.assertAlmostEqual(math.sqrt(sum(x * x for x in v)), 1.0, delta=1e-6)
        self.assertEqual(traduz.resposta_embeddings({"data": [{"index": 0, "embedding": [3.0, 4.0]}]}), {"embedding": [3.0, 4.0]})
        real = traduz.resposta_embed(amostra("embeddings.json"), "g")
        self.assertEqual(len(real["embeddings"]), 2)

    def test_keep_alive(self):
        k = traduz.keep_alive_segundos
        self.assertEqual(k("5m", "1m"), 300)
        self.assertEqual(k("1h", "5m"), 3600)
        self.assertEqual(k("1h30m", "5m"), 5400)
        self.assertEqual(k("10s", "5m"), 10)
        self.assertEqual(k(30, "5m"), 30)
        self.assertEqual(k("30", "5m"), 30)
        self.assertEqual(k(0, "5m"), 0)
        self.assertEqual(k("0", "5m"), 0)
        self.assertIsNone(k(-1, "5m"))
        self.assertIsNone(k("-1m", "5m"))
        self.assertEqual(k(None, "5m"), 300)
        self.assertEqual(k("lixo", "5m"), 300)

    def test_imagens_sem_projetor_erro(self):
        with self.assertRaises(ValueError) as e:
            traduz.pedido_chat({"model": "qwen3:4b", "messages": [{"role": "user", "content": "o que e", "images": ["aGk="]}]}, self.qwen)
        self.assertIn("nao le imagens", str(e.exception))

    def test_imagens_com_projetor(self):
        m = dataclasses.replace(self.qwen, projetor="x.gguf")
        c = traduz.pedido_chat({"model": "v", "messages": [{"role": "user", "content": "o que e", "images": ["aGk="]}]}, m)
        partes = c["messages"][0]["content"]
        self.assertEqual(partes[0], {"type": "text", "text": "o que e"})
        self.assertEqual(partes[1]["type"], "image_url")
        self.assertTrue(partes[1]["image_url"]["url"].startswith("data:image/"))


if __name__ == "__main__":
    unittest.main()
