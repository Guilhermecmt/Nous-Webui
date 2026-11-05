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

Quando avisar (aviso):
  sempre  toda execucao vira nota e aviso
  mudou   so' se o resultado for diferente do da ultima execucao (hash)
  modelo  o modelo decide, com saida JSON {"avisar": bool, "texto": "..."}

Execucao que nao aconteceu:
  Modelo fora do ar, sem nenhuma chamada respondida: tenta de novo em 5, 15 e 30 min
  e so' depois registra a falha (last_status "tentando" e depois "erro").
  PC desligado: as perdas colapsam numa execucao so', e so' se a hora passou ha'
  menos de metade do periodo (minimo 2 min, maximo 2 h). Fora disso pula
  (last_status "pulada"): "Bom dia 8h" nao roda as 23h.
"""
import hashlib
import json
import os
import re
import sys
import threading
from datetime import datetime, timedelta

import requests

import agenda_db as db

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
EMAIL_URL = "http://127.0.0.1:8995"
# Mesmo num_ctx do chat (monitor/register_model_ctx.py): com outro valor o
# Ollama recarrega o modelo (no 0.30 o padrao chega a 256k e estoura a VRAM).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))
KINDS = ("pergunta", "pesquisa", "emails", "resumo_dia")
AVISOS = ("sempre", "mudou", "modelo")
RETRY_DELAYS = (300, 900, 1800)  # 5, 15 e 30 min
CATCHUP_MIN = 120
CATCHUP_MAX = 7200
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")
_DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Saida estruturada do Ollama: sentinela de texto ("[SILENT]") modelo 4B erra
JSON_AVISO = {"type": "object", "required": ["avisar", "texto"],
              "properties": {"avisar": {"type": "boolean"}, "texto": {"type": "string"}}}
_PEDE_JSON = ('\n\nResponda SO\' com JSON: {"avisar": true ou false, "texto": "..."}\n'
              "- avisar: true se ha' algo que o usuario precisa saber agora; false se nao ha' "
              "nada novo nem importante\n"
              "- texto: a resposta completa, em portugues do Brasil")


class ModeloForaDoAr(requests.exceptions.ConnectionError):
    """Nao deu para falar com o Ollama. So' esta falha ganha nova tentativa: o
    e-mail fora do ar tambem e' ConnectionError, mas nao se resolve esperando o modelo."""


_respostas = threading.local()  # chamadas ao modelo respondidas na execucao desta thread


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
        if cand.timestamp() > after_ts and _bate(p, cand):
            return db.to_ts(cand)
        cand += timedelta(days=1)
    return None


def _bate(p, cand):
    if p["tipo"] == "dias_uteis":
        return cand.weekday() < 5
    if p["tipo"] == "semanal":
        return cand.weekday() == p["dia"] - 1
    if p["tipo"] == "mensal":
        return cand.day == p["dia"]
    return True


def last_slot(schedule, ts):
    """Ultimo horario marcado ate' ts, inclusive (None = ainda nao houve)."""
    p = parse_schedule(schedule)
    if p["tipo"] == "uma_vez":
        return p["ts"] if p["ts"] <= ts else None
    cand = db.local_dt(ts).replace(hour=p["h"], minute=p["m"], second=0, microsecond=0)
    for _ in range(400):
        if cand.timestamp() <= ts and _bate(p, cand):
            return db.to_ts(cand)
        cand -= timedelta(days=1)
    return None


