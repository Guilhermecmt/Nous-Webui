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

ACCOUNT_FILE = ".email_account.json"

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


def load_account() -> Optional[dict]:
    path = _account_path()
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_account(data: dict) -> None:
    path = _account_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    # Restringir permissões ao dono (best-effort no Windows)
    try:
        import stat
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


def delete_account() -> None:
    path = _account_path()
    try:
        os.remove(path)
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
            if "attachment" in cd:
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


def list_recent(n: int = 20) -> list[dict]:
    """Retorna os n emails mais recentes da caixa de entrada."""
    acc = load_account()
    if not acc:
        return []
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
            _, raw = conn.uid("FETCH", uid, "(RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
            if not raw or not raw[0]:
                continue
            header_bytes = raw[0][1] if isinstance(raw[0], tuple) else raw[0]
            msg = email.message_from_bytes(header_bytes)
            snippet_uid = uid.decode()
            msgs.append({
                "uid": snippet_uid,
                "from": _decode_header_str(msg.get("From", "")),
                "subject": _decode_header_str(msg.get("Subject", "(sem assunto)")),
                "date": msg.get("Date", ""),
                "message_id": msg.get("Message-ID", ""),
                "snippet": "",
                "category": None,
                "summary": None,
            })
        conn.logout()
        return msgs
    except Exception as e:
        return [{"error": str(e)}]


def get_message(uid: str) -> dict:
    """Retorna o corpo completo de um email pelo UID."""
    acc = load_account()
    if not acc:
        return {"error": "sem conta configurada"}
    try:
        conn = _imap_connect(acc)
        conn.select("INBOX", readonly=True)
        # UID FETCH: o uid recebido de list_recent é um UID estável, não um
        # número de sequência — evita abrir/responder a mensagem errada.
        _, raw = conn.uid("FETCH", uid.encode(), "(RFC822)")
        conn.logout()
        if not raw or not raw[0]:
            return {"error": "mensagem não encontrada"}
        msg = email.message_from_bytes(raw[0][1])
        return {
            "uid": uid,
            "from": _decode_header_str(msg.get("From", "")),
            "to": _decode_header_str(msg.get("To", "")),
            "subject": _decode_header_str(msg.get("Subject", "")),
            "date": msg.get("Date", ""),
            "message_id": msg.get("Message-ID", ""),
            "body": _get_body(msg),
        }
    except Exception as e:
        return {"error": str(e)}


def send_message(to: str, subject: str, body: str, in_reply_to: Optional[str] = None) -> tuple[bool, str]:
    """Envia email via SMTP. Só chamado após confirmação explícita do usuário."""
    acc = load_account()
    if not acc:
        return False, "Sem conta configurada."
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
        server.quit()
        return True, "Email enviado com sucesso."
    except smtplib.SMTPAuthenticationError:
        return False, "Credenciais rejeitadas pelo servidor SMTP."
    except OSError as e:
        return False, f"Servidor SMTP inacessível: {e}"
    except Exception as e:
        return False, str(e)
