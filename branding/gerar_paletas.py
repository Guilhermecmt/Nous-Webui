# -*- coding: utf-8 -*-
"""
Nous - gera as folhas de estilo das paletas a partir de branding/paletas.json.

Saidas (versionadas; um teste confere que estao em dia com o JSON):
  branding/nous-paletas.css       escuro pela classe .dark (Open WebUI, Nous Code)
  branding/nous-paletas-auto.css  escuro pelo prefers-color-scheme (paginas sem o
                                  JavaScript de tema: celular, carregamento, relatorios)

Cada paleta vira um bloco [data-nous-paleta="id"] (claro) e outro para o escuro.
O seletor vale em qualquer elemento, nao so' no <html>: e' assim que os cartoes do
seletor de cores mostram a previa de cada paleta. Ouro tambem fica em :root, para
a tela ja' nascer certa antes de qualquer JavaScript.

Uso:  python branding/gerar_paletas.py
"""
import json
import os

AQUI = os.path.dirname(os.path.abspath(__file__))
JSON = os.path.join(AQUI, "paletas.json")
SAIDAS = {"classe": os.path.join(AQUI, "nous-paletas.css"),
          "auto": os.path.join(AQUI, "nous-paletas-auto.css")}

# luminosidade dos cinzas do Open WebUI 0.12 (oklch, croma 0 de fabrica)
CINZAS = [(50, 98), (100, 94), (200, 92), (300, 85), (400, 77), (500, 69),
          (600, 51), (700, 42), (800, 32), (850, 27), (900, 20), (950, 16)]
CHAVES = [("bg", "bg"), ("lado", "lado"), ("alto", "alto"), ("linha", "linha"),
          ("txt", "txt"), ("mut", "mut"), ("acc", "acc"), ("on_acc", "on-acc"),
          ("acc_txt", "acc-txt"), ("sec", "sec"), ("det", "det"), ("ok", "ok"),
          ("perigo", "perigo")]
LETRA_CLARA, LETRA_ESCURA = "#ffffff", "#141414"


def carregar():
    with open(JSON, encoding="utf-8") as f:
        return json.load(f)


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(h):
    def canal(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def letra_sobre(fundo):
    return LETRA_CLARA if contraste(fundo, LETRA_CLARA) >= contraste(fundo, LETRA_ESCURA) else LETRA_ESCURA


def tokens(paleta, modo):
    """Valores de um modo, com os calculados (acc-rgb, on-sec, on-det)."""
    c = paleta[modo]
    t = {nome: c[chave] for chave, nome in CHAVES}
    t["acc-rgb"] = ",".join(str(v) for v in _rgb(c["acc"]))
    t["txt-rgb"] = ",".join(str(v) for v in _rgb(c["txt"]))  # tons translucidos da cor do texto
    t["on-sec"] = letra_sobre(c["sec"])
    t["on-det"] = letra_sobre(c["det"])
    return t


def _num(x):
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return s or "0"


def cinzas(paleta):
    """Cinzas do Open WebUI tingidos pela paleta. Vao com !important porque o Open
    WebUI escreve --color-gray-800..950 direto no style do <html> no tema escuro.
    Paleta sem croma (Ouro) nao declara nada: fica exatamente como o Open WebUI."""
    matiz, croma = paleta["cinza"]["matiz"], paleta["cinza"]["croma"]
    if not croma:
        return []
    out = []
    for passo, luz in CINZAS:
        fator = 0.5 if passo <= 300 else (0.8 if passo <= 600 else 1.0)
        out.append((f"color-gray-{passo}", f"oklch({luz}% {_num(croma * fator)} {_num(matiz)}) !important"))
    return out


def _decl(pares):
    return ";".join(f"--{k}:{v}" for k, v in pares)


def _nous(t):
    ordem = ["bg", "lado", "alto", "linha", "txt", "txt-rgb", "mut", "acc", "acc-rgb", "on-acc",
             "acc-txt", "sec", "on-sec", "det", "on-det", "ok", "perigo"]
    return [(f"nous-{k}", t[k]) for k in ordem]


def css(dados, escuro="classe"):
    paletas = {p["id"]: p for p in dados["paletas"]}
    padrao = paletas[dados["padrao"]]
    linhas = ["/* Gerado por branding/gerar_paletas.py a partir de paletas.json: nao edite a mao. */"]
    linhas.append(":root{" + _decl(_nous(tokens(padrao, "claro")) + cinzas(padrao)) + "}")
    if escuro == "classe":
        linhas.append(".dark{" + _decl(_nous(tokens(padrao, "escuro"))) + "}")
    for p in dados["paletas"]:
        sel = f'[data-nous-paleta="{p["id"]}"]'
        linhas.append(sel + "{" + _decl(_nous(tokens(p, "claro")) + cinzas(p)) + "}")
        if escuro == "classe":
            linhas.append(f".dark{sel},.dark {sel}" + "{" + _decl(_nous(tokens(p, "escuro"))) + "}")
    if escuro == "auto":
        dentro = [":root{" + _decl(_nous(tokens(padrao, "escuro"))) + "}"]
        for p in dados["paletas"]:
            dentro.append(f'[data-nous-paleta="{p["id"]}"]' + "{" + _decl(_nous(tokens(p, "escuro"))) + "}")
        linhas.append("@media (prefers-color-scheme:dark){" + "\n".join(dentro) + "}")
    return "\n".join(linhas) + "\n"


def main():
    dados = carregar()
    for modo, caminho in SAIDAS.items():
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(css(dados, escuro=modo))
        print("gerado:", os.path.relpath(caminho, os.path.dirname(AQUI)))


if __name__ == "__main__":
    main()
