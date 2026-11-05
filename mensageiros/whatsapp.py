# -*- coding: utf-8 -*-
"""
Nous - canal do WhatsApp (experimental). O WhatsApp nao tem API para isto: quem fala
com ele e' a ponte em Node (mensageiros/whatsapp-ponte, biblioteca Baileys, nao
oficial), que entra como "aparelho conectado" da conta. A conta pode ser suspensa
por isso, e a tela diz antes de ligar.

So' existe o modo "conversa consigo mesmo": o Nous le' apenas o que a pessoa escreve
no proprio numero. Mensagem de outra pessoa, e o que ela manda para os outros, a
ponte descarta antes de chegar aqui, e aqui confere de novo.

A ponte escuta em 127.0.0.1 e exige um segredo gerado a cada vez que sobe.

Etapas: instalar (npm ci, uma vez) -> parear (QR) -> rodar.
"""
import asyncio
import json
import os
import secrets
import shutil
import subprocess

import aiohttp

import ponte

CANAL = "whatsapp"
PORTA = 8987
_AQUI = os.path.dirname(os.path.abspath(__file__))
DIR_PONTE = os.path.join(_AQUI, "whatsapp-ponte")
SEM_JANELA = 0x08000000
POLL = 1.0


def porta():
    return int(os.environ.get("NOUS_WHATSAPP_PORT", PORTA))


def sessao(data_dir):
    return os.path.join(ponte.pasta(data_dir), "whatsapp", "sessao")


def pareado(data_dir):
    return os.path.isfile(os.path.join(sessao(data_dir), "creds.json"))


def achar_node():
    """O mesmo criterio de launchers/node-nous.ps1: o do computador ou o portatil."""
    raiz = os.path.dirname(_AQUI)
    for c in (shutil.which("node"), os.path.join(os.environ.get("ProgramFiles", ""), "nodejs", "node.exe"),
              os.path.join(raiz, "runtime", "node", "node.exe")):
        if c and os.path.isfile(c):
            return c
    return None


def _npm(node):
    """npm-cli.js ao lado do node: funciona igual no Node instalado e no portatil."""
    base = os.path.dirname(node)
    cli = os.path.join(base, "node_modules", "npm", "bin", "npm-cli.js")
    return [node, cli] if os.path.isfile(cli) else None


def instalado():
    return os.path.isdir(os.path.join(DIR_PONTE, "node_modules", "@whiskeysockets", "baileys"))


