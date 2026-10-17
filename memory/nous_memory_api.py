# -*- coding: utf-8 -*-
"""
Nous Memory API — micro-servico REST para gerenciar memorias e personas.

Porta 8993 (CORS liberado p/ o navegador em localhost:8080).

Memorias:
  GET  /memories?user_id=...&persona=...  lista memorias do usuario
  POST /memories                          { user_id, text, persona? } -> adiciona
  PUT  /memories/{id}                     { user_id, text }           -> edita texto
  DELETE /memories/{id}?user_id=...       deleta memoria
  POST /memories/{id}/pin                 { user_id, pinned } -> fixa (entra em toda conversa)
  POST /memories/tidy                     { user_id, persona? } -> PROPOE juntar repetidas/contradicoes
  POST /memories/tidy/apply               { user_id, grupos:[{ids, texto}] } -> aplica o que o usuario aprovou
  GET  /memories/export?user_id=...       todas as memorias em JSON (backup / levar para outro PC)
  POST /memories/import/extract?user_id=&nome=   corpo = arquivo (.txt .md .docx .pdf .html .json)
                                          ou JSON {user_id, texto}: PROPOE fatos (o usuario escolhe)
  POST /memories/import/apply             { user_id, persona?, fatos:[{text, pinned?}] } -> salva os escolhidos

Personas:
  GET  /personas                          dicionario de todas as personas
  GET  /persona?user_id=...               persona ativa do usuario
  POST /persona                           { user_id, name } -> muda persona ativa
  POST /persona/config                    { name, folder?, description? } -> cria/edita
  DELETE /persona/{name}                  deleta persona (nunca 'default')

GET /health
"""
import os
import re
import json
import time
import sqlite3
import urllib.parse
from aiohttp import web

PORT        = 8993
DB_NAME     = "nous_memory.sqlite3"
ACTIVE_FILE = "nous_active_persona.json"
CONFIG_FILE = "nous_personas.json"
FILES_CFG   = "nous_files.json"


def _data_dir():
    for v in (os.environ.get("DATA_DIR"), os.environ.get("NOUS_DATA_DIR")):
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def _db():
    return os.path.join(_data_dir(), DB_NAME)


def _normalize(s):
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[.;:!?]+$", "", s)
    return s


def _read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f) or (default if default is not None else {})
    except Exception:
        return default if default is not None else {}


def _write_json(path, data):
    # Escrita ATOMICA: grava em .tmp e troca de uma vez. Sem isto, o leitor
    # (Open WebUI / indexador) pode pegar um JSON truncado no meio da escrita.
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---- personas ---------------------------------------------------------------

def _active_path():  return os.path.join(_data_dir(), ACTIVE_FILE)
def _config_path():  return os.path.join(_data_dir(), CONFIG_FILE)
def _files_path():   return os.path.join(_data_dir(), FILES_CFG)


def get_active_persona(user_id):
    return _read_json(_active_path(), {}).get(user_id, "default")


def set_active_persona(user_id, persona):
    data = _read_json(_active_path(), {})
    data[user_id] = persona
    _write_json(_active_path(), data)
    _sync_files_folder(persona)


def _sync_files_folder(persona):
    """Atualiza nous_files.json com a pasta da persona ativa (sem sobrescrever se vazio)."""
    folder = get_personas().get(persona, {}).get("folder", "")
    if not folder:
        return
    cfg = _read_json(_files_path(), {})
    if cfg.get("folder") != folder:
        cfg["folder"] = folder
        _write_json(_files_path(), cfg)


def get_personas():
    data = _read_json(_config_path(), {})
    if "default" not in data:
        data["default"] = {"description": "Modo padrao", "folder": ""}
    return data


def upsert_persona(name, description, folder):
    data = get_personas()
    data[name] = {"description": description, "folder": folder}
    _write_json(_config_path(), data)


def remove_persona(name):
    if name == "default":
        return False
    data = get_personas()
    data.pop(name, None)
    _write_json(_config_path(), data)
    return True


# ---- memorias ---------------------------------------------------------------

def _conn():
    db = _db()
    if not os.path.isfile(db):
        return None
    cx = sqlite3.connect(db, timeout=10)
    return cx


