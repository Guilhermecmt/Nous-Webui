# -*- coding: utf-8 -*-
"""
Nous WebUI - Aplicador de identidade visual.

Aplica em uma instalacao existente do Open WebUI:
  - a logo (coruja Nous) em todos os favicons/logos/splash
  - favicon.svg (PNG embutido) e favicon.ico
  - o tema "Branco & Ouro" (static/custom.css)
  - o comportamento extra (static/loader.js): painel de recursos, memorias,
    Loja de Modelos, tema claro/escuro
  - o nome do app "Nous" (sem o sufixo "(Open WebUI)")

Ao final grava um MARCADOR em <data-dir>/.branding_marker.json com a versao
do open-webui e o hash da logo. Com --if-needed, sai na hora se o marcador
ainda vale (mesma versao + mesma logo) — e' o modo usado no boot pelo
start-nous.ps1, que torna a identidade AUTO-CURATIVA: se um upgrade do
open-webui apagar o tema/logo, o proximo boot reaplica sozinho.

Uso:
    <venv>/Scripts/python.exe branding/apply_branding.py [--data-dir DIR] [--if-needed]

Exit codes: 0 = aplicado/ja valido; 1 = falha real (logo ausente, PIL, etc.).
"""
import os, io, sys, json, base64, shutil, hashlib, argparse
from datetime import datetime

try:
    import open_webui
except ImportError:
    print("open_webui nao encontrado. Rode este script com o Python do ambiente "
          "que tem o Open WebUI instalado (ex.: <venv>/Scripts/python.exe).")
    sys.exit(1)

OW = os.path.dirname(open_webui.__file__)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(REPO, "branding", "assets")
MASTER = os.path.join(ASSETS, "nous_logo.png")
CSS_SRC = os.path.join(REPO, "branding", "nous-gold.css")
JS_SRC = os.path.join(REPO, "branding", "nous-loader.js")
# Paineis extras (agenda, skills...): cada um e' um IIFE proprio, concatenado
# depois do nous-loader.js no mesmo loader.js (sem <script> a mais).
JS_MODULES = os.path.join(REPO, "branding", "modules")


def _module_files():
    if not os.path.isdir(JS_MODULES):
        return []
    return [os.path.join(JS_MODULES, f) for f in sorted(os.listdir(JS_MODULES)) if f.endswith(".js")]


def _loader_js():
    if not os.path.exists(JS_SRC):
        return ""
    parts = [open(JS_SRC, encoding="utf-8").read()]
    for p in _module_files():
        parts.append(f"\n/* ---- modulo: {os.path.basename(p)} ---- */\n"
                     + open(p, encoding="utf-8").read())
    return "\n".join(parts)
BACKUP = os.path.join(REPO, "bkp", "openwebui-originais")

STATIC_DIRS = {
    "static": os.path.join(OW, "static"),
    "frontend_static": os.path.join(OW, "frontend", "static"),
}
# nome -> tamanho padrao (px) usado SE o arquivo ainda nao existir.
# Importante: o frontend referencia /static/favicon.png e /static/splash.png;
# se faltarem, a logo/splash quebram (404). Por isso criamos os que faltam.
IMG_TARGETS = {
    "apple-touch-icon.png": 180,
    "favicon-96x96.png": 96,
    "favicon-dark.png": 512,
    "favicon.png": 512,
    "logo.png": 512,
    "splash.png": 512,
    "splash-dark.png": 512,
    "web-app-manifest-192x192.png": 192,
    "web-app-manifest-512x512.png": 512,
}


def _ow_version():
    try:
        from importlib.metadata import version
        return version("open-webui")
    except Exception:
        return getattr(open_webui, "__version__", "desconhecida")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _inputs_hash():
    """Hash conjunto da logo + css + js: qualquer mudanca reaplica tudo."""
    h = hashlib.sha256()
    for p in (MASTER, CSS_SRC, JS_SRC, *_module_files()):
        if os.path.exists(p):
            h.update(_sha256(p).encode())
    return h.hexdigest()


def marker_path(data_dir):
    return os.path.join(data_dir, ".branding_marker.json")


def marker_valid(data_dir):
    try:
        with open(marker_path(data_dir), encoding="utf-8") as f:
            m = json.load(f)
        return (m.get("open_webui_version") == _ow_version()
                and m.get("inputs_sha256") == _inputs_hash()
                # se o tema sumiu do pacote (reinstalacao), o marcador nao vale
                and os.path.exists(os.path.join(OW, "static", "custom.css")))
    except Exception:
        return False


