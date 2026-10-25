# -*- coding: utf-8 -*-
"""
Servidor de e-mail de mentira para os testes do Assistente de E-mail.

Um IMAP4rev1 minimo (so' o que o Nous usa: LOGIN, EXAMINE/SELECT, UID SEARCH,
UID FETCH, LOGOUT) e um SMTP que so' guarda as mensagens (EHLO, STARTTLS ou SSL
direto, AUTH PLAIN/LOGIN, MAIL, RCPT, DATA). Tudo em TLS, com o certificado de
teste de cert/ (o teste aponta SSL_CERT_FILE para ele), so' em 127.0.0.1 e so'
na biblioteca padrao. Nenhum dado sai da maquina.
"""
import os
import re
import ssl
import time
import base64
import socket
import socketserver
import threading

AQUI = os.path.dirname(os.path.abspath(__file__))
CERT = os.path.join(AQUI, "cert", "certificado-de-teste.pem")
CHAVE = os.path.join(AQUI, "cert", "chave-de-teste.pem")


def porta_livre(inicio=9200, fim=9299):
    """Primeira porta livre da faixa reservada aos testes (9200-9299)."""
    for p in range(inicio, fim + 1):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError("sem porta livre em 9200-9299")


def _contexto():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, CHAVE)
    return ctx


class _Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    # sem barulho de traceback quando o cliente larga a conexao no meio
    def handle_error(self, request, client_address):
        pass


class _Base:
    """Liga/desliga um servidor numa thread."""
    handler = None

    def __init__(self, porta=None, ssl_direto=True):
        self.porta = porta or porta_livre()
        self.ssl_direto = ssl_direto
        self.modo = "normal"        # normal | travado (nao responde) | derruba (fecha na hora)
        self.conexoes = 0
        self.ctx = _contexto()
        dono = self

        class H(self.handler):
            srv = dono
        self._srv = _Servidor(("127.0.0.1", self.porta), H)
        self._t = threading.Thread(target=self._srv.serve_forever, daemon=True)

    def start(self):
        self._t.start()
        return self

    def stop(self):
        self._srv.shutdown()
        self._srv.server_close()


# ---------------------------------------------------------------- IMAP

class Msg:
    def __init__(self, uid, raw, flags=()):
        self.uid, self.raw, self.flags = uid, raw, set(flags)


