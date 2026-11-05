# -*- coding: utf-8 -*-
"""
Testes das tarefas agendadas: nova tentativa com o modelo fora do ar, execucoes
perdidas, "so' avisar quando importa", tarefa criada pelo chat e ntfy. Sem Ollama de
verdade: "fora do ar" e' uma porta fechada e as respostas do modelo sao de mentira.

    python -m unittest discover -s agenda/tests -v
"""
import asyncio
import http.server
import json
import os
import shutil
import socket
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["NOUS_NO_TOAST"] = "1"

try:
    import requests  # noqa: E402
    import agenda_db as db  # noqa: E402
    import agenda_tasks as tasks  # noqa: E402
    import nous_agenda_api as api  # noqa: E402
    import nous_agenda as chat  # noqa: E402
    from aiohttp.test_utils import TestClient, TestServer  # noqa: E402
    HAVE_DEPS = True
except Exception:  # pragma: no cover
    HAVE_DEPS = False

UID = "u1"


def ts(*a):
    return db.to_ts(datetime(*a))


def porta_fechada():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Resposta:
    """Resposta do /api/generate."""

    def __init__(self, texto="", status=200):
        self.texto, self.status_code = texto, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} erro")

    def json(self):
        return {"response": self.texto}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nous-tarefas-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.data_antes = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self.tmp
        self.addCleanup(self._volta_data)
        self.cx = db.connect()
        self.addCleanup(self.cx.close)
        self.agora = ts(2026, 11, 5, 8, 0)
        p = mock.patch.object(db, "now", lambda: self.agora)
        p.start()
        self.addCleanup(p.stop)
        urls = (tasks.OLLAMA_URL, tasks.EMAIL_URL)
        self.addCleanup(lambda: (setattr(tasks, "OLLAMA_URL", urls[0]), setattr(tasks, "EMAIL_URL", urls[1])))
        tasks.OLLAMA_URL = f"http://127.0.0.1:{porta_fechada()}"
        tasks.EMAIL_URL = f"http://127.0.0.1:{porta_fechada()}"
        g = mock.patch.object(tasks, "local_model", lambda: "qwen3:4b")  # porta fechada demora 2 s no Windows
        g.start()
        self.addCleanup(g.stop)

    def _volta_data(self):
        if self.data_antes is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self.data_antes

    def tarefa(self, schedule="diario 08:00", kind="pergunta", prompt="oi", next_run=None, **extra):
        """Cria a tarefa um dia antes, para o horario de teste ja' ter vencido."""
        guarda = self.agora
        self.agora = ts(2026, 1, 1, 0, 0)
        t = tasks.task_save(self.cx, UID, {"name": "Bom dia", "kind": kind, "prompt": prompt,
                                           "schedule": schedule, **extra})
        self.agora = guarda
        self.set(t["id"], next_run=guarda if next_run is None else next_run)
        return t["id"]

    def set(self, tid, **campos):
        sets = ", ".join(f"{k}=?" for k in campos)
        self.cx.execute(f"UPDATE tasks SET {sets} WHERE id=?", (*campos.values(), tid))
        self.cx.commit()

    def row(self, tid):
        return dict(self.cx.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())

    def notifs(self):
        return [dict(r) for r in self.cx.execute("SELECT * FROM notif ORDER BY id")]

    def notas(self):
        return [dict(r) for r in self.cx.execute("SELECT * FROM notes")]

    def roda_vencidas(self):
        """O que o relogio faz: pega as vencidas e executa como agendadas."""
        return [tasks.execute(self.cx, t, agendada=True)[0] for t in tasks.due_tasks(self.cx)]

    def modelo(self, *respostas):
        """Modelo de mentira: uma resposta por chamada (Exception = levanta)."""
        p = mock.patch.object(tasks.requests, "post", side_effect=list(respostas))
        fake = p.start()
        self.addCleanup(p.stop)
        return fake


