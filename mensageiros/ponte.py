# -*- coding: utf-8 -*-
"""
Nous - Falar com o Nous pelo Telegram e pelo WhatsApp: o que os dois canais dividem.

A mensagem chega do celular, entra no Open WebUI pela API (/api/chat/completions)
e a resposta volta pelo mesmo canal. Por entrar no Open WebUI, ela passa pelos
mesmos filtros da tela: memoria, agenda, habilidades, e-mail. O modelo continua
rodando no computador; o que sai da maquina e' so' o texto e o audio da conversa,
que passam pelo servidor do Telegram ou pelo WhatsApp. Por isso vem desligado.

Regras (as duas primeiras vem do Hermes Agent, gateway/pairing.py e
tools/send_message_tool.py):
  - quem nao pareou nao recebe resposta nenhuma: um bot publico nao pode virar
    porta de entrada para o seu computador;
  - o modelo nunca manda mensagem sozinho: ele so' responde a quem falou com ele.

Pastas em NousData\\mensageiros:
  config.json              canais ligados. So' o monitor escreve.
  estado.json              o que o processo esta' fazendo. So' ele escreve.
  codigo_<canal>.json      codigo de uso unico em vigor (so' o hash).
  donos\\<canal>_<id>.json  quem pode falar: um arquivo por pessoa.
  conversas\\<id>.json      ultimas mensagens de cada pessoa.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid

import aiohttp

CODIGO_VALIDADE = 300     # segundos, como o QR do celular
MAX_TENTATIVAS = 5        # codigos errados antes de queimar o codigo em vigor
TAM_CODIGO = 8
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # sem 0/O/1/I/L
MAX_HISTORICO = 20        # mensagens enviadas ao modelo a cada pergunta
TEMPO_RESPOSTA = 600      # modelo local na CPU pode levar minutos
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")

AJUDA = ("Pode escrever ou mandar áudio, como no Nous do computador.\n\n"
         "/novo começa uma conversa nova\n"
         "/ajuda mostra esta mensagem\n\n"
         "O computador precisa estar ligado para eu responder.")
SEM_RESPOSTA = "Não consegui responder agora. Veja se o Nous está aberto no computador e tente de novo."
SEM_MODELO = "Nenhum modelo está instalado no Nous. Abra a Loja de modelos no computador."
SO_TEXTO = "Por enquanto eu entendo texto e áudio."
AUDIO_FALHOU = "Não consegui entender o áudio. Tente de novo ou escreva."


def pasta(data_dir):
    return os.path.join(str(data_dir), "mensageiros")


def ler_json(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def escrever_json(caminho, dados):
    """Grava de uma vez (temporario + troca): ninguem le' pela metade."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = "%s.%d.tmp" % (caminho, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, caminho)


def apagar(caminho):
    try:
        os.remove(caminho)
    except OSError:
        pass


def config(data_dir):
    return ler_json(os.path.join(pasta(data_dir), "config.json")) or {}


def salvar_config(data_dir, c):
    escrever_json(os.path.join(pasta(data_dir), "config.json"), c)


