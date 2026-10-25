# -*- coding: utf-8 -*-
"""
Assistente de E-mail do Nous, de ponta a ponta, contra um IMAP/SMTP de mentira.

Sem rede e sem Ollama (um Ollama e uma Agenda de mentira sobem em portas locais).
Rode da raiz do repositorio:

    python -m unittest discover -s email/testes -t email/testes -v

Precisa de aiohttp e requests (os mesmos do Open WebUI); sem eles, pula tudo.
"""
import os
import sys
import json
import time
import shutil
import tempfile
import threading
import unittest
import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from email import message_from_bytes
from email.header import decode_header, make_header
from email.policy import default as POLICY

AQUI = os.path.dirname(os.path.abspath(__file__))
EMAIL_DIR = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, EMAIL_DIR)
sys.path.insert(0, os.path.join(os.path.dirname(EMAIL_DIR), "utilidades"))

try:
    import aiohttp  # noqa: F401
    import requests  # noqa: F401
except ImportError as _e:  # pragma: no cover
    raise unittest.SkipTest("faltam aiohttp/requests: %s" % _e)

from aiohttp.test_utils import TestServer, TestClient  # noqa: E402
import servidor_falso as sf  # noqa: E402
import caixa_falsa as cx  # noqa: E402
import nous_email as ne  # noqa: E402
import nous_email_api as api  # noqa: E402
import drafts  # noqa: E402

DONO, SENHA = cx.DONO, "senha-do-gui"
OUTRO, SENHA2 = "ana@outra.test", "outra-senha"


# ---------------------------------------------------------------- servidor HTTP de mentira

class HttpFalso:
    """Ollama / Agenda de mentira: `rotas` = {(metodo, caminho): funcao(corpo_json) -> (status, json)}."""

    def __init__(self):
        self.rotas, self.pedidos = {}, []
        dono = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _go(self, metodo):
                n = int(self.headers.get("Content-Length") or 0)
                corpo = json.loads(self.rfile.read(n) or b"{}") if n else {}
                dono.pedidos.append((metodo, self.path, corpo))
                f = dono.rotas.get((metodo, self.path))
                st, data = f(corpo) if f else (404, {"error": "sem rota"})
                b = json.dumps(data).encode()
                self.send_response(st)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                self._go("GET")

            def do_POST(self):
                self._go("POST")

        self.porta = sf.porta_livre()
        self.srv = ThreadingHTTPServer(("127.0.0.1", self.porta), H)
        self.srv.daemon_threads = True
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.porta

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


def _ollama_falso(modelos):
    """Ollama que classifica por palavra-chave. `modelos` = lista de dicts do /api/tags."""
    h = HttpFalso()
    h.rotas[("GET", "/api/tags")] = lambda _b: (200, {"models": h.modelos})
    h.modelos = modelos

    def gerar(b):
        p = b.get("prompt", "")
        fmt = b.get("format") or {}
        props = (fmt.get("properties") or {}) if isinstance(fmt, dict) else {}
        if "categoria" in props:
            t = p.lower()
            cat = ("Spam" if "dinheiro" in t or "prêmio" in t else "Promoção" if "desconto" in t or "ofertas" in t
                   else "Importante" if "fatura" in t or "boleto" in t or "orçamento" in t else "Pode esperar")
            return 200, {"response": json.dumps({"categoria": cat, "resumo": "resumo falso: " + p.split("Assunto:")[-1][:30].strip()})}
        if "destinatario" in props:
            import re
            m = re.search(r'Mensagem: """(.*)"""', p, re.S)
            alvo = re.search(r"\b(?:pra|pro|para|ao|a)\s+(?:o\s+|a\s+)?([A-ZÁÉÍÓÚ][\wçãé]+)", m.group(1) if m else "")
            return 200, {"response": json.dumps({"destinatario": alvo.group(1) if alvo else ""})}
        if p.startswith("Resuma"):
            return 200, {"response": "Resumo falso do e-mail."}
        if p.startswith("Escreva uma resposta"):
            return 200, {"response": "Olá! Obrigado pela mensagem. Respondo em breve."}
        return 200, {"response": "ok"}
    h.rotas[("POST", "/api/generate")] = gerar
    return h


# ---------------------------------------------------------------- ambiente do modulo

class Amb:
    pass


A = Amb()


def setUpModule():
    A.cert_antes = os.environ.get("SSL_CERT_FILE")
    os.environ["SSL_CERT_FILE"] = sf.CERT          # o cliente confia so' no certificado de teste
    A.raiz = tempfile.mkdtemp(prefix="nous-email-teste-")
    A.imap = sf.ImapFalso({}).start()
    A.smtp = sf.SmtpFalso({}, ssl_direto=False).start()       # STARTTLS (porta 587 e afins)
    A.smtp_ssl = sf.SmtpFalso({}, ssl_direto=True).start()    # SSL desde o inicio (porta 465)
    A.ollama = _ollama_falso([{"name": "qwen3:4b"}])
    A.agenda = HttpFalso()
    api.OLLAMA_URL = A.ollama.url
    api.AGENDA_URL = A.agenda.url
    ne.TIMEOUT = 3


def tearDownModule():
    for s in (A.imap, A.smtp, A.smtp_ssl, A.ollama, A.agenda):
        s.stop()
    if A.cert_antes is None:
        os.environ.pop("SSL_CERT_FILE", None)
    else:
        os.environ["SSL_CERT_FILE"] = A.cert_antes
    shutil.rmtree(A.raiz, ignore_errors=True)


def conta_dict(user=DONO, senha=SENHA, **over):
    d = {"user": user, "app_password": senha, "imap": "localhost", "smtp": "localhost",
         "imap_port": A.imap.porta, "smtp_port": A.smtp.porta}
    d.update(over)
    return d


def msg_decodificada(raw):
    return message_from_bytes(raw, policy=POLICY)


class Base(unittest.TestCase):
    def setUp(self):
        self.dados = tempfile.mkdtemp(dir=A.raiz)
        os.environ["DATA_DIR"] = self.dados
        os.environ.pop("NOUS_DATA_DIR", None)
        self.caixa = cx.monta(DONO, SENHA)
        self.caixa2 = cx.monta(OUTRO, SENHA2)
        A.imap.contas = {DONO: self.caixa, OUTRO: self.caixa2}
        A.imap.modo = A.smtp.modo = A.smtp_ssl.modo = "normal"
        A.imap.rejeita_tudo = A.smtp.rejeita_tudo = A.smtp_ssl.rejeita_tudo = False
        A.imap.flags_depois = False
        A.imap.comandos, A.imap.bytes_fetch, A.imap.marcou_lido = [], 0, []
        for s in (A.smtp, A.smtp_ssl):
            s.contas = {DONO: {"senha": SENHA}, OUTRO: {"senha": SENHA2}}
            s.enviadas, s.recusa = [], set()
        A.ollama.modelos = [{"name": "qwen3:4b"}]
        A.ollama.pedidos.clear()
        A.agenda.pedidos.clear()
        A.agenda.rotas.clear()
        api._cache.clear()
        ne.TIMEOUT = 3
        self.addCleanup(shutil.rmtree, self.dados, True)

    def uid(self, chave, caixa=None):
        return str((caixa or self.caixa)["uids"][chave])

    def salva(self, **over):
        ne.save_account(conta_dict(**over))


# ================================================================ cliente: conectar

