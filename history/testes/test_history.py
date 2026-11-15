# -*- coding: utf-8 -*-
"""
Testes do historico de conversas: busca por data, um trecho por conversa, vizinhos, palavra
solta e, principalmente, conversa apagada que nao pode voltar como contexto.

O indexador e o filtro sao os de verdade, sobre um webui.db de mentira com o formato do
Open WebUI 0.12.3. Sem Ollama: os embeddings sao uma contagem de palavras.

    python -m unittest discover -s history/testes -t history/testes
"""
import datetime
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import numpy  # noqa: F401
    import pydantic  # noqa: F401
    import requests  # noqa: F401
    TEM_DEPS = True
except ImportError:  # pragma: no cover
    TEM_DEPS = False


def carregar(nome, *partes):
    spec = importlib.util.spec_from_file_location(nome, os.path.join(RAIZ, *partes))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


if TEM_DEPS:
    idx = carregar("index_history_t", "history", "index_history.py")
    hist = carregar("nous_history_t", "history", "nous_history.py")

AGORA = datetime.datetime(2026, 11, 5, 10, 0)  # quinta
VOCAB = ["dentista", "consulta", "viagem", "paris", "receita", "bolo", "imposto", "carro", "pneu", "jardim"]


def ts(*a):
    return int(datetime.datetime(*a).timestamp())


def vetor(texto):
    """Embedding de mentira: quais palavras do vocabulario aparecem."""
    t = (texto or "").lower()
    return [float(w in t) for w in VOCAB]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nous-hist-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.dict(os.environ, {"DATA_DIR": self.tmp})
        p.start()
        self.addCleanup(p.stop)
        self.webui = os.path.join(self.tmp, "webui.db")
        self.w = sqlite3.connect(self.webui)
        self.addCleanup(self.w.close)
        self.w.execute("""CREATE TABLE chat_message (id TEXT PRIMARY KEY, chat_id TEXT, user_id TEXT, role TEXT,
                          content TEXT, output TEXT, created_at INTEGER)""")
        self.h = idx.open_hist(os.path.join(self.tmp, "nous_history.sqlite3"))
        self.addCleanup(self.h.close)
        e = mock.patch.object(idx, "_embed", vetor)
        e.start()
        self.addCleanup(e.stop)
        hist._CACHE.update(key=None, ids=[], msg_ids=[], asst_ids=[], user_msgs=[], asst_msgs=[], chats=[],
                           timestamps=[], mat=None)
        self.f = hist.Filter()
        self.f._embed = vetor
        self.n = 0

    def par(self, chat, pergunta, resposta="Certo, anotado por aqui.", quando=None, user="u1"):
        """Uma pergunta e a resposta, com ids no formato <chat>-<mensagem>."""
        self.n += 1
        quando = quando or ts(2026, 11, 1, 9, 0) + self.n
        q, a = f"{chat}-q{self.n}", f"{chat}-a{self.n}"
        self.w.execute("INSERT INTO chat_message VALUES (?,?,?,?,?,?,?)", (q, chat, user, "user", pergunta, None, quando))
        if resposta:
            self.w.execute("INSERT INTO chat_message VALUES (?,?,?,?,?,?,?)",
                           (a, chat, user, "assistant", resposta, None, quando + 1))
        self.w.commit()
        return q, a

    def indexa(self):
        return idx.index_once(self.h, self.webui, log=lambda *_: None)

    def apaga_chat(self, chat):
        self.w.execute("DELETE FROM chat_message WHERE chat_id=?", (chat,))
        self.w.commit()

    def apaga_msg(self, mid):
        self.w.execute("DELETE FROM chat_message WHERE id=?", (mid,))
        self.w.commit()

    def busca(self, q, user="u1", **kw):
        return self.f._retrieve(q, user_id=user, now=AGORA, **kw)

    def textos(self, q, **kw):
        return "\n".join(t for _l, t in self.busca(q, **kw)[0])

    def indexados(self):
        return self.h.execute("SELECT COUNT(*) FROM dialogues").fetchone()[0]

    def fts(self, palavra):
        return self.h.execute("SELECT COUNT(*) FROM dialogues_fts WHERE dialogues_fts MATCH ?",
                              (f'"{palavra}"',)).fetchone()[0]


