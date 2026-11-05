# -*- coding: utf-8 -*-
"""Aplica o branding do repo no Open WebUI do teste, sem sujar o repo.

O apply_branding.py guarda os originais em <repo>/bkp/openwebui-originais. Aqui a
copia vai para o DATA_DIR temporario: so' o venv do teste e o DATA_DIR mudam.

Uso: <venv>/Scripts/python.exe aplicar_branding.py <data-dir>
"""
import os
import sys

sys.dont_write_bytecode = True  # sem __pycache__ dentro de branding/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "branding"))

import apply_branding  # noqa: E402

data_dir = sys.argv[1]
apply_branding.BACKUP = os.path.join(data_dir, "originais")
sys.argv = ["apply_branding.py", "--data-dir", data_dir]
sys.exit(apply_branding.main())
