# -*- coding: utf-8 -*-
"""
Nous Agenda API - micro-servico REST local, porta 8996.

Notas e lembretes, calendario (com sincronizacao CalDAV) e tarefas agendadas. Um relogio interno (a cada
20 s) dispara os lembretes e as tarefas MESMO com o navegador fechado: o aviso
aparece como notificacao do Windows e fica na fila que o painel do Nous mostra.

Rotas (todas com user_id, como a Memory API):
  GET  /health
  GET  /today?user_id=&days=7          compromissos + lembretes dos proximos dias
  GET  /notes?user_id=&q=&done=        POST /notes  POST /notes/update  POST /notes/delete
  GET  /events?user_id=&from=&to=      POST /events POST /events/update POST /events/delete
  POST /ics/import {user_id, ics}      GET  /ics/export?user_id=
  GET  /caldav?user_id=                contas CalDAV (sem a senha), calendarios e estado
  POST /caldav/connect {server, username, password, name}   testa e guarda a conta
  POST /caldav/calendars {account_id, enabled:[ids], default_id}  escolhe o que sincronizar
  POST /caldav/sync {account_id?}      sincroniza agora    POST /caldav/disconnect {account_id}
  GET  /subs?user_id=                  POST /subs   POST /subs/delete   POST /subs/sync
  GET  /tasks?user_id=                 POST /tasks  POST /tasks/update  POST /tasks/delete
  POST /tasks/run {user_id, id}        roda agora
  GET  /recent?user_id=&secs=180       quantas notas/compromissos acabaram de ser criados
  GET  /settings?user_id=              POST /settings {aviso_email, ntfy_topico}
  POST /settings/test                  manda um aviso de teste pelos canais ligados
  GET  /notifications?user_id=         POST /notifications/seen {user_id, ids}

CORS apenas de origem local (mesmo padrao do monitor).
"""
import os
import sys
import time
import asyncio
import sqlite3
import subprocess
import urllib.parse

import requests
from aiohttp import web

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import agenda_db as db       # noqa: E402
import agenda_tasks as tasks  # noqa: E402
import caldav_sync as dav    # noqa: E402

PORT = 8996  # NOUS_AGENDA_PORT muda (testes)
TICK_S = 20
SUB_SYNC_S = 3600
CALDAV_SYNC_S = 300  # CalDAV: de 5 em 5 min, e ~1 min depois de uma mudanca feita aqui
_running = set()  # ids de tarefas rodando agora


# ----------------------------------------------------------------- CORS
def _origin_ok(origin):
    if not origin:
        return True
    try:
        host = urllib.parse.urlparse(origin).hostname
    except Exception:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _host_ok(request):
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
    return host in ("localhost", "127.0.0.1", "::1")


def _cors_headers(origin):
    return {
        "Access-Control-Allow-Origin": origin if (origin and _origin_ok(origin)) else "null",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


@web.middleware
async def cors_mw(request, handler):
    origin = request.headers.get("Origin")
    if not _origin_ok(origin) or not _host_ok(request):
        return web.json_response({"error": "forbidden origin"}, status=403,
                                 headers=_cors_headers(origin))
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_cors_headers(origin))
    try:
        resp = await handler(request)
    except ValueError as e:  # validacao: mensagem amigavel para o painel
        resp = web.json_response({"error": str(e)}, status=400)
    resp.headers.update(_cors_headers(origin))
    return resp


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def _uid(d):
    u = (d.get("user_id") or "").strip()
    if not u:
        raise ValueError("user_id ausente")
    return u


def _ok(data=None, **kw):
    return web.json_response(data if data is not None else {"ok": True, **kw})


# ----------------------------------------------------------------- toast
# Notificacao nativa do Windows sem modulo extra (API WinRT via PowerShell).
# O AppId do PowerShell e' registrado em todo Windows 10/11, entao o toast
# aparece mesmo sem o Nous ter um atalho com AppUserModelID proprio.
_PS_TOAST = r"""
$ErrorActionPreference='SilentlyContinue'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$t = [Security.SecurityElement]::Escape($env:NOUS_TOAST_T)
$b = [Security.SecurityElement]::Escape($env:NOUS_TOAST_B)
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>")
$id = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show([Windows.UI.Notifications.ToastNotification]::new($x))
"""


def toast(title, body):
    if os.name != "nt" or os.environ.get("NOUS_NO_TOAST"):
        return
    env = dict(os.environ, NOUS_TOAST_T=("Nous - " + title)[:120], NOUS_TOAST_B=(body or "")[:240])
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PS_TOAST],
                         env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


