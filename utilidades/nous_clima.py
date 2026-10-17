# -*- coding: utf-8 -*-
"""
title: Nous Clima
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Previsao do tempo no chat: "vai chover amanha em Curitiba?", "como esta o
  tempo?". Quando a pergunta e' sobre clima, busca a previsao no Open-Meteo
  (gratuito, sem cadastro e sem chave) e entrega os numeros ao modelo, que
  responde em portugues. Sem cidade na pergunta, usa a cidade padrao (valve).
"""
import re
import unicodedata
from typing import Optional

from pydantic import BaseModel, Field

try:
    import requests
except Exception:
    requests = None

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FC_URL = "https://api.open-meteo.com/v1/forecast"

# So' frases que perguntam do tempo de fato: "frio", "calor" ou "tempo" sozinhos
# aparecem em muita conversa que nao e' sobre clima ("quanto tempo leva").
_WHEN_WHERE = r"(?:em|no|na|hoje|amanh[aã]|agora|para|pra|nesta|nessa|neste|nesse|essa semana|esta semana)"
_TRIGGER = re.compile(
    r"\b(previs[aã]o do tempo|previs[aã]o (?:de chuva|para|pra|em|no|na)|clima " + _WHEN_WHERE + r"|tempo " + _WHEN_WHERE + r"|"
    r"como (?:est[aá]|vai estar|vai ficar|fica|t[aá]) o (?:tempo|clima)|"
    r"vai (?:chover|garoar|nevar|fazer (?:frio|calor|sol))|"
    r"(?:est[aá]|t[aá]) (?:chovendo|fazendo (?:frio|calor)) " + _WHEN_WHERE + r"|"
    r"chance de chuva|temperatura " + _WHEN_WHERE + r"|guarda.chuva)\b", re.I)
_NOT_WEATHER = re.compile(r"\b(quanto tempo|mesmo tempo|faz tempo|tempo livre|tempo de "
                          r"(?:espera|entrega|resposta|estudo|tela)|clima organizacional)\b", re.I)

# Palavras que encerram o nome da cidade ("em Curitiba amanha de manha")
_STOP_AFTER = re.compile(
    r"\b(hoje|amanh[aã]|agora|nesta|nessa|esta|essa|este|esse|semana|fim de semana|"
    r"de manh[aã]|[aà] tarde|[aà] noite|depois|durante|no domingo|na segunda|"
    r"s[aá]bado|domingo|segunda|ter[cç]a|quarta|quinta|sexta)\b.*$", re.I)

# Codigos WMO do Open-Meteo
_WMO = {
    0: "ceu limpo", 1: "quase limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "neblina", 48: "neblina com geada", 51: "garoa fraca", 53: "garoa",
    55: "garoa forte", 56: "garoa congelante", 57: "garoa congelante forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte", 66: "chuva congelante",
    67: "chuva congelante forte", 71: "neve fraca", 73: "neve", 75: "neve forte",
    77: "granizo fino", 80: "pancadas de chuva fracas", 81: "pancadas de chuva",
    82: "pancadas de chuva fortes", 85: "pancadas de neve", 86: "pancadas de neve fortes",
    95: "trovoadas", 96: "trovoadas com granizo", 99: "trovoadas fortes com granizo",
}
_DIAS = ["segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo"]


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c
                        if isinstance(p, dict) and p.get("type") == "text")
    return ""


_WEATHER_WORDS = re.compile(r"\b(tempo|clima|previs[aã]o|chuva|chover|sol|frio|calor|"
                            r"temperatura|guarda.chuva)\b", re.I)


def _city_candidates(text):
    """Palpites do nome da cidade, na ordem da frase. Cada preposicao gera um
    candidato (lookahead): "no Rio de Janeiro" da "Rio de Janeiro" e "Janeiro";
    quem decide e' o geocodificador, tentando na ordem."""
    t = re.sub(r"[?!.,;:]+", " ", text)
    out = []
    for h in re.finditer(r"\b(?:em|no|na|para|pra|de)\s+(?=(\S.*)$)", t, re.I):
        cand = _STOP_AFTER.sub("", h.group(1)).strip()
        if not cand or _WEATHER_WORDS.search(cand) or re.search(r"\d", cand):
            continue
        if len(cand.split()) <= 4 and cand not in out:
            out.append(cand)
    return out


# Apelidos que o geocodificador nao conhece
_APELIDOS = {"floripa": "Florianopolis", "sampa": "Sao Paulo", "sp": "Sao Paulo",
             "bh": "Belo Horizonte", "poa": "Porto Alegre", "rio": "Rio de Janeiro",
             "rj": "Rio de Janeiro", "bsb": "Brasilia", "cwb": "Curitiba"}