def write_marker(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    data = {
        "open_webui_version": _ow_version(),
        "inputs_sha256": _inputs_hash(),
        "applied_at": datetime.now().isoformat(timespec="seconds"),
    }
    with open(marker_path(data_dir), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def backup(path, label):
    if os.path.exists(path):
        b = os.path.join(BACKUP, f"{label}__{os.path.basename(path)}")
        if not os.path.exists(b):
            shutil.copy2(path, b)


def _fit(Image, master, w, h):
    """Redimensiona a logo p/ (w,h). Se nao for quadrada, centraliza com fundo
    transparente (preserva o formato esperado pelo frontend)."""
    if w == h:
        return master.resize((w, h), Image.LANCZOS)
    side = min(w, h)
    m = master.resize((side, side), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(m, ((w - side) // 2, (h - side) // 2), m)
    return out


def apply_images(Image, master):
    # frontend/favicon.png (raiz)
    extra = os.path.join(OW, "frontend", "favicon.png")
    if os.path.exists(extra):
        backup(extra, "frontend")
        with Image.open(extra) as im:
            w, h = im.size
        _fit(Image, master, w, h).save(extra)
    for label, d in STATIC_DIRS.items():
        if not os.path.isdir(d):
            continue
        for name, default in IMG_TARGETS.items():
            p = os.path.join(d, name)
            if os.path.exists(p):
                backup(p, label)
                with Image.open(p) as im:
                    w, h = im.size
            else:
                w = h = default  # cria do zero (instalacao que nao trazia o arquivo)
            _fit(Image, master, w, h).save(p)


def apply_favicons_and_css(Image, master):
    small = master.resize((128, 128), Image.LANCZOS)
    buf = io.BytesIO(); small.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" '
        'viewBox="0 0 128 128"><image href="data:image/png;base64,'
        + b64 + '" width="128" height="128"/></svg>'
    )
    ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    css = open(CSS_SRC, encoding="utf-8").read()
    js = _loader_js()
    for label, d in STATIC_DIRS.items():
        if not os.path.isdir(d):
            continue
        for f in ("custom.css", "loader.js", "favicon.svg", "favicon.ico"):
            backup(os.path.join(d, f), label)
        open(os.path.join(d, "custom.css"), "w", encoding="utf-8").write(css)
        if js:
            open(os.path.join(d, "loader.js"), "w", encoding="utf-8").write(js)
        open(os.path.join(d, "favicon.svg"), "w", encoding="utf-8").write(svg)
        master.save(os.path.join(d, "favicon.ico"), sizes=ico_sizes)


def patch_name(app_name="Nous"):
    env = os.path.join(OW, "env.py")
    src = open(env, encoding="utf-8").read()
    old = (
        "WEBUI_NAME = os.getenv('WEBUI_NAME', 'Open WebUI')\n"
        "if WEBUI_NAME != 'Open WebUI':\n"
        "    WEBUI_NAME += ' (Open WebUI)'"
    )
    new = f"WEBUI_NAME = os.getenv('WEBUI_NAME') or '{app_name}'"
    if new in src:
        return "ja aplicado"
    if old in src:
        backup(env, "env")
        open(env, "w", encoding="utf-8", newline="\n").write(src.replace(old, new))
        return "patch aplicado"
    # nao-fatal: o tema/logo seguem valendo; so' o sufixo do nome pode aparecer
    return "AVISO: padrao nao encontrado (versao nova do Open WebUI? atualize o pin)"


def main():
    ap = argparse.ArgumentParser(description="Aplica a identidade Nous no Open WebUI")
    ap.add_argument("--data-dir",
                    default=os.path.join(os.path.expanduser("~"), "NousData"))
    ap.add_argument("--if-needed", action="store_true",
                    help="sai em silencio se o marcador ainda vale (modo boot)")
    args = ap.parse_args()

    if args.if_needed and marker_valid(args.data_dir):
        return 0  # nada a fazer: mesma versao do open-webui, mesmos arquivos Nous

    if not os.path.exists(MASTER):
        print(f"[erro] Logo-mestre nao encontrada: {MASTER}")
        return 1
    if not os.path.exists(CSS_SRC):
        print(f"[erro] Tema nao encontrado: {CSS_SRC}")
        return 1
    if not any(os.path.isdir(d) for d in STATIC_DIRS.values()):
        print("[erro] Nenhuma pasta static do Open WebUI encontrada em: " + OW)
        return 1
    try:
        from PIL import Image
    except ImportError:
        print("[erro] Pillow (PIL) nao instalado neste ambiente. "
              "Rode: <venv>/Scripts/python.exe -m pip install pillow")
        return 1

    os.makedirs(BACKUP, exist_ok=True)
    master = Image.open(MASTER).convert("RGBA")
    print("Open WebUI em:", OW)
    apply_images(Image, master);            print("  [ok] logos/favicons (png)")
    apply_favicons_and_css(Image, master);  print("  [ok] favicon.svg/.ico + tema custom.css + loader.js")
    print("  [nome]", patch_name())
    write_marker(args.data_dir);            print("  [ok] marcador gravado (auto-cura no boot)")
    print("\nIdentidade Nous aplicada. Reinicie o servidor e use Ctrl+Shift+R no navegador.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:
        print(f"[erro] Falha ao aplicar a identidade: {e}")
        sys.exit(1)
