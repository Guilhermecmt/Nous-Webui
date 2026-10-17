# -*- coding: utf-8 -*-
"""
title: Nous Agenda
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Agenda pelo chat: "me lembre de pagar a luz sexta as 9h", "anota: ideia
  para o projeto...", "marca dentista dia 20 as 14h", "o que eu tenho amanha?".
  Quando a mensagem parece um pedido de agenda, o modelo LOCAL extrai os dados
  (titulo, data, repeticao) e o filtro grava no servico da agenda (porta 8996).
  O modelo do chat so' confirma. Tudo fica na maquina.
"""
import re
import os
import json
import time
import asyncio
import hashlib
import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Mesmo num_ctx do chat (monitor/register_model_ctx.py): com outro valor o
# Ollama recarrega o modelo (no 0.30 o padrao chega a 256k e estoura a VRAM).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))

try:
    import requests
except Exception:
    requests = None

_CREATE = re.compile(
    r"\b(me lembr[ae]|lembr[ae]-me|me avis[ae]|lembrete|anot[ae]|anotar|"
    r"(?:cri[ae]|salv[ae]|fa[cz]a?) (?:uma |um )?(?:nota|lembrete|evento|compromisso)|"
    r"agend[ae]|agendar|marc[ae] (?:um|uma|na|no|pra|para|dia)|marcar|"
    # "marca dentista dia 20" sim; "a marca do carro" nao: exige data/hora perto
    r"marc[ae]\b.{0,60}?(?:\bdia \d+|amanh[aã]|\bhoje\b|segunda|ter[cç]a|quarta|quinta|sexta|"
    r"s[aá]bado|domingo|\b[aà]s \d+|\b\d{1,2}h|\b\d{1,2}/\d{1,2})|"
    r"(?:coloc|p[oõ]e|bot)[ae]? (?:isso )?na (?:minha )?agenda|"
    r"adicion[ae] (?:na|ao|no) (?:minha |meu )?(?:agenda|calend[aá]rio))\b", re.I)
_QUERY = re.compile(
    r"\b((?:o que|quais?|que|qual) (?:eu )?(?:tenho|tem|h[aá]|vou ter)\b(?: \w+){0,4}? "
    r"(?:marcad|agendad|na agenda|hoje|amanh[aã]|semana|dias|m[eê]s|compromisso|lembrete|reuni)|"
    r"minha agenda|meus compromissos|meus lembretes|minhas notas|estou livre|t[oô] livre|"
    r"tenho algo (?:hoje|amanh[aã]|marcado)|"
    r"(?:quais?|qual)\b[^?]{0,25}\b(?:compromisso|reuni[aã]o|reuni[oõ]es|lembrete|consulta|evento)s?\b"
    r"[^?]{0,25}\b(?:tenho|tem|h[aá])\b)", re.I)

_OPEN_PANEL = re.compile(r"^\s*(?:abr[ae]|abrir|mostr[ae]|mostrar|me mostra|ver|quero ver)\s+(?:a |o |minha |meu )?"
                         r"(?:agenda|calend[aá]rio|notas|lembretes|tarefas)\s*[.!?]*\s*$", re.I)
_EMAIL_REQ = re.compile(r"\b(?:mand[ae]r?|envi[ae]r?|escrev[ae]r?|responde[r]?)\b.{0,25}\b(?:e-?mail|email)\b", re.I)
_UNDO = re.compile(r"^\s*(?:↩\s*)?(desfaz(?:er|a)?|cancela(?:r)?(?: isso| esse| essa| o [uú]ltimo| a [uú]ltima)?|"
                   r"apaga (?:isso|esse|essa|o que voc[eê] (?:criou|marcou|anotou|salvou)))\s*[.!]?\s*$", re.I)

_DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")