class ConectarTests(Base):
    def test_conecta_com_senha_certa(self):
        ok, msg = ne.test_connection(conta_dict())
        self.assertTrue(ok, msg)

    def test_senha_errada_diz_isso_em_portugues_sem_lixo_tecnico(self):
        ok, msg = ne.test_connection(conta_dict(app_password="errada"))
        self.assertFalse(ok)
        self.assertIn("senha", msg.lower())
        self.assertNotIn("b'", msg)

    def test_servidor_fora_do_ar(self):
        morta = sf.porta_livre(9280, 9299)       # nada escutando
        ok, msg = ne.test_connection(conta_dict(imap_port=morta))
        self.assertFalse(ok)
        self.assertIn("Não consegui conectar", msg)
        self.assertIn("localhost", msg)
        self.assertNotIn("WinError", msg)

    def test_servidor_que_nao_responde_nao_trava(self):
        A.imap.modo = "travado"
        ne.TIMEOUT = 1
        t = time.time()
        ok, msg = ne.test_connection(conta_dict())
        self.assertFalse(ok)
        self.assertLess(time.time() - t, 5)
        self.assertIn("tempo", msg)

    def test_servidor_que_derruba_a_conexao(self):
        A.imap.modo = "derruba"
        ok, msg = ne.test_connection(conta_dict())
        self.assertFalse(ok)
        self.assertTrue(msg)

    def test_nome_de_servidor_que_nao_existe(self):
        ok, msg = ne.test_connection(conta_dict(imap="servidor-que-nao-existe.invalid"))
        self.assertFalse(ok)
        self.assertIn("servidor-que-nao-existe.invalid", msg)
        self.assertIn("Não encontrei", msg)

    def test_certificado_nao_confiavel_e_recusado(self):
        """O imaplib/smtplib da stdlib nao verificam o certificado por padrao."""
        antes = os.environ.pop("SSL_CERT_FILE")
        try:
            ok, msg = ne.test_connection(conta_dict())
        finally:
            os.environ["SSL_CERT_FILE"] = antes
        self.assertFalse(ok)
        self.assertIn("certificado", msg.lower())

    def test_senha_com_acento(self):
        A.imap.contas[DONO]["senha"] = "coração-123"
        ok, msg = ne.test_connection(conta_dict(app_password="coração-123"))
        self.assertTrue(ok, msg)
        for s in (A.smtp, A.smtp_ssl):
            s.contas[DONO]["senha"] = "coração-123"
        self.salva(app_password="coração-123")
        ok, msg = ne.send_message("maria@familia.com.br", "Oi", "Texto")
        self.assertTrue(ok, msg)

    def test_senha_com_aspas_e_barra(self):
        senha = 'a"b\\c d'
        A.imap.contas[DONO]["senha"] = senha
        ok, msg = ne.test_connection(conta_dict(app_password=senha))
        self.assertTrue(ok, msg)

    def test_duas_contas_e_padrao(self):
        self.salva()
        self.salva(user=OUTRO, app_password=SENHA2)
        self.assertEqual([a["user"] for a in ne.list_accounts()], [DONO, OUTRO])
        self.assertEqual(ne.load_account()["user"], DONO)
        self.assertTrue(ne.set_default(OUTRO))
        self.assertEqual(ne.load_account()["user"], OUTRO)
        ne.delete_account(OUTRO)
        self.assertEqual(ne.load_account()["user"], DONO)

    def test_arquivo_de_contas_nao_vaza_na_listagem(self):
        self.salva()
        self.assertNotIn("app_password", json.dumps(ne.list_accounts()))


# ================================================================ cliente: caixa de entrada

class CaixaTests(Base):
    def setUp(self):
        super().setUp()
        self.salva()

    def test_lista_as_mais_recentes_primeiro(self):
        msgs = ne.list_recent(50)
        self.assertEqual(len(msgs), len(self.caixa["msgs"]))
        self.assertEqual([m["uid"] for m in msgs][0], str(max(self.caixa["uids"].values())))
        self.assertEqual(ne.list_recent(3)[0]["uid"], msgs[0]["uid"])
        self.assertEqual(len(ne.list_recent(3)), 3)

    def test_acentos_e_latin1_nos_cabecalhos(self):
        m = {x["uid"]: x for x in ne.list_recent(50)}[self.uid("latin1")]
        self.assertEqual(m["subject"], "Atenção: reunião às 14h")
        self.assertIn("José Conceição", m["from"])
        m = {x["uid"]: x for x in ne.list_recent(50)}[self.uid("pessoal")]
        self.assertEqual(m["subject"], "Jantar de sábado?")

    def test_nao_lidos_e_flags_em_qualquer_ordem(self):
        for depois in (False, True):
            A.imap.flags_depois = depois
            por_uid = {x["uid"]: x for x in ne.list_recent(50)}
            self.assertFalse(por_uid[self.uid("pessoal")]["unread"], "flags_depois=%s" % depois)
            self.assertTrue(por_uid[self.uid("promocao")]["unread"], "flags_depois=%s" % depois)

    def test_newsletter_e_em_massa(self):
        por_uid = {x["uid"]: x for x in ne.list_recent(50)}
        n = por_uid[self.uid("news1")]
        self.assertTrue(n["bulk"])
        self.assertIn("mailto:sair@boletim.com.br", n["list_unsubscribe"])
        self.assertIn("https://boletim.com.br/sair", n["list_unsubscribe"])
        self.assertTrue(por_uid[self.uid("promocao")]["bulk"])           # Precedence: bulk
        self.assertFalse(por_uid[self.uid("pessoal")]["bulk"])

    def test_sem_assunto(self):
        m = {x["uid"]: x for x in ne.list_recent(50)}[self.uid("sem_assunto")]
        self.assertEqual(m["subject"], "(sem assunto)")

    def test_trecho_do_corpo_vai_para_a_triagem(self):
        por_uid = {x["uid"]: x for x in ne.list_recent(50)}
        self.assertIn("jantar", por_uid[self.uid("pessoal")]["snippet"])
        self.assertIn("Aproveite", por_uid[self.uid("promocao")]["snippet"])
        self.assertIn("extrato", por_uid[self.uid("html")]["snippet"])          # so' HTML
        self.assertNotIn("alert", por_uid[self.uid("html")]["snippet"])
        self.assertIn("reunião", por_uid[self.uid("latin1")]["snippet"])
        self.assertIn("fatura", por_uid[self.uid("cobranca")]["snippet"])
        self.assertLessEqual(max(len(m["snippet"]) for m in por_uid.values()), 400)

    def test_listar_nao_baixa_o_anexo_grande_nem_marca_como_lido(self):
        ne.list_recent(50)
        self.assertLess(A.imap.bytes_fetch, 200 * 1024, "baixou %d bytes só para listar" % A.imap.bytes_fetch)
        self.assertEqual(A.imap.marcou_lido, [])
        ne.get_message(self.uid("promocao"))
        self.assertEqual(A.imap.marcou_lido, [])           # abrir tambem nao marca (EXAMINE)

    def test_listar_e_rapido_em_um_so_pedido(self):
        ne.list_recent(50)
        self.assertLessEqual(A.imap.comandos.count("UID"), 3)          # SEARCH + FETCH em lote

    def test_corpo_com_acentos(self):
        m = ne.get_message(self.uid("pessoal"))
        self.assertIn("Vamos jantar lá em casa no sábado às 20h", m["body"])
        self.assertEqual(m["subject"], "Jantar de sábado?")
        self.assertEqual(m["attachments"], [])

    def test_corpo_em_latin1(self):
        m = ne.get_message(self.uid("latin1"))
        self.assertEqual(m["body"], "Atenção: a reunião é às 14h na sala dos coração e ação.")

    def test_charset_desconhecido_nao_vira_corpo_vazio(self):
        m = ne.get_message(self.uid("estranho"))
        self.assertIn("proposta", m["body"])

    def test_so_html_vira_texto_sem_script_nem_estilo(self):
        m = ne.get_message(self.uid("html"))
        self.assertEqual(m["body"], "Olá! O extrato de outubro está disponível no app.")

    def test_multipart_alternative_prefere_o_texto(self):
        m = ne.get_message(self.uid("promocao"))
        self.assertIn("Aproveite as ofertas", m["body"])
        self.assertNotIn("<", m["body"])

    def test_thread_cabecalhos_de_resposta(self):
        m = ne.get_message(self.uid("thread3"))
        self.assertEqual(m["message_id"], "<orc3@falso.test>")
        self.assertIn("Fechado!", m["body"])

    def test_cobranca_tem_anexo_pdf(self):
        m = ne.get_message(self.uid("cobranca"))
        self.assertEqual([(a["name"], a["type"]) for a in m["attachments"]], [("boleto-outubro.pdf", "application/pdf")])
        self.assertIn("Linha digitável", m["body"])

    def test_baixa_o_anexo_certo(self):
        m = ne.get_message(self.uid("cobranca"))
        nome, tipo, dados = ne.get_attachment(self.uid("cobranca"), m["attachments"][0]["idx"])
        self.assertEqual((nome, tipo), ("boleto-outubro.pdf", "application/pdf"))
        self.assertTrue(dados.startswith(b"%PDF-1.4"))
        with self.assertRaises(RuntimeError):
            ne.get_attachment(self.uid("cobranca"), 99)

    def test_anexo_grande_chega_inteiro(self):
        m = ne.get_message(self.uid("grande"))
        self.assertEqual(len(m["attachments"]), 1)
        self.assertEqual(m["attachments"][0]["size"], cx.GRANDE)
        _n, _t, dados = ne.get_attachment(self.uid("grande"), m["attachments"][0]["idx"])
        self.assertEqual(len(dados), cx.GRANDE)

    def test_convite_de_calendario(self):
        m = ne.get_message(self.uid("convite"))
        self.assertIn("BEGIN:VCALENDAR", m["invite"])
        self.assertEqual(m["attachments"], [])        # o .ics nao aparece como anexo comum

    def test_uid_inexistente(self):
        self.assertIn("error", ne.get_message("99999"))

    def test_conta_errada_na_listagem_devolve_erro_claro(self):
        A.imap.rejeita_tudo = True
        r = ne.list_recent(5)
        self.assertEqual(len(r), 1)
        self.assertIn("senha", r[0]["error"].lower())

    def test_escolhe_a_conta_pedida(self):
        self.salva(user=OUTRO, app_password=SENHA2)
        a = ne.list_recent(50, DONO)
        b = ne.list_recent(50, OUTRO)
        self.assertEqual({m["account"] for m in a}, {DONO})
        self.assertEqual({m["account"] for m in b}, {OUTRO})


