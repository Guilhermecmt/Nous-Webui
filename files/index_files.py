# -*- coding: utf-8 -*-
"""
Nous - Indexador de arquivos locais (Fase 2: acesso aos seus dados).

Varre uma pasta sua (.md / .txt), divide em trechos, gera embeddings via Ollama
e guarda tudo em nous_files.sqlite3 (dentro do NousData, gitignored) com uma
tabela FTS5 para busca por palavra-chave. O filtro nous_files.py consulta esse
indice (busca HIBRIDA: semantica + palavra-chave) e injeta os trechos relevantes
no contexto do chat. 100% local.

Incremental: so' reindexa arquivos novos/alterados (mtime+tamanho, depois hash) e
remove do indice os que sumiram. Idempotente.

USO:
    python files/index_files.py --data-dir <DATA_DIR> [--folder <pasta>] [--once]
    (sem --once roda em modo "watch": reindexa a cada N segundos, lendo a pasta
     do arquivo de config a cada ciclo, entao mudar a pasta nao exige reiniciar.)
"""
import os
import sys
import json
import time
import socket
import hashlib
import argparse
import sqlite3

try:
    import numpy as np
except Exception:
    np = None

try:
    import requests
except Exception:
    requests = None

DB_NAME = "nous_files.sqlite3"
CONFIG_NAME = "nous_files.json"
# Multilingue: em portugues separa trechos relevantes de irrelevantes bem melhor
# que o nomic-embed-text (calibracao no CHANGELOG da 2.8).
EMBED_MODEL = os.environ.get("NOUS_EMBED_MODEL", "granite-embedding:278m")
OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
EXTS = (".md", ".txt")
SKIP_DIRS = {".obsidian", ".git", ".trash", "node_modules", ".vscode", "__pycache__"}
MAX_FILE_BYTES = 2_000_000          # ignora arquivos absurdamente grandes
WATCH_SECONDS = 20
LOCK_PORT = 8991                    # mutex de processo unico (bind falha = ja roda)


# ----------------------------- caminhos / config -----------------------------
def resolve_data_dir(arg):
    for v in (arg, os.environ.get("DATA_DIR"), os.environ.get("NOUS_DATA_DIR")):
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def config_path(data_dir):
    return os.path.join(data_dir, CONFIG_NAME)


def read_folder(data_dir, override=None):
    """Pasta a indexar: --folder > env > config json. (None = nada configurado)."""
    if override:
        return override
    env = os.environ.get("NOUS_FILES_DIR")
    if env:
        return env
    try:
        with open(config_path(data_dir), encoding="utf-8-sig") as f:
            folder = (json.load(f) or {}).get("folder")
            if folder:
                return folder
    except Exception:
        pass
    return None


# ----------------------------- banco -----------------------------
def connect(db):
    cx = sqlite3.connect(db, timeout=30)
    cx.execute("PRAGMA journal_mode=WAL")
    cx.execute(
        """CREATE TABLE IF NOT EXISTS files(
               path TEXT PRIMARY KEY, mtime REAL, size INTEGER,
               hash TEXT, indexed_at INTEGER)"""
    )
    cx.execute(
        """CREATE TABLE IF NOT EXISTS chunks(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               path TEXT, ord INTEGER, heading TEXT, text TEXT, embedding BLOB)"""
    )
    cx.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
    cx.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text)")
    cx.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
    # Vetores de outro modelo nao se comparam com os novos: reindexa tudo.
    em = cx.execute("SELECT value FROM meta WHERE key='embed_model'").fetchone()
    if em is None or em[0] != EMBED_MODEL:
        if cx.execute("SELECT 1 FROM chunks LIMIT 1").fetchone():
            cx.execute("DELETE FROM chunks")
            cx.execute("DELETE FROM chunks_fts")
            cx.execute("DELETE FROM files")
        cx.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('embed_model',?)", (EMBED_MODEL,))
    cx.commit()
    return cx


def drop_file(cx, path):
    rows = cx.execute("SELECT id FROM chunks WHERE path=?", (path,)).fetchall()
    for (cid,) in rows:
        cx.execute("DELETE FROM chunks_fts WHERE rowid=?", (cid,))
    cx.execute("DELETE FROM chunks WHERE path=?", (path,))
    cx.execute("DELETE FROM files WHERE path=?", (path,))


# ----------------------------- texto -----------------------------
def chunk_text(text, max_chars=900):
    """Divide em trechos de ~max_chars por paragrafo, anexando o heading vigente."""
    chunks = []
    heading = ""
    buf = []
    buf_len = 0

    def flush():
        nonlocal buf, buf_len
        if buf:
            chunks.append((heading, "\n".join(buf).strip()))
            buf, buf_len = [], 0

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if stripped.startswith("#"):          # heading markdown -> novo contexto
            flush()
            heading = stripped.lstrip("#").strip()
            continue
        if not line.strip():                  # paragrafo em branco
            if buf_len >= max_chars * 0.6:
                flush()
            continue
        buf.append(line)
        buf_len += len(line) + 1
        if buf_len >= max_chars:
            flush()
    flush()
    return [(h, t) for (h, t) in chunks if t]