# ----------------------------------------------------------------- outros canais
NTFY_URL = os.environ.get("NOUS_NTFY_URL", "https://ntfy.sh").rstrip("/")


def deliver(cx, uid, title, body):
    """Alem do aviso do Windows: e-mail para a propria conta e/ou celular (ntfy),
    se o usuario ligou em Agenda > Avisos. Falha de um canal nao afeta os outros."""
    s = db.settings_get(cx, uid)
    if s["aviso_email"] == "1":
        try:
            tasks.send_email_to_self("[Nous] " + title, body or title)
        except Exception:
            pass
    if s["ntfy_topico"]:
        try:
            # JSON (e nao headers) para acentos chegarem certos no celular
            requests.post(NTFY_URL + "/", json={"topic": s["ntfy_topico"], "title": "Nous - " + title,
                                                "message": body or title, "tags": ["bell"]}, timeout=10)
        except Exception:
            pass


# ----------------------------------------------------------------- GPU livre
# Tarefas agendadas esperam o usuario parar de conversar: com uma GPU so', uma
# tarefa rodando no meio da conversa deixaria as respostas lentas. Adia em
# blocos de 5 min, no maximo 6 vezes (30 min), e depois roda de qualquer jeito.
ACTIVE_SECS = 120
DEFER_SECS = 300
MAX_DEFERS = 6
_defers = {}  # task_id -> quantas vezes ja' adiou


def user_active():
    p = os.path.join(db.data_dir(), "webui.db")
    if not os.path.isfile(p):
        return False
    try:
        wx = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
        try:
            last = wx.execute("SELECT MAX(updated_at) FROM chat").fetchone()[0] or 0
        finally:
            wx.close()
    except Exception:
        return False
    if last > 10 ** 12:  # alguns bancos guardam em ns/ms
        last = last / (10 ** 9 if last > 10 ** 15 else 10 ** 3)
    return (time.time() - last) < ACTIVE_SECS


# ----------------------------------------------------------------- relogio
def _sync_sub(cx, sub):
    try:
        r = requests.get(sub["url"], timeout=30, headers={"User-Agent": "Nous-Agenda/1.0"})
        r.raise_for_status()
        n = db.import_ics(cx, sub["user_id"], r.text, source="sub:" + sub["id"],
                          remind_min=sub["remind_min"])
        cx.execute("UPDATE subs SET last_sync=?, last_error=NULL WHERE id=?", (db.now(), sub["id"]))
        cx.commit()
        return n
    except Exception as e:
        cx.execute("UPDATE subs SET last_sync=?, last_error=? WHERE id=?",
                   (db.now(), str(e)[:200], sub["id"]))
        cx.commit()
        return -1


def _tick_sync():
    """Lembretes + tarefas vencidas. Roda numa thread (sqlite e rede bloqueiam)."""
    cx = db.connect()
    try:
        for uid, title, body in db.due_reminders(cx):
            toast(title, body)
            deliver(cx, uid, title, body)
        due = [t for t in tasks.due_tasks(cx) if t["id"] not in _running]
        if due and user_active():
            run = []
            for t in due:
                n = _defers.get(t["id"], 0)
                if n < MAX_DEFERS:
                    _defers[t["id"]] = n + 1
                    cx.execute("UPDATE tasks SET next_run=?, enabled=1 WHERE id=?",
                               (db.now() + DEFER_SECS, t["id"]))
                else:
                    run.append(t)
            cx.commit()
            due = run
        for t in due:
            _defers.pop(t["id"], None)
        return due
    finally:
        cx.close()


def _run_task_sync(task, chain=None):
    _running.add(task["id"])
    cx = db.connect()
    try:
        ok, title = tasks.execute(cx, task, contexto=(chain or {}).get("texto"))
        toast(("Tarefa pronta: " if ok else "Tarefa falhou: ") + task["name"], title)
        if ok:
            note = db.note_get(cx, task["user_id"], cx.execute(
                "SELECT last_note FROM tasks WHERE id=?", (task["id"],)).fetchone()[0])
            if db.settings_get(cx, task["user_id"])["ntfy_topico"]:
                deliver(cx, task["user_id"], "Tarefa pronta: " + task["name"],
                        (note or {}).get("body", "")[:900])
            # Cadeia: a proxima tarefa recebe este resultado como contexto
            nxt = task.get("then_task")
            seen = set((chain or {}).get("seen", ())) | {task["id"]}
            if nxt and nxt not in seen and len(seen) < 6:
                t2 = tasks.task_get(cx, task["user_id"], nxt)
                if t2:
                    _running.discard(task["id"])
                    _run_task_sync(t2, {"texto": (note or {}).get("body", ""), "seen": seen})
    finally:
        cx.close()
        _running.discard(task["id"])


