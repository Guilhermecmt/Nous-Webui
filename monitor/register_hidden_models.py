# -*- coding: utf-8 -*-
"""
Oculta modelos de EMBEDDING do seletor de modelos do chat.

Modelos como nomic-embed-text servem para busca semântica (RAG de arquivos,
histórico e memória) — não conversam. Mas o Open WebUI os lista no dropdown do
chat junto com os modelos de conversa; um usuário leigo seleciona, manda
mensagem e não recebe resposta nenhuma, sem entender por quê.

Mecanismo (confirmado em open_webui/utils/models.py, 0.9.6): se existir uma
linha na tabela `model` com o MESMO id de um modelo base do Ollama e
is_active = 0, o Open WebUI faz models.remove(...) e ele some do seletor.
O uso interno (API de embeddings) NÃO passa por essa lista, então a busca
semântica continua funcionando normalmente.

Idempotente: pode rodar a cada boot. Só age sobre modelos de embedding
realmente instalados; se um for removido do Ollama, a linha oculta é limpa.

USO:
    python monitor/register_hidden_models.py [--data-dir <DATA_DIR>]
"""
import os
import json
import time
import argparse
import sqlite3

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")

# Padrões que identificam um modelo de embedding (mesma lista usada na Loja,
# na Arena e no wizard do nous-loader.js).
_EMBED_PATTERNS = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-", "rerank")


def _embedding_models():
    """Tags de modelos de embedding instalados no Ollama (ex.: nomic-embed-text:latest)."""
    try:
        import requests
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        out = []
        for m in r.json().get("models", []):
            name = m.get("name", "")
            if name and any(p in name.lower() for p in _EMBED_PATTERNS):
                out.append(name)
        return out
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
    candidates.append(os.path.join(os.path.expanduser("~"), "NousData"))
    for d in candidates:
        p = os.path.join(d, "webui.db")
        if os.path.isfile(p):
            return p
    return None


def _table_exists(cx, name):
    return cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _pick_owner(cx):
    """user_id para a linha (o Open WebUI espera um dono). Admin > qualquer > sistema."""
    try:
        row = cx.execute(
            "SELECT id FROM user WHERE role='admin' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row:
            return row[0]
        row = cx.execute("SELECT id FROM user ORDER BY created_at LIMIT 1").fetchone()
        if row:
            return row[0]
    except Exception:
        pass
    return "nous-system"


def _hide_model(cx, model_id, owner, now):
    """Insere/atualiza uma linha override is_active=0 para ocultar o modelo do seletor."""
    meta = json.dumps({"hidden": True, "description": "Modelo de busca (uso interno do Nous)."})
    params = json.dumps({})
    row = cx.execute("SELECT id FROM model WHERE id=?", (model_id,)).fetchone()
    if row:
        cx.execute(
            "UPDATE model SET is_active=0, base_model_id=NULL, meta=?, updated_at=? WHERE id=?",
            (meta, now, model_id),
        )
    else:
        cx.execute(
            """INSERT INTO model
               (id, user_id, base_model_id, name, params, meta, is_active, updated_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (model_id, owner, None, model_id, params, meta, 0, now, now),
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()

    embeds = _embedding_models()
    db = _resolve_db(a.data_dir)
    if not db:
        print("[Nous] webui.db ainda não existe. Tentarei no próximo boot.")
        return

    cx = sqlite3.connect(db, timeout=15)
    try:
        if not _table_exists(cx, "model"):
            print("[Nous] Tabela 'model' ainda não criada. Tentarei no próximo boot.")
            return

        owner = _pick_owner(cx)
        now = int(time.time())

        if embeds:
            for mid in embeds:
                _hide_model(cx, mid, owner, now)
            cx.commit()
            print(f"[Nous] Modelos de embedding ocultados do seletor: {embeds}")
        else:
            print("[Nous] Nenhum modelo de embedding instalado — nada a ocultar.")
    finally:
        cx.close()


if __name__ == "__main__":
    main()
