# -*- coding: utf-8 -*-
"""
Tarefas agendadas do Nous: "todo dia as 8h, resuma meus e-mails",
"toda segunda, pesquise novidades sobre X". Rodam no servico da agenda (8996),
mesmo com o navegador fechado; o resultado vira uma nota (etiqueta "tarefa"),
um aviso no Nous e, se pedido, um e-mail para a propria conta.

Tipos (kind):
  pergunta  o modelo local responde ao texto da tarefa (sem internet)
  pesquisa  Pesquisa Profunda na web (precisa do SearXNG, igual ao chat)
  emails    resumo da caixa de entrada (precisa do Assistente de Email)
  resumo_dia  compromissos e lembretes de hoje + e-mails importantes

Agenda (schedule), sempre em horario local:
  "diario 08:00" | "dias_uteis 08:00" | "semanal 1 08:00" (1=segunda..7=domingo)
  "mensal 15 08:00" | "uma_vez 2026-10-20T08:00"
"""
import os
import re
import sys
from datetime import datetime, timedelta

import requests

import agenda_db as db

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
EMAIL_URL = "http://127.0.0.1:8995"
# Mesmo num_ctx do chat (monitor/register_model_ctx.py): com outro valor o
# Ollama recarrega o modelo (no 0.30 o padrao chega a 256k e estoura a VRAM).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))
KINDS = ("pergunta", "pesquisa", "emails", "resumo_dia")
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")
_DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------ agenda

def parse_schedule(s):
    s = (s or "").strip().lower()
    m = re.fullmatch(r"(diario|dias_uteis)\s+(\d{1,2}):(\d{2})", s)
    if m:
        return {"tipo": m.group(1), "h": int(m.group(2)), "m": int(m.group(3))}
    m = re.fullmatch(r"semanal\s+([1-7])\s+(\d{1,2}):(\d{2})", s)
    if m:
        return {"tipo": "semanal", "dia": int(m.group(1)), "h": int(m.group(2)), "m": int(m.group(3))}
    m = re.fullmatch(r"mensal\s+(\d{1,2})\s+(\d{1,2}):(\d{2})", s)
    if m and 1 <= int(m.group(1)) <= 31:
        return {"tipo": "mensal", "dia": int(m.group(1)), "h": int(m.group(2)), "m": int(m.group(3))}
    m = re.fullmatch(r"uma_vez\s+(\S+)", s)
    if m:
        return {"tipo": "uma_vez", "ts": db.parse_when(m.group(1))}
    raise ValueError("agenda invalida: " + s)


def next_run(schedule, after_ts):
    """Proxima execucao estritamente depois de after_ts (None = nao repete)."""
    p = parse_schedule(schedule)
    if p["tipo"] == "uma_vez":
        return p["ts"] if p["ts"] > after_ts else None
    base = db.local_dt(after_ts)
    cand = base.replace(hour=p["h"], minute=p["m"], second=0, microsecond=0)
    for _ in range(400):
        ok = cand.timestamp() > after_ts
        if p["tipo"] == "dias_uteis":
            ok = ok and cand.weekday() < 5
        elif p["tipo"] == "semanal":
            ok = ok and cand.weekday() == p["dia"] - 1
        elif p["tipo"] == "mensal":
            ok = ok and cand.day == p["dia"]
        if ok:
            return db.to_ts(cand)
        cand += timedelta(days=1)
    return None


def describe(schedule):
    try:
        p = parse_schedule(schedule)
    except Exception:
        return schedule
    hora = f"{p.get('h', 0):02d}:{p.get('m', 0):02d}"
    if p["tipo"] == "diario":
        return f"todo dia as {hora}"
    if p["tipo"] == "dias_uteis":
        return f"de segunda a sexta as {hora}"
    if p["tipo"] == "semanal":
        return f"toda {_DIAS[p['dia'] - 1]} as {hora}"
    if p["tipo"] == "mensal":
        return f"todo dia {p['dia']} do mes as {hora}"
    return "uma vez, em " + db.local_dt(p["ts"]).strftime("%d/%m/%Y %H:%M")


# ------------------------------------------------------------------ CRUD

