# -*- coding: utf-8 -*-
"""
Testes da sincronizacao CalDAV da Agenda (agenda/caldav_sync.py). Sem rede externa.

Rodam contra dois servidores locais:
  * um CalDAV de mentira (stdlib, neste arquivo), nos dois jeitos: com sync-token
    (RFC 6578) e so' com ctag/etag;
  * o Radicale de verdade, se estiver instalado (pip install radicale) - senao pula.

    python -m unittest discover -s agenda/tests -v
"""
import base64
import hashlib
import http.server
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["NOUS_TZ"] = "America/Sao_Paulo"

try:
    import requests  # noqa: E402
    import dateutil  # noqa: F401,E402
    import agenda_db as db  # noqa: E402
    import caldav_sync as cd  # noqa: E402
    HAVE_DEPS = True
except Exception:  # pragma: no cover
    HAVE_DEPS = False

USER, PASS = "gui", "senha-de-app"
UID = "u1"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


# ---------------------------------------------------------------- servidor de mentira

class FakeState:
    def __init__(self, sync):
        self.sync = sync
        self.cals = {}      # '/gui/pessoal/' -> {'name', 'items': {name: (etag, body)}, 'log': [(n, name, deleted)], 'n': 0}
        self.requests = []  # (metodo, caminho)
        self.lock = threading.Lock()

    def mk(self, path, name):
        self.cals[path] = {"name": name, "items": {}, "log": [], "n": 0}


