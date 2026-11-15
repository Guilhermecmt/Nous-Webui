# -*- coding: utf-8 -*-
"""Marcas no fim da resposta (⟦tarefa⟧, ⟦abrir⟧, ⟦opcao⟧, avisos) precisam chegar a' tela.

No Open WebUI 0.12 o outlet recebe a resposta com `content` E `output` (lista de itens
type=message com partes output_text). Quando `output` existe, a tela desenha so' ele
(ContentRenderer -> StructuredOutputRenderer) e ignora o `content`: um filtro que mexe
so' no `content` some com a marca e o Nous Code / painel nunca abre."""
import asyncio
import importlib.util
import os
import sys
import time
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UID = "u1"


def carregar(nome, *partes):
    spec = importlib.util.spec_from_file_location(nome, os.path.join(RAIZ, *partes))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


def texto_da_tela(msg):
    """O que a tela do 0.12 mostra: o texto do `output` quando ele existe."""
    out = msg.get("output")
    if isinstance(out, list) and out:
        return "\n".join("".join(p.get("text") or "" for p in (i.get("content") or []) if isinstance(p, dict))
                         for i in out if isinstance(i, dict) and i.get("type") == "message")
    return msg.get("content") or ""


def corpo(resposta, com_output=True):
    asst = {"id": "m2", "role": "assistant", "content": resposta}
    if com_output:
        asst["output"] = [
            {"type": "reasoning", "id": "r1", "content": [{"type": "output_text", "text": "pensando"}]},
            {"type": "message", "id": "m", "status": "completed", "role": "assistant",
             "content": [{"type": "output_text", "text": resposta}]},
        ]
    return {"messages": [{"id": "m1", "role": "user", "content": "oi"}, asst]}


def rodar(coro):
    return asyncio.run(coro)


class MarcasChegamATela(unittest.TestCase):
    def conferir(self, body, marca):
        asst = body["messages"][-1]
        self.assertIn(marca, asst["content"])
        self.assertIn(marca, texto_da_tela(asst))
        # o raciocinio nao ganha a marca
        if asst.get("output"):
            self.assertNotIn(marca, asst["output"][0]["content"][0]["text"])

    def test_comandos_tarefa(self):
        mod = carregar("nous_comandos_t", "utilidades", "nous_comandos.py")
        f = mod.Filter()
        marca = mod.marcador_tarefa("auto", "lista os arquivos de Downloads")
        f._pending[UID] = (time.time(), marca)
        body = rodar(f.outlet(corpo("Abrindo o Nous Code com o seu pedido."), {"id": UID}))
        self.conferir(body, marca)

    def test_comandos_sem_output(self):
        mod = carregar("nous_comandos_t2", "utilidades", "nous_comandos.py")
        f = mod.Filter()
        f._pending[UID] = (time.time(), "⟦abrir:agenda⟧")
        body = rodar(f.outlet(corpo("Pronto, abrindo.", com_output=False), {"id": UID}))
        self.assertTrue(body["messages"][-1]["content"].endswith("⟦abrir:agenda⟧"))
        self.assertNotIn("output", body["messages"][-1])

    def test_comandos_output_sem_item_de_mensagem(self):
        mod = carregar("nous_comandos_t3", "utilidades", "nous_comandos.py")
        f = mod.Filter()
        f._pending[UID] = (time.time(), "⟦abrir:agenda⟧")
        body = corpo("Pronto.")
        body["messages"][-1]["output"] = body["messages"][-1]["output"][:1]  # so' o raciocinio
        body = rodar(f.outlet(body, {"id": UID}))
        self.conferir(body, "⟦abrir:agenda⟧")

    def test_agenda_desfazer(self):
        mod = carregar("nous_agenda_t", "agenda", "nous_agenda.py")
        f = mod.Filter()
        f._marks[UID] = time.time()
        body = rodar(f.outlet(corpo("Anotei: dentista sexta as 14h."), {"id": UID}))
        self.conferir(body, "⟦opcao:↩ Desfazer|desfazer⟧")

    def test_email_opcoes(self):
        mod = carregar("nous_email_chat_t", "email", "nous_email_chat.py")
        f = mod.Filter()
        f._options[UID] = (time.time(), [("Ler o primeiro", "ler o primeiro e-mail")])
        body = rodar(f.outlet(corpo("Chegaram 3 e-mails."), {"id": UID}))
        self.conferir(body, "⟦opcao:Ler o primeiro|ler o primeiro e-mail⟧")

    def test_guarda_aviso(self):
        mod = carregar("nous_guarda_t", "utilidades", "nous_guarda.py")
        if mod.requests is None:
            self.skipTest("sem requests")
        f = mod.Filter()
        f._agenda_ok = lambda uid: False
        body = rodar(f.outlet(corpo("Agendei para sexta."), {"id": UID}))
        self.conferir(body, "⚠ Atenção: nada foi salvo na sua agenda")


if __name__ == "__main__":
    unittest.main()