def catchup_window(schedule, slot):
    """Quanto atraso ainda vale: metade do periodo, entre 2 min e 2 h. Tarefa de
    uma vez nao tem periodo nem proxima chance: fica com a janela maior."""
    nxt = next_run(schedule, slot)
    if nxt is None:
        return CATCHUP_MAX
    return max(CATCHUP_MIN, min(CATCHUP_MAX, (nxt - slot) // 2))


def _too_late(d, t):
    """Passou da janela? Mede a partir do horario marcado mais recente (colapsa os dias
    perdidos) ou do next_run guardado, que numa nova tentativa ou num adiamento e' mais novo."""
    ref = max(d["next_run"], last_slot(d["schedule"], t) or 0)
    return t - ref > catchup_window(d["schedule"], ref)


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
    aviso = d.get("aviso") or "sempre"
    if kind not in KINDS:
        raise ValueError("tipo de tarefa invalido")
    if aviso not in AVISOS:
        raise ValueError("opção de aviso inválida")
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
              1 if d.get("enabled", True) else 0, nxt, 1 if d.get("email") else 0, then_task, aviso)
    if tid:
        # mexeu na tarefa: o next_run acima vale e as novas tentativas pendentes acabam
        cx.execute("""UPDATE tasks SET name=?, kind=?, prompt=?, schedule=?, enabled=?,
                          next_run=?, email=?, then_task=?, aviso=?, retry_count=0,
                          last_status=CASE WHEN last_status='tentando' THEN NULL ELSE last_status END,
                          updated_at=? WHERE id=? AND user_id=?""",
                   (*fields, t, tid, user_id))
    else:
        tid = db.new_id()
        cx.execute("""INSERT INTO tasks (name, kind, prompt, schedule, enabled, next_run, email,
                          then_task, aviso, id, user_id, created_at, updated_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
    """Tarefas vencidas; ja avanca o next_run (um travamento nao repete em loop).
    Devolve uma so' por tarefa, por mais horarios que tenham passado, e nenhuma se
    o ultimo deles ficou fora da janela."""
    t = db.now()
    out = []
    for r in cx.execute("SELECT * FROM tasks WHERE enabled=1 AND next_run IS NOT NULL AND next_run <= ?",
                        (t,)).fetchall():
        d = dict(r)
        nxt = next_run(d["schedule"], t)
        cx.execute("UPDATE tasks SET next_run=?, enabled=? WHERE id=?",
                   (nxt, 1 if nxt else 0, d["id"]))
        if _too_late(d, t):
            _pula(cx, d, nxt)
        else:
            out.append(d)
    cx.commit()
    return out


def _pula(cx, d, nxt):
    """Fora da janela: nao roda, mas fica registrado (nada some em silencio)."""
    hora = db.local_dt(d["next_run"]).strftime("%d/%m às %H:%M")
    if d.get("retry_count"):  # esperava nova tentativa e o PC desligou: a falha ja' era certa
        status = "erro"
        motivo = f"Não rodou em {hora}: o motor de IA não respondeu e o Nous ficou desligado."
    else:
        status = "pulada"
        motivo = f"Não rodou em {hora}: o Nous estava desligado na hora marcada."
    cx.execute("UPDATE tasks SET last_status=?, last_error=?, retry_count=0 WHERE id=?",
               (status, motivo, d["id"]))
    # Recorrente volta no proximo horario; a de uma vez e a falha merecem aviso
    if status == "erro" or nxt is None:
        db.notify(cx, d["user_id"], "tarefa", "Tarefa não rodou: " + d["name"], motivo)


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


def llm(prompt, timeout=300, fmt=None, temperature=0.4):
    payload = {"model": local_model(), "prompt": prompt, "stream": False,
               "options": {"temperature": temperature, "num_ctx": NUM_CTX}}
    if fmt is not None:
        payload["format"] = fmt
        payload["think"] = False  # modelo pequeno "pensa em voz alta" antes do JSON
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as e:
        raise ModeloForaDoAr(str(e)) from e
    r.raise_for_status()
    _respostas.n = getattr(_respostas, "n", 0) + 1
    return (r.json().get("response") or "").strip()


def _modelo_no_ar():
    """A pesquisa engole os erros do Ollama e devolveria trechos soltos da web como se
    tivesse dado certo: confere antes de comecar."""
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    except requests.exceptions.ConnectionError as e:
        raise ModeloForaDoAr(str(e)) from e


def _hoje(hora=True):
    d = datetime.now()
    return f"{_DIAS[d.weekday()]}, {d.strftime('%d/%m/%Y %H:%M' if hora else '%d/%m/%Y')}"


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
    aviso = task.get("aviso") or "sempre"
    # Quem compara resultados precisa de resposta estavel: sem sorteio e sem o minuto no pedido
    hoje = _hoje(hora=aviso == "sempre")

    def ask(texto):
        if aviso == "modelo":
            return llm(texto + _PEDE_JSON, fmt=JSON_AVISO, temperature=0)
        if aviso == "mudou":
            return llm(texto, temperature=0)
        return llm(texto)

    if contexto and kind != "pesquisa":
        prompt = (f"{prompt}\n\nUse como base o resultado da etapa anterior:\n"
                  f"\"\"\"{contexto[:6000]}\"\"\"").strip()
    if kind == "pergunta":
        return ask(f"Hoje e' {hoje}. Responda em portugues do Brasil.\n\n{prompt}")
    if kind == "pesquisa":
        _modelo_no_ar()
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
        return ask("Voce e' o assistente de e-mail do usuario. Abaixo estao os e-mails "
                   "mais recentes ja classificados. Escreva um resumo curto em portugues: "
                   "primeiro o que exige acao, depois o resto em uma linha cada. "
                   f"Nao invente e-mails.{extra}\n\n{_emails_text()}")
    if kind == "resumo_dia":
        try:
            emails = _emails_text()
        except Exception:
            emails = "(Assistente de Email nao conectado)"
        extra = f"\nPedido extra do usuario: {prompt}" if prompt else ""
        return ask(f"Hoje e' {hoje}. Escreva um 'bom dia' curto e util em portugues "
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


def parse_decisao(bruto):
    """Saida JSON do modelo -> (avisar, texto). Na duvida avisa: melhor um aviso a
    mais que perder um. So' um false de verdade, em JSON valido, fica quieto."""
    try:
        d = json.loads(bruto)
    except (TypeError, ValueError):
        d = None
    if not isinstance(d, dict):
        return True, _texto_de_json_quebrado(bruto)
    texto = str(d.get("texto") or "").strip()
    if d.get("avisar") is False:
        return False, texto
    return True, texto or _texto_de_json_quebrado(bruto)


def _texto_de_json_quebrado(bruto):
    bruto = (bruto or "").strip()
    m = re.search(r'"texto"\s*:\s*"(.*)', bruto, re.S)  # cortado no meio: salva o que veio
    if m:
        bruto = re.sub(r'"?\s*}?\s*$', "", m.group(1)).replace('\\n', "\n").strip()
    if not bruto or bruto.startswith(("{", "[")):
        return "A tarefa rodou, mas a resposta do modelo veio sem texto."
    return bruto


def _pesquisa_importa(task, relatorio):
    """A pesquisa nao aceita saida JSON: o relatorio vai para uma segunda chamada,
    so' para decidir. Se ela falhar, avisa."""
    try:
        bruto = llm(f"Pedido do usuario: {task['prompt']}\n\nResultado da pesquisa:\n"
                    f"\"\"\"{relatorio[:6000]}\"\"\"{_PEDE_JSON}", fmt=JSON_AVISO, temperature=0)
    except Exception:
        return True
    return parse_decisao(bruto)[0]


def result_hash(text):
    """Hash do que importa: o link do relatorio muda a cada pesquisa, e espaco ou
    maiuscula nao sao novidade."""
    t = re.sub(r"Relatorio visual: \S+", "", text or "")
    t = " ".join(t.split()).casefold()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def _decide(task, bruto):
    """Resultado cru -> (texto, avisar)."""
    aviso = task.get("aviso") or "sempre"
    if aviso == "modelo":
        if task["kind"] == "pesquisa":
            return bruto, _pesquisa_importa(task, bruto)
        avisar, texto = parse_decisao(bruto)
        return texto, avisar
    if aviso == "mudou":
        return bruto, result_hash(bruto) != task.get("last_hash")
    return bruto, True


def _plan_retry(cx, task, t):
    """Proxima tentativa -> (quando, numero), ou None se acabaram ou nao faz sentido."""
    r = cx.execute("SELECT enabled, retry_count FROM tasks WHERE id=?", (task["id"],)).fetchone()
    if r is None:
        return None  # apagada enquanto rodava
    uma_vez = parse_schedule(task["schedule"])["tipo"] == "uma_vez"
    if not r["enabled"] and not uma_vez:  # a de uma vez ja' nasce desligada em due_tasks
        return None  # pausada enquanto rodava
    n = r["retry_count"] or 0
    if n >= len(RETRY_DELAYS):
        return None
    at = t + RETRY_DELAYS[n]
    natural = next_run(task["schedule"], t)
    if natural is not None and natural <= at:
        return None  # o proprio horario da tarefa chega antes
    return at, n + 1


def execute(cx, task, contexto=None, agendada=False):
    """Roda a tarefa e registra o resultado. Devolve (status, titulo):
      ok            virou nota e aviso
      sem_novidade  rodou e nao ha' o que avisar (nada de nota, aviso ou e-mail)
      tentando      modelo fora do ar, nova tentativa marcada (sem aviso ainda)
      erro          falhou de vez: aviso e status no painel
    agendada = veio do relogio. "Rodar agora" e tarefa em cadeia nao tentam de novo:
    quem clicou ve a falha na hora, e a cadeia perderia o contexto da etapa anterior."""
    stamp = db.local_dt(db.now()).strftime("%d/%m %H:%M")
    title = f"{task['name']} - {stamp}"
    _respostas.n = 0
    erro, h = None, None
    try:
        text, avisar = _decide(task, run_task(cx, task, contexto))
        h = result_hash(text)
        status = "ok" if avisar else "sem_novidade"
    except Exception as e:
        erro = _friendly(e)
        status = "erro"
        fora_do_ar = isinstance(e, ModeloForaDoAr) and _respostas.n == 0
        if fora_do_ar and agendada and not contexto:
            plano = _plan_retry(cx, task, db.now())
            if plano:
                cx.execute("""UPDATE tasks SET last_run=?, last_status='tentando', last_error=?,
                                  retry_count=?, next_run=?, enabled=1 WHERE id=?""",
                           (db.now(), erro, plano[1], plano[0], task["id"]))
                cx.commit()
                return "tentando", title
        text = "A tarefa nao pode ser concluida: " + erro
        if fora_do_ar and agendada and task.get("retry_count"):
            text += f" Tentei de novo {task['retry_count']} vez(es)."
    # Falha nao vira nota (poluiria as notas): fica o aviso e o status da tarefa
    note_id = None
    if status == "ok":
        note_id = db.note_create(cx, task["user_id"],
                                 {"title": title, "body": text, "tags": "tarefa"})["id"]
    cx.execute("""UPDATE tasks SET last_run=?, last_status=?, last_note=COALESCE(?, last_note),
                      last_hash=COALESCE(?, last_hash), last_error=? WHERE id=?""",
               (db.now(), status, note_id, h, erro, task["id"]))
    # Rodar agora que falha nao mexe nas tentativas em andamento. Qualquer outro desfecho
    # encerra a escada; se "Rodar agora" deu certo, a tentativa marcada nao serve mais.
    if agendada or status != "erro":
        cx.execute("UPDATE tasks SET retry_count=0 WHERE id=?", (task["id"],))
        if not agendada and task.get("retry_count"):
            nxt = next_run(task["schedule"], db.now())
            cx.execute("UPDATE tasks SET next_run=?, enabled=? WHERE id=?",
                       (nxt, 1 if nxt else 0, task["id"]))
    cx.commit()
    if status == "sem_novidade":
        return status, title
    db.notify(cx, task["user_id"], "tarefa", title, text[:300], note_id)
    if status == "ok" and task["email"]:
        try:
            send_email_to_self("[Nous] " + title, text)
        except Exception:
            pass
    return status, title