def _handler(state):
    NS = ('xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav" '
          'xmlns:cs="http://calendarserver.org/ns/" xmlns:a="http://apple.com/ns/ical/"')

    class H(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _auth(self):
            tok = base64.b64encode(("%s:%s" % (USER, PASS)).encode()).decode()
            if self.headers.get("Authorization") != "Basic " + tok:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="x"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                return False
            return True

        def _send(self, code, body=b"", headers=None, ctype="application/xml; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _read(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n).decode("utf-8") if n else ""

        def _ms(self, items):
            return '<?xml version="1.0"?><d:multistatus %s>%s</d:multistatus>' % (NS, "".join(items))

        def _cal_resp(self, path, cal):
            tok = ('<d:sync-token>tok-%d</d:sync-token>' % cal["n"]) if state.sync else ""
            return ('<d:response><d:href>%s</d:href><d:propstat><d:prop><d:resourcetype><d:collection/><c:calendar/>'
                    '</d:resourcetype><d:displayname>%s</d:displayname><cs:getctag>ctag-%d</cs:getctag>%s'
                    '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>'
                    '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>'
                    % (path, cal["name"], cal["n"], tok))

        def _find(self, path):
            for cp, cal in state.cals.items():
                if path.startswith(cp):
                    return cp, cal, path[len(cp):]
            return None, None, None

        def do_PROPFIND(self):
            with state.lock:
                state.requests.append(("PROPFIND", self.path))
                if not self._auth():
                    return
                self._read()
                path = urllib.parse.unquote(self.path.split("?")[0])
                depth = self.headers.get("Depth", "0")
                if path == "/":
                    return self._send(207, self._ms([
                        '<d:response><d:href>/</d:href><d:propstat><d:prop><d:current-user-principal>'
                        '<d:href>/gui/</d:href></d:current-user-principal></d:prop><d:status>HTTP/1.1 200 OK'
                        '</d:status></d:propstat></d:response>']))
                if path == "/gui/":
                    items = ['<d:response><d:href>/gui/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/>'
                             '</d:resourcetype><c:calendar-home-set><d:href>/gui/</d:href></c:calendar-home-set>'
                             '</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>']
                    if depth == "1":
                        items += [self._cal_resp(p, c) for p, c in state.cals.items()]
                    return self._send(207, self._ms(items))
                cp, cal, rest = self._find(path)
                if cal is None:
                    return self._send(404)
                if rest == "":
                    items = [self._cal_resp(cp, cal)]
                    if depth == "1":
                        for name, (etag, _b) in cal["items"].items():
                            items.append('<d:response><d:href>%s%s</d:href><d:propstat><d:prop><d:getetag>%s</d:getetag>'
                                         '<d:resourcetype/></d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat>'
                                         '</d:response>' % (cp, name, etag))
                    return self._send(207, self._ms(items))
                if rest in cal["items"]:
                    return self._send(207, self._ms([
                        '<d:response><d:href>%s</d:href><d:propstat><d:prop><d:getetag>%s</d:getetag></d:prop>'
                        '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>' % (path, cal["items"][rest][0])]))
                return self._send(404)

        def do_REPORT(self):
            with state.lock:
                state.requests.append(("REPORT", self.path))
                if not self._auth():
                    return
                body = self._read()
                cp, cal, rest = self._find(urllib.parse.unquote(self.path))
                if cal is None:
                    return self._send(404)
                if "sync-collection" in body:
                    if not state.sync:
                        return self._send(501)
                    m = re.search(r"<d:sync-token>(.*?)</d:sync-token>", body)
                    tok = m.group(1) if m else ""
                    since = 0
                    if tok:
                        mm = re.fullmatch(r"tok-(\d+)", tok)
                        if not mm:
                            return self._send(403, '<d:error xmlns:d="DAV:"><d:valid-sync-token/></d:error>')
                        since = int(mm.group(1))
                    last = {}
                    for n, name, gone in cal["log"]:
                        if n > since:
                            last[name] = gone
                    items = []
                    for name, gone in last.items():
                        if gone:
                            items.append('<d:response><d:href>%s%s</d:href><d:status>HTTP/1.1 404 Not Found</d:status></d:response>' % (cp, name))
                        else:
                            items.append('<d:response><d:href>%s%s</d:href><d:propstat><d:prop><d:getetag>%s</d:getetag></d:prop>'
                                         '<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>' % (cp, name, cal["items"][name][0]))
                    xml = self._ms(items).replace("</d:multistatus>", "<d:sync-token>tok-%d</d:sync-token></d:multistatus>" % cal["n"])
                    return self._send(207, xml)
                hrefs = re.findall(r"<d:href>(.*?)</d:href>", body)
                items = []
                for h in hrefs:
                    name = urllib.parse.unquote(h)[len(cp):]
                    if name in cal["items"]:
                        etag, data = cal["items"][name]
                        items.append('<d:response><d:href>%s</d:href><d:propstat><d:prop><d:getetag>%s</d:getetag>'
                                     '<c:calendar-data>%s</c:calendar-data></d:prop><d:status>HTTP/1.1 200 OK</d:status>'
                                     '</d:propstat></d:response>' % (h, etag, data.replace("&", "&amp;").replace("<", "&lt;")))
                return self._send(207, self._ms(items))

        def do_GET(self):
            with state.lock:
                if not self._auth():
                    return
                cp, cal, rest = self._find(urllib.parse.unquote(self.path))
                if cal is None or rest not in cal["items"]:
                    return self._send(404)
                etag, data = cal["items"][rest]
                return self._send(200, data, {"ETag": etag}, "text/calendar")

        def do_PUT(self):
            with state.lock:
                state.requests.append(("PUT", self.path))
                if not self._auth():
                    return
                data = self._read()
                cp, cal, rest = self._find(urllib.parse.unquote(self.path))
                if cal is None or not rest:
                    return self._send(404)
                cur = cal["items"].get(rest)
                if self.headers.get("If-None-Match") == "*" and cur:
                    return self._send(412)
                im = self.headers.get("If-Match")
                if im and (not cur or cur[0] != im):
                    return self._send(412)
                etag = '"%s"' % hashlib.md5(data.encode("utf-8")).hexdigest()
                cal["items"][rest] = (etag, data)
                cal["n"] += 1
                cal["log"].append((cal["n"], rest, False))
                self._send(204 if cur else 201, b"", {"ETag": etag})

        def do_DELETE(self):
            with state.lock:
                state.requests.append(("DELETE", self.path))
                if not self._auth():
                    return
                cp, cal, rest = self._find(urllib.parse.unquote(self.path))
                if cal is None or rest not in cal["items"]:
                    return self._send(404)
                im = self.headers.get("If-Match")
                if im and cal["items"][rest][0] != im:
                    return self._send(412)
                del cal["items"][rest]
                cal["n"] += 1
                cal["log"].append((cal["n"], rest, True))
                self._send(204)

        def do_MKCALENDAR(self):
            with state.lock:
                if not self._auth():
                    return
                body = self._read()
                m = re.search(r"<d:displayname>(.*?)</d:displayname>", body)
                state.mk(urllib.parse.unquote(self.path), m.group(1) if m else "Calendario")
                self._send(201)

    return H


class FakeServer:
    def __init__(self, sync=True):
        self.state = FakeState(sync)
        self.port = free_port()
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), _handler(self.state))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/" % self.port

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def requests_log(self):
        return list(self.state.requests)

    def clear_log(self):
        self.state.requests.clear()


