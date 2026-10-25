"""
title: Nous Email
author: Nous
version: 0.1.0
required_open_webui_version: 0.5.0
description: >
  E-mail pelo chat, sempre com aprovacao. "Manda um e-mail pra Maria cobrando
  a fatura": o filtro acha a Maria nos contatos, o modelo do chat escreve (com
  as habilidades e memorias do Nous) e o texto vira um RASCUNHO em Recursos >
  Email > Rascunhos. Nada e' enviado sem o clique do usuario.
  "O que chegou de importante?" traz a caixa de entrada ja' classificada.
"""
import os
import re
import json
import time
import asyncio
from typing import Optional

from pydantic import BaseModel, Field

try:
    import requests
except Exception:
    requests = None

# Mesmo num_ctx do chat (monitor/register_model_ctx.py).
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")

_SEND = re.compile(
    r"\b(?:mand[ae]r?|envi[ae]r?|escrev[ae]r?|redij[ae]|prepar[ae]r?|fa[cz]a?) (?:um |uma |o |a )?"
    r"(?:e-?mail|email|mensagem por e-?mail)\b|\be-?mail (?:pr[ao]|para)\b", re.I)
_INBOX = re.compile(
    r"\b(meus e-?mails|minha caixa(?: de entrada)?|caixa de entrada|chegou (?:algum |alguma )?(?:e-?mail|coisa)|"
    r"e-?mails? (?:novos|importantes|de hoje|n[aã]o lidos)|tenho (?:algum )?e-?mail)\b", re.I)
_SUBJ = re.compile(r"^\s*\**\s*assunto\s*\**\s*:\s*\**\s*(.+?)\**\s*$", re.I | re.M)

_WHO_SCHEMA = {"type": "object", "required": ["destinatario"],
               "properties": {"destinatario": {"type": "string"}}}
_WHO_PROMPT = """Para QUEM o usuario quer mandar o e-mail? Responda so' com o nome (ou o
endereco de e-mail, se ele escreveu um), sem palavras como "para" ou "o/a".
Se nao disse, responda "".

Exemplos:
"manda um email pra Maria cobrando a fatura" -> {{"destinatario": "Maria"}}
"escreve um e-mail para o joao.silva@empresa.com.br sobre a reuniao" -> {{"destinatario": "joao.silva@empresa.com.br"}}
"envia email ao Carlos da contabilidade" -> {{"destinatario": "Carlos"}}

Mensagem: \"\"\"{msg}\"\"\""""


def _text(m):
    c = m.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _split_email(text):
    """(assunto, corpo) da resposta do modelo, que foi instruido a comecar com 'Assunto:'."""
    m = _SUBJ.search(text or "")
    if not m:
        return None, None
    subject = m.group(1).strip().strip("*").strip()
    body = text[m.end():].strip()
    body = re.sub(r"^\s*(?:\**corpo\**\s*:\s*)", "", body, flags=re.I)
    # tira comentarios do modelo depois do e-mail (ex.: "Quer que eu ajuste algo?")
    body = re.split(r"\n\s*(?:---+|\*\*\*+)\s*\n", body)[0].strip()
    return subject[:200], body


