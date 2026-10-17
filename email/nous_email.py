# -*- coding: utf-8 -*-
"""
Cliente IMAP/SMTP para o Nous Email — stdlib pura (imaplib, smtplib, email).

Lê credenciais de NousData/.email_account.json.
Nunca loga a senha. Nunca envia sem chamada explícita.
"""
import imaplib
import smtplib
import email
import json
import os
import re
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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
        return " ".join(re.sub(r"<[^>]+>", " ", html).split())


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
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ct == "text/plain" and not plain:
                plain = text
            elif ct == "text/html" and not html:
                html = text
        return plain.strip() or _strip_html(html)
    else:
        ct = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        try:
            payload = msg.get_payload(decode=True)
            text = (payload or b"").decode(charset, errors="replace")
        except Exception:
            text = ""
        if ct == "text/html":
            return _strip_html(text)
        return text.strip()


def _imap_connect(acc: dict) -> imaplib.IMAP4_SSL:
    host = acc["imap"]
    port = int(acc.get("imap_port", 993))
    conn = imaplib.IMAP4_SSL(host, port)
    conn.login(acc["user"], acc["app_password"])
    return conn


def _imap_logout(conn) -> None:
    """Fecha a conexão IMAP sem nunca lançar (best-effort)."""
    if conn is None:
        return
    try:
        conn.logout()
    except Exception:
        pass


def test_connection(acc: dict) -> tuple[bool, str]:
    """Valida credenciais IMAP. Retorna (ok, mensagem)."""
    try:
        conn = _imap_connect(acc)
        conn.logout()
        return True, "Conexão bem-sucedida."
    except imaplib.IMAP4.error as e:
        return False, f"Credenciais rejeitadas: {e}"
    except OSError as e:
        return False, f"Servidor IMAP inacessível ({acc.get('imap')}): {e}"
    except Exception as e:
        return False, str(e)


_LIST_HEADERS = "FROM TO SUBJECT DATE MESSAGE-ID LIST-UNSUBSCRIBE LIST-ID PRECEDENCE AUTO-SUBMITTED"


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
        msgs = []
        for uid in uids:
            _, raw = conn.uid("FETCH", uid, f"(RFC822.SIZE FLAGS BODY.PEEK[HEADER.FIELDS ({_LIST_HEADERS})])")
            if not raw or not raw[0]:
                continue
            header_bytes = raw[0][1] if isinstance(raw[0], tuple) else raw[0]
            flags = raw[0][0].decode(errors="ignore") if isinstance(raw[0], tuple) else ""
            msg = email.message_from_bytes(header_bytes)
            snippet_uid = uid.decode()
            msgs.append({
                "uid": snippet_uid,
                "account": acc["user"],
                "from": _decode_header_str(msg.get("From", "")),
                "to": _decode_header_str(msg.get("To", "")),
                "subject": _decode_header_str(msg.get("Subject", "(sem assunto)")),
                "date": msg.get("Date", ""),
                "message_id": msg.get("Message-ID", ""),
                "unread": "\\Seen" not in flags,
                # Newsletter/lista: RFC 2369 + cabecalhos de envio automatico
                "list_unsubscribe": " ".join(str(msg.get("List-Unsubscribe", "")).split()),
                "bulk": bool(msg.get("List-Id") or str(msg.get("Precedence", "")).lower() in ("bulk", "list")
                             or str(msg.get("Auto-Submitted", "no")).lower() != "no"),
                "snippet": "",
                "category": None,
                "summary": None,
            })
        return msgs
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        _imap_logout(conn)


def _fetch(uid: str, account: Optional[str]):
    acc = load_account(account)
    if not acc:
        raise RuntimeError("sem conta configurada")
    conn = _imap_connect(acc)
    try:
        conn.select("INBOX", readonly=True)
        # UID FETCH: o uid recebido de list_recent é um UID estável, não um
        # número de sequência — evita abrir/responder a mensagem errada.
        _, raw = conn.uid("FETCH", uid.encode(), "(RFC822)")
    finally:
        _imap_logout(conn)
    if not raw or not raw[0] or not isinstance(raw[0], tuple):
        raise RuntimeError("mensagem não encontrada")
    return email.message_from_bytes(raw[0][1])


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
        "list_unsubscribe": " ".join(str(msg.get("List-Unsubscribe", "")).split()),
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


def send_message(to: str, subject: str, body: str, in_reply_to: Optional[str] = None,
                 account: Optional[str] = None) -> tuple[bool, str]:
    """Envia email via SMTP. Só chamado após confirmação explícita do usuário."""
    acc = load_account(account)
    if not acc:
        return False, "Sem conta configurada."
    server = None
    try:
        msg = MIMEMultipart()
        msg["From"] = acc["user"]
        msg["To"] = to
        msg["Subject"] = subject
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.attach(MIMEText(body, "plain", "utf-8"))

        smtp_host = acc["smtp"]
        smtp_port = int(acc.get("smtp_port", 465))

        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()

        server.login(acc["user"], acc["app_password"])
        server.sendmail(acc["user"], [to], msg.as_string())
        return True, "Email enviado com sucesso."
    except smtplib.SMTPAuthenticationError:
        return False, "Credenciais rejeitadas pelo servidor SMTP."
    except OSError as e:
        return False, f"Servidor SMTP inacessível: {e}"
    except Exception as e:
        return False, str(e)
    finally:
        # Fecha o socket em qualquer caminho (sucesso ou erro). quit() envia
        # QUIT e pode lançar se a conexão já estiver quebrada — close() não.
        if server is not None:
            try:
                server.quit()
            except Exception:
                try:
                    server.close()
                except Exception:
                    pass