# O modelo so' CLASSIFICA e da o titulo. Datas sao calculadas por _parse_when
# (modelo pequeno erra conta de calendario: "sexta que vem" virava hoje).
_PROMPT = """Classifique a mensagem do usuario (agenda pessoal, em portugues).

Responda SO' com JSON: {{"acao": "...", "titulo": "...", "detalhes": "...", "repetir": "..."}}
- acao: "lembrete" (quer ser AVISADO numa hora) | "evento" (compromisso marcado: consulta,
  reuniao, aniversario, viagem, aula) | "nota" (guardar uma ideia/informacao) |
  "consulta" (quer SABER o que tem na agenda) | "nenhuma" (nao e' pedido de agenda)
- titulo: curto, SEM data, SEM hora e SEM verbos como "me lembre", "marca", "anota"
- detalhes: o resto do conteudo util (local, observacoes) ou ""
- repetir: "nenhum" | "diario" | "dias_uteis" | "semanal" | "mensal" | "anual"

Exemplos:
"me lembre de tomar o remedio todo dia as 8h" -> {{"acao":"lembrete","titulo":"Tomar o remedio","detalhes":"","repetir":"diario"}}
"marca dentista dia 28 as 14h30 na clinica Sorriso" -> {{"acao":"evento","titulo":"Dentista","detalhes":"Clinica Sorriso","repetir":"nenhum"}}
"anota: ideia de presente para a Ana, um livro" -> {{"acao":"nota","titulo":"Ideia de presente para a Ana","detalhes":"um livro","repetir":"nenhum"}}
"o que eu tenho amanha?" -> {{"acao":"consulta","titulo":"","detalhes":"","repetir":"nenhum"}}
"qual a marca de carro mais vendida?" -> {{"acao":"nenhuma","titulo":"","detalhes":"","repetir":"nenhum"}}

Mensagem: \"\"\"{msg}\"\"\""""

_MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4, "maio": 5,
          "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
          "novembro": 11, "dezembro": 12}
_WD = {"segunda": 0, "terca": 1, "terça": 1, "quarta": 2, "quinta": 3, "sexta": 4,
       "sabado": 5, "sábado": 5, "domingo": 6}
_EVENT_WORDS = re.compile(r"\b(marc|agend|consulta|reuni|compromisso|dentista|m[eé]dic|"
                          r"entrevista|anivers|aula|viagem|voo|exame|culto|missa|jantar|almo[cç]o)", re.I)
_NOTE_WORDS = re.compile(r"\b(anot|nota\b|guard[ae]|salv[ae] (?:isso|a ideia))", re.I)
_CMD_PREFIX = re.compile(r"^\s*(me lembr[ae] (?:de|que)?|lembr[ae]-me (?:de)?|lembrete(?: de| para| pra)?|"
                         r"marc[ae]r?|agend[ae]r?|anot[ae]r?:?|cri[ae] (?:uma |um )?(?:nota|lembrete|evento))\s*",
                         re.I)