@unittest.skipUnless(HAVE_DEPS, "faltam dependencias")
class NovaTentativa(Base):
    def test_ollama_fora_marca_para_5_min_sem_avisar_ainda(self):
        tid = self.tarefa()
        self.assertEqual(self.roda_vencidas(), ["tentando"])
        r = self.row(tid)
        self.assertEqual(r["next_run"], self.agora + 300)
        self.assertEqual((r["retry_count"], r["last_status"]), (1, "tentando"))
        self.assertIn("nao esta no ar", r["last_error"])
        self.assertEqual((self.notifs(), self.notas()), ([], []))

    def test_escada_5_15_30_e_depois_falha_visivel(self):
        tid = self.tarefa()
        inicio = self.agora
        for espera in (300, 900, 1800):
            self.assertEqual(self.roda_vencidas(), ["tentando"])
            self.assertEqual(self.row(tid)["next_run"], self.agora + espera)
            self.assertEqual(self.notifs(), [])
            self.agora += espera
        self.assertEqual(self.roda_vencidas(), ["erro"])
        r = self.row(tid)
        self.assertEqual((r["last_status"], r["retry_count"]), ("erro", 0))
        self.assertIn("nao esta no ar", r["last_error"])
        avisos = self.notifs()
        self.assertEqual(len(avisos), 1)
        self.assertIn("nao pode ser concluida", avisos[0]["body"])
        self.assertIn("3 vez", avisos[0]["body"])
        self.assertEqual(r["next_run"], inicio + 86400)  # segue no horario normal

    def test_ollama_voltou_na_segunda_tentativa(self):
        tid = self.tarefa()
        self.roda_vencidas()
        self.agora += 300
        self.modelo(Resposta("Bom dia!"))
        self.assertEqual(self.roda_vencidas(), ["ok"])
        r = self.row(tid)
        self.assertEqual((r["retry_count"], r["last_status"], r["last_error"]), (0, "ok", None))
        self.assertEqual(r["next_run"], ts(2026, 11, 6, 8, 0))
        self.assertEqual(self.notas()[0]["body"], "Bom dia!")

    def test_nao_repete_se_alguma_chamada_ja_foi_respondida(self):
        tid = self.tarefa()
        self.modelo(Resposta("primeira"), requests.exceptions.ConnectionError("caiu"))

        def duas_chamadas(_cx, _t, _c=None):
            tasks.llm("a")
            return tasks.llm("b")
        with mock.patch.object(tasks, "run_task", duas_chamadas):
            self.assertEqual(self.roda_vencidas(), ["erro"])
        self.assertEqual(self.row(tid)["retry_count"], 0)
        self.assertEqual(len(self.notifs()), 1)

    def test_email_fora_do_ar_nao_e_modelo_fora_do_ar(self):
        tid = self.tarefa(kind="emails", prompt="")
        self.assertEqual(self.roda_vencidas(), ["erro"])
        self.assertEqual(self.row(tid)["retry_count"], 0)

    def test_erro_http_do_modelo_nao_repete(self):
        tid = self.tarefa()
        self.modelo(Resposta(status=500))
        self.assertEqual(self.roda_vencidas(), ["erro"])
        self.assertEqual(self.row(tid)["next_run"], ts(2026, 11, 6, 8, 0))

    def test_timeout_de_resposta_nao_conta_como_falha_de_conexao(self):
        tid = self.tarefa()
        self.modelo(requests.exceptions.ReadTimeout("demorou"))
        self.assertEqual(self.roda_vencidas(), ["erro"])
        self.assertEqual(self.row(tid)["retry_count"], 0)

    def test_pesquisa_com_ollama_fora_tenta_de_novo_em_vez_de_nota_com_trechos_soltos(self):
        tid = self.tarefa(kind="pesquisa", prompt="novidades")
        self.assertEqual(self.roda_vencidas(), ["tentando"])
        self.assertEqual(self.row(tid)["retry_count"], 1)
        self.assertEqual(self.notas(), [])

    def test_rodar_agora_falha_na_hora_e_nao_mexe_no_horario(self):
        tid = self.tarefa(next_run=ts(2026, 11, 6, 8, 0))
        status, _ = tasks.execute(self.cx, tasks.task_get(self.cx, UID, tid))
        self.assertEqual(status, "erro")
        r = self.row(tid)
        self.assertEqual((r["retry_count"], r["next_run"]), (0, ts(2026, 11, 6, 8, 0)))

    def test_rodar_agora_com_sucesso_cancela_a_tentativa_marcada(self):
        tid = self.tarefa()
        self.roda_vencidas()
        self.modelo(Resposta("ok"))
        self.assertEqual(tasks.execute(self.cx, tasks.task_get(self.cx, UID, tid))[0], "ok")
        r = self.row(tid)
        self.assertEqual((r["retry_count"], r["next_run"]), (0, ts(2026, 11, 6, 8, 0)))

    def test_rodar_agora_que_falha_nao_quebra_a_escada(self):
        tid = self.tarefa()
        self.roda_vencidas()
        marcada = self.row(tid)["next_run"]
        tasks.execute(self.cx, tasks.task_get(self.cx, UID, tid))
        r = self.row(tid)
        self.assertEqual((r["retry_count"], r["next_run"]), (1, marcada))

    def test_etapa_de_cadeia_nao_repete_porque_perderia_o_contexto(self):
        tid = self.tarefa()
        t = tasks.task_get(self.cx, UID, tid)
        self.assertEqual(tasks.execute(self.cx, t, contexto="anterior", agendada=True)[0], "erro")
        self.assertEqual(self.row(tid)["retry_count"], 0)

    def test_tarefa_de_uma_vez_tambem_tenta_e_depois_desliga(self):
        tid = self.tarefa(schedule="uma_vez 2026-11-05T08:00")
        for espera in (300, 900, 1800):
            self.assertEqual(self.roda_vencidas(), ["tentando"])
            self.assertEqual(self.row(tid)["enabled"], 1)
            self.agora += espera
        self.assertEqual(self.roda_vencidas(), ["erro"])
        r = self.row(tid)
        self.assertEqual((r["enabled"], r["next_run"]), (0, None))

    def test_nao_marca_tentativa_depois_do_proximo_horario_normal(self):
        tid = self.tarefa(next_run=ts(2026, 11, 5, 7, 58))
        self.agora = ts(2026, 11, 5, 7, 58)
        self.assertEqual(self.roda_vencidas(), ["erro"])
        self.assertEqual(self.row(tid)["next_run"], ts(2026, 11, 5, 8, 0))

    def test_pausada_enquanto_rodava_nao_volta_a_ligar(self):
        tid = self.tarefa()
        t = tasks.due_tasks(self.cx)[0]
        self.set(tid, enabled=0)
        self.assertEqual(tasks.execute(self.cx, t, agendada=True)[0], "erro")
        self.assertEqual(self.row(tid)["enabled"], 0)

    def test_editar_a_tarefa_encerra_as_tentativas(self):
        tid = self.tarefa()
        self.roda_vencidas()
        tasks.task_save(self.cx, UID, {**tasks.task_get(self.cx, UID, tid), "enabled": False}, tid=tid)
        r = self.row(tid)
        self.assertEqual((r["retry_count"], r["last_status"]), (0, None))