def task_save(cx, user_id, d, tid=None):
    name = (d.get("name") or "").strip()
    kind = d.get("kind") or "pergunta"
    schedule = (d.get("schedule") or "").strip()
    if kind not in KINDS:
        raise ValueError("tipo de tarefa invalido")
    if not name:
        raise ValueError("de um nome para a tarefa")
    if kind in ("pergunta", "pesquisa") and not (d.get("prompt") or "").strip():
        raise ValueError("escreva o que o Nous deve fazer")
    nxt = next_run(schedule, db.now())  # valida a agenda
    if nxt is None:
        raise ValueError("esse horario ja passou")
    then_task = (d.get("then_task") or "").strip() or None
    if then_task and then_task == tid:
        raise ValueError("uma tarefa nao pode chamar ela mesma em seguida")
    if then_task and not cx.execute(
            "SELECT 1 FROM tasks WHERE id=? AND user_id=?", (then_task, user_id)).fetchone():
        raise ValueError("a tarefa seguinte nao existe")
    t = db.now()
    fields = (name, kind, (d.get("prompt") or "").strip(), schedule,
              1 if d.get("enabled", True) else 0, nxt, 1 if d.get("email") else 0, then_task)
    if tid:
        cx.execute("""UPDATE tasks SET name=?, kind=?, prompt=?, schedule=?, enabled=?,
                          next_run=?, email=?, then_task=?, updated_at=? WHERE id=? AND user_id=?""",
                   (*fields, t, tid, user_id))
    else:
        tid = db.new_id()
        cx.execute("""INSERT INTO tasks (name, kind, prompt, schedule, enabled, next_run, email,
                          then_task, id, user_id, created_at, updated_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (*fields, tid, user_id, t, t))
    cx.commit()
    return task_get(cx, user_id, tid)


def task_get(cx, user_id, tid):
    r = cx.execute("SELECT * FROM tasks WHERE id=? AND user_id=?", (tid, user_id)).fetchone()
    if r is None:
        return None
    d = dict(r)
    d["quando"] = describe(d["schedule"])
    return d


def tasks_list(cx, user_id):
    out = []
    for r in cx.execute("SELECT * FROM tasks WHERE user_id=? ORDER BY created_at", (user_id,)):
        d = dict(r)
        d["quando"] = describe(d["schedule"])
        out.append(d)
    return out


def task_delete(cx, user_id, tid):
    cx.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (tid, user_id))
    cx.commit()


def due_tasks(cx):
    """Tarefas vencidas; ja avanca o next_run (um travamento nao repete em loop)."""
    t = db.now()
    out = []
    for r in cx.execute("SELECT * FROM tasks WHERE enabled=1 AND next_run IS NOT NULL AND next_run <= ?",
                        (t,)).fetchall():
        d = dict(r)
        nxt = next_run(d["schedule"], t)
        cx.execute("UPDATE tasks SET next_run=?, enabled=? WHERE id=?",
                   (nxt, 1 if nxt else 0, d["id"]))
        out.append(d)
    cx.commit()
    return out


# ------------------------------------------------------------------ execucao

def local_model():
    """Primeiro modelo de chat LOCAL (mesma regra do e-mail: nunca nuvem)."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        for m in r.json().get("models", []):
            name = m.get("name", "")
            nuvem = "/" in name or "cloud" in name.lower() or m.get("remote_host") or m.get("remote_model")
            if not nuvem and not any(p in name.lower() for p in _EMBED):
                return name
    except Exception:
        pass
    return os.environ.get("NOUS_MODEL", "gemma4:12b")


def llm(prompt, timeout=300):
    r = requests.post(f"{OLLAMA_URL}/api/generate",
                      json={"model": local_model(), "prompt": prompt, "stream": False,
                            "options": {"temperature": 0.4, "num_ctx": NUM_CTX}}, timeout=timeout)
    r.raise_for_status()
    return (r.json().get("response") or "").strip()


def _hoje():
    d = datetime.now()
    return f"{_DIAS[d.weekday()]}, {d.strftime('%d/%m/%Y %H:%M')}"


def _emails_text():
    r = requests.get(f"{EMAIL_URL}/inbox", timeout=300)
    if r.status_code != 200:
        raise RuntimeError("o Assistente de Email nao esta conectado")
    msgs = r.json()
    lines = [f"- [{m.get('category', '?')}] {m.get('from', '')}: {m.get('subject', '')} "
             f"- {m.get('summary') or m.get('snippet', '')[:160]}" for m in msgs]
    return "\n".join(lines) or "(caixa de entrada vazia)"


def _agenda_text(cx, user_id):
    up = db.upcoming(cx, user_id, days=1)
    lines = []
    for e in up["events"]:
        quando = "dia inteiro" if e["all_day"] else db.local_dt(e["occ_start"]).strftime("%H:%M")
        lines.append(f"- {quando} {e['title']}" + (f" ({e['location']})" if e["location"] else ""))
    for n in up["notes"]:
        ts = n["due_at"] or n["remind_at"]
        atraso = " (ATRASADO)" if ts < up["now"] else ""
        lines.append(f"- lembrete: {n['title'] or n['body'][:80]}{atraso}")
    return "\n".join(lines) or "(nada marcado para hoje)"


def run_task(cx, task, contexto=None):
    """Executa e devolve o texto do resultado (levanta excecao em falha).
    contexto = resultado da tarefa anterior quando esta roda em cadeia (a
    pesquisa ignora: o texto da tarefa ja' e' a pergunta de busca)."""
    kind, prompt = task["kind"], task["prompt"]
    if contexto and kind != "pesquisa":
        prompt = (f"{prompt}\n\nUse como base o resultado da etapa anterior:\n"
                  f"\"\"\"{contexto[:6000]}\"\"\"").strip()
    if kind == "pergunta":
        return llm(f"Hoje e' {_hoje()}. Responda em portugues do Brasil.\n\n{prompt}")
    if kind == "pesquisa":
        sp = os.path.join(_REPO, "search")
        if sp not in sys.path:
            sys.path.insert(0, sp)
        from nous_search.deep_research import deep_research
        model = local_model()
        res = deep_research(prompt, model=model)
        text = res.get("report") or "(a pesquisa nao trouxe resultado)"
        if res.get("sources"):
            try:
                from nous_search.report import save
                rid = save(prompt, text, res["sources"], model)
                text += ("\n\nRelatorio visual: http://127.0.0.1:8990/research/view?id=" + rid)
            except Exception:
                pass
        return text
    if kind == "emails":
        extra = f"\nFoco pedido pelo usuario: {prompt}" if prompt else ""
        return llm("Voce e' o assistente de e-mail do usuario. Abaixo estao os e-mails "
                   "mais recentes ja classificados. Escreva um resumo curto em portugues: "
                   "primeiro o que exige acao, depois o resto em uma linha cada. "
                   f"Nao invente e-mails.{extra}\n\n{_emails_text()}")
    if kind == "resumo_dia":
        try:
            emails = _emails_text()
        except Exception:
            emails = "(Assistente de Email nao conectado)"
        extra = f"\nPedido extra do usuario: {prompt}" if prompt else ""
        return llm(f"Hoje e' {_hoje()}. Escreva um 'bom dia' curto e util em portugues "
                   "com a agenda do dia e os e-mails que pedem acao. Nao invente nada "
                   f"alem do que esta abaixo.{extra}\n\nAGENDA DE HOJE:\n"
                   f"{_agenda_text(cx, task['user_id'])}\n\nE-MAILS:\n{emails}")
    raise ValueError("tipo desconhecido")


def send_email_to_self(subject, text):
    st = requests.get(f"{EMAIL_URL}/status", timeout=5).json()
    if not st.get("connected"):
        return False
    # confirmado: quem pediu "mandar por e-mail" foi o usuario, ao criar a tarefa; e so' para ele mesmo
    r = requests.post(f"{EMAIL_URL}/send", json={"to": st["user"], "subject": subject,
                                                 "body": text, "confirmado": True}, timeout=60)
    return r.status_code == 200


def _friendly(e):
    m = str(e).lower()
    if "404" in m and "api/generate" in m:
        return "nenhum modelo de conversa instalado. Baixe um em Recursos > Baixar modelos."
    if isinstance(e, requests.exceptions.ConnectionError):
        return "o motor de IA (Ollama) nao esta no ar."
    if isinstance(e, requests.exceptions.Timeout):
        return "o modelo demorou demais para responder."
    return str(e)


def execute(cx, task, contexto=None):
    """Roda a tarefa e registra o resultado (nota + aviso). Devolve (ok, titulo)."""
    stamp = db.local_dt(db.now()).strftime("%d/%m %H:%M")
    title = f"{task['name']} - {stamp}"
    try:
        text = run_task(cx, task, contexto)
        status = "ok"
    except Exception as e:
        text = "A tarefa nao pode ser concluida: " + _friendly(e)
        status = "erro"
    # Falha nao vira nota (poluiria as notas): fica o aviso e o status da tarefa
    note_id = None
    if status == "ok":
        note_id = db.note_create(cx, task["user_id"],
                                 {"title": title, "body": text, "tags": "tarefa"})["id"]
    cx.execute("UPDATE tasks SET last_run=?, last_status=?, last_note=COALESCE(?, last_note) WHERE id=?",
               (db.now(), status, note_id, task["id"]))
    cx.commit()
    db.notify(cx, task["user_id"], "tarefa", title, text[:300], note_id)
    if status == "ok" and task["email"]:
        try:
            send_email_to_self("[Nous] " + title, text)
        except Exception:
            pass
    return status == "ok", title
