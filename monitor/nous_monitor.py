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
  GET  /research     -> biblioteca de relatorios da Pesquisa Profunda
  GET  /research/view?id=  -> o relatorio visual (HTML, CSP sem scripts)
  POST /research/delete    -> body {"id": ...}
  POST /image/remove-bg    -> corpo = bytes da imagem; devolve PNG sem fundo
  GET  /diag               -> cada peca do Nous: ok? + dica do que fazer
  POST /pdf/fields         -> corpo = PDF; campos preenchiveis
  POST /pdf/fill           -> {pdf: base64, values, place?}; devolve o PDF preenchido/assinado
  POST /pdf/autofill       -> {fields, facts}; sugere valores a partir das memorias
  GET|POST /pdf/signature  -> assinatura desenhada (PNG em NousData); POST /pdf/signature/delete
  GET  /docs, /docs/get?id=, /docs/version?id=&i=   Documentos (v2.9)
  POST /docs/save {id?, titulo, texto, motivo?} | /docs/delete {id}
  POST /docs/ai   {texto, instrucao, ini?, fim?, model?} -> sugestoes (diff) para aceitar/recusar
  POST /docs/import?nome=  corpo = arquivo -> {titulo, texto}
  POST /docs/export {titulo, texto, formato: docx|pdf|md} -> o arquivo
  GET  /research/export?id=&formato=docx|pdf|md     relatorio da Pesquisa em Word/PDF
  GET  /model/check?name=  qualquer modelo do Ollama/Hugging Face: tamanho e se cabe
  GET  /catalog?vram_gb=&ram_gb=&gpu=  simulacao "e se eu tivesse outra maquina"

GPU: lido dos contadores de desempenho do Windows (funcionam em PT-BR com os
nomes em ingles) + tamanho real da VRAM via registro (qwMemorySize).
Modelos: lidos do proprio Ollama (/api/ps), com contagem regressiva de descarga.

Nao usa dependencia nova: aiohttp ja vem no venv do Open WebUI.
"""
import os
import sys
import json
import re
import asyncio
import subprocess
import urllib.parse
import sqlite3
import shutil
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
_EXTRA_PULLABLE = {"nomic-embed-text", "granite-embedding:278m"}

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
$dimms = @(Get-CimInstance Win32_PhysicalMemory)
$mts = ($dimms | Measure-Object ConfiguredClockSpeed -Maximum).Maximum
[pscustomobject]@{ded_used=[int64]$ded;shr_used=[int64]$shr;ded_total=[int64]$total;shr_total=[int64]($ram/2);ram_total=[int64]$ram;gpu_name=[string]$name;ram_mts=[int]$mts;ram_dimms=[int]$dimms.Count} | ConvertTo-Json -Compress
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
    # Para o ComfyUI (porta 8188) matando o processo Python que o sustenta.
    # O /interrupt do ComfyUI aborta a geração em curso mas não libera a VRAM;
    # apenas encerrar o processo libera completamente.
    await _stop_comfyui()
    return targets


async def _start_comfyui() -> bool:
    """Sobe o ComfyUI (porta 8188) se ainda não estiver no ar. Retorna True se ok."""
    # Já está no ar?
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as s:
            async with s.get("http://localhost:8188/system_stats") as r:
                if r.status < 500:
                    return True
    except Exception:
        pass

    # Localiza o ComfyUI
    home = Path.home()
    cu = None
    for d in ("ComfyUI", "ComfyUI-Zluda"):
        candidate = home / d
        if (candidate / "venv" / "Scripts" / "python.exe").exists():
            cu = candidate
            break
    if not cu:
        return False

    cpy  = str(cu / "venv" / "Scripts" / "python.exe")
    main = str(cu / "main.py")
    env  = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        await asyncio.create_subprocess_exec(
            cpy, main, "--port", "8188",
            cwd=str(cu),
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
    except Exception:
        return False

    # Aguarda até 90 s
    deadline = asyncio.get_event_loop().time() + 90
    chk = aiohttp.ClientTimeout(total=4)
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(3)
        try:
            async with aiohttp.ClientSession(timeout=chk) as s:
                async with s.get("http://localhost:8188/system_stats") as r:
                    if r.status < 500:
                        return True
        except Exception:
            pass
    return False


async def h_comfyui_start(request):
    ok = await _start_comfyui()
    return web.json_response({"ok": ok})


async def _stop_comfyui():
    """Encerra o processo Python do ComfyUI (porta 8188) liberando a VRAM."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue"
            " | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=8)
    except Exception:
        pass


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
    tier = _tier(vram_gb, ram_gb)
    return {"gpu_name": gpu.get("gpu_name") or "",
            "vram_gb": vram_gb, "ram_gb": ram_gb, "tier": tier,
            "gpu_bw": _gpu_bandwidth(gpu.get("gpu_name"), vram_gb) if tier != "cpu" else 0,
            "ram_bw": _ram_bandwidth(gpu.get("ram_mts"), gpu.get("ram_dimms"))}


# ---------------------------------------------- Estimativa de velocidade
# Gerar 1 token le o modelo inteiro da memoria, entao a velocidade e' limitada
# pela banda: tokens/s ~= banda (GB/s) / tamanho do modelo (GB) * eficiencia.
# Ideia do llmfit (MIT, Alex Jones); tabela e formula escritas aqui.
# Banda em GB/s pela ficha tecnica oficial de cada placa.
_GPU_BW = {
    "rtx 5090": 1792, "rtx 5080": 960, "rtx 5070 ti": 896, "rtx 5070": 672,
    "rtx 5060 ti": 448, "rtx 5060": 448,
    "rtx 4090": 1008, "rtx 4080 super": 736, "rtx 4080": 717,
    "rtx 4070 ti super": 672, "rtx 4070 ti": 504, "rtx 4070 super": 504,
    "rtx 4070": 504, "rtx 4060 ti": 288, "rtx 4060": 272,
    "rtx 3090 ti": 1008, "rtx 3090": 936, "rtx 3080 ti": 912, "rtx 3080": 760,
    "rtx 3070 ti": 608, "rtx 3070": 448, "rtx 3060 ti": 448, "rtx 3060": 360,
    "rtx 3050": 224, "rtx 2080 ti": 616, "rtx 2080": 448, "rtx 2070": 448,
    "rtx 2060": 336, "gtx 1660 super": 336, "gtx 1660": 192,
    "gtx 1080 ti": 484, "gtx 1080": 320, "gtx 1070": 256,
    "rx 9070 xt": 640, "rx 9070": 640, "rx 9060 xt": 320,
    "rx 7900 xtx": 960, "rx 7900 xt": 800, "rx 7900 gre": 576,
    "rx 7800 xt": 624, "rx 7700 xt": 432, "rx 7600 xt": 288, "rx 7600": 288,
    "rx 6950 xt": 576, "rx 6900 xt": 512, "rx 6800 xt": 512, "rx 6800": 512,
    "rx 6750 xt": 432, "rx 6700 xt": 384, "rx 6650 xt": 280, "rx 6600": 224,
    "arc b580": 456, "arc a770": 560, "arc a750": 512,
}
_GPU_BW_KEYS = sorted(_GPU_BW, key=len, reverse=True)  # "4070 ti" antes de "4070"
_GPU_EFF = 0.55
_CPU_EFF = 0.5


