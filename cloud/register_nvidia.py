# -*- coding: utf-8 -*-
"""
Registra (ou remove) a conexao NVIDIA NIM direto no banco do Open WebUI.
Sem credenciais de admin, sem navegador, sem servidor no ar.

Logica:
  - Chave presente em NousData\.nvidia_api_key  => garante a URL da NVIDIA
    em openai.api_base_urls + api_keys + api_configs (idempotente, nao mexe
    em outras conexoes que o usuario tenha criado).
  - Chave ausente ou vazia                      => remove a entrada da NVIDIA
    (limpeza reversa e segura).

Chamado pelo launcher a cada boot (Register-Cloud em start-nous.ps1).
Tambem chamado diretamente por ativar-nuvem.ps1 / desativar-nuvem.ps1.

USO:
    python cloud/register_nvidia.py [--data-dir <DATA_DIR>]
"""
import os
import sys
import json
import time
import datetime
import sqlite3
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ajustes"))
from config_db import obter, definir  # noqa: E402

NVIDIA_URL  = "https://integrate.api.nvidia.com/v1"
KEY_FILE    = ".nvidia_api_key"

# Modelos curados: bom balance entre qualidade, velocidade e diversidade.
# Edite conforme o catalogo atual em build.nvidia.com/models.
ALLOWLIST = [
    "deepseek-ai/deepseek-r1",
    "meta/llama-3.3-70b-instruct",
    "qwen/qwen3-235b-a22b-instruct-2507",
    "minimaxai/minimax-m1-40k",
    "moonshotai/kimi-k2-instruct",
]


# ------------------------------------------------------------------ helpers

def resolve_paths(data_dir):
    candidates = []
    if data_dir:
        candidates.append(data_dir)
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            candidates.append(v)
    candidates.append(os.path.join(os.path.expanduser("~"), "NousData"))
    return candidates


def resolve_db(candidates):
    for d in candidates:
        p = os.path.join(d, "webui.db")
        if os.path.isfile(p):
            return p
    try:
        from open_webui.env import DATABASE_URL
        if DATABASE_URL.startswith("sqlite") and ":///" in DATABASE_URL:
            p = DATABASE_URL.split(":///", 1)[1]
            if os.path.isfile(p):
                return p
    except Exception:
        pass
    return None


def read_key(candidates):
    for d in candidates:
        p = os.path.join(d, KEY_FILE)
        if os.path.isfile(p):
            k = open(p, encoding="utf-8").read().strip()
            if k:
                return k
    return None


def table_exists(cx, name):
    row = cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


# --------------------------------------------------- config read/write

# So' o trecho "openai" da config interessa; config_db.py cuida dos dois
# formatos da tabela (blob unico ate a 0.9, uma linha por chave a partir da 0.10).
OPENAI_KEYS = ("enable", "api_base_urls", "api_keys", "api_configs")


def read_config(cx):
    """Devolve {'openai': {enable, api_base_urls, api_keys, api_configs}}."""
    cfg = {}
    for k in OPENAI_KEYS:
        v = obter(cx, "openai." + k)
        if v is not None:
            cfg.setdefault("openai", {})[k] = v
    return cfg


def write_config(cx, data):
    openai_cfg = data.get("openai") or {}
    definir(cx, {"openai." + k: openai_cfg[k] for k in OPENAI_KEYS if k in openai_cfg})
    cx.commit()


# --------------------------------------------------- register / remove

def register(cx, api_key):
    """Garante que NVIDIA_URL esta em api_base_urls com a chave correta."""
    cfg = read_config(cx)
    openai_cfg = cfg.setdefault("openai", {})

    urls  = list(openai_cfg.get("api_base_urls") or [])
    keys  = list(openai_cfg.get("api_keys") or [])
    confs = dict(openai_cfg.get("api_configs") or {})

    # Garantir arrays paralelos do mesmo tamanho
    while len(keys)  < len(urls): keys.append("")
    while len(urls)  < len(keys): urls.append("")

    # Verificar se ja existe (busca por URL)
    idx = None
    for i, u in enumerate(urls):
        if u == NVIDIA_URL:
            idx = i
            break

    if idx is None:
        idx = len(urls)
        urls.append(NVIDIA_URL)
        keys.append(api_key)
    else:
        keys[idx] = api_key  # atualiza a chave se mudou

    # Garantir que api_configs tem entrada para esse indice
    str_idx = str(idx)
    existing = confs.get(str_idx, {})
    confs[str_idx] = {
        "enable": True,
        "model_ids": ALLOWLIST,
        "connection_type": "external",
        "prefix_id": None,
        "tags": [],
        "provider": "nvidia",
        "azure": False,
        "api_type": "openai",
        "auth_type": "bearer",
        "api_version": "",
        "headers": {},
        # preservar campos extras que o usuario possa ter adicionado
        **{k: v for k, v in existing.items()
           if k not in ("enable", "model_ids", "connection_type", "provider",
                        "azure", "api_type", "auth_type", "api_version", "headers")},
    }

    openai_cfg["enable"] = True
    openai_cfg["api_base_urls"] = urls
    openai_cfg["api_keys"]      = keys
    openai_cfg["api_configs"]   = confs
    cfg["openai"] = openai_cfg

    write_config(cx, cfg)
    print(f"[Nous] NVIDIA NIM registrada (indice {idx}, {len(ALLOWLIST)} modelos).")


def remove(cx):
    """Remove a entrada da NVIDIA de api_base_urls/api_keys/api_configs."""
    cfg = read_config(cx)
    openai_cfg = cfg.get("openai", {})

    urls  = list(openai_cfg.get("api_base_urls") or [])
    keys  = list(openai_cfg.get("api_keys") or [])
    confs = dict(openai_cfg.get("api_configs") or {})

    idx = None
    for i, u in enumerate(urls):
        if u == NVIDIA_URL:
            idx = i
            break

    if idx is None:
        print("[Nous] NVIDIA NIM nao estava registrada. Nada a fazer.")
        return

    urls.pop(idx)
    if idx < len(keys):
        keys.pop(idx)

    # Reconstruir api_configs sem o indice removido e reindexar
    new_confs = {}
    for i, u in enumerate(urls):
        old_key = str(i if i < idx else i + 1)
        if old_key in confs:
            new_confs[str(i)] = confs[old_key]

    openai_cfg["api_base_urls"] = urls
    openai_cfg["api_keys"]      = keys
    openai_cfg["api_configs"]   = new_confs
    cfg["openai"] = openai_cfg

    write_config(cx, cfg)
    print("[Nous] NVIDIA NIM removida da configuracao.")


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()

    candidates = resolve_paths(a.data_dir)
    api_key    = read_key(candidates)

    db = resolve_db(candidates)
    if not db:
        print("[Nous] webui.db nao encontrado (servidor ainda nao iniciou). "
              "Tentarei no proximo boot.")
        return

    cx = sqlite3.connect(db, timeout=15)
    try:
        if not table_exists(cx, "config"):
            print("[Nous] Tabela 'config' ainda nao criada. Tentarei no proximo boot.")
            return

        if api_key:
            register(cx, api_key)
        else:
            remove(cx)
    finally:
        cx.close()


if __name__ == "__main__":
    main()
