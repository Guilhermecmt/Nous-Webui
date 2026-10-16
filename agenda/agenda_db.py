# -*- coding: utf-8 -*-
"""
Agenda do Nous - camada de dados (SQLite em <DATA_DIR>/nous_agenda.sqlite3).

  notes    notas e lembretes (com data, aviso e repeticao)
  events   compromissos do calendario (locais, importados de .ics ou de uma
           assinatura de calendario, ex.: o endereco iCal secreto do Google)
  subs     assinaturas de calendario (URL .ics, sincronizada de hora em hora)
  notif    fila de avisos que o painel do Nous mostra (e marca como vistos)
  tasks    tarefas agendadas (ver agenda_tasks.py)

Horarios sao epoch em segundos (UTC). Dia inteiro = meia-noite local.
Sem dependencia nova: dateutil (rrule) ja vem no venv do Open WebUI.
"""
import os
import re
import json
import time
import uuid
import sqlite3
from datetime import datetime, timedelta, timezone

from dateutil import tz
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

LOCAL = tz.tzlocal()
DB_NAME = "nous_agenda.sqlite3"

# Repeticoes simples da interface -> RRULE (eventos) / passo (notas)
REPEATS = {
    "diario": "FREQ=DAILY",
    "dias_uteis": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
    "semanal": "FREQ=WEEKLY",
    "mensal": "FREQ=MONTHLY",
    "anual": "FREQ=YEARLY",
}


def data_dir():
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def db_path():
    return os.path.join(data_dir(), DB_NAME)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '', pinned INTEGER NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0,
    due_at INTEGER, remind_at INTEGER, repeat TEXT, notified_at INTEGER,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS notes_user ON notes(user_id, done);
CREATE INDEX IF NOT EXISTS notes_remind ON notes(remind_at);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    start_at INTEGER NOT NULL, end_at INTEGER NOT NULL,
    all_day INTEGER NOT NULL DEFAULT 0, rrule TEXT, exdates TEXT,
    remind_min INTEGER, uid TEXT, source TEXT NOT NULL DEFAULT 'local',
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS events_user ON events(user_id, start_at);
CREATE INDEX IF NOT EXISTS events_source ON events(source);

