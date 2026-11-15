# -*- coding: utf-8 -*-
"""Paletas do Nous: valores, contraste e folhas de estilo geradas."""
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
BRANDING = os.path.dirname(AQUI)
sys.path.insert(0, BRANDING)

import gerar_paletas as gp  # noqa: E402

IDS = ["ouro", "pitaya", "maracuja", "melancia", "ametista", "ceu", "mata"]
CHAVES = {"bg", "lado", "alto", "linha", "txt", "mut", "acc", "on_acc", "acc_txt", "sec", "det", "ok", "perigo"}


class TestPaletas(unittest.TestCase):
    def setUp(self):
        self.dados = gp.carregar()

    def test_sete_paletas_e_padrao_ouro(self):
        self.assertEqual([p["id"] for p in self.dados["paletas"]], IDS)
        self.assertEqual(self.dados["padrao"], "ouro")
        for p in self.dados["paletas"]:
            for modo in ("claro", "escuro"):
                self.assertEqual(set(p[modo]), CHAVES, f"{p['id']}/{modo}")

    def test_contraste_minimo(self):
        pares = [("txt", "bg"), ("mut", "bg"), ("acc_txt", "bg"), ("on_acc", "acc"), ("txt", "alto"), ("perigo", "bg")]
        for p in self.dados["paletas"]:
            if p["id"] == "ouro":
                continue  # o classico fica como e' hoje
            for modo in ("claro", "escuro"):
                c = p[modo]
                for a, b in pares:
                    r = gp.contraste(c[a], c[b])
                    self.assertGreaterEqual(r, 4.5, f"{p['id']}/{modo}: {a} sobre {b} = {r:.2f}")
                t = gp.tokens(p, modo)
                for k in ("sec", "det"):  # letra escolhida sobre a cor de apoio e a de detalhe
                    r = gp.contraste(t[k], t["on-" + k])
                    self.assertGreaterEqual(r, 4.5, f"{p['id']}/{modo}: letra sobre {k} = {r:.2f}")

    def test_tokens_calculados(self):
        pitaya = self.dados["paletas"][1]
        t = gp.tokens(pitaya, "claro")
        self.assertEqual(t["acc"], "#c2185b")
        self.assertEqual(t["acc-rgb"], "194,24,91")
        self.assertEqual(t["txt-rgb"], "38,22,31")
        self.assertEqual(t["on-sec"], "#ffffff")   # verde escuro pede letra branca
        self.assertEqual(t["on-det"], "#ffffff")   # semente preta
        ceu = gp.tokens(self.dados["paletas"][5], "escuro")
        self.assertEqual(ceu["on-sec"], "#141414")  # rosa claro pede letra escura

    def test_css_tem_bloco_por_paleta(self):
        css = gp.css(self.dados, escuro="classe")
        for i in IDS:
            self.assertIn(f'[data-nous-paleta="{i}"]{{', css)
            self.assertIn(f'.dark[data-nous-paleta="{i}"],.dark [data-nous-paleta="{i}"]{{', css)
        raiz = css.split(":root{", 1)[1].split("}", 1)[0]
        self.assertIn("--nous-acc:#a87a1c", raiz)
        self.assertIn("--nous-bg:#ffffff", raiz)
        escuro = css.split("\n.dark{", 1)[1].split("}", 1)[0]
        self.assertIn("--nous-acc:#c8962e", escuro)

    def test_bloco_claro_vem_antes_do_escuro(self):
        css = gp.css(self.dados, escuro="classe")
        self.assertLess(css.index('[data-nous-paleta="pitaya"]{'), css.index('.dark[data-nous-paleta="pitaya"]'))

    def test_auto_usa_media_query(self):
        css = gp.css(self.dados, escuro="auto")
        self.assertNotIn(".dark", css)
        self.assertIn("@media (prefers-color-scheme:dark){", css)
        midia = css.split("@media (prefers-color-scheme:dark){", 1)[1]
        self.assertIn('[data-nous-paleta="maracuja"]{', midia)
        self.assertIn("--nous-bg:#17111a", midia)

    def test_ouro_cinza_neutro(self):
        css = gp.css(self.dados, escuro="classe")
        raiz = css.split(":root{", 1)[1].split("}", 1)[0]
        self.assertNotIn("--color-gray", raiz)  # Ouro nao mexe nos cinzas do Open WebUI
        ouro = css.split('[data-nous-paleta="ouro"]{', 1)[1].split("}", 1)[0]
        self.assertNotIn("--color-gray", ouro)
        pit = css.split('[data-nous-paleta="pitaya"]{', 1)[1].split("}", 1)[0]
        # !important: o Open WebUI escreve os cinzas escuros no style do <html>
        self.assertIn("--color-gray-900:oklch(20% 0.014 345) !important", pit)
        self.assertIn("--color-gray-100:oklch(94% 0.007 345) !important", pit)

    def test_css_versionado_igual_ao_gerado(self):
        for nome, modo in (("nous-paletas.css", "classe"), ("nous-paletas-auto.css", "auto")):
            with open(os.path.join(BRANDING, nome), encoding="utf-8") as f:
                self.assertEqual(f.read(), gp.css(self.dados, escuro=modo),
                                 f"{nome} desatualizado: rode python branding/gerar_paletas.py")


if __name__ == "__main__":
    unittest.main()