def _subs_sync_all():
    cx = db.connect()
    try:
        for s in cx.execute("SELECT * FROM subs").fetchall():
            _sync_sub(cx, dict(s))
    finally:
        cx.close()


async def clock(app):
    loop = asyncio.get_event_loop()
    last_sub = 0
    while True:
        try:
            due = await loop.run_in_executor(None, _tick_sync)
            for t in due:
                loop.run_in_executor(None, _run_task_sync, t)
            loop.run_in_executor(None, dav.sync_due, CALDAV_SYNC_S)
            if db.now() - last_sub >= SUB_SYNC_S:
                last_sub = db.now()
                loop.run_in_executor(None, _subs_sync_all)
        except Exception as e:
            print(f"[Nous][agenda] relogio: {e}", file=sys.stderr)
        await asyncio.sleep(TICK_S)


async def _start_clock(app):
    app["clock"] = asyncio.get_event_loop().create_task(clock(app))


async def _stop_clock(app):
    app["clock"].cancel()


# ----------------------------------------------------------------- rotas
def _q(request, k, default=None):
    return request.query.get(k, default)


async def h_health(request):
    return _ok()


async def h_today(request):
    uid = _uid(request.query)
    days = max(1, min(60, int(_q(request, "days", 7))))
    cx = db.connect()
    try:
        return _ok(db.upcoming(cx, uid, days))
    finally:
        cx.close()


async def h_notes(request):
    uid = _uid(request.query)
    done = _q(request, "done")
    cx = db.connect()
    try:
        return _ok({"notes": db.notes_list(cx, uid, q=_q(request, "q"),
                                           done=None if done in (None, "") else done == "1")})
    finally:
        cx.close()


async def h_note_create(request):
    d = await _body(request)
    cx = db.connect()
    try:
        return _ok({"note": db.note_create(cx, _uid(d), d)})
    finally:
        cx.close()


async def h_note_update(request):
    d = await _body(request)
    cx = db.connect()
    try:
        return _ok({"note": db.note_update(cx, _uid(d), d.get("id"), d)})
    finally:
        cx.close()


async def h_note_delete(request):
    d = await _body(request)
    cx = db.connect()
    try:
        db.note_delete(cx, _uid(d), d.get("id"))
        return _ok()
    finally:
        cx.close()


async def h_events(request):
    uid = _uid(request.query)
    t0 = int(_q(request, "from") or db.now())
    t1 = int(_q(request, "to") or (t0 + 31 * 86400))
    cx = db.connect()
    try:
        evs = db.events_between(cx, uid, t0, min(t1, t0 + 400 * 86400))
        names = {"dav:" + r["id"]: r["name"] for r in cx.execute(
            "SELECT id, name FROM caldav_cals WHERE user_id=?", (uid,))}
        for e in evs:
            e["cal"] = names.get(e["source"])
            e.pop("raw", None)  # o .ics do servidor so' serve para a sincronizacao
        return _ok({"events": evs})
    finally:
        cx.close()


async def h_event_create(request):
    d = await _body(request)
    cx = db.connect()
    try:
        uid = _uid(d)
        if d.get("calendar_id"):  # criado direto num calendario CalDAV: sobe na proxima sincronizacao
            cal = dav.calendar_for_new(cx, uid, d["calendar_id"])
            eid = db.event_create(cx, uid, d, source="dav:" + cal["id"], dirty=2)
        else:
            eid = db.event_create(cx, uid, d)
        cx.commit()
        ev = db.event_get(cx, uid, eid)
        ev.pop("raw", None)
        return _ok({"event": ev})
    finally:
        cx.close()


async def h_event_update(request):
    d = await _body(request)
    cx = db.connect()
    try:
        ev = db.event_update(cx, _uid(d), d.get("id"), d)
        if ev:
            ev.pop("raw", None)
        return _ok({"event": ev})
    finally:
        cx.close()


async def h_event_delete(request):
    d = await _body(request)
    cx = db.connect()
    try:
        db.event_delete(cx, _uid(d), d.get("id"))
        return _ok()
    finally:
        cx.close()


async def h_ics_import(request):
    d = await _body(request)
    text = d.get("ics") or ""
    if "BEGIN:VCALENDAR" not in text:
        raise ValueError("isso nao parece um arquivo de calendario (.ics)")
    cx = db.connect()
    try:
        return _ok({"imported": db.import_ics(cx, _uid(d), text)})
    finally:
        cx.close()


