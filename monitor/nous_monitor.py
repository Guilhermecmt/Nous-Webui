# -*- coding: utf-8 -*-
"""
Nous Monitor - micro-servico local que alimenta o painel de recursos do Nous.

Expoe (em http://127.0.0.1:8990, so' para paginas locais - ver cors_mw):
  GET  /stats        -> { gpu:{ded_used,ded_total,shr_used,shr_total}, models:[...] }
  POST /unload       -> descarrega modelo(s) do Ollama (libera a VRAM na hora)
                        body opcional: {"model":"gemma4:12b"}; sem body = todos
  GET  /hardware     -> { gpu_name, vram_gb, ram_gb, tier }  (tier: gpu-20/gpu-12/gpu-8/cpu)
  GET  /installed    -> { online, models:[{name,size}], chat:[nomes] }
  GET  /catalog      -> catalogo curado (catalog.json) + installed/fit/pull por modelo,
                        ordenado: recomendados p/ esta maquina primeiro
  POST /pull         -> body {"model":"tag"}; inicia download via Ollama /api/pull
                        em background (singleton por modelo)
  GET  /pull/status  -> ?model=tag -> { status: baixando|pronto|erro, pct, ... }

GPU: lido dos contadores de desempenho do Windows (funcionam em PT-BR com os
nomes em ingles) + tamanho real da VRAM via registro (qwMemorySize).
Modelos: lidos do proprio Ollama (/api/ps), com contagem regressiva de descarga.

Nao usa dependencia nova: aiohttp ja vem no venv do Open WebUI.
"""
import os
import sys
import json
import asyncio
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import aiohttp
from aiohttp import web

OLLAMA = "http://127.0.0.1:11434"
PORT = 8990
GB = 1073741824
CATALOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalog.json")

# --------------------------------------------------------------------------
# Dados persistentes do NousData (DATA_DIR ou ~/NousData)
# --------------------------------------------------------------------------

def _data_dir():
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return Path(v)
    return Path.home() / "NousData"
# s de cache: maior que o intervalo do painel (3 s), p/ que cada ciclo de
# polling reaproveite a leitura anterior em vez de abrir outro powershell.
_GPU_TTL = 4.0
# Modelos de apoio que o proprio Nous baixa (fora do catalogo da Loja).
_EXTRA_PULLABLE = {"nomic-embed-text"}

# PowerShell que devolve a memoria da GPU (usada + total) em bytes, como JSON.
_PS_GPU = r"""
$ErrorActionPreference='SilentlyContinue'
$c = Get-Counter @('\GPU Adapter Memory(*)\Dedicated Usage','\GPU Adapter Memory(*)\Shared Usage')
$ded = ($c.CounterSamples | Where-Object {$_.Path -like '*dedicated*'} | Measure-Object CookedValue -Sum).Sum
$shr = ($c.CounterSamples | Where-Object {$_.Path -like '*shared*'}    | Measure-Object CookedValue -Sum).Sum
$total = 0
Get-ChildItem 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}' | ForEach-Object {
  $v = (Get-ItemProperty $_.PSPath -Name 'HardwareInformation.qwMemorySize').'HardwareInformation.qwMemorySize'
  if ($v -and [int64]$v -gt $total) { $total = [int64]$v }
}
$ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
$name = (Get-CimInstance Win32_VideoController | Sort-Object AdapterRAM -Descending | Select-Object -First 1).Name
[pscustomobject]@{ded_used=[int64]$ded;shr_used=[int64]$shr;ded_total=[int64]$total;shr_total=[int64]($ram/2);ram_total=[int64]$ram;gpu_name=[string]$name} | ConvertTo-Json -Compress
"""

_gpu_cache = {"t": 0.0, "data": None, "fetched": False}


async def _read_gpu():
    now = asyncio.get_event_loop().time()
    # Guard pelo timestamp, NÃO pela presença de dados: uma leitura que falhou
    # (data=None) também respeita o TTL, senão o powershell.exe seria disparado
    # a cada poll enquanto a GPU estivesse temporariamente ilegível.
    if _gpu_cache["fetched"] and (now - _gpu_cache["t"]) < _GPU_TTL:
        return _gpu_cache["data"]
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PS_GPU,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        data = json.loads(out.decode("utf-8", "ignore").strip())
    except Exception:
        data = None
    _gpu_cache.update(t=now, data=data, fetched=True)
    return data