def _gpu_bandwidth(name, vram_gb):
    n = (name or "").lower()
    for k in _GPU_BW_KEYS:
        if k in n:
            return _GPU_BW[k]
    # placa desconhecida: placas com mais VRAM costumam ter barramento maior
    return 450 if vram_gb >= 16 else 300 if vram_gb >= 8 else 200


def _ram_bandwidth(mts, dimms):
    mts = mts or 0
    if mts <= 0:
        return 50  # DDR4 dual channel tipico
    channels = 2 if (dimms or 0) >= 2 else 1
    return round(mts * 8 * channels / 1000)


def _speed(model, hw):
    """{tps, onde}: tokens/s estimados e onde o modelo roda (gpu|misto|cpu)."""
    size = model["download_gb"] * 1.1  # pesos + buffers do runtime
    ram_bw = hw.get("ram_bw") or 50
    gpu_bw = hw.get("gpu_bw") or 0
    if hw["tier"] == "cpu" or not gpu_bw:
        return {"tps": round(ram_bw / size * _CPU_EFF, 1), "onde": "cpu"}
    # ~1.5 GB da VRAM ficam para o contexto da conversa e o sistema
    frac = max(0.0, min(1.0, (hw["vram_gb"] - 1.5) / size))
    if frac >= 1.0:
        return {"tps": round(gpu_bw / size * _GPU_EFF, 1), "onde": "gpu"}
    # parte na RAM: cada token passa pelos dois lados, e o lado lento domina
    t = (frac * size / (gpu_bw * _GPU_EFF)) + ((1 - frac) * size / (ram_bw * _CPU_EFF))
    return {"tps": round(1 / t, 1), "onde": "misto" if frac > 0 else "cpu"}


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


def _local_chat(name):
    """Modelo de conversa que roda aqui. A lista vem do proprio Ollama, entao
    "usuario/modelo" e "hf.co/..." sao locais; so' os ":cloud" saem da maquina."""
    n = (name or "").lower()
    return _is_chat(n) and not re.search(r"[-:]cloud$", n)


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


class _Parado(Exception):
    """Download sem avancar: os bytes nao mudam ha' _PARADO_S segundos."""


_PARADO_S = 90       # sem nenhum byte novo por este tempo = travado
_TENTATIVAS = 3      # o Ollama continua de onde parou, entao recomecar e' barato


async def _pull_uma_vez(tag, st, digests):
    """Uma passada pelo stream NDJSON do /api/pull. True = terminou."""
    loop = asyncio.get_event_loop()
    ultimo, quando = -1, loop.time()
    # sock_read curto: o Ollama manda progresso varias vezes por segundo; o
    # silencio total tambem conta como travado
    timeout = aiohttp.ClientTimeout(total=None, connect=10, sock_read=_PARADO_S)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        async with s.post(f"{OLLAMA}/api/pull", json={"name": tag, "stream": True}) as r:
            async for raw in r.content:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                if d.get("error"):
                    raise RuntimeError(d["error"])
                if d.get("digest") and d.get("total"):
                    digests[d["digest"]] = (int(d.get("completed") or 0), int(d["total"]))
                    comp = sum(c for c, _ in digests.values())
                    tot = sum(t for _, t in digests.values())
                    if tot:
                        st.update(pct=round(comp / tot, 4), completed_gb=round(comp / GB, 2),
                                  total_gb=round(tot / GB, 2))
                    if comp != ultimo:
                        ultimo, quando = comp, loop.time()
                        st["nota"] = None
                    elif loop.time() - quando > _PARADO_S:
                        raise _Parado()
                if (d.get("status") or "") == "success":
                    st.update(status="pronto", pct=1.0, nota=None)
                    return True
    return False


async def _do_pull(tag):
    """Baixa pelo Ollama; se travar ou a conexao cair, tenta de novo sozinho
    (ate' _TENTATIVAS vezes) mostrando o aviso no card da Loja."""
    st = _pulls[tag]
    digests = {}
    try:
        for tentativa in range(1, _TENTATIVAS + 1):
            try:
                if await _pull_uma_vez(tag, st, digests):
                    return
                motivo = "O download foi interrompido."
            except (_Parado, asyncio.TimeoutError, aiohttp.ClientError) as e:
                motivo = ("O download parou de andar." if isinstance(e, (_Parado, asyncio.TimeoutError))
                          else _friendly_pull_error(str(e)))
            if tentativa < _TENTATIVAS:
                st["nota"] = f"Conexao lenta: tentando de novo ({tentativa + 1}/{_TENTATIVAS})..."
                await asyncio.sleep(3 * tentativa)
        st.update(status="erro", nota=None, error=motivo + " Verifique a internet e tente de novo.")
    except Exception as e:
        st.update(status="erro", nota=None, error=_friendly_pull_error(str(e)))
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


def _simular(hw, q):
    """?vram_gb=&ram_gb=&gpu= : "e se eu tivesse outra maquina?" (v2.9)."""
    try:
        vram = max(0.0, min(256.0, float(q.get("vram_gb", hw["vram_gb"]))))
        ram = max(1.0, min(1024.0, float(q.get("ram_gb", hw["ram_gb"]) or 1)))
    except (TypeError, ValueError):
        return hw
    gpu = (q.get("gpu") or "").strip()[:60]
    tier = _tier(vram, ram)
    return {"gpu_name": gpu or ("GPU com %g GB" % vram if vram else ""), "vram_gb": vram, "ram_gb": ram,
            "tier": tier, "gpu_bw": _gpu_bandwidth(gpu, vram) if tier != "cpu" else 0,
            "ram_bw": hw.get("ram_bw") or 50, "simulado": True}


def _installed_match(tag, installed):
    return bool(installed) and any(n == tag or n.startswith(tag + ":") or
                                   (":" not in tag and n == tag + ":latest") for n in installed)


async def h_catalog(request):
    hw, installed = await asyncio.gather(_hardware(), _installed_tags())
    if "vram_gb" in request.query or "ram_gb" in request.query:
        hw = _simular(hw, request.query)
    models = []
    catalog = _load_catalog()
    for m in catalog:
        e = dict(m)
        e["installed"] = _installed_match(m["tag"], installed)
        e["fit"] = _fit(m, hw)
        e["speed"] = _speed(m, hw)
        pull = _pulls.get(m["tag"])
        if pull:
            e["pull"] = pull
        models.append(e)
    # downloads de fora do catalogo (v2.9: "qualquer modelo"), com o progresso
    tags = {m["tag"] for m in catalog} | _EXTRA_PULLABLE
    outros = [{"tag": t, "pull": p, "download_gb": (_checked.get(t) or {}).get("gb"),
               "installed": _installed_match(t, installed)}
              for t, p in _pulls.items() if t not in tags]
    return web.json_response({"hardware": hw,
                              "ollama_online": installed is not None,
                              "models": _sort_models(models, hw),
                              "outros": outros})


