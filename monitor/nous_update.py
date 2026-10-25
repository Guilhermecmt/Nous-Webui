# -*- coding: utf-8 -*-
"""
Nous Monitor - rotas de atualizacao (app e modelos). Carregado pelo nous_monitor.py.

O trabalho de verdade e' do atualizacao/nous-atualizar.ps1 (PowerShell: continua
funcionando mesmo com o ambiente Python quebrado). Aqui so' se le o estado que
ele grava e se dispara o script - nunca se recebe endereco de download do navegador.

  GET  /update/status            -> { versao, verificar, estado:{disponivel, versao_nova, fase, ...} }
  POST /update/check             -> procura agora (ignora o limite de 1 vez por dia)
  POST /update/apply             -> aplica a versao nova (so' se o estado diz que ha uma)
  POST /update/config {verificar}-> liga/desliga a procura automatica
  POST /update/modelos/atualizar {model} -> baixa a versao nova de um modelo ja' instalado
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from aiohttp import web

_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_APP = Path(__file__).resolve().parent.parent
_SCRIPT = _APP / "atualizacao" / "nous-atualizar.ps1"
_procs = {}   # acao -> Popen (evita duas execucoes ao mesmo tempo)


def _ler(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _versao():
    try:
        return (_APP / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return None


def _rodando(acao):
    p = _procs.get(acao)
    return bool(p) and p.poll() is None


def _disparar(acao, data_dir, forcar=False):
    if _rodando(acao):
        return False
    if sys.platform != "win32" or not _SCRIPT.exists():
        return False
    args = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-File", str(_SCRIPT), "-Acao", acao, "-AppDir", str(_APP), "-DataDir", str(data_dir)]
    if forcar:
        args.append("-Forcar")
    _procs[acao] = subprocess.Popen(
        args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=_CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP, close_fds=True)
    return True


def add_routes(app, h_pull, extra_pullable, data_dir_fn):
    def estado_path():
        return data_dir_fn() / "atualizacao-estado.json"

    def cfg_path():
        return data_dir_fn() / "atualizacao-config.json"

    def verificar_ligado():
        c = _ler(cfg_path()) or {}
        return bool(c.get("verificar", True))

    async def h_status(request):
        est = _ler(estado_path()) or {}
        return web.json_response({"versao": _versao(), "verificar": verificar_ligado(), "estado": est,
                                  "ocupado": _rodando("Aplicar") or _rodando("Tudo")})

    async def h_check(request):
        return web.json_response({"started": _disparar("Tudo", data_dir_fn(), forcar=True)})

    async def h_apply(request):
        est = _ler(estado_path()) or {}
        if not est.get("disponivel"):
            return web.json_response({"started": False, "reason": "nao ha versao nova"}, status=400)
        if est.get("fase") in ("preparando", "baixando", "conferindo", "instalando", "reiniciando") and _rodando("Aplicar"):
            return web.json_response({"started": False, "reason": "em andamento"})
        return web.json_response({"started": _disparar("Aplicar", data_dir_fn())})

    async def h_config(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict) or not isinstance(body.get("verificar"), bool):
            return web.json_response({"ok": False, "reason": "informe verificar: true ou false"}, status=400)
        c = _ler(cfg_path()) or {}
        c["verificar"] = body["verificar"]
        cfg_path().parent.mkdir(parents=True, exist_ok=True)
        cfg_path().write_text(json.dumps(c, indent=2), encoding="utf-8")
        return web.json_response({"ok": True, "verificar": c["verificar"]})

    async def h_modelo(request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        nome = ((body or {}).get("model") or "").strip() if isinstance(body, dict) else ""
        novos = {m.get("nome") for m in ((_ler(estado_path()) or {}).get("modelos_novos") or []) if isinstance(m, dict)}
        if not nome or nome not in novos:
            return web.json_response({"started": False, "reason": "esse modelo nao esta na lista de atualizacoes"}, status=400)
        # Ja' esta instalado (veio do /api/tags): o /pull so' libera o que e' do catalogo ou conferido
        extra_pullable.add(nome)
        return await h_pull(request)

    app.add_routes([web.get("/update/status", h_status),
                    web.post("/update/check", h_check),
                    web.post("/update/apply", h_apply),
                    web.post("/update/config", h_config),
                    web.post("/update/modelos/atualizar", h_modelo)])