@unittest.skipUnless(TEM_DEPS, "faltam numpy/pydantic/requests")
class Periodo(unittest.TestCase):
    def dias(self, texto, now=AGORA):
        a, b, resto = hist._periodo(texto, now)
        return (datetime.datetime.fromtimestamp(a).date().isoformat(),
                datetime.datetime.fromtimestamp(b).date().isoformat(), resto)

    def test_ontem_e_anteontem(self):
        self.assertEqual(self.dias("o que vimos ontem?")[:2], ("2026-11-04", "2026-11-05"))
        self.assertEqual(self.dias("e anteontem?")[:2], ("2026-11-03", "2026-11-04"))
        self.assertEqual(self.dias("e antes de ontem?")[:2], ("2026-11-03", "2026-11-04"))

    def test_semana_passada_vai_de_segunda_a_domingo(self):
        self.assertEqual(self.dias("na semana passada")[:2], ("2026-10-26", "2026-11-02"))

    def test_mes_passado_com_e_sem_acento(self):
        self.assertEqual(self.dias("no mês passado")[:2], ("2026-10-01", "2026-11-01"))
        self.assertEqual(self.dias("no mes passado")[:2], ("2026-10-01", "2026-11-01"))

    def test_mes_passado_em_janeiro_e_dezembro_do_ano_anterior(self):
        self.assertEqual(self.dias("mês passado", datetime.datetime(2027, 1, 15))[:2], ("2026-12-01", "2027-01-01"))

    def test_a_data_sai_da_busca(self):
        self.assertEqual(self.dias("a receita de bolo de ontem")[2], "a receita de bolo")

    def test_sem_data(self):
        for t in ("a receita de bolo", "o passado da semana", "ontemporaneo", ""):
            self.assertIsNone(hist._periodo(t, AGORA), t)


@unittest.skipUnless(TEM_DEPS, "faltam numpy/pydantic/requests")
class BuscaPorData(Base):
    def test_ontem_so_traz_ontem(self):
        self.par("velha", "receita de bolo de cenoura", quando=ts(2026, 10, 20, 9, 0))
        self.par("nova", "receita de bolo de fuba", quando=ts(2026, 11, 4, 9, 0))
        self.indexa()
        t = self.textos("a receita de bolo de ontem")
        self.assertIn("fuba", t)
        self.assertNotIn("cenoura", t)

    def test_data_sem_nada_naquele_dia_nao_traz_o_que_e_de_outro_dia(self):
        self.par("velha", "receita de bolo de cenoura", quando=ts(2026, 10, 20, 9, 0))
        self.indexa()
        self.assertEqual(self.busca("a receita de bolo de ontem"), ([], []))

    def test_o_que_conversamos_ontem_traz_mesmo_sem_assunto(self):
        self.par("a", "preciso trocar o pneu do carro", quando=ts(2026, 11, 4, 9, 0))
        self.par("b", "qual imposto pago este ano", quando=ts(2026, 11, 4, 15, 0))
        self.par("c", "plantas para o jardim", quando=ts(2026, 10, 1, 9, 0))
        self.indexa()
        chunks, srcs = self.busca("o que conversamos ontem?")
        self.assertEqual(srcs, ["b", "a"])  # do mais novo ao mais velho
        self.assertNotIn("jardim", "\n".join(t for _l, t in chunks))

    def test_data_sem_pedido_de_lembrar_nao_despeja_o_dia_inteiro(self):
        self.par("a", "preciso trocar o pneu do carro", quando=ts(2026, 11, 4, 9, 0))
        self.indexa()
        self.assertEqual(self.busca("como foi o jogo do flamengo ontem"), ([], []))

    def test_a_palavra_ontem_nao_conta_como_assunto(self):
        self.par("a", "ontem fui ao mercado comprar arroz", quando=ts(2026, 10, 1, 9, 0))
        self.indexa()
        self.assertEqual(self.busca("ontem mercado"), ([], []))

    def test_data_em_milissegundos_tambem_filtra(self):
        self.par("ms", "receita de bolo de milho", quando=ts(2026, 11, 4, 9, 0) * 1000)
        self.indexa()
        self.assertIn("milho", self.textos("receita de bolo de ontem"))

    def test_palavra_chave_antiga_nao_toma_as_vagas_da_data(self):
        for i in range(30):
            self.par(f"v{i}", f"receita de bolo numero {i}", quando=ts(2026, 9, 1, 9, 0) + i)
        self.par("nova", "receita de bolo de fuba", quando=ts(2026, 11, 4, 9, 0))
        self.indexa()
        self.f._embed = lambda _t: None
        self.assertIn("fuba", self.textos("receita bolo ontem"))