class _ImapH(socketserver.StreamRequestHandler):
    srv = None

    def setup(self):
        self.request.settimeout(30)
        if self.srv.ssl_direto:
            self.request = self.srv.ctx.wrap_socket(self.request, server_side=True)
        super().setup()

    def finish(self):
        try:
            super().finish()
        finally:
            try:
                self.request.close()
            except Exception:
                pass

    def say(self, b):
        if isinstance(b, str):
            b = b.encode("utf-8")
        self.wfile.write(b)
        self.wfile.flush()

    def handle(self):
        s = self.srv
        s.conexoes += 1
        if s.modo == "derruba":
            return
        if s.modo == "travado":
            time.sleep(8)
            return
        self.user = None
        self.somente_leitura = True
        self.say("* OK [CAPABILITY IMAP4rev1] Nous servidor falso\r\n")
        while True:
            line = self.rfile.readline()
            if not line:
                return
            line = line.rstrip(b"\r\n")
            # literal sincronizado ({n}) no fim da linha: pede e le os bytes
            while True:
                m = re.search(rb"\{(\d+)\}$", line)
                if not m:
                    break
                self.say("+ pode mandar\r\n")
                line = line[:m.start()] + b'"' + self.rfile.read(int(m.group(1))).replace(b"\\", b"\\\\").replace(b'"', b'\\"') + b'"' \
                    + self.rfile.readline().rstrip(b"\r\n")
            txt = line.decode("utf-8", errors="replace")
            parts = txt.split(" ", 2)
            if len(parts) < 2:
                self.say("* BAD comando vazio\r\n")
                continue
            tag, cmd = parts[0], parts[1].upper()
            args = parts[2] if len(parts) > 2 else ""
            s.comandos.append(cmd if cmd != "LOGIN" else "LOGIN")  # nunca guarda a senha
            if cmd == "CAPABILITY":
                self.say("* CAPABILITY IMAP4rev1\r\n%s OK ok\r\n" % tag)
            elif cmd == "NOOP":
                self.say("%s OK ok\r\n" % tag)
            elif cmd == "LOGIN":
                u, p = self._login_args(args)
                caixa = s.contas.get(u)
                if s.rejeita_tudo or not caixa or caixa["senha"] != p:
                    self.say('%s NO [AUTHENTICATIONFAILED] Invalid credentials (Failure)\r\n' % tag)
                else:
                    self.user = u
                    self.say("%s OK Logged in\r\n" % tag)
            elif cmd == "LOGOUT":
                self.say("* BYE ate logo\r\n%s OK Logout completed\r\n" % tag)
                return
            elif not self.user:
                self.say("%s NO precisa fazer login\r\n" % tag)
            elif cmd in ("SELECT", "EXAMINE"):
                self.somente_leitura = cmd == "EXAMINE"
                caixa = s.contas[self.user]["msgs"]
                self.say("* %d EXISTS\r\n* 0 RECENT\r\n* FLAGS (\\Seen \\Answered \\Flagged \\Deleted \\Draft)\r\n"
                         "%s OK [%s] %s completed\r\n" % (len(caixa), tag, "READ-ONLY" if self.somente_leitura else "READ-WRITE", cmd))
            elif cmd == "UID":
                sub, _, resto = args.partition(" ")
                sub = sub.upper()
                if sub == "SEARCH":
                    uids = [str(m.uid) for m in s.contas[self.user]["msgs"]]
                    self.say("* SEARCH %s\r\n%s OK SEARCH completed\r\n" % (" ".join(uids), tag))
                elif sub == "FETCH":
                    self._fetch(tag, resto)
                else:
                    self.say("%s BAD UID %s nao suportado\r\n" % (tag, sub))
            else:
                self.say("%s BAD comando %s nao suportado\r\n" % (tag, cmd))

    def _login_args(self, args):
        toks = re.findall(r'"((?:[^"\\]|\\.)*)"|(\S+)', args)
        vals = [(a if a != "" or not b else b) for a, b in toks]
        vals = [re.sub(r"\\(.)", r"\1", v) for v in vals]
        return (vals + ["", ""])[:2]

    def _fetch(self, tag, resto):
        s = self.srv
        m = re.match(r"(\S+) \((.*)\)\s*$", resto)
        if not m:
            self.say("%s BAD FETCH mal formado\r\n" % tag)
            return
        quais = {u for u in self._uids(m.group(1), s.contas[self.user]["msgs"])}
        itens = re.findall(r"BODY(?:\.PEEK)?\[[^\]]*\](?:<\d+\.\d+>)?|[A-Z0-9.]+", m.group(2))
        for i, msg in enumerate(s.contas[self.user]["msgs"], 1):
            if msg.uid not in quais:
                continue
            ini, fim, flags_dep = ["UID %d" % msg.uid], [], None
            for it in itens:
                itu = it.upper()
                if itu == "UID":
                    continue
                if itu == "FLAGS":
                    f = "FLAGS (%s)" % " ".join(sorted(msg.flags))
                    if s.flags_depois:
                        flags_dep = f
                    else:
                        ini.append(f)
                elif itu == "RFC822.SIZE":
                    ini.append("RFC822.SIZE %d" % len(msg.raw))
                elif itu in ("RFC822", "BODY[]", "BODY.PEEK[]"):
                    fim.append(("RFC822" if itu == "RFC822" else "BODY[]", msg.raw))
                    if not self.somente_leitura and itu != "BODY.PEEK[]":
                        msg.flags.add("\\Seen")
                        s.marcou_lido.append(msg.uid)
                elif itu.startswith("BODY"):
                    sec = re.search(r"\[(.*)\]", it).group(1)
                    cab, _, corpo = msg.raw.partition(b"\r\n\r\n")
                    if sec.upper().startswith("HEADER.FIELDS"):
                        campos = {c.upper() for c in re.search(r"\((.*)\)", sec).group(1).split()}
                        saida, atual = [], False
                        for l in cab.split(b"\r\n"):
                            if l[:1] in (b" ", b"\t"):
                                if atual:
                                    saida.append(l)
                                continue
                            nome = l.split(b":", 1)[0].decode("ascii", "replace").upper()
                            atual = nome in campos
                            if atual:
                                saida.append(l)
                        dados = b"\r\n".join(saida) + b"\r\n\r\n"
                        nome = "BODY[%s]" % sec
                    elif sec.upper() == "TEXT":
                        dados = corpo
                        nome = "BODY[TEXT]"
                        rec = re.search(r"<(\d+)\.(\d+)>", it)
                        if rec:
                            a, n = int(rec.group(1)), int(rec.group(2))
                            dados = dados[a:a + n]
                            nome += "<%d>" % a
                    else:
                        dados, nome = msg.raw, "BODY[%s]" % sec
                    fim.append((nome, dados))
            s.bytes_fetch += sum(len(d) for _n, d in fim)
            out = "* %d FETCH (%s" % (i, " ".join(ini))
            self.say(out)
            for n, d in fim:
                self.say(" %s {%d}\r\n" % (n, len(d)))
                self.say(d)
            if flags_dep:
                self.say(" " + flags_dep)
            self.say(")\r\n")
        self.say("%s OK Fetch completed\r\n" % tag)

    @staticmethod
    def _uids(conjunto, msgs):
        todos = [m.uid for m in msgs]
        out = []
        for pedaco in conjunto.split(","):
            if ":" in pedaco:
                a, b = pedaco.split(":")
                a = int(a)
                b = max(todos) if b == "*" else int(b)
                out += [u for u in todos if a <= u <= b]
            elif pedaco.isdigit():
                out.append(int(pedaco))
        return out