def _parse_when(msg, now):
    """Datas em portugues -> {"start": datetime|None, "has_time": bool, "end": datetime|None}.
    Determinístico: hoje/amanha/depois de amanha, dia da semana (+ "que vem"),
    "dia 28", "28 de outubro", "28/10[/2026]", "daqui a N min/horas/dias/semanas",
    horas "9h", "9h30", "14:30", "as 9 da noite", "meio-dia", periodos "de manha/a tarde/a noite"."""
    t = " " + (msg or "").lower() + " "
    t = t.replace("ã", "a").replace("á", "a").replace("à", "a").replace("â", "a").replace("ç", "c") \
         .replace("é", "e").replace("ê", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    day = None
    hour = minute = None

    m = re.search(r"\bdaqui a (\d+|uma?|dois|duas|tres) (minutos?|horas?|dias?|semanas?)\b", t) or \
        re.search(r"\bem (\d+) (minutos?|horas?)\b", t)
    if m:
        n = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3}.get(m.group(1)) or int(m.group(1))
        unit = m.group(2)
        if unit.startswith("minuto"):
            s = now + datetime.timedelta(minutes=n)
            return {"start": s.replace(second=0, microsecond=0), "has_time": True, "end": None}
        if unit.startswith("hora"):
            s = now + datetime.timedelta(hours=n)
            return {"start": s.replace(second=0, microsecond=0), "has_time": True, "end": None}
        day = (now + datetime.timedelta(days=n * (7 if unit.startswith("semana") else 1))).date()

    if day is None:
        m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            y = int(m.group(3)) if m.group(3) else now.year
            y = y + 2000 if y < 100 else y
            try:
                day = datetime.date(y, mo, d)
                if not m.group(3) and day < now.date():
                    day = datetime.date(y + 1, mo, d)
            except ValueError:
                day = None
    if day is None:
        m = re.search(r"\b(?:dia )?(\d{1,2}) de (" + "|".join(k for k in _MESES if "ç" not in k) + r")\b", t)
        if m:
            try:
                day = datetime.date(now.year, _MESES[m.group(2)], int(m.group(1)))
                if day < now.date():
                    day = datetime.date(now.year + 1, day.month, day.day)
            except ValueError:
                day = None
    if day is None:
        m = re.search(r"\bdia (\d{1,2})\b", t)
        if m:
            d = int(m.group(1))
            y, mo = now.year, now.month
            for _ in range(3):
                try:
                    cand = datetime.date(y, mo, d)
                    if cand >= now.date():
                        day = cand
                        break
                except ValueError:
                    pass
                mo, y = (1, y + 1) if mo == 12 else (mo + 1, y)
    if day is None:
        if re.search(r"\bdepois de amanha\b", t):
            day = (now + datetime.timedelta(days=2)).date()
        elif re.search(r"\bamanha\b", t):
            day = (now + datetime.timedelta(days=1)).date()
        elif re.search(r"\bhoje\b|\bhj\b", t):
            day = now.date()
    if day is None:
        m = re.search(r"\b(proxim[ao] )?(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:-feira)?( que vem| da semana que vem)?\b", t)
        if m:
            delta = (_WD[m.group(2)] - now.weekday()) % 7
            # proxima ocorrencia; "sexta" numa sexta e' hoje, salvo "que vem"/"proxima"
            if delta == 0 and (m.group(1) or m.group(3)):
                delta = 7
            day = (now + datetime.timedelta(days=delta)).date()
    if day is None and re.search(r"\bsemana que vem\b|\bproxima semana\b", t):
        day = (now + datetime.timedelta(days=7)).date()

    # ---- hora
    # o horario que aparece PRIMEIRO na frase (fora de "ate ..."), seja "14h30", "9h" ou "as 9"
    cands = []
    for pat in (r"\b(\d{1,2})(?::|h)(\d{2})\b", r"\b(\d{1,2}) ?h(?:oras?)?\b", r"\bas (\d{1,2})\b(?! de )(?!/)"):
        for mm in re.finditer(pat, t):
            if not re.search(r"\bate (?:as )?$", t[max(0, mm.start() - 7):mm.start()]):
                cands.append(mm)
    m = min(cands, key=lambda x: x.start()) if cands else None
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else 0
        tail = t[m.end():m.end() + 16]
        if hour < 12 and re.match(r"\s*(da tarde|da noite|pm)", tail):
            hour += 12
        if hour > 23 or minute > 59:
            hour = minute = None
    elif re.search(r"\bmeio[- ]dia\b", t):
        hour, minute = 12, 0
    elif re.search(r"\bmeia[- ]noite\b", t):
        hour, minute = 0, 0
    elif re.search(r"\bde manha\b|\bpela manha\b", t):
        hour, minute = 9, 0
    elif re.search(r"\b(a|de|pela) tarde\b", t):
        hour, minute = 15, 0
    elif re.search(r"\b(a|de|pela) noite\b", t):
        hour, minute = 20, 0

    if day is None and hour is None:
        return {"start": None, "has_time": False, "end": None}
    if day is None:  # so' a hora: hoje, ou amanha se ja passou
        cand = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if cand <= now:
            cand += datetime.timedelta(days=1)
        return {"start": cand, "has_time": True, "end": None}
    start = datetime.datetime.combine(day, datetime.time(hour or 0, minute or 0))
    end = None
    m = re.search(r"\bate (?:as )?(\d{1,2})(?::|h)?(\d{2})?\b", t)
    if hour is not None and m:
        try:
            end = datetime.datetime.combine(day, datetime.time(int(m.group(1)), int(m.group(2) or 0)))
            end = end if end > start else None
        except ValueError:
            end = None
    return {"start": start, "has_time": hour is not None, "end": end}


_DATE_BITS = re.compile(
    r"\b(?:(?:proxim[ao]|pr[oó]xim[ao]) )?(?:segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)(?:-feira)?"
    r"(?: que vem)?\b|\b(?:hoje|amanh[aã]|depois de amanh[aã]|semana que vem|que vem)\b|"
    r"\bdia \d{1,2}(?: de \w+)?\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|"
    r"\b(?:[aà]s |at[eé] (?:[aà]s )?)\d{1,2}(?:(?::|h)\d{2}|h)?\b(?: da (?:manh[aã]|tarde|noite))?|"
    r"\b\d{1,2}(?::|h)\d{2}\b|\b\d{1,2}h\b|"
    r"\b(?:de|pela|[aà]) (?:manh[aã]|tarde|noite)\b|\bmeio[- ]dia\b|\bdaqui a \S+ \w+\b", re.I)


