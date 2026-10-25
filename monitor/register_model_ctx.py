# -*- coding: utf-8 -*-
"""
Define um num_ctx adequado para os modelos de chat — corrige resposta VAZIA
quando a busca web injeta muito contexto.

Problema (confirmado): o Ollama usa num_ctx=4096 por padrao. Quando a busca na
web injeta varias paginas (BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL=True manda
o conteudo inteiro pro prompt), o prompt estoura os 4096 tokens. O modelo
TRUNCA e devolve resposta vazia — a UI mostra "N fontes recuperadas" e nada
de texto. Os modelos do catalogo suportam contextos muito maiores (gemma4:12b
suporta 262k), so' falta o Open WebUI pedir uma janela maior.

Mecanismo (open_webui/utils/payload.py): o Open WebUI le model.params da
tabela `model` e aplica num_ctx as options da request Ollama. Este script
grava params.num_ctx para cada modelo de chat instalado.

NUM_CTX padrao = 16384: cabe a busca web tipica (~5 paginas) com folga sem
pesar demais em maquinas modestas. Ajustavel pela env NOUS_NUM_CTX (use 8192
em maquinas muito limitadas, 32768 se tiver 12+ GB de VRAM).

Idempotente: roda a cada boot, preserva outros params que o usuario tenha
definido e nao mexe em modelos de embedding.

USO:
    python monitor/register_model_ctx.py [--data-dir <DATA_DIR>]
"""
import os
import sys
import json
import time
import argparse
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ajustes"))
from config_db import obter, definir, tem_config, caminho_busca_web  # noqa: E402

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))
SYSTEM_PT = ("Você é o Nous, um assistente pessoal que roda no computador do usuário. "
             "Responda sempre em português do Brasil, a menos que o usuário peça outro idioma. "
             "Seja claro e direto.")

# Modelos de embedding nao recebem num_ctx de chat.
_EMBED_PATTERNS = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-", "rerank")


def _chat_models():
    """Tags de modelos de chat instalados (exclui embeddings)."""
    try:
        import requests
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        out = []
        for m in r.json().get("models", []):
            name = m.get("name", "")
            if name and not any(p in name.lower() for p in _EMBED_PATTERNS):
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


def _set_ctx(cx, model_id, owner, now):
    """Grava params.num_ctx para o modelo, preservando params e meta existentes."""
    row = cx.execute("SELECT params, meta, name, is_active FROM model WHERE id=?", (model_id,)).fetchone()
    if row:
        try:
            params = json.loads(row[0]) if row[0] else {}
        except Exception:
            params = {}
        if not isinstance(params, dict):
            params = {}
        changed = False
        # So' atualiza se faltar ou estiver menor — nao reduz um valor que o
        # usuario tenha aumentado de proposito.
        if int(params.get("num_ctx") or 0) < NUM_CTX:
            params["num_ctx"] = NUM_CTX
            changed = True
        # Sem prompt de sistema, modelos pequenos (qwen3:4b) respondem em ingles
        # a perguntas em portugues. So' preenche se o usuario nao definiu um.
        if "system" not in params:
            params["system"] = SYSTEM_PT
            changed = True
        if not changed:
            return False
        cx.execute(
            "UPDATE model SET params=?, updated_at=? WHERE id=?",
            (json.dumps(params), now, model_id),
        )
    else:
        params = {"num_ctx": NUM_CTX, "system": SYSTEM_PT}
        meta = json.dumps({})
        cx.execute(
            """INSERT INTO model
               (id, user_id, base_model_id, name, params, meta, is_active, updated_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (model_id, owner, None, model_id, json.dumps(params), meta, 1, now, now),
        )
    return True


# Quantas paginas a busca web injeta no prompt. Menos paginas = menos contexto
# = menor chance de estourar o num_ctx e deixar a resposta vazia. 3 cobre bem
# a maioria das perguntas. Ajustavel por NOUS_WEB_RESULTS.
WEB_RESULTS = int(os.environ.get("NOUS_WEB_RESULTS", "3"))
WEB_ENGINE = os.environ.get("WEB_SEARCH_ENGINE", "duckduckgo")


def _set_web_search(cx):
    """Garante a config COMPLETA de busca web no DB: enable=True, engine e
    result_count. Necessario porque ENABLE_PERSISTENT_CONFIG=True faz o Open
    WebUI ler do DB e ignorar as env vars do start-nous.ps1 apos o 1o boot.
    Sem enable/engine gravados, a busca web nao roda de forma confiavel
    (recupera 0 fontes ou cai no RAG de historico)."""
    if not _table_exists(cx, "config") or not tem_config(cx):
        return False
    # "web.search" a partir da 0.10, "rag.web.search" antes (config_db.py)
    base = caminho_busca_web(cx)
    desired = {
        base + ".enable": True,
        base + ".engine": WEB_ENGINE,
        base + ".result_count": WEB_RESULTS,
    }
    # so' escreve se algo estiver diferente (idempotente)
    if all(obter(cx, k) == v for k, v in desired.items()):
        return False
    definir(cx, desired)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()

    models = _chat_models()
    db = _resolve_db(a.data_dir)
    if not db:
        print("[Nous] webui.db ainda não existe. Tentarei no próximo boot.")
        return

    cx = sqlite3.connect(db, timeout=15)
    try:
        if not _table_exists(cx, "model"):
            print("[Nous] Tabela 'model' ainda não criada. Tentarei no próximo boot.")
            return
        if not models:
            print("[Nous] Nenhum modelo de chat instalado — nada a configurar.")
            return

        owner = _pick_owner(cx)
        now = int(time.time())
        changed = []
        for mid in models:
            if _set_ctx(cx, mid, owner, now):
                changed.append(mid)

        web_changed = _set_web_search(cx)
        cx.commit()

        if changed:
            print(f"[Nous] num_ctx={NUM_CTX} aplicado a: {changed}")
        else:
            print(f"[Nous] num_ctx já adequado (>= {NUM_CTX}) em todos os modelos.")
        if web_changed:
            print(f"[Nous] busca web configurada: enable=True, engine={WEB_ENGINE}, result_count={WEB_RESULTS}.")
    finally:
        cx.close()


if __name__ == "__main__":
    main()