# ------------------------------------------- Qualquer modelo (v2.9)
# O usuario cola um nome do Ollama ("qwen3:8b"), um link do ollama.com ou um
# repositorio GGUF do Hugging Face. Antes de baixar, o tamanho vem do registro
# (manifesto, sem baixar nada) e o Nous diz se cabe na maquina e no disco.

_checked = {}      # tag -> {"gb", "t"}: so' baixa o que foi conferido aqui
_CHECK_TTL = 3600
_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json"
_NOME_OK = re.compile(r"^(?:hf\.co/[\w.-]+/[\w.-]+|(?:[a-z0-9][\w.-]*/)?[a-z0-9][\w.-]*)(?::[\w.-]{1,80})?$", re.I)


def _nome_modelo(raw):
    """Texto colado -> nome que o Ollama entende (ou None)."""
    s = (raw or "").strip().strip("'\"`")
    s = re.sub(r"^ollama\s+(?:run|pull)\s+", "", s, flags=re.I).strip()
    m = re.match(r"^https?://(?:www\.)?ollama\.com/(?:library/)?([\w.-]+(?:/[\w.-]+)?(?::[\w.-]+)?)/?$", s, re.I)
    if m:
        s = m.group(1)
    m = re.match(r"^(?:https?://)?(?:www\.)?(?:huggingface\.co|hf\.co)/([\w.-]+/[\w.-]+)(?:/(?:tree|blob|resolve)/\S*)?/?(:[\w.-]+)?$",
                 s, re.I)
    if m:
        s = "hf.co/" + m.group(1) + (m.group(2) or "")
    if s.lower().startswith("huggingface.co/"):
        s = "hf.co/" + s[15:]
    return s if _NOME_OK.match(s) and len(s) <= 160 else None


def _manifest_url(name):
    base, _, tag = name.partition(":")
    tag = tag or "latest"
    if base.lower().startswith("hf.co/"):
        return f"https://hf.co/v2/{base[6:]}/manifests/{tag}"
    path = base if "/" in base else "library/" + base
    return f"https://registry.ollama.ai/v2/{path}/manifests/{tag}"


async def h_model_check(request):
    name = _nome_modelo(request.query.get("name"))
    if not name:
        return web.json_response({"ok": False, "erro": "Nao entendi esse nome. Exemplos: qwen3:8b, "
                                  "gemma3, ou um link do ollama.com ou do Hugging Face."})
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.get(_manifest_url(name), headers={"Accept": _MANIFEST}) as r:
                if r.status in (401, 404):
                    return web.json_response({"ok": False, "name": name, "erro": (
                        "Nao achei esse modelo. Confira o nome (e o tamanho depois dos dois pontos)."
                        if not name.lower().startswith("hf.co/") else
                        "Nao achei esse modelo no Hugging Face. Ele precisa ter arquivos GGUF "
                        "(procure repositorios com 'GGUF' no nome).")})
                if r.status != 200:
                    raise RuntimeError(f"HTTP {r.status}")
                man = await r.json(content_type=None)
    except Exception as e:
        print(f"[Nous][loja] manifesto de {name}: {e}", file=sys.stderr)
        return web.json_response({"ok": False, "name": name,
                                  "erro": "Sem conexao com o catalogo de modelos. Verifique a internet."})
    layers = man.get("layers") or []
    total = sum(int(x.get("size") or 0) for x in layers) + int((man.get("config") or {}).get("size") or 0)
    if not total:
        return web.json_response({"ok": False, "name": name, "erro": "Esse modelo nao tem arquivos para baixar."})
    gb = round(total / GB, 1)
    hw, installed = await asyncio.gather(_hardware(), _installed_tags())
    m = {"download_gb": gb, "min_vram_gb": round(gb * 1.1 + 1.0, 1), "min_ram_cpu_gb": round(gb * 1.5 + 4, 1)}
    try:
        free = round(shutil.disk_usage(str(_data_dir() if _data_dir().exists() else Path.home())).free / GB, 1)
    except Exception:
        free = None
    _checked[name] = {"gb": gb, "t": asyncio.get_event_loop().time()}
    return web.json_response({
        "ok": True, "name": name, "download_gb": gb, "fit": _fit(m, hw), "speed": _speed(m, hw),
        "vision": any("projector" in (x.get("mediaType") or "") for x in layers),
        "installed": _installed_match(name, installed), "disk_free_gb": free,
        "cabe_disco": free is None or free >= gb + 2, "hardware": hw})


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
        # Fora do catalogo, so' o que passou pelo /model/check ha' pouco (o
        # usuario viu o tamanho) e cabe no disco: sem isto qualquer pagina
        # local podia pedir um modelo de centenas de GB.
        chk = _checked.get(tag)
        if not chk or asyncio.get_event_loop().time() - chk["t"] > _CHECK_TTL:
            return web.json_response(
                {"started": False, "reason": "confira o modelo antes de baixar"}, status=400)
        try:
            free = shutil.disk_usage(str(_data_dir() if _data_dir().exists() else Path.home())).free / GB
            if free < chk["gb"] + 2:
                return web.json_response({"started": False, "reason": "sem espaco em disco"}, status=400)
        except Exception:
            pass
    cur = _pulls.get(tag)
    if cur and cur["status"] == "baixando":
        return web.json_response({"started": False, "reason": "em andamento"})
    if cur and cur["status"] == "pronto":
        # Já baixado nesta sessão: não refaz o download nem apaga o estado.
        return web.json_response({"started": False, "reason": "ja baixado"})
    _pulls[tag] = {"status": "baixando", "pct": 0.0,
                   "completed_gb": 0.0, "total_gb": 0.0, "error": None, "nota": None}
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


# ------------------------------------------------- Galeria de Imagens (v2.3)

def _webui_db():
    dd = _data_dir()
    p = dd / "webui.db"
    return str(p) if p.is_file() else None


def _gallery_images():
    """Retorna lista de dicts com metadados de imagens geradas pelo Flux."""
    db_path = _webui_db()
    if not db_path:
        return []
    try:
        cx = sqlite3.connect(db_path, timeout=10)
        cx.row_factory = sqlite3.Row
        rows = cx.execute(
            "SELECT id, filename, meta, path, created_at FROM file "
            "WHERE filename LIKE '%generated-image%' OR filename LIKE '%image.png' "
            "ORDER BY created_at DESC"
        ).fetchall()
        cx.close()
    except Exception:
        return []
    images = []
    for r in rows:
        try:
            meta = json.loads(r["meta"] or "{}")
        except Exception:
            meta = {}
        # Filtra apenas imagens geradas pelo pipe (content_type image/png)
        if meta.get("content_type") not in ("image/png", "image/jpeg", "image/webp"):
            continue
        path = r["path"] or ""
        exists = os.path.isfile(path) if path else False
        images.append({
            "id": r["id"],
            "filename": r["filename"],
            "path": path,
            "exists": exists,
            "size": meta.get("size", 0),
            "chat_id": (meta.get("data") or {}).get("chat_id"),
            "created_at": r["created_at"],
        })
    return images


