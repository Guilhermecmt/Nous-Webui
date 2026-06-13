# -*- coding: utf-8 -*-
"""
Servidor TTS local OpenAI-compatível para o Nous.

Expõe POST /v1/audio/speech no mesmo contrato da API OpenAI, chamando o
binário Piper com a voz pt_BR por baixo. O Open WebUI é configurado para
usar engine "openai" com base_url http://127.0.0.1:8994/v1 — sem nenhuma
mudança no frontend. Áudio 100% local, nunca sai da máquina.

Assets esperados em NousData\\voice\\:
  piper.exe            — binário do Piper para Windows
  <voice>.onnx         — modelo de voz (ex.: pt_BR-faber-medium.onnx)
  <voice>.onnx.json    — config da voz

Porta: 8994 (singleton — aborta se já ocupada).

USO:
    python voice/nous_tts_server.py [--data-dir <DATA_DIR>] [--port 8994]
"""
import os
import sys
import json
import socket
import argparse
import tempfile
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

DEFAULT_PORT   = 8994
DEFAULT_VOICE  = "pt_BR-faber-medium"


# --------------------------------------------------------------------------
# Asset resolution
# --------------------------------------------------------------------------

def resolve_voice_dir(data_dir: str | None) -> Path:
    candidates = []
    if data_dir:
        candidates.append(data_dir)
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            candidates.append(v)
    candidates.append(os.path.join(os.path.expanduser("~"), "NousData"))
    for d in candidates:
        p = Path(d) / "voice"
        if p.is_dir():
            return p
    # Fallback: first candidate even if not yet created
    base = candidates[0] if candidates else os.path.join(os.path.expanduser("~"), "NousData")
    return Path(base) / "voice"


def find_piper(voice_dir: Path) -> Path | None:
    p = voice_dir / "piper.exe"
    return p if p.is_file() else None


def find_voice_model(voice_dir: Path, voice_name: str) -> Path | None:
    """Return path to the .onnx file for the given voice name."""
    # Exact match first
    p = voice_dir / f"{voice_name}.onnx"
    if p.is_file():
        return p
    # Any pt_BR .onnx as fallback
    for f in sorted(voice_dir.glob("pt_BR-*.onnx")):
        return f
    # Any .onnx at all
    for f in sorted(voice_dir.glob("*.onnx")):
        return f
    return None


# --------------------------------------------------------------------------
# Piper synthesis
# --------------------------------------------------------------------------

def synthesize(text: str, voice_dir: Path, voice_name: str,
               output_format: str = "wav") -> bytes:
    """Call piper.exe and return raw audio bytes (wav or mp3)."""
    piper = find_piper(voice_dir)
    if piper is None:
        raise RuntimeError("piper.exe nao encontrado em " + str(voice_dir))

    model = find_voice_model(voice_dir, voice_name)
    if model is None:
        raise RuntimeError("Modelo de voz pt_BR nao encontrado em " + str(voice_dir))

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name

    try:
        proc = subprocess.run(
            [str(piper), "--model", str(model), "--output_file", wav_path],
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Piper saiu com {proc.returncode}: {proc.stderr.decode()}")

        with open(wav_path, "rb") as f:
            audio = f.read()
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass

    # Open WebUI aceita wav diretamente quando pede mp3; devolvemos wav sempre
    # (evita dependência de ffmpeg no leigo). O campo response_format é ignorado.
    return audio


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------

_voice_dir: Path = None  # set at startup
_voice_name: str = DEFAULT_VOICE


class TTSHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):  # silencia o log padrão
        pass

    def _send(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "http://localhost:8080")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        if self.path == "/health" or self.path == "/v1/health":
            info = {
                "status": "ok",
                "voice_dir": str(_voice_dir),
                "piper": str(find_piper(_voice_dir)) if _voice_dir else None,
                "model": str(find_voice_model(_voice_dir, _voice_name)) if _voice_dir else None,
            }
            body = json.dumps(info).encode()
            self._send(200, body, "application/json")
        else:
            self._send(404, b'{"error":"not found"}', "application/json")

    def do_POST(self):
        if self.path != "/v1/audio/speech":
            self._send(404, b'{"error":"not found"}', "application/json")
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send(400, b'{"error":"invalid json"}', "application/json")
            return

        text = payload.get("input", "")
        if not text:
            self._send(400, b'{"error":"input is required"}', "application/json")
            return

        voice = payload.get("voice", _voice_name) or _voice_name
        fmt   = payload.get("response_format", "wav")

        try:
            audio = synthesize(text, _voice_dir, voice, fmt)
            self._send(200, audio, "audio/wav")
        except Exception as exc:
            err = json.dumps({"error": str(exc)}).encode()
            self._send(500, err, "application/json")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    global _voice_dir, _voice_name

    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--port",     type=int, default=DEFAULT_PORT)
    ap.add_argument("--voice",    default=DEFAULT_VOICE)
    a = ap.parse_args()

    _voice_dir  = resolve_voice_dir(a.data_dir)
    _voice_name = a.voice

    if port_in_use(a.port):
        print(f"[NousTTS] Porta {a.port} ja em uso — outro servidor no ar. Saindo.")
        sys.exit(0)

    piper = find_piper(_voice_dir)
    model = find_voice_model(_voice_dir, _voice_name)
    if piper is None or model is None:
        print(f"[NousTTS] Assets de voz nao encontrados em {_voice_dir}. "
              "Use 'Ativar conversa por voz' no Nous para baixa-los.")
        sys.exit(1)

    print(f"[NousTTS] Iniciando na porta {a.port} | voz: {model.stem}")
    server = HTTPServer(("127.0.0.1", a.port), TTSHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
