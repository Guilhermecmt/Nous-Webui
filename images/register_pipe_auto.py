# -*- coding: utf-8 -*-
"""
Instala/atualiza o Pipe 'Gerador de Imagem Local' DIRETO no banco do Open WebUI.
Sem credenciais, sem navegador, sem painel de admin.

Idempotente: pode rodar a cada inicializacao do Nous. Re-sincroniza o codigo
de nous_image_pipe.py (o arquivo em disco e' a fonte da verdade) e garante que
o Pipe continua ativo. O usuario so' precisa selecionalo no dropdown de modelos.

USO:
    python images/register_pipe_auto.py [--data-dir <DATA_DIR>] [--pipe <arquivo>]
"""
import os
import sys
import time
import json
import argparse
import sqlite3

FUNC_ID = "nous_image"
FUNC_NAME = "Gerador de Imagem Local"
DESC = (
    "Detecta pedidos de imagem e roteia ao ComfyUI/Flux.1 Schnell. "
    "Qualquer outra coisa vai ao Ollama. 100% local, sem assinatura."
)


def comfy_installed():
    """ComfyUI instalado? Checa os dois locais padrao: ComfyUI e o fork
    ComfyUI-Zluda (usado em GPUs AMD). Antes so' olhava ~/ComfyUI, entao o
    Pipe ficava inativo/escondido em maquinas com o ComfyUI-Zluda."""
    home = os.path.expanduser("~")
    for d in ("ComfyUI", "ComfyUI-Zluda"):
        if os.path.isfile(os.path.join(home, d, "main.py")):
            return True
    return False


def resolve_db(data_dir):
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
    try:
        from open_webui.env import DATABASE_URL
        if DATABASE_URL.startswith("sqlite") and ":///" in DATABASE_URL:
            p = DATABASE_URL.split(":///", 1)[1]
            if os.path.isfile(p):
                return p
    except Exception:
        pass
    return os.path.join(candidates[0], "webui.db") if candidates else None


def table_exists(cx, name):
    row = cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def pick_creator(cx):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--pipe", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "nous_image_pipe.py"))
    a = ap.parse_args()

    if not os.path.isfile(a.pipe):
        print(f"Pipe nao encontrado (ComfyUI nao instalado?): {a.pipe}")
        return  # nao e' erro: o usuario pode nao ter instalado as imagens

    content = open(a.pipe, encoding="utf-8").read()

    db = resolve_db(a.data_dir)
    if not db or not os.path.isfile(db):
        print("webui.db ainda nao existe (servidor nao iniciou). "
              "O Pipe sera registrado na proxima inicializacao.")
        return

    cx = sqlite3.connect(db, timeout=15)
    try:
        if not table_exists(cx, "function"):
            print("Tabela 'function' ainda nao criada pelo servidor. Tentarei no proximo boot.")
            return

        now = int(time.time())
        meta = json.dumps({"description": DESC, "manifest": {}})
        creator = pick_creator(cx)

        row = cx.execute(
            "SELECT user_id FROM function WHERE id=?", (FUNC_ID,)
        ).fetchone()

        # So' fica ATIVO (aparece no dropdown) se o ComfyUI estiver instalado.
        # Sem isso, o 'Gerador de Imagem Local' apareceria quebrado. Auto-cura:
        # instalou o ComfyUI depois -> proximo boot ativa; removeu -> desativa.
        active = 1 if comfy_installed() else 0

        if row:
            user_id = row[0]
            if (user_id in (None, "", "nous-system")) and creator != "nous-system":
                user_id = creator
            cx.execute(
                """UPDATE function
                   SET name=?, type='pipe', content=?, meta=?,
                       is_active=?, is_global=0, user_id=?, updated_at=?
                   WHERE id=?""",
                (FUNC_NAME, content, meta, active, user_id, now, FUNC_ID),
            )
            action = "atualizado"
        else:
            cx.execute(
                """INSERT INTO function
                   (id, user_id, name, type, content, meta, valves,
                    is_active, is_global, updated_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (FUNC_ID, creator, FUNC_NAME, "pipe", content, meta, None,
                 active, 0, now, now),
            )
            action = "instalado"

        cx.commit()
        estado = "ativo" if active else "inativo (instale o ComfyUI para ativar)"
        print(f"Pipe '{FUNC_NAME}' {action} - {estado} (id='{FUNC_ID}').")
    finally:
        cx.close()


if __name__ == "__main__":
    main()
