# -*- coding: utf-8 -*-
"""
Nous - gera a coruja do terminal (abertura do comando `nous`) a partir da logo.

A coruja de branding/assets/nous_logo.png vira desenho em braille: cada letra e' um
bloco de 2x4 pontos, o que deixa o traco fino da logo reconhecivel em 15 colunas.
Saida: code/cli/coruja.ts (versionado; um teste confere que esta' em dia com a logo).
As cores (degrade da paleta escolhida) sao aplicadas no terminal, nao aqui.

Uso:  python branding/gerar_coruja_terminal.py
"""
import os

import numpy as np
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(AQUI, "assets", "nous_logo.png")
SAIDA = os.path.join(os.path.dirname(AQUI), "code", "cli", "coruja.ts")
COLUNAS = 15
LIMIAR = 0.32
# bit de cada ponto do braille: (coluna, linha) -> bit
PONTOS = [(0, 0, 0x01), (0, 1, 0x02), (0, 2, 0x04), (1, 0, 0x08), (1, 1, 0x10), (1, 2, 0x20), (0, 3, 0x40), (1, 3, 0x80)]


def linhas(colunas=COLUNAS, limiar=LIMIAR):
    im = Image.open(LOGO).convert("RGBA")
    im = im.crop(im.getchannel("A").getbbox())
    w = colunas * 2
    h = int(round(im.height * w / im.width / 4.0)) * 4
    a = np.asarray(im.getchannel("A").resize((w, h), Image.LANCZOS)).astype(float) / 255
    out = []
    for r in range(h // 4):
        s = ""
        for c in range(colunas):
            v = 0
            for dx, dy, bit in PONTOS:
                if a[r * 4 + dy, c * 2 + dx] > limiar:
                    v |= bit
            s += chr(0x2800 + v) if v else " "
        out.append(s.rstrip())
    return out


def ts(ls):
    corpo = "\n".join("  '" + l + "'," for l in ls)
    return ("// Gerado por branding/gerar_coruja_terminal.py a partir de branding/assets/nous_logo.png:\n"
            "// nao edite a mao. A coruja do Nous em braille (2x4 pontos por letra), para a abertura\n"
            "// do `nous` no terminal; o degrade da paleta e' aplicado em cli/tela.ts.\n"
            "export const CORUJA: string[] = [\n" + corpo + "\n];\n")


def main():
    with open(SAIDA, "w", encoding="utf-8", newline="\n") as f:
        f.write(ts(linhas()))
    print("gerado:", os.path.relpath(SAIDA, os.path.dirname(AQUI)))


if __name__ == "__main__":
    main()
