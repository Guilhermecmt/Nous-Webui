# -*- coding: utf-8 -*-
"""
Nous - Indexador do historico de conversas (Fase 4: memoria de contexto).

Le o webui.db do Open WebUI, agrupa as mensagens em pares de dialogo
(pergunta + resposta), gera embeddings via Ollama e guarda em
nous_history.sqlite3 (NousData/). O filtro nous_history.py consulta
esse indice para recuperar contexto de conversas anteriores.

Incremental: usa marca d'agua de tempo (com 1h de sobreposicao) para
so' reprocessar conversas novas. Deduplicacao por msg_id. Idempotente.

USO:
    python history/index_history.py --data-dir <DATA_DIR> [--once]
    (sem --once roda em modo watch: 60 s por ciclo)
"""
import os
import re
import sys
import json
import time
import socket
import sqlite3
import argparse

try:
    import numpy as np
except Exception:
    np = None

try:
    import requests
except Exception:
    requests = None

DB_NAME       = "nous_history.sqlite3"
WEBUI_DB      = "webui.db"
LOCK_PORT     = 8992          # mutex de processo unico (diferente do indexador de arquivos, 8991)
WATCH_SECONDS = 60            # conversas mudam com menos frequencia que arquivos
OVERLAP_SECS  = 3600          # 1 h de sobreposicao: captura respostas que chegam depois
MIN_TEXT_LEN  = 15            # ignora mensagens muito curtas ("ok", emojis, etc.)
EMBED_MODEL   = os.environ.get("NOUS_EMBED_MODEL", "granite-embedding:278m")
OLLAMA_URL    = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
PARSER_VERSION = "2"          # bump => forca reindex (mudou a extracao de texto)


# ---- caminhos ---------------------------------------------------------------

def resolve_data_dir(arg):
    for v in (arg, os.environ.get("DATA_DIR"), os.environ.get("NOUS_DATA_DIR")):
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


# ---- texto ------------------------------------------------------------------

_RE_REASONING = re.compile(r"<details[^>]*reasoning.*?</details>", re.IGNORECASE | re.DOTALL)
_RE_TAG       = re.compile(r"<[^>]+>")


def _extract_text(raw) -> str:
    """Extrai texto plano de content (str, JSON list/dict, bytes).

    IMPORTANTE: no webui.db a coluna `content` vem JSON-encoded — uma string
    entre aspas (ex.: "Ol\\u00e1, tudo bem?"). Sem decodificar, indexariamos o
    literal com aspas e escapes unicode. Por isso tentamos json.loads tambem
    quando a string comeca com aspas, nao so' com [ ou {.
    """
    if not raw:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="ignore")
    if isinstance(raw, str):
        s = raw.strip()
        if s[:1] in ('"', '[', '{'):
            try:
                return _extract_text(json.loads(s))
            except Exception:
                pass
        return s
    if isinstance(raw, list):
        return " ".join(
            p.get("text", "") for p in raw
            if isinstance(p, dict) and p.get("type") == "text"
        ).strip()
    if isinstance(raw, dict):
        inner = raw.get("content") or raw.get("text") or ""
        return _extract_text(inner)
    return str(raw).strip()


def _clean_text(s: str) -> str:
    """Remove blocos de raciocinio (<details type=reasoning>) e tags HTML que o
    Open WebUI guarda na resposta do assistente — senao o historico fica
    dominado por '<details>', '<summary>' etc. em vez do texto util."""
    if not s:
        return ""
    s = _RE_REASONING.sub(" ", s)
    s = _RE_TAG.sub(" ", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _pair_messages(msgs):
    """
    Agrupa linhas (id, user_id, role, content, output, created_at) em pares dialogo.
    Retorna lista de dicts com msg_id, user_id, user_msg, asst_msg, created_at.
    """
    pairs = []
    i = 0
    while i < len(msgs):
        msg_id, user_id, role, content, output, created_at = msgs[i]
        if role == "user":
            user_text = _extract_text(content)
            asst_text = ""
            if i + 1 < len(msgs) and msgs[i + 1][2] == "assistant":
                raw_asst = msgs[i + 1][3] or msgs[i + 1][4]  # content ou output
                asst_text = _clean_text(_extract_text(raw_asst))
                i += 2
            else:
                i += 1
            if len(user_text) >= MIN_TEXT_LEN:
                pairs.append({
                    "msg_id":     msg_id,
                    "user_id":    user_id or "default",
                    "user_msg":   user_text,
                    "asst_msg":   asst_text,
                    "created_at": created_at or 0,
                })
        else:
            i += 1
    return pairs


# ---- embeddings -------------------------------------------------------------

def _embed(text):
    if requests is None:
        return None
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text[:6000]},
            timeout=60,
        )
        if r.status_code != 200:
            return None
        v = r.json().get("embedding")
        return v if v else None
    except Exception:
        return None


