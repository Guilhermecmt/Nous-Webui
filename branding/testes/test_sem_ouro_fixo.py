# -*- coding: utf-8 -*-
"""Nenhuma tela do Nous pode ficar dourada numa paleta que nao e' a Ouro: as cores do
ouro so' existem em paletas.json e nas folhas geradas dela (nous-paletas*.css)."""
import os
import re
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
BRANDING = os.path.dirname(AQUI)
REPO = os.path.dirname(BRANDING)

OURO = re.compile(r"#(c8962e|e7c069|a87a1c|7f5b10|8a6414|e7c977|a9781f)\b|"
                  r"rgba\(\s*(200\s*,\s*150\s*,\s*46|231\s*,\s*192\s*,\s*105|138\s*,\s*100\s*,\s*20)\s*,", re.I)
LIVRES = {"paletas.json", "nous-paletas.css", "nous-paletas-auto.css"}

# telas fora de branding/ que tambem seguem a paleta
OUTRAS = [os.path.join(REPO, *p) for p in (
    ("code", "ide", "app.css"), ("code", "ide", "app.js"), ("code", "ide", "index.html"),
    ("celular", "nous_celular.py"), ("launchers", "loading.html"),
    ("search", "nous_search", "report.py"),
)]


def arquivos():
    for raiz, pastas, nomes in os.walk(BRANDING):
        pastas[:] = [p for p in pastas if p not in ("testes", "assets", "__pycache__")]
        for n in nomes:
            if n.endswith((".js", ".css")) and n not in LIVRES:
                yield os.path.join(raiz, n)
    for p in OUTRAS:
        if os.path.exists(p):
            yield p


class TestSemOuroFixo(unittest.TestCase):
    def test_sem_ouro_fixo(self):
        achados = []
        for p in arquivos():
            with open(p, encoding="utf-8") as f:
                for i, linha in enumerate(f, 1):
                    for m in OURO.finditer(linha):
                        achados.append(f"{os.path.relpath(p, REPO)}:{i}: {m.group(0)}")
        self.assertEqual(achados, [], "cor do ouro fixa no codigo (use --nous-*):\n" + "\n".join(achados[:60]) +
                         (f"\n... e mais {len(achados) - 60}" if len(achados) > 60 else ""))


if __name__ == "__main__":
    unittest.main()