async def h_ics_export(request):
    uid = _uid(request.query)
    cx = db.connect()
    try:
        return web.Response(text=db.export_ics(cx, uid), content_type="text/calendar",
                            headers={"Content-Disposition": 'attachment; filename="nous-agenda.ics"'})
    finally:
        cx.close()


async def h_subs(request):
    uid = _uid(request.query)
    cx = db.connect()
    try:
        return _ok({"subs": db.subs_list(cx, uid)})
    finally:
        cx.close()


async def h_sub_create(request):
    d = await _body(request)
    cx = db.connect()
    try:
        sid = db.sub_create(cx, _uid(d), d.get("name"), d.get("url"), d.get("remind_min"))
        sub = dict(cx.execute("SELECT * FROM subs WHERE id=?", (sid,)).fetchone())
    finally:
        cx.close()
    n = await asyncio.get_event_loop().run_in_executor(None, _sync_one, sub)
    return _ok({"id": sid, "imported": n})


def _sync_one(sub):
    cx = db.connect()
    try:
        return _sync_sub(cx, sub)
    finally:
        cx.close()


async def h_sub_delete(request):
    d = await _body(request)
    cx = db.connect()
    try:
        db.sub_delete(cx, _uid(d), d.get("id"))
        return _ok()
    finally:
        cx.close()


async def h_sub_sync(request):
    d = await _body(request)
    uid = _uid(d)
    cx = db.connect()
    try:
        subs = [dict(r) for r in cx.execute("SELECT * FROM subs WHERE user_id=?", (uid,))]
    finally:
        cx.close()
    loop = asyncio.get_event_loop()
    res = [await loop.run_in_executor(None, _sync_one, s) for s in subs]
    return _ok({"synced": len(res), "failed": sum(1 for n in res if n < 0)})


async def h_tasks(request):
    uid = _uid(request.query)
    cx = db.connect()
    try:
        return _ok({"tasks": tasks.tasks_list(cx, uid), "running": sorted(_running)})
    finally:
        cx.close()


async def h_task_create(request):
    d = await _body(request)
    cx = db.connect()
    try:
        return _ok({"task": tasks.task_save(cx, _uid(d), d)})
    finally:
        cx.close()


async def h_task_update(request):
    d = await _body(request)
    cx = db.connect()
    try:
        uid = _uid(d)
        cur = tasks.task_get(cx, uid, d.get("id"))
        if not cur:
            raise ValueError("tarefa nao encontrada")
        merged = {**cur, **d}
        return _ok({"task": tasks.task_save(cx, uid, merged, tid=cur["id"])})
    finally:
        cx.close()


async def h_task_delete(request):
    d = await _body(request)
    cx = db.connect()
    try:
        tasks.task_delete(cx, _uid(d), d.get("id"))
        return _ok()
    finally:
        cx.close()


async def h_task_run(request):
    d = await _body(request)
    cx = db.connect()
    try:
        t = tasks.task_get(cx, _uid(d), d.get("id"))
    finally:
        cx.close()
    if not t:
        raise ValueError("tarefa nao encontrada")
    if t["id"] in _running:
        return _ok({"started": False, "reason": "em andamento"})
    _running.add(t["id"])  # marca ja: um segundo clique nao dispara outra
    asyncio.get_event_loop().run_in_executor(None, _run_task_sync, t)
    return _ok({"started": True})


async def h_recent(request):
    """Quantas notas/compromissos o usuario criou nos ultimos `secs` segundos
    (o filtro Nous Guarda confere se um "agendei!" do modelo e' verdade)."""
    uid = _uid(request.query)
    since = db.now() - max(10, min(3600, int(_q(request, "secs", 180))))
    cx = db.connect()
    try:
        n = cx.execute("SELECT COUNT(*) FROM notes WHERE user_id=? AND created_at>=?", (uid, since)).fetchone()[0]
        e = cx.execute("SELECT COUNT(*) FROM events WHERE user_id=? AND created_at>=?", (uid, since)).fetchone()[0]
        return _ok({"notes": n, "events": e})
    finally:
        cx.close()


async def h_settings(request):
    uid = _uid(request.query)
    cx = db.connect()
    try:
        return _ok({"settings": db.settings_get(cx, uid)})
    finally:
        cx.close()


async def h_settings_save(request):
    d = await _body(request)
    cx = db.connect()
    try:
        return _ok({"settings": db.settings_set(cx, _uid(d), d)})
    finally:
        cx.close()