def _clean_details(detalhes):
    """Tira datas/horas dos detalhes (ja estao no horario do lembrete)."""
    rest = _DATE_BITS.sub(" ", detalhes or "")
    rest = re.sub(r"\s+", " ", rest).strip(" ,.;:-")
    return rest if len(re.sub(r"\W", "", rest)) >= 3 else ""


def _clean_title(titulo, msg):
    t = _CMD_PREFIX.sub("", (titulo or "").strip()).strip(" .:-")
    if not t:
        t = _CMD_PREFIX.sub("", msg).strip(" .:-")[:80]
    return (t[:1].upper() + t[1:])[:200] if t else "Lembrete"


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _fmt(ts, all_day=False):
    d = datetime.datetime.fromtimestamp(ts)
    s = f"{_DIAS[d.weekday()]} {d.strftime('%d/%m/%Y')}"
    return s if all_day else s + d.strftime(" as %H:%M")


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga a agenda pelo chat.")
        AGENDA_URL: str = Field(default="http://127.0.0.1:8996", description="Servico da agenda do Nous.")
        OLLAMA_URL: str = Field(default="http://127.0.0.1:11434", description="Ollama local (extrai os dados do pedido).")
        AVISO_PADRAO_MIN: int = Field(default=30, description="Minutos de antecedencia do aviso de compromissos.")

    def __init__(self):
        self.valves = self.Valves()
        self._done = {}   # hash(usuario+mensagem) -> (quando, texto). Regenerar nao duplica.
        self._last = {}   # usuario -> (quando, "notes"|"events", id, titulo): o que "desfazer" apaga
        self._marks = {}  # usuario -> quando: a proxima resposta ganha o botao "Desfazer"

    # ---------------------------------------------------------- modelo local
    def _model(self, chat_model):
        try:
            tags = requests.get(f"{self.valves.OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
        except Exception:
            return None
        names = [m.get("name", "") for m in tags]
        if chat_model in names or (chat_model + ":latest") in names:
            return chat_model  # o modelo do chat ja esta na VRAM: resposta rapida
        for n in names:
            if "/" not in n and not any(p in n.lower() for p in _EMBED):
                return n
        return None

    def _extract(self, msg, chat_model):
        model = self._model(chat_model)
        if not model:
            return None
        prompt = _PROMPT.format(msg=msg[:2000])
        r = requests.post(f"{self.valves.OLLAMA_URL}/api/generate",
                          json={"model": model, "prompt": prompt, "stream": False,
                                "format": "json", "think": False,
                                "options": {"temperature": 0, "num_ctx": NUM_CTX}}, timeout=120)
        r.raise_for_status()
        return json.loads(r.json().get("response") or "{}")

    # ---------------------------------------------------------- agenda
    def _api(self, method, path, **kw):
        r = requests.request(method, self.valves.AGENDA_URL + path, timeout=15, **kw)
        data = r.json()
        if r.status_code != 200:
            raise RuntimeError(data.get("error") or "erro na agenda")
        return data

    def _apply(self, d, uid, msg="", now=None):
        """Executa a acao e devolve o texto para o modelo confirmar (ou None)."""
        now = now or datetime.datetime.now()
        hoje = f"Hoje e' {_DIAS[now.weekday()]}, {now:%d/%m/%Y}, {now:%H:%M}. "
        acao = (d.get("acao") or "nenhuma").lower()
        detalhes = _clean_details(d.get("detalhes"))
        repetir = d.get("repetir") if d.get("repetir") in (
            "diario", "dias_uteis", "semanal", "mensal", "anual") else None
        w = _parse_when(msg, now)
        start = w["start"]
        # O modelo pequeno confunde os tipos: as palavras do usuario decidem
        if acao == "consulta" or (_QUERY.search(msg) and not _CREATE.search(msg)):
            acao = "consulta"
        elif acao in ("lembrete", "nota", "evento"):
            if _NOTE_WORDS.search(msg) and not start:
                acao = "nota"
            elif start and _EVENT_WORDS.search(msg) and not re.search(r"\b(lembr|avis)", msg, re.I):
                acao = "evento"
            elif acao == "nota" and start and re.search(r"\b(lembr|avis)", msg, re.I):
                acao = "lembrete"
        titulo = _clean_title(d.get("titulo"), msg) if acao != "consulta" else ""
        if start and start <= now and acao in ("lembrete", "evento") and not repetir:
            return (f"[Nous Agenda] {hoje}O horario pedido ({_fmt(start.timestamp())}) ja passou. "
                    "Nada foi salvo: pergunte ao usuario para quando ele quer.")

        if acao == "consulta":
            t = msg.lower()
            dias = (1 if re.search(r"\bhoje\b", t) else 2 if re.search(r"\bamanh", t)
                    else 31 if re.search(r"\bm[eê]s\b", t) else 7)
            up = self._api("GET", "/today", params={"user_id": uid, "days": dias})
            lines = []
            for e in up["events"]:
                lines.append(f"- {_fmt(e['occ_start'], e['all_day'])}: {e['title']}"
                             + (f" ({e['location']})" if e["location"] else ""))
            for n in up["notes"]:
                ts = n["due_at"] or n["remind_at"]
                atraso = " [ATRASADO]" if ts < up["now"] else ""
                lines.append(f"- lembrete {_fmt(ts)}: {n['title'] or n['body'][:80]}{atraso}")
            corpo = "\n".join(lines) or "(nada marcado nesse periodo)"
            return (f"[Nous Agenda] {hoje}Agenda do usuario nos proximos {dias} dia(s), lida "
                    f"agora do Nous:\n{corpo}\nResponda a pergunta com base nisso, de forma "
                    "organizada. As datas acima estao certas; nao comente o ano. Nao invente compromissos.")

        if acao == "nota" or (acao == "lembrete" and not start):
            n = self._api("POST", "/notes", json={"user_id": uid, "title": titulo,
                                                  "body": detalhes})["note"]
            self._last[uid] = (time.time(), "notes", n["id"], n["title"] or "nota")
            return (f"[Nous Agenda] {hoje}Nota salva: \"{n['title'] or n['body'][:60]}\"."
                    + (" O usuario pediu um lembrete mas nao disse quando; pergunte o dia e a "
                       "hora do aviso." if acao == "lembrete" else "")
                    + " Confirme em uma frase curta.")

        if acao == "lembrete":
            if not w["has_time"]:
                start = start.replace(hour=9, minute=0)
            n = self._api("POST", "/notes", json={"user_id": uid, "title": titulo, "body": detalhes,
                                                  "remind_at": int(start.timestamp()),
                                                  "due_at": int(start.timestamp()),
                                                  "repeat": repetir})["note"]
            self._last[uid] = (time.time(), "notes", n["id"], n["title"])
            rep = f", repetindo ({repetir.replace('_', ' ')})" if repetir else ""
            return (f"[Nous Agenda] {hoje}Lembrete criado: \"{n['title']}\" para "
                    f"{_fmt(n['remind_at'])}{rep}. O Nous vai avisar no computador nessa hora. "
                    "Confirme ao usuario em uma frase curta, repetindo exatamente essa data.")

        if acao == "evento" and start:
            dia_inteiro = not w["has_time"]
            aviso = None if dia_inteiro else self.valves.AVISO_PADRAO_MIN
            body = {"user_id": uid, "title": titulo, "description": detalhes,
                    "location": "", "start_at": int(start.timestamp()),
                    "all_day": dia_inteiro, "remind_min": aviso}
            if w["end"]:
                body["end_at"] = int(w["end"].timestamp())
            if repetir:
                body["repeat"] = repetir
            e = self._api("POST", "/events", json=body)["event"]
            self._last[uid] = (time.time(), "events", e["id"], e["title"])
            return (f"[Nous Agenda] {hoje}Compromisso salvo: \"{e['title']}\" em "
                    f"{_fmt(e['start_at'], e['all_day'])}"
                    + (f" ({detalhes})" if detalhes else "")
                    + (f", com aviso {aviso} min antes" if aviso else "")
                    + ". Confirme ao usuario em uma frase curta, repetindo exatamente essa data.")

        if acao == "evento":
            return (f"[Nous Agenda] {hoje}O usuario quer marcar um compromisso mas nao disse "
                    "quando. Pergunte o dia e a hora. Nada foi salvo ainda.")
        return None

    # ---------------------------------------------------------- ciclo
    async def inlet(self, body: dict, __user__: Optional[dict] = None,
                    __event_emitter__=None) -> dict:
        if not self.valves.ENABLED or requests is None:
            return body
        uid = (__user__ or {}).get("id")
        messages = body.get("messages", [])
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        msg = _text(last) if last else ""
        if uid and msg and _UNDO.search(msg):
            text = await asyncio.to_thread(self._undo, uid)
            if text:
                return _inject(body, messages, text)
        # "reuniao com a equipe segunda as 10h" nao diz "marca", mas e' agenda: palavra
        # de compromisso + data, fora de pergunta ("tenho consulta amanha, o que levo?")
        implicit = (_EVENT_WORDS.search(msg or "") and "?" not in (msg or "")
                    and _parse_when(msg, datetime.datetime.now())["start"] is not None)
        if not uid or not msg or not (_CREATE.search(msg) or _QUERY.search(msg) or implicit):
            return body
        if _OPEN_PANEL.search(msg):
            return body  # "abre minha agenda": quem resolve e' o Nous Comandos (abre o painel)
        if _EMAIL_REQ.search(msg):
            return body  # "manda um e-mail pra Maria marcando a reuniao de sexta" e' e-mail, nao agenda

        async def status(desc, done):
            if __event_emitter__:
                try:
                    await __event_emitter__({"type": "status", "data": {"description": desc, "done": done}})
                except Exception:
                    pass

        key = hashlib.sha1(f"{uid}\n{msg}".encode("utf-8")).hexdigest()
        t = time.time()
        self._done = {k: v for k, v in self._done.items() if t - v[0] < 86400}
        if key in self._done and not _QUERY.search(msg):
            text = self._done[key][1]  # regenerou a resposta: ja foi gravado
        else:
            await status("Verificando a agenda...", False)
            try:
                data = await asyncio.to_thread(self._extract, msg, body.get("model") or "")
                text = await asyncio.to_thread(self._apply, data or {}, uid, msg) if data else None
                if text:
                    self._done[key] = (t, text)  # so' sucesso: falha tenta de novo
            except requests.exceptions.ConnectionError:
                text = ("[Nous Agenda] O servico da agenda nao esta no ar, entao NADA foi "
                        "salvo. Avise o usuario e sugira abrir o Nous de novo pelo atalho.")
            except Exception as e:
                text = (f"[Nous Agenda] Nao consegui salvar na agenda ({e}). Avise o "
                        "usuario; nao diga que foi salvo.")
        await status("Agenda atualizada." if text else "Nada para a agenda.", True)
        if not text:
            return body
        if self._last.get(uid, (0,))[0] >= t:  # criou algo agora: a resposta ganha "Desfazer"
            self._marks[uid] = time.time()
        return _inject(body, messages, text)

    def _undo(self, uid):
        last = self._last.get(uid)
        if not last or time.time() - last[0] > 1800:
            return None  # nada recente: "desfazer" segue para o modelo normalmente
        _t, kind, item_id, title = last
        try:
            self._api("POST", f"/{kind}/delete", json={"user_id": uid, "id": item_id})
        except Exception as e:
            return f"[Nous Agenda] Nao consegui desfazer ({e}). Avise o usuario."
        self._last.pop(uid, None)
        tipo = "o compromisso" if kind == "events" else "a nota/lembrete"
        return (f"[Nous Agenda] Desfeito: {tipo} \"{title}\" foi apagado da agenda agora. "
                "Confirme ao usuario em uma frase curta.")

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """Poe o botao "Desfazer" (marcador que o loader do Nous vira botao)."""
        uid = (__user__ or {}).get("id")
        if not uid or time.time() - self._marks.pop(uid, 0) > 900:
            return body
        msgs = body.get("messages", [])
        asst = next((m for m in reversed(msgs) if m.get("role") == "assistant"), None)
        if asst and isinstance(asst.get("content"), str) and "⟦opcao:↩ Desfazer" not in asst["content"]:
            asst["content"] += "\n\n⟦opcao:↩ Desfazer|desfazer⟧"
        return body


def _inject(body, messages, text):
    if messages and messages[0].get("role") == "system":
        base = (messages[0].get("content") or "").rstrip()
        messages[0]["content"] = (base + "\n\n" + text) if base else text
    else:
        messages.insert(0, {"role": "system", "content": text})
    body["messages"] = messages
    return body