def list_memories(user_id, persona=None):
    cx = _conn()
    if cx is None:
        return []
    try:
        cols = {r[1] for r in cx.execute("PRAGMA table_info(memories)").fetchall()}
        pin = "COALESCE(pinned, 0)" if "pinned" in cols else "0"
        order = f"ORDER BY {pin} DESC, created_at DESC"
        if "persona" in cols:
            if persona and persona != "all":
                rows = cx.execute(
                    f"SELECT id, text, persona, created_at, {pin} FROM memories "
                    "WHERE user_id=? AND (persona=? OR persona IS NULL) " + order,
                    (user_id, persona),
                ).fetchall()
            else:
                rows = cx.execute(
                    f"SELECT id, text, persona, created_at, {pin} FROM memories "
                    "WHERE user_id=? " + order,
                    (user_id,),
                ).fetchall()
        else:
            rows = cx.execute(
                "SELECT id, text, 'default', created_at, 0 FROM memories "
                "WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [{"id": r[0], "text": r[1], "persona": r[2] or "default", "created_at": r[3],
                 "pinned": bool(r[4])} for r in rows]
    finally:
        cx.close()


def set_pinned(mem_id, user_id, pinned):
    cx = _conn()
    if cx is None:
        return False
    try:
        try:
            cx.execute("ALTER TABLE memories ADD COLUMN pinned INTEGER DEFAULT 0")
        except Exception:
            pass
        cx.execute("UPDATE memories SET pinned=? WHERE id=? AND user_id=?",
                   (1 if pinned else 0, mem_id, user_id))
        cx.commit()
        return cx.execute("SELECT changes()").fetchone()[0] > 0
    finally:
        cx.close()


# ---- faxina: o modelo PROPOE juntar repetidas/contraditorias; o usuario aprova ----

OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
NUM_CTX = int(os.environ.get("NOUS_NUM_CTX", "16384"))
_EMBED = ("embed", "nomic", "minilm", "bge-", "e5-", "gte-")
EMBED_MODEL = os.environ.get("NOUS_EMBED_MODEL", "granite-embedding:278m")
PAIR_MIN_SIM = 0.72   # granite: repetidas >= 0.80; contradicoes caem em ~0.74
MAX_PAIRS = 30
_PAIR_SCHEMA = {
    "type": "object", "required": ["relacao", "texto_final"],
    "properties": {"relacao": {"type": "string", "enum": ["mesma_coisa", "contradicao", "diferentes"]},
                   "texto_final": {"type": "string"}},
}
_PAIR_PROMPT = """Duas memorias sobre o mesmo usuario. A e' a mais antiga, B a mais recente.
A: {a}
B: {b}

Classifique:
- "mesma_coisa": dizem o mesmo fato com outras palavras (texto_final = uma frase juntando as duas)
- "contradicao": nao podem ser verdade ao mesmo tempo (texto_final = o fato de B, o mais recente)
- "diferentes": sao fatos diferentes, mesmo que parecidos (texto_final = "")

texto_final e' uma frase completa, no mesmo estilo das memorias.

Exemplos:
"O usuario gosta de cafe sem acucar" / "O usuario adora cafe puro, sem acucar" -> mesma_coisa,
  texto_final "O usuario gosta de cafe puro, sem acucar"
"O usuario mora em Curitiba" / "O usuario se mudou para Florianopolis" -> contradicao,
  texto_final "O usuario mora em Florianopolis"
"O usuario leu o livro 1 da serie" / "O usuario leu o livro 2 da serie" -> diferentes
"O usuario mora em Curitiba" / "O usuario torce para o Coritiba" -> diferentes
Responda so' com JSON."""


def _local_model():
    import requests
    try:
        for m in requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", []):
            n = m.get("name", "")
            if "/" not in n and not any(p in n.lower() for p in _EMBED):
                return n
    except Exception:
        pass
    return None


