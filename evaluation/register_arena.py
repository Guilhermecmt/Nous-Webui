# -*- coding: utf-8 -*-
"""
Liga o 'Comparar Modelos (Nous)' via Arena do Open WebUI.

Regras:
- Só ativa se houver >= 2 modelos de CHAT instalados no Ollama
  (ignora modelos de embedding como nomic-embed-text).
- Idempotente: pode rodar a cada boot sem efeito colateral.
- Escreve em evaluation.arena.enable e evaluation.arena.models no webui.db.

USO:
    python evaluation/register_arena.py [--data-dir <DATA_DIR>]
"""
import json
import os
import sys
import argparse
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ajustes"))
from config_db import obter, definir, tem_config  # noqa: E402

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

# Modelos que não servem para comparação (embeddings / tools-only).
_EMBED_PATTERNS = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")

ARENA_MODEL_ID = "nous-compare"
ARENA_MODEL_NAME = "Comparar Modelos (Nous)"
ARENA_DESC = (
    "Envie a mesma pergunta para dois modelos e veja as respostas lado a lado — "
    "sem saber qual é qual. Vote no melhor antes de revelar os nomes."
)


def _chat_models() -> list[str]:
    """Retorna tags dos modelos de chat instalados no Ollama."""
    try:
        import requests
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        tags = r.json().get("models", [])
        names = []
        for m in tags:
            name = m.get("name", "")
            if not any(p in name.lower() for p in _EMBED_PATTERNS):
                names.append(name)
        return names
    except Exception:
        return []


def _resolve_db(data_dir):
    candidates = []
    if data_dir:
        candidates.append(data_dir)
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            candidates.append(v)
    for d in candidates:
        p = os.path.join(d, "webui.db")
        if os.path.isfile(p):
            return p
    return os.path.join(candidates[0], "webui.db") if candidates else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()

    chat_models = _chat_models()
    if len(chat_models) < 2:
        print(
            f"Comparar Modelos: apenas {len(chat_models)} modelo(s) de chat instalado(s) "
            f"— precisa de ≥ 2. Registrarei quando o 2º modelo for baixado."
        )
        # Desativar sem remover, para auto-cura funcionar no próximo boot.
        db = _resolve_db(a.data_dir)
        if db and os.path.isfile(db):
            cx = sqlite3.connect(db, timeout=15)
            try:
                if cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'").fetchone():
                    if obter(cx, "evaluation.arena.enable"):
                        definir(cx, {"evaluation.arena.enable": False})
                        cx.commit()
                        print("Arena desativado (< 2 modelos).")
            finally:
                cx.close()
        return

    db = _resolve_db(a.data_dir)
    if not db or not os.path.isfile(db):
        print("webui.db ainda não existe. Registrarei no próximo boot.")
        return

    cx = sqlite3.connect(db, timeout=15)
    try:
        if not cx.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='config'"
        ).fetchone():
            print("Tabela 'config' ainda não criada. Tentarei no próximo boot.")
            return

        if not tem_config(cx):
            print("Config vazia. Tentarei no próximo boot.")
            return

        # Arena model que aponta para os dois primeiros modelos de chat instalados.
        arena_model = {
            "id": ARENA_MODEL_ID,
            "name": ARENA_MODEL_NAME,
            "meta": {
                "profile_image_url": "/favicon.png",
                "description": ARENA_DESC,
                "model_ids": chat_models[:2],
            },
        }

        definir(cx, {"evaluation.arena.enable": True,
                     "evaluation.arena.models": [arena_model]})
        cx.commit()
        print(
            f"Comparar Modelos ativado com modelos: {chat_models[:2]} "
            f"(id='{ARENA_MODEL_ID}')."
        )
    finally:
        cx.close()


if __name__ == "__main__":
    main()