async def _read_models():
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(f"{OLLAMA}/api/ps") as r:
                raw = await r.json()
    except Exception:
        return []
    now = datetime.now(timezone.utc)
    out = []
    for m in raw.get("models", []):
        left = None
        exp = m.get("expires_at")
        if exp:
            try:
                dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                left = max(0, int((dt - now).total_seconds()))
            except Exception:
                pass
        size = m.get("size", 0) or 0
        vram = m.get("size_vram", 0) or 0
        out.append({"name": m.get("name") or m.get("model"),
                    "vram": vram, "shared": max(0, size - vram),
                    "total": size, "seconds_left": left})
    return out


async def _unload(model=None):
    targets = [model] if model else [m["name"] for m in await _read_models()]
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        for t in targets:
            if not t:
                continue
            try:
                async with s.post(f"{OLLAMA}/api/generate",
                                  json={"model": t, "keep_alive": 0}):
                    pass
            except Exception:
                pass
    return targets


# ------------------------------------------------- Loja de Modelos (v2.2)

def _tier(vram_gb, ram_gb):
    if vram_gb >= 20:
        return "gpu-20"
    if vram_gb >= 12:
        return "gpu-12"
    if vram_gb >= 8:
        return "gpu-8"
    return "cpu"


async def _hardware():
    gpu = await _read_gpu() or {}
    vram_gb = round((gpu.get("ded_total") or 0) / GB, 1)
    ram_gb = round((gpu.get("ram_total") or 0) / GB, 1)
    if not ram_gb and gpu.get("shr_total"):
        ram_gb = round(gpu["shr_total"] * 2 / GB, 1)
    return {"gpu_name": gpu.get("gpu_name") or "",
            "vram_gb": vram_gb, "ram_gb": ram_gb,
            "tier": _tier(vram_gb, ram_gb)}


def _load_catalog():
    try:
        with open(CATALOG_PATH, encoding="utf-8") as f:
            return json.load(f).get("models", [])
    except Exception:
        return []


