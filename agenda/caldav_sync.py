# -*- coding: utf-8 -*-
"""
Agenda do Nous - sincronizacao CalDAV de duas vias.

Conecta uma conta CalDAV (iCloud, Nextcloud, Fastmail, Radicale... com senha de
app), deixa o usuario escolher os calendarios e mantem os dois lados iguais:

  * o que o servidor tem e o Nous nao (novo/alterado/apagado) desce;
  * o que foi criado/alterado/apagado no Nous sobe.

Como descobre mudancas (RFC 6578 / ctag / etag):
  1. um PROPFIND na pasta de calendarios traz o ctag e o sync-token de todos;
  2. se nada mudou, nao baixa nada; se o servidor tem sync-token, pede so' o
     que mudou desde o token guardado (REPORT sync-collection); sem isso, lista
     os etags (PROPFIND Depth 1) e compara com os locais;
  3. so' baixa (calendar-multiget) os recursos cujo etag mudou.
  Para subir usa If-Match/If-None-Match com o etag: o servidor recusa (412) se
  alguem mexeu no meio, e isso vira conflito em vez de sobrescrever calado.

Conflito (os dois lados mexeram no mesmo compromisso desde a ultima sincronizacao):
  o SERVIDOR VENCE, e a versao do Nous nao se perde: vira um compromisso novo,
  so' no Nous, chamado "<titulo> (versao do Nous)", com um aviso explicando.
  Regra unica para todos os casos (alterado x alterado, alterado x apagado,
  apagado x alterado): quem esta no servidor prevalece; nada some sem rastro.

Segredos: a senha de app fica no SQLite protegida pelo DPAPI do Windows
(so' abre na mesma conta do Windows, neste PC) - nunca em texto puro.

Sem dependencia nova: requests e dateutil ja vem no venv do Open WebUI.
"""
import base64
import ctypes
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import requests

import agenda_db as db

D = "{DAV:}"
C = "{urn:ietf:params:xml:ns:caldav}"
CS = "{http://calendarserver.org/ns/}"
AP = "{http://apple.com/ns/ical/}"
TIMEOUT = 30
UA = "Nous-Agenda/1.0 (CalDAV)"


class DavError(Exception):
    """Erro ja' em portugues simples, pronto para mostrar ao usuario."""

    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


# ------------------------------------------------------------------ segredo (DPAPI)

class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.c_void_p)]


def _dpapi(data, protect):
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.restype = ctypes.c_int
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    fn.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob), ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_Blob)]
    buf = ctypes.create_string_buffer(data, len(data))
    ent = ctypes.create_string_buffer(b"Nous CalDAV", 11)
    bin_ = _Blob(len(data), ctypes.cast(buf, ctypes.c_void_p))
    bent = _Blob(11, ctypes.cast(ent, ctypes.c_void_p))
    out = _Blob()
    if not fn(ctypes.byref(bin_), None, ctypes.byref(bent), None, None, 0x1, ctypes.byref(out)):
        raise OSError("DPAPI recusou")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def seal(text):
    """Texto -> 'dpapi:<base64>' (Windows). Fora do Windows (so' testes/desenvolvimento)
    cai em 'plain:'; no Windows, se o DPAPI falhar, nao guarda (melhor erro que texto puro)."""
    raw = text.encode("utf-8")
    if os.name == "nt" and not os.environ.get("NOUS_CALDAV_PLAIN"):
        try:
            return "dpapi:" + base64.b64encode(_dpapi(raw, True)).decode()
        except Exception:
            raise DavError("O Windows nao deixou guardar a senha com seguranca. Tente de novo.")
    return "plain:" + base64.b64encode(raw).decode()


def unseal(blob):
    kind, _, b64 = (blob or "").partition(":")
    raw = base64.b64decode(b64)
    if kind == "dpapi":
        return _dpapi(raw, False).decode("utf-8")
    if kind == "plain":
        return raw.decode("utf-8")
    raise DavError("senha guardada em formato desconhecido; conecte a conta de novo")


# ------------------------------------------------------------------ HTTP / WebDAV

def _is_local_host(host):
    return host in ("localhost", "127.0.0.1", "::1")


def check_url(url):
    url = (url or "").strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[9:]
    if not re.match(r"https?://", url, re.I):
        url = "https://" + url
    p = urllib.parse.urlparse(url)
    if not p.hostname:
        raise DavError("O endereco do servidor nao parece certo.")
    if p.scheme.lower() != "https" and not _is_local_host(p.hostname):
        raise DavError("O endereco precisa comecar com https:// (a senha nao pode ir aberta pela internet).")
    return url


class Dav:
    def __init__(self, user, password):
        self.s = requests.Session()
        self.user, self.password = user, password
        self.s.headers["User-Agent"] = UA

    def request(self, method, url, body=None, headers=None, depth=None):
        h = dict(headers or {})
        if depth is not None:
            h["Depth"] = str(depth)
        if body is not None and "Content-Type" not in h:
            h["Content-Type"] = "application/xml; charset=utf-8"
        data = body.encode("utf-8") if isinstance(body, str) else body
        for _ in range(6):  # redirecionamentos a mao: o requests troca PROPFIND por GET no 301/302
            try:
                r = self.s.request(method, url, data=data, headers=h, auth=(self.user, self.password),
                                   timeout=TIMEOUT, allow_redirects=False)
            except requests.exceptions.SSLError:
                raise DavError("Nao consegui confirmar a seguranca do servidor (certificado).")
            except requests.exceptions.ConnectionError:
                raise DavError("Nao consegui falar com o servidor. Confira o endereco e a internet.")
            except requests.exceptions.Timeout:
                raise DavError("O servidor demorou demais para responder.")
            except requests.exceptions.RequestException as e:
                raise DavError("Falha de rede: " + type(e).__name__)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
                nxt = urllib.parse.urljoin(url, r.headers["Location"])
                pn = urllib.parse.urlparse(nxt)
                if pn.scheme != "https" and not _is_local_host(pn.hostname or ""):
                    raise DavError("O servidor tentou mandar para um endereco sem seguranca (http).")
                url = nxt
                continue
            return r
        raise DavError("O servidor ficou redirecionando sem parar.")

    def check(self, r, what, ok=(200, 201, 204, 207)):
        if r.status_code in ok:
            return r
        raise DavError(friendly_status(r.status_code, what), r.status_code)


