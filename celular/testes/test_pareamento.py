# -*- coding: utf-8 -*-
"""Pareamento do celular: filtro de IP, codigo de uso unico, cookie guardado so' como hash."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pareamento as par  # noqa: E402


class FiltroDeIp(unittest.TestCase):
    def test_aceita_rede_de_casa(self):
        for ip in ("192.168.1.5", "10.0.0.2", "172.16.0.9", "172.31.255.1", "169.254.4.234", "fd12:3456::1", "fe80::1",
                   "fe80::1%12", "::ffff:192.168.1.5"):
            self.assertTrue(par.ip_permitido(ip), ip)

    def test_recusa_o_resto(self):
        for ip in ("8.8.8.8", "172.32.0.1", "172.15.0.1", "192.169.0.1", "11.0.0.1", "127.0.0.1", "::1", "0.0.0.0",
                   "224.0.0.1", "2001:4860:4860::8888", "::ffff:8.8.8.8", "", "abc", "192.168.1", None, "192.168.1.5.6"):
            self.assertFalse(par.ip_permitido(ip), ip)

    def test_host(self):
        nomes = {"meu-pc"}
        for h in ("192.168.1.5:8999", "192.168.1.5", "[fe80::1]:8999", "meu-pc:8999", "meu-pc.local:8999", "MEU-PC"):
            self.assertTrue(par.host_permitido(h, nomes), h)
        for h in ("evil.com", "evil.com:8999", "8.8.8.8:8999", "localhost:8999", "127.0.0.1:8999", "", None,
                  "192.168.1.5.evil.com", "outro-pc"):
            self.assertFalse(par.host_permitido(h, nomes), h)


class Codigo(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = self._t.name

    def tearDown(self):
        self._t.cleanup()

    def test_uso_unico(self):
        cod, _ = par.novo_codigo(self.d)
        self.assertRegex(cod, r"^[A-Z2-9]{4}-[A-Z2-9]{4}$")
        c = par.trocar_codigo(self.d, cod.lower().replace("-", " "), "Mozilla Android Chrome/120", "192.168.1.9")
        self.assertTrue(c)
        self.assertIsNone(par.trocar_codigo(self.d, cod, "", ""), "o codigo nao pode valer duas vezes")
        self.assertEqual(len(par.listar_aparelhos(self.d)), 1)

    def test_vence(self):
        cod, exp = par.novo_codigo(self.d, agora=1000)
        self.assertIsNone(par.trocar_codigo(self.d, cod, "", "", agora=exp + 1))
        self.assertIsNone(par.codigo_vigente(self.d, agora=exp + 1))
        # vencido: nem o certo funciona depois
        self.assertIsNone(par.trocar_codigo(self.d, cod, "", "", agora=exp - 1))

    def test_errado_nao_gasta_o_certo(self):
        cod, _ = par.novo_codigo(self.d)
        self.assertIsNone(par.trocar_codigo(self.d, "AAAA-AAAA", "", ""))
        self.assertTrue(par.trocar_codigo(self.d, cod, "", ""))

    def test_novo_codigo_invalida_o_anterior(self):
        a, _ = par.novo_codigo(self.d)
        b, _ = par.novo_codigo(self.d)
        self.assertIsNone(par.trocar_codigo(self.d, a, "", ""))
        self.assertTrue(par.trocar_codigo(self.d, b, "", "") or par.trocar_codigo(self.d, b, "", "") is None)

    def test_cookie_so_como_hash(self):
        cod, _ = par.novo_codigo(self.d)
        cookie = par.trocar_codigo(self.d, cod, "Mozilla iPhone Safari/605", "10.0.0.7")
        aid, segredo = cookie.split(".", 1)
        arq = os.path.join(par.pasta(self.d), "aparelhos", aid + ".json")
        with open(arq, encoding="utf-8") as f:
            bruto = f.read()
        self.assertNotIn(segredo, bruto)
        self.assertEqual(json.loads(bruto)["nome"], "iPhone - Safari")
        self.assertIsNotNone(par.aparelho_do_cookie(self.d, cookie))
        for ruim in (aid + ".errado", "x." + segredo, "", None, aid, "../../etc." + segredo, aid + "." + "a" * 500):
            self.assertIsNone(par.aparelho_do_cookie(self.d, ruim), ruim)

    def test_remover_vale_na_hora(self):
        cod, _ = par.novo_codigo(self.d)
        cookie = par.trocar_codigo(self.d, cod, "", "")
        self.assertTrue(par.remover_aparelho(self.d, cookie.split(".")[0]))
        self.assertIsNone(par.aparelho_do_cookie(self.d, cookie))
        self.assertFalse(par.remover_aparelho(self.d, "../codigo"))

    def test_cookie_vence_em_180_dias(self):
        cod, _ = par.novo_codigo(self.d, agora=1000)
        cookie = par.trocar_codigo(self.d, cod, "", "", agora=1001)
        self.assertIsNotNone(par.aparelho_do_cookie(self.d, cookie, agora=1002))
        self.assertIsNone(par.aparelho_do_cookie(self.d, cookie, agora=1001 + par.COOKIE_VALIDADE + 5))


class FreioDeTentativas(unittest.TestCase):
    def test_bloqueia_ip_e_queima_codigo(self):
        t = [1000.0]
        f = par.Freio(relogio=lambda: t[0])
        for _ in range(4):
            self.assertFalse(f.falhou("1.1.1.1"))
        self.assertEqual(f.bloqueado("1.1.1.1"), 0)
        f.falhou("1.1.1.1")
        self.assertGreater(f.bloqueado("1.1.1.1"), 0)
        t[0] += 301
        self.assertEqual(f.bloqueado("1.1.1.1"), 0)
        # 10 erros no total (de varios IPs) queimam o codigo
        queimou = [f.falhou("2.2.2.%d" % i) for i in range(10)]
        self.assertTrue(any(queimou))


if __name__ == "__main__":
    unittest.main()