# ---- banco de destino -------------------------------------------------------

def open_hist(db_path):
    cx = sqlite3.connect(db_path, timeout=30)
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute("""
        CREATE TABLE IF NOT EXISTS sync_state (
            key TEXT PRIMARY KEY, value INTEGER DEFAULT 0
        )""")
    cx.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY, value TEXT
        )""")
    cx.execute("""
        CREATE TABLE IF NOT EXISTS dialogues (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            msg_id     TEXT    UNIQUE NOT NULL,
            chat_id    TEXT    NOT NULL,
            user_id    TEXT    NOT NULL,
            user_msg   TEXT    NOT NULL,
            asst_msg   TEXT    DEFAULT '',
            created_at INTEGER NOT NULL,
            embedding  BLOB
        )""")
    cx.execute("CREATE INDEX IF NOT EXISTS idx_hist_user ON dialogues(user_id)")
    cx.execute("CREATE INDEX IF NOT EXISTS idx_hist_chat ON dialogues(chat_id)")
    cx.execute("CREATE INDEX IF NOT EXISTS idx_hist_ts   ON dialogues(created_at)")
    # FTS5 com duas colunas: busca tanto na pergunta quanto na resposta
    cx.execute("CREATE VIRTUAL TABLE IF NOT EXISTS dialogues_fts USING fts5(user_msg, asst_msg)")
    cx.commit()
    return cx


def embed_ready():
    """O modelo de embeddings esta' instalado? Sem ele, o ciclo espera: indexar
    agora gravaria trechos sem vetor (so' palavra-chave) para sempre."""
    if requests is None:
        return False
    try:
        tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5).json().get("models", [])
    except Exception:
        return False
    want = EMBED_MODEL if ":" in EMBED_MODEL else EMBED_MODEL + ":latest"
    return any(m.get("name") == want for m in tags)


def doc_prefix(text):
    """So' o nomic-embed-text pede prefixo de tarefa; os outros modelos nao."""
    return ("search_document: " + text) if EMBED_MODEL.startswith("nomic") else text


# ---- ciclo de indexacao -----------------------------------------------------

def check_reindex_needed(hist_cx, log=print):
    """Reconstroi o indice do zero se o modelo de embedding mudou (dimensao pode
    diferir) ou se a versao do parser de texto mudou (indice antigo corrompido).
    Idempotente: roda a cada ciclo, mas so' apaga quando algo realmente mudou."""
    pv = hist_cx.execute("SELECT value FROM meta WHERE key='parser_version'").fetchone()
    em = hist_cx.execute("SELECT value FROM meta WHERE key='embed_model'").fetchone()
    has_rows = hist_cx.execute("SELECT 1 FROM dialogues LIMIT 1").fetchone() is not None

    need = False
    if pv is None and has_rows:
        need = True                         # indice anterior 'a correcao do parser
    elif pv is not None and pv[0] != PARSER_VERSION:
        need = True
    if em is not None and em[0] != EMBED_MODEL:
        need = True                         # trocou o modelo de embedding

    if need:
        hist_cx.execute("DELETE FROM dialogues")
        hist_cx.execute("DELETE FROM dialogues_fts")
        hist_cx.execute("DELETE FROM sync_state")
        log("  [~] reindexando historico do zero (parser/modelo mudou)")
    hist_cx.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('parser_version',?)", (PARSER_VERSION,))
    hist_cx.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('embed_model',?)", (EMBED_MODEL,))
    hist_cx.commit()