# ----------------------------- embeddings -----------------------------
def embed(text):
    """Embedding via Ollama. Retorna list[float] ou None (mantem so' palavra-chave)."""
    if requests is None:
        return None
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text[:8000]},
            timeout=60,
        )
        if r.status_code != 200:
            return None
        v = r.json().get("embedding")
        return v if v else None
    except Exception:
        return None


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


# ----------------------------- varredura -----------------------------
def walk_files(folder):
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for n in names:
            if n.lower().endswith(EXTS):
                yield os.path.join(root, n)


def index_once(cx, folder, log=print):
    if not folder or not os.path.isdir(folder):
        return 0, 0
    seen = set()
    changed = 0
    on_disk = list(walk_files(folder))
    for path in on_disk:
        seen.add(path)
        try:
            st = os.stat(path)
        except OSError:
            continue
        if st.st_size > MAX_FILE_BYTES:
            continue
        row = cx.execute(
            "SELECT mtime, size, hash FROM files WHERE path=?", (path,)
        ).fetchone()
        if row and abs(row[0] - st.st_mtime) < 1 and row[1] == st.st_size:
            continue  # inalterado
        try:
            data = open(path, "rb").read()
        except OSError:
            continue
        h = hashlib.sha1(data).hexdigest()
        if row and row[2] == h:
            cx.execute("UPDATE files SET mtime=?, size=? WHERE path=?",
                       (st.st_mtime, st.st_size, path))
            cx.commit()
            continue
        text = data.decode("utf-8", errors="ignore")
        drop_file(cx, path)
        for ord_, (heading, chunk) in enumerate(chunk_text(text)):
            emb_input = (heading + "\n" + chunk) if heading else chunk
            vec = embed(doc_prefix(emb_input))
            blob = None
            if vec is not None and np is not None:
                blob = np.asarray(vec, dtype="float32").tobytes()
            cur = cx.execute(
                "INSERT INTO chunks(path, ord, heading, text, embedding) VALUES (?,?,?,?,?)",
                (path, ord_, heading, chunk, blob),
            )
            cx.execute("INSERT INTO chunks_fts(rowid, text) VALUES (?, ?)",
                       (cur.lastrowid, (heading + "\n" + chunk) if heading else chunk))
        cx.execute(
            "INSERT OR REPLACE INTO files(path, mtime, size, hash, indexed_at) "
            "VALUES (?,?,?,?,?)",
            (path, st.st_mtime, st.st_size, h, int(time.time())),
        )
        cx.commit()
        changed += 1
        log(f"  [+] {os.path.relpath(path, folder)}")

    # remove o que sumiu do disco
    removed = 0
    known = [r[0] for r in cx.execute("SELECT path FROM files").fetchall()]
    for path in known:
        if path not in seen:
            drop_file(cx, path)
            removed += 1
    if removed:
        cx.commit()
        log(f"  [-] {removed} arquivo(s) removido(s) do indice")
    return changed, removed


# ----------------------------- main -----------------------------
def acquire_lock():
    """Garante processo unico (modo watch): tenta segurar uma porta local."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", LOCK_PORT))
        s.listen(1)
        return s  # mantem aberto durante a vida do processo
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--folder", default=None)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    data_dir = resolve_data_dir(a.data_dir)
    db = os.path.join(data_dir, DB_NAME)
    os.makedirs(data_dir, exist_ok=True)

    if a.once:
        folder = read_folder(data_dir, a.folder)
        if not folder:
            print("Nenhuma pasta configurada para indexar.")
            return
        cx = connect(db)
        try:
            ch, rm = index_once(cx, folder, log=print)
            print(f"Indexacao concluida: {ch} alterado(s), {rm} removido(s). Pasta: {folder}")
        finally:
            cx.close()
        return

    # modo watch (processo unico)
    lock = acquire_lock()
    if lock is None:
        print("Indexador ja' em execucao. Saindo.")
        return
    print(f"Indexador do Nous em modo watch (a cada {WATCH_SECONDS}s).")
    cx = connect(db)
    try:
        while True:
            folder = read_folder(data_dir, a.folder)
            if folder and os.path.isdir(folder) and embed_ready():
                try:
                    index_once(cx, folder, log=lambda *_: None)
                except Exception as e:
                    print("Erro na indexacao:", e)
            time.sleep(WATCH_SECONDS)
    finally:
        cx.close()


if __name__ == "__main__":
    main()