class RadicaleServer:
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="nous-rad-")
        self.port = free_port()
        with open(os.path.join(self.tmp, "users"), "w") as f:
            f.write("%s:%s\n" % (USER, PASS))
        cfg = os.path.join(self.tmp, "config")
        with open(cfg, "w") as f:
            f.write("[server]\nhosts = 127.0.0.1:%d\n[auth]\ntype = htpasswd\nhtpasswd_filename = %s\n"
                    "htpasswd_encryption = plain\n[storage]\nfilesystem_folder = %s\n[logging]\nlevel = warning\n"
                    % (self.port, os.path.join(self.tmp, "users").replace("\\", "/"),
                       os.path.join(self.tmp, "data").replace("\\", "/")))
        self.proc = subprocess.Popen([sys.executable, "-m", "radicale", "--config", cfg],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.url = "http://127.0.0.1:%d/" % self.port
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.25)

    def stop(self):
        self.proc.terminate()
        self.proc.wait(10)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def requests_log(self):
        return []

    def clear_log(self):
        pass


def have_radicale():
    try:
        import radicale  # noqa: F401
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- "outro aparelho"

class Other:
    """Outro cliente mexendo direto no servidor (celular, Thunderbird...)."""

    def __init__(self, base):
        self.base = base
        self.s = requests.Session()
        self.s.auth = (USER, PASS)

    def mkcal(self, path, name):
        body = ('<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:set><d:prop>'
                '<d:displayname>%s</d:displayname><c:supported-calendar-component-set><c:comp name="VEVENT"/>'
                '</c:supported-calendar-component-set></d:prop></d:set></c:mkcalendar>' % name)
        r = self.s.request("MKCALENDAR", self.base + path.lstrip("/"), data=body.encode(),
                           headers={"Content-Type": "application/xml"})
        assert r.status_code == 201, r.status_code

    def put(self, cal, name, ics, if_match=None):
        h = {"Content-Type": "text/calendar"}
        if if_match:
            h["If-Match"] = if_match
        r = self.s.put(self.base + cal.lstrip("/") + name, data=ics.encode("utf-8"), headers=h)
        assert r.status_code in (201, 204), (r.status_code, r.text)
        return r.headers.get("ETag")

    def delete(self, cal, name):
        r = self.s.delete(self.base + cal.lstrip("/") + name)
        assert r.status_code in (200, 204), r.status_code

    def get(self, cal, name):
        r = self.s.get(self.base + cal.lstrip("/") + name)
        return r.text if r.status_code == 200 else None

    def names(self, cal):
        r = self.s.request("PROPFIND", self.base + cal.lstrip("/"), headers={"Depth": "1"},
                           data=b'<d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>')
        return sorted(h.rsplit("/", 1)[-1] for h in re.findall(r"<(?:\w+:)?href>([^<]*\.ics)</", r.text))


def vevent(uid, summary, start="DTSTART:20261103T120000Z", end="DTEND:20261103T130000Z", extra=""):
    return ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Teste//PT\r\nBEGIN:VEVENT\r\nUID:%s\r\nDTSTAMP:20261001T000000Z\r\n"
            "SUMMARY:%s\r\n%s\r\n%s\r\n%sEND:VEVENT\r\nEND:VCALENDAR\r\n" % (uid, summary, start, end, extra))


def epoch(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp())


# ---------------------------------------------------------------- os testes