async def _installed_models():
    """[{name, size}] instalados no Ollama; None = Ollama fora do ar."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(f"{OLLAMA}/api/tags") as r:
                data = await r.json()
        return [{"name": m.get("name") or m.get("model") or "",
                 "size": m.get("size") or 0} for m in data.get("models", [])]
    except Exception:
        return None


async def _installed_tags():
    """Nomes instalados no Ollama; None = Ollama fora do ar."""
    models = await _installed_models()
    return None if models is None else [m["name"] for m in models]


_NOT_CHAT = ("embed", "minilm", "bge-", "rerank")


def _is_chat(name):
    n = (name or "").lower()
    return not any(k in n for k in _NOT_CHAT)


def _fit(model, hw):
    """recomendado = aproveita bem ESTA maquina; ok = roda; pesado = nao cabe."""
    if hw["tier"] == "cpu":
        if hw["ram_gb"] <= 0:
            return "ok"  # hardware desconhecido: nao assustar
        # tolerancia: maquinas "de 16 GB" reportam ~15.9 (memoria reservada)
        if model["min_ram_cpu_gb"] > hw["ram_gb"] + 0.6:
            return "pesado"
        # na CPU, menor = mais rapido = melhor experiencia
        return "recomendado" if model["download_gb"] <= 4.0 else "ok"
    vram = hw["vram_gb"]
    if model["min_vram_gb"] > vram:
        return "pesado"
    # bem dimensionado p/ a placa (nem subaproveitado, nem no limite)
    return "recomendado" if model["min_vram_gb"] >= vram / 2.5 else "ok"


def _sort_models(models, hw):
    rank = {"recomendado": 0, "ok": 1, "pesado": 2}
    cpu = hw["tier"] == "cpu"

    def key(m):
        dl = m["download_gb"]
        # GPU: dentro do grupo, melhor qualidade primeiro; CPU: mais leve primeiro
        return (rank[m["fit"]], dl if (cpu or m["fit"] == "pesado") else -dl)

    return sorted(models, key=key)


# Estado dos downloads (vive no monitor: a UI pode fechar/reabrir sem perder)
_pulls = {}        # tag -> {status, pct, completed_gb, total_gb, error}
_pull_tasks = {}   # tag -> asyncio.Task


def _friendly_pull_error(msg):
    m = (msg or "").lower()
    if "file does not exist" in m or "manifest" in m or "not found" in m:
        return "Modelo nao encontrado no catalogo do Ollama. Confira o nome."
    if ("connect" in m or "timeout" in m or "no such host" in m
            or "temporary failure" in m or "connection" in m):
        return "Sem conexao com a internet (ou o Ollama esta fechado). Tente de novo."
    if "space" in m or "disk" in m:
        return "Sem espaco em disco suficiente para este modelo."
    return "O download falhou: " + (msg or "erro desconhecido")


async def _do_pull(tag):
    """Consome o stream NDJSON do Ollama /api/pull agregando progresso por digest."""
    st = _pulls[tag]
    digests = {}
    try:
        timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=600)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(f"{OLLAMA}/api/pull",
                              json={"name": tag, "stream": True}) as r:
                async for raw in r.content:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        d = json.loads(raw)
                    except Exception:
                        continue
                    if d.get("error"):
                        st.update(status="erro",
                                  error=_friendly_pull_error(d["error"]))
                        return
                    if d.get("digest") and d.get("total"):
                        digests[d["digest"]] = (int(d.get("completed") or 0),
                                                int(d["total"]))
                        comp = sum(c for c, _ in digests.values())
                        tot = sum(t for _, t in digests.values())
                        if tot:
                            st.update(pct=round(comp / tot, 4),
                                      completed_gb=round(comp / GB, 2),
                                      total_gb=round(tot / GB, 2))
                    if (d.get("status") or "") == "success":
                        st.update(status="pronto", pct=1.0)
                        return
        if st["status"] == "baixando":
            st.update(status="erro",
                      error="O download foi interrompido. Tente de novo.")
    except Exception as e:
        st.update(status="erro", error=_friendly_pull_error(str(e)))
    finally:
        _pull_tasks.pop(tag, None)


# ----------------------------------------------------------------- HTTP / CORS
# Restrito a origens locais (mesmo padrão da Memory/Email API). O monitor expõe
# /pull (inicia downloads) e /unload (libera a VRAM); sem esta restrição qualquer
# site aberto no navegador poderia dispará-los via CSRF.

def _origin_ok(origin):
    if not origin:
        return True
    try:
        host = urllib.parse.urlparse(origin).hostname
    except Exception:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _host_ok(request):
    # Barra DNS rebinding: um dominio externo apontado p/ 127.0.0.1 chega com
    # Host: dominio-externo (e Origin dele mesmo, que o _origin_ok ja recusa).
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
    return host in ("localhost", "127.0.0.1", "::1")


def _cors_headers(origin):
    return {
        "Access-Control-Allow-Origin":  origin if (origin and _origin_ok(origin)) else "null",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


@web.middleware
async def cors_mw(request, handler):
    origin = request.headers.get("Origin")
    if not _origin_ok(origin) or not _host_ok(request):
        return web.json_response({"error": "forbidden origin"}, status=403,
                                 headers=_cors_headers(origin))
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=_cors_headers(origin))
    resp = await handler(request)
    resp.headers.update(_cors_headers(origin))
    return resp


async def h_stats(request):
    gpu, models = await asyncio.gather(_read_gpu(), _read_models())
    return web.json_response({"gpu": gpu, "models": models})


async def h_unload(request):
    model = None
    try:
        body = await request.json()
        model = (body or {}).get("model")
    except Exception:
        pass
    return web.json_response({"unloaded": await _unload(model)})


async def h_health(request):
    return web.json_response({"ok": True})


async def h_hardware(request):
    return web.json_response(await _hardware())


async def h_catalog(request):
    hw, installed = await asyncio.gather(_hardware(), _installed_tags())
    models = []
    for m in _load_catalog():
        e = dict(m)
        e["installed"] = bool(installed) and any(
            n == m["tag"] or n.startswith(m["tag"] + ":")
            for n in (installed or []))
        e["fit"] = _fit(m, hw)
        pull = _pulls.get(m["tag"])
        if pull:
            e["pull"] = pull
        models.append(e)
    return web.json_response({"hardware": hw,
                              "ollama_online": installed is not None,
                              "models": _sort_models(models, hw)})


async def h_pull(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    tag = ((body or {}).get("model") or "").strip()
    if not tag:
        return web.json_response(
            {"started": False, "reason": "modelo nao informado"}, status=400)
    allowed = {m.get("tag") for m in _load_catalog()} | _EXTRA_PULLABLE
    if tag not in allowed:
        # So' o catalogo da Loja: sem isto qualquer pagina local podia pedir um
        # modelo de centenas de GB. Outros modelos: Painel Admin > Modelos.
        return web.json_response(
            {"started": False, "reason": "modelo fora do catalogo"}, status=400)
    cur = _pulls.get(tag)
    if cur and cur["status"] == "baixando":
        return web.json_response({"started": False, "reason": "em andamento"})
    if cur and cur["status"] == "pronto":
        # Já baixado nesta sessão: não refaz o download nem apaga o estado.
        return web.json_response({"started": False, "reason": "ja baixado"})
    _pulls[tag] = {"status": "baixando", "pct": 0.0,
                   "completed_gb": 0.0, "total_gb": 0.0, "error": None}
    _pull_tasks[tag] = asyncio.get_event_loop().create_task(_do_pull(tag))
    return web.json_response({"started": True})


async def h_installed(request):
    """Modelos instalados (com tamanho). O painel usa isto em vez de chamar o
    Ollama direto do navegador. chat = so' modelos de conversa (sem embeddings)."""
    models = await _installed_models()
    if models is None:
        return web.json_response({"online": False, "models": [], "chat": []})
    return web.json_response({"online": True, "models": models,
                              "chat": [m["name"] for m in models if _is_chat(m["name"])]})