@unittest.skipUnless(HAVE_DEPS, "faltam dependencias")
class ExecucoesPerdidas(Base):
    def vencidas(self):
        return [t["id"] for t in tasks.due_tasks(self.cx)]

    def test_bom_dia_das_8h_nao_roda_as_23h(self):
        tid = self.tarefa(next_run=ts(2026, 11, 5, 8, 0))
        self.agora = ts(2026, 11, 5, 23, 0)
        self.assertEqual(self.vencidas(), [])
        r = self.row(tid)
        self.assertEqual(r["next_run"], ts(2026, 11, 6, 8, 0))
        self.assertEqual((r["last_status"], r["last_run"]), ("pulada", None))
        self.assertIn("05/11 às 08:00", r["last_error"])
        self.assertEqual(self.notifs(), [])  # volta amanha: so' fica no painel

    def test_ligou_as_9h30_roda_uma_vez(self):
        tid = self.tarefa(next_run=ts(2026, 11, 5, 8, 0))
        self.agora = ts(2026, 11, 5, 9, 30)
        self.assertEqual(self.vencidas(), [tid])
        self.assertEqual(self.vencidas(), [])
        self.assertEqual(self.row(tid)["next_run"], ts(2026, 11, 6, 8, 0))

    def test_tres_dias_desligado_colapsa_em_uma_execucao(self):
        tid = self.tarefa(next_run=ts(2026, 11, 2, 8, 0))
        self.agora = ts(2026, 11, 5, 8, 30)
        self.assertEqual(self.vencidas(), [tid])
        self.assertEqual(self.vencidas(), [])
        self.assertEqual(self.row(tid)["next_run"], ts(2026, 11, 6, 8, 0))

    def test_tres_dias_desligado_e_ligou_a_noite_nao_roda(self):
        tid = self.tarefa(next_run=ts(2026, 11, 2, 8, 0))
        self.agora = ts(2026, 11, 5, 23, 0)
        self.assertEqual(self.vencidas(), [])
        self.assertEqual(self.row(tid)["next_run"], ts(2026, 11, 6, 8, 0))

    def test_limite_exato_da_janela(self):
        tid = self.tarefa(next_run=ts(2026, 11, 5, 8, 0))
        self.agora = ts(2026, 11, 5, 10, 0)
        self.assertEqual(self.vencidas(), [tid])
        tid2 = self.tarefa(next_run=ts(2026, 11, 5, 8, 0))
        self.agora = ts(2026, 11, 5, 10, 0) + 1
        self.assertEqual(self.vencidas(), [])
        self.assertEqual(self.row(tid2)["last_status"], "pulada")

    def test_janela_e_metade_do_periodo_entre_2_min_e_2_h(self):
        slot = ts(2026, 11, 5, 8, 0)
        for periodo, janela in ((60, 120), (1800, 900), (7200, 3600), (86400, 7200), (7 * 86400, 7200)):
            with mock.patch.object(tasks, "next_run", lambda _s, a, p=periodo: a + p):
                self.assertEqual(tasks.catchup_window("diario 08:00", slot), janela, periodo)
        self.assertEqual(tasks.catchup_window("diario 08:00", slot), 7200)

    def test_sexta_perdida_nao_vira_sabado_em_dias_uteis(self):
        tid = self.tarefa(schedule="dias_uteis 08:00", next_run=ts(2026, 11, 6, 8, 0))
        self.agora = ts(2026, 11, 7, 8, 30)  # sabado
        self.assertEqual(self.vencidas(), [])
        self.assertEqual(self.row(tid)["next_run"], ts(2026, 11, 9, 8, 0))

    def test_de_uma_vez_dentro_da_janela_roda(self):
        tid = self.tarefa(schedule="uma_vez 2026-11-05T08:00", next_run=ts(2026, 11, 5, 8, 0))
        self.agora = ts(2026, 11, 5, 9, 0)
        self.assertEqual(self.vencidas(), [tid])

    def test_de_uma_vez_fora_da_janela_desliga_e_avisa(self):
        tid = self.tarefa(schedule="uma_vez 2026-11-05T08:00", next_run=ts(2026, 11, 5, 8, 0))
        self.agora = ts(2026, 11, 5, 23, 0)
        self.assertEqual(self.vencidas(), [])
        r = self.row(tid)
        self.assertEqual((r["enabled"], r["next_run"], r["last_status"]), (0, None, "pulada"))
        self.assertIn("Tarefa não rodou", self.notifs()[0]["title"])

    def test_tentativa_atrasada_por_adiamentos_mede_do_horario_dela(self):
        tid = self.tarefa(next_run=ts(2026, 11, 5, 10, 40))
        self.set(tid, retry_count=2)
        self.agora = ts(2026, 11, 5, 10, 41)  # 2h41 depois das 8h, mas 1 min depois do marcado
        self.assertEqual(self.vencidas(), [tid])

    def test_pc_desligou_no_meio_das_tentativas_registra_a_falha(self):
        tid = self.tarefa(next_run=ts(2026, 11, 5, 8, 20))
        self.set(tid, retry_count=2, last_status="tentando")
        self.agora = ts(2026, 11, 5, 23, 0)
        self.assertEqual(self.vencidas(), [])
        r = self.row(tid)
        self.assertEqual((r["last_status"], r["retry_count"]), ("erro", 0))
        self.assertEqual(len(self.notifs()), 1)

    def test_lembrete_atrasado_continua_avisando(self):
        db.note_create(self.cx, UID, {"title": "Pagar a luz", "remind_at": ts(2026, 11, 5, 8, 0)})
        self.agora = ts(2026, 11, 5, 23, 0)
        self.assertEqual([f[1] for f in db.due_reminders(self.cx)], ["Lembrete: Pagar a luz"])


