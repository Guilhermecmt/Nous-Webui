# -*- coding: utf-8 -*-
"""
Ajustes do Nous sobre os padroes do Open WebUI (0.9.6 a 0.12), gravados na tabela
config (os dois formatos dela; ver config_db.py).

Cada ajuste roda UMA vez por instalacao (marcador em NousData/.ajustes_nous.json):
se o admin mudar depois pelo painel, o Nous nao desfaz. Ajuste novo = versao nova
na lista abaixo.

  1  ui.default_locale = pt-BR (so' se estiver vazio)
  1  rag.youtube_loader_language = pt, pt-BR, en (o padrao 'en' pegava a legenda
     em ingles do video)
  1  calendar.enable / automations.enable = False: o Nous tem a Agenda propria
     (lembretes com aviso do Windows, iCal, tarefas). Duas agendas confundem.
  1  Embeddings de documentos do Open WebUI pelo Ollama com granite-embedding:278m
     (multilingue, o mesmo do resto do Nous) no lugar do all-MiniLM-L6-v2 (so'
     ingles), SO' se ainda nao ha nenhum arquivo/conhecimento indexado (trocar o
     modelo invalida os vetores antigos). Pelo Ollama e nao pelo sentence-
     transformers: o download do Hugging Face falha no Windows sem Modo de
     Desenvolvedor (WinError 1314, links simbolicos) e quebrava a busca.
  2  models.default_params.function_calling = legacy. A partir da 0.10 o Open
     WebUI usa "nativo" (o modelo decide chamar a busca web, os documentos...
     como ferramentas); modelos pequenos de PC nao chamam e a busca na web
     voltava sem fontes. "legacy" e' o comportamento de sempre: o Open WebUI
     faz a busca e poe o resultado no contexto. So' se o usuario nao escolheu.

Os mesmos valores vao como variavel de ambiente no launcher, para instalacoes
novas (onde a tabela config ainda nao tem a chave).

USO:
    python ajustes/register_ajustes.py [--data-dir <DATA_DIR>]
"""
import os
import sys
import json
import argparse
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "evaluation"))
from register_arena import _resolve_db  # noqa: E402
from config_db import obter, definir, tem_config, por_chave  # noqa: E402

NOUS_EMBED = "granite-embedding:278m"
OLD_EMBED = "sentence-transformers/all-MiniLM-L6-v2"


def _count(cx, table):
    try:
        return cx.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        return 0


def ajuste_1(cx, log):
    if not obter(cx, "ui.default_locale"):
        definir(cx, {"ui.default_locale": "pt-BR"})
        log.append("idioma padrao pt-BR")
    if obter(cx, "rag.youtube_loader_language") in (None, ["en"]):
        definir(cx, {"rag.youtube_loader_language": ["pt", "pt-BR", "en"]})
        log.append("legendas do YouTube em portugues")
    definir(cx, {"calendar.enable": False, "automations.enable": False})
    log.append("calendario/automacoes nativos escondidos (o Nous usa a Agenda propria)")
    engine = obter(cx, "rag.embedding_engine", "")
    model = obter(cx, "rag.embedding_model", OLD_EMBED)
    if engine in ("", None) and model in (OLD_EMBED, None):
        if _count(cx, "file") == 0 and _count(cx, "knowledge") == 0:
            definir(cx, {"rag.embedding_engine": "ollama", "rag.embedding_model": NOUS_EMBED})
            log.append("embeddings de documentos multilingues (granite pelo Ollama)")
        else:
            log.append("embeddings mantidos (ja ha documentos indexados)")


def ajuste_2(cx, log):
    # So' vale na tabela nova (0.10+). Antes da atualizacao o servidor guarda a
    # config inteira de memoria e apagaria a chave; o ajuste espera a atualizacao.
    if not por_chave(cx):
        return False
    params = obter(cx, "models.default_params")
    params = dict(params) if isinstance(params, dict) else {}
    if "function_calling" not in params:
        params["function_calling"] = "legacy"
        definir(cx, {"models.default_params": params})
        log.append("busca web e documentos pelo modo de sempre (legacy)")


AJUSTES = [(1, ajuste_1), (2, ajuste_2)]


def sem_novidades(cx):
    """O Open WebUI mostra as notas da versao, em ingles, ao administrador toda vez
    que a versao muda (settings.showChangelog, padrao ligado). O Nous e' quem
    atualiza e conta as novidades: grava showChangelog=false nas contas que ainda
    nao escolheram. Roda a cada inicio (conta nova tambem entra aqui)."""
    try:
        contas = cx.execute("SELECT id, settings FROM user").fetchall()
    except Exception:
        return
    for uid, raw in contas:
        try:
            s = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
        except Exception:
            continue
        if not isinstance(s, dict):
            s = {}
        ui = s.get("ui") if isinstance(s.get("ui"), dict) else {}
        if "showChangelog" in ui:
            continue
        ui["showChangelog"] = False
        s["ui"] = ui
        cx.execute("UPDATE user SET settings = ? WHERE id = ?", (json.dumps(s, ensure_ascii=False), uid))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    a = ap.parse_args()
    db = _resolve_db(a.data_dir)
    if not db or not os.path.isfile(db):
        print("webui.db ainda nao existe. Ajustes na proxima inicializacao.")
        return
    marker = os.path.join(os.path.dirname(db), ".ajustes_nous.json")
    try:
        done = json.load(open(marker, encoding="utf-8")).get("versao", 0)
    except Exception:
        done = 0
    pending = [(v, f) for v, f in AJUSTES if v > done]
    cx = sqlite3.connect(db, timeout=15)
    try:
        sem_novidades(cx)
        cx.commit()
        if not pending:
            return
        if not cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'").fetchone():
            print("Tabela 'config' ainda nao criada. Tentarei no proximo boot.")
            return
        if not tem_config(cx):
            print("Config ainda vazia (o servidor ainda nao gravou os padroes). Tentarei no proximo boot.")
            return
        log = []
        feito = done
        for v, f in pending:
            if f(cx, log) is False:   # ainda nao da' para aplicar: tenta de novo no proximo inicio
                break
            feito = v
        cx.commit()
    finally:
        cx.close()
    if feito == done:
        return
    with open(marker, "w", encoding="utf-8") as fh:
        json.dump({"versao": feito}, fh)
    if log:
        print("Ajustes do Nous: " + "; ".join(log) + ". Valem a partir do proximo inicio do Nous.")


if __name__ == "__main__":
    main()