class ImapFalso(_Base):
    handler = _ImapH

    def __init__(self, contas, porta=None, ssl_direto=True):
        """contas: {usuario: {"senha": ..., "msgs": [Msg, ...]}}"""
        super().__init__(porta, ssl_direto)
        self.contas = contas
        self.rejeita_tudo = False
        self.flags_depois = False   # FLAGS depois do literal (como alguns servidores fazem)
        self.comandos = []
        self.bytes_fetch = 0
        self.marcou_lido = []


# ---------------------------------------------------------------- SMTP

class _SmtpH(socketserver.StreamRequestHandler):
    srv = None

    def setup(self):
        self.request.settimeout(30)
        if self.srv.ssl_direto:
            self.request = self.srv.ctx.wrap_socket(self.request, server_side=True)
        super().setup()

    def finish(self):
        try:
            super().finish()
        finally:
            try:
                self.request.close()
            except Exception:
                pass

    def say(self, t):
        self.wfile.write(t.encode("utf-8"))
        self.wfile.flush()

    def handle(self):
        s = self.srv
        s.conexoes += 1
        if s.modo == "derruba":
            return
        if s.modo == "travado":
            time.sleep(8)
            return
        self.say("220 nous.falso ESMTP pronto\r\n")
        auth, remetente, dest = None, None, []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            txt = line.decode("utf-8", errors="replace").rstrip("\r\n")
            cmd = txt.split(" ", 1)[0].upper()
            if cmd == "EHLO":
                ext = ["250-nous.falso", "250-8BITMIME", "250-SMTPUTF8"]
                if not s.ssl_direto and not isinstance(self.request, ssl.SSLSocket):
                    ext.append("250-STARTTLS")
                ext.append("250 AUTH PLAIN LOGIN")
                self.say("\r\n".join(ext) + "\r\n")
            elif cmd == "HELO":
                self.say("250 nous.falso\r\n")
            elif cmd == "STARTTLS":
                self.say("220 pode comecar o TLS\r\n")
                self.request = s.ctx.wrap_socket(self.request, server_side=True)
                self.rfile = self.request.makefile("rb")
                self.wfile = self.request.makefile("wb", 0)
            elif cmd == "AUTH":
                p = txt.split()
                mec = p[1].upper() if len(p) > 1 else ""
                if mec == "PLAIN":
                    cred = p[2] if len(p) > 2 else None
                    if cred is None:
                        self.say("334 \r\n")
                        cred = self.rfile.readline().decode().strip()
                    _a, u, pw = base64.b64decode(cred).decode("utf-8").split("\0")
                elif mec == "LOGIN":
                    self.say("334 VXNlcm5hbWU6\r\n")
                    u = base64.b64decode(self.rfile.readline().strip()).decode("utf-8")
                    self.say("334 UGFzc3dvcmQ6\r\n")
                    pw = base64.b64decode(self.rfile.readline().strip()).decode("utf-8")
                else:
                    self.say("504 mecanismo nao suportado\r\n")
                    continue
                c = s.contas.get(u)
                if s.rejeita_tudo or not c or c["senha"] != pw:
                    self.say("535 5.7.8 Username and Password not accepted\r\n")
                else:
                    auth = u
                    self.say("235 2.7.0 Autenticado\r\n")
            elif cmd == "MAIL":
                if s.exige_auth and not auth:
                    self.say("530 5.7.0 Autenticacao necessaria\r\n")
                    continue
                remetente = re.search(r"<([^>]*)>", txt).group(1)
                dest = []
                self.say("250 ok\r\n")
            elif cmd == "RCPT":
                a = re.search(r"<([^>]*)>", txt).group(1)
                if a.lower() in s.recusa:
                    self.say("550 5.1.1 Destinatario inexistente\r\n")
                else:
                    dest.append(a)
                    self.say("250 ok\r\n")
            elif cmd == "DATA":
                if not dest:
                    self.say("503 sem destinatario\r\n")
                    continue
                self.say("354 pode mandar, termine com <CRLF>.<CRLF>\r\n")
                linhas = []
                while True:
                    l = self.rfile.readline()
                    if l in (b".\r\n", b".\n", b""):
                        break
                    linhas.append(l[1:] if l.startswith(b"..") else l)
                s.enviadas.append({"auth": auth, "de": remetente, "para": list(dest), "raw": b"".join(linhas)})
                self.say("250 2.0.0 aceito para entrega\r\n")
            elif cmd == "RSET":
                dest = []
                self.say("250 ok\r\n")
            elif cmd == "NOOP":
                self.say("250 ok\r\n")
            elif cmd == "QUIT":
                self.say("221 ate logo\r\n")
                return
            else:
                self.say("502 comando nao suportado\r\n")


class SmtpFalso(_Base):
    handler = _SmtpH

    def __init__(self, contas, porta=None, ssl_direto=False):
        """ssl_direto=False: texto puro com STARTTLS (portas 587 e afins); True: SSL desde o inicio (465)."""
        super().__init__(porta, ssl_direto)
        self.contas = contas
        self.rejeita_tudo = False
        self.exige_auth = True
        self.recusa = set()
        self.enviadas = []