@unittest.skipUnless(HAVE_DEPS, "faltam dependencias")
class SoAvisarQuandoImporta(Base):
    def roda(self, tid):
        return tasks.execute(self.cx, tasks.task_get(self.cx, UID, tid), agendada=True)[0]

    def test_mudou_primeira_vez_avisa_igual_fica_quieto_diferente_avisa(self):
        tid = self.tarefa(aviso="mudou")
        self.modelo(Resposta("Dolar a 5,10"), Resposta("  dolar a 5,10 \n"), Resposta("Dolar a 5,20"))
        self.assertEqual(self.roda(tid), "ok")
        self.assertEqual(self.roda(tid), "sem_novidade")
        self.assertEqual((len(self.notas()), len(self.notifs())), (1, 1))
        self.assertEqual(self.row(tid)["last_status"], "sem_novidade")
        self.assertEqual(self.roda(tid), "ok")
        self.assertEqual((len(self.notas()), len(self.notifs())), (2, 2))

    def test_sem_a_opcao_resultado_igual_avisa_sempre(self):
        tid = self.tarefa()
        self.modelo(Resposta("igual"), Resposta("igual"))
        self.assertEqual((self.roda(tid), self.roda(tid)), ("ok", "ok"))

    def test_resultado_igual_nao_manda_email(self):
        tid = self.tarefa(aviso="mudou", email=True)
        self.modelo(Resposta("igual"), Resposta("igual"))
        with mock.patch.object(tasks, "send_email_to_self") as envia:
            self.roda(tid)
            self.roda(tid)
        self.assertEqual(envia.call_count, 1)

    def test_falha_no_meio_nao_apaga_o_ultimo_resultado(self):
        tid = self.tarefa(aviso="mudou")
        self.modelo(Resposta("igual"), Resposta(status=500), Resposta("igual"))
        self.assertEqual([self.roda(tid) for _ in range(3)], ["ok", "erro", "sem_novidade"])

    def test_link_do_relatorio_muda_mas_nao_e_novidade(self):
        a = "Texto\n\nRelatorio visual: http://127.0.0.1:8990/research/view?id=aaa"
        b = "Texto\n\nRelatorio visual: http://127.0.0.1:8990/research/view?id=bbb"
        self.assertEqual(tasks.result_hash(a), tasks.result_hash(b))
        self.assertNotEqual(tasks.result_hash(a), tasks.result_hash("Outro\n\n" + a))

    def test_mudou_pede_resposta_estavel_ao_modelo(self):
        tid = self.tarefa(aviso="mudou")
        fake = self.modelo(Resposta("x"))
        self.roda(tid)
        corpo = fake.call_args.kwargs["json"]
        self.assertEqual(corpo["options"]["temperature"], 0)
        self.assertNotRegex(corpo["prompt"], r"\d\d:\d\d")
        self.assertNotIn("format", corpo)

    def test_modelo_usa_format_do_ollama_e_nao_sentinela(self):
        tid = self.tarefa(aviso="modelo")
        fake = self.modelo(Resposta('{"avisar": false, "texto": "nada"}'))
        self.assertEqual(self.roda(tid), "sem_novidade")
        corpo = fake.call_args.kwargs["json"]
        self.assertEqual(corpo["format"], tasks.JSON_AVISO)
        self.assertIs(corpo["think"], False)
        self.assertEqual((self.notas(), self.notifs()), ([], []))

    def test_modelo_manda_avisar_a_nota_tem_o_texto_e_nao_o_json(self):
        tid = self.tarefa(aviso="modelo")
        self.modelo(Resposta('{"avisar": true, "texto": "Chegou boleto"}'))
        self.assertEqual(self.roda(tid), "ok")
        self.assertEqual(self.notas()[0]["body"], "Chegou boleto")

    def test_json_quebrado_avisa_com_o_texto_que_veio(self):
        tid = self.tarefa(aviso="modelo")
        self.modelo(Resposta("Tem um boleto vencendo hoje"))
        self.assertEqual(self.roda(tid), "ok")
        self.assertEqual(self.notas()[0]["body"], "Tem um boleto vencendo hoje")

    def test_json_cortado_avisa_mesmo_dizendo_false(self):
        tid = self.tarefa(aviso="modelo")
        self.modelo(Resposta('{"avisar": false, "texto": "Tem um bol'))
        self.assertEqual(self.roda(tid), "ok")
        self.assertEqual(self.notas()[0]["body"], "Tem um bol")

    def test_decisoes_estranhas_avisam(self):
        for bruto in ('{"avisar": "false", "texto": "t"}', '{"texto": "t"}', '{"avisar": 0, "texto": "t"}'):
            self.assertEqual(tasks.parse_decisao(bruto), (True, "t"), bruto)
        for bruto in ("", None, "[]", "{}", '{"avisar": true, "texto": ""}'):
            avisar, texto = tasks.parse_decisao(bruto)
            self.assertTrue(avisar, bruto)
            self.assertIn("sem texto", texto, bruto)

    def pesquisa(self, *respostas):
        tid = self.tarefa(kind="pesquisa", prompt="novidades", aviso="modelo")
        self.modelo(*respostas)
        falso = mock.MagicMock()
        falso.deep_research.return_value = {"report": "Relatorio completo", "sources": []}
        with mock.patch.dict(sys.modules, {"nous_search": mock.MagicMock(),
                                           "nous_search.deep_research": falso}), \
                mock.patch.object(tasks, "_modelo_no_ar", lambda: None):
            return self.roda(tid)

    def test_pesquisa_decide_numa_segunda_chamada_e_guarda_o_relatorio(self):
        self.assertEqual(self.pesquisa(Resposta('{"avisar": true, "texto": "curto"}')), "ok")
        self.assertEqual(self.notas()[0]["body"], "Relatorio completo")

    def test_pesquisa_sem_novidade_fica_quieta(self):
        self.assertEqual(self.pesquisa(Resposta('{"avisar": false, "texto": ""}')), "sem_novidade")

    def test_pesquisa_com_decisao_falhando_avisa(self):
        self.assertEqual(self.pesquisa(requests.exceptions.ConnectionError("caiu")), "ok")

    def test_opcao_invalida_e_recusada(self):
        with self.assertRaises(ValueError):
            self.tarefa(aviso="talvez")

    def test_quieta_nao_faz_toast_nem_ntfy_nem_segue_a_cadeia(self):
        seguinte = self.tarefa(next_run=ts(2027, 1, 1, 8, 0))
        tid = self.tarefa(aviso="modelo", then_task=seguinte)
        self.modelo(Resposta('{"avisar": false, "texto": ""}'))
        db.settings_set(self.cx, UID, {"ntfy_topico": "codigo-bem-comprido"})
        with mock.patch.object(api, "toast") as toast, mock.patch.object(api, "deliver") as deliver:
            api._run_task_sync(tasks.task_get(self.cx, UID, tid), None, True)
        self.assertEqual((toast.call_count, deliver.call_count), (0, 0))
        self.assertIsNone(self.row(seguinte)["last_run"])

    def test_tentando_nao_faz_toast_e_falha_final_faz(self):
        tid = self.tarefa()
        with mock.patch.object(api, "toast") as toast:
            api._run_task_sync(tasks.task_get(self.cx, UID, tid), None, True)
            self.assertEqual(toast.call_count, 0)
            self.set(tid, retry_count=3)
            api._run_task_sync(tasks.task_get(self.cx, UID, tid), None, True)
        self.assertEqual(toast.call_args.args[0], "Tarefa falhou: Bom dia")