def tidy_propose(user_id, persona=None):
    """Duas etapas: embeddings escolhem os PARES parecidos; o modelo julga um par
    por vez. Mandar a lista inteira fazia um modelo de 4B juntar tudo numa frase."""
    import requests
    import numpy as np
    mems = sorted(list_memories(user_id, persona)[:200], key=lambda m: m["id"])
    if len(mems) < 2:
        return []
    model = _local_model()
    if not model:
        raise RuntimeError("nenhum modelo de conversa instalado")
    r = requests.post(f"{OLLAMA_URL}/api/embed",
                      json={"model": EMBED_MODEL, "input": [m["text"] for m in mems]}, timeout=120)
    r.raise_for_status()
    a = np.asarray(r.json()["embeddings"], dtype="float32")
    a /= np.linalg.norm(a, axis=1, keepdims=True)
    sims = a @ a.T
    # "leu o livro 1" x "leu o livro 2": so' os numeros mudam = fatos diferentes.
    # Sem este corte, uma serie de 26 livros gerava 325 pares e esgotava o limite.
    shape = [re.sub(r"\d+", "#", _normalize(m["text"])) for m in mems]
    pairs = [(float(sims[i, j]), i, j) for i in range(len(mems)) for j in range(i + 1, len(mems))
             if sims[i, j] >= PAIR_MIN_SIM and shape[i] != shape[j]]
    pairs.sort(reverse=True)
    out, used = [], set()
    for _s, i, j in pairs[:MAX_PAIRS]:
        if i in used or j in used:
            continue
        resp = requests.post(f"{OLLAMA_URL}/api/generate",
                             json={"model": model, "stream": False, "think": False, "format": _PAIR_SCHEMA,
                                   "prompt": _PAIR_PROMPT.format(a=mems[i]["text"], b=mems[j]["text"]),
                                   "options": {"temperature": 0, "num_ctx": NUM_CTX}}, timeout=120)
        d = json.loads(resp.json().get("response") or "{}")
        rel, texto = d.get("relacao"), (d.get("texto_final") or "").strip()
        if rel in ("mesma_coisa", "contradicao") and texto:
            used.update((i, j))
            out.append({"ids": [mems[i]["id"], mems[j]["id"]], "texto": texto,
                        "motivo": "contradicao" if rel == "contradicao" else "repetida",
                        "antes": [mems[i]["text"], mems[j]["text"]]})
    return out


def tidy_apply(user_id, grupos):
    cx = _conn()
    if cx is None:
        return 0
    n = 0
    try:
        for g in grupos:
            ids = [int(i) for i in g.get("ids") or []]
            texto = (g.get("texto") or "").strip()
            if len(ids) < 2 or not texto:
                continue
            q = ",".join("?" * len(ids))
            rows = cx.execute(f"SELECT persona, COALESCE(pinned, 0) FROM memories "
                              f"WHERE user_id=? AND id IN ({q})", (user_id, *ids)).fetchall()
            if len(rows) != len(ids):
                continue  # alguma ja' foi apagada/editada: nao mexe
            cx.execute(f"DELETE FROM memories WHERE user_id=? AND id IN ({q})", (user_id, *ids))
            cx.execute("INSERT INTO memories(user_id, text, norm, created_at, persona, pinned) "
                       "VALUES(?,?,?,?,?,?)",
                       (user_id, texto, _normalize(texto), int(time.time()),
                        rows[0][0] or "default", max(r[1] for r in rows)))
            n += 1
        cx.commit()
        return n
    finally:
        cx.close()


# ---- importar / exportar (v2.9) ---------------------------------------------
# Importar: o modelo PROPOE fatos tirados de um arquivo (curriculo, "sobre mim",
# memorias copiadas do ChatGPT...) e o usuario marca quais guardar. Um backup
# do proprio Nous (JSON exportado) volta direto, sem passar pelo modelo.

IMPORT_CHUNK = 6000      # caracteres por pedido ao modelo
IMPORT_MAX_CHUNKS = 8    # ~48 mil caracteres (umas 15 paginas); o resto e' avisado
_FACTS_SCHEMA = {"type": "object", "required": ["fatos"],
                 "properties": {"fatos": {"type": "array", "items": {"type": "string"}}}}
_IMPORT_PROMPT = """Este texto foi escrito pelo usuario ou e' sobre ele (curriculo, apresentacao,
anotacoes pessoais, memorias de outro assistente). Extraia o que vale a pena LEMBRAR sobre o
usuario em conversas futuras: nome, onde mora, trabalho e formacao, familia, gostos, metas,
restricoes (saude, alimentacao), jeito de escrever e preferencias.

Regras:
- comece pelo nome do usuario, se aparecer ("O usuario se chama ...");
- se o texto ja' for uma lista de fatos (memorias de outro assistente, mesmo em ingles),
  traduza CADA linha para uma frase (ex.: "Prefers concise answers" -> "O usuario prefere respostas curtas");
- uma frase curta e COMPLETA por fato, em portugues, comecando com "O usuario" (ex.: "O usuario mora em Recife");
  nunca termine com "...";
- dado de outra pessoa fica na frase dela: "A filha do usuario, Lia, tem 6 anos" (e nao "O usuario tem 6 anos");
- como o usuario quer as respostas tambem conta: "O usuario prefere respostas curtas";
- so' o que o texto diz; nada de suposicoes; nada de fatos gerais do mundo;
- no maximo 25 fatos; se nao houver nada pessoal, devolva a lista vazia.

TEXTO:
<<<
{texto}
>>>

Responda so' com JSON: {{"fatos": [...]}}"""