class Filter:
    class Valves(BaseModel):
        ENABLED: bool = Field(default=True, description="Liga/desliga o e-mail pelo chat.")
        EMAIL_URL: str = Field(default="http://127.0.0.1:8995", description="Servico de e-mail do Nous.")
        OLLAMA_URL: str = Field(default="", description="URL do Ollama. Vazio = OLLAMA_BASE_URL ou 127.0.0.1:11434.")

    def __init__(self):
        self.valves = self.Valves()
        self._pending = {}  # user_id -> (quando, contato) entre o inlet e o outlet
        self._options = {}  # user_id -> (quando, [(rotulo, comando)]): botoes de escolha
        self._saved = {}    # hash da resposta -> draft id (regenerar nao duplica)

    def _ollama(self):
        return (self.valves.OLLAMA_URL or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")

    def _local_names(self):
        """Nomes dos modelos que rodam nesta maquina (sem os de nuvem e sem os de embeddings)."""
        try:
            tags = requests.get(f"{self._ollama()}/api/tags", timeout=5).json().get("models", [])
        except Exception:
            return None
        return [m.get("name", "") for m in tags
                if "/" not in m.get("name", "") and "cloud" not in m.get("name", "").lower()
                and not (m.get("remote_host") or m.get("remote_model"))
                and not any(p in m.get("name", "").lower() for p in _EMBED)]

    def _model(self, chat_model):
        names = self._local_names()
        if names is None:
            return None
        if chat_model in names or (chat_model + ":latest") in names:
            return chat_model
        return names[0] if names else None

    def _chat_is_local(self, chat_model):
        """O modelo do chat roda nesta maquina? E-mail so' vai para modelo local."""
        names = self._local_names()
        return bool(names) and (chat_model in names or (chat_model + ":latest") in names)

    def _api(self, method, path, **kw):
        r = requests.request(method, self.valves.EMAIL_URL + path, timeout=kw.pop("timeout", 20), **kw)
        data = r.json()
        if r.status_code != 200:
            raise RuntimeError(data.get("error") or "erro no servico de e-mail")
        return data

    def _who(self, msg, chat_model):
        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", msg)
        if m:
            return m.group(0)
        model = self._model(chat_model)
        if not model:
            return ""
        r = requests.post(f"{self._ollama()}/api/generate",
                          json={"model": model, "prompt": _WHO_PROMPT.format(msg=msg[:1000]), "stream": False,
                                "think": False, "format": _WHO_SCHEMA,
                                "options": {"temperature": 0, "num_ctx": NUM_CTX}}, timeout=60)
        return (json.loads(r.json().get("response") or "{}").get("destinatario") or "").strip()

    def _plan_send(self, uid, msg, chat_model):
        """Texto de sistema para o pedido de envio (e guarda o destinatario p/ o outlet)."""
        st = self._api("GET", "/status")
        if not st.get("connected"):
            return ("[Nous Email] O usuario quer mandar um e-mail, mas nenhuma conta de e-mail esta "
                    "conectada. Explique que ele pode conectar em Recursos > Assistente de Email. "
                    "Nao escreva o e-mail ainda.")
        who = self._who(msg, chat_model)
        if not who:
            return "[Nous Email] O usuario quer mandar um e-mail mas nao disse para quem. Pergunte."
        matches = self._api("GET", "/contacts/resolve", params={"q": who})["matches"]
        if not matches:
            return (f"[Nous Email] \"{who}\" nao esta nos contatos. Diga isso ao usuario (\"nos seus contatos\") e peca o endereco de "
                    "e-mail dessa pessoa. Nao escreva o e-mail ainda.")
        exact = [c for c in matches if (c.get("name") or "").lower().split()[:1] == who.lower().split()[:1]]
        if len(matches) > 1 and len({c["email"] for c in matches}) > 1 and len(exact) != 1:
            opcoes = "; ".join(f"{c.get('name') or '?'} <{c['email']}>" for c in matches[:5])
            # botoes na resposta: cada um repete o pedido ja' com o endereco certo
            self._options[uid] = (time.time(), [
                (c.get("name") or c["email"], f"manda o e-mail para {c['email']}") for c in matches[:5]])
            return (f"[Nous Email] Ha' mais de um contato para \"{who}\": {opcoes}. Pergunte qual deles. "
                    "Nao escreva o e-mail ainda.")
        c = exact[0] if len(exact) == 1 else matches[0]
        self._pending[uid] = (time.time(), c)
        nome = c.get("name") or c["email"]
        return (f"[Nous Email] Escreva o e-mail que o usuario pediu para {nome} <{c['email']}>. "
                "FORMATO OBRIGATORIO: a primeira linha e' 'Assunto: ...', depois uma linha em branco "
                "e o corpo do e-mail, pronto para enviar. Nao diga que enviou: o Nous vai guardar "
                "como RASCUNHO e o usuario envia depois de revisar.")

    def _inbox_text(self, chat_model=""):
        st = self._api("GET", "/status")
        if not st.get("connected"):
            return ("[Nous Email] Nenhuma conta de e-mail conectada. Explique que ele pode conectar "
                    "em Recursos > Assistente de Email.")
        if not self._chat_is_local(chat_model):
            # privacidade: o conteudo dos e-mails nao vai para um modelo de nuvem
            return ("[Nous Email] O modelo desta conversa roda fora do computador (nuvem), e por privacidade o "
                    "Nous nao mostra e-mails a ele. Diga isso ao usuario e peca para trocar para um modelo "
                    "local e perguntar de novo. Nao invente e-mails.")
        msgs = self._api("GET", "/inbox", timeout=300)
        lines = [f"- [{m.get('category') or '?'}]{' (nao lido)' if m.get('unread') else ''} "
                 f"{m.get('from', '')}: {m.get('subject', '')} - {m.get('summary') or ''}" for m in msgs]
        return ("[Nous Email] Caixa de entrada do usuario agora (20 mais recentes, ja' classificados "
                "pelo Nous):\n" + "\n".join(lines) + "\nResponda o que ele perguntou com base nisso, "
                "destacando primeiro o que pede acao. Nao invente e-mails.")

    async def inlet(self, body: dict, __user__: Optional[dict] = None, __event_emitter__=None) -> dict:
        if not self.valves.ENABLED or requests is None:
            return body
        uid = (__user__ or {}).get("id")
        messages = body.get("messages", [])
        last = next((m for m in reversed(messages) if m.get("role") == "user"), None)
        msg = _text(last) if last else ""
        if not uid or not msg:
            return body
        want_send, want_inbox = bool(_SEND.search(msg)), bool(_INBOX.search(msg))
        if not (want_send or want_inbox):
            return body

        async def status(desc, done):
            if __event_emitter__:
                try:
                    await __event_emitter__({"type": "status", "data": {"description": desc, "done": done}})
                except Exception:
                    pass

        await status("Consultando o e-mail...", False)
        try:
            if want_send:
                text = await asyncio.to_thread(self._plan_send, uid, msg, body.get("model") or "")
            else:
                text = await asyncio.to_thread(self._inbox_text, body.get("model") or "")
        except requests.exceptions.ConnectionError:
            text = ("[Nous Email] O servico de e-mail do Nous nao esta no ar. Avise o usuario e sugira "
                    "abrir o Nous de novo pelo atalho. Nada foi enviado.")
        except Exception as e:
            text = f"[Nous Email] Nao consegui acessar o e-mail ({e}). Avise o usuario."
        await status("E-mail consultado.", True)

        if messages and messages[0].get("role") == "system":
            base = (messages[0].get("content") or "").rstrip()
            messages[0]["content"] = (base + "\n\n" + text) if base else text
        else:
            messages.insert(0, {"role": "system", "content": text})
        body["messages"] = messages
        return body

    async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        uid = (__user__ or {}).get("id")
        opts = self._options.pop(uid, None) if uid else None
        if opts and time.time() - opts[0] < 900:
            asst = next((m for m in reversed(body.get("messages", [])) if m.get("role") == "assistant"), None)
            if asst and isinstance(asst.get("content"), str):
                asst["content"] += "\n\n" + " ".join(
                    f"⟦opcao:{rot.replace('|', '/').replace('⟧', '')}|{cmd}⟧" for rot, cmd in opts[1])
            return body
        pend = self._pending.pop(uid, None) if uid else None
        if not pend or time.time() - pend[0] > 900:
            return body
        contato = pend[1]
        messages = body.get("messages", [])
        asst = next((m for m in reversed(messages) if m.get("role") == "assistant"), None)
        if not asst:
            return body
        subject, text = _split_email(_text(asst))
        if not subject or not text:
            return body
        key = str(hash((uid, subject, text)))
        try:
            if key not in self._saved:
                d = await asyncio.to_thread(self._api, "POST", "/drafts", json={
                    "to": contato["email"], "to_name": contato.get("name", ""), "subject": subject,
                    "body": text, "origem": "chat"})
                self._saved[key] = d["draft"]["id"]
            note = ("\n\n---\n✉ **Rascunho salvo, nada foi enviado.** Para revisar e enviar para "
                    f"{contato.get('name') or contato['email']} <{contato['email']}>: "
                    "Recursos > Assistente de Email > Rascunhos.")
        except Exception:
            note = "\n\n---\n⚠ Nao consegui salvar o rascunho (o servico de e-mail esta fora do ar)."
        if isinstance(asst.get("content"), str):
            asst["content"] += note
        body["messages"] = messages
        return body
