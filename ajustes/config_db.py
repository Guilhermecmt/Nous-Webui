# -*- coding: utf-8 -*-
"""
Leitura e escrita das configuracoes do Open WebUI direto no webui.db, para os
register_*.py do Nous. Entende os dois formatos da tabela 'config':

  Open WebUI ate 0.9.x : uma linha so' (id, data, version, created_at,
                         updated_at) com tudo num JSON aninhado
  Open WebUI 0.10+     : uma linha por chave (key, value, updated_at), com o
                         caminho pontilhado como chave: "ui.default_locale",
                         "web.search.enable", "openai.api_configs" (este com o
                         dicionario inteiro no valor)

Os caminhos usados pelo Nous sao os mesmos nos dois formatos (so' a busca web
mudou de "rag.web.search.*" para "web.search.*"; ver caminho_busca_web). Assim
o mesmo script serve antes e depois da atualizacao, e tambem para voltar atras
se uma atualizacao for desfeita. O Open WebUI le a config direto do banco, sem
guardar copia na memoria, entao o que se grava aqui vale no proximo pedido.

USO (nos scripts vizinhos):
    sys.path.insert(0, os.path.join(HERE, "..", "ajustes"))
    from config_db import obter, definir, apagar, tem_config
"""
import json
import time
import datetime


def por_chave(cx):
    """True se a tabela config e' a nova (uma linha por chave)."""
    cols = {r[1] for r in cx.execute("PRAGMA table_info(config)")}
    return "key" in cols and "value" in cols


def _blob(cx):
    row = cx.execute("SELECT id, data FROM config ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None, {}
    try:
        data = json.loads(row[1]) if isinstance(row[1], str) else row[1]
    except Exception:
        data = {}
    return row[0], data if isinstance(data, dict) else {}


def _salvar_blob(cx, cid, data):
    # Colunas DATETIME do Open WebUI esperam string ISO, NAO epoch inteiro
    # (gravar int faz o servidor crashar no boot com fromisoformat).
    agora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = json.dumps(data, ensure_ascii=False)
    if cid is not None:
        cx.execute("UPDATE config SET data=?, updated_at=? WHERE id=?", (payload, agora, cid))
    else:
        cx.execute("INSERT INTO config (data, version, created_at, updated_at) VALUES (?,0,?,?)",
                   (payload, agora, agora))


def _no_blob(obj, caminho):
    for k in caminho.split("."):
        if isinstance(obj, dict) and k in obj:
            obj = obj[k]
        else:
            return False, None
    return True, obj


def tem_config(cx):
    """False enquanto o servidor ainda nao gravou nenhuma configuracao (1o boot)."""
    if por_chave(cx):
        return bool(cx.execute("SELECT 1 FROM config LIMIT 1").fetchone())
    return bool(_blob(cx)[1])


def obter(cx, caminho, padrao=None):
    if por_chave(cx):
        row = cx.execute("SELECT value FROM config WHERE key=?", (caminho,)).fetchone()
        if not row:
            return padrao
        try:
            return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception:
            return padrao
    achou, valor = _no_blob(_blob(cx)[1], caminho)
    return valor if achou else padrao


def definir(cx, valores):
    """Grava {caminho: valor}. Quem chama faz o commit."""
    if por_chave(cx):
        agora = int(time.time())
        for caminho, valor in valores.items():
            cx.execute(
                "INSERT INTO config (key, value, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (caminho, json.dumps(valor, ensure_ascii=False), agora))
        return
    cid, data = _blob(cx)
    for caminho, valor in valores.items():
        obj = data
        chaves = caminho.split(".")
        for k in chaves[:-1]:
            if not isinstance(obj.get(k), dict):
                obj[k] = {}
            obj = obj[k]
        obj[chaves[-1]] = valor
    _salvar_blob(cx, cid, data)


def apagar(cx, caminhos):
    """Remove as chaves (o Open WebUI volta ao padrao delas no proximo boot)."""
    if por_chave(cx):
        for caminho in caminhos:
            cx.execute("DELETE FROM config WHERE key=?", (caminho,))
        return
    cid, data = _blob(cx)
    for caminho in caminhos:
        obj = data
        chaves = caminho.split(".")
        for k in chaves[:-1]:
            obj = obj.get(k) if isinstance(obj, dict) else None
        if isinstance(obj, dict):
            obj.pop(chaves[-1], None)
    _salvar_blob(cx, cid, data)


def caminho_busca_web(cx):
    """Prefixo da busca web: "web.search" (0.10+) ou "rag.web.search" (antes)."""
    return "web.search" if por_chave(cx) else "rag.web.search"