@unittest.skipUnless(TEM_DEPS, "faltam numpy/pydantic/requests")
class UmTrechoPorConversa(Base):
    def test_tres_dialogos_da_mesma_conversa_viram_um(self):
        for texto in ("receita de bolo um", "receita de bolo dois", "receita de bolo tres"):
            self.par("a", texto)
        self.indexa()
        chunks, srcs = self.busca("receita de bolo")
        self.assertEqual((srcs, len(chunks)), (["a"], 1))

    def test_as_vagas_vao_para_conversas_diferentes(self):
        for texto in ("receita de bolo um", "receita de bolo dois", "receita de bolo tres"):
            self.par("a", texto)
        self.par("b", "receita de bolo de fuba")
        self.par("c", "receita de bolo de milho")
        self.indexa()
        self.assertEqual(sorted(self.busca("receita de bolo")[1]), ["a", "b", "c"])

    def test_conversa_atual_continua_de_fora(self):
        self.par("a", "receita de bolo de fuba")
        self.indexa()
        self.assertEqual(self.busca("receita de bolo", exclude_chat="a"), ([], []))

    def test_outra_pessoa_continua_de_fora(self):
        self.par("a", "receita de bolo de fuba", user="u2")
        self.indexa()
        self.assertEqual(self.busca("receita de bolo"), ([], []))


@unittest.skipUnless(TEM_DEPS, "faltam numpy/pydantic/requests")
class Vizinhos(Base):
    def preparar(self):
        self.par("a", "primeiro vamos falar do orcamento geral", quando=ts(2026, 11, 1, 9, 0))
        self.par("a", "receita de bolo de fuba cremoso", quando=ts(2026, 11, 1, 10, 0))
        self.par("a", "e depois separei os ingredientes todos", quando=ts(2026, 11, 1, 11, 0))
        self.par("b", "preciso de uma receita de bolo simples", quando=ts(2026, 11, 2, 9, 0))
        self.par("b", "agora outra coisa bem diferente aqui", quando=ts(2026, 11, 2, 10, 0))

    def test_melhor_resultado_traz_antes_e_depois_em_ordem(self):
        self.preparar()
        self.indexa()
        chunks, srcs = self.busca("receita bolo fuba")
        self.assertEqual(srcs[0], "a")
        t = chunks[0][1]
        self.assertLess(t.index("orcamento"), t.index("fuba"))
        self.assertLess(t.index("fuba"), t.index("ingredientes"))

    def test_os_outros_resultados_nao_trazem(self):
        self.preparar()
        self.indexa()
        chunks, srcs = self.busca("receita bolo fuba")
        self.assertEqual(srcs, ["a", "b"])
        self.assertNotIn("outra coisa", chunks[1][1])

    def test_vizinho_nao_toma_o_lugar_de_outra_conversa(self):
        self.preparar()
        self.indexa()
        self.f.valves.MAX_CONTEXT_CHARS = 130
        self.assertEqual(self.busca("receita bolo fuba")[1], ["a", "b"])

    def test_limite_total_vale_com_os_vizinhos(self):
        self.preparar()
        self.indexa()
        self.f.valves.MAX_CONTEXT_CHARS = 200
        total = sum(len(t.replace("\n\n", "")) for _l, t in self.busca("receita bolo fuba")[0])
        self.assertLessEqual(total, 200)

    def test_vizinho_apagado_nao_aparece(self):
        self.preparar()
        self.indexa()
        self.apaga_msg("a-q1")
        t = self.textos("receita bolo fuba")
        self.assertNotIn("orcamento", t)
        self.assertIn("ingredientes", t)