async def h_pull_status(request):
    tag = (request.query.get("model") or "").strip()
    return web.json_response(_pulls.get(tag) or {"status": "nenhum"})


# ------------------------------------------------- Voz local (v2.3)

# Estado do download de assets de voz (singleton, igual ao _pulls dos modelos)
_voice_install: dict = {"status": "inativo", "step": "", "pct": 0.0, "error": None}
_voice_task = None


def _friendly_voice_error(stderr_text: str) -> str:
    """Traduz o stderr tecnico do PowerShell numa mensagem para o usuario leigo.
    O detalhe tecnico NUNCA vai para a tela — fica so' no log do servidor."""
    m = (stderr_text or "").lower()
    if ("could not" in m or "resolve" in m or "no such host" in m or "timed out" in m
            or "remote name" in m or "connection" in m or "internet" in m):
        return ("Nao consegui baixar os arquivos de voz. Verifique sua conexao "
                "com a internet e tente de novo.")
    if "space" in m or "disk" in m or "espaco" in m:
        return "Sem espaco em disco suficiente para instalar a voz."
    if "denied" in m or "unauthorized" in m or "negado" in m or "permission" in m:
        return ("O Windows bloqueou a gravacao dos arquivos de voz. Tente rodar o "
                "Nous novamente (e verifique o antivirus).")
    # Qualquer outra falha (inclusive erro de script): mensagem generica e acionavel.
    return ("Nao foi possivel ativar a voz agora. Tente de novo; se persistir, "
            "reinicie o Nous.")


def _voice_assets_present():
    vdir = _data_dir() / "voice"
    has_piper = (vdir / "piper.exe").is_file()
    has_onnx  = bool(list(vdir.glob("pt_BR-*.onnx")))
    return has_piper and has_onnx


async def _do_voice_install():
    global _voice_install
    script = Path(__file__).parent.parent / "voice" / "install-voice.ps1"
    py     = Path(sys.executable)
    data_dir = _data_dir()

    _voice_install.update(status="instalando", pct=0.1,
                          step="Baixando Piper e voz pt_BR...", error=None)
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-DataDir", str(data_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            raw = stderr.decode("utf-8", "ignore").strip()
            # Log tecnico SO' no servidor (para diagnostico); a tela ve so' o amigavel.
            if raw:
                print(f"[Nous][voz] install-voice.ps1 falhou (rc={proc.returncode}):\n{raw}",
                      file=sys.stderr)
            _voice_install.update(status="erro", pct=0.0, step="",
                                  error=_friendly_voice_error(raw))
        else:
            _voice_install.update(status="pronto", pct=1.0,
                                  step="Voz ativada!", error=None)
    except asyncio.TimeoutError:
        _voice_install.update(status="erro", pct=0.0, step="",
                              error="A instalacao da voz demorou demais. Verifique sua "
                                    "internet e tente de novo.")
    except Exception as e:
        print(f"[Nous][voz] erro inesperado: {e}", file=sys.stderr)
        _voice_install.update(status="erro", pct=0.0, step="",
                              error="Nao foi possivel ativar a voz agora. Tente de novo.")


async def h_voice_status(request):
    present = _voice_assets_present()
    return web.json_response({
        "ativo": present,
        "install": _voice_install,
    })


async def h_voice_install(request):
    global _voice_task
    if _voice_assets_present():
        return web.json_response({"started": False, "reason": "ja instalado"})
    if _voice_install.get("status") == "instalando":
        return web.json_response({"started": False, "reason": "em andamento"})
    _voice_task = asyncio.get_event_loop().create_task(_do_voice_install())
    return web.json_response({"started": True})


def build_app():
    app = web.Application(middlewares=[cors_mw])
    app.add_routes([web.get("/stats", h_stats),
                    web.post("/unload", h_unload),
                    web.get("/health", h_health),
                    web.get("/hardware", h_hardware),
                    web.get("/catalog", h_catalog),
                    web.get("/installed", h_installed),
                    web.post("/pull", h_pull),
                    web.get("/pull/status", h_pull_status),
                    web.get("/voice/status", h_voice_status),
                    web.post("/voice/install", h_voice_install)])
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=PORT, print=None)