def index_once(hist_cx, webui_db, log=print):
    """Le novas conversas do webui.db e indexa pares de dialogo. Retorna (added)."""
    if not os.path.isfile(webui_db):
        return 0

    check_reindex_needed(hist_cx, log)

    row = hist_cx.execute(
        "SELECT value FROM sync_state WHERE key='last_indexed_at'"
    ).fetchone()
    stored_ts = row[0] if row else 0
    last_ts   = stored_ts - OVERLAP_SECS

    # Abre webui.db em modo somente-leitura (evita lock com o servidor)
    try:
        src = sqlite3.connect(f"file:{webui_db}?mode=ro", uri=True, timeout=10)
    except Exception:
        try:
            src = sqlite3.connect(webui_db, timeout=10)
        except Exception:
            return 0

    added = 0
    seen_max_ts = stored_ts   # maior created_at JA' visto; sobe mesmo sem indexar

    try:
        tables = {r[0] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "chat_message" not in tables:
            return 0

        # Descobre quais chats tem mensagens novas
        affected = [r[0] for r in src.execute(
            "SELECT DISTINCT chat_id FROM chat_message WHERE created_at > ?",
            (last_ts,)
        ).fetchall()]
        if not affected:
            return 0

        for chat_id in affected:
            msgs = src.execute(
                """SELECT id, user_id, role, content, output, created_at
                   FROM chat_message
                   WHERE chat_id=? AND role IN ('user','assistant')
                   ORDER BY created_at ASC""",
                (chat_id,),
            ).fetchall()

            # Avanca a marca d'agua por TODA mensagem vista (mesmo curta/sem par),
            # senao conversas curtas seriam re-varridas a cada ciclo, para sempre.
            for m in msgs:
                if m[5]:
                    seen_max_ts = max(seen_max_ts, m[5])

            for pair in _pair_messages(msgs):
                # Deduplicacao: msg_id ja' indexado? pula.
                if hist_cx.execute(
                    "SELECT id FROM dialogues WHERE msg_id=?", (pair["msg_id"],)
                ).fetchone():
                    continue

                embed_text = pair["user_msg"]
                if pair["asst_msg"]:
                    embed_text += "\n" + pair["asst_msg"]
                vec = _embed(doc_prefix(embed_text))
                blob = None
                if vec is not None and np is not None:
                    blob = np.asarray(vec, dtype="float32").tobytes()

                try:
                    cur = hist_cx.execute(
                        """INSERT INTO dialogues
                           (msg_id, chat_id, user_id, user_msg, asst_msg, created_at, embedding)
                           VALUES (?,?,?,?,?,?,?)""",
                        (pair["msg_id"], chat_id, pair["user_id"],
                         pair["user_msg"], pair["asst_msg"],
                         pair["created_at"], blob),
                    )
                    hist_cx.execute(
                        "INSERT INTO dialogues_fts(rowid, user_msg, asst_msg) VALUES (?,?,?)",
                        (cur.lastrowid, pair["user_msg"], pair["asst_msg"] or ""),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    pass  # corrida rara: ja' inserido por outro ciclo

        hist_cx.commit()

        # Persiste a marca d'agua sempre que avancou — mesmo com added==0 (so'
        # mensagens curtas), evitando re-scan eterno dos mesmos chats.
        if seen_max_ts > stored_ts:
            hist_cx.execute(
                "INSERT OR REPLACE INTO sync_state(key, value) VALUES ('last_indexed_at',?)",
                (seen_max_ts,),
            )
            hist_cx.commit()
        if added:
            log(f"  [+] {added} dialogo(s) indexado(s) no historico")

    finally:
        src.close()

    return added


# ---- lock / main ------------------------------------------------------------

def acquire_lock():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    data_dir = resolve_data_dir(a.data_dir)
    os.makedirs(data_dir, exist_ok=True)
    hist_db  = os.path.join(data_dir, DB_NAME)
    webui_db = os.path.join(data_dir, WEBUI_DB)

    if a.once:
        cx = open_hist(hist_db)
        try:
            n = index_once(cx, webui_db, log=print)
            print(f"Indexacao concluida: {n} dialogo(s) adicionado(s).")
        finally:
            cx.close()
        return

    lock = acquire_lock()
    if lock is None:
        print("Indexador de historico ja em execucao. Saindo.")
        return

    print(f"Indexador de historico em modo watch (a cada {WATCH_SECONDS}s).")
    cx = open_hist(hist_db)
    try:
        while True:
            try:
                if embed_ready():
                    index_once(cx, webui_db, log=lambda *_: None)
            except Exception as e:
                print("Erro na indexacao do historico:", e)
            time.sleep(WATCH_SECONDS)
    finally:
        cx.close()


if __name__ == "__main__":
    main()
