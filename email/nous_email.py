# -*- coding: utf-8 -*-
"""
Cliente IMAP/SMTP para o Nous Email — stdlib pura (imaplib, smtplib, email).

Lê credenciais de NousData/.email_accounts.json.
Nunca loga a senha. Nunca envia sem chamada explícita.
Confere o certificado do servidor (TLS) e traduz os erros de rede para português.
"""
import imaplib
import smtplib
import ssl
import socket
import base64
import email
import html as _html
import json
import os
import re
from email.header import decode_header
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid
from typing import Optional

ACCOUNT_FILE = ".email_account.json"     # formato antigo (uma conta so')
ACCOUNTS_FILE = ".email_accounts.json"   # v2.8: {"padrao": user, "contas": {user: conta}}

# Tabela de detecção automática de IMAP/SMTP por domínio.
_AUTO = {
    "gmail.com":      {"imap": "imap.gmail.com",    "smtp": "smtp.gmail.com",     "imap_port": 993, "smtp_port": 465},
    "googlemail.com": {"imap": "imap.gmail.com",    "smtp": "smtp.gmail.com",     "imap_port": 993, "smtp_port": 465},
    "outlook.com":    {"imap": "outlook.office365.com", "smtp": "smtp.office365.com", "imap_port": 993, "smtp_port": 587},
    "hotmail.com":    {"imap": "outlook.office365.com", "smtp": "smtp.office365.com", "imap_port": 993, "smtp_port": 587},
    "live.com":       {"imap": "outlook.office365.com", "smtp": "smtp.office365.com", "imap_port": 993, "smtp_port": 587},
    "msn.com":        {"imap": "outlook.office365.com", "smtp": "smtp.office365.com", "imap_port": 993, "smtp_port": 587},
    "yahoo.com":      {"imap": "imap.mail.yahoo.com",   "smtp": "smtp.mail.yahoo.com", "imap_port": 993, "smtp_port": 465},
    "yahoo.com.br":   {"imap": "imap.mail.yahoo.com",   "smtp": "smtp.mail.yahoo.com", "imap_port": 993, "smtp_port": 465},
}


def _data_dir() -> str:
    for v in (os.environ.get("DATA_DIR"), os.environ.get("NOUS_DATA_DIR")):
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def _account_path() -> str:
    return os.path.join(_data_dir(), ACCOUNT_FILE)


def _accounts_path() -> str:
    return os.path.join(_data_dir(), ACCOUNTS_FILE)


def _read_store() -> dict:
    """{"padrao": user, "contas": {user: conta}}. Le o arquivo antigo (uma conta)
    se o novo ainda nao existe; a migracao acontece no proximo save."""
    try:
        with open(_accounts_path(), encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st.get("contas"), dict):
            return st
    except Exception:
        pass
    try:
        with open(_account_path(), encoding="utf-8") as f:
            old = json.load(f)
        if old.get("user"):
            return {"padrao": old["user"], "contas": {old["user"]: old}}
    except Exception:
        pass
    return {"padrao": None, "contas": {}}


def _write_store(st: dict) -> None:
    path = _accounts_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)
    os.replace(tmp, path)
    # Restringir permissões ao dono (best-effort no Windows)
    try:
        import stat
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
    try:  # migrado: o arquivo antigo (com senha) nao fica para tras
        os.remove(_account_path())
    except FileNotFoundError:
        pass


def list_accounts() -> list[dict]:
    st = _read_store()
    return [{"user": u, "padrao": u == st.get("padrao"), "imap": a.get("imap", "")}
            for u, a in st["contas"].items()]


def load_account(account: Optional[str] = None) -> Optional[dict]:
    st = _read_store()
    user = account or st.get("padrao") or next(iter(st["contas"]), None)
    return st["contas"].get(user) if user else None


def save_account(data: dict) -> None:
    st = _read_store()
    st["contas"][data["user"]] = data
    if not st.get("padrao") or st["padrao"] not in st["contas"]:
        st["padrao"] = data["user"]
    _write_store(st)


def set_default(account: str) -> bool:
    st = _read_store()
    if account not in st["contas"]:
        return False
    st["padrao"] = account
    _write_store(st)
    return True


def delete_account(account: Optional[str] = None) -> None:
    """Remove uma conta (ou todas, sem argumento)."""
    st = _read_store()
    if account:
        st["contas"].pop(account, None)
        if st.get("padrao") == account:
            st["padrao"] = next(iter(st["contas"]), None)
    if account and st["contas"]:
        _write_store(st)
        return
    for p in (_accounts_path(), _account_path()):
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def detect_servers(email_addr: str) -> dict:
    domain = email_addr.split("@")[-1].lower() if "@" in email_addr else ""
    return _AUTO.get(domain, {})