@unittest.skipUnless(HAVE_DEPS, "faltam dependencias")
class TarefaPeloChat(unittest.TestCase):
    def setUp(self):
        self.agora = datetime(2026, 11, 5, 10, 0)  # quinta
        self.f = chat.Filter()
        self.posts = []

        def falso(method, path, **kw):
            self.posts.append((method, path, kw.get("json")))
            if path == "/tasks":
                return {"task": {"id": "t1", "name": kw["json"]["name"],
                                 "quando": tasks.describe(kw["json"]["schedule"])}}
            if path == "/notes":
                return {"note": {"id": "n1", "title": kw["json"]["title"], "body": "",
                                 "remind_at": kw["json"].get("remind_at")}}
            return {"ok": True}
        self.f._api = falso

    def aplica(self, msg, acao="tarefa", titulo="", repetir="nenhum"):
        d = {"acao": acao, "titulo": titulo, "detalhes": "", "repetir": repetir}
        return self.f._apply(d, UID, msg, now=self.agora)

    def criada(self):
        return [b for _m, p, b in self.posts if p == "/tasks"]

    def test_exemplo_do_pedido(self):
        r = self.aplica("todo dia às 8h me manda a agenda", titulo="Agenda do dia")
        (b,) = self.criada()
        self.assertEqual((b["schedule"], b["kind"], b["name"]), ("diario 08:00", "resumo_dia", "Agenda do dia"))
        self.assertIn('Tarefa criada: "Agenda do dia", todo dia as 08:00', r)
        self.assertIn("Confirme", r)

    def test_horario_vem_da_regra_mesmo_com_modelo_dizendo_outra_coisa(self):
        self.aplica("toda segunda às 7h30 pesquise novidades sobre energia solar", repetir="diario")
        (b,) = self.criada()
        self.assertEqual((b["schedule"], b["kind"]), ("semanal 1 07:30", "pesquisa"))
        self.assertEqual(b["prompt"], "pesquise novidades sobre energia solar")

    def test_agendas_lidas_por_regra(self):
        casos = {
            "todos os dias às 7h me dá um resumo dos e-mails": "diario 07:00",
            "diariamente às 9 da noite me manda a agenda": "diario 21:00",
            "de segunda a sexta às 18h resuma meus e-mails": "dias_uteis 18:00",
            "nos dias úteis às 8h me manda a agenda": "dias_uteis 08:00",
            "toda sexta às 17h me manda a agenda": "semanal 5 17:00",
            "todos os domingos às 20h me manda a agenda": "semanal 7 20:00",
            "toda semana às 10h me manda a agenda": "semanal 4 10:00",
            "todo dia 5 às 9h me manda a agenda": "mensal 5 09:00",
            "todo mês às 9h me manda a agenda": "mensal 5 09:00",
            "todo dia 8h me manda a agenda": "diario 08:00",
            "todo dia 8 horas me manda a agenda": "diario 08:00",
            "cria uma tarefa para amanhã às 8h: pesquisar preço de passagem": "uma_vez 2026-11-06T08:00",
        }
        for msg, esperado in casos.items():
            self.assertTrue(chat._is_task(msg), msg)
            self.assertEqual(chat._task_schedule(msg, self.agora), esperado, msg)
            tasks.parse_schedule(esperado)

    def test_tipos(self):
        casos = {
            "todo dia às 8h me manda a agenda": "resumo_dia",
            "todo dia às 8h me manda um bom dia": "resumo_dia",
            "todo dia às 18h resuma meus e-mails": "emails",
            "toda segunda às 9h me manda as notícias de IA": "pesquisa",
            "toda segunda às 9h pesquise a agenda 2030 da ONU": "pesquisa",
            "agenda uma tarefa para amanhã às 8h: resumir os e-mails": "emails",
            "todo dia às 8h me manda uma frase motivacional": "pergunta",
        }
        for msg, esperado in casos.items():
            self.assertEqual(chat._task_kind(msg), esperado, msg)

    def test_pedido_mantem_as_palavras_do_usuario(self):
        self.assertEqual(chat._task_prompt("todo dia às 8h pesquise as novidades de hoje"),
                         "pesquise as novidades de hoje")
        self.assertEqual(chat._task_prompt("cria uma tarefa para amanhã às 8h: pesquisar preço de passagem"),
                         "pesquisar preço de passagem")

    def test_sem_hora_nada_e_salvo_e_pergunta(self):
        r = self.aplica("todo dia me manda a agenda")
        self.assertEqual(self.criada(), [])
        self.assertIn("NADA foi salvo", r)

    def test_dois_dias_da_semana_nada_e_salvo(self):
        r = self.aplica("toda segunda e quarta às 8h me manda a agenda")
        self.assertEqual(self.criada(), [])
        self.assertIn("NADA foi salvo", r)

    def test_lembrete_repetido_continua_lembrete(self):
        msg = "me lembre de tomar o remedio todo dia às 8h"
        self.assertFalse(chat._is_task(msg))
        self.aplica(msg, acao="lembrete", titulo="Tomar o remedio", repetir="diario")
        self.assertEqual(self.criada(), [])
        self.assertEqual([p for _m, p, _b in self.posts], ["/notes"])

    def test_modelo_chamou_lembrete_de_tarefa_vira_lembrete(self):
        self.aplica("me lembre de tomar agua todo dia às 8h", titulo="Tomar agua", repetir="diario")
        self.assertEqual([p for _m, p, _b in self.posts], ["/notes"])

    def test_modelo_chamou_tarefa_de_lembrete_a_regra_corrige(self):
        self.aplica("todo dia às 8h me manda a agenda", acao="lembrete")
        self.assertEqual(len(self.criada()), 1)

    def test_modelo_diz_nenhuma_segura_falso_alarme(self):
        self.assertIsNone(self.aplica("todo dia às 8h faz sol aqui", acao="nenhuma"))
        self.assertEqual(self.posts, [])

    def test_pergunta_precisa_do_aval_do_modelo(self):
        msg = "você me manda as notícias todo dia às 8h?"
        self.aplica(msg, acao="lembrete", titulo="Noticias", repetir="diario")
        self.assertEqual(self.criada(), [])
        self.aplica(msg, acao="tarefa")
        self.assertEqual(len(self.criada()), 1)

    def test_email_para_outra_pessoa_nao_e_tarefa(self):
        self.assertFalse(chat._is_task("manda um e-mail pra Maria todo dia às 8h"))
        self.assertTrue(chat._is_task("todo dia às 18h me manda um resumo dos e-mails"))

    def test_conversa_comum_nao_e_tarefa(self):
        for msg in ("todo dia eu faço exercício", "a marca do carro", "resuma este texto", "manda ver",
                    "todo dia a Maria reclama", "faz a tarefa de casa comigo"):
            self.assertFalse(chat._is_task(msg), msg)

    def test_desfazer_apaga_a_tarefa(self):
        self.aplica("todo dia às 8h me manda a agenda", titulo="Agenda do dia")
        r = self.f._undo(UID)
        self.assertEqual(self.posts[-1][:2], ("POST", "/tasks/delete"))
        self.assertIn("a tarefa", r)

    def inlet(self, msg):
        body = {"model": "m", "messages": [{"role": "user", "content": msg}]}
        return asyncio.run(self.f.inlet(body, {"id": UID}))

    def test_inlet_resumo_de_emails_nao_e_barrado_como_pedido_de_email(self):
        with mock.patch.object(self.f, "_extract", return_value={"acao": "tarefa", "titulo": "E-mails"}):
            # no singular: _EMAIL_REQ nao casa com "e-mails" e o desvio nem seria testado
            b = self.inlet("todo dia às 18h me manda um resumo do e-mail")
        self.assertEqual(self.criada()[0]["kind"], "emails")
        self.assertIn("Tarefa criada", b["messages"][0]["content"])

    def test_inlet_regenerar_a_resposta_nao_duplica(self):
        msg = "todo dia às 8h me manda minha agenda"  # tambem casa com a consulta
        with mock.patch.object(self.f, "_extract", return_value={"acao": "tarefa", "titulo": "Agenda"}):
            self.inlet(msg)
            self.inlet(msg)
        self.assertEqual(len(self.criada()), 1)

    def test_a_troca_de_acentos_nao_mudou_a_leitura_de_datas(self):
        w = chat._parse_when("sábado às 14h30", self.agora)
        self.assertEqual(w["start"], datetime(2026, 11, 7, 14, 30))

    def test_prompt_continua_formatavel(self):
        self.assertIn('"acao":"tarefa"', chat._PROMPT.format(msg="x"))