@unittest.skipUnless(TEM_DEPS, "faltam numpy/pydantic/requests")
class PalavraSozinha(Base):
    def test_uma_palavra_sem_similaridade_nao_qualifica(self):
        self.par("a", "comprei uma mesa para a sala nova")
        self.indexa()
        self.assertEqual(self.busca("mesa"), ([], []))
        self.assertEqual(self.busca("qual a melhor mesa de sinuca profissional"), ([], []))

    def test_duas_palavras_qualificam_sem_similaridade(self):
        self.par("a", "comprei uma mesa para a sala nova")
        self.indexa()
        self.assertEqual(self.busca("mesa sala")[1], ["a"])

    def test_duas_palavras_valem_sem_acento(self):
        self.par("a", "o relatório do balanço saiu hoje de manhã")
        self.indexa()
        self.assertEqual(self.busca("relatorio balanco")[1], ["a"])

    def test_a_mesma_palavra_repetida_nao_conta_como_duas(self):
        self.par("a", "mesa mesa mesa para a sala")
        self.indexa()
        self.assertEqual(self.busca("mesa mesa"), ([], []))

    def test_uma_palavra_com_similaridade_qualifica(self):
        self.par("a", "marquei o dentista para terça")
        self.indexa()
        self.assertEqual(self.busca("dentista")[1], ["a"])

    def test_sem_embeddings_uma_palavra_tambem_nao_qualifica(self):
        self.par("a", "marquei o dentista para terça")
        self.indexa()
        self.f._embed = lambda _t: None
        self.assertEqual(self.busca("dentista"), ([], []))