# ------------------------------------------------------------------ pareamento
def _hash(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _id_de(canal, remetente):
    return _hash("%s:%s" % (canal, remetente))[:24]


def _arq_codigo(data_dir, canal):
    return os.path.join(pasta(data_dir), "codigo_%s.json" % canal)


def novo_codigo(data_dir, canal, user_id):
    """Codigo de uso unico para `user_id` do Nous. Um por vez, 5 minutos."""
    cod = "".join(secrets.choice(ALFABETO) for _ in range(TAM_CODIGO))
    expira = time.time() + CODIGO_VALIDADE
    escrever_json(_arq_codigo(data_dir, canal), {"hash": _hash(cod), "expira": expira, "user_id": user_id, "tentativas": 0})
    return cod, expira


def codigo_vigente(data_dir, canal):
    d = ler_json(_arq_codigo(data_dir, canal))
    return d["expira"] if d and d.get("expira", 0) > time.time() else None


def usar_codigo(data_dir, canal, tentativa):
    """user_id do Nous se o codigo vale; None se nao. Vale uma vez so'. Depois de
    MAX_TENTATIVAS erros o codigo morre: 40 bits nao bastam contra quem tenta sem parar."""
    arq = _arq_codigo(data_dir, canal)
    d = ler_json(arq)
    if not d or d.get("expira", 0) <= time.time():
        apagar(arq)
        return None
    if hmac.compare_digest(d.get("hash", ""), _hash(str(tentativa or "").strip().upper())):
        apagar(arq)
        return d.get("user_id")
    d["tentativas"] = int(d.get("tentativas", 0)) + 1
    if d["tentativas"] >= MAX_TENTATIVAS:
        apagar(arq)
    else:
        escrever_json(arq, d)
    return None


def _arq_dono(data_dir, did):
    return os.path.join(pasta(data_dir), "donos", re.sub(r"[^a-z0-9_]", "", str(did)) + ".json")


def adicionar_dono(data_dir, canal, remetente, nome, user_id):
    did = "%s_%s" % (canal, _id_de(canal, remetente))
    d = {"id": did, "canal": canal, "remetente": str(remetente), "nome": nome or "", "user_id": user_id, "desde": time.time()}
    escrever_json(_arq_dono(data_dir, did), d)
    return d


def dono_de(data_dir, canal, remetente):
    return ler_json(_arq_dono(data_dir, "%s_%s" % (canal, _id_de(canal, remetente))))


def listar_donos(data_dir, canal):
    base = os.path.join(pasta(data_dir), "donos")
    try:
        nomes = sorted(os.listdir(base))
    except OSError:
        return []
    achados = (ler_json(os.path.join(base, n)) for n in nomes if n.startswith(canal + "_") and n.endswith(".json"))
    return [{"id": d["id"], "nome": d.get("nome", ""), "desde": d.get("desde")} for d in achados if d]


def remover_dono(data_dir, did):
    arq = _arq_dono(data_dir, did)
    existe = os.path.isfile(arq)
    apagar(arq)
    return existe


def remover_donos(data_dir, canal):
    for d in listar_donos(data_dir, canal):
        remover_dono(data_dir, d["id"])


# ------------------------------------------------------------------ conversa
def _arq_conversa(data_dir, canal, remetente):
    return os.path.join(pasta(data_dir), "conversas", _id_de(canal, remetente) + ".json")


def historico(data_dir, canal, remetente):
    d = ler_json(_arq_conversa(data_dir, canal, remetente))
    return d.get("mensagens", []) if d else []


def guardar_historico(data_dir, canal, remetente, mensagens):
    escrever_json(_arq_conversa(data_dir, canal, remetente), {"mensagens": mensagens[-MAX_HISTORICO:]})


def esquecer_conversa(data_dir, canal, remetente):
    apagar(_arq_conversa(data_dir, canal, remetente))


def para_celular(texto):
    """Telegram e WhatsApp nao desenham Markdown como a tela do Nous."""
    t = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t, flags=re.S)
    return t.strip()


def dividir(texto, limite):
    """Pedacos de ate' `limite` caracteres, cortando em quebra de linha ou espaco."""
    t = texto.strip()
    partes = []
    while len(t) > limite:
        corte = t.rfind("\n", 0, limite)
        if corte < limite // 2:
            corte = t.rfind(" ", 0, limite)
        if corte < limite // 2:
            corte = limite
        partes.append(t[:corte].rstrip())
        t = t[corte:].lstrip()
    if t:
        partes.append(t)
    return partes


# ------------------------------------------------------------------ Open WebUI
def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _session_stamp(data_dir, user_id):
    """O Open WebUI 0.12 recusa token cujo carimbo nao bate com o da conta (ele muda
    quando a pessoa sai de todos os aparelhos). Fica em webui.db, no mesmo NousData."""
    import sqlite3
    db = os.path.join(str(data_dir), "webui.db")
    if not os.path.isfile(db):
        return None
    cx = sqlite3.connect(db, timeout=10)
    try:
        r = cx.execute("SELECT session_stamp FROM auth WHERE id=? AND active=1", (user_id,)).fetchone()
    finally:
        cx.close()
    return r[0] if r else None


def token_de(data_dir, user_id, validade=3600):
    """Token de sessao do Open WebUI (JWT HS256) assinado com a chave do proprio Nous
    (NousData\\.webui_secret_key), com as mesmas claims do login. Quem le' esses
    arquivos ja' e' dono do computador."""
    with open(os.path.join(str(data_dir), ".webui_secret_key"), "r", encoding="utf-8") as f:
        chave = f.read().strip().encode("utf-8")
    corpo = {"id": user_id, "typ": "session", "session_stamp": _session_stamp(data_dir, user_id),
             "exp": int(time.time()) + validade, "jti": str(uuid.uuid4())}
    base = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8")) + "." + \
        _b64(json.dumps(corpo, separators=(",", ":")).encode("utf-8"))
    return base + "." + _b64(hmac.new(chave, base.encode("ascii"), hashlib.sha256).digest())


class SemModelo(Exception):
    pass