# ================================================================ cliente: enviar

class EnviarTests(Base):
    def setUp(self):
        super().setUp()
        self.salva()

    def enviada(self, i=-1, srv=None):
        return (srv or A.smtp).enviadas[i]

    def test_envia_com_starttls_e_acentos(self):
        ok, msg = ne.send_message("maria@familia.com.br", "Jantar de sábado: confirmado ✓", "Oi, Maria!\nPode ser às 20h. Coração.")
        self.assertTrue(ok, msg)
        e = self.enviada()
        self.assertEqual((e["auth"], e["de"], e["para"]), (DONO, DONO, ["maria@familia.com.br"]))
        m = msg_decodificada(e["raw"])
        self.assertEqual(m["Subject"], "Jantar de sábado: confirmado ✓")
        self.assertEqual(m.get_body().get_content().replace("\r\n", "\n").strip(),
                         "Oi, Maria!\nPode ser às 20h. Coração.")
        self.assertTrue(m["Date"] and m["Message-ID"], "falta Date/Message-ID (alguns provedores recusam)")
        self.assertEqual(m["From"], DONO)

    def test_envia_com_ssl_direto(self):
        self.salva(smtp_port=A.smtp_ssl.porta, smtp_security="ssl")
        ok, msg = ne.send_message("maria@familia.com.br", "Oi", "Texto")
        self.assertTrue(ok, msg)
        self.assertEqual(len(A.smtp_ssl.enviadas), 1)
        self.assertEqual(len(A.smtp.enviadas), 0)

    def test_resposta_leva_in_reply_to(self):
        ne.send_message("carlos@empresa.com.br", "Re: Orçamento do site", "Fechado.", "<orc3@falso.test>")
        m = msg_decodificada(self.enviada()["raw"])
        self.assertEqual(m["In-Reply-To"], "<orc3@falso.test>")
        self.assertEqual(m["References"], "<orc3@falso.test>")

    def test_destinatario_com_nome_e_varios(self):
        ok, msg = ne.send_message("Maria Souza <maria@familia.com.br>, joao@x.test", "Oi", "Texto")
        self.assertTrue(ok, msg)
        self.assertEqual(self.enviada()["para"], ["maria@familia.com.br", "joao@x.test"])

    def test_assunto_com_quebra_de_linha_nao_injeta_cabecalho(self):
        ok, msg = ne.send_message("maria@familia.com.br", "Oi\r\nBcc: espiao@x.test", "Texto")
        e = self.enviada() if A.smtp.enviadas else None
        if e:
            self.assertEqual(e["para"], ["maria@familia.com.br"])
            m = message_from_bytes(e["raw"])
            self.assertIsNone(m["Bcc"])
            self.assertNotIn(b"\nBcc:", e["raw"])

    def test_destinatario_recusado_diz_qual(self):
        A.smtp.recusa = {"naoexiste@x.test"}
        ok, msg = ne.send_message("naoexiste@x.test", "Oi", "Texto")
        self.assertFalse(ok)
        self.assertIn("naoexiste@x.test", msg)
        self.assertNotIn("b'", msg)

    def test_senha_errada_no_smtp(self):
        self.salva(app_password="errada")
        ok, msg = ne.send_message("maria@familia.com.br", "Oi", "Texto")
        self.assertFalse(ok)
        self.assertIn("senha", msg.lower())

    def test_smtp_fora_do_ar(self):
        self.salva(smtp_port=sf.porta_livre(9280, 9299))
        ok, msg = ne.send_message("maria@familia.com.br", "Oi", "Texto")
        self.assertFalse(ok)
        self.assertIn("Não consegui conectar", msg)

    def test_smtp_travado_nao_trava(self):
        A.smtp.modo = "travado"
        ne.TIMEOUT = 1
        t = time.time()
        ok, msg = ne.send_message("maria@familia.com.br", "Oi", "Texto")
        self.assertFalse(ok)
        self.assertLess(time.time() - t, 6)

    def test_sem_conta(self):
        ne.delete_account()
        ok, msg = ne.send_message("maria@familia.com.br", "Oi", "Texto")
        self.assertFalse(ok)

    def test_envia_pela_conta_escolhida(self):
        self.salva(user=OUTRO, app_password=SENHA2)
        ok, msg = ne.send_message("maria@familia.com.br", "Oi", "Texto", None, OUTRO)
        self.assertTrue(ok, msg)
        self.assertEqual(self.enviada()["de"], OUTRO)


# ================================================================ servico HTTP