CREATE TABLE IF NOT EXISTS ev_notified (k TEXT PRIMARY KEY, at INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS subs (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL, remind_min INTEGER,
    last_sync INTEGER, last_error TEXT, created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notif (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
    kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
    ref TEXT, created_at INTEGER NOT NULL, seen INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS notif_user ON notif(user_id, seen);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'pergunta', prompt TEXT NOT NULL DEFAULT '',
    schedule TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
    next_run INTEGER, last_run INTEGER, last_status TEXT, last_note TEXT,
    email INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
"""


def connect():
    os.makedirs(data_dir(), exist_ok=True)
    cx = sqlite3.connect(db_path(), timeout=15)
    cx.row_factory = sqlite3.Row
    cx.execute("PRAGMA journal_mode=WAL")
    cx.executescript(_SCHEMA)
    return cx


def now():
    return int(time.time())


def new_id():
    return uuid.uuid4().hex[:16]


def _row(r):
    return dict(r) if r is not None else None


def _int_or_none(v):
    if v in (None, "", "null"):
        return None
    return int(v)


# ------------------------------------------------------------------ datas

def local_dt(ts):
    return datetime.fromtimestamp(ts, LOCAL)


def to_ts(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL)
    return int(dt.timestamp())


def parse_when(s):
    """ISO local ('2026-10-17T09:00', '2026-10-17') ou epoch -> epoch."""
    if s in (None, ""):
        return None
    if isinstance(s, (int, float)):
        return int(s)
    s = str(s).strip()
    if s.isdigit():
        return int(s)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return to_ts(dt)


def next_repeat(ts, repeat):
    """Proxima ocorrencia de uma nota repetida, a partir de ts."""
    d = local_dt(ts)
    if repeat == "diario":
        d += timedelta(days=1)
    elif repeat == "dias_uteis":
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
    elif repeat == "semanal":
        d += timedelta(weeks=1)
    elif repeat == "mensal":
        d += relativedelta(months=1)
    elif repeat == "anual":
        d += relativedelta(years=1)
    else:
        return None
    return to_ts(d)


# ------------------------------------------------------------------ notas

NOTE_FIELDS = ("title", "body", "tags", "pinned", "done", "due_at", "remind_at", "repeat")


def _clean_note(d):
    out = {}
    for k in NOTE_FIELDS:
        if k not in d:
            continue
        v = d[k]
        if k in ("due_at", "remind_at"):
            v = parse_when(v)
        elif k in ("pinned", "done"):
            v = 1 if v else 0
        elif k == "repeat":
            v = v if v in REPEATS else None
        else:
            v = (v or "").strip()
        out[k] = v
    return out


def note_create(cx, user_id, d):
    f = _clean_note(d)
    if not (f.get("title") or f.get("body")):
        raise ValueError("nota vazia")
    t = now()
    nid = new_id()
    f.setdefault("title", "")
    f.setdefault("body", "")
    cx.execute(
        """INSERT INTO notes (id, user_id, title, body, tags, pinned, done, due_at,
               remind_at, repeat, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (nid, user_id, f["title"], f["body"], f.get("tags", ""), f.get("pinned", 0),
         f.get("done", 0), f.get("due_at"), f.get("remind_at"), f.get("repeat"), t, t))
    cx.commit()
    return note_get(cx, user_id, nid)


def note_get(cx, user_id, nid):
    return _row(cx.execute("SELECT * FROM notes WHERE id=? AND user_id=?",
                           (nid, user_id)).fetchone())


def note_update(cx, user_id, nid, d):
    f = _clean_note(d)
    if not f:
        return note_get(cx, user_id, nid)
    if "remind_at" in f:
        f["notified_at"] = None  # novo horario -> avisar de novo
    sets = ", ".join(f"{k}=?" for k in f)
    cx.execute(f"UPDATE notes SET {sets}, updated_at=? WHERE id=? AND user_id=?",
               (*f.values(), now(), nid, user_id))
    cx.commit()
    return note_get(cx, user_id, nid)


def note_delete(cx, user_id, nid):
    cx.execute("DELETE FROM notes WHERE id=? AND user_id=?", (nid, user_id))
    cx.commit()


def notes_list(cx, user_id, q=None, done=None, limit=300):
    sql, args = "SELECT * FROM notes WHERE user_id=?", [user_id]
    if done is not None:
        sql += " AND done=?"
        args.append(1 if done else 0)
    if q:
        sql += " AND (title LIKE ? OR body LIKE ? OR tags LIKE ?)"
        args += [f"%{q}%"] * 3
    sql += (" ORDER BY pinned DESC, done ASC,"
            " CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at ASC, updated_at DESC LIMIT ?")
    args.append(limit)
    return [dict(r) for r in cx.execute(sql, args)]


# ------------------------------------------------------------------ eventos

EVENT_FIELDS = ("title", "description", "location", "start_at", "end_at",
                "all_day", "rrule", "remind_min")


def _clean_event(d):
    out = {}
    for k in EVENT_FIELDS:
        if k not in d:
            continue
        v = d[k]
        if k in ("start_at", "end_at"):
            v = parse_when(v)
        elif k == "all_day":
            v = 1 if v else 0
        elif k == "remind_min":
            v = _int_or_none(v)
        elif k == "rrule":
            v = (v or "").strip() or None
        else:
            v = (v or "").strip()
        out[k] = v
    rep = d.get("repeat")
    if rep is not None:
        out["rrule"] = REPEATS.get(rep)
    return out


def event_create(cx, user_id, d, source="local", uid=None, exdates=None):
    f = _clean_event(d)
    if not f.get("title") or not f.get("start_at"):
        raise ValueError("evento precisa de titulo e inicio")
    if f.get("all_day"):
        s = local_dt(f["start_at"]).replace(hour=0, minute=0, second=0)
        f["start_at"] = to_ts(s)
    if not f.get("end_at") or f["end_at"] <= f["start_at"]:
        f["end_at"] = f["start_at"] + (86400 if f.get("all_day") else 3600)
    t = now()
    eid = new_id()
    cx.execute(
        """INSERT INTO events (id, user_id, title, description, location, start_at, end_at,
               all_day, rrule, exdates, remind_min, uid, source, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (eid, user_id, f["title"], f.get("description", ""), f.get("location", ""),
         f["start_at"], f["end_at"], f.get("all_day", 0), f.get("rrule"),
         json.dumps(exdates) if exdates else None, f.get("remind_min"),
         uid or (eid + "@nous"), source, t, t))
    return eid


def event_get(cx, user_id, eid):
    return _row(cx.execute("SELECT * FROM events WHERE id=? AND user_id=?",
                           (eid, user_id)).fetchone())


def event_update(cx, user_id, eid, d):
    f = _clean_event(d)
    if f:
        sets = ", ".join(f"{k}=?" for k in f)
        cx.execute(f"UPDATE events SET {sets}, updated_at=? WHERE id=? AND user_id=? AND source='local'",
                   (*f.values(), now(), eid, user_id))
        cx.commit()
    return event_get(cx, user_id, eid)


def event_delete(cx, user_id, eid):
    cx.execute("DELETE FROM events WHERE id=? AND user_id=?", (eid, user_id))
    cx.commit()


def _occurrences(ev, t0, t1):
    """Inicios (epoch) das ocorrencias de ev que cruzam [t0, t1)."""
    dur = max(60, ev["end_at"] - ev["start_at"])
    if not ev["rrule"]:
        if ev["start_at"] < t1 and ev["start_at"] + dur > t0:
            return [ev["start_at"]]
        return []
    ex = set(json.loads(ev["exdates"])) if ev["exdates"] else set()
    start = local_dt(ev["start_at"])
    lo, hi = local_dt(t0 - dur), local_dt(t1)
    rule = None
    # UNTIL com/sem 'Z' precisa casar com o dtstart (com/sem fuso) no dateutil
    for dt in (start, start.replace(tzinfo=None)):
        try:
            rule = rrulestr(ev["rrule"], dtstart=dt)
            occ = rule.between(lo if dt.tzinfo else lo.replace(tzinfo=None),
                               hi if dt.tzinfo else hi.replace(tzinfo=None), inc=True)
            break
        except Exception:
            rule = None
    if rule is None:
        try:  # ultima tentativa: sem o UNTIL
            r = re.sub(r";?UNTIL=[^;]*", "", ev["rrule"])
            occ = rrulestr(r, dtstart=start).between(lo, hi, inc=True)
        except Exception:
            return [ev["start_at"]] if t0 <= ev["start_at"] < t1 else []
    out = []
    for o in occ[:500]:
        ts = to_ts(o)
        if ts not in ex and ts < t1 and ts + dur > t0:
            out.append(ts)
    return out


def events_between(cx, user_id, t0, t1):
    rows = cx.execute(
        """SELECT * FROM events WHERE user_id=? AND
               (rrule IS NOT NULL OR (start_at < ? AND end_at > ?))""",
        (user_id, t1, t0)).fetchall()
    out = []
    for r in rows:
        ev = dict(r)
        dur = max(60, ev["end_at"] - ev["start_at"])
        for s in _occurrences(ev, t0, t1):
            o = dict(ev)
            o["occ_start"], o["occ_end"] = s, s + dur
            out.append(o)
    out.sort(key=lambda e: (e["occ_start"], e["title"]))
    return out


def upcoming(cx, user_id, days=7):
    """Visao 'Hoje': atrasados + compromissos e lembretes dos proximos dias."""
    t = now()
    start_today = to_ts(local_dt(t).replace(hour=0, minute=0, second=0, microsecond=0))
    t1 = start_today + days * 86400
    evs = events_between(cx, user_id, start_today, t1)
    notes = [dict(r) for r in cx.execute(
        """SELECT * FROM notes WHERE user_id=? AND done=0 AND
               COALESCE(due_at, remind_at) IS NOT NULL AND COALESCE(due_at, remind_at) < ?
           ORDER BY COALESCE(due_at, remind_at)""", (user_id, t1))]
    return {"now": t, "from": start_today, "to": t1, "events": evs, "notes": notes}


# ------------------------------------------------------------------ avisos

def notify(cx, user_id, kind, title, body="", ref=None):
    cx.execute("INSERT INTO notif (user_id, kind, title, body, ref, created_at) VALUES (?,?,?,?,?,?)",
               (user_id, kind, title, body, ref, now()))
    cx.commit()


def notif_pending(cx, user_id):
    return [dict(r) for r in cx.execute(
        "SELECT * FROM notif WHERE user_id=? AND seen=0 ORDER BY id LIMIT 20", (user_id,))]


def notif_seen(cx, user_id, ids):
    if ids:
        q = ",".join("?" * len(ids))
        cx.execute(f"UPDATE notif SET seen=1 WHERE user_id=? AND id IN ({q})",
                   (user_id, *[int(i) for i in ids]))
    # fila nao cresce para sempre
    cx.execute("DELETE FROM notif WHERE seen=1 AND created_at < ?", (now() - 30 * 86400,))
    cx.commit()


def _fmt_hora(ts):
    d = local_dt(ts)
    return d.strftime("%H:%M")


def due_reminders(cx):
    """Gera os avisos vencidos. Devolve [(user_id, titulo, corpo)] para o toast."""
    t = now()
    fired = []
    for r in cx.execute(
            """SELECT * FROM notes WHERE done=0 AND remind_at IS NOT NULL AND remind_at <= ?
                   AND (notified_at IS NULL OR notified_at < remind_at)""", (t,)).fetchall():
        n = dict(r)
        title = n["title"] or (n["body"][:60] if n["body"] else "Lembrete")
        notify(cx, n["user_id"], "lembrete", title, n["body"] if n["title"] else "", n["id"])
        fired.append((n["user_id"], "Lembrete: " + title, n["body"][:200]))
        if n["repeat"]:
            nxt = n["remind_at"]
            for _ in range(400):  # pula ocorrencias perdidas com o PC desligado
                nxt = next_repeat(nxt, n["repeat"])
                if nxt is None or nxt > t:
                    break
            shift = (nxt - n["remind_at"]) if nxt else 0
            cx.execute("UPDATE notes SET remind_at=?, due_at=?, notified_at=? WHERE id=?",
                       (nxt, (n["due_at"] + shift) if n["due_at"] else None, t, n["id"]))
        else:
            cx.execute("UPDATE notes SET notified_at=? WHERE id=?", (t, n["id"]))
    cx.commit()

    # Compromissos com "avisar X min antes"
    horizon = t + 24 * 3600
    rows = cx.execute("SELECT DISTINCT user_id FROM events WHERE remind_min IS NOT NULL").fetchall()
    for (uid,) in rows:
        for ev in events_between(cx, uid, t - 300, horizon):
            if ev["remind_min"] is None:
                continue
            fire_at = ev["occ_start"] - ev["remind_min"] * 60
            if not (fire_at <= t < ev["occ_start"] + 300):
                continue
            k = f"{ev['id']}@{ev['occ_start']}"
            if cx.execute("SELECT 1 FROM ev_notified WHERE k=?", (k,)).fetchone():
                continue
            cx.execute("INSERT INTO ev_notified (k, at) VALUES (?,?)", (k, t))
            quando = "dia inteiro" if ev["all_day"] else "as " + _fmt_hora(ev["occ_start"])
            body = (quando + (" - " + ev["location"] if ev["location"] else ""))
            notify(cx, uid, "compromisso", ev["title"], body, ev["id"])
            fired.append((uid, ev["title"], body))
    cx.execute("DELETE FROM ev_notified WHERE at < ?", (t - 7 * 86400,))
    cx.commit()
    return fired


# ------------------------------------------------------------------ ICS

def _unfold(text):
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif raw:
            lines.append(raw)
    return lines


def _unescape(v):
    return (v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",")
             .replace("\\;", ";").replace("\\\\", "\\"))


def _escape(v):
    return (v or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _parse_dt(value, params):
    """-> (epoch, all_day)"""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        d = datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=LOCAL)
        return to_ts(d), True
    if value.endswith("Z"):
        d = datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return int(d.timestamp()), False
    d = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    zone = LOCAL
    tzid = params.get("TZID")
    if tzid and ZoneInfo is not None:
        try:
            zone = ZoneInfo(tzid.strip('"'))
        except Exception:
            zone = LOCAL  # TZIDs do Windows/Outlook: usa o fuso local
    return int(d.replace(tzinfo=zone).timestamp()), False


def parse_ics(text):
    """Lista de dicts de VEVENT (sem dependencia externa)."""
    events, cur = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            cur = {"exdates": []}
            continue
        if line == "END:VEVENT":
            if cur and cur.get("start_at") and not cur.get("cancelled"):
                events.append(cur)
            cur = None
            continue
        if cur is None or ":" not in line:
            continue
        head, value = line.split(":", 1)
        parts = head.split(";")
        name = parts[0].upper()
        params = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.upper()] = v
        try:
            if name == "DTSTART":
                cur["start_at"], cur["all_day"] = _parse_dt(value, params)
            elif name == "DTEND":
                cur["end_at"], _ = _parse_dt(value, params)
            elif name == "DURATION":
                m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value)
                if m:
                    w, d, h, mi, s = (int(x or 0) for x in m.groups())
                    cur["duration"] = (((w * 7 + d) * 24 + h) * 60 + mi) * 60 + s
            elif name == "SUMMARY":
                cur["title"] = _unescape(value)
            elif name == "DESCRIPTION":
                cur["description"] = _unescape(value)[:4000]
            elif name == "LOCATION":
                cur["location"] = _unescape(value)
            elif name == "RRULE":
                cur["rrule"] = value
            elif name == "EXDATE":
                for v in value.split(","):
                    cur["exdates"].append(_parse_dt(v, params)[0])
            elif name == "UID":
                cur["uid"] = value
            elif name == "STATUS" and value.upper() == "CANCELLED":
                cur["cancelled"] = True
            elif name == "RECURRENCE-ID":
                cur["recurrence_id"] = True
        except Exception:
            continue
    for e in events:
        if not e.get("end_at"):
            e["end_at"] = e["start_at"] + (e.get("duration") or (86400 if e.get("all_day") else 3600))
        e.setdefault("title", "(sem titulo)")
    return events


def import_ics(cx, user_id, text, source="local", remind_min=None):
    """Importa VEVENTs. source='sub:<id>' substitui todos os eventos da assinatura."""
    evs = parse_ics(text)
    if source != "local":
        cx.execute("DELETE FROM events WHERE user_id=? AND source=?", (user_id, source))
    else:
        # reimportar o mesmo arquivo nao duplica
        uids = [e["uid"] for e in evs if e.get("uid")]
        for i in range(0, len(uids), 500):
            chunk = uids[i:i + 500]
            cx.execute(f"DELETE FROM events WHERE user_id=? AND source='local' AND uid IN "
                       f"({','.join('?' * len(chunk))})", (user_id, *chunk))
    n = 0
    for e in evs:
        if e.get("recurrence_id"):
            continue  # excecoes de serie: a serie principal ja cobre a data
        d = {k: e.get(k) for k in ("title", "description", "location", "start_at",
                                    "end_at", "all_day", "rrule")}
        d["remind_min"] = remind_min
        try:
            event_create(cx, user_id, d, source=source, uid=e.get("uid"),
                         exdates=e.get("exdates") or None)
            n += 1
        except Exception:
            continue
    cx.commit()
    return n


def export_ics(cx, user_id):
    def fmt(ts, all_day):
        if all_day:
            return ";VALUE=DATE:" + local_dt(ts).strftime("%Y%m%d")
        return ":" + datetime.fromtimestamp(ts, timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Nous//Agenda//PT"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for r in cx.execute("SELECT * FROM events WHERE user_id=? AND source='local'", (user_id,)):
        e = dict(r)
        out += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}",
                "DTSTART" + fmt(e["start_at"], e["all_day"]),
                "DTEND" + fmt(e["end_at"], e["all_day"]),
                "SUMMARY:" + _escape(e["title"])]
        if e["description"]:
            out.append("DESCRIPTION:" + _escape(e["description"]))
        if e["location"]:
            out.append("LOCATION:" + _escape(e["location"]))
        if e["rrule"]:
            out.append("RRULE:" + e["rrule"])
        out.append("END:VEVENT")
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"


# ------------------------------------------------------------------ assinaturas

def subs_list(cx, user_id):
    return [dict(r) for r in cx.execute(
        "SELECT * FROM subs WHERE user_id=? ORDER BY created_at", (user_id,))]


def sub_create(cx, user_id, name, url, remind_min=None):
    url = (url or "").strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[9:]
    if not re.match(r"https?://", url, re.I):
        raise ValueError("endereco precisa comecar com https://")
    sid = new_id()
    cx.execute("INSERT INTO subs (id, user_id, name, url, remind_min, created_at) VALUES (?,?,?,?,?,?)",
               (sid, user_id, (name or "").strip() or "Calendario", url,
                _int_or_none(remind_min), now()))
    cx.commit()
    return sid


def sub_delete(cx, user_id, sid):
    cx.execute("DELETE FROM subs WHERE id=? AND user_id=?", (sid, user_id))
    cx.execute("DELETE FROM events WHERE user_id=? AND source=?", (user_id, "sub:" + sid))
    cx.commit()
