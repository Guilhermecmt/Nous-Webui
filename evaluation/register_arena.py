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
import argparse
import sqlite3

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


def _read_config(cx):
    row = cx.execute("SELECT data FROM config LIMIT 1").fetchone()
    if row:
        return json.loads(row[0])
    return {}


def _write_config(cx, data):
    cx.execute("UPDATE config SET data=?", (json.dumps(data, ensure_ascii=False),))


def _set_nested(obj, path: str, value):
    """Escreve value em obj seguindo o caminho dot-separated, criando dicts conforme necessário."""
    keys = path.split(".")
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    obj[keys[-1]] = value


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
                    data = _read_config(cx)
                    arena = data.get("evaluation", {}).get("arena", {})
                    if arena.get("enable"):
                        _set_nested(data, "evaluation.arena.enable", False)
                        _write_config(cx, data)
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

        data = _read_config(cx)
        if not data:
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

        _set_nested(data, "evaluation.arena.enable", True)
        _set_nested(data, "evaluation.arena.models", [arena_model])
        _write_config(cx, data)
        cx.commit()
        print(
            f"Comparar Modelos ativado com modelos: {chat_models[:2]} "
            f"(id='{ARENA_MODEL_ID}')."
        )
    finally:
        cx.close()


if __name__ == "__main__":
    main()
