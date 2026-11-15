"""Sobe e derruba os llama-server do nous-motor: um processo por modelo carregado.

Regras (docs/PLANO-MOTOR-PROPRIO.md, "Regras do modo llama"):
- contexto = pedido, senao o padrao; nunca acima do context_length do GGUF; pedido maior recarrega;
- ate max_modelos de geracao carregados (embedding nao conta); sai o ocioso usado ha mais tempo;
- modelo com pedido em andamento nunca e' derrubado: quem precisa da vaga espera;
- keep_alive marca quando o modelo pode sair; faxina() derruba os vencidos.
"""
import asyncio
import collections
import dataclasses
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

import aiohttp

from traduz import keep_alive_segundos

PARA_SEMPRE = "2318-08-30T00:00:00Z"  # o Ollama usa uma data longe assim para keep_alive -1


class ErroMotor(Exception):
    """Erro com mensagem em portugues, pronta para ir ao usuario."""


@dataclasses.dataclass
class _Proc:
    modelo: object
    ctx: int
    proc: object
    url: str
    em_uso: int = 0
    usado_em: float = 0.0
    expira_em: "float | None" = 0.0
    stderr: collections.deque = dataclasses.field(default_factory=lambda: collections.deque(maxlen=40))
    leitor: "asyncio.Task | None" = None

    @property
    def vivo(self):
        return self.proc.returncode is None


def _porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def _iniciar_padrao(argv):
    extra = {}
    if sys.platform == "win32":
        extra["creationflags"] = subprocess.CREATE_NO_WINDOW
    return await asyncio.create_subprocess_exec(*argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.PIPE, **extra)