class Nous:
    """Fala com o Open WebUI do proprio computador."""

    def __init__(self, data_dir):
        self.dd = str(data_dir)
        self.owui = os.environ.get("NOUS_OWUI_URL", "http://127.0.0.1:8080").rstrip("/")
        self.ollama = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

    def _cab(self, user_id):
        return {"Authorization": "Bearer " + token_de(self.dd, user_id)}

    async def modelo(self, s):
        """O que ja' esta' na placa de video; senao o primeiro local. Nunca nuvem:
        a conversa do celular nao pode sair para um terceiro sem a pessoa escolher."""
        def bom(m):
            n = m.get("name", "")
            return n and "/" not in n and "cloud" not in n.lower() and not m.get("remote_host") and \
                not m.get("remote_model") and not any(p in n.lower() for p in _EMBED)
        for caminho in ("/api/ps", "/api/tags"):
            try:
                async with s.get(self.ollama + caminho, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    d = await r.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                continue
            for m in (d or {}).get("models", []):
                if bom(m):
                    return m["name"]
        raise SemModelo()

    async def responder(self, user_id, mensagens, canal):
        sistema = {"role": "system", "content": "Você está respondendo pelo %s, no celular. Seja breve e direto, "
                                                "em texto simples, sem tabelas." % canal}
        async with aiohttp.ClientSession() as s:
            corpo = {"model": await self.modelo(s), "messages": [sistema] + mensagens, "stream": False}
            async with s.post(self.owui + "/api/chat/completions", json=corpo, headers=self._cab(user_id),
                              timeout=aiohttp.ClientTimeout(total=TEMPO_RESPOSTA)) as r:
                d = await r.json(content_type=None)
                if r.status != 200:
                    raise RuntimeError("open webui respondeu %d" % r.status)
        return ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""

    async def transcrever(self, user_id, dados, nome):
        """Audio -> texto pelo Whisper local do proprio Open WebUI: nao sai da maquina."""
        form = aiohttp.FormData()
        form.add_field("file", dados, filename=nome, content_type="audio/ogg")
        form.add_field("language", "pt")
        async with aiohttp.ClientSession() as s:
            async with s.post(self.owui + "/api/v1/audio/transcriptions", data=form, headers=self._cab(user_id),
                              timeout=aiohttp.ClientTimeout(total=TEMPO_RESPOSTA)) as r:
                d = await r.json(content_type=None)
                if r.status != 200:
                    raise RuntimeError("transcricao respondeu %d" % r.status)
        return (d.get("text") or "").strip()


class Atendente:
    """Recebe a mensagem de um canal e devolve a resposta. Uma de cada vez: a placa
    de video e' uma so', e duas perguntas juntas so' deixariam as duas mais lentas."""

    def __init__(self, data_dir, nous=None):
        self.dd = str(data_dir)
        self.nous = nous or Nous(data_dir)
        self._fila = asyncio.Lock()

    async def atender(self, canal, remetente, user_id, texto, enviar):
        t = (texto or "").strip()
        comando = t.split()[0].lower().split("@")[0] if t.startswith("/") else ""
        if comando in ("/novo", "/nova"):
            esquecer_conversa(self.dd, canal, remetente)
            await enviar("Conversa nova. Pode falar.")
            return
        if comando in ("/ajuda", "/help", "/start"):
            await enviar(AJUDA)
            return
        if not t:
            return
        async with self._fila:
            msgs = historico(self.dd, canal, remetente) + [{"role": "user", "content": t}]
            try:
                resposta = para_celular(await self.nous.responder(user_id, msgs, canal))
            except SemModelo:
                await enviar(SEM_MODELO)
                return
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, OSError, ValueError) as e:
                print("[Nous][mensageiros] sem resposta: %s" % type(e).__name__, flush=True)
                await enviar(SEM_RESPOSTA)
                return
            if not resposta:
                await enviar(SEM_RESPOSTA)
                return
            guardar_historico(self.dd, canal, remetente, msgs + [{"role": "assistant", "content": resposta}])
        await enviar(resposta)

    async def atender_audio(self, canal, remetente, user_id, dados, nome, enviar):
        try:
            async with self._fila:
                texto = await self.nous.transcrever(user_id, dados, nome)
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, OSError, ValueError) as e:
            print("[Nous][mensageiros] audio: %s" % type(e).__name__, flush=True)
            await enviar(AUDIO_FALHOU)
            return
        if not texto:
            await enviar(AUDIO_FALHOU)
            return
        # devolve o que entendeu: Whisper erra, e a pessoa precisa ver antes de confiar
        await enviar("🎤 " + texto)
        await self.atender(canal, remetente, user_id, texto, enviar)