class Base:
    """Roda a mesma bateria em cada tipo de servidor (subclasses mais abaixo)."""
    make_server = None
    CAL = "/gui/pessoal/"

    @classmethod
    def setUpClass(cls):
        cls.server = cls.make_server()

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="nous-ag-")
        os.environ["DATA_DIR"] = self.tmp
        os.environ["NOUS_CALDAV_PLAIN"] = ""  # cofre de verdade (DPAPI no Windows)
        self.cx = db.connect()
        self.other = Other(self.server.url)
        # calendario novo e limpo por teste (nome unico)
        self.CAL = "/gui/c%s/" % db.new_id()
        self.other.mkcal(self.CAL, "Pessoal")
        self.aid = cd.connect(self.cx, UID, self.server.url, USER, PASS, "Teste")
        acc = cd.accounts_list(self.cx, UID)[0]
        self.cal = next(c for c in acc["calendars"] if c["url"].endswith(self.CAL))
        cd.choose_calendars(self.cx, UID, self.aid, [self.cal["id"]], self.cal["id"])

    def tearDown(self):
        self.cx.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- ajudantes
    def sync(self, force=False):
        r = cd.sync_account(self.cx, self.aid, UID, force)
        self.assertTrue(r.get("ok"), r)
        return r

    def evs(self, source=None):
        q = "SELECT * FROM events WHERE user_id=?"
        a = [UID]
        if source:
            q += " AND source=?"
            a.append(source)
        return [dict(r) for r in self.cx.execute(q, a)]

    def dav_ev(self, title):
        m = [e for e in self.evs("dav:" + self.cal["id"]) if e["title"] == title]
        self.assertEqual(len(m), 1, "esperava 1 evento %r, achei %r" % (title, [e["title"] for e in self.evs()]))
        return m[0]

    def notifs(self):
        return [dict(r) for r in self.cx.execute("SELECT * FROM notif WHERE kind='sincronizacao'")]

    def new_here(self, title, start="2026-11-03T09:00", end="2026-11-03T10:00", **kw):
        d = dict(title=title, start_at=start, end_at=end, **kw)
        eid = db.event_create(self.cx, UID, d, source="dav:" + self.cal["id"], dirty=2)
        self.cx.commit()
        return eid

    # --- conta / segredo
    def test_senha_guardada_protegida(self):
        sec = self.cx.execute("SELECT secret FROM caldav_accounts").fetchone()[0]
        self.assertNotIn(PASS, sec)
        if os.name == "nt":
            self.assertTrue(sec.startswith("dpapi:"))
        self.assertEqual(cd.unseal(sec), PASS)
        self.assertNotIn("secret", cd.accounts_list(self.cx, UID)[0])

    def test_senha_errada_mensagem_simples(self):
        with self.assertRaises(cd.DavError) as e:
            cd.connect(self.cx, UID, self.server.url, USER, "errada")
        self.assertIn("SENHA DE APP", str(e.exception))

    def test_google_explica(self):
        with self.assertRaises(cd.DavError) as e:
            cd.connect(self.cx, UID, "https://apidata.googleusercontent.com/caldav/v2/x@gmail.com/events",
                       "x@gmail.com", "abc")
        self.assertIn("Google", str(e.exception))

    def test_https_obrigatorio_fora_do_pc(self):
        with self.assertRaises(cd.DavError):
            cd.check_url("http://agenda.exemplo.com/dav")
        self.assertEqual(cd.check_url("agenda.exemplo.com/dav"), "https://agenda.exemplo.com/dav")

    # --- servidor -> Nous
    def test_desce_novo_alterado_apagado(self):
        e1 = self.other.put(self.CAL, "a.ics", vevent("a@x", "Reuniao"))
        self.other.put(self.CAL, "b.ics", vevent("b@x", "Almoco", "DTSTART:20261104T150000Z", "DTEND:20261104T160000Z"))
        r = self.sync()
        self.assertEqual(sorted(e["title"] for e in self.evs()), ["Almoco", "Reuniao"])
        self.assertEqual(self.dav_ev("Reuniao")["start_at"], epoch(2026, 11, 3, 12))
        self.assertIn("2 recebidos", r["summary"])
        # alterado la'
        self.other.put(self.CAL, "a.ics", vevent("a@x", "Reuniao com o time", extra="LOCATION:Sala 2\r\n"), if_match=e1)
        # apagado la'
        self.other.delete(self.CAL, "b.ics")
        self.sync()
        self.assertEqual([e["title"] for e in self.evs()], ["Reuniao com o time"])
        self.assertEqual(self.dav_ev("Reuniao com o time")["location"], "Sala 2")

    def test_sem_mudanca_nao_baixa_de_novo(self):
        self.other.put(self.CAL, "a.ics", vevent("a@x", "Reuniao"))
        self.sync()
        self.server.clear_log()
        self.sync()
        self.assertEqual(len(self.evs()), 1)
        self.assertNotIn("PUT", [m for m, _ in self.server.requests_log()])

    def test_fuso_sao_paulo_e_dia_inteiro_e_recorrencia(self):
        self.other.put(self.CAL, "sp.ics", vevent(
            "sp@x", "Aula", "DTSTART;TZID=America/Sao_Paulo:20261103T090000", "DTEND;TZID=America/Sao_Paulo:20261103T100000",
            "RRULE:FREQ=WEEKLY;COUNT=4\r\nEXDATE;TZID=America/Sao_Paulo:20261110T090000\r\n"))
        self.other.put(self.CAL, "dia.ics", vevent("dia@x", "Feriado", "DTSTART;VALUE=DATE:20261115", "DTEND;VALUE=DATE:20261116"))
        self.sync()
        aula = self.dav_ev("Aula")
        self.assertEqual(aula["start_at"], epoch(2026, 11, 3, 12))  # 09:00 em Sao Paulo = 12:00 UTC
        self.assertEqual(aula["rrule"], "FREQ=WEEKLY;COUNT=4")
        occ = [o["occ_start"] for o in db.events_between(self.cx, UID, epoch(2026, 11, 1), epoch(2026, 12, 15))
               if o["title"] == "Aula"]
        self.assertEqual(occ, [epoch(2026, 11, d, 12) for d in (3, 17, 24)])  # dia 10 saiu (EXDATE)
        fer = self.dav_ev("Feriado")
        self.assertEqual(fer["all_day"], 1)
        self.assertEqual(fer["end_at"] - fer["start_at"], 86400)

    def test_alarme_do_servidor_vira_lembrete_e_dispara(self):
        soon = int(time.time()) + 10 * 60
        dt = datetime.fromtimestamp(soon, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dt2 = datetime.fromtimestamp(soon + 3600, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.other.put(self.CAL, "al.ics", vevent("al@x", "Consulta", "DTSTART:" + dt, "DTEND:" + dt2,
                                                    "BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:x\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\n"))
        self.sync()
        self.assertEqual(self.dav_ev("Consulta")["remind_min"], 15)
        fired = db.due_reminders(self.cx)
        self.assertEqual([f[1] for f in fired], ["Consulta"])
        # sem alarme: usa o padrao do calendario (30 min)
        self.other.put(self.CAL, "sa.ics", vevent("sa@x", "Sem alarme"))
        self.sync()
        self.assertEqual(self.dav_ev("Sem alarme")["remind_min"], 30)

    # --- Nous -> servidor
    def test_sobe_novo_alterado_apagado(self):
        eid = self.new_here("Dentista", location="Centro, sala 3", remind_min=10)
        r = self.sync()
        self.assertIn("1 enviado", r["summary"])
        row = self.dav_ev("Dentista")
        self.assertEqual(row["dirty"], 0)
        name = row["href"].rsplit("/", 1)[-1]
        txt = self.other.get(self.CAL, name)
        self.assertIn("SUMMARY:Dentista", txt)
        self.assertIn("LOCATION:Centro\\, sala 3", txt)
        self.assertIn("DTSTART:20261103T120000Z", txt)
        self.assertIn("TRIGGER:-PT10M", txt)
        # alterado aqui
        db.event_update(self.cx, UID, eid, {"title": "Dentista (remarcado)", "start_at": "2026-11-04T09:00",
                                            "end_at": "2026-11-04T10:00"})
        self.assertEqual(self.dav_ev("Dentista (remarcado)")["dirty"], 1)
        self.sync()
        txt = self.other.get(self.CAL, name)
        self.assertIn("SUMMARY:Dentista (remarcado)", txt)
        self.assertIn("DTSTART:20261104T120000Z", txt)
        self.assertIn("SEQUENCE:1", txt)
        # apagado aqui
        db.event_delete(self.cx, UID, eid)
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM caldav_tomb").fetchone()[0], 1)
        self.sync()
        self.assertEqual(self.other.names(self.CAL), [])
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM caldav_tomb").fetchone()[0], 0)

    def test_apagar_evento_que_nunca_subiu_nao_deixa_rastro(self):
        eid = self.new_here("Rascunho")
        db.event_delete(self.cx, UID, eid)
        self.assertEqual(self.cx.execute("SELECT COUNT(*) FROM caldav_tomb").fetchone()[0], 0)
        self.sync()
        self.assertEqual(self.other.names(self.CAL), [])

    def test_recorrente_novo_vai_com_fuso_e_volta_igual(self):
        self.new_here("Pilates", rrule="FREQ=WEEKLY;BYDAY=TU", start="2026-11-03T07:30", end="2026-11-03T08:30")
        self.sync()
        row = self.dav_ev("Pilates")
        txt = self.other.get(self.CAL, row["href"].rsplit("/", 1)[-1])
        self.assertIn("DTSTART;TZID=America/Sao_Paulo:20261103T073000", txt)
        self.assertIn("RRULE:FREQ=WEEKLY;BYDAY=TU", txt)
        # relendo do servidor (forca) nada muda
        self.sync(force=True)
        again = self.dav_ev("Pilates")
        self.assertEqual((again["start_at"], again["end_at"], again["rrule"]),
                         (row["start_at"], row["end_at"], row["rrule"]))

    def test_alterar_preserva_o_que_o_nous_nao_conhece(self):
        extra = ("ATTENDEE;CN=Ana:mailto:ana@exemplo.com\r\nORGANIZER:mailto:eu@exemplo.com\r\n"
                 "BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:Lembrete\r\nTRIGGER:-PT30M\r\nEND:VALARM\r\n")
        self.other.put(self.CAL, "r.ics", vevent("r@x", "Reuniao", extra=extra))
        self.sync()
        row = self.dav_ev("Reuniao")
        db.event_update(self.cx, UID, row["id"], {"title": "Reuniao de pauta"})
        self.sync()
        txt = self.other.get(self.CAL, "r.ics")
        self.assertIn("SUMMARY:Reuniao de pauta", txt)
        self.assertIn("ATTENDEE;CN=Ana:mailto:ana@exemplo.com", txt)
        self.assertIn("ORGANIZER:mailto:eu@exemplo.com", txt)
        self.assertEqual(txt.count("BEGIN:VALARM"), 1)
        self.assertIn("DESCRIPTION:Lembrete", txt)  # o do alarme continua
        # trocar o aviso troca so' o alarme
        db.event_update(self.cx, UID, row["id"], {"remind_min": 60})
        self.sync()
        txt = self.other.get(self.CAL, "r.ics")
        self.assertEqual(txt.count("BEGIN:VALARM"), 1)
        self.assertEqual(cd._alarm_minutes(db._unfold(txt)), 60)  # (o servidor pode reescrever como -PT1H)
        self.assertIn("ATTENDEE;CN=Ana", txt)

    def test_acentos_e_linhas_longas(self):
        t = "Reunião de planejamento estratégico com a diretoria — sessão única"
        self.new_here(t, description="ação " * 40)
        txt = cd.build_ics(self.evs()[0])  # o que sobe (o servidor pode reescrever a sua copia)
        self.sync()
        self.assertTrue(all(len(l.encode("utf-8")) <= 75 for l in txt.split("\r\n")))
        self.sync(force=True)
        self.assertEqual(self.dav_ev(t)["description"], ("ação " * 40).strip())

    # --- conflitos
    def _sincronizado(self, title="Reuniao"):
        etag = self.other.put(self.CAL, "c.ics", vevent("c@x", title))
        self.sync()
        return self.dav_ev(title), etag

    def test_conflito_alterado_nos_dois_lados_servidor_vence(self):
        row, etag = self._sincronizado()
        db.event_update(self.cx, UID, row["id"], {"title": "Reuniao (minha ideia)"})
        self.other.put(self.CAL, "c.ics", vevent("c@x", "Reuniao (ideia do chefe)"), if_match=etag)
        r = self.sync()
        titles = sorted(e["title"] for e in self.evs())
        self.assertEqual(titles, ["Reuniao (ideia do chefe)", "Reuniao (minha ideia) (versao do Nous)"])
        copia = [e for e in self.evs() if "versao do Nous" in e["title"]][0]
        self.assertEqual((copia["source"], copia["dirty"]), ("local", 0))  # a copia fica so' no Nous
        self.assertEqual(len(r["conflicts"]), 1)
        self.assertEqual(len(self.notifs()), 1)
        self.assertIn("servidor", self.notifs()[0]["body"])
        self.assertEqual(self.dav_ev("Reuniao (ideia do chefe)")["dirty"], 0)
        self.assertNotIn("minha ideia", self.other.get(self.CAL, "c.ics"))

    def test_conflito_alterado_aqui_apagado_la(self):
        row, _ = self._sincronizado()
        db.event_update(self.cx, UID, row["id"], {"title": "Reuniao mudada"})
        self.other.delete(self.CAL, "c.ics")
        self.sync()
        self.assertEqual([(e["title"], e["source"]) for e in self.evs()], [("Reuniao mudada (versao do Nous)", "local")])
        self.assertEqual(len(self.notifs()), 1)

    def test_conflito_apagado_aqui_alterado_la(self):
        row, etag = self._sincronizado()
        db.event_delete(self.cx, UID, row["id"])
        self.other.put(self.CAL, "c.ics", vevent("c@x", "Reuniao mudada la"), if_match=etag)
        self.sync()
        self.assertEqual([e["title"] for e in self.evs()], ["Reuniao mudada la"])
        self.assertEqual(self.other.names(self.CAL), ["c.ics"])  # nao foi apagado
        self.assertEqual(len(self.notifs()), 1)

    def test_apagado_nos_dois_lados_nao_e_conflito(self):
        row, _ = self._sincronizado()
        db.event_delete(self.cx, UID, row["id"])
        self.other.delete(self.CAL, "c.ics")
        r = self.sync()
        self.assertEqual((self.evs(), r["conflicts"], self.notifs()), ([], [], []))

    def test_corrida_no_envio_412_vira_conflito(self):
        row, etag = self._sincronizado()
        db.event_update(self.cx, UID, row["id"], {"title": "Minha"})
        self.other.put(self.CAL, "c.ics", vevent("c@x", "Dele"), if_match=etag)
        acc = dict(self.cx.execute("SELECT * FROM caldav_accounts").fetchone())
        cal = dict(self.cx.execute("SELECT * FROM caldav_cals WHERE id=?", (self.cal["id"],)).fetchone())
        st = cd.Stats()
        cd._push(self.cx, cd.Dav(USER, PASS), acc, cal, st)  # sem puxar antes: o servidor recusa (If-Match)
        self.assertEqual(sorted(e["title"] for e in self.evs()), ["Dele", "Minha (versao do Nous)"])
        self.assertEqual(len(st.conflicts), 1)

    # --- escolha de calendarios / desconectar
    def test_desmarcar_calendario_tira_do_nous_mas_nao_apaga_no_servidor(self):
        self.other.put(self.CAL, "a.ics", vevent("a@x", "Reuniao"))
        self.sync()
        cd.choose_calendars(self.cx, UID, self.aid, [], None)
        self.assertEqual(self.evs(), [])
        self.assertEqual(self.other.names(self.CAL), ["a.ics"])

    def test_desconectar_limpa_tudo(self):
        self.other.put(self.CAL, "a.ics", vevent("a@x", "Reuniao"))
        self.sync()
        cd.disconnect(self.cx, UID, self.aid)
        self.assertEqual((self.evs(), cd.accounts_list(self.cx, UID)), ([], []))
        self.assertEqual(self.other.names(self.CAL), ["a.ics"])

    def test_pendentes_e_estado_da_conta(self):
        self.new_here("Pendente")
        self.assertEqual(cd.accounts_list(self.cx, UID)[0]["pending"], 1)
        self.sync()
        a = cd.accounts_list(self.cx, UID)[0]
        self.assertEqual(a["pending"], 0)
        self.assertTrue(a["last_ok"] and not a["last_error"])

    def test_servidor_fora_do_ar_guarda_erro_e_mantem_pendencia(self):
        self.new_here("Pendente")
        self.cx.execute("UPDATE caldav_accounts SET url=?, home_url=?", ("http://127.0.0.1:1/", "http://127.0.0.1:1/"))
        self.cx.execute("UPDATE caldav_cals SET url=?", ("http://127.0.0.1:1/x/",))
        self.cx.commit()
        r = cd.sync_account(self.cx, self.aid)
        self.assertFalse(r["ok"])
        a = cd.accounts_list(self.cx, UID)[0]
        self.assertTrue(a["last_error"])
        self.assertEqual(a["pending"], 1)

    def test_relogio_so_chama_quando_deve(self):
        due = cd.accounts_due(self.cx, 300, now=db.now() + 10)
        self.assertEqual(due, [self.aid])
        cd._last_try[self.aid] = (db.now(), False)
        self.assertEqual(cd.accounts_due(self.cx, 300), [])
        self.assertEqual(cd.accounts_due(self.cx, 300, now=db.now() + 301), [self.aid])


@unittest.skipUnless(HAVE_DEPS, "faltam requests/dateutil")
class PatchIcsTests(unittest.TestCase):
    def test_patch_mexe_so_no_que_mudou(self):
        raw = vevent("p@x", "Velho", "DTSTART;TZID=America/Sao_Paulo:20261103T090000",
                     "DTEND;TZID=America/Sao_Paulo:20261103T100000",
                     "X-CUSTOM:abc\r\nATTENDEE:mailto:a@b.com\r\n")
        ev = {k: v for k, v in db.parse_ics(raw)[0].items()}
        ev.update(title="Novo", description="", location="", rrule=None, remind_min=None, exdates=None, all_day=0)
        out = cd.patch_ics(raw, ev)
        self.assertIn("SUMMARY:Novo", out)
        self.assertIn("X-CUSTOM:abc", out)
        self.assertIn("ATTENDEE:mailto:a@b.com", out)
        self.assertIn("DTSTART;TZID=America/Sao_Paulo:20261103T090000", out)  # horario intacto
        # horario alterado continua no fuso original
        ev["start_at"] += 3600
        ev["end_at"] += 3600
        out = cd.patch_ics(raw, ev)
        self.assertIn("DTSTART;TZID=America/Sao_Paulo:20261103T100000", out)

    def test_serie_com_excecao_continua_inteira(self):
        raw = ("BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:s@x\r\nSUMMARY:Serie\r\nDTSTART:20261103T120000Z\r\n"
               "DTEND:20261103T130000Z\r\nRRULE:FREQ=DAILY;COUNT=3\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nUID:s@x\r\n"
               "RECURRENCE-ID:20261104T120000Z\r\nSUMMARY:Excecao\r\nDTSTART:20261104T150000Z\r\nDTEND:20261104T160000Z\r\n"
               "END:VEVENT\r\nEND:VCALENDAR\r\n")
        ev = db.parse_ics(raw)[0]
        ev.update(title="Serie 2", description="", location="", remind_min=None, exdates=None, all_day=0)
        out = cd.patch_ics(raw, ev)
        self.assertIn("SUMMARY:Serie 2", out)
        self.assertIn("SUMMARY:Excecao", out)
        self.assertEqual(out.count("BEGIN:VEVENT"), 2)


@unittest.skipUnless(HAVE_DEPS, "faltam requests/dateutil")
class FakeSync(Base, unittest.TestCase):
    make_server = staticmethod(lambda: FakeServer(sync=True))


@unittest.skipUnless(HAVE_DEPS, "faltam requests/dateutil")
class FakeCtag(Base, unittest.TestCase):
    """Servidor sem sync-token: so' ctag + lista de etags."""
    make_server = staticmethod(lambda: FakeServer(sync=False))


@unittest.skipUnless(HAVE_DEPS and have_radicale(), "Radicale nao instalado (pip install radicale)")
class Radicale(Base, unittest.TestCase):
    make_server = staticmethod(RadicaleServer)


if __name__ == "__main__":
    unittest.main()