class Ntfy(http.server.BaseHTTPRequestHandler):
    """Servidor ntfy de mentira: guarda o que chegou."""
    recebidos = []
    status = 200

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(n).decode("utf-8"))
        Ntfy.recebidos.append((self.path, self.headers.get("Authorization"), corpo))
        self.send_response(Ntfy.status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


class NtfyBase(Base):
    def setUp(self):
        super().setUp()
        Ntfy.recebidos, Ntfy.status = [], 200
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Ntfy)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        p = mock.patch.object(api, "NTFY_URL", self.url)
        p.start()
        self.addCleanup(p.stop)
        self.topico = "codigo-bem-comprido"

    def tarefa_pronta(self, texto="Saldo da conta: R$ 1.234"):
        tid = self.tarefa()
        # aqui nao da' para trocar requests.post: o ntfy usa o mesmo modulo
        with mock.patch.object(tasks, "llm", return_value=texto):
            api._run_task_sync(tasks.task_get(self.cx, UID, tid), None, True)


@unittest.skipUnless(HAVE_DEPS, "faltam dependencias")
class NtfyEnvio(NtfyBase):
    def test_por_padrao_vai_so_o_titulo(self):
        db.settings_set(self.cx, UID, {"ntfy_topico": self.topico})
        self.tarefa_pronta()
        ((path, auth, corpo),) = Ntfy.recebidos
        self.assertEqual(corpo["message"], "Tarefa concluída: Bom dia")
        self.assertEqual((corpo["topic"], path, auth), (self.topico, "/", None))
        self.assertNotIn("Saldo", json.dumps(corpo, ensure_ascii=False))

    def test_conteudo_so_com_a_opcao_ligada(self):
        db.settings_set(self.cx, UID, {"ntfy_topico": self.topico, "ntfy_conteudo": True})
        self.tarefa_pronta()
        corpo = Ntfy.recebidos[0][2]
        self.assertEqual(corpo["message"], "Saldo da conta: R$ 1.234")
        self.assertEqual(corpo["title"], "Nous - Tarefa concluída: Bom dia")

    def test_conteudo_cortado_em_900(self):
        db.settings_set(self.cx, UID, {"ntfy_topico": self.topico, "ntfy_conteudo": True})
        self.tarefa_pronta("x" * 2000)
        self.assertEqual(len(Ntfy.recebidos[0][2]["message"]), 900)

    def test_servidor_e_token_proprios(self):
        with mock.patch.object(api, "NTFY_URL", "http://127.0.0.1:1"):  # o publico nao pode ser usado
            db.settings_set(self.cx, UID, {"ntfy_topico": self.topico, "ntfy_servidor": self.url + "/",
                                           "ntfy_token": api.dav.seal("tk_segredo")})
            self.tarefa_pronta()
        self.assertEqual(Ntfy.recebidos[0][1], "Bearer tk_segredo")

    def test_lembrete_nao_manda_o_corpo_da_nota(self):
        db.settings_set(self.cx, UID, {"ntfy_topico": self.topico})
        api.deliver(self.cx, UID, "Lembrete: Exame", "resultado do exame de sangue")
        corpo = Ntfy.recebidos[0][2]
        self.assertEqual(corpo["message"], "Lembrete: Exame")
        self.assertNotIn("sangue", json.dumps(corpo))

    def test_email_continua_recebendo_o_texto(self):
        db.settings_set(self.cx, UID, {"ntfy_topico": self.topico, "aviso_email": True})
        with mock.patch.object(tasks, "send_email_to_self") as envia:
            api.deliver(self.cx, UID, "Tarefa concluída: X", "texto inteiro")
        envia.assert_called_once_with("[Nous] Tarefa concluída: X", "texto inteiro")

    def test_servidor_recusou_nao_derruba_e_e_informado(self):
        db.settings_set(self.cx, UID, {"ntfy_topico": self.topico})
        Ntfy.status = 403
        self.assertIs(api.deliver(self.cx, UID, "t", "b"), False)

    def test_sem_topico_nao_sai_nada(self):
        self.assertIsNone(api.deliver(self.cx, UID, "t", "b"))
        self.assertEqual(Ntfy.recebidos, [])

    def test_endereco_invalido_e_recusado(self):
        for ruim in ("ntfy.exemplo.com", "ftp://x.com", "https://user:senha@x.com", "https://x.com/a b"):
            with self.assertRaises(ValueError, msg=ruim):
                db.settings_set(self.cx, UID, {"ntfy_servidor": ruim})
        self.assertEqual(db.settings_set(self.cx, UID, {"ntfy_servidor": "https://x.com/ntfy/"})["ntfy_servidor"],
                         "https://x.com/ntfy")