def friendly_status(code, what="falar com o servidor"):
    if code == 401:
        return ("O servidor nao aceitou o usuario ou a senha. Use uma SENHA DE APP (nao a senha normal) "
                "e confira o usuario.")
    if code == 403:
        return "O servidor nao deixou fazer isso (sem permissao ou calendario so' de leitura)."
    if code == 404:
        return "O servidor nao encontrou esse endereco. Confira o endereco do servidor."
    if code == 429:
        return "O servidor pediu para ir mais devagar. Tente de novo em alguns minutos."
    if code >= 500:
        return "O servidor esta com problema agora (erro %d). Tente mais tarde." % code
    return "Nao deu para %s (erro %d)." % (what, code)


def _xml(r):
    try:
        return ET.fromstring(r.content)
    except ET.ParseError:
        raise DavError("O servidor respondeu algo que nao e' CalDAV. Confira o endereco.")


def _multistatus(r):
    """Resposta 207 -> [{'href', 'status', 'props': {tag: Element}}] (props so' dos 200)."""
    root = _xml(r)
    out = []
    for resp in root.iter(D + "response"):
        href = (resp.findtext(D + "href") or "").strip()
        status = resp.findtext(D + "status") or ""
        props = {}
        for ps in resp.findall(D + "propstat"):
            st = ps.findtext(D + "status") or ""
            if " 200" in st or not st:
                for p in ps.findall(D + "prop"):
                    for el in p:
                        props[el.tag] = el
        out.append({"href": href, "status": status, "props": props})
    return out


def _text(props, tag):
    el = props.get(tag)
    return (el.text or "").strip() if el is not None else ""


def _href_of(props, tag):
    el = props.get(tag)
    if el is None:
        return ""
    h = el.find(D + "href")
    return (h.text or "").strip() if h is not None else ""


def _is_cal(props):
    rt = props.get(D + "resourcetype")
    return rt is not None and rt.find(C + "calendar") is not None


PROP_BODY = '<?xml version="1.0" encoding="utf-8"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" ' \
            'xmlns:cs="http://calendarserver.org/ns/" xmlns:a="http://apple.com/ns/ical/"><d:prop>%s</d:prop></d:propfind>'


def propfind(dav, url, depth, props):
    r = dav.request("PROPFIND", url, PROP_BODY % "".join("<%s/>" % p for p in props), depth=depth)
    dav.check(r, "ler o calendario")
    return _multistatus(r)


def norm_href(href):
    """Caminho do recurso, sem escapes, para comparar o mesmo endereco escrito de jeitos diferentes."""
    return urllib.parse.unquote(urllib.parse.urlparse(href).path)


# ------------------------------------------------------------------ descoberta

CAL_PROPS = ["d:resourcetype", "d:displayname", "c:supported-calendar-component-set", "cs:getctag",
             "d:sync-token", "a:calendar-color"]


def _calendars_from(responses, base):
    cals = []
    for r in responses:
        p = r["props"]
        if not _is_cal(p):
            continue
        comps = p.get(C + "supported-calendar-component-set")
        if comps is not None and not any((c.get("name") or "").upper() == "VEVENT" for c in comps):
            continue  # so' tarefas/notas
        url = urllib.parse.urljoin(base, r["href"])
        name = _text(p, D + "displayname") or norm_href(url).rstrip("/").rsplit("/", 1)[-1] or "Calendario"
        color = _text(p, AP + "calendar-color")[:9]
        cals.append({"url": url, "name": name, "color": color,
                     "ctag": _text(p, CS + "getctag") or None,
                     "sync_token": _text(p, D + "sync-token") or None})
    return cals


def discover(dav, url):
    """-> (home_url, [calendarios]). Aceita o endereco do servidor, do usuario ou de um calendario."""
    host = urllib.parse.urlparse(url).hostname or ""
    if host.endswith("google.com") or host.endswith("googleusercontent.com"):
        raise DavError(
            "O Google Agenda nao aceita senha de app no CalDAV (so' login do Google, que o Nous nao faz). "
            "Para o Google use o endereco secreto iCal (so' leitura), ou veja o guia da Agenda.")
    tried = [url]
    pr = urllib.parse.urlparse(url)
    wk = "%s://%s/.well-known/caldav" % (pr.scheme, pr.netloc)
    if wk not in tried:
        tried.append(wk)
    last = None
    for u in tried:
        try:
            resp = propfind(dav, u, 0, ["d:resourcetype", "d:current-user-principal", "c:calendar-home-set"])
        except DavError as e:
            last = e
            if e.status in (401,):
                raise
            continue
        if not resp:
            continue
        p = resp[0]["props"]
        base = u
        if _is_cal(p):  # o endereco ja' e' um calendario
            full = propfind(dav, u, 0, CAL_PROPS)
            return u, _calendars_from(full, u)
        home = _href_of(p, C + "calendar-home-set")
        if not home:
            principal = _href_of(p, D + "current-user-principal")
            if principal:
                pu = urllib.parse.urljoin(base, principal)
                rp = propfind(dav, pu, 0, ["c:calendar-home-set"])
                if rp:
                    home = _href_of(rp[0]["props"], C + "calendar-home-set")
                    base = pu
        if not home:  # talvez o endereco seja a propria pasta de calendarios
            home = base
        home_url = urllib.parse.urljoin(base, home)
        cals = _calendars_from(propfind(dav, home_url, 1, CAL_PROPS), home_url)
        if cals or home != base:
            return home_url, cals
    if last:
        raise last
    raise DavError("Nao encontrei calendarios nesse endereco. Confira o endereco do servidor.")