@unittest.skipUnless(TEM_DEPS, "faltam numpy/pydantic/requests")
class ConversaApagada(Base):
    def purge(self):
        return idx.purge_deleted(self.h, self.webui, log=lambda *_: None)

    def test_conversa_apagada_sai_do_indice_e_da_busca_de_palavras(self):
        self.par("a", "receita secreta de bolo da vovo")
        self.par("b", "receita de bolo de fuba")
        self.indexa()
        self.apaga_chat("a")
        self.assertEqual(self.purge(), 1)
        self.assertEqual(self.indexados(), 1)
        self.assertEqual(self.fts("secreta"), 0)
        self.assertEqual(self.busca("receita de bolo")[1], ["b"])

    def test_apagar_so_a_resposta_tira_o_dialogo(self):
        _q, a = self.par("a", "como declarar o imposto", "Resposta com dado sensivel")
        self.indexa()
        self.apaga_msg(a)
        self.assertEqual(self.purge(), 1)
        self.assertEqual((self.indexados(), self.fts("sensivel")), (0, 0))

    def test_apagar_so_a_pergunta_tira_o_dialogo(self):
        q, _a = self.par("a", "como declarar o imposto", "Resposta com dado sensivel")
        self.indexa()
        self.apaga_msg(q)
        self.assertEqual(self.purge(), 1)

    def test_o_resto_nao_e_tocado(self):
        self.par("a", "receita de bolo de fuba")
        self.par("b", "receita de bolo de milho", user="u2")
        self.indexa()
        self.assertEqual(self.purge(), 0)
        self.assertEqual(self.indexados(), 2)

    def test_apagada_nao_volta_na_indexacao_seguinte(self):
        self.par("a", "receita de bolo de fuba")
        self.par("b", "receita de bolo de milho")
        self.indexa()
        self.apaga_chat("a")
        self.purge()
        self.par("b", "mais uma receita de bolo")
        self.indexa()
        self.assertEqual(self.h.execute("SELECT COUNT(*) FROM dialogues WHERE chat_id='a'").fetchone()[0], 0)

    def test_com_o_ollama_fora_do_ar_a_limpeza_roda_e_a_indexacao_nao(self):
        self.par("a", "receita de bolo de fuba")
        self.indexa()
        self.apaga_chat("a")
        with mock.patch.object(idx, "embed_ready", return_value=False), \
                mock.patch.object(idx, "index_once") as indexa:
            idx.cycle(self.h, self.webui, log=lambda *_: None)
        self.assertEqual(self.indexados(), 0)
        indexa.assert_not_called()

    def test_ciclo_com_ollama_no_ar_limpa_e_indexa(self):
        self.par("a", "receita de bolo de fuba")
        self.indexa()
        self.apaga_chat("a")
        self.par("b", "receita de bolo de milho")
        with mock.patch.object(idx, "embed_ready", return_value=True):
            idx.cycle(self.h, self.webui, log=lambda *_: None)
        self.assertEqual([r[0] for r in self.h.execute("SELECT chat_id FROM dialogues")], ["b"])

    def test_erro_na_limpeza_nao_para_a_indexacao(self):
        self.par("a", "receita de bolo de fuba")
        with mock.patch.object(idx, "embed_ready", return_value=True), \
                mock.patch.object(idx, "purge_deleted", side_effect=sqlite3.OperationalError("travado")):
            idx.cycle(self.h, self.webui, log=lambda *_: None)
        self.assertEqual(self.indexados(), 1)

    def test_filtro_nao_traz_apagada_mesmo_antes_da_limpeza(self):
        self.par("a", "receita secreta de bolo da vovo")
        self.indexa()
        self.apaga_chat("a")
        self.assertEqual(self.busca("receita de bolo"), ([], []))  # sem purge: indexador parado

    def test_filtro_nao_traz_resposta_apagada_antes_da_limpeza(self):
        _q, a = self.par("a", "receita de bolo", "Segredo da vovo")
        self.indexa()
        self.apaga_msg(a)
        self.assertEqual(self.busca("receita de bolo"), ([], []))

    def test_apagada_cede_a_vaga_para_a_proxima(self):
        self.par("a", "receita de bolo de fuba")
        self.par("b", "receita de bolo de milho")
        self.indexa()
        self.apaga_chat("a")
        self.assertEqual(self.busca("receita de bolo")[1], ["b"])

    def test_sem_conseguir_conferir_nao_injeta_nada(self):
        self.par("a", "receita de bolo de fuba")
        self.indexa()
        self.w.close()
        os.remove(self.webui)
        self.assertEqual(self.busca("receita de bolo"), ([], []))

    def test_filtro_com_indice_em_cache_ve_a_limpeza(self):
        self.par("a", "receita de bolo de fuba")
        self.par("b", "receita de bolo de milho")
        self.indexa()
        self.busca("receita de bolo")  # enche o cache
        self.apaga_chat("a")
        self.purge()
        self.assertEqual(self.busca("receita de bolo")[1], ["b"])
        self.assertNotIn("a", hist._CACHE["chats"])

    def test_inlet_nao_injeta_a_conversa_apagada(self):
        import asyncio
        self.par("a", "receita secreta de bolo da vovo")
        self.indexa()
        self.apaga_chat("a")
        body = {"messages": [{"role": "user", "content": "receita de bolo"}]}
        out = asyncio.run(self.f.inlet(body, {"id": "u1"}))
        self.assertEqual(len(out["messages"]), 1)

    def test_o_texto_some_do_arquivo_do_banco(self):
        self.par("a", "palavrasecretaunica do cliente", "outrasecretaunica na resposta")
        self.indexa()
        self.apaga_chat("a")
        self.purge()
        self.h.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for nome in os.listdir(self.tmp):
            if nome.startswith("nous_history"):
                with open(os.path.join(self.tmp, nome), "rb") as f:
                    dados = f.read()
                self.assertNotIn(b"secretaunica", dados, nome)

    def test_sem_a_tabela_nao_apaga_nada(self):
        self.par("a", "receita de bolo de fuba")
        self.indexa()
        self.w.execute("DROP TABLE chat_message")
        self.w.commit()
        self.assertEqual(self.purge(), 0)
        self.assertEqual(self.indexados(), 1)

    def test_sem_o_webui_db_nao_apaga_nada(self):
        self.par("a", "receita de bolo de fuba")
        self.indexa()
        self.w.close()
        os.remove(self.webui)
        self.assertEqual(self.purge(), 0)
        self.assertEqual(self.indexados(), 1)

    def test_apagou_tudo_o_indice_esvazia(self):
        self.par("a", "receita de bolo de fuba")
        self.par("b", "receita de bolo de milho")
        self.indexa()
        self.w.execute("DELETE FROM chat_message")
        self.w.commit()
        self.assertEqual(self.purge(), 2)