class ApiBase(Base, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = TestServer(api.build_app(), port=sf.porta_livre())
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def chama(self, metodo, caminho, corpo=None, **params):
        r = await self.client.request(metodo, caminho, json=corpo, params=params or None)
        ct = r.headers.get("Content-Type", "")
        data = await r.json() if "json" in ct else await r.read()
        return r.status, data

    async def conecta(self, **over):
        c = conta_dict(**over)
        return await self.chama("POST", "/connect", c)

    def nada_enviado(self):
        self.assertEqual(A.smtp.enviadas + A.smtp_ssl.enviadas, [], "algo foi enviado sem confirmacao")


class ContasApiTests(ApiBase):
    async def test_conectar_senha_errada_da_401_com_mensagem_clara(self):
        st, d = await self.conecta(app_password="errada")
        self.assertEqual(st, 401)
        self.assertIn("senha", d["error"].lower())
        st, d = await self.chama("GET", "/status")
        self.assertFalse(d["connected"])

    async def test_provedor_desconhecido_pede_servidores(self):
        st, d = await self.chama("POST", "/connect", {"user": "x@empresa-desconhecida.com.br", "app_password": "s"})
        self.assertEqual(st, 400)
        self.assertIn("imap", d["error"])

    async def test_endereco_invalido(self):
        st, d = await self.chama("POST", "/connect", {"user": "isso nao e email", "app_password": "s",
                                                      "imap": "localhost", "smtp": "localhost"})
        self.assertEqual(st, 400)

    async def test_porta_invalida_da_400_e_nao_estoura(self):
        st, d = await self.conecta(imap_port="abc")
        self.assertEqual(st, 400)
        self.assertIn("porta", d["error"].lower())

    async def test_smtp_com_senha_errada_avisa_mas_conecta(self):
        A.smtp.rejeita_tudo = True
        st, d = await self.conecta()
        self.assertEqual(st, 200)
        self.assertIn("aviso", d)
        self.assertIn("enviar", d["aviso"])

    async def test_varias_contas_status_e_padrao(self):
        await self.conecta()
        st, d = await self.conecta(user=OUTRO, app_password=SENHA2)
        self.assertEqual(st, 200)
        st, d = await self.chama("GET", "/status")
        self.assertEqual(d["user"], DONO)
        self.assertEqual(len(d["accounts"]), 2)
        self.assertNotIn("app_password", json.dumps(d))
        st, d = await self.chama("POST", "/accounts/default", {"account": OUTRO})
        self.assertEqual(st, 200)
        st, d = await self.chama("GET", "/status")
        self.assertEqual(d["user"], OUTRO)
        st, d = await self.chama("POST", "/accounts/default", {"account": "ninguem@x.test"})
        self.assertEqual(st, 404)
        await self.chama("POST", "/disconnect", {"account": OUTRO})
        st, d = await self.chama("GET", "/status")
        self.assertEqual([a["user"] for a in d["accounts"]], [DONO])

    async def test_senha_nao_aparece_em_nenhuma_resposta_nem_no_ollama(self):
        await self.conecta()
        for caminho in ("/status", "/accounts"):
            st, d = await self.chama("GET", caminho)
            self.assertNotIn(SENHA, json.dumps(d))
        await self.chama("GET", "/inbox")
        self.assertNotIn(SENHA, json.dumps(A.ollama.pedidos))

    async def test_arquivo_de_contas_so_com_a_conta(self):
        await self.conecta()
        self.assertFalse(os.path.exists(os.path.join(self.dados, ".email_account.json")))
        self.assertTrue(os.path.exists(os.path.join(self.dados, ".email_accounts.json")))

    async def test_origem_estranha_e_barrada(self):
        r = await self.client.get("/status", headers={"Origin": "https://site-malvado.example"})
        self.assertEqual(r.status, 403)
        r = await self.client.get("/status", headers={"Host": "rebind.example"})
        self.assertEqual(r.status, 403)

    async def test_sem_conta_inbox_da_400(self):
        st, d = await self.chama("GET", "/inbox")
        self.assertEqual(st, 400)


class CaixaApiTests(ApiBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.conecta()

    async def test_triagem_classifica_e_resume(self):
        st, msgs = await self.chama("GET", "/inbox")
        self.assertEqual(st, 200)
        por_uid = {m["uid"]: m for m in msgs}
        self.assertEqual(por_uid[self.uid("spam")]["category"], "Spam")
        self.assertEqual(por_uid[self.uid("promocao")]["category"], "Promoção")
        self.assertEqual(por_uid[self.uid("cobranca")]["category"], "Importante")
        self.assertTrue(por_uid[self.uid("cobranca")]["summary"])
        self.nada_enviado()

    async def test_triagem_recebe_o_trecho_do_corpo(self):
        await self.chama("GET", "/inbox")
        prompts = " ".join(b.get("prompt", "") for _m, _p, b in A.ollama.pedidos)
        self.assertIn("Trecho: Oi, Gui!", prompts)               # o modelo ve' o comeco do corpo, nao so' o assunto
        self.assertIn("Aproveite as ofertas", prompts)

    async def test_triagem_usa_so_o_modelo_local(self):
        A.ollama.modelos = [{"name": "gpt-oss:120b-cloud"}, {"name": "qwen3-coder:480b-cloud"},
                            {"name": "x/modelo-da-nuvem"}, {"name": "kimi-k2:1t", "remote_host": "https://ollama.com:443"},
                            {"name": "nomic-embed-text:latest"}, {"name": "qwen3:4b"}]
        await self.chama("GET", "/inbox")
        usados = {b.get("model") for _m, p, b in A.ollama.pedidos if p == "/api/generate"}
        self.assertEqual(usados, {"qwen3:4b"})

    async def test_sem_modelo_local_nao_manda_nada_para_a_nuvem(self):
        A.ollama.modelos = [{"name": "gpt-oss:120b-cloud"}]
        await self.chama("GET", "/inbox")
        usados = {b.get("model") for _m, p, b in A.ollama.pedidos if p == "/api/generate"}
        self.assertFalse(any("cloud" in (u or "") for u in usados), usados)

    async def test_ollama_fora_do_ar_nao_derruba_a_caixa_e_nao_guarda_o_fracasso(self):
        bom = A.ollama.rotas[("POST", "/api/generate")]
        A.ollama.rotas[("POST", "/api/generate")] = lambda _b: (503, {"error": "carregando o modelo"})
        try:
            st, msgs = await self.chama("GET", "/inbox")
            self.assertEqual(st, 200)
            self.assertEqual({m["category"] for m in msgs}, {"Não classificado"})
        finally:
            A.ollama.rotas[("POST", "/api/generate")] = bom
        st, msgs = await self.chama("GET", "/inbox")           # voltou: nao pode ficar preso ao fracasso
        self.assertIn("Spam", {m["category"] for m in msgs})

    async def test_resumo_que_falhou_nao_fica_guardado(self):
        u = self.uid("pessoal")
        bom = A.ollama.rotas[("POST", "/api/generate")]
        A.ollama.rotas[("POST", "/api/generate")] = lambda _b: (503, {"error": "carregando o modelo"})
        try:
            st, d = await self.chama("GET", "/message", uid=u)
            self.assertEqual(st, 200)
            self.assertIn("Não foi possível", d["summary"])
        finally:
            A.ollama.rotas[("POST", "/api/generate")] = bom
        st, d = await self.chama("GET", "/message", uid=u)
        self.assertEqual(d["summary"], "Resumo falso do e-mail.")

    async def test_resumo_e_anexos_da_mensagem(self):
        st, d = await self.chama("GET", "/message", uid=self.uid("cobranca"))
        self.assertEqual(st, 200)
        self.assertEqual(d["summary"], "Resumo falso do e-mail.")
        self.assertEqual(d["attachments"][0]["name"], "boleto-outubro.pdf")
        st, d = await self.chama("GET", "/message")
        self.assertEqual(st, 400)

    async def test_cache_nao_mistura_contas_quando_o_padrao_muda(self):
        await self.conecta(user=OUTRO, app_password=SENHA2)
        # mesmo UID nas duas caixas, conteudos diferentes
        outra = self.caixa2["msgs"][0]
        self.assertEqual(outra.uid, self.caixa["msgs"][0].uid)
        outra.raw = outra.raw.replace(b"Jantar", b"Reuniao").replace(b"jantar", b"reuniao")
        u = str(outra.uid)

        def resposta(corpo):
            p = corpo["prompt"]
            return 200, {"response": "RESUMO:" + ("A" if "Jantar" in p else "B")}
        A.ollama.rotas[("POST", "/api/generate")] = resposta
        try:
            st, d1 = await self.chama("GET", "/message", uid=u)
            await self.chama("POST", "/accounts/default", {"account": OUTRO})
            st, d2 = await self.chama("GET", "/message", uid=u)
        finally:
            A.ollama.rotas[("POST", "/api/generate")] = _ollama_falso([]).rotas[("POST", "/api/generate")]
        self.assertNotEqual(d1["body"], d2["body"])
        self.assertNotEqual(d1["summary"], d2["summary"], "resumo da outra conta veio do cache")

    async def test_inbox_de_outra_conta(self):
        await self.conecta(user=OUTRO, app_password=SENHA2)
        st, msgs = await self.chama("GET", "/inbox", account=OUTRO)
        self.assertEqual({m["account"] for m in msgs}, {OUTRO})

    async def test_contatos_aprendidos_da_caixa(self):
        await self.chama("GET", "/inbox")
        st, d = await self.chama("GET", "/contacts")
        emails = {c["email"] for c in d["contacts"]}
        self.assertIn("maria@familia.com.br", emails)
        self.assertIn("carlos@empresa.com.br", emails)
        self.assertIn("jose@antigo.com.br", emails)
        nomes = {c["email"]: c["name"] for c in d["contacts"]}
        self.assertEqual(nomes["maria@familia.com.br"], "Maria Souza")
        self.assertEqual(nomes["jose@antigo.com.br"], "José Conceição")
        # newsletter, promocao em massa e a propria conta nao viram contato
        self.assertNotIn("news@boletim.com.br", emails)
        self.assertNotIn("ofertas@lojamega.com.br", emails)
        self.assertNotIn(DONO, emails)
        st, d = await self.chama("GET", "/contacts/resolve", q="maria")
        self.assertEqual(d["matches"][0]["email"], "maria@familia.com.br")
        st, d = await self.chama("GET", "/contacts/resolve", q="jose")           # sem acento acha "José"
        self.assertEqual(d["matches"][0]["email"], "jose@antigo.com.br")

    async def test_contatos_crud_e_vcard(self):
        st, d = await self.chama("POST", "/contacts", {"name": "Dona Zuleide", "email": "ZULEIDE@x.test", "phone": "11 99999-0000"})
        c = d["contact"]
        self.assertEqual(c["email"], "zuleide@x.test")
        st, d = await self.chama("POST", "/contacts/update", {"id": c["id"], "notes": "vizinha"})
        self.assertEqual(d["contact"]["notes"], "vizinha")
        st, vcf = await self.chama("GET", "/contacts/export")
        self.assertIn(b"Dona Zuleide", vcf)
        await self.chama("POST", "/contacts/delete", {"id": c["id"]})
        st, n = await self.chama("POST", "/contacts/import", {"vcf": vcf.decode()})
        self.assertEqual(n["imported"], 1)

    async def test_newsletters_agrupadas_com_link_de_saida(self):
        st, d = await self.chama("GET", "/newsletters")
        self.assertEqual(st, 200)
        ls = d["newsletters"]
        self.assertEqual(len(ls), 1)
        self.assertEqual(ls[0]["count"], 3)
        self.assertEqual(ls[0]["mailto"], "mailto:sair@boletim.com.br?subject=sair&body=quero%20sair")
        self.assertEqual(ls[0]["http"], "https://boletim.com.br/sair?id=42")
        self.nada_enviado()

    async def test_sair_da_lista_por_email_so_com_confirmacao(self):
        link = "mailto:sair@boletim.com.br?subject=sair&body=quero%20sair"
        st, d = await self.chama("POST", "/unsubscribe", {"link": link})
        self.assertEqual(st, 400)
        self.nada_enviado()
        st, d = await self.chama("POST", "/unsubscribe", {"link": link, "confirmado": True})
        self.assertEqual(st, 200)
        self.assertEqual(d["how"], "email")
        e = A.smtp.enviadas[0]
        self.assertEqual(e["para"], ["sair@boletim.com.br"])
        m = msg_decodificada(e["raw"])
        self.assertEqual(m["Subject"], "sair")
        self.assertEqual(m.get_body().get_content().strip(), "quero sair")

    async def test_sair_da_lista_por_link_so_devolve_o_link(self):
        st, d = await self.chama("POST", "/unsubscribe", {"link": "https://boletim.com.br/sair?id=42"})
        self.assertEqual((st, d["how"]), (200, "link"))
        self.nada_enviado()
        st, d = await self.chama("POST", "/unsubscribe", {"link": "javascript:alert(1)"})
        self.assertEqual(st, 400)
        st, d = await self.chama("POST", "/unsubscribe", {"link": "file:///c:/windows/win.ini"})
        self.assertEqual(st, 400)

    async def test_sair_da_lista_com_destino_malicioso_nao_injeta_cabecalho(self):
        link = "mailto:sair@boletim.com.br?subject=sair%0D%0ABcc:%20espiao@x.test"
        st, d = await self.chama("POST", "/unsubscribe", {"link": link, "confirmado": True})
        for e in A.smtp.enviadas:
            self.assertEqual(e["para"], ["sair@boletim.com.br"])
            self.assertNotIn(b"\nBcc:", e["raw"])

    async def test_baixar_anexo(self):
        m = (await self.chama("GET", "/message", uid=self.uid("cobranca")))[1]
        st, dados = await self.chama("GET", "/attachment", uid=self.uid("cobranca"), idx=m["attachments"][0]["idx"])
        self.assertEqual(st, 200)
        self.assertTrue(dados.startswith(b"%PDF"))
        r = await self.client.get("/attachment", params={"uid": self.uid("cobranca"), "idx": m["attachments"][0]["idx"]})
        self.assertIn('filename="boleto-outubro.pdf"', r.headers["Content-Disposition"])
        st, d = await self.chama("GET", "/attachment", uid=self.uid("cobranca"), idx=77)
        self.assertEqual(st, 404)

    async def test_nome_de_anexo_perigoso_nao_quebra_o_cabecalho(self):
        cru = (b"From: x@y.test\r\nTo: gui@falso.test\r\nSubject: anexo\r\nMIME-Version: 1.0\r\n"
               b"Content-Type: multipart/mixed; boundary=B\r\n\r\n--B\r\nContent-Type: text/plain\r\n\r\ntexto\r\n"
               b"--B\r\nContent-Type: application/pdf\r\n"
               b"Content-Disposition: attachment; filename*=utf-8''a%22b%0D%0AX-Evil%3A%201.pdf\r\n\r\nPDF\r\n--B--\r\n")
        self.caixa["msgs"].append(sf.Msg(900, cru))
        r = await self.client.get("/attachment", params={"uid": "900", "idx": 2})
        self.assertEqual(r.status, 200)
        self.assertNotIn("X-Evil", [k for k in r.headers])
        self.assertEqual(r.headers["Content-Disposition"].count("\n"), 0)

    async def test_ler_anexo_boleto_em_pdf(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("sem pypdf neste Python (o do Open WebUI tem)")
        m = (await self.chama("GET", "/message", uid=self.uid("cobranca")))[1]
        st, d = await self.chama("POST", "/attachment/read", {"uid": self.uid("cobranca"), "idx": m["attachments"][0]["idx"]})
        self.assertEqual(st, 200, d)
        self.assertEqual(len(d["boletos"]), 1)
        self.assertIn("Itau", d["boletos"][0])
        self.assertIn("1.234,56", d["boletos"][0])
        self.assertNotIn("NAO conferem", d["boletos"][0])
        self.assertEqual(d["summary"], "Resumo falso do e-mail.")

    async def test_ler_anexo_de_tipo_desconhecido_explica(self):
        m = (await self.chama("GET", "/message", uid=self.uid("grande")))[1]
        st, d = await self.chama("POST", "/attachment/read", {"uid": self.uid("grande"), "idx": m["attachments"][0]["idx"]})
        self.assertEqual(st, 422)
        self.assertIn("fotos-casamento.bin", d["error"])

    async def test_convite_vai_para_a_agenda(self):
        A.agenda.rotas[("POST", "/ics/import")] = lambda b: (200, {"imported": 1})
        st, d = await self.chama("POST", "/invite/add", {"uid": self.uid("convite"), "user_id": "u1"})
        self.assertEqual((st, d["imported"]), (200, 1))
        _m, _p, corpo = A.agenda.pedidos[-1]
        self.assertEqual(corpo["user_id"], "u1")
        self.assertIn("SUMMARY:Reuniao de alinhamento", corpo["ics"])

    async def test_convite_sem_agenda_no_ar_e_sem_convite(self):
        api.AGENDA_URL = "http://127.0.0.1:%d" % sf.porta_livre(9280, 9299)
        try:
            st, d = await self.chama("POST", "/invite/add", {"uid": self.uid("convite"), "user_id": "u1"})
        finally:
            api.AGENDA_URL = A.agenda.url
        self.assertEqual(st, 502)
        self.assertIn("Agenda", d["error"])
        st, d = await self.chama("POST", "/invite/add", {"uid": self.uid("pessoal"), "user_id": "u1"})
        self.assertEqual(st, 404)
        st, d = await self.chama("POST", "/invite/add", {"uid": self.uid("convite")})
        self.assertEqual(st, 400)

    async def test_ler_so_nunca_envia(self):
        """Tudo que le, resume, classifica ou rascunha deixa o SMTP intocado."""
        await self.chama("GET", "/inbox")
        await self.chama("GET", "/newsletters")
        for k in ("pessoal", "cobranca", "convite", "news1"):
            await self.chama("GET", "/message", uid=self.uid(k))
        st, d = await self.chama("POST", "/draft", uid=self.uid("thread3"))
        self.assertEqual(st, 200)
        self.assertEqual(d["draft"], "Olá! Obrigado pela mensagem. Respondo em breve.")
        self.nada_enviado()
        self.assertEqual(drafts.list_drafts(), [])


class EnvioApiTests(ApiBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.conecta()

    async def test_send_exige_confirmacao_explicita(self):
        corpo = {"to": "maria@familia.com.br", "subject": "Oi", "body": "Texto"}
        st, d = await self.chama("POST", "/send", corpo)
        self.assertEqual(st, 400)
        self.assertIn("confirm", d["error"].lower())
        self.nada_enviado()
        st, d = await self.chama("POST", "/send", dict(corpo, confirmado="sim"))      # so' true de verdade
        self.assertEqual(st, 400)
        self.nada_enviado()
        st, d = await self.chama("POST", "/send", dict(corpo, confirmado=True))
        self.assertEqual(st, 200)
        self.assertEqual(len(A.smtp.enviadas), 1)

    async def test_send_valida_campos(self):
        for corpo in ({}, {"to": "x"}, {"to": "sem-arroba", "subject": "a", "body": "b", "confirmado": True},
                      {"to": "a@b.test", "subject": "", "body": "b", "confirmado": True}):
            st, d = await self.chama("POST", "/send", corpo)
            self.assertEqual(st, 400, corpo)
        self.nada_enviado()

    async def test_send_erro_do_servidor_vira_502_legivel(self):
        A.smtp.recusa = {"x@y.test"}
        st, d = await self.chama("POST", "/send", {"to": "x@y.test", "subject": "a", "body": "b", "confirmado": True})
        self.assertEqual(st, 502)
        self.assertIn("x@y.test", d["error"])

    async def test_rascunho_do_chat_nao_envia_sozinho(self):
        st, d = await self.chama("POST", "/drafts", {"to": "maria@familia.com.br", "subject": "Fatura", "body": "Oi", "origem": "chat"})
        self.assertEqual(d["draft"]["status"], "pendente")
        await asyncio.sleep(0)
        await api._tick()                              # o relogio do agendador passa
        self.nada_enviado()
        st, d = await self.chama("GET", "/drafts")
        self.assertEqual(d["drafts"][0]["status"], "pendente")

    async def test_enviar_rascunho_exige_confirmacao(self):
        d = (await self.chama("POST", "/drafts", {"to": "maria@familia.com.br", "subject": "Fatura", "body": "Oi"}))[1]["draft"]
        st, r = await self.chama("POST", "/drafts/send", {"id": d["id"]})
        self.assertEqual(st, 400)
        self.nada_enviado()
        st, r = await self.chama("POST", "/drafts/send", {"id": d["id"], "confirmado": True})
        self.assertEqual(st, 200)
        self.assertEqual(len(A.smtp.enviadas), 1)
        self.assertEqual(drafts.get(d["id"])["status"], "enviado")

    async def test_rascunho_nao_e_enviado_duas_vezes(self):
        d = (await self.chama("POST", "/drafts", {"to": "maria@familia.com.br", "subject": "Fatura", "body": "Oi"}))[1]["draft"]
        await self.chama("POST", "/drafts/send", {"id": d["id"], "confirmado": True})
        st, r = await self.chama("POST", "/drafts/send", {"id": d["id"], "confirmado": True})
        self.assertEqual(st, 409)
        self.assertEqual(len(A.smtp.enviadas), 1)

    async def test_cliques_juntos_no_enviar_mandam_uma_vez_so(self):
        d = (await self.chama("POST", "/drafts", {"to": "maria@familia.com.br", "subject": "Fatura", "body": "Oi"}))[1]["draft"]
        rs = await asyncio.gather(*[self.chama("POST", "/drafts/send", {"id": d["id"], "confirmado": True}) for _ in range(3)])
        self.assertEqual(sorted(st for st, _d in rs), [200, 409, 409])
        self.assertEqual(len(A.smtp.enviadas), 1)

    async def test_falha_no_envio_deixa_o_rascunho_com_erro_e_tenta_de_novo_so_a_pedido(self):
        d = (await self.chama("POST", "/drafts", {"to": "x@y.test", "subject": "a", "body": "b"}))[1]["draft"]
        A.smtp.recusa = {"x@y.test"}
        st, r = await self.chama("POST", "/drafts/send", {"id": d["id"], "confirmado": True})
        self.assertEqual(st, 502)
        self.assertEqual(drafts.get(d["id"])["status"], "erro")
        await api._tick()
        self.assertEqual(A.smtp.enviadas, [])
        A.smtp.recusa = set()
        st, r = await self.chama("POST", "/drafts/send", {"id": d["id"], "confirmado": True})
        self.assertEqual(st, 200)

    async def test_agendado_sai_na_hora_certa_e_so_o_agendado(self):
        a = (await self.chama("POST", "/drafts", {"to": "a@x.test", "subject": "agendado", "body": "b"}))[1]["draft"]
        b = (await self.chama("POST", "/drafts", {"to": "b@x.test", "subject": "pendente", "body": "b"}))[1]["draft"]
        st, r = await self.chama("POST", "/drafts/schedule", {"id": a["id"], "send_at": int(time.time()) - 5,
                                                              "confirmado": True})
        self.assertEqual(st, 400)
        st, r = await self.chama("POST", "/drafts/schedule", {"id": a["id"], "send_at": int(time.time()) + 3600})
        self.assertEqual(st, 400)                                   # sem confirmado: nao agenda
        self.assertEqual(drafts.get(a["id"])["status"], "pendente")
        st, r = await self.chama("POST", "/drafts/schedule", {"id": a["id"], "send_at": int(time.time()) + 3600,
                                                              "confirmado": True})
        self.assertEqual(r["draft"]["status"], "agendado")
        await api._tick()
        self.nada_enviado()                      # ainda nao chegou a hora
        drafts.update(a["id"], {"send_at": int(time.time()) - 1})
        await api._tick()
        await api._tick()                        # e o relogio seguinte nao repete
        self.assertEqual([e["para"] for e in A.smtp.enviadas], [["a@x.test"]])
        self.assertEqual(drafts.get(b["id"])["status"], "pendente")
        self.assertEqual(drafts.get(a["id"])["status"], "enviado")

    async def test_agendar_rascunho_ja_enviado_e_recusado(self):
        d = (await self.chama("POST", "/drafts", {"to": "a@x.test", "subject": "s", "body": "b"}))[1]["draft"]
        await self.chama("POST", "/drafts/send", {"id": d["id"], "confirmado": True})
        st, r = await self.chama("POST", "/drafts/schedule", {"id": d["id"], "send_at": int(time.time()) + 600,
                                                              "confirmado": True})
        self.assertEqual(st, 409)
        await api._tick()
        self.assertEqual(len(A.smtp.enviadas), 1)

    async def test_editar_nao_muda_o_status_nem_o_estado_de_envio(self):
        d = (await self.chama("POST", "/drafts", {"to": "a@x.test", "subject": "s", "body": "b"}))[1]["draft"]
        st, r = await self.chama("POST", "/drafts/update", {"id": d["id"], "body": "novo", "status": "enviado", "send_at": 1})
        self.assertEqual(r["draft"]["body"], "novo")
        self.assertEqual(r["draft"]["status"], "pendente")
        await api._tick()
        self.nada_enviado()

    async def test_rascunho_valida_destino(self):
        st, r = await self.chama("POST", "/drafts", {"to": "sem-arroba", "subject": "s", "body": "b"})
        self.assertEqual(st, 400)

    async def test_rascunho_sai_pela_conta_dele(self):
        await self.conecta(user=OUTRO, app_password=SENHA2)
        d = (await self.chama("POST", "/drafts", {"to": "a@x.test", "subject": "s", "body": "b", "account": OUTRO}))[1]["draft"]
        await self.chama("POST", "/drafts/send", {"id": d["id"], "confirmado": True})
        self.assertEqual(A.smtp.enviadas[0]["de"], OUTRO)

    async def test_apagar_rascunho(self):
        d = (await self.chama("POST", "/drafts", {"to": "a@x.test", "subject": "s", "body": "b"}))[1]["draft"]
        await self.chama("POST", "/drafts/delete", {"id": d["id"]})
        self.assertEqual(drafts.list_drafts(), [])


# ================================================================ e-mail pelo chat

# ================================================================ Agenda (a de verdade) e tarefas agendadas

class AgendaTests(ApiBase):
    """O e-mail conversa com a Agenda do Nous: convites (.ics) e tarefas 'resuma meus e-mails'."""

    async def asyncSetUp(self):
        sys.path.insert(0, os.path.join(os.path.dirname(EMAIL_DIR), "agenda"))
        try:
            import nous_agenda_api as ag
            import agenda_tasks as tarefas
        except ImportError as e:
            self.skipTest("faltam dependencias da Agenda: %s" % e)
        await super().asyncSetUp()
        self.tarefas = tarefas
        self.ag_server = TestServer(ag.build_app(), port=sf.porta_livre())
        self.ag_client = TestClient(self.ag_server)
        await self.ag_client.start_server()
        self.agenda_antes = (api.AGENDA_URL, tarefas.EMAIL_URL, tarefas.OLLAMA_URL)
        api.AGENDA_URL = "http://127.0.0.1:%d" % self.ag_server.port
        tarefas.EMAIL_URL = "http://127.0.0.1:%d" % self.server.port
        tarefas.OLLAMA_URL = A.ollama.url
        await self.conecta()

    async def asyncTearDown(self):
        if hasattr(self, "ag_client"):
            await self.ag_client.close()
            api.AGENDA_URL, self.tarefas.EMAIL_URL, self.tarefas.OLLAMA_URL = self.agenda_antes
        await super().asyncTearDown()

    async def test_convite_chega_na_agenda_de_verdade(self):
        st, d = await self.chama("POST", "/invite/add", {"uid": self.uid("convite"), "user_id": "u1"})
        self.assertEqual((st, d["imported"]), (200, 1), d)
        r = await self.ag_client.get("/events", params={"user_id": "u1", "from": 1793000000, "to": 1794000000})
        evs = (await r.json())["events"]
        self.assertEqual([e["title"] for e in evs], ["Reuniao de alinhamento"])

    async def test_tarefa_resumo_de_emails_usa_modelo_local_e_a_caixa(self):
        A.ollama.modelos = [{"name": "gpt-oss:120b-cloud"}, {"name": "qwen3:4b"}]
        cx = self.tarefas.db.connect()
        try:
            texto = await asyncio.to_thread(self.tarefas.run_task, cx, {"kind": "emails", "prompt": "", "user_id": "u1"})
        finally:
            cx.close()
        self.assertEqual(texto, "ok")
        _m, _p, corpo = next(x for x in reversed(A.ollama.pedidos) if x[1] == "/api/generate")
        self.assertEqual(corpo["model"], "qwen3:4b")
        self.assertIn("Fatura de outubro", corpo["prompt"])
        self.nada_enviado()

    async def test_tarefa_que_manda_por_email_manda_so_para_a_propria_conta(self):
        ok = await asyncio.to_thread(self.tarefas.send_email_to_self, "[Nous] Resumo", "Bom dia!")
        self.assertTrue(ok)
        self.assertEqual([e["para"] for e in A.smtp.enviadas], [[DONO]])
        self.assertEqual(msg_decodificada(A.smtp.enviadas[0]["raw"])["Subject"], "[Nous] Resumo")

    async def test_tarefa_sem_email_conectado_nao_envia(self):
        await self.chama("POST", "/disconnect", {})
        ok = await asyncio.to_thread(self.tarefas.send_email_to_self, "[Nous] Resumo", "Bom dia!")
        self.assertFalse(ok)
        self.nada_enviado()


# ================================================================ a tela nao envia sem perguntar

class TelaTests(unittest.TestCase):
    def test_todo_envio_da_tela_leva_confirmacao(self):
        js = open(os.path.join(os.path.dirname(EMAIL_DIR), "branding", "modules", "email.js"), encoding="utf-8").read()
        import re
        chamadas = re.findall(r"api\('POST', '(/(?:send|drafts/send|drafts/schedule|unsubscribe))'[^\n]*", js)
        self.assertGreaterEqual(len(chamadas), 4)
        for linha in re.findall(r"api\('POST', '/(?:send|drafts/send|drafts/schedule|unsubscribe)'[^\n]*", js):
            self.assertIn("confirmado: true", linha, linha)

    def test_so_a_agenda_e_a_tela_chamam_o_envio(self):
        raiz = os.path.dirname(EMAIL_DIR)
        achados = []
        for pasta in ("agenda", "utilidades", "monitor", "memory", "skills", "history", "documentos", "branding"):
            for dp, _d, fs in os.walk(os.path.join(raiz, pasta)):
                if "node_modules" in dp:
                    continue
                for f in fs:
                    if f.endswith((".py", ".js")):
                        t = open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read()
                        if "8995" in t and "/send" in t:
                            achados.append(f)
        self.assertEqual(sorted(achados), ["agenda_tasks.py", "email.js"])


def _carrega_filtro():
    try:
        import pydantic  # noqa: F401
    except ImportError:                    # o Open WebUI tem; aqui basta um substituto minimo
        import types

        class BaseModel:
            def __init__(self, **kw):
                for k in getattr(type(self), "__annotations__", {}):
                    setattr(self, k, kw.get(k, getattr(type(self), k, None)))

        mod = types.ModuleType("pydantic")
        mod.BaseModel, mod.Field = BaseModel, (lambda default=None, **kw: default)
        sys.modules["pydantic"] = mod
    spec = importlib.util.spec_from_file_location("nous_email_chat_teste", os.path.join(EMAIL_DIR, "nous_email_chat.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class ChatTests(ApiBase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.mod = _carrega_filtro()
        self.f = self.mod.Filter()
        self.f.valves.EMAIL_URL = "http://127.0.0.1:%d" % self.server.port
        self.f.valves.OLLAMA_URL = A.ollama.url
        self.user = {"id": "u1"}

    def pedido(self, texto):
        return {"model": "qwen3:4b", "messages": [{"role": "user", "content": texto}]}

    async def inlet(self, texto):
        body = await self.f.inlet(self.pedido(texto), self.user)
        return body["messages"][0]["content"] if body["messages"][0]["role"] == "system" else ""

    async def test_sem_conta_explica_como_conectar(self):
        sistema = await self.inlet("manda um email pra Maria cobrando a fatura")
        self.assertIn("nenhuma conta", sistema)
        self.assertIn("Assistente de Email", sistema)

    async def test_conversa_comum_passa_batido(self):
        body = await self.f.inlet(self.pedido("qual a capital da França?"), self.user)
        self.assertEqual(len(body["messages"]), 1)

    async def test_pedido_de_envio_vira_rascunho_e_nada_e_enviado(self):
        await self.conecta()
        await self.chama("GET", "/inbox")                      # aprende a Maria
        sistema = await self.inlet("manda um email pra Maria cobrando a fatura")
        self.assertIn("Maria Souza <maria@familia.com.br>", sistema)
        self.assertIn("Assunto:", sistema)
        resposta = {"model": "qwen3:4b", "messages": [
            {"role": "user", "content": "manda um email pra Maria cobrando a fatura"},
            {"role": "assistant", "content": "Assunto: Fatura em aberto\n\nOi, Maria! Tudo bem?\nPode me mandar a fatura de outubro?\n\nAbraço,\nGui"}]}
        out = await self.f.outlet(resposta, self.user)
        self.assertIn("Rascunho salvo, nada foi enviado", out["messages"][-1]["content"])
        ds = drafts.list_drafts()
        self.assertEqual(len(ds), 1)
        self.assertEqual((ds[0]["to"], ds[0]["subject"], ds[0]["status"], ds[0]["origem"]),
                         ("maria@familia.com.br", "Fatura em aberto", "pendente", "chat"))
        self.assertIn("Pode me mandar a fatura", ds[0]["body"])
        self.nada_enviado()
        # regenerar a resposta nao duplica o rascunho
        self.f._pending["u1"] = (time.time(), {"email": "maria@familia.com.br", "name": "Maria Souza"})
        await self.f.outlet(resposta, self.user)
        self.assertEqual(len(drafts.list_drafts()), 1)
        await api._tick()
        self.nada_enviado()

    async def test_endereco_escrito_na_mensagem(self):
        await self.conecta()
        sistema = await self.inlet("escreve um e-mail para joao.silva@empresa.com.br sobre a reuniao")
        self.assertIn("joao.silva@empresa.com.br", sistema)

    async def test_contato_desconhecido_pede_o_endereco(self):
        await self.conecta()
        sistema = await self.inlet("manda um email pra Zuleide")
        self.assertIn("nao esta nos contatos", sistema)
        self.assertEqual(self.f._pending, {})

    async def test_dois_contatos_com_o_mesmo_nome_pergunta_qual(self):
        await self.conecta()
        await self.chama("POST", "/contacts", {"name": "Carlos Lima", "email": "carlos@empresa.com.br"})
        await self.chama("POST", "/contacts", {"name": "Carlos Dias", "email": "carlos.dias@outra.test"})
        sistema = await self.inlet("manda um email pro Carlos")
        self.assertIn("mais de um contato", sistema)
        out = await self.f.outlet({"messages": [{"role": "assistant", "content": "Qual deles?"}]}, self.user)
        self.assertIn("⟦opcao:", out["messages"][-1]["content"])
        self.assertEqual(drafts.list_drafts(), [])

    async def test_resposta_sem_assunto_nao_vira_rascunho(self):
        await self.conecta()
        await self.chama("POST", "/contacts", {"name": "Maria Souza", "email": "maria@familia.com.br"})
        await self.inlet("manda um email pra Maria")
        out = await self.f.outlet({"messages": [{"role": "assistant", "content": "Claro! Sobre o que quer falar?"}]}, self.user)
        self.assertEqual(drafts.list_drafts(), [])
        self.assertNotIn("Rascunho salvo", out["messages"][-1]["content"])

    async def test_caixa_de_entrada_pelo_chat(self):
        await self.conecta()
        sistema = await self.inlet("o que chegou de importante nos meus emails?")
        self.assertIn("[Importante]", sistema)
        self.assertIn("Fatura de outubro", sistema)
        self.assertIn("[Spam]", sistema)
        self.nada_enviado()

    async def test_modelo_de_nuvem_no_chat_nao_ve_os_emails(self):
        await self.conecta()
        A.ollama.modelos = [{"name": "qwen3:4b"}, {"name": "gpt-oss:120b-cloud"}]
        for modelo in ("gpt-oss:120b-cloud", "openrouter/x-ai/grok", "gpt-4o"):
            body = {"model": modelo, "messages": [{"role": "user", "content": "o que chegou de importante nos meus emails?"}]}
            out = await self.f.inlet(body, self.user)
            sistema = out["messages"][0]["content"]
            self.assertIn("nuvem", sistema, modelo)
            self.assertNotIn("Fatura de outubro", sistema, modelo)

    async def test_servico_de_email_fora_do_ar(self):
        self.f.valves.EMAIL_URL = "http://127.0.0.1:%d" % sf.porta_livre(9280, 9299)
        sistema = await self.inlet("manda um email pra Maria")
        self.assertIn("nao esta no ar", sistema)
        self.assertIn("Nada foi enviado", sistema)

    async def test_frases_que_disparam(self):
        for frase in ("manda um e-mail pra Maria", "envie um email para o João", "escreva um email ao Carlos",
                      "prepare um e-mail para o chefe", "faça um email para a Ana"):
            self.assertTrue(self.mod._SEND.search(frase), frase)
        for frase in ("meus e-mails", "tenho algum email novo?", "chegou algum email?", "minha caixa de entrada"):
            self.assertTrue(self.mod._INBOX.search(frase), frase)
        for frase in ("o que é um email?", "como configurar o Outlook"):
            self.assertFalse(self.mod._SEND.search(frase) or self.mod._INBOX.search(frase), frase)


import asyncio  # noqa: E402  (usado pelos testes assincronos acima)

if __name__ == "__main__":
    unittest.main()
