"""
title: Nous Guarda
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  Modelos pequenos as vezes DIZEM que fizeram algo sem ter feito ("agendei
  para sexta", "enviei o e-mail"). Depois de cada resposta, esta guarda confere
  na Agenda e no E-mail do Nous se algo foi mesmo criado; se nao foi, acrescenta
  um aviso claro e ensina como pedir. Nao chama IA: so' confere os servicos.
"""
import re
import time
import asyncio
from typing import Optional

from pydantic import BaseModel, Field

try:
    import requests
except Exception:
    requests = None

# So' AFIRMACOES DE ACAO ("agendei", "lembrete criado"). "Voce tem uma reuniao
# marcada segunda" e' consulta a agenda, nao acao, e nao pode disparar o aviso.
_AGENDA_CLAIM = re.compile(
    r"\b(agendei|marquei|anotei|adicionei (?:na|[aà]) (?:sua )?agenda|salvei (?:na|em sua|na sua) agenda|"
    r"criei (?:o |um |uma |seu |sua )?(?:lembrete|evento|compromisso|nota)|"
    r"lembrete (?:criado|salvo|agendado|configurado|definido)|"
    r"vou te (?:lembrar|avisar)|te lembrarei|voc[eê] ser[aá] (?:lembrad[oa]|avisad[oa]))\b"
    r"|^\s*(?:pronto[,!]?\s*)?(?:agendado|anotado|marcado)\b", re.I | re.M)
_EMAIL_CLAIM = re.compile(r"\b(enviei (?:o |um |seu )?e-?mail|e-?mail (?:foi )?enviado|mandei (?:o |um )?e-?mail)\b", re.I)


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=50, description="Roda depois dos outros filtros.")
        ENABLED: bool = Field(default=True, description="Liga/desliga a conferencia de acoes.")
        AGENDA_URL: str = Field(default="http://127.0.0.1:8996", description="Servico da agenda.")
        EMAIL_URL: str = Field(default="http://127.0.0.1:8995", description="Servico de e-mail.")
        JANELA_S: int = Field(default=240, description="Quanto tempo atras uma criacao conta como 'desta resposta'.")

    def __init__(self):
        self.valves = self.Valves()

    def _agenda_ok(self, uid):
        try:
            d = requests.get(self.valves.AGENDA_URL + "/recent",
                             params={"user_id": uid, "secs": self.valves.JANELA_S}, timeout=5).json()
            return (d.get("notes", 0) + d.get("events", 0)) > 0
        except Exception:
            return True  # servico fora: nao acusa o modelo sem prova

    def _email_ok(self):
        try:
            ds = requests.get(self.valves.EMAIL_URL + "/drafts", timeout=5).json().get("drafts", [])
            t = time.time() - self.valves.JANELA_S
            return any(d.get("created", 0) >= t or (d.get("sent_at") or 0) >= t for d in ds)
        except Exception:
            return True

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.ENABLED or requests is None:
            return body
        uid = (__user__ or {}).get("id")
        asst = next((m for m in reversed(body.get("messages", [])) if m.get("role") == "assistant"), None)
        text = asst.get("content") if asst else None
        if not uid or not isinstance(text, str) or "⚠ Atenção" in text:
            return body
        aviso = None
        if _AGENDA_CLAIM.search(text) and not await asyncio.to_thread(self._agenda_ok, uid):
            aviso = ("⚠ Atenção: nada foi salvo na sua agenda. Para o Nous guardar de verdade, peça assim: "
                     "\"me lembre de pagar a luz sexta às 9h\" ou \"marca dentista dia 28 às 14h\".")
        elif _EMAIL_CLAIM.search(text) and not await asyncio.to_thread(self._email_ok):
            aviso = ("⚠ Atenção: nenhum e-mail foi enviado nem salvo. Peça \"manda um e-mail pra Maria ...\": "
                     "o Nous cria um rascunho para você revisar e enviar.")
        if aviso:
            asst["content"] = text + "\n\n---\n" + aviso
        return body