@unittest.skipUnless(HAVE_DEPS, "faltam dependencias")
class NtfyMigracao(Base):
    def banco_antigo(self):
        """Banco de quem ja' usava: so' as chaves antigas."""
        self.cx.execute("INSERT INTO settings (user_id, key, value) VALUES (?,?,?)",
                        (UID, "ntfy_topico", "codigo-antigo-123"))
        self.cx.commit()

    def test_quem_usava_continua_no_topico_e_passa_ao_padrao_seguro(self):
        self.banco_antigo()
        s = db.settings_get(self.cx, UID)
        self.assertEqual((s["ntfy_topico"], s["ntfy_conteudo"], s["ntfy_servidor"]),
                         ("codigo-antigo-123", "0", ""))

    def test_avisa_uma_vez_so(self):
        self.banco_antigo()
        self.assertEqual(db.migrate_ntfy(self.cx), 1)
        self.assertEqual(db.migrate_ntfy(self.cx), 0)
        (n,) = self.notifs()
        self.assertIn("só o nome da tarefa", n["body"])

    def test_quem_nao_usa_ntfy_nao_recebe_aviso(self):
        db.settings_set(self.cx, UID, {"aviso_email": True})
        self.assertEqual(db.migrate_ntfy(self.cx), 0)

    def test_quem_configura_depois_da_atualizacao_nao_recebe_aviso(self):
        db.settings_set(self.cx, UID, {"ntfy_topico": "codigo-novo-1234"})
        self.assertEqual(db.migrate_ntfy(self.cx), 0)

    def test_tarefas_do_banco_antigo_ganham_as_colunas_novas(self):
        self.cx.close()
        os.remove(db.db_path())
        for extra in ("-wal", "-shm"):
            if os.path.exists(db.db_path() + extra):
                os.remove(db.db_path() + extra)
        velho = sqlite3.connect(db.db_path())
        velho.execute("""CREATE TABLE tasks (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'pergunta', prompt TEXT NOT NULL DEFAULT '', schedule TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1, next_run INTEGER, last_run INTEGER, last_status TEXT,
            last_note TEXT, email INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL)""")
        velho.execute("INSERT INTO tasks (id, user_id, name, schedule, next_run, created_at, updated_at) "
                      "VALUES ('a', 'u1', 'Velha', 'diario 08:00', ?, 1, 1)", (self.agora,))
        velho.commit()
        velho.close()
        self.cx = db.connect()
        self.addCleanup(self.cx.close)
        r = self.row("a")
        self.assertEqual((r["aviso"], r["retry_count"], r["last_hash"], r["last_error"]),
                         ("sempre", 0, None, None))
        self.assertEqual([t["id"] for t in tasks.due_tasks(self.cx)], ["a"])