class WhatsApp:
    def __init__(self, data_dir, user_id, atendente, avisar=lambda estado, **extra: None):
        self.dd = str(data_dir)
        self.user_id = user_id
        self.atendente = atendente
        self.avisar = avisar
        self.segredo = secrets.token_hex(24)
        self.proc = None

    def _env(self):
        e = dict(os.environ)
        cache = os.path.join(ponte.pasta(self.dd), "whatsapp", "cache")
        e.update({"NOUS_PONTE_SEGREDO": self.segredo, "NOUS_AUDIO_CACHE": cache, "NOUS_IMAGEM_CACHE": cache, "NOUS_DOC_CACHE": cache})
        return e

    async def _instalar(self, node):
        if instalado():
            return True
        cmd = _npm(node)
        if not cmd:
            self.avisar("sem_npm")
            return False
        self.avisar("instalando")
        p = await asyncio.create_subprocess_exec(*cmd, "ci", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund", cwd=DIR_PONTE,
                                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=SEM_JANELA)
        await p.wait()
        if p.returncode != 0 or not instalado():
            self.avisar("falha_instalar")
            return False
        return True

    async def _subir(self, node, *extra, saida=subprocess.DEVNULL):
        os.makedirs(sessao(self.dd), exist_ok=True)
        return await asyncio.create_subprocess_exec(
            node, "bridge.js", "--port", str(porta()), "--session", sessao(self.dd), *extra,
            cwd=DIR_PONTE, env=self._env(), stdout=saida, stderr=subprocess.DEVNULL, creationflags=SEM_JANELA)

    async def _parear(self, node):
        """Sobe a ponte so' para mostrar o QR. Ela sai sozinha depois de conectar."""
        self.proc = await self._subir(node, "--pair-only", "--pair-json", saida=subprocess.PIPE)
        conectou = False
        while True:
            linha = await self.proc.stdout.readline()
            if not linha:
                break
            try:
                ev = json.loads(linha.decode("utf-8", "replace"))
            except ValueError:
                continue
            if ev.get("event") == "qr":
                self.avisar("qr", qr=ev.get("qr"))
            elif ev.get("event") == "connected":
                conectou = True
                self.avisar("pareando")
            elif ev.get("event") == "error":
                break
        await self.proc.wait()
        return conectou and pareado(self.dd)

    def _cab(self):
        return {"X-Nous-Ponte": self.segredo}

    async def _enviar(self, s, chat, texto):
        url = "http://127.0.0.1:%d/send" % porta()
        async with s.post(url, json={"chatId": chat, "message": texto}, headers=self._cab(),
                          timeout=aiohttp.ClientTimeout(total=60)) as r:
            if r.status != 200:
                raise aiohttp.ClientError("ponte recusou (%d)" % r.status)

    async def _tratar(self, s, ev):
        chat = ev.get("chatId") or ""
        # a ponte ja' filtra; aqui e' a segunda trava, e barata
        if ev.get("isGroup") or not chat or not ev.get("eProprio"):
            return
        enviar = lambda t: self._enviar(s, chat, ponte.para_celular(t))
        try:
            if ev.get("hasMedia") and ev.get("mediaType") in ("audio", "ptt", "voice"):
                arquivos = ev.get("mediaUrls") or []
                if not arquivos:
                    await enviar(ponte.AUDIO_FALHOU)
                    return
                with open(arquivos[0], "rb") as f:
                    dados = f.read()
                ponte.apagar(arquivos[0])
                await self.atendente.atender_audio(CANAL, chat, self.user_id, dados, "audio.ogg", enviar)
            elif ev.get("hasMedia"):
                await enviar(ponte.SO_TEXTO)
            else:
                await self.atendente.atender(CANAL, chat, self.user_id, ev.get("body") or "", enviar)
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
            print("[Nous][whatsapp] mensagem: %s" % type(e).__name__, flush=True)

    async def _ler_mensagens(self):
        url = "http://127.0.0.1:%d/messages" % porta()
        async with aiohttp.ClientSession() as s:
            while self.proc and self.proc.returncode is None:
                await asyncio.sleep(POLL)
                try:
                    async with s.get(url, headers=self._cab(), timeout=aiohttp.ClientTimeout(total=10)) as r:
                        itens = await r.json(content_type=None) if r.status == 200 else []
                    async with s.get("http://127.0.0.1:%d/health" % porta(), headers=self._cab(),
                                     timeout=aiohttp.ClientTimeout(total=5)) as r:
                        saude = await r.json(content_type=None) if r.status == 200 else {}
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    continue
                self.avisar("conectado" if saude.get("status") == "connected" else "reconectando")
                for ev in itens if isinstance(itens, list) else []:
                    if isinstance(ev, dict) and "body" in ev:
                        asyncio.create_task(self._tratar(s, ev))

    def parar(self):
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass

    async def rodar(self):
        node = achar_node()
        if not node:
            self.avisar("sem_node")
            return
        if not await self._instalar(node):
            return
        espera = 5
        try:
            while True:
                if not pareado(self.dd):
                    if not await self._parear(node):
                        self.avisar("qr_expirou")
                        return
                self.avisar("reconectando")
                self.proc = await self._subir(node)
                await self._ler_mensagens()
                await self.proc.wait()
                # a ponte sai com 1 quando a conta foi desconectada pelo celular
                if self.proc.returncode == 1 and not pareado(self.dd):
                    self.avisar("deslogado")
                    return
                await asyncio.sleep(espera)
                espera = min(120, espera * 2)
        finally:
            self.parar()