def list_calendars(dav, home_url):
    return _calendars_from(propfind(dav, home_url, 1, CAL_PROPS), home_url)


# ------------------------------------------------------------------ .ics (leitura/escrita fina)

CRLF = "\r\n"


def _fold(line):
    """Dobra a linha em 75 octetos (RFC 5545) sem partir caractere acentuado ao meio."""
    b = line.encode("utf-8")
    if len(b) <= 75:
        return line
    out, cur, size = [], "", 0
    limit = 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            out.append(cur)
            cur, size, limit = " ", 1, 75
        cur += ch
        size += n
    out.append(cur)
    return CRLF.join(out)


def _esc(v):
    return db._escape(v)


def _stamp(ts=None):
    return datetime.fromtimestamp(ts or time.time(), timezone.utc).strftime("%Y%m%dT%H%M%SZ")


_WIN_TZ = {
    "E. South America Standard Time": "America/Sao_Paulo",
    "Central Brazilian Standard Time": "America/Cuiaba",
    "SA Eastern Standard Time": "America/Fortaleza",
    "Bahia Standard Time": "America/Bahia",
    "Tocantins Standard Time": "America/Araguaina",
    "SA Pacific Standard Time": "America/Bogota",
    "Argentina Standard Time": "America/Argentina/Buenos_Aires",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Pacific Standard Time": "America/Los_Angeles",
    "UTC": "UTC",
}
_local_tzid_cache = []