def _gal_meta_path():
    return _data_dir() / "gallery_meta.json"


def _gal_meta():
    """{id: {"fav": bool, "album": str}} - favoritas e albuns da galeria (v2.8)."""
    try:
        return json.loads(_gal_meta_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


async def h_gallery(request):
    images = await asyncio.get_event_loop().run_in_executor(None, _gallery_images)
    meta = _gal_meta()
    # Não expõe o path completo ao frontend por segurança
    safe = [{**{k: v for k, v in img.items() if k != "path"},
             "fav": bool(meta.get(img["id"], {}).get("fav")),
             "album": meta.get(img["id"], {}).get("album", "")} for img in images]
    albums = sorted({m.get("album") for m in meta.values() if m.get("album")})
    return web.json_response({"images": safe, "albums": albums})


async def h_gallery_meta(request):
    """{id, fav?, album?}: marca favorita / poe num album ("" tira do album)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    img_id = str((body or {}).get("id") or "")
    if not img_id:
        return web.json_response({"error": "id ausente"}, status=400)
    meta = _gal_meta()
    m = meta.setdefault(img_id, {})
    if "fav" in body:
        m["fav"] = bool(body["fav"])
    if "album" in body:
        m["album"] = re.sub(r"\s+", " ", str(body["album"] or "")).strip()[:60]
    if not m.get("fav") and not m.get("album"):
        meta.pop(img_id, None)
    p = _gal_meta_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)
    return web.json_response({"ok": True})


async def h_gallery_image(request):
    """Serve os bytes da imagem para exibição na galeria (miniatura inline)."""
    img_id = request.match_info.get("id", "")
    if not img_id:
        return web.Response(status=400)
    images = await asyncio.get_event_loop().run_in_executor(None, _gallery_images)
    match = next((img for img in images if img["id"] == img_id), None)
    if not match:
        return web.Response(status=404)
    path = match.get("path", "")
    if not path or not os.path.isfile(path):
        return web.Response(status=404)
    try:
        data = Path(path).read_bytes()
        return web.Response(body=data, content_type="image/png",
                            headers={"Cache-Control": "max-age=3600"})
    except Exception:
        return web.Response(status=500)


def _move_to_recycle(path: str) -> bool:
    """Move arquivo para o lixeiro do Windows via PowerShell."""
    try:
        script = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile("
            "'" + path.replace("'", "''") + "',"
            f"'OnlyErrorDialogs','SendToRecycleBin')"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            timeout=10, capture_output=True
        )
        return result.returncode == 0
    except Exception:
        return False


def _delete_image(img_id: str, permanent: bool) -> dict:
    db_path = _webui_db()
    if not db_path:
        return {"ok": False, "error": "banco nao encontrado"}

    try:
        cx = sqlite3.connect(db_path, timeout=10)
        row = cx.execute("SELECT path FROM file WHERE id=?", (img_id,)).fetchone()
        if not row:
            cx.close()
            return {"ok": False, "error": "imagem nao encontrada"}
        file_path = row[0] or ""
        cx.execute("DELETE FROM file WHERE id=?", (img_id,))
        cx.commit()
        cx.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    file_deleted = False
    if file_path and os.path.isfile(file_path):
        if permanent:
            try:
                os.remove(file_path)
                file_deleted = True
            except Exception:
                pass
        else:
            file_deleted = _move_to_recycle(file_path)

    return {"ok": True, "file_deleted": file_deleted,
            "permanent": permanent, "id": img_id}


async def h_gallery_delete(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    img_id = (body.get("id") or "").strip()
    permanent = bool(body.get("permanent", False))
    if not img_id:
        return web.json_response({"ok": False, "error": "id ausente"}, status=400)
    result = await asyncio.get_event_loop().run_in_executor(
        None, _delete_image, img_id, permanent)
    return web.json_response(result)


# ------------------------------------------------- Relatorios de pesquisa (v2.7)
# Biblioteca da Pesquisa Profunda (search/nous_search/report.py grava em
# NousData/research). A pagina e' servida com CSP sem scripts: o texto veio da
# web via LLM.

_REPORT_CSP = ("default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; "
               "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def _report_mod():
    sp = str(Path(__file__).resolve().parent.parent / "search")
    if sp not in sys.path:
        sys.path.insert(0, sp)
    from nous_search import report
    return report


async def h_research_list(request):
    return web.json_response({"reports": _report_mod().list_reports()})


async def h_research_view(request):
    p = _report_mod().report_path(request.query.get("id"))
    if not p:
        return web.Response(status=404, text="Relatorio nao encontrado.")
    with open(p, encoding="utf-8") as f:
        return web.Response(text=f.read(), content_type="text/html",
                            headers={"Content-Security-Policy": _REPORT_CSP,
                                     "Referrer-Policy": "no-referrer"})


async def h_research_delete(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    _report_mod().delete((body or {}).get("id"))
    return web.json_response({"ok": True})


# ------------------------------------------------- Editor de fotos (v2.7)
# "Remover fundo" do editor: U^2-Net pequeno (u2netp, Apache-2.0, 4,5 MB) via
# onnxruntime, que ja vem no venv do Open WebUI. Baixado no primeiro uso para
# NousData/models e conferido pelo SHA-256. O resto do editor roda no navegador.

_U2NET_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"
_U2NET_SHA = "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"
_MAX_IMG = 20 * 1024 * 1024
_u2net = {"session": None}
_u2net_lock = asyncio.Lock()


def _u2net_session():
    if _u2net["session"] is not None:
        return _u2net["session"]
    import hashlib
    import urllib.request
    import onnxruntime as ort
    path = _data_dir() / "models" / "u2netp.onnx"
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        urllib.request.urlretrieve(_U2NET_URL, tmp)
        if hashlib.sha256(tmp.read_bytes()).hexdigest() != _U2NET_SHA:
            tmp.unlink()
            raise RuntimeError("o arquivo do modelo veio corrompido")
        tmp.replace(path)
    _u2net["session"] = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return _u2net["session"]


def _remove_bg(data):
    import io
    import numpy as np
    from PIL import Image
    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGBA")
    rgb = img.convert("RGB")
    x = np.asarray(rgb.resize((320, 320), Image.LANCZOS), dtype=np.float32)
    x = x / max(1.0, float(x.max()))
    x = (x - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    x = x.transpose(2, 0, 1)[None, ...].astype(np.float32)
    sess = _u2net_session()
    pred = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    lo, hi = float(pred.min()), float(pred.max())
    pred = (pred - lo) / ((hi - lo) or 1.0)
    mask = Image.fromarray((pred * 255).astype("uint8"), "L").resize(img.size, Image.LANCZOS)
    # mantem a transparencia que a imagem ja tinha
    alpha = Image.fromarray(np.minimum(np.asarray(mask), np.asarray(img.getchannel("A"))))
    img.putalpha(alpha)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


async def h_remove_bg(request):
    data = await request.read()
    if not data or len(data) > _MAX_IMG:
        return web.json_response({"error": "imagem vazia ou maior que 20 MB"}, status=400)
    async with _u2net_lock:  # um por vez: CPU e memoria
        try:
            png = await asyncio.get_event_loop().run_in_executor(None, _remove_bg, data)
        except Exception as e:
            msg = str(e)
            if "urlopen" in msg or "getaddrinfo" in msg or "corrompido" in msg:
                msg = "Nao consegui baixar o modelo de recorte (4,5 MB). Verifique a internet."
            else:
                print(f"[Nous][editor] remover fundo: {e}", file=sys.stderr)
                msg = "Nao consegui abrir esta imagem."
            return web.json_response({"error": msg}, status=500)
    return web.Response(body=png, content_type="image/png")


# ------------------------------------------------- Diagnostico (v2.8)
# "O que esta funcionando?": cada peca do Nous com uma dica do que fazer.

_SERVICOS = [
    ("Servidor do Nous", "http://127.0.0.1:8080/health", True,
     "Feche o navegador e abra o Nous pelo atalho da area de trabalho."),
    ("Memoria e personas", "http://127.0.0.1:8993/health", True,
     "Abra o Nous pelo atalho: ele inicia este servico sozinho."),
    ("Assistente de Email", "http://127.0.0.1:8995/health", True,
     "Abra o Nous pelo atalho: ele inicia este servico sozinho."),
    ("Agenda, lembretes e tarefas", "http://127.0.0.1:8996/health", True,
     "Abra o Nous pelo atalho. Sem este servico os lembretes nao avisam."),
    ("Habilidades", "http://127.0.0.1:8997/health", True,
     "Abra o Nous pelo atalho: ele inicia este servico sozinho."),
    ("Nous Code (painel Codigo)", "http://127.0.0.1:8998/health", False,
     "Opcional. Precisa do Node.js 22.18+ (winget install OpenJS.NodeJS.LTS); depois abra o Nous pelo atalho."),
    ("Voz (Piper)", "http://127.0.0.1:8994/health", False,
     "Opcional. Ative em Recursos > Ativar voz em PT-BR."),
    ("Busca na web (SearXNG)", "http://127.0.0.1:8888/healthz", False,
     "Opcional, usada pela Pesquisa Profunda. Precisa do Docker Desktop aberto."),
    ("Imagens (ComfyUI)", "http://127.0.0.1:8188/system_stats", False,
     "Opcional. Instale pelo images/install-comfyui.ps1."),
]


async def _probe(s, url):
    try:
        async with s.get(url) as r:
            return r.status < 500
    except Exception:
        return False


async def h_diag(request):
    timeout = aiohttp.ClientTimeout(total=4)
    out = []
    async with aiohttp.ClientSession(timeout=timeout) as s:
        oks = await asyncio.gather(*[_probe(s, url) for _n, url, _e, _d in _SERVICOS])
    for (nome, _url, essencial, dica), ok in zip(_SERVICOS, oks):
        out.append({"nome": nome, "ok": ok, "essencial": essencial, "dica": "" if ok else dica})
    models = await _installed_models()
    if models is None:
        out.insert(0, {"nome": "Motor de IA (Ollama)", "ok": False, "essencial": True,
                       "dica": "Abra o Nous pelo atalho (ele liga o Ollama) ou abra o app Ollama."})
    else:
        names = [m["name"] for m in models]
        chat = [n for n in names if _is_chat(n)]
        out.insert(0, {"nome": "Motor de IA (Ollama)", "ok": True, "essencial": True, "dica": ""})
        out.insert(1, {"nome": "Modelo de conversa", "ok": bool(chat), "essencial": True,
                       "detalhe": ", ".join(chat[:4]),
                       "dica": "" if chat else "Baixe um modelo em Recursos > Baixar modelos."})
        emb = any(n.startswith("granite-embedding") for n in names)
        out.insert(2, {"nome": "Busca por significado (embeddings)", "ok": emb, "essencial": True,
                       "dica": "" if emb else "Abra o Nous pelo atalho: ele baixa o granite-embedding (~560 MB) sozinho."})
    # disco onde ficam os dados
    try:
        import shutil
        free = shutil.disk_usage(str(_data_dir())).free / GB
        out.append({"nome": "Espaco livre em disco", "ok": free >= 5, "essencial": True,
                    "detalhe": f"{free:.0f} GB livres",
                    "dica": "" if free >= 5 else "Libere espaco: modelos de IA ocupam de 2 a 20 GB cada."})
    except Exception:
        pass
    return web.json_response({"itens": out})


# ------------------------------------------------- Formularios PDF (v2.8)
# Preencher PDF preenchivel e carimbar a assinatura (documentos/pdf_tools.py).

def _doc_mod(name):
    """Modulo de documentos/ (pdf_tools, escrita, exportar, textos)."""
    import importlib
    p = str(Path(__file__).resolve().parent.parent / "documentos")
    if p not in sys.path:
        sys.path.insert(0, p)
    return importlib.import_module(name)


def _pdf_mod():
    return _doc_mod("pdf_tools")


async def h_pdf_fields(request):
    data = await request.read()
    if not data.startswith(b"%PDF"):
        return web.json_response({"error": "isso nao e' um PDF"}, status=400)
    try:
        return web.json_response(await asyncio.get_event_loop().run_in_executor(None, _pdf_mod().fields, data))
    except Exception:
        return web.json_response({"error": "nao consegui abrir este PDF (protegido ou corrompido?)"}, status=400)


async def h_pdf_fill(request):
    import base64
    try:
        body = await request.json()
        pdf = base64.b64decode(body.get("pdf") or "")
    except Exception:
        return web.json_response({"error": "pedido invalido"}, status=400)
    pt = _pdf_mod()
    sig = None
    if body.get("place"):
        if not os.path.isfile(pt.sig_path()):
            return web.json_response({"error": "desenhe sua assinatura primeiro"}, status=400)
        sig = Path(pt.sig_path()).read_bytes()
    try:
        out = await asyncio.get_event_loop().run_in_executor(
            None, pt.fill, pdf, body.get("values") or {}, sig, body.get("place"))
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        print(f"[Nous][pdf] {e}", file=sys.stderr)
        return web.json_response({"error": "nao consegui preencher este PDF"}, status=500)
    return web.Response(body=out, content_type="application/pdf")


async def h_pdf_sig_get(request):
    p = _pdf_mod().sig_path()
    if not os.path.isfile(p):
        return web.json_response({"exists": False})
    return web.Response(body=Path(p).read_bytes(), content_type="image/png")


async def h_pdf_sig_save(request):
    data = await request.read()
    if not data.startswith(b"\x89PNG") or len(data) > 2 * 1024 * 1024:
        return web.json_response({"error": "assinatura invalida"}, status=400)
    p = Path(_pdf_mod().sig_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return web.json_response({"ok": True})


async def h_pdf_sig_delete(request):
    p = Path(_pdf_mod().sig_path())
    if p.is_file():
        p.unlink()
    return web.json_response({"ok": True})


_AUTOFILL_PROMPT = """Preencha um formulario com os FATOS conhecidos sobre o usuario. So' use o que esta
nos fatos; campo sem informacao fica "". Datas no formato dd/mm/aaaa.

FATOS:
{facts}

CAMPOS (nome :: rotulo):
{fields}

Responda so' com JSON: um objeto com o nome de cada campo e o valor."""


async def h_pdf_autofill(request):
    """Sugere valores para os campos a partir das memorias (o usuario revisa)."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    flds = [f for f in (body.get("fields") or []) if f.get("type") == "text"][:60]
    facts = [str(x) for x in (body.get("facts") or [])][:150]
    if not flds or not facts:
        return web.json_response({"values": {}})
    schema = {"type": "object", "properties": {f["name"]: {"type": "string"} for f in flds}}
    prompt = _AUTOFILL_PROMPT.format(facts="\n".join(f"- {x}" for x in facts),
                                     fields="\n".join(f"{f['name']} :: {f.get('label', '')}" for f in flds))
    models = await _installed_tags() or []
    chat = [m for m in models if _local_chat(m)]
    if not chat:
        return web.json_response({"error": "nenhum modelo de conversa instalado"}, status=400)
    try:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(f"{OLLAMA}/api/generate", json={
                    "model": chat[0], "prompt": prompt, "stream": False, "think": False, "format": schema,
                    "options": {"temperature": 0, "num_ctx": int(os.environ.get("NOUS_NUM_CTX", "16384"))}}) as r:
                values = json.loads((await r.json()).get("response") or "{}")
    except Exception:
        return web.json_response({"error": "o modelo nao respondeu"}, status=502)
    return web.json_response({"values": {k: v for k, v in values.items() if isinstance(v, str) and v.strip()}})


# --------------------------------------------------------------------------
# Comparar modelos (v2.8): a mesma pergunta para 2 a 4 modelos, um de cada vez
# (uma placa so': em paralelo eles disputariam a VRAM e a velocidade mentiria).
# Cada resposta volta com tempo e tokens/s; o voto do usuario vai para um placar.
# --------------------------------------------------------------------------

_CMP_LOCK = asyncio.Lock()
_CMP_SYSTEM = "Responda sempre em portugues do Brasil, de forma clara e direta."


def _score_path():
    return _data_dir() / "compare_score.json"


def _score_read():
    try:
        return json.loads(_score_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _score_write(sc):
    p = _score_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _score_list(sc):
    out = []
    for name, v in sc.items():
        jogos = v.get("jogos", 0)
        out.append({"model": name, "jogos": jogos, "vitorias": v.get("vitorias", 0),
                    "empates": v.get("empates", 0),
                    "taxa": round(100 * v.get("vitorias", 0) / jogos) if jogos else 0,
                    "tps": round(v["tps_soma"] / v["tps_n"], 1) if v.get("tps_n") else None})
    out.sort(key=lambda x: (-x["taxa"], -x["vitorias"], -x["jogos"], x["model"]))
    return out


async def _cmp_chat(s, payload):
    async with s.post(f"{OLLAMA}/api/chat", json=payload) as r:
        d = await r.json(content_type=None)
        return r.status, d


async def h_compare_run(request):
    """{model, prompt} -> {text, secs, load, tokens, tps}. Um modelo por vez."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    model = str(body.get("model") or "")[:120]
    prompt = str(body.get("prompt") or "").strip()[:8000]
    if not model or not prompt:
        return web.json_response({"error": "faltou o modelo ou a pergunta"}, status=400)
    tags = await _installed_tags()
    if tags is None:
        return web.json_response({"error": "o motor de IA (Ollama) nao esta no ar"}, status=503)
    if model not in tags or not _is_chat(model):
        return web.json_response({"error": "esse modelo nao esta instalado"}, status=400)
    payload = {"model": model, "stream": False, "think": False, "keep_alive": "2m",
               "messages": [{"role": "system", "content": _CMP_SYSTEM}, {"role": "user", "content": prompt}],
               "options": {"num_ctx": int(os.environ.get("NOUS_NUM_CTX", "16384"))}}
    async with _CMP_LOCK:
        try:
            timeout = aiohttp.ClientTimeout(total=600)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                status, d = await _cmp_chat(s, payload)
                if status != 200 and "think" in str(d.get("error", "")).lower():
                    payload.pop("think")  # modelo sem modo de pensar: pede de novo sem o campo
                    status, d = await _cmp_chat(s, payload)
        except asyncio.TimeoutError:
            return web.json_response({"error": "o modelo demorou demais (10 min)"}, status=504)
        except Exception:
            return web.json_response({"error": "o motor de IA nao respondeu"}, status=502)
    if status != 200:
        return web.json_response({"error": str(d.get("error") or "falhou")[:300]}, status=502)
    text = (d.get("message") or {}).get("content") or ""
    # alguns modelos (qwen3) pensam em voz alta mesmo com think=False e o "<think>"
    # de abertura fica no molde: vale o que vem depois do ultimo "</think>"
    text = text.rsplit("</think>", 1)[-1].strip()
    ev, evd = d.get("eval_count") or 0, d.get("eval_duration") or 0
    return web.json_response({"text": text,
                              "secs": round((d.get("total_duration") or 0) / 1e9, 1),
                              "load": round((d.get("load_duration") or 0) / 1e9, 1),
                              "tokens": ev,
                              "tps": round(ev / (evd / 1e9), 1) if evd else None})


async def h_compare_vote(request):
    """{models:[...], winner: modelo|"" (empate), tps:{modelo: n}} -> placar."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    models = [str(m)[:120] for m in (body.get("models") or []) if isinstance(m, str) and m]
    models = list(dict.fromkeys(models))
    winner = str(body.get("winner") or "")
    tps = body.get("tps") or {}
    if not 2 <= len(models) <= 4 or (winner and winner not in models):
        return web.json_response({"error": "voto invalido"}, status=400)
    sc = _score_read()
    for m in models:
        v = sc.setdefault(m, {"jogos": 0, "vitorias": 0, "empates": 0, "tps_soma": 0.0, "tps_n": 0})
        v["jogos"] += 1
        if not winner:
            v["empates"] = v.get("empates", 0) + 1
        elif m == winner:
            v["vitorias"] += 1
        t = tps.get(m) if isinstance(tps, dict) else None
        if isinstance(t, (int, float)) and 0 < t < 10000:
            v["tps_soma"] += float(t)
            v["tps_n"] += 1
    _score_write(sc)
    return web.json_response({"placar": _score_list(sc)})


async def h_compare_score(request):
    return web.json_response({"placar": _score_list(_score_read())})


async def h_compare_reset(request):
    try:
        _score_path().unlink()
    except FileNotFoundError:
        pass
    return web.json_response({"placar": []})


# --------------------------------------------------------------------------
# Documentos (v2.9): escrever com a IA propondo mudancas (documentos/escrita.py)
# e exportar para Word/PDF (documentos/exportar.py), tambem os relatorios.
# --------------------------------------------------------------------------

_DOC_LOCK = asyncio.Lock()


async def _body_json(request):
    try:
        return await request.json() or {}
    except Exception:
        return {}


async def _run(fn, *args):
    return await asyncio.get_event_loop().run_in_executor(None, fn, *args)


async def _pick_model(pedido):
    """O modelo pedido (se instalado e local) ou o primeiro de conversa local."""
    tags = await _installed_tags()
    if tags is None:
        raise RuntimeError("o motor de IA (Ollama) nao esta no ar")
    chat = [m for m in tags if _local_chat(m)]
    if pedido in chat:
        return pedido
    if not chat:
        raise RuntimeError("nenhum modelo de conversa instalado (Recursos > Baixar modelos)")
    return chat[0]


def _download(data, nome, ctype):
    """Resposta de arquivo com o nome certo (acentos via filename*)."""
    nome = re.sub(r'[\\/:*?"<>|\r\n]+', " ", nome or "documento").strip()[:90] or "documento"
    ascii_nome = nome.encode("ascii", "ignore").decode() or "documento"
    cs = "utf-8" if ctype.startswith("text/") else None
    return web.Response(body=data, content_type=ctype, charset=cs, headers={
        "Content-Disposition": "attachment; filename=\"%s\"; filename*=UTF-8''%s"
                               % (ascii_nome, urllib.parse.quote(nome))})


_FORMATOS = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             "pdf": "application/pdf", "md": "text/markdown"}


async def _exportar(titulo, md, formato):
    if formato not in _FORMATOS:
        return web.json_response({"error": "formato invalido"}, status=400)
    if formato == "md":
        data = md.encode("utf-8")
    else:
        ex = _doc_mod("exportar")
        try:
            data = await _run(getattr(ex, formato), titulo, md)
        except Exception as e:
            print(f"[Nous][docs] exportar {formato}: {e}", file=sys.stderr)
            return web.json_response({"error": "nao consegui gerar o arquivo"}, status=500)
    return _download(data, f"{titulo}.{formato}", _FORMATOS[formato])


async def h_docs_list(request):
    return web.json_response({"docs": await _run(_doc_mod("escrita").listar)})


async def h_docs_get(request):
    es = _doc_mod("escrita")
    doc = es.ler(request.query.get("id"))
    if not doc:
        return web.json_response({"error": "documento nao encontrado"}, status=404)
    return web.json_response(es.resumo(doc))


async def h_docs_save(request):
    b = await _body_json(request)
    if "texto" not in b:  # pedido quebrado nao vira documento vazio
        return web.json_response({"error": "pedido invalido"}, status=400)
    es = _doc_mod("escrita")
    doc = await _run(es.salvar, str(b.get("id") or ""), str(b.get("titulo") or ""),
                     str(b.get("texto") or ""), str(b.get("motivo") or "")[:80])
    return web.json_response(es.resumo(doc))


async def h_docs_delete(request):
    b = await _body_json(request)
    _doc_mod("escrita").apagar(str(b.get("id") or ""))
    return web.json_response({"ok": True})


async def h_docs_version(request):
    texto = _doc_mod("escrita").versao(request.query.get("id"), request.query.get("i"))
    if texto is None:
        return web.json_response({"error": "versao nao encontrada"}, status=404)
    return web.json_response({"texto": texto})


async def h_docs_ai(request):
    """O modelo reescreve (tudo ou a selecao); volta o diff para o usuario revisar."""
    b = await _body_json(request)
    es = _doc_mod("escrita")
    texto = str(b.get("texto") or "")
    ini, fim = b.get("ini"), b.get("fim")
    sel = isinstance(ini, int) and isinstance(fim, int) and fim > ini
    try:
        msgs, pre, alvo, suf = es.prompt(texto, str(b.get("instrucao") or ""),
                                         ini if sel else None, fim if sel else None)
        model = await _pick_model(str(b.get("model") or ""))
    except (ValueError, RuntimeError) as e:
        return web.json_response({"error": str(e)}, status=400)
    pensa = await _pensa_sempre(model)
    if not pensa:
        msgs = es.sem_pensar(msgs, model)
    payload = {"model": model, "stream": True, "think": pensa, "keep_alive": "5m", "messages": msgs,
               "options": {"temperature": 0.3, "num_ctx": int(os.environ.get("NOUS_NUM_CTX", "16384"))}}
    t0 = asyncio.get_event_loop().time()
    # stream: NDJSON {"d": pedaco} enquanto o modelo escreve (o painel mostra
    # ao vivo) e no fim {"fim": {...}} ou {"erro": "..."}. Se o usuario cancela,
    # a conexao cai, o laco para e o Ollama para de gerar.
    resp = None
    if b.get("stream"):
        resp = web.StreamResponse(headers={"Content-Type": "application/x-ndjson", "Cache-Control": "no-store",
                                           **_cors_headers(request.headers.get("Origin"))})
        await resp.prepare(request)

    async def manda(obj):
        if resp is not None:
            await resp.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    partes, erro, status_erro, pensou = [], None, 502, 0
    async with _DOC_LOCK:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=420, sock_read=180)) as s:
                for tentativa in (1, 2):
                    async with s.post(f"{OLLAMA}/api/chat", json=payload) as r:
                        if r.status != 200:
                            d = await r.json(content_type=None)
                            if tentativa == 1 and "think" in str(d.get("error", "")).lower():
                                payload.pop("think", None)  # modelo sem modo de pensar
                                continue
                            erro = str(d.get("error") or "falhou")[:300]
                            break
                        async for raw in r.content:
                            raw = raw.strip()
                            if not raw:
                                continue
                            try:
                                d = json.loads(raw)
                            except Exception:
                                continue
                            if d.get("error"):
                                erro = str(d["error"])[:300]
                                break
                            msg = d.get("message") or {}
                            if msg.get("thinking"):
                                # o painel mostra "pensando..." com a contagem, nao o raciocinio
                                antes, pensou = pensou, pensou + len(msg["thinking"])
                                if pensou // 300 != antes // 300:
                                    await manda({"p": pensou})
                            pedaco = msg.get("content") or ""
                            if pedaco:
                                partes.append(pedaco)
                                await manda({"d": pedaco})
                            if d.get("done"):
                                break
                    break
        except ConnectionResetError:  # o usuario cancelou (o aiohttp herda dela)
            return resp
        except asyncio.TimeoutError:
            erro, status_erro = "o modelo demorou demais (7 min). Tente com um trecho menor.", 504
        except Exception as e:
            print(f"[Nous][docs] ia: {e}", file=sys.stderr)
            erro = "o motor de IA nao respondeu"
    if not erro:
        novo = es.limpar("".join(partes), alvo)
        if not novo.strip():
            erro = "o modelo devolveu um texto vazio. Tente de novo."
    if erro:
        if resp is None:
            return web.json_response({"error": erro}, status=status_erro)
        await manda({"erro": erro})
        await resp.write_eof()
        return resp
    segs = es.diff(alvo, novo, pre, suf)
    fim = {"segs": segs, "model": model, "mudancas": sum(1 for x in segs if x["t"] == "~"),
           "secs": round(asyncio.get_event_loop().time() - t0, 1)}
    if resp is None:
        return web.json_response(fim)
    await manda({"fim": fim})
    await resp.write_eof()
    return resp


_PENSA = {}   # modelo -> sempre pensa? (cache do /api/show)


async def _pensa_sempre(model):
    """Modelos como o qwen3 2507 "thinking" abrem o <think> no proprio molde:
    com think=False o raciocinio vaza para a resposta. Para esses o pedido vai
    com think=True, e o Ollama separa o raciocinio (message.thinking)."""
    if model not in _PENSA:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
                async with s.post(f"{OLLAMA}/api/show", json={"model": model}) as r:
                    d = await r.json(content_type=None)
            tpl = d.get("template") or ""
            _PENSA[model] = "thinking" in (d.get("capabilities") or []) and "assistant\n<think>" in tpl
        except Exception:
            return False
    return _PENSA[model]


async def h_docs_porque(request):
    """{antes, depois, contexto?, model?} -> {motivo}: uma frase explicando a sugestao."""
    b = await _body_json(request)
    antes, depois = str(b.get("antes") or "")[:2000], str(b.get("depois") or "")[:2000]
    if not antes.strip() and not depois.strip():
        return web.json_response({"error": "nada para explicar"}, status=400)
    es = _doc_mod("escrita")
    regra = es.porque_regra(antes, depois)
    if regra:
        return web.json_response({"motivo": regra, "fonte": "regra"})
    try:
        model = await _pick_model(str(b.get("model") or ""))
    except RuntimeError as e:
        return web.json_response({"error": str(e)}, status=400)
    prompt = es.prompt_porque(antes, depois, str(b.get("contexto") or "")[:1500])
    payload = {"model": model, "stream": False, "think": await _pensa_sempre(model), "keep_alive": "5m",
               "format": {"type": "object", "required": ["motivo"], "properties": {"motivo": {"type": "string"}}},
               "messages": es.sem_pensar([{"role": "user", "content": prompt}], model),
               "options": {"temperature": 0.2, "num_ctx": int(os.environ.get("NOUS_NUM_CTX", "16384"))}}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
            status, d = await _cmp_chat(s, payload)
            if status != 200 and "think" in str(d.get("error", "")).lower():
                payload.pop("think")
                status, d = await _cmp_chat(s, payload)
        motivo = json.loads((d.get("message") or {}).get("content") or "{}").get("motivo") or ""
    except Exception:
        return web.json_response({"error": "o modelo nao respondeu"}, status=502)
    motivo = re.sub(r"\s+", " ", motivo).strip()[:300]
    return web.json_response({"motivo": motivo or "O modelo nao soube explicar esta mudanca.", "fonte": "ia"})


async def h_docs_diff(request):
    """{a, b} -> {segs}: o que mudou entre duas versoes (a = antes)."""
    b = await _body_json(request)
    segs = await _run(_doc_mod("escrita").diff, str(b.get("a") or "")[:500000], str(b.get("b") or "")[:500000])
    return web.json_response({"segs": segs, "mudancas": sum(1 for x in segs if x["t"] == "~")})


async def h_docs_import(request):
    data = await request.read()
    nome = request.query.get("nome") or "arquivo.txt"
    try:
        texto, aviso = await _run(_doc_mod("textos").extrair, nome, data)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        print(f"[Nous][docs] importar {nome}: {e}", file=sys.stderr)
        return web.json_response({"error": "nao consegui ler este arquivo"}, status=400)
    return web.json_response({"titulo": os.path.splitext(os.path.basename(nome))[0][:120],
                              "texto": texto, "aviso": aviso})


async def h_docs_export(request):
    b = await _body_json(request)
    return await _exportar(str(b.get("titulo") or "Documento")[:120], str(b.get("texto") or ""),
                           str(b.get("formato") or ""))


async def h_research_export(request):
    rep = _report_mod()
    rid = request.query.get("id")
    md = rep.como_markdown(rid)
    if md is None:
        return web.json_response({"error": "relatorio nao encontrado"}, status=404)
    meta = next((r for r in rep.list_reports() if r.get("id") == rid), {})
    titulo = (meta.get("question") or "Pesquisa").strip()[:100]
    return await _exportar(titulo, md, request.query.get("formato") or "pdf")


def build_app():
    app = web.Application(middlewares=[cors_mw], client_max_size=_MAX_IMG + 1024)
    app.add_routes([web.get("/stats", h_stats),
                    web.post("/unload", h_unload),
                    web.get("/health", h_health),
                    web.get("/hardware", h_hardware),
                    web.get("/catalog", h_catalog),
                    web.get("/model/check", h_model_check),
                    web.get("/installed", h_installed),
                    web.post("/pull", h_pull),
                    web.get("/pull/status", h_pull_status),
                    web.get("/voice/status", h_voice_status),
                    web.post("/voice/install", h_voice_install),
                    web.post("/comfyui/start", h_comfyui_start),
                    web.get("/gallery", h_gallery),
                    web.get("/gallery/image/{id}", h_gallery_image),
                    web.post("/gallery/delete", h_gallery_delete),
                    web.post("/gallery/meta", h_gallery_meta),
                    web.get("/research", h_research_list),
                    web.get("/research/view", h_research_view),
                    web.post("/research/delete", h_research_delete),
                    web.post("/image/remove-bg", h_remove_bg),
                    web.get("/diag", h_diag),
                    web.post("/pdf/fields", h_pdf_fields),
                    web.post("/pdf/fill", h_pdf_fill),
                    web.post("/pdf/autofill", h_pdf_autofill),
                    web.get("/pdf/signature", h_pdf_sig_get),
                    web.post("/pdf/signature", h_pdf_sig_save),
                    web.post("/pdf/signature/delete", h_pdf_sig_delete),
                    web.post("/compare/run", h_compare_run),
                    web.post("/compare/vote", h_compare_vote),
                    web.get("/compare/score", h_compare_score),
                    web.post("/compare/reset", h_compare_reset),
                    web.get("/docs", h_docs_list),
                    web.get("/docs/get", h_docs_get),
                    web.get("/docs/version", h_docs_version),
                    web.post("/docs/save", h_docs_save),
                    web.post("/docs/delete", h_docs_delete),
                    web.post("/docs/ai", h_docs_ai),
                    web.post("/docs/porque", h_docs_porque),
                    web.post("/docs/diff", h_docs_diff),
                    web.post("/docs/import", h_docs_import),
                    web.post("/docs/export", h_docs_export),
                    web.get("/research/export", h_research_export)])
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=PORT, print=None)