@unittest.skipUnless(TEM_DEPS, "faltam numpy/pydantic/requests")
class IndiceAntigo(Base):
    """Indice de antes do asst_id: a resposta pode ter sido apagada antes da atualizacao."""

    def envelhece(self):
        self.h.execute("UPDATE dialogues SET asst_id=NULL")
        self.h.commit()

    def purge(self):
        return idx.purge_deleted(self.h, self.webui, log=lambda *_: None)

    def test_resposta_que_ainda_existe_ganha_o_id(self):
        _q, a = self.par("a", "como declarar o imposto", "Pelo programa da Receita")
        self.indexa()
        self.envelhece()
        self.assertEqual(self.purge(), 0)
        self.assertEqual(self.h.execute("SELECT asst_id FROM dialogues").fetchone()[0], a)

    def test_resposta_apagada_antes_da_atualizacao_sai(self):
        _q, a = self.par("a", "como declarar o imposto", "Resposta com dado sensivel")
        self.indexa()
        self.envelhece()
        self.apaga_msg(a)
        self.assertEqual(self.purge(), 1)
        self.assertEqual(self.fts("sensivel"), 0)

    def test_resposta_trocada_por_outra_sai(self):
        _q, a = self.par("a", "como declarar o imposto", "Resposta com dado sensivel")
        self.indexa()
        self.envelhece()
        self.apaga_msg(a)
        self.w.execute("INSERT INTO chat_message VALUES ('a-a9','a','u1','assistant','Outra resposta',NULL,?)",
                       (ts(2026, 11, 2, 9, 0),))
        self.w.commit()
        self.assertEqual(self.purge(), 1)

    def test_banco_sem_a_coluna_ganha_ao_abrir_e_o_filtro_aguenta_antes_disso(self):
        self.par("a", "receita de bolo de fuba")
        self.indexa()
        self.h.close()
        db = os.path.join(self.tmp, "nous_history.sqlite3")
        cx = sqlite3.connect(db)
        cx.execute("ALTER TABLE dialogues DROP COLUMN asst_id")
        cx.commit()
        cx.close()
        self.assertEqual(self.busca("receita de bolo")[1], ["a"])
        self.h = idx.open_hist(db)
        self.addCleanup(self.h.close)
        self.assertEqual(self.h.execute("SELECT asst_id FROM dialogues").fetchone(), (None,))


if __name__ == "__main__":
    unittest.main()