def local_tzid():
    """Nome IANA do fuso do Windows ('America/Sao_Paulo'), ou None. Vale NOUS_TZ se definido."""
    if _local_tzid_cache:
        return _local_tzid_cache[0]
    name = os.environ.get("NOUS_TZ") or None
    if not name and os.name == "nt":
        try:
            out = subprocess.run(["tzutil", "/g"], capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
            name = _WIN_TZ.get(out)
        except Exception:
            name = None
    if name and db.zone(name) is None:
        name = None
    _local_tzid_cache.append(name)
    return name


def _fmt_dt(ts, all_day, tzid):
    """-> (parametros, valor) de DTSTART/DTEND/EXDATE."""
    if all_day:
        return ";VALUE=DATE", db.local_dt(ts).strftime("%Y%m%d")
    z = db.zone(tzid) if tzid else None
    if z is not None:
        return ";TZID=" + tzid, datetime.fromtimestamp(ts, z).strftime("%Y%m%dT%H%M%S")
    return "", datetime.fromtimestamp(ts, timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _time_lines(ev, tzid):
    pa, va = _fmt_dt(ev["start_at"], ev["all_day"], tzid)
    pb, vb = _fmt_dt(ev["end_at"], ev["all_day"], tzid)
    return ["DTSTART%s:%s" % (pa, va), "DTEND%s:%s" % (pb, vb)]


def _alarm_lines(minutes):
    if minutes is None:
        return []
    trig = "PT0S" if minutes == 0 else "-PT%dM" % minutes
    return ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Lembrete", "TRIGGER:" + trig, "END:VALARM"]


def _alarm_minutes(lines):
    """Minutos de antecedencia do primeiro VALARM com TRIGGER relativo, ou None."""
    inside = False
    for ln in lines:
        if ln == "BEGIN:VALARM":
            inside = True
        elif ln == "END:VALARM":
            inside = False
        elif inside and ln.upper().startswith("TRIGGER"):
            m = re.search(r":(-?)P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?\s*$", ln)
            if m and "VALUE=DATE-TIME" not in ln.upper():
                neg, w, d, h, mi, s = m.groups()
                total = (((int(w or 0) * 7 + int(d or 0)) * 24 + int(h or 0)) * 60 + int(mi or 0)) + int(s or 0) // 60
                return total if neg else 0
    return None


def build_ics(ev):
    """.ics novo para um evento criado no Nous."""
    rec = bool(ev.get("rrule"))
    tzid = local_tzid() if rec else None  # recorrente precisa do fuso (horario de verao); o resto vai em UTC
    ex = []
    if ev.get("exdates"):
        import json
        for ts in json.loads(ev["exdates"]):
            pa, va = _fmt_dt(ts, ev["all_day"], tzid)
            ex.append("EXDATE%s:%s" % (pa, va))
    st = _stamp()
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Nous//Agenda//PT", "BEGIN:VEVENT",
             "UID:" + ev["uid"], "DTSTAMP:" + st, "CREATED:" + _stamp(ev.get("created_at")),
             "LAST-MODIFIED:" + st, "SEQUENCE:0", "SUMMARY:" + _esc(ev["title"])]
    lines += _time_lines(ev, tzid)
    if rec:
        lines.append("RRULE:" + ev["rrule"])
    lines += ex
    if ev.get("description"):
        lines.append("DESCRIPTION:" + _esc(ev["description"]))
    if ev.get("location"):
        lines.append("LOCATION:" + _esc(ev["location"]))
    lines += _alarm_lines(ev.get("remind_min"))
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return CRLF.join(_fold(x) for x in lines) + CRLF


def _master_block(lines):
    """(inicio, fim) do VEVENT principal (sem RECURRENCE-ID), em indices de `lines`."""
    i = 0
    while i < len(lines):
        if lines[i] == "BEGIN:VEVENT":
            j = i + 1
            while j < len(lines) and lines[j] != "END:VEVENT":
                j += 1
            if not any(x.upper().startswith("RECURRENCE-ID") for x in lines[i:j]):
                return i, j
            i = j
        i += 1
    return None


def _pname(line):
    return line.split(":", 1)[0].split(";", 1)[0].upper()


def master_info(raw):
    """Campos do VEVENT principal de um .ics do servidor (ou None)."""
    evs = [e for e in db.parse_ics(raw) if not e.get("recurrence_id")]
    return evs[0] if evs else None


def patch_ics(raw, ev):
    """Atualiza SO' o que mudou no VEVENT principal; tudo o mais (participantes, anexos,
    fusos, excecoes de uma serie, alarmes extras) segue como o servidor mandou."""
    lines = db._unfold(raw)
    blk = _master_block(lines)
    cur = master_info(raw)
    if blk is None or cur is None:
        return build_ics(ev)
    a, b = blk
    body = lines[a + 1:b]
    drop = set()
    add = []
    if (ev["title"] or "") != (cur.get("title") or ""):
        drop.add("SUMMARY")
        add.append("SUMMARY:" + _esc(ev["title"]))
    if (ev["description"] or "") != (cur.get("description") or ""):
        drop.add("DESCRIPTION")
        if ev["description"]:
            add.append("DESCRIPTION:" + _esc(ev["description"]))
    if (ev["location"] or "") != (cur.get("location") or ""):
        drop.add("LOCATION")
        if ev["location"]:
            add.append("LOCATION:" + _esc(ev["location"]))
    if (ev["rrule"] or "") != (cur.get("rrule") or ""):
        drop.add("RRULE")
        if ev["rrule"]:
            add.append("RRULE:" + ev["rrule"])
    if (ev["start_at"], ev["end_at"], bool(ev["all_day"])) != (cur["start_at"], cur["end_at"], bool(cur.get("all_day"))):
        drop |= {"DTSTART", "DTEND", "DURATION"}
        tzid = None
        for ln in body:
            if _pname(ln) == "DTSTART":
                m = re.search(r"TZID=([^;:]+)", ln.split(":", 1)[0])
                tzid = m.group(1).strip('"') if m else None
        if tzid and db.zone(tzid) is None:
            tzid = None
        add += _time_lines(ev, tzid)
    old_alarm = _alarm_minutes(body)
    new_alarm = ev.get("remind_min")
    swap_alarm = (new_alarm != old_alarm) and not (new_alarm is None and old_alarm is None)
    seq = 0
    final, depth, skipping = [], 0, False
    for ln in body:
        if ln.startswith("BEGIN:"):
            if swap_alarm and ln == "BEGIN:VALARM" and depth == 0:
                skipping = True  # troca o alarme: o antigo sai por inteiro
            depth += 1
            if not skipping:
                final.append(ln)
            continue
        if ln.startswith("END:"):
            depth -= 1
            if skipping:
                skipping = depth > 0
            else:
                final.append(ln)
            continue
        if skipping or depth > 0:  # dentro de um subcomponente (VALARM): intocado
            if not skipping:
                final.append(ln)
            continue
        n = _pname(ln)
        if n in drop or n in ("DTSTAMP", "LAST-MODIFIED"):
            continue
        if n == "SEQUENCE":
            try:
                seq = int(ln.split(":", 1)[1]) + 1
            except Exception:
                seq = 1
            continue
        final.append(ln)
    st = _stamp()
    final += add + ["DTSTAMP:" + st, "LAST-MODIFIED:" + st, "SEQUENCE:%d" % max(seq, 1)]
    if swap_alarm:
        final += _alarm_lines(new_alarm)
    lines[a + 1:b] = final
    return CRLF.join(_fold(x) for x in lines) + CRLF


# ------------------------------------------------------------------ armazenamento

def accounts_list(cx, user_id):
    out = []
    for a in cx.execute("SELECT * FROM caldav_accounts WHERE user_id=? ORDER BY created_at", (user_id,)):
        a = dict(a)
        a.pop("secret", None)
        cals = [dict(c) for c in cx.execute("SELECT * FROM caldav_cals WHERE account_id=? ORDER BY name", (a["id"],))]
        for c in cals:
            c.pop("ctag", None)
            c.pop("sync_token", None)
        a["calendars"] = cals
        ids = [c["id"] for c in cals]
        pend = 0
        if ids:
            q = ",".join("?" * len(ids))
            srcs = ["dav:" + i for i in ids]
            pend = cx.execute(f"SELECT COUNT(*) FROM events WHERE dirty>0 AND source IN ({q})", srcs).fetchone()[0]
            pend += cx.execute(f"SELECT COUNT(*) FROM caldav_tomb WHERE cal_id IN ({q})", ids).fetchone()[0]
        a["pending"] = pend
        out.append(a)
    return out


def connect(cx, user_id, url, username, password, name=None):
    """Testa a conta, descobre os calendarios e guarda tudo (calendarios ainda DESLIGADOS:
    o usuario escolhe quais sincronizar). Devolve o id da conta."""
    url = check_url(url)
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        raise DavError("Preencha o usuario e a senha de app.")
    dav = Dav(username, password)
    home, cals = discover(dav, url)
    if not cals:
        raise DavError("Entrei na conta, mas nao achei nenhum calendario de compromissos nela.")
    aid = db.new_id()
    host = urllib.parse.urlparse(url).hostname or "CalDAV"
    cx.execute("INSERT INTO caldav_accounts (id, user_id, name, url, home_url, username, secret, created_at)"
               " VALUES (?,?,?,?,?,?,?,?)",
               (aid, user_id, (name or "").strip() or host, url, home, username, seal(password), db.now()))
    for i, c in enumerate(cals):
        cx.execute("INSERT INTO caldav_cals (id, account_id, user_id, url, name, color, ctag, sync_token)"
                   " VALUES (?,?,?,?,?,?,NULL,NULL)",
                   (db.new_id(), aid, user_id, c["url"], c["name"], c["color"]))
    cx.commit()
    return aid


def choose_calendars(cx, user_id, account_id, enabled_ids, default_id=None):
    """Liga os calendarios escolhidos; os desligados saem do Nous (no servidor continuam)."""
    acc = _account(cx, user_id, account_id)
    enabled_ids = set(enabled_ids or [])
    cals = [dict(c) for c in cx.execute("SELECT * FROM caldav_cals WHERE account_id=?", (acc["id"],))]
    for c in cals:
        on = c["id"] in enabled_ids
        if c["enabled"] and not on:
            _drop_cal_events(cx, c["id"])
            cx.execute("UPDATE caldav_cals SET enabled=0, ctag=NULL, sync_token=NULL, is_default=0 WHERE id=?", (c["id"],))
        elif on and not c["enabled"]:
            cx.execute("UPDATE caldav_cals SET enabled=1, ctag=NULL, sync_token=NULL WHERE id=?", (c["id"],))
    on_ids = [c["id"] for c in cals if c["id"] in enabled_ids]
    if default_id not in on_ids:
        default_id = on_ids[0] if on_ids else None
    cx.execute("UPDATE caldav_cals SET is_default=0 WHERE account_id=?", (acc["id"],))
    if default_id:
        cx.execute("UPDATE caldav_cals SET is_default=1 WHERE id=?", (default_id,))
    cx.commit()


def _drop_cal_events(cx, cal_id):
    cx.execute("DELETE FROM events WHERE source=?", ("dav:" + cal_id,))
    cx.execute("DELETE FROM caldav_tomb WHERE cal_id=?", (cal_id,))


def disconnect(cx, user_id, account_id):
    """Tira a conta do Nous: os compromissos dela saem daqui; no servidor nada e' apagado."""
    acc = _account(cx, user_id, account_id)
    for c in cx.execute("SELECT id FROM caldav_cals WHERE account_id=?", (acc["id"],)).fetchall():
        _drop_cal_events(cx, c["id"])
    cx.execute("DELETE FROM caldav_cals WHERE account_id=?", (acc["id"],))
    cx.execute("DELETE FROM caldav_accounts WHERE id=?", (acc["id"],))
    cx.commit()


def _account(cx, user_id, account_id):
    r = cx.execute("SELECT * FROM caldav_accounts WHERE id=? AND user_id=?", (account_id, user_id)).fetchone()
    if not r:
        raise ValueError("conta nao encontrada")
    return dict(r)


def calendar_for_new(cx, user_id, cal_id):
    r = cx.execute("SELECT * FROM caldav_cals WHERE id=? AND user_id=? AND enabled=1", (cal_id, user_id)).fetchone()
    if not r:
        raise ValueError("calendario nao encontrado")
    return dict(r)


# ------------------------------------------------------------------ sincronizacao

class Stats:
    def __init__(self):
        self.down_new = self.down_upd = self.down_del = 0
        self.up_new = self.up_upd = self.up_del = 0
        self.conflicts = []   # frases para o usuario
        self.errors = []

    def text(self):
        parts = []
        down = self.down_new + self.down_upd + self.down_del
        up = self.up_new + self.up_upd + self.up_del
        if down:
            parts.append("%d recebido%s do servidor" % (down, "" if down == 1 else "s"))
        if up:
            parts.append("%d enviado%s" % (up, "" if up == 1 else "s"))
        if self.conflicts:
            parts.append("%d conflito%s resolvido%s" % (len(self.conflicts), "" if len(self.conflicts) == 1 else "s",
                                                        "" if len(self.conflicts) == 1 else "s"))
        if self.errors:
            parts.append("%d problema%s" % (len(self.errors), "" if len(self.errors) == 1 else "s"))
        return ", ".join(parts) if parts else "tudo em dia"


_locks = {}
_locks_guard = threading.Lock()


def _lock_for(account_id):
    with _locks_guard:
        return _locks.setdefault(account_id, threading.Lock())


def sync_account(cx, account_id, user_id=None, force=False):
    """Sincroniza uma conta. Nunca levanta por causa de rede: grava o erro na conta."""
    r = cx.execute("SELECT * FROM caldav_accounts WHERE id=?", (account_id,)).fetchone()
    if not r:
        raise ValueError("conta nao encontrada")
    acc = dict(r)
    if user_id and acc["user_id"] != user_id:
        raise ValueError("conta nao encontrada")
    lock = _lock_for(account_id)
    if not lock.acquire(blocking=False):
        return {"busy": True}
    st = Stats()
    try:
        try:
            dav = Dav(acc["username"], unseal(acc["secret"]))
            _sync_account(cx, dav, acc, st, force)
            err = None
        except DavError as e:
            err = str(e)
        except Exception as e:  # defeito nosso: nao derruba o relogio da Agenda
            err = "Erro inesperado na sincronizacao (%s)." % type(e).__name__
            print("[Nous][agenda] caldav:", repr(e), file=sys.stderr)
        t = db.now()
        if err:
            cx.execute("UPDATE caldav_accounts SET last_sync=?, last_error=?, last_summary=? WHERE id=?",
                       (t, err[:300], st.text() if (st.down_new or st.up_new or st.down_upd) else None, account_id))
        else:
            summ = st.text()
            if st.errors:
                summ += ". " + st.errors[0]
            cx.execute("UPDATE caldav_accounts SET last_sync=?, last_ok=?, last_error=NULL, last_summary=? WHERE id=?",
                       (t, t, summ[:400], account_id))
        cx.commit()
        return {"ok": err is None, "error": err, "summary": st.text(), "conflicts": st.conflicts,
                "errors": st.errors}
    finally:
        lock.release()


def _sync_account(cx, dav, acc, st, force):
    home = acc["home_url"] or acc["url"]
    try:
        listing = list_calendars(dav, home)
    except DavError as e:
        if e.status == 404:  # o servidor mudou a pasta: descobre de novo
            home, listing = discover(dav, acc["url"])
            cx.execute("UPDATE caldav_accounts SET home_url=? WHERE id=?", (home, acc["id"]))
        else:
            raise
    known = {norm_href(c["url"]).rstrip("/"): dict(c) for c in
             cx.execute("SELECT * FROM caldav_cals WHERE account_id=?", (acc["id"],))}
    seen = set()
    for lc in listing:
        key = norm_href(lc["url"]).rstrip("/")
        seen.add(key)
        if key in known:
            cx.execute("UPDATE caldav_cals SET name=?, color=? WHERE id=?", (lc["name"], lc["color"], known[key]["id"]))
        else:  # calendario novo na conta: aparece na lista, desligado
            cid = db.new_id()
            cx.execute("INSERT INTO caldav_cals (id, account_id, user_id, url, name, color) VALUES (?,?,?,?,?,?)",
                       (cid, acc["id"], acc["user_id"], lc["url"], lc["name"], lc["color"]))
    for key, c in known.items():
        if key not in seen:  # sumiu do servidor
            _drop_cal_events(cx, c["id"])
            cx.execute("DELETE FROM caldav_cals WHERE id=?", (c["id"],))
    cx.commit()
    by_url = {norm_href(lc["url"]).rstrip("/"): lc for lc in listing}
    for c in [dict(x) for x in cx.execute(
            "SELECT * FROM caldav_cals WHERE account_id=? AND enabled=1", (acc["id"],))]:
        live = by_url.get(norm_href(c["url"]).rstrip("/"), {})
        try:
            _sync_cal(cx, dav, acc, c, live, st, force)
            cx.execute("UPDATE caldav_cals SET last_sync=?, last_error=NULL WHERE id=?", (db.now(), c["id"]))
        except DavError as e:
            if e.status == 401:
                raise
            st.errors.append("%s: %s" % (c["name"], e))
            cx.execute("UPDATE caldav_cals SET last_sync=?, last_error=? WHERE id=?", (db.now(), str(e)[:200], c["id"]))
        cx.commit()


def _local_rows(cx, cal_id):
    return {norm_href(r["href"]): dict(r) for r in
            cx.execute("SELECT * FROM events WHERE source=? AND href IS NOT NULL", ("dav:" + cal_id,))}


def _sync_cal(cx, dav, acc, cal, live, st, force):
    cid = cal["id"]
    ctag, token = live.get("ctag"), live.get("sync_token")
    unchanged = (not force and (ctag or token) and ctag == cal["ctag"] and token == cal["sync_token"])
    new_ctag, new_token = ctag, token
    if not unchanged:
        changed, removed, tok2 = _server_changes(dav, cal, token)
        new_token = tok2 if tok2 else token
        _apply_pull(cx, dav, acc, cal, changed, removed, st)
    _push(cx, dav, acc, cal, st)
    # a posicao so' avanca depois de tudo aplicado: se algo falhar no meio, na proxima
    # vez o servidor devolve de novo as mesmas mudancas (aplicar duas vezes e' inofensivo)
    cx.execute("UPDATE caldav_cals SET ctag=?, sync_token=? WHERE id=?", (new_ctag, new_token, cid))


def _server_changes(dav, cal, live_token):
    """-> ({href_normalizado: (href, etag)}, {hrefs removidos}, novo_token)."""
    base = cal["url"]
    if live_token:  # servidor com sync-token (RFC 6578): so' o que mudou desde o ultimo
        try:
            body = ('<?xml version="1.0" encoding="utf-8"?><d:sync-collection xmlns:d="DAV:">'
                    '<d:sync-token>%s</d:sync-token><d:sync-level>1</d:sync-level>'
                    '<d:prop><d:getetag/></d:prop></d:sync-collection>' % (cal["sync_token"] or ""))
            r = dav.request("REPORT", base, body, depth=0)
            if r.status_code == 207:
                changed, removed = {}, set()
                for x in _multistatus(r):
                    n = norm_href(x["href"])
                    if n.rstrip("/") == norm_href(base).rstrip("/"):
                        continue
                    if " 404" in x["status"]:
                        removed.add(n)
                    else:
                        changed[n] = (x["href"], _text(x["props"], D + "getetag"))
                tok = _xml(r).findtext(D + "sync-token")
                return changed, removed, (tok or "").strip() or None
            # token vencido/invalido (403/409/410): lista tudo
        except DavError as e:
            if e.status == 401:
                raise
    resp = propfind(dav, base, 1, ["d:getetag", "d:resourcetype"])
    changed, removed = {}, None
    for x in resp:
        n = norm_href(x["href"])
        if n.rstrip("/") == norm_href(base).rstrip("/") or x["props"].get(D + "resourcetype") is not None and \
                x["props"][D + "resourcetype"].find(D + "collection") is not None:
            continue
        changed[n] = (x["href"], _text(x["props"], D + "getetag"))
    return changed, removed, live_token  # removed None = "compare com a lista completa"


def _fetch(dav, cal, hrefs):
    """calendar-multiget (com GET de reserva) -> {href_norm: (etag, ics)}."""
    out = {}
    hrefs = list(hrefs)
    for i in range(0, len(hrefs), 40):
        chunk = hrefs[i:i + 40]
        body = ('<?xml version="1.0" encoding="utf-8"?><c:calendar-multiget xmlns:d="DAV:" '
                'xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop>%s'
                '</c:calendar-multiget>' % "".join("<d:href>%s</d:href>" % _xesc(h) for h in chunk))
        r = dav.request("REPORT", cal["url"], body, depth=1)
        if r.status_code == 207:
            for x in _multistatus(r):
                data = x["props"].get(C + "calendar-data")
                if data is not None and data.text:
                    out[norm_href(x["href"])] = (_text(x["props"], D + "getetag"), data.text)
    for h in hrefs:
        n = norm_href(h)
        if n not in out:
            r = dav.request("GET", urllib.parse.urljoin(cal["url"], h))
            if r.status_code == 200:
                out[n] = (r.headers.get("ETag", "").strip(), r.text)
    return out


def _xesc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _apply_pull(cx, dav, acc, cal, changed, removed, st):
    cid, src = cal["id"], "dav:" + cal["id"]
    local = _local_rows(cx, cid)
    tombs = {norm_href(t["href"]): dict(t) for t in cx.execute("SELECT * FROM caldav_tomb WHERE cal_id=?", (cid,))}
    if removed is None:  # lista completa: o que nao esta' nela foi apagado no servidor
        removed = {n for n in local if n not in changed}
    need = []
    for n, (href, etag) in changed.items():
        row = local.get(n)
        if n in tombs and etag and tombs[n]["etag"] == etag:
            continue  # e' o mesmo que apagamos aqui: nao mexeram la', so' falta o DELETE subir
        if row is None or not etag or row["etag"] != etag:
            need.append(href)
    got = _fetch(dav, cal, need) if need else {}
    for href in need:
        n = norm_href(href)
        etag, ics = got.get(n, (None, None))
        if ics is None:
            continue
        etag = etag or changed[n][1]
        _apply_remote(cx, acc, cal, local.get(n), href, etag, ics, n in tombs, tombs.get(n), st)
    for n in removed:
        row = local.get(n)
        if n in tombs:  # apagamos aqui e la' tambem: acabou
            cx.execute("DELETE FROM caldav_tomb WHERE id=?", (tombs[n]["id"],))
        if row is None:
            continue
        if row["dirty"] == 1:
            _keep_copy(cx, acc, row, "foi apagado no servidor, mas voce tinha mudado aqui")
            st.conflicts.append(row["title"])
        cx.execute("DELETE FROM events WHERE id=?", (row["id"],))
        st.down_del += 1
    cx.commit()


def _apply_remote(cx, acc, cal, row, href, etag, ics, has_tomb, tomb, st):
    src = "dav:" + cal["id"]
    m = master_info(ics)
    if m is None:  # tarefa, ou compromisso cancelado: nao mostramos
        if row is not None and row["dirty"] == 0:
            cx.execute("DELETE FROM events WHERE id=?", (row["id"],))
            st.down_del += 1
        return
    lines = db._unfold(ics)
    alarm = _alarm_minutes(lines)
    path = urllib.parse.urlparse(href).path or href
    if has_tomb:  # apagado aqui, mas alguem mexeu la': o servidor vence, o evento volta
        cx.execute("DELETE FROM caldav_tomb WHERE id=?", (tomb["id"],))
        db.notify(cx, acc["user_id"], "sincronizacao", "Compromisso de volta: " + m.get("title", ""),
                  "Voce apagou este compromisso, mas ele foi alterado no servidor depois. Mantivemos a versao do servidor.")
        st.conflicts.append(m.get("title", ""))
    if row is not None:
        if row["dirty"]:
            _keep_copy(cx, acc, row, "foi alterado no servidor ao mesmo tempo")
            st.conflicts.append(row["title"])
        remind = alarm if alarm is not None else row["remind_min"]
        cx.execute("""UPDATE events SET title=?, description=?, location=?, start_at=?, end_at=?, all_day=?,
                      rrule=?, exdates=?, remind_min=?, uid=?, href=?, etag=?, raw=?, dirty=0, updated_at=?
                      WHERE id=?""",
                   (m.get("title", ""), m.get("description", ""), m.get("location", ""), m["start_at"], m["end_at"],
                    1 if m.get("all_day") else 0, m.get("rrule"), _exd(m), remind, m.get("uid") or row["uid"],
                    path, etag, ics, db.now(), row["id"]))
        st.down_upd += 1
        return
    remind = alarm if alarm is not None else cal.get("remind_min", 30)
    t = db.now()
    cx.execute("""INSERT INTO events (id, user_id, title, description, location, start_at, end_at, all_day, rrule,
                  exdates, remind_min, uid, source, href, etag, raw, dirty, created_at, updated_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?)""",
               (db.new_id(), acc["user_id"], m.get("title", ""), m.get("description", ""), m.get("location", ""),
                m["start_at"], m["end_at"], 1 if m.get("all_day") else 0, m.get("rrule"), _exd(m), remind,
                m.get("uid") or db.new_id() + "@dav", src, path, etag, ics, t, t))
    st.down_new += 1


def _exd(m):
    import json
    return json.dumps(m["exdates"]) if m.get("exdates") else None


def _keep_copy(cx, acc, row, why):
    """Conflito: a versao do Nous vira um compromisso so' daqui, e o usuario e' avisado."""
    copy = {k: row[k] for k in ("title", "description", "location", "start_at", "end_at", "all_day", "rrule",
                                "remind_min")}
    copy["title"] = (row["title"] + " (versao do Nous)")[:200]
    eid = db.event_create(cx, acc["user_id"], copy, source="local")
    if row.get("exdates"):
        cx.execute("UPDATE events SET exdates=? WHERE id=?", (row["exdates"], eid))
    db.notify(cx, acc["user_id"], "sincronizacao", "Conflito: " + row["title"],
              'Este compromisso %s. Vale a versao do servidor; a sua ficou guardada como "%s".' % (why, copy["title"]), eid)


def _push(cx, dav, acc, cal, st):
    cid, src = cal["id"], "dav:" + cal["id"]
    # 1) apagados aqui
    for t in [dict(x) for x in cx.execute("SELECT * FROM caldav_tomb WHERE cal_id=? ORDER BY id", (cid,))]:
        h = {"If-Match": t["etag"]} if t["etag"] else {}
        r = dav.request("DELETE", urllib.parse.urljoin(cal["url"], t["href"]), headers=h)
        if r.status_code in (200, 202, 204, 404, 410):
            cx.execute("DELETE FROM caldav_tomb WHERE id=?", (t["id"],))
            st.up_del += 1
        elif r.status_code == 412:  # alguem mexeu la' depois: traz de volta, o servidor vence
            got = _fetch(dav, cal, [t["href"]])
            n = norm_href(t["href"])
            if n in got:
                etag, ics = got[n]
                _apply_remote(cx, acc, cal, None, t["href"], etag, ics, True, t, st)
            else:
                cx.execute("DELETE FROM caldav_tomb WHERE id=?", (t["id"],))
        else:
            st.errors.append('"%s": %s' % (t["title"], friendly_status(r.status_code, "apagar no servidor")))
    # 2) criados e alterados aqui
    for ev in [dict(x) for x in cx.execute("SELECT * FROM events WHERE source=? AND dirty>0 ORDER BY dirty DESC", (src,))]:
        is_new = not ev["href"]
        try:
            if is_new:
                ics = build_ics(ev)
                fname = re.sub(r"[^A-Za-z0-9._-]", "_", ev["uid"]) + ".ics"
                url = urllib.parse.urljoin(cal["url"], fname)
                hdr = {"If-None-Match": "*"}
            else:
                ics = patch_ics(ev["raw"], ev) if ev["raw"] else build_ics(ev)
                url = urllib.parse.urljoin(cal["url"], ev["href"])
                hdr = {"If-Match": ev["etag"]} if ev["etag"] else {}
            hdr["Content-Type"] = "text/calendar; charset=utf-8"
            r = dav.request("PUT", url, ics.encode("utf-8"), headers=hdr)
        except DavError as e:
            if e.status == 401:
                raise
            st.errors.append('"%s": %s' % (ev["title"], e))
            continue
        if r.status_code in (200, 201, 204):
            etag = (r.headers.get("ETag") or "").strip()
            if not etag:
                try:
                    pr = propfind(dav, url, 0, ["d:getetag"])
                    etag = _text(pr[0]["props"], D + "getetag") if pr else ""
                except DavError:
                    etag = ""
            path = urllib.parse.urlparse(url).path
            cx.execute("UPDATE events SET href=?, etag=?, raw=? WHERE id=?", (path, etag or None, ics, ev["id"]))
            cx.execute("UPDATE events SET dirty=0 WHERE id=? AND updated_at=?", (ev["id"], ev["updated_at"]))
            st.up_new += 1 if is_new else 0
            st.up_upd += 0 if is_new else 1
        elif r.status_code in (412, 409) and not is_new:
            # alguem mexeu la' no meio: traz a versao do servidor (que vence) e guarda a nossa como copia
            got = _fetch(dav, cal, [ev["href"]])
            n = norm_href(ev["href"])
            if n in got:
                etag, sics = got[n]
                _apply_remote(cx, acc, cal, ev, ev["href"], etag, sics, False, None, st)
            else:  # sumiu de la'
                _keep_copy(cx, acc, ev, "foi apagado no servidor, mas voce tinha mudado aqui")
                st.conflicts.append(ev["title"])
                cx.execute("DELETE FROM events WHERE id=?", (ev["id"],))
        else:
            st.errors.append('"%s": %s' % (ev["title"], friendly_status(r.status_code, "enviar ao servidor")))
    cx.commit()


# ------------------------------------------------------------------ relogio

BACKOFF_S = 900
_last_try = {}  # account_id -> (quando, falhou?)


def accounts_due(cx, every_s, now=None):
    """Contas a sincronizar agora: passou o intervalo, ou ha' mudanca local esperando (apos um
    respiro de 1 min depois de uma falha, para nao martelar o servidor)."""
    now = now or db.now()
    due = []
    for a in [dict(r) for r in cx.execute("SELECT * FROM caldav_accounts")]:
        if not cx.execute("SELECT 1 FROM caldav_cals WHERE account_id=? AND enabled=1", (a["id"],)).fetchone():
            continue
        t, failed = _last_try.get(a["id"], (0, False))
        ids = [r[0] for r in cx.execute("SELECT id FROM caldav_cals WHERE account_id=? AND enabled=1", (a["id"],))]
        q = ",".join("?" * len(ids))
        pend = cx.execute(f"SELECT COUNT(*) FROM events WHERE dirty>0 AND source IN ({q})",
                          ["dav:" + i for i in ids]).fetchone()[0] + \
            cx.execute(f"SELECT COUNT(*) FROM caldav_tomb WHERE cal_id IN ({q})", ids).fetchone()[0]
        wait = 60 if pend else every_s
        if failed:
            wait = max(wait, BACKOFF_S if not pend else 120)
        if now - t >= wait:
            due.append(a["id"])
    return due


def sync_due(every_s=300):
    """Chamado pelo relogio da Agenda (numa thread)."""
    cx = db.connect()
    try:
        for aid in accounts_due(cx, every_s):
            res = sync_account(cx, aid)
            _last_try[aid] = (db.now(), not res.get("ok", False) and not res.get("busy"))
    finally:
        cx.close()
