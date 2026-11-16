# -*- coding: utf-8 -*-
"""A coruja do terminal (code/cli/coruja.ts) esta' em dia com a logo."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

import gerar_coruja_terminal as g  # noqa: E402


class TestCorujaTerminal(unittest.TestCase):
    def test_desenho_em_braille(self):
        ls = g.linhas()
        self.assertGreaterEqual(len(ls), 10)
        self.assertTrue(all(len(l) <= g.COLUNAS for l in ls))
        letras = "".join(ls).replace(" ", "")
        self.assertTrue(letras and all(0x2800 < ord(c) <= 0x28FF for c in letras))

    def test_arquivo_versionado_em_dia(self):
        with open(g.SAIDA, encoding="utf-8") as f:
            self.assertEqual(f.read(), g.ts(g.linhas()),
                             "code/cli/coruja.ts desatualizado: rode python branding/gerar_coruja_terminal.py")


if __name__ == "__main__":
    unittest.main()