def export_memories(user_id):
    return {"app": "Nous", "tipo": "memorias", "versao": 1,
            "exportado_em": time.strftime("%Y-%m-%d %H:%M"),
            "memorias": [{"text": m["text"], "persona": m["persona"], "pinned": m["pinned"],
                          "created_at": m["created_at"]} for m in list_memories(user_id, "all")]}


def _textos_mod():
    import sys
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "documentos")
    if p not in sys.path:
        sys.path.insert(0, p)
    import textos
    return textos


def _chunks(texto):
    """Pedacos de ate' IMPORT_CHUNK, cortando em fim de paragrafo quando da'."""
    out, i = [], 0
    while i < len(texto) and len(out) < IMPORT_MAX_CHUNKS:
        fim = min(len(texto), i + IMPORT_CHUNK)
        if fim < len(texto):
            corte = texto.rfind("\n", i + IMPORT_CHUNK // 2, fim)
            fim = corte if corte > 0 else fim
        out.append(texto[i:fim])
        i = fim
    return out, i < len(texto)


def import_extract(user_id, nome=None, dados=None, texto=None):
    """{fatos:[{text, pinned, persona?, ja}], truncado, origem}. Nao grava nada."""
    import requests
    existentes = {_normalize(m["text"]) for m in list_memories(user_id, "all")}
    if dados is not None and (nome or "").lower().endswith(".json"):
        try:
            d = json.loads(dados.decode("utf-8-sig"))
        except Exception:
            d = None
        if isinstance(d, dict) and d.get("tipo") == "memorias" and isinstance(d.get("memorias"), list):
            fatos = []
            for m in d["memorias"][:2000]:
                t = str((m or {}).get("text") or "").strip()[:500]
                if t:
                    fatos.append({"text": t, "pinned": bool(m.get("pinned")), "persona": str(m.get("persona") or "default")[:60],
                                  "ja": _normalize(t) in existentes})
            return {"fatos": fatos, "truncado": False, "origem": "backup"}
    if texto is None:
        texto, aviso = _textos_mod().extrair(nome, dados)
        if not texto:
            raise ValueError(aviso or "o arquivo nao tem texto")
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("nada para ler")
    model = _local_model()
    if not model:
        raise RuntimeError("nenhum modelo de conversa instalado")
    partes, truncado = _chunks(texto)
    fatos, vistos = [], set()
    for parte in partes:
        r = requests.post(f"{OLLAMA_URL}/api/generate", timeout=240,
                          json={"model": model, "stream": False, "think": False, "format": _FACTS_SCHEMA,
                                "prompt": _IMPORT_PROMPT.format(texto=parte), "keep_alive": "5m",
                                "options": {"temperature": 0, "num_ctx": NUM_CTX}})
        try:
            lista = json.loads(r.json().get("response") or "{}").get("fatos") or []
        except Exception:
            lista = []
        for f in lista:
            f = re.sub(r"\s+", " ", str(f)).strip()[:300]
            n = _normalize(f)
            # "O usuario se chama ..." = o modelo preencheu o molde sem ter o dado
            if len(f) < 8 or n in vistos or "..." in f or "…" in f:
                continue
            vistos.add(n)
            fatos.append({"text": f, "pinned": False, "ja": n in existentes})
    return {"fatos": fatos, "truncado": truncado, "origem": "modelo"}


def import_apply(user_id, persona, fatos):
    n = 0
    for f in fatos[:2000]:
        t = str((f or {}).get("text") or "").strip()[:500]
        if not t:
            continue
        mid = add_memory(user_id, t, str(f.get("persona") or persona or "default")[:60])
        if mid is None:
            continue  # repetida
        n += 1
        if f.get("pinned"):
            set_pinned(mid, user_id, True)
    return n


def add_memory(user_id, text, persona="default"):
    db = _db()
    if not os.path.isfile(db):
        return None
    cx = sqlite3.connect(db, timeout=10)
    try:
        cols = {r[1] for r in cx.execute("PRAGMA table_info(memories)").fetchall()}
        norm = _normalize(text)
        if "persona" in cols:
            if cx.execute(
                "SELECT id FROM memories WHERE user_id=? AND norm=? AND (persona=? OR persona IS NULL)",
                (user_id, norm, persona),
            ).fetchone():
                return None
            cur = cx.execute(
                "INSERT INTO memories(user_id, text, norm, created_at, persona) VALUES(?,?,?,?,?)",
                (user_id, text, norm, int(time.time()), persona),
            )
        else:
            if cx.execute(
                "SELECT id FROM memories WHERE user_id=? AND norm=?", (user_id, norm)
            ).fetchone():
                return None
            cur = cx.execute(
                "INSERT INTO memories(user_id, text, norm, created_at) VALUES(?,?,?,?)",
                (user_id, text, norm, int(time.time())),
            )
        cx.commit()
        return cur.lastrowid
    finally:
        cx.close()


def edit_memory(mem_id, user_id, text):
    cx = _conn()
    if cx is None:
        return False
    try:
        norm = _normalize(text)
        cx.execute(
            "UPDATE memories SET text=?, norm=? WHERE id=? AND user_id=?",
            (text, norm, mem_id, user_id),
        )
        cx.commit()
        changed = cx.execute("SELECT changes()").fetchone()[0]
        return changed > 0
    finally:
        cx.close()


def delete_memory(mem_id, user_id):
    cx = _conn()
    if cx is None:
        return False
    try:
        cx.execute("DELETE FROM memories WHERE id=? AND user_id=?", (mem_id, user_id))
        cx.commit()
        changed = cx.execute("SELECT changes()").fetchone()[0]
        return changed > 0
    finally:
        cx.close()


# ---- handlers ---------------------------------------------------------------

async def _json_body(request):
    """Le o corpo JSON com tolerancia: retorna None se nao for JSON valido."""
    try:
        return await request.json()
    except Exception:
        return None


async def h_health(request):
    return web.json_response({"ok": True})


async def h_list(request):
    uid = request.rel_url.query.get("user_id")
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    persona = request.rel_url.query.get("persona")
    return web.json_response(list_memories(uid, persona))


async def h_add(request):
    body = await _json_body(request)
    if body is None:
        return web.json_response({"error": "invalid json"}, status=400)
    uid  = body.get("user_id")
    text = (body.get("text") or "").strip()
    if not uid or not text:
        return web.json_response({"error": "user_id and text required"}, status=400)
    mid = add_memory(uid, text, body.get("persona", "default"))
    if mid is None:
        return web.json_response({"ok": False, "reason": "duplicate"})
    return web.json_response({"ok": True, "id": mid})


async def h_edit(request):
    try:
        mid = int(request.match_info["id"])
    except Exception:
        return web.json_response({"error": "invalid id"}, status=400)
    body = await _json_body(request)
    if body is None:
        return web.json_response({"error": "invalid json"}, status=400)
    uid  = body.get("user_id")
    text = (body.get("text") or "").strip()
    if not uid or not text:
        return web.json_response({"error": "user_id and text required"}, status=400)
    return web.json_response({"ok": edit_memory(mid, uid, text)})


async def h_delete(request):
    try:
        mid = int(request.match_info["id"])
    except Exception:
        return web.json_response({"error": "invalid id"}, status=400)
    uid = request.rel_url.query.get("user_id")
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    return web.json_response({"ok": delete_memory(mid, uid)})


async def h_pin(request):
    try:
        mid = int(request.match_info["id"])
    except Exception:
        return web.json_response({"error": "invalid id"}, status=400)
    body = await _json_body(request) or {}
    uid = body.get("user_id")
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    return web.json_response({"ok": set_pinned(mid, uid, bool(body.get("pinned")))})


async def h_tidy(request):
    body = await _json_body(request) or {}
    uid = body.get("user_id")
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    import asyncio
    try:
        grupos = await asyncio.get_event_loop().run_in_executor(
            None, tidy_propose, uid, body.get("persona"))
    except Exception as e:
        msg = str(e) if "modelo" in str(e) else "O modelo nao respondeu. Tente de novo."
        return web.json_response({"error": msg}, status=502)
    return web.json_response({"grupos": grupos})


async def h_tidy_apply(request):
    body = await _json_body(request) or {}
    uid = body.get("user_id")
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    return web.json_response({"ok": True, "aplicados": tidy_apply(uid, body.get("grupos") or [])})


async def h_export(request):
    uid = request.rel_url.query.get("user_id")
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    data = json.dumps(export_memories(uid), ensure_ascii=False, indent=1).encode("utf-8")
    return web.Response(body=data, content_type="application/json", charset="utf-8", headers={
        "Content-Disposition": 'attachment; filename="memorias-nous-%s.json"' % time.strftime("%Y-%m-%d")})


async def h_import_extract(request):
    import asyncio
    q = request.rel_url.query
    if (request.content_type or "").startswith("application/json"):
        body = await _json_body(request) or {}
        uid, nome, dados, texto = body.get("user_id"), None, None, str(body.get("texto") or "")[:200000]
    else:
        uid, nome, dados, texto = q.get("user_id"), q.get("nome") or "arquivo.txt", await request.read(), None
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    try:
        res = await asyncio.get_event_loop().run_in_executor(None, import_extract, uid, nome, dados, texto)
    except ValueError as e:
        return web.json_response({"error": str(e)}, status=400)
    except Exception as e:
        print(f"[Nous][memoria] importar: {e}")
        msg = str(e) if "modelo" in str(e) else "O modelo nao respondeu. Tente de novo."
        return web.json_response({"error": msg}, status=502)
    return web.json_response(res)


async def h_import_apply(request):
    body = await _json_body(request) or {}
    uid = body.get("user_id")
    if not uid:
        return web.json_response({"error": "user_id required"}, status=400)
    n = import_apply(uid, body.get("persona") or "default", body.get("fatos") or [])
    return web.json_response({"ok": True, "salvas": n})


async def h_personas(request):
    return web.json_response(get_personas())


async def h_get_active(request):
    uid = request.rel_url.query.get("user_id", "default")
    return web.json_response({"persona": get_active_persona(uid)})


async def h_set_active(request):
    body = await _json_body(request)
    if body is None:
        return web.json_response({"error": "invalid json"}, status=400)
    uid  = body.get("user_id", "default")
    name = (body.get("name") or body.get("persona") or "default").strip()
    set_active_persona(uid, name)
    return web.json_response({"ok": True, "persona": name})


async def h_save_persona(request):
    body = await _json_body(request)
    if body is None:
        return web.json_response({"error": "invalid json"}, status=400)
    name = (body.get("name") or "").strip()
    if not name:
        return web.json_response({"error": "name required"}, status=400)
    upsert_persona(name, body.get("description", ""), body.get("folder", ""))
    return web.json_response({"ok": True})


async def h_del_persona(request):
    name = request.match_info["name"]
    if name == "default":
        return web.json_response({"error": "cannot delete default"}, status=400)
    return web.json_response({"ok": remove_persona(name)})


# ---- CORS / origem ----------------------------------------------------------
# A API mexe em dados do usuario (memorias, pasta indexada). Com CORS '*' qualquer
# site aberto no navegador poderia chama-la (CSRF local) e, p.ex., apontar a pasta
# de arquivos para C:\Users\... exfiltrando dados via contexto do chat. Por isso so'
# aceitamos chamadas de origem local (o proprio Nous em localhost) — e refletimos
# exatamente essa origem em vez de '*'. Ferramentas locais (curl, sem header Origin)
# continuam funcionando.

def _origin_ok(origin):
    if not origin:
        return True   # sem Origin = nao e' fetch de navegador (curl/servico local)
    try:
        host = urllib.parse.urlparse(origin).hostname
    except Exception:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _cors_headers(origin):
    return {
        "Access-Control-Allow-Origin":  origin if (origin and _origin_ok(origin)) else "null",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


def _host_ok(request):
    # Barra DNS rebinding (mesmo padrao do monitor): dominio externo apontado
    # para 127.0.0.1 chega com Host: dominio-externo.
    host = (request.host or "").rsplit(":", 1)[0].strip("[]")
    return host in ("localhost", "127.0.0.1", "::1")


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


def build_app():
    # 21 MB: importar memorias de um arquivo (o padrao do aiohttp e' 1 MB)
    app = web.Application(middlewares=[cors_mw], client_max_size=21 * 1024 * 1024)
    app.add_routes([
        web.get("/health",          h_health),
        web.get("/memories",        h_list),
        web.post("/memories",       h_add),
        web.put("/memories/{id}",   h_edit),
        web.delete("/memories/{id}", h_delete),
        web.post("/memories/{id}/pin", h_pin),
        web.post("/memories/tidy", h_tidy),
        web.post("/memories/tidy/apply", h_tidy_apply),
        web.get("/memories/export", h_export),
        web.post("/memories/import/extract", h_import_extract),
        web.post("/memories/import/apply", h_import_apply),
        web.get("/personas",        h_personas),
        web.get("/persona",         h_get_active),
        web.post("/persona",        h_set_active),
        web.post("/persona/config", h_save_persona),
        web.delete("/persona/{name}", h_del_persona),
    ])
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=PORT, print=None)