def _decode_header_str(val: str) -> str:
    parts = decode_header(val or "")
    out = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            try:
                out.append(chunk.decode(enc or "utf-8", errors="replace"))
            except Exception:
                out.append(chunk.decode("utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _strip_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        return " ".join(soup.get_text(" ").split())
    except Exception:
        html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1\s*>", " ", html)
        return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _decode_text(payload: bytes, charset: Optional[str]) -> str:
    """bytes -> texto. Charset que o Python nao conhece (x-unknown, unknown-8bit,
    comum em spam e e-mail antigo) cai em UTF-8 e, se nao der, em Windows-1252:
    antes virava corpo vazio."""
    try:
        return payload.decode(charset or "utf-8", errors="replace")
    except LookupError:
        try:
            return payload.decode("utf-8")
        except UnicodeDecodeError:
            return payload.decode("cp1252", errors="replace")


def _get_body(msg) -> str:
    """Extrai texto limpo da mensagem (preferir text/plain; fallback HTML)."""
    if msg.is_multipart():
        plain, html = "", ""
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition") or "")
            # Ignora anexos e arquivos inline (.txt/.html com filename) — só
            # queremos o corpo da mensagem, não um anexo de texto.
            if "attachment" in cd or part.get_filename():
                continue
            if ct not in ("text/plain", "text/html"):
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text = _decode_text(payload, part.get_content_charset())
            except Exception:
                continue
            if ct == "text/plain" and not plain:
                plain = text
            elif ct == "text/html" and not html:
                html = text
        return plain.strip() or _strip_html(html)
    else:
        ct = msg.get_content_type()
        if not ct.startswith("text/") or "attachment" in str(msg.get("Content-Disposition") or ""):
            return ""   # so' um PDF/imagem: nao ha' texto para mostrar
        try:
            payload = msg.get_payload(decode=True)
            text = _decode_text(payload or b"", msg.get_content_charset())
        except Exception:
            text = ""
        if ct == "text/html":
            return _strip_html(text)
        return text.strip()


# ---- conexao e erros em portugues -------------------------------------------

TIMEOUT = 20  # segundos: servidor que nao responde nao pode travar o Nous


def _ssl_ctx() -> ssl.SSLContext:
    """Contexto que CONFERE o certificado e o nome do servidor. O padrao do
    imaplib/smtplib nao confere nada: a senha iria para qualquer um no meio do
    caminho (Wi-Fi publico, por exemplo)."""
    return ssl.create_default_context()


def _texto_do_servidor(e) -> str:
    """Mensagem do servidor (que o imaplib/smtplib entregam como bytes) em texto."""
    partes = []
    for a in e.args:
        if isinstance(a, bytes):
            a = a.decode("utf-8", errors="replace")
        if isinstance(a, (str,)) and not a.isdigit():
            partes.append(a)
    return " ".join(" ".join(partes).split())


def _explica(e: Exception, host: str = "", port=None, o_que: str = "") -> str:
    """Erro de rede/servidor -> frase simples para o usuario (sem WinError, sem b'...')."""
    onde = f"{host}:{port}" if host and port else (host or "o servidor")
    if isinstance(e, ssl.SSLCertVerificationError):
        return (f"O certificado de segurança de {host or 'o servidor'} não é confiável (ou não é desse "
                "endereço). Por segurança o Nous não enviou sua senha. Confira o endereço do servidor; "
                "em rede de empresa ou escola, o antivírus ou o proxy pode estar interceptando a conexão.")
    if isinstance(e, socket.gaierror):
        return f"Não encontrei o servidor {host}. Confira o endereço e a conexão com a internet."
    if isinstance(e, (socket.timeout, TimeoutError)):
        return f"O servidor {onde} não respondeu a tempo. Tente de novo; se continuar, confira o endereço e a porta."
    if isinstance(e, ConnectionRefusedError):
        return (f"Não consegui conectar em {onde}. O servidor está fora do ar ou o endereço/porta "
                "está errado.")
    if isinstance(e, ssl.SSLError):
        return (f"Não consegui abrir a conexão segura com {onde}. A porta pode estar errada "
                f"(993 para receber e 465 ou 587 para enviar são as usuais) ({e.__class__.__name__}).")
    if isinstance(e, (ConnectionError, EOFError, imaplib.IMAP4.abort, smtplib.SMTPServerDisconnected)):
        return f"O servidor {onde} encerrou a conexão antes do fim. Tente de novo em instantes."
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        quem = ", ".join(f"{a} ({c} {m.decode('utf-8', 'replace') if isinstance(m, bytes) else m})"
                         for a, (c, m) in e.recipients.items())
        return f"O servidor recusou o destinatário: {quem}."
    if isinstance(e, smtplib.SMTPSenderRefused):
        return f"O servidor recusou o remetente {e.sender}: {_texto_do_servidor(e)}"
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return ("O servidor de envio recusou o e-mail ou a senha. Confira os dados e use a senha de "
                "aplicativo (não a senha normal da conta)." + _com_resposta(e))
    if isinstance(e, imaplib.IMAP4.error):
        return ("O servidor recusou o e-mail ou a senha. Confira os dados e use a senha de aplicativo "
                "(não a senha normal da conta)." + _com_resposta(e))
    if isinstance(e, smtplib.SMTPException):
        return f"O servidor de envio respondeu com erro: {_texto_do_servidor(e) or e.__class__.__name__}"
    if isinstance(e, OSError):
        return f"Não consegui conectar em {onde}: {e.strerror or e}"
    return str(e) or e.__class__.__name__


def _com_resposta(e) -> str:
    t = _texto_do_servidor(e)
    return f" (resposta do servidor: {t})" if t else ""


def _imap_connect(acc: dict) -> imaplib.IMAP4_SSL:
    host = acc["imap"]
    port = int(acc.get("imap_port", 993))
    conn = imaplib.IMAP4_SSL(host, port, ssl_context=_ssl_ctx(), timeout=TIMEOUT)
    conn._encoding = "utf-8"   # senha com acento (o padrao do imaplib e' ASCII e estoura)
    try:
        conn.login(acc["user"], acc["app_password"])
    except BaseException:
        _imap_logout(conn)
        raise
    return conn


def _imap_logout(conn) -> None:
    """Fecha a conexão IMAP sem nunca lançar (best-effort)."""
    if conn is None:
        return
    try:
        conn.logout()
    except Exception:
        try:
            conn.shutdown()
        except Exception:
            pass


def test_connection(acc: dict) -> tuple[bool, str]:
    """Valida credenciais IMAP. Retorna (ok, mensagem)."""
    try:
        conn = _imap_connect(acc)
        _imap_logout(conn)
        return True, "Conexão bem-sucedida."
    except Exception as e:
        return False, _explica(e, acc.get("imap", ""), acc.get("imap_port", 993))


def _smtp_open(acc: dict):
    """Conexão SMTP já autenticada. Porta 465 = SSL desde o início; as outras (587...)
    começam sem criptografia e sobem para TLS (STARTTLS). `smtp_security` ("ssl" ou
    "starttls") força um dos dois."""
    host = acc["smtp"]
    port = int(acc.get("smtp_port", 465))
    modo = acc.get("smtp_security") or ("ssl" if port == 465 else "starttls")
    if modo == "ssl":
        server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=_ssl_ctx())
    else:
        server = smtplib.SMTP(host, port, timeout=TIMEOUT)
    try:
        if modo != "ssl":
            server.ehlo()
            server.starttls(context=_ssl_ctx())
        _smtp_login(server, acc["user"], acc["app_password"])
    except BaseException:
        _smtp_close(server)
        raise
    return server


def _smtp_login(server, user: str, pwd: str) -> None:
    try:
        (user + pwd).encode("ascii")
    except UnicodeEncodeError:
        # smtplib.login() so' aceita ASCII; senha com acento vai por AUTH PLAIN em UTF-8
        server.ehlo_or_helo_if_needed()
        cred = base64.b64encode(f"\0{user}\0{pwd}".encode("utf-8")).decode("ascii")
        code, resp = server.docmd("AUTH", "PLAIN " + cred)
        if code != 235:
            raise smtplib.SMTPAuthenticationError(code, resp)
        return
    server.login(user, pwd)


def _smtp_close(server) -> None:
    # quit() envia QUIT e pode lançar se a conexão já estiver quebrada — close() não.
    if server is None:
        return
    try:
        server.quit()
    except Exception:
        try:
            server.close()
        except Exception:
            pass


def test_smtp(acc: dict) -> tuple[bool, str]:
    """Valida o servidor de envio (login, sem mandar nada)."""
    try:
        _smtp_close(_smtp_open(acc))
        return True, "Conexão bem-sucedida."
    except Exception as e:
        return False, _explica(e, acc.get("smtp", ""), acc.get("smtp_port", 465))


_LIST_HEADERS = ("FROM TO SUBJECT DATE MESSAGE-ID LIST-UNSUBSCRIBE LIST-ID PRECEDENCE AUTO-SUBMITTED "
                 "CONTENT-TYPE CONTENT-TRANSFER-ENCODING MIME-VERSION")
_SNIPPET_BYTES = 2500   # so' o comeco do corpo: nunca baixa anexo para listar


def _parse_fetch(data) -> list[dict]:
    """Respostas de um UID FETCH em lote -> [{uid, flags, hdr, txt}].
    Cada literal ({n}) chega como uma tupla do imaplib; FLAGS e UID podem vir
    antes ou depois dos literais, conforme o servidor."""
    out, cur = [], None
    for item in data or []:
        if isinstance(item, tuple):
            meta = item[0].decode("latin-1")
            if re.match(r"\s*\d+ \(", meta):
                cur = {"meta": "", "hdr": b"", "txt": b""}
                out.append(cur)
            if cur is None:
                continue
            cur["meta"] += " " + meta
            nome = re.search(r"(BODY\[[^\]]*\](?:<\d+>)?)\s*\{\d+\}\s*$", meta)
            if nome:
                n = nome.group(1).upper()
                if n.startswith("BODY[HEADER"):
                    cur["hdr"] = item[1]
                elif n.startswith("BODY[TEXT]"):
                    cur["txt"] = item[1]
        elif isinstance(item, bytes) and cur is not None:
            cur["meta"] += " " + item.decode("latin-1")
    res = []
    for c in out:
        u = re.search(r"\bUID (\d+)", c["meta"])
        f = re.search(r"\bFLAGS \(([^)]*)\)", c["meta"])
        if u:
            res.append({"uid": u.group(1), "flags": f.group(1) if f else "", "hdr": c["hdr"], "txt": c["txt"]})
    return res


def _snippet(hdr: bytes, txt: bytes) -> str:
    """Primeiras palavras do corpo (a IA da triagem le' isto)."""
    if not txt:
        return ""
    try:
        m = email.message_from_bytes(hdr.rstrip(b"\r\n") + b"\r\n\r\n" + txt)
        return " ".join(_get_body(m).split())[:300]
    except Exception:
        return ""


def list_recent(n: int = 20, account: Optional[str] = None) -> list[dict]:
    """Retorna os n emails mais recentes da caixa de entrada."""
    acc = load_account(account)
    if not acc:
        return []
    conn = None
    try:
        conn = _imap_connect(acc)
        conn.select("INBOX", readonly=True)
        # UID em vez de número de sequência: o UID é estável mesmo que outro
        # email seja apagado/movido entre a listagem e a abertura da mensagem.
        _, data = conn.uid("SEARCH", None, "ALL")
        uids = (data[0] or b"").split()
        uids = uids[-n:][::-1]  # os mais recentes primeiro
        if not uids:
            return []
        # um unico pedido para todos (80 idas e voltas eram lentas em servidor de verdade)
        _, raw = conn.uid("FETCH", b",".join(uids),
                          f"(RFC822.SIZE FLAGS BODY.PEEK[HEADER.FIELDS ({_LIST_HEADERS})] "
                          f"BODY.PEEK[TEXT]<0.{_SNIPPET_BYTES}>)")
        por_uid = {r["uid"]: r for r in _parse_fetch(raw)}
        msgs = []
        for uid in (u.decode() for u in uids):
            r = por_uid.get(uid)
            if not r:
                continue
            msg = email.message_from_bytes(r["hdr"])
            msgs.append({
                "uid": uid,
                "account": acc["user"],
                "from": _decode_header_str(msg.get("From", "")),
                "to": _decode_header_str(msg.get("To", "")),
                "subject": _decode_header_str(msg.get("Subject", "") or "(sem assunto)"),
                "date": msg.get("Date", ""),
                "message_id": msg.get("Message-ID", ""),
                "unread": "\\Seen" not in r["flags"],
                # Newsletter/lista: RFC 2369 + cabecalhos de envio automatico
                "list_unsubscribe": " ".join(_decode_header_str(str(msg.get("List-Unsubscribe", ""))).split()),
                "bulk": bool(msg.get("List-Id") or str(msg.get("Precedence", "")).lower() in ("bulk", "list")
                             or str(msg.get("Auto-Submitted", "no")).lower() != "no"),
                "snippet": _snippet(r["hdr"], r["txt"]),
                "category": None,
                "summary": None,
            })
        return msgs
    except Exception as e:
        return [{"error": _explica(e, acc.get("imap", ""), acc.get("imap_port", 993))}]
    finally:
        _imap_logout(conn)


def _fetch(uid: str, account: Optional[str]):
    acc = load_account(account)
    if not acc:
        raise RuntimeError("sem conta configurada")
    conn = None
    try:
        conn = _imap_connect(acc)
        conn.select("INBOX", readonly=True)
        # UID FETCH: o uid recebido de list_recent é um UID estável, não um
        # número de sequência — evita abrir/responder a mensagem errada.
        _, raw = conn.uid("FETCH", uid.encode(), "(RFC822)")
    except (OSError, imaplib.IMAP4.error, EOFError) as e:
        raise RuntimeError(_explica(e, acc.get("imap", ""), acc.get("imap_port", 993))) from e
    finally:
        _imap_logout(conn)
    lit = next((x for x in (raw or []) if isinstance(x, tuple)), None)
    if lit is None:
        raise RuntimeError("mensagem não encontrada")
    return email.message_from_bytes(lit[1])


def _parts(msg):
    """[(indice, nome, tipo, bytes)] dos anexos e do convite (text/calendar)."""
    out = []
    for i, part in enumerate(msg.walk()):
        if part.is_multipart():
            continue
        name = part.get_filename()
        ct = part.get_content_type()
        if name or ct == "text/calendar":
            try:
                data = part.get_payload(decode=True) or b""
            except Exception:
                data = b""
            out.append((i, _decode_header_str(name or "convite.ics"), ct, data))
    return out


def get_message(uid: str, account: Optional[str] = None) -> dict:
    """Retorna o corpo completo de um email pelo UID (+ anexos e convite)."""
    try:
        msg = _fetch(uid, account)
    except Exception as e:
        return {"error": str(e)}
    parts = _parts(msg)
    invite = next((d for _i, _n, ct, d in parts if ct == "text/calendar"), None)
    return {
        "uid": uid,
        "from": _decode_header_str(msg.get("From", "")),
        "to": _decode_header_str(msg.get("To", "")),
        "subject": _decode_header_str(msg.get("Subject", "")),
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "body": _get_body(msg),
        "list_unsubscribe": " ".join(_decode_header_str(str(msg.get("List-Unsubscribe", ""))).split()),
        "attachments": [{"idx": i, "name": n, "type": ct, "size": len(d)}
                        for i, n, ct, d in parts if ct != "text/calendar"],
        "invite": invite.decode("utf-8", errors="replace") if invite else None,
    }


def get_attachment(uid: str, idx: int, account: Optional[str] = None):
    """(nome, tipo, bytes) do anexo de indice idx."""
    for i, n, ct, d in _parts(_fetch(uid, account)):
        if i == idx:
            return n, ct, d
    raise RuntimeError("anexo não encontrado")


def one_line(s) -> str:
    """Cabeçalho em uma linha só: CR/LF dentro do assunto ou do destino abriam
    caminho para injetar outro cabeçalho (Bcc:) no e-mail."""
    return " ".join(str(s or "").split())


def addresses(s: str) -> list[str]:
    """Endereços de 'Maria <m@x.com>, joao@y.com' -> ['m@x.com', 'joao@y.com'] (so' os válidos)."""
    return [a for _n, a in getaddresses([one_line(s)]) if re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+", a)]


def send_message(to: str, subject: str, body: str, in_reply_to: Optional[str] = None,
                 account: Optional[str] = None) -> tuple[bool, str]:
    """Envia email via SMTP. Só chamado após confirmação explícita do usuário."""
    acc = load_account(account)
    if not acc:
        return False, "Sem conta configurada."
    rcpts = addresses(to)
    if not rcpts:
        return False, "Endereço de destino inválido."
    server = None
    try:
        msg = EmailMessage()
        msg["From"] = acc["user"]
        msg["To"] = ", ".join(rcpts) if len(rcpts) > 1 else one_line(to)
        msg["Subject"] = one_line(subject)
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=acc["user"].split("@")[-1] or None)
        if in_reply_to:
            msg["In-Reply-To"] = one_line(in_reply_to)
            msg["References"] = one_line(in_reply_to)
        msg.set_content(body or "", charset="utf-8", cte="quoted-printable")

        server = _smtp_open(acc)
        recusados = server.send_message(msg, from_addr=acc["user"], to_addrs=rcpts)
        if recusados:
            quem = ", ".join(recusados)
            return True, f"Email enviado, mas o servidor recusou: {quem}."
        return True, "Email enviado com sucesso."
    except Exception as e:
        return False, _explica(e, acc.get("smtp", ""), acc.get("smtp_port", 465))
    finally:
        _smtp_close(server)
