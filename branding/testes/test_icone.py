# -*- coding: utf-8 -*-
"""Icone do Nous: selo escuro com a coruja dourada, legivel pela bandeja do Windows."""
import os
import struct
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
BRANDING = os.path.dirname(AQUI)
ICO = os.path.join(BRANDING, "assets", "nous.ico")
SELO = os.path.join(BRANDING, "assets", "nous-selo.png")
sys.path.insert(0, BRANDING)

TAMANHOS = [16, 20, 24, 32, 40, 48, 64, 128, 256]
PNG = b"\x89PNG\r\n\x1a\n"


def quadros():
    with open(ICO, "rb") as f:
        dados = f.read()
    _, tipo, n = struct.unpack_from("<HHH", dados, 0)
    assert tipo == 1
    out = []
    for i in range(n):
        w, h, _, _, _, _, tam, ini = struct.unpack_from("<BBBBHHII", dados, 6 + 16 * i)
        out.append((w or 256, dados[ini:ini + tam]))
    return out


class TestIcone(unittest.TestCase):
    def test_ico_tem_os_tamanhos(self):
        self.assertEqual(sorted(w for w, _ in quadros()), TAMANHOS)

    def test_quadros_pequenos_em_bmp(self):
        # O GDI+ do PowerShell 5.1 (bandeja) nao le PNG em quadro pequeno: vira ruido.
        for w, corpo in quadros():
            if w < 256:
                self.assertFalse(corpo.startswith(PNG), f"quadro de {w} px esta' em PNG")

    def test_selo_opaco_no_fundo(self):
        from PIL import Image
        im = Image.open(SELO).convert("RGBA")
        self.assertEqual(im.size, (512, 512))
        self.assertEqual(im.getpixel((40, 256)), (20, 18, 16, 255))  # fundo do selo, ao lado da coruja
        self.assertEqual(im.getpixel((0, 0))[3], 0)                  # canto arredondado transparente

    def test_ico_pequeno_tem_coruja_dourada(self):
        from PIL import Image
        import gerar_icone
        im = gerar_icone.selo(16).convert("RGB")
        dourados = sum(1 for p in im.getdata() if p[0] > 150 and p[1] > 110 and p[2] < 110)
        self.assertGreater(dourados, 20)  # a coruja aparece (antes: ruido colorido)


if __name__ == "__main__":
    unittest.main()
