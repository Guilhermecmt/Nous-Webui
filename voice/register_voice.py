# -*- coding: utf-8 -*-
"""
Configura STT (Whisper local) e TTS (Piper via servidor local) no banco do
Open WebUI. Sem credenciais de admin, sem servidor no ar.

Logica:
  - Assets presentes em NousData\\voice\\ (piper.exe + .onnx) => configura STT
    com Whisper local (pt) e TTS apontando para http://127.0.0.1:8994/v1.
  - Assets ausentes => remove a config de voz (volta ao padrao vazio).

Chaves escritas no JSON da tabela config (formato de open-webui==0.9.6):
  audio.stt.engine         = "whisper"
  audio.stt.whisper_model  = "small"   (base em CPU, medium em GPU)
  audio.tts.engine         = "openai"
  audio.tts.openai.api_base_url = "http://127.0.0.1:8994/v1"
  audio.tts.openai.api_key      = "nous-local"
  audio.tts.voice               = "pt_BR-faber-medium"
  audio.tts.model               = "piper"

Chamado por install-voice.ps1 e pelo launcher a cada boot (Register-Voice).

USO:
    python voice/register_voice.py [--data-dir <DATA_DIR>] [--voice <nome>]
"""
import os
import sys
import json
import time
import datetime
import sqlite3
import argparse
from pathlib import Path

TTS_SERVER_URL  = "http://127.0.0.1:8994/v1"
TTS_API_KEY     = "nous-local"
DEFAULT_VOICE   = "pt_BR-faber-medium"


# --------------------------------------------------------------------------
# Resolucao de caminhos (padrao dos outros register_*.py)
# --------------------------------------------------------------------------

def resolve_paths(data_dir):
    candidates = []
    if data_dir:
        candidates.append(data_dir)
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            candidates.append(v)
    candidates.append(os.path.join(os.path.expanduser("~"), "NousData"))
    return candidates


def resolve_db(candidates):
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
    return None


def voice_assets_present(candidates, voice_name):
    """True se piper.exe e o modelo .onnx existirem em NousData/voice/."""
    for d in candidates:
        vdir = Path(d) / "voice"
        piper = vdir / "piper.exe"
        onnx  = vdir / f"{voice_name}.onnx"
        # fallback: qualquer .onnx pt_BR
        if not onnx.is_file():
            matches = list(vdir.glob("pt_BR-*.onnx"))
            if matches:
                onnx = matches[0]
        if piper.is_file() and onnx.is_file():
            return True
    return False


def detect_gpu(candidates):
    """Retorna True se houver GPU VRAM > 0 (tenta o registro do Windows)."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Class"
            r"\{4d36e968-e325-11ce-bfc1-08002be10318}\0000",
        )
        val, _ = winreg.QueryValueEx(key, "HardwareInformation.qwMemorySize")
        return int(val) > 0
    except Exception:
        return False


# --------------------------------------------------------------------------
# Leitura / escrita do config (padrao de register_nvidia.py)
# --------------------------------------------------------------------------

def table_exists(cx, name):
    row = cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def read_config(cx):
    row = cx.execute(
        "SELECT data FROM config ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return {}
    raw = row[0]
    return json.loads(raw) if isinstance(raw, str) else raw


def write_config(cx, data):
    row = cx.execute("SELECT id FROM config ORDER BY id DESC LIMIT 1").fetchone()
    # Colunas DATETIME do Open WebUI esperam string ISO, NAO epoch inteiro
    # (gravar int faz o servidor crashar no boot com fromisoformat).
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = json.dumps(data, ensure_ascii=False)
    if row:
        cx.execute(
            "UPDATE config SET data=?, updated_at=? WHERE id=?",
            (payload, now, row[0]),
        )
    else:
        cx.execute(
            "INSERT INTO config (data, version, created_at, updated_at) VALUES (?,0,?,?)",
            (payload, now, now),
        )
    cx.commit()


# --------------------------------------------------------------------------
# Register / remove
# --------------------------------------------------------------------------

def register(cx, voice_name, has_gpu):
    cfg = read_config(cx)
    audio = cfg.setdefault("audio", {})

    # STT — Whisper local em portugues
    stt = audio.setdefault("stt", {})
    stt["engine"] = "whisper"
    stt["whisper_model"] = "medium" if has_gpu else "small"
    # WHISPER_LANGUAGE nao esta no JSON de config (e' env-only na 0.9.6),
    # mas guardamos aqui para referencia; o launcher pode setar WHISPER_LANGUAGE=pt
    stt["language"] = "pt"

    # TTS — servidor Piper local via contrato OpenAI
    tts = audio.setdefault("tts", {})
    tts["engine"] = "openai"
    tts_openai = tts.setdefault("openai", {})
    tts_openai["api_base_url"] = TTS_SERVER_URL
    tts_openai["api_key"]      = TTS_API_KEY
    tts["voice"] = voice_name
    tts["model"] = "piper"

    cfg["audio"] = audio
    write_config(cx, cfg)
    model = "medium (GPU)" if has_gpu else "small (CPU)"
    print(f"[NousVoz] STT Whisper {model} + TTS Piper {voice_name} registrados.")


def remove(cx):
    cfg = read_config(cx)
    if "audio" in cfg:
        cfg["audio"] = {}
        write_config(cx, cfg)
        print("[NousVoz] Config de voz removida (assets ausentes).")
    else:
        print("[NousVoz] Nenhuma config de voz para remover.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--voice",    default=DEFAULT_VOICE)
    a = ap.parse_args()

    candidates = resolve_paths(a.data_dir)
    assets_ok  = voice_assets_present(candidates, a.voice)

    db = resolve_db(candidates)
    if not db:
        print("[NousVoz] webui.db nao encontrado. Tentarei no proximo boot.")
        return

    cx = sqlite3.connect(db, timeout=15)
    try:
        if not table_exists(cx, "config"):
            print("[NousVoz] Tabela 'config' ainda nao criada. Tentarei no proximo boot.")
            return

        if assets_ok:
            has_gpu = detect_gpu(candidates)
            register(cx, a.voice, has_gpu)
        else:
            remove(cx)
    finally:
        cx.close()


if __name__ == "__main__":
    main()