class Gerente:
    def __init__(self, binario, max_modelos=2, ctx_padrao=16384, keep_padrao="5m", iniciar=None,
                 espera_pronto=180.0, arquivo_pids=None):
        self.binario = binario
        self.max_modelos = max(1, int(max_modelos))
        self.ctx_padrao = int(ctx_padrao)
        self.keep_padrao = keep_padrao
        self.iniciar = iniciar or _iniciar_padrao
        self.espera_pronto = espera_pronto
        self.arquivo_pids = arquivo_pids
        self._procs = {}
        self._travas = {}
        self._subindo = asyncio.Lock()
        self._mudou = asyncio.Condition()

    # ------------------------------------------------------------------ util
    def _trava(self, nome):
        return self._travas.setdefault(nome, asyncio.Lock())

    def _ctx_alvo(self, m, ctx):
        alvo = int(ctx) if ctx else self.ctx_padrao
        maximo = int(m.gguf.get("contexto") or 0)
        if maximo:
            alvo = min(alvo, maximo)
        return max(alvo, 256)

    def _argv(self, m, ctx, porta):
        a = [self.binario, "-m", m.blob, "--host", "127.0.0.1", "--port", str(porta), "-c", str(ctx),
             "-ngl", "999", "--jinja", "--reasoning-format", "deepseek", "-np", "1", "--no-webui"]
        if m.gguf.get("embedding"):
            a.append("--embeddings")
        if m.projetor:
            a += ["--mmproj", m.projetor]
        return a

    def _gravar_pids(self):
        if not self.arquivo_pids:
            return
        try:
            os.makedirs(os.path.dirname(self.arquivo_pids), exist_ok=True)
            with open(self.arquivo_pids, "w", encoding="utf-8") as f:
                json.dump([p.proc.pid for p in self._procs.values() if p.vivo], f)
        except OSError:
            pass

    async def _avisar(self):
        async with self._mudou:
            self._mudou.notify_all()

    # --------------------------------------------------------------- subir
    async def _ler_stderr(self, p):
        try:
            while True:
                linha = await p.proc.stderr.readline()
                if not linha:
                    break
                p.stderr.append(linha.decode("utf-8", "replace").rstrip())
        except (asyncio.CancelledError, Exception):
            pass

    async def _esperar_pronto(self, p):
        limite = time.monotonic() + self.espera_pronto
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as s:
            while True:
                if not p.vivo:
                    await asyncio.sleep(0.05)  # deixa o leitor pegar o fim do stderr
                    fim = " | ".join(x for x in list(p.stderr)[-6:] if x)
                    raise ErroMotor("o llama-server parou ao carregar %s%s" % (p.modelo.nome, (": " + fim) if fim else ""))
                try:
                    async with s.get(p.url + "/health") as r:
                        if r.status == 200:
                            return
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                    pass
                if time.monotonic() > limite:
                    await self._encerrar(p)
                    raise ErroMotor("o modelo %s nao ficou pronto em %d s" % (p.modelo.nome, self.espera_pronto))
                await asyncio.sleep(0.1)

    async def _subir(self, m, ctx):
        porta = _porta_livre()
        proc = await self.iniciar(self._argv(m, ctx, porta))
        p = _Proc(modelo=m, ctx=ctx, proc=proc, url="http://127.0.0.1:%d" % porta, usado_em=time.monotonic())
        if getattr(proc, "stderr", None) is not None:
            p.leitor = asyncio.ensure_future(self._ler_stderr(p))
        try:
            await self._esperar_pronto(p)
        except BaseException:
            if p.vivo:
                await self._encerrar(p)
            raise
        seg = keep_alive_segundos(None, self.keep_padrao)
        p.expira_em = None if seg is None else time.time() + seg
        self._procs[m.nome] = p
        self._gravar_pids()
        return p

    async def _encerrar(self, p):
        if p.vivo:
            try:
                p.proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(p.proc.wait(), 5)
            except asyncio.TimeoutError:
                try:
                    p.proc.kill()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(p.proc.wait(), 5)
                except asyncio.TimeoutError:
                    pass
        if p.leitor:
            p.leitor.cancel()
        if self._procs.get(p.modelo.nome) is p:
            del self._procs[p.modelo.nome]
        self._gravar_pids()
        await self._avisar()

    async def _abrir_espaco(self, nome):
        while True:
            geracao = [p for n, p in self._procs.items()
                       if n != nome and p.vivo and not p.modelo.gguf.get("embedding")]
            if len(geracao) < self.max_modelos:
                return
            ociosos = sorted((p for p in geracao if p.em_uso == 0), key=lambda p: p.usado_em)
            if ociosos:
                await self._encerrar(ociosos[0])
                continue
            async with self._mudou:
                await self._mudou.wait()

    async def _esperar_livre(self, p):
        while p.em_uso > 0 and p.vivo:
            async with self._mudou:
                await self._mudou.wait()

    async def _garantir(self, m, ctx):
        alvo = self._ctx_alvo(m, ctx)
        async with self._trava(m.nome):
            p = self._procs.get(m.nome)
            if p and not p.vivo:
                await self._encerrar(p)
                p = None
            if p and (p.ctx >= alvo or not ctx):
                p.usado_em = time.monotonic()
                return p
            if p:
                await self._esperar_livre(p)
                alvo = max(alvo, p.ctx)
                await self._encerrar(p)
            async with self._subindo:
                if not m.gguf.get("embedding"):
                    await self._abrir_espaco(m.nome)
                return await self._subir(m, alvo)

    # ------------------------------------------------------------ publico
    async def garantir(self, m, ctx):
        """Devolve a URL base de um llama-server pronto com o modelo m."""
        return (await self._garantir(m, ctx)).url

    def usando(self, m, ctx, keep_alive):
        gerente = self

        class _Uso:
            async def __aenter__(self):
                self.p = await gerente._garantir(m, ctx)
                self.p.em_uso += 1
                return self.p.url

            async def __aexit__(self, *exc):
                p = self.p
                p.em_uso -= 1
                p.usado_em = time.monotonic()
                seg = keep_alive_segundos(keep_alive, gerente.keep_padrao)
                p.expira_em = None if seg is None else time.time() + seg
                await gerente._avisar()
                return False

        return _Uso()

    async def soltar(self, nome):
        p = self._procs.get(nome)
        if not p:
            return False
        if p.em_uso > 0:
            p.expira_em = time.time()  # sai na faxina, quando o pedido acabar
        else:
            await self._encerrar(p)
        return True

    async def soltar_todos(self):
        for p in list(self._procs.values()):
            await self._encerrar(p)

    async def faxina(self):
        agora = time.time()
        for p in list(self._procs.values()):
            if not p.vivo:
                await self._encerrar(p)
            elif p.em_uso == 0 and p.expira_em is not None and p.expira_em <= agora:
                await self._encerrar(p)

    def ativos(self):
        saida = []
        for p in sorted(self._procs.values(), key=lambda p: p.modelo.nome):
            if not p.vivo:
                continue
            m = p.modelo
            if p.expira_em is None:
                expira = PARA_SEMPRE
            else:
                expira = datetime.fromtimestamp(p.expira_em, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
            saida.append({
                "name": m.nome, "model": m.nome, "size": m.tamanho, "digest": m.digest,
                "details": {"parent_model": "", "format": "gguf", "family": m.familia, "families": [m.familia],
                            "parameter_size": m.tamanho_param, "quantization_level": m.quantizacao},
                "expires_at": expira, "size_vram": m.tamanho, "context_length": p.ctx,
            })
        return saida