def _strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga a previsao do tempo no chat.")
        CIDADE_PADRAO: str = Field(default="", description="Cidade usada quando a pergunta nao diz qual (ex.: Sao Paulo).")
        PAIS: str = Field(default="BR", description="Pais preferido na busca da cidade (codigo de 2 letras; vazio = qualquer).")
        DIAS: int = Field(default=4, description="Quantos dias de previsao entregar ao modelo.")

    def __init__(self):
        self.valves = self.Valves()
        self._geo = {}  # nome -> (lat, lon, rotulo)

    def _geocode(self, name):
        key = _strip_accents(name.lower())
        if key in self._geo:
            return self._geo[key]
        name = _APELIDOS.get(key, name)
        params = {"name": name, "count": 5, "language": "pt", "format": "json"}
        r = requests.get(GEO_URL, params=params, timeout=10)
        res = (r.json() or {}).get("results") or []
        if self.valves.PAIS:
            pref = [x for x in res if x.get("country_code") == self.valves.PAIS.upper()]
            res = pref or res
        if not res:
            self._geo[key] = None
            return None
        x = res[0]
        label = ", ".join(v for v in (x.get("name"), x.get("admin1"), x.get("country")) if v)
        self._geo[key] = (x["latitude"], x["longitude"], label)
        return self._geo[key]

    def _forecast(self, lat, lon):
        params = {
            "latitude": lat, "longitude": lon, "timezone": "auto",
            "forecast_days": max(1, min(7, self.valves.DIAS)),
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "precipitation,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max,precipitation_sum",
        }
        r = requests.get(FC_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def _summary(self, label, fc):
        import datetime
        cur = fc.get("current") or {}
        lines = [f"Local: {label}",
                 f"Agora ({cur.get('time', '')}): {cur.get('temperature_2m')} C "
                 f"(sensacao {cur.get('apparent_temperature')} C), "
                 f"{_WMO.get(cur.get('weather_code'), 'condicao desconhecida')}, "
                 f"umidade {cur.get('relative_humidity_2m')}%, "
                 f"vento {cur.get('wind_speed_10m')} km/h"]
        d = fc.get("daily") or {}
        for i, day in enumerate(d.get("time") or []):
            try:
                wd = _DIAS[datetime.date.fromisoformat(day).weekday()]
            except Exception:
                wd = ""
            rel = "hoje" if i == 0 else "amanha" if i == 1 else wd
            lines.append(
                f"{day} ({rel}): {_WMO.get(d['weather_code'][i], '?')}, "
                f"min {d['temperature_2m_min'][i]} C / max {d['temperature_2m_max'][i]} C, "
                f"chance de chuva {d['precipitation_probability_max'][i]}%, "
                f"chuva prevista {d['precipitation_sum'][i]} mm")
        return "\n".join(lines)

    async def inlet(self, body: dict, __user__: Optional[dict] = None,
                    __event_emitter__=None) -> dict:
        if not self.valves.ENABLED or requests is None:
            return body
        messages = body.get("messages", [])
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        q = _text(last) if last else ""
        if not q or not _TRIGGER.search(q) or _NOT_WEATHER.search(q):
            return body

        cands = _city_candidates(q)
        padrao = self.valves.CIDADE_PADRAO.strip()
        if padrao and padrao not in cands:
            cands.append(padrao)
        if not cands:
            text = ("[Nous Clima] O usuario perguntou sobre o tempo mas nao disse a "
                    "cidade. Pergunte qual cidade (e diga que ele pode definir uma "
                    "cidade padrao em Funcoes > Nous Clima).")
        else:
            try:
                geo = None
                for city in cands[:4]:
                    geo = self._geocode(city)
                    if geo:
                        break
                if geo is None:
                    text = (f"[Nous Clima] Nao encontrei a cidade '{cands[0]}'. Peca ao "
                            "usuario o nome da cidade (e o estado, se for comum).")
                else:
                    lat, lon, label = geo
                    if __event_emitter__:
                        try:
                            await __event_emitter__({"type": "status", "data": {
                                "description": f"Consultando a previsao para {label}...", "done": False}})
                        except Exception:
                            pass
                    text = ("[Nous Clima] Previsao do tempo atual (fonte: Open-Meteo). "
                            "Responda a pergunta do usuario com estes dados, de forma "
                            "curta e pratica (ex.: se leva guarda-chuva):\n"
                            + self._summary(label, self._forecast(lat, lon)))
            except Exception:
                text = ("[Nous Clima] O servico de previsao nao respondeu (sem "
                        "internet?). Avise o usuario; nao invente a previsao.")

        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + text) if base else text
        else:
            messages.insert(0, {"role": "system", "content": text})
        body["messages"] = messages
        if __event_emitter__:
            try:
                await __event_emitter__({"type": "status", "data": {
                    "description": "Previsao do tempo consultada.", "done": True}})
            except Exception:
                pass
        return body
