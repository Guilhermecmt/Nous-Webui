# -*- coding: utf-8 -*-
"""
Nous - gera o icone (nous.ico) e o selo (nous-selo.png) a partir da coruja.

A coruja dourada e' a mesma de nous_logo.png. O que muda e' a legibilidade:
  - selo escuro proprio: nao depende da cor da barra de tarefas nem do papel de parede;
  - traco um pouco mais grosso so' nos tamanhos pequenos (tamanho optico);
  - de 16 a 24 px a coruja sai sem a coroa, que la' virava um caroco e roubava
    espaco dos olhos. De 32 px para cima a coroa volta.
Os quadros menores que 256 px vao em BMP: o GDI+ do PowerShell 5.1 (bandeja do
Windows) nao le PNG em quadro pequeno e desenhava pixels aleatorios.

Uso:  python branding/gerar_icone.py
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

AQUI = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(AQUI, "assets")
LOGO = os.path.join(ASSETS, "nous_logo.png")
TAMANHOS = [16, 20, 24, 32, 40, 48, 64, 128, 256]

OURO_CLARO = (246, 214, 122)
OURO = (214, 164, 56)
FUNDO = (20, 18, 16)          # #141210, o mesmo fundo escuro do Nous
CORTE_COROA = 0.20            # fracao de cima da coruja onde fica a coroa
ESCALA = 8                    # desenha em 8x e reduz no fim


def _mestre():
    im = Image.open(LOGO).convert("RGBA")
    return im.crop(im.getchannel("A").getbbox())


def _gradiente(w, h):
    t = np.linspace(0, 1, h)[:, None, None]
    rgb = np.array(OURO_CLARO, float) * (1 - t) + np.array(OURO, float) * t
    return np.broadcast_to(rgb, (h, w, 3)).astype(np.uint8)


def coruja(alt, engrossar=0.0, coroa=True):
    """Coruja dourada com `alt` px de altura; `engrossar` = px a mais por lado no tamanho final."""
    src = _mestre()
    if not coroa:
        a = np.asarray(src.getchannel("A"))
        corte = int(src.height * CORTE_COROA)
        linhas = np.where(a[corte:].max(axis=1) > 20)[0]
        src = src.crop((0, corte + int(linhas[0]), src.width, src.height))
        src = src.crop(src.getchannel("A").getbbox())
    H = alt * ESCALA
    W = max(1, round(src.width * H / src.height))
    a = src.getchannel("A").resize((W, H), Image.LANCZOS)
    if engrossar > 0:
        r = max(1, round(engrossar * ESCALA))
        pad = r + 2
        a = a.crop((-pad, -pad, W + pad, H + pad)).filter(ImageFilter.MaxFilter(2 * r + 1))
    a = a.resize((max(1, round(a.width / ESCALA)), max(1, round(a.height / ESCALA))), Image.BOX)
    alfa = np.clip(np.asarray(a).astype(float) / 255 * 1.25, 0, 1)
    rgb = _gradiente(a.width, a.height)
    return Image.fromarray(np.dstack([rgb, (alfa * 255).astype(np.uint8)]), "RGBA")


def selo(tam):
    """O icone num tamanho: selo escuro de cantos arredondados com a coruja no meio."""
    grande = tam * 4
    can = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    d = ImageDraw.Draw(can)
    raio = int(grande * 0.24)
    d.rounded_rectangle((0, 0, grande - 1, grande - 1), radius=raio, fill=FUNDO + (255,))
    if tam >= 32:
        d.rounded_rectangle((2, 2, grande - 3, grande - 3), radius=raio - 2,
                            outline=OURO + (110,), width=max(2, tam // 8))
    can = can.resize((tam, tam), Image.LANCZOS)
    pequeno = tam <= 32
    o = coruja(round(tam * (0.84 if tam <= 20 else 0.80)), engrossar=0.08 if pequeno else 0.0, coroa=tam >= 32)
    can.alpha_composite(o, ((tam - o.width) // 2, (tam - o.height) // 2))
    return can


def main():
    quadros = {t: selo(t) for t in TAMANHOS}
    ico = os.path.join(ASSETS, "nous.ico")
    quadros[256].save(ico, format="ICO", sizes=[(t, t) for t in TAMANHOS],
                      append_images=[quadros[t] for t in TAMANHOS if t != 256],
                      bitmap_format="bmp")
    _quadro_256_em_png(ico, quadros[256])
    selo(512).save(os.path.join(ASSETS, "nous-selo.png"), optimize=True)
    print("gerados: branding/assets/nous.ico e branding/assets/nous-selo.png")


def _quadro_256_em_png(ico, im256):
    """Troca so' o quadro de 256 px por PNG (fica bem menor; o Windows le' PNG nesse tamanho)."""
    import io
    import struct
    dados = bytearray(open(ico, "rb").read())
    _, _, n = struct.unpack_from("<HHH", dados, 0)
    entradas = [list(struct.unpack_from("<BBBBHHII", dados, 6 + 16 * i)) for i in range(n)]
    corpos = [bytes(dados[e[7]:e[7] + e[6]]) for e in entradas]
    buf = io.BytesIO()
    im256.save(buf, format="PNG", optimize=True)
    for i, e in enumerate(entradas):
        if e[0] == 0:
            corpos[i] = buf.getvalue()
    out = bytearray(struct.pack("<HHH", 0, 1, n))
    pos = 6 + 16 * n
    for e, c in zip(entradas, corpos):
        e[6], e[7] = len(c), pos
        out += struct.pack("<BBBBHHII", *e)
        pos += len(c)
    for c in corpos:
        out += c
    open(ico, "wb").write(out)


if __name__ == "__main__":
    main()