async def h_settings_test(request):
    d = await _body(request)
    uid = _uid(d)

    def run():
        cx = db.connect()
        try:
            deliver(cx, uid, "Teste de aviso", "Se voce esta lendo isto, os avisos do Nous chegam aqui.")
        finally:
            cx.close()
    await asyncio.get_event_loop().run_in_executor(None, run)
    return _ok()


async def h_notifs(request):
    uid = _uid(request.query)
    cx = db.connect()
    try:
        return _ok({"items": db.notif_pending(cx, uid)})
    finally:
        cx.close()


async def h_notifs_seen(request):
    d = await _body(request)
    cx = db.connect()
    try:
        db.notif_seen(cx, _uid(d), d.get("ids") or [])
        return _ok()
    finally:
        cx.close()


# ----------------------------------------------------------------- CalDAV
def _caldav_run(fn, *a):
    cx = db.connect()
    try:
        return fn(cx, *a)
    finally:
        cx.close()


async def _in_thread(fn, *a):
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _caldav_run, fn, *a)
    except dav.DavError as e:
        raise ValueError(str(e))


async def h_caldav(request):
    uid = _uid(request.query)
    return _ok({"accounts": await _in_thread(dav.accounts_list, uid)})


async def h_caldav_connect(request):
    d = await _body(request)
    uid = _uid(d)
    aid = await _in_thread(dav.connect, uid, d.get("server"), d.get("username"), d.get("password"), d.get("name"))
    return _ok({"id": aid, "accounts": await _in_thread(dav.accounts_list, uid)})


async def h_caldav_calendars(request):
    d = await _body(request)
    uid = _uid(d)
    await _in_thread(dav.choose_calendars, uid, d.get("account_id"), d.get("enabled") or [], d.get("default_id"))
    res = await _in_thread(dav.sync_account, d.get("account_id"), uid, True)  # ja' traz os eventos
    return _ok({"sync": res, "accounts": await _in_thread(dav.accounts_list, uid)})


async def h_caldav_sync(request):
    d = await _body(request)
    uid = _uid(d)
    ids = [d["account_id"]] if d.get("account_id") else [a["id"] for a in await _in_thread(dav.accounts_list, uid)]
    res = [await _in_thread(dav.sync_account, i, uid, bool(d.get("force"))) for i in ids]
    return _ok({"sync": res, "accounts": await _in_thread(dav.accounts_list, uid)})


async def h_caldav_disconnect(request):
    d = await _body(request)
    uid = _uid(d)
    await _in_thread(dav.disconnect, uid, d.get("account_id"))
    return _ok({"accounts": await _in_thread(dav.accounts_list, uid)})


def build_app():
    app = web.Application(middlewares=[cors_mw], client_max_size=8 * 1024 * 1024)
    app.add_routes([
        web.get("/health", h_health),
        web.get("/today", h_today),
        web.get("/notes", h_notes),
        web.post("/notes", h_note_create),
        web.post("/notes/update", h_note_update),
        web.post("/notes/delete", h_note_delete),
        web.get("/events", h_events),
        web.post("/events", h_event_create),
        web.post("/events/update", h_event_update),
        web.post("/events/delete", h_event_delete),
        web.post("/ics/import", h_ics_import),
        web.get("/ics/export", h_ics_export),
        web.get("/subs", h_subs),
        web.post("/subs", h_sub_create),
        web.post("/subs/delete", h_sub_delete),
        web.post("/subs/sync", h_sub_sync),
        web.get("/caldav", h_caldav),
        web.post("/caldav/connect", h_caldav_connect),
        web.post("/caldav/calendars", h_caldav_calendars),
        web.post("/caldav/sync", h_caldav_sync),
        web.post("/caldav/disconnect", h_caldav_disconnect),
        web.get("/tasks", h_tasks),
        web.post("/tasks", h_task_create),
        web.post("/tasks/update", h_task_update),
        web.post("/tasks/delete", h_task_delete),
        web.post("/tasks/run", h_task_run),
        web.get("/recent", h_recent),
        web.get("/settings", h_settings),
        web.post("/settings", h_settings_save),
        web.post("/settings/test", h_settings_test),
        web.get("/notifications", h_notifs),
        web.post("/notifications/seen", h_notifs_seen),
    ])
    app.on_startup.append(_start_clock)
    app.on_cleanup.append(_stop_clock)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("NOUS_AGENDA_PORT", PORT))
    web.run_app(build_app(), host="127.0.0.1", port=port, print=None)