@unittest.skipUnless(HAVE_DEPS, "faltam dependencias")
class Rotas(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nous-rotas-")
        self.data_antes = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = self.tmp
        cx = db.connect()
        cx.execute("INSERT INTO settings (user_id, key, value) VALUES (?,?,?)",
                   ("velho", "ntfy_topico", "codigo-antigo-123"))
        cx.commit()
        cx.close()
        self.client = TestClient(TestServer(api.build_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        if self.data_antes is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self.data_antes
        await asyncio.sleep(0.05)
        shutil.rmtree(self.tmp, True)

    async def salva(self, **d):
        r = await self.client.post("/settings", json={"user_id": UID, **d})
        return r.status, await r.json()

    async def guardado(self):
        cx = db.connect()
        try:
            return db.settings_get(cx, UID)["ntfy_token"]
        finally:
            cx.close()

    async def test_token_nao_volta_para_a_tela_nem_fica_em_texto_puro(self):
        st, d = await self.salva(ntfy_token="tk_segredo")
        self.assertEqual(st, 200)
        self.assertNotIn("ntfy_token", d["settings"])
        self.assertIs(d["settings"]["ntfy_token_salvo"], True)
        r = await self.client.get("/settings", params={"user_id": UID})
        texto = await r.text()
        self.assertNotIn("tk_segredo", texto)
        self.assertNotIn("dpapi", texto)
        selado = await self.guardado()
        self.assertNotIn("tk_segredo", selado)
        self.assertEqual(api.dav.unseal(selado), "tk_segredo")

    async def test_token_em_branco_mantem_e_apagar_apaga(self):
        await self.salva(ntfy_token="tk_segredo")
        _st, d = await self.salva(ntfy_token="", ntfy_topico="")
        self.assertIs(d["settings"]["ntfy_token_salvo"], True)
        _st, d = await self.salva(ntfy_token="", ntfy_token_apagar=True)
        self.assertIs(d["settings"]["ntfy_token_salvo"], False)

    async def test_token_com_espaco_no_meio_e_recusado(self):
        st, d = await self.salva(ntfy_token="tk segredo")
        self.assertEqual(st, 400)
        self.assertIn("token", d["error"])

    async def test_teste_de_aviso_conta_que_o_servidor_recusou(self):
        await self.salva(ntfy_topico="codigo-bem-comprido", ntfy_servidor=f"http://127.0.0.1:{porta_fechada()}")
        r = await self.client.post("/settings/test", json={"user_id": UID})
        self.assertIs((await r.json())["ntfy"], False)

    async def test_ao_iniciar_avisa_quem_ja_usava_o_ntfy(self):
        r = await self.client.get("/notifications", params={"user_id": "velho"})
        self.assertEqual([n["title"] for n in (await r.json())["items"]], ["Avisos no celular mudaram"])

    async def test_relogio_roda_como_agendada_e_o_botao_nao(self):
        with mock.patch.object(api, "_tick_sync", return_value=[{"id": "x"}]), \
                mock.patch.object(api.dav, "sync_due"), mock.patch.object(api, "_subs_sync_all"), \
                mock.patch.object(api, "_run_task_sync") as roda:
            relogio = asyncio.ensure_future(api.clock(None))
            await asyncio.sleep(0.1)
            relogio.cancel()
            roda.assert_any_call({"id": "x"}, None, True)
            r = await self.client.post("/tasks", json={"user_id": UID, "name": "T", "prompt": "p",
                                                       "schedule": "diario 08:00"})
            t = (await r.json())["task"]
            roda.reset_mock()
            await self.client.post("/tasks/run", json={"user_id": UID, "id": t["id"]})
            await asyncio.sleep(0.05)
            self.assertEqual(len(roda.call_args.args), 1)  # agendada fica no padrao, False
        api._running.discard(t["id"])

    async def test_opcao_de_aviso_passa_pela_rota_e_sobrevive_a_edicao(self):
        r = await self.client.post("/tasks", json={"user_id": UID, "name": "T", "prompt": "p",
                                                   "schedule": "diario 08:00", "aviso": "mudou"})
        t = (await r.json())["task"]
        self.assertEqual(t["aviso"], "mudou")
        r = await self.client.post("/tasks/update", json={"user_id": UID, "id": t["id"], "enabled": False})
        self.assertEqual((await r.json())["task"]["aviso"], "mudou")


if __name__ == "__main__":
    unittest.main()
