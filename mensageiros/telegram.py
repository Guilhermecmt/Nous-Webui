# -*- coding: utf-8 -*-
"""
Nous - canal do Telegram. Nao abre porta nenhuma: o computador pergunta ao Telegram
se ha' mensagem nova (long polling, conexao so' de saida).

Sem biblioteca do Telegram: tres chamadas da Bot API sobre o aiohttp que o Open
WebUI ja' instala. O tratamento do 409 e o limite de tempo do long polling vem do
Hermes Agent (plugins/platforms/telegram, MIT).

O token do bot vai na URL, entao nenhum erro de rede e' registrado por inteiro:
so' o tipo da excecao.
"""
import asyncio
import os

import aiohttp

import ponte

CANAL = "telegram"
LIMITE = 4000             # o Telegram aceita 4096; sobra para nao cortar no meio
ESPERA_POLL = 25
TEMPO_POLL = 45           # acima da espera: no Windows, conexao morta travaria para sempre
MAX_AUDIO = 20 * 1024 * 1024


def api_base():
    return os.environ.get("NOUS_TELEGRAM_API", "https://api.telegram.org").rstrip("/")


class TokenInvalido(Exception):
    pass


class Conflito(Exception):
    pass


async def _chamar(s, token, metodo, tempo=30, **campos):
    url = "%s/bot%s/%s" % (api_base(), token, metodo)
    async with s.post(url, json=campos, timeout=aiohttp.ClientTimeout(total=tempo)) as r:
        d = await r.json(content_type=None)
    if r.status == 401:
        raise TokenInvalido()
    if r.status == 409:
        raise Conflito()
    if r.status == 429:
        await asyncio.sleep(min(30, int(((d or {}).get("parameters") or {}).get("retry_after", 2))))
        raise aiohttp.ClientError("limite do telegram")
    if not (d or {}).get("ok"):
        raise aiohttp.ClientError("telegram recusou (%d)" % r.status)
    return d.get("result")


async def validar(token):
    """@nome do bot, ou TokenInvalido."""
    async with aiohttp.ClientSession() as s:
        eu = await _chamar(s, token, "getMe", tempo=15)
    return eu.get("username") or ""


class Telegram:
    def __init__(self, data_dir, token, atendente, avisar=lambda estado: None):
        self.dd = str(data_dir)
        self.token = token
        self.atendente = atendente
        self.avisar = avisar
        self.fila = asyncio.Queue()

    async def _enviar(self, s, chat, texto):
        for parte in ponte.dividir(ponte.para_celular(texto), LIMITE):
            await _chamar(s, self.token, "sendMessage", chat_id=chat, text=parte)

    async def _digitando(self, s, chat):
        """O Telegram apaga o "digitando" em 5 s: repete enquanto o modelo pensa."""
        try:
            while True:
                await _chamar(s, self.token, "sendChatAction", chat_id=chat, action="typing", tempo=10)
                await asyncio.sleep(4)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            pass

    async def _baixar(self, s, file_id):
        info = await _chamar(s, self.token, "getFile", file_id=file_id)
        if int(info.get("file_size") or 0) > MAX_AUDIO:
            raise ValueError("audio grande demais")
        url = "%s/file/bot%s/%s" % (api_base(), self.token, info["file_path"])
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=120)) as r:
            if r.status != 200:
                raise aiohttp.ClientError("download do audio falhou")
            return await r.read()

    def _parear(self, chat, de, texto):
        """/start <codigo>. Codigo errado: silencio, como para qualquer estranho."""
        partes = (texto or "").split()
        if len(partes) != 2 or partes[0].split("@")[0].lower() != "/start":
            return None
        uid = ponte.usar_codigo(self.dd, CANAL, partes[1])
        if not uid:
            return None
        return ponte.adicionar_dono(self.dd, CANAL, chat, de.get("first_name") or de.get("username") or "", uid)

    async def _tratar(self, s, m):
        chat = (m.get("chat") or {})
        # so' conversa direta: em grupo, qualquer um leria a resposta
        if chat.get("type") != "private":
            return
        cid = chat.get("id")
        texto = m.get("text") or ""
        dono = ponte.dono_de(self.dd, CANAL, cid)
        if not dono:
            if self._parear(cid, m.get("from") or {}, texto):
                await self._enviar(s, cid, "Pronto, conectado ao seu Nous.\n\n" + ponte.AJUDA)
            return
        enviar = lambda t: self._enviar(s, cid, t)
        pulso = asyncio.create_task(self._digitando(s, cid))
        try:
            voz = m.get("voice") or m.get("audio")
            if voz:
                dados = await self._baixar(s, voz["file_id"])
                await self.atendente.atender_audio(CANAL, cid, dono["user_id"], dados, "audio.ogg", enviar)
            elif texto:
                await self.atendente.atender(CANAL, cid, dono["user_id"], texto, enviar)
            else:
                await enviar(ponte.SO_TEXTO)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as e:
            print("[Nous][telegram] mensagem: %s" % type(e).__name__, flush=True)
            await enviar(ponte.AUDIO_FALHOU if m.get("voice") or m.get("audio") else ponte.SEM_RESPOSTA)
        finally:
            pulso.cancel()

    async def _consumir(self, s):
        while True:
            m = await self.fila.get()
            try:
                await self._tratar(s, m)
            except (aiohttp.ClientError, asyncio.TimeoutError, TokenInvalido, Conflito) as e:
                print("[Nous][telegram] resposta: %s" % type(e).__name__, flush=True)

    async def rodar(self):
        offset = None
        conflitos = 0
        async with aiohttp.ClientSession() as s:
            consumidor = asyncio.create_task(self._consumir(s))
            try:
                while True:
                    try:
                        campos = {"timeout": ESPERA_POLL, "allowed_updates": ["message"]}
                        if offset is not None:
                            campos["offset"] = offset
                        novos = await _chamar(s, self.token, "getUpdates", tempo=TEMPO_POLL, **campos)
                        conflitos = 0
                        self.avisar("conectado")
                        for u in novos or []:
                            # adianta o offset antes de atender: mensagem que derruba o
                            # processo nao pode voltar para sempre
                            offset = u["update_id"] + 1
                            if u.get("message"):
                                self.fila.put_nowait(u["message"])
                    except TokenInvalido:
                        self.avisar("token_invalido")
                        await asyncio.sleep(300)
                    except Conflito:
                        # o Telegram segura a sessao anterior por ~30 s depois de um reinicio
                        conflitos += 1
                        self.avisar("conflito")
                        await asyncio.sleep(min(60, 10 + conflitos * 10))
                    except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError) as e:
                        print("[Nous][telegram] rede: %s" % type(e).__name__, flush=True)
                        self.avisar("sem_internet")
                        await asyncio.sleep(10)
            finally:
                consumidor.cancel()
