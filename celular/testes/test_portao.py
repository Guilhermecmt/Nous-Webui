# -*- coding: utf-8 -*-
"""Portao do celular: IP, Host, CSRF, pareamento, freio, streaming, WebSocket e servicos.
Um Open WebUI e um servico de mentira rodam em portas livres; nada sai do computador.
O IP de origem vem do cabecalho X-Teste-Ip (so' existe com --modo-teste)."""
import asyncio
import gzip
import os
import sys
import tempfile
import unittest

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import nous_celular as portao  # noqa: E402
import pareamento as par  # noqa: E402

CASA = {"X-Teste-Ip": "192.168.1.20"}


def upstream_falso(visto):
    """Faz de conta de Open WebUI / servico: devolve o que recebeu para o teste conferir."""
    async def eco(request):
        visto.append({"metodo": request.method, "path": request.raw_path, "host": request.host,
                      "origin": request.headers.get("Origin"), "cookie": request.headers.get("Cookie"),
                      "xnp": request.headers.get("X-Nous-Portao"), "xff": request.headers.get("X-Forwarded-For")})
        corpo = await request.read()
        r = web.json_response({"ok": True, "tam": len(corpo)})
        r.set_cookie("sessao", "abc", httponly=True)
        r.set_cookie("outra", "def")
        return r

    async def fluxo(request):
        r = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await r.prepare(request)
        for i in range(3):
            await r.write(("data: %d\n\n" % i).encode())
            await asyncio.sleep(0.4)
        return r

    async def zip_(request):
        return web.Response(body=gzip.compress(b"ola " * 100), headers={"Content-Encoding": "gzip", "Content-Type": "text/plain"})

    async def vai(request):
        raise web.HTTPFound("http://127.0.0.1:%d/destino" % portao.OWUI)

    async def ws(request):
        w = web.WebSocketResponse()
        await w.prepare(request)
        visto.append({"ws_origin": request.headers.get("Origin"), "ws_cookie": request.headers.get("Cookie")})
        async for m in w:
            await w.send_str("eco:" + m.data)
        return w

    app = web.Application(client_max_size=0)
    app.add_routes([web.get("/fluxo", fluxo), web.get("/zip", zip_), web.get("/vai", vai), web.get("/ws", ws),
                    web.route("*", "/{x:.*}", eco)])
    return app


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = self._t.name
        self.visto = []
        self.up = TestServer(upstream_falso(self.visto), host="127.0.0.1")
        await self.up.start_server()
        self.svc = TestServer(upstream_falso(self.visto), host="127.0.0.1")
        await self.svc.start_server()
        self._old = (portao.OWUI, portao.UPSTREAM_ORIGEM, portao.SERVICOS)
        portao.OWUI = self.up.port
        portao.UPSTREAM_ORIGEM = "http://127.0.0.1:%d" % self.up.port
        portao.SERVICOS = (self.svc.port, 8990)
        self.gw = TestServer(portao.build_app(self.d, teste=True), host="127.0.0.1")
        await self.gw.start_server()
        # o celular de verdade chega com Host = IP do PC na rede de casa; aqui o teste finge isso
        self.host = "192.168.1.5:%d" % self.gw.port
        self.sess = aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar(), auto_decompress=False,
                                          headers={"Host": self.host})
        self.base = "http://127.0.0.1:%d" % self.gw.port

    async def asyncTearDown(self):
        await self.sess.close()
        await self.gw.close()
        await self.svc.close()
        await self.up.close()
        portao.OWUI, portao.UPSTREAM_ORIGEM, portao.SERVICOS = self._old
        self._t.cleanup()

    async def parear(self, ip="192.168.1.20", ua="Mozilla/5.0 (Linux; Android 14) Chrome/120"):
        cod, _ = par.novo_codigo(self.d)
        return await self.trocar(cod, ip, ua)

    async def trocar(self, cod, ip="192.168.1.20", ua="Mozilla/5.0 (Linux; Android 14) Chrome/120", origin=True):
        h = {"X-Teste-Ip": ip, "X-Nous-Portao": "1", "User-Agent": ua}
        if origin:
            h["Origin"] = "http://" + self.host
        return await self.sess.post(self.base + "/_portao/trocar", json={"codigo": cod}, headers=h)

    def cookie(self, resp):
        return resp.cookies[par.COOKIE].value

    def h(self, ck, **mais):
        d = dict(CASA)
        d["Cookie"] = "%s=%s" % (par.COOKIE, ck)
        d.update(mais)
        return d


class Entrada(Base):
    async def test_ip_fora_da_rede_de_casa(self):
        for ip in ("8.8.8.8", "172.32.0.1", "127.0.0.1", "2001:4860::1", "::1"):
            r = await self.sess.get(self.base + "/", headers={"X-Teste-Ip": ip, "Accept": "text/html"})
            self.assertEqual(r.status, 403, ip)
        for ip in ("192.168.1.20", "10.1.1.1", "172.20.0.5", "fd00::5", "fe80::9"):
            r = await self.sess.get(self.base + "/", headers={"X-Teste-Ip": ip, "Accept": "text/html"})
            self.assertEqual(r.status, 401, ip)       # entra no portao, mas sem cookie so' ve' o pareamento

    async def test_host_estranho(self):
        r = await self.sess.get(self.base + "/", headers={**CASA, "Host": "evil.example:8999"})
        self.assertEqual(r.status, 403)

    async def test_sem_cookie_so_ve_a_pagina_de_parear(self):
        r = await self.sess.get(self.base + "/", headers={**CASA, "Accept": "text/html"})
        self.assertEqual(r.status, 401)
        self.assertIn("ligado ao seu Nous", await r.text())
        r = await self.sess.get(self.base + "/api/chats", headers=CASA)
        self.assertEqual(r.status, 401)
        r = await self.sess.get(self.base + "/_nous/%d/stats" % self.svc.port, headers=CASA)
        self.assertEqual(r.status, 401)
        r = await self.sess.get(self.base + "/_portao/parear", headers=CASA)
        self.assertEqual(r.status, 200)
        r = await self.sess.get(self.base + "/_portao/qualquer-outra", headers=CASA)
        self.assertEqual(r.status, 404)
        self.assertEqual(self.visto, [], "nada pode ter chegado ao Open WebUI")

    async def test_saude_so_do_proprio_pc(self):
        r = await self.sess.get(self.base + "/_portao/saude", headers={"X-Teste-Ip": "127.0.0.1"})
        self.assertEqual(r.status, 200)
        r = await self.sess.get(self.base + "/_portao/saude", headers={"X-Teste-Ip": "8.8.8.8"})
        self.assertEqual(r.status, 403)


class Pareamento(Base):
    async def test_fluxo_completo(self):
        r = await self.parear()
        self.assertEqual(r.status, 200)
        sc = r.headers["Set-Cookie"]
        self.assertIn("HttpOnly", sc)
        self.assertIn("SameSite=Strict", sc)
        self.assertIn("Max-Age=", sc)
        ck = self.cookie(r)
        r2 = await self.sess.get(self.base + "/api/config?x=1&y=%C3%A9", headers=self.h(ck))
        self.assertEqual(r2.status, 200)
        v = self.visto[-1]
        self.assertEqual(v["host"], "127.0.0.1:%d" % self.up.port)
        self.assertEqual(v["path"], "/api/config?x=1&y=%C3%A9")
        self.assertNotIn(par.COOKIE, v["cookie"] or "")
        self.assertIsNone(v["xff"])
        # os dois Set-Cookie do Open WebUI chegam ao celular
        self.assertEqual({c.key for c in r2.cookies.values()}, {"sessao", "outra"})

    async def test_codigo_vale_uma_vez(self):
        cod, _ = par.novo_codigo(self.d)
        self.assertEqual((await self.trocar(cod)).status, 200)
        self.assertEqual((await self.trocar(cod)).status, 400)

    async def test_csrf_na_troca(self):
        cod, _ = par.novo_codigo(self.d)
        r = await self.sess.post(self.base + "/_portao/trocar", json={"codigo": cod},
                                 headers={**CASA, "X-Nous-Portao": "1", "Origin": "http://evil.example"})
        self.assertEqual(r.status, 403)
        r = await self.sess.post(self.base + "/_portao/trocar", data="codigo=" + cod,
                                 headers={**CASA, "Origin": "http://" + self.host, "Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(r.status, 400)       # sem JSON e sem o cabecalho proprio
        self.assertEqual((await self.trocar(cod)).status, 200, "o codigo nao foi gasto pelos pedidos barrados")

    async def test_csrf_com_cookie_valido(self):
        ck = self.cookie(await self.parear())
        antes = len(self.visto)
        r = await self.sess.post(self.base + "/api/v1/chats/new", json={}, headers=self.h(ck, Origin="http://evil.example"))
        self.assertEqual(r.status, 403)
        r = await self.sess.post(self.base + "/api/v1/chats/new", json={}, headers=self.h(ck, **{"Sec-Fetch-Site": "cross-site"}))
        self.assertEqual(r.status, 403)
        self.assertEqual(len(self.visto), antes, "nada chegou ao Open WebUI")
        r = await self.sess.post(self.base + "/api/v1/chats/new", json={}, headers=self.h(ck, Origin="http://" + self.host))
        self.assertEqual(r.status, 200)
        self.assertEqual(self.visto[-1]["origin"], portao.UPSTREAM_ORIGEM)

    async def test_forca_bruta_por_ip(self):
        par.novo_codigo(self.d)
        for _ in range(5):
            self.assertEqual((await self.trocar("AAAA-AAAA", ip="192.168.1.77")).status, 400)
        r = await self.trocar("AAAA-AAAA", ip="192.168.1.77")
        self.assertEqual(r.status, 429)
        self.assertIn("Retry-After", r.headers)

    async def test_forca_bruta_queima_o_codigo(self):
        cod, _ = par.novo_codigo(self.d)
        for i in range(10):
            await self.trocar("AAAA-AAA%d" % (i % 9 + 2), ip="192.168.1.%d" % (100 + i))
        self.assertEqual((await self.trocar(cod, ip="192.168.1.200")).status, 400, "codigo queimado depois de 10 erros")

    async def test_remover_aparelho_corta_na_hora(self):
        r = await self.parear()
        ck = self.cookie(r)
        self.assertEqual((await self.sess.get(self.base + "/x", headers=self.h(ck))).status, 200)
        par.remover_aparelho(self.d, ck.split(".")[0])
        self.assertEqual((await self.sess.get(self.base + "/x", headers=self.h(ck))).status, 401)

    async def test_codigo_vencido(self):
        cod, exp = par.novo_codigo(self.d, agora=1.0)
        self.assertEqual((await self.trocar(cod)).status, 400)


class Repasse(Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.ck = self.cookie(await self.parear())

    async def test_streaming_nao_e_bufferizado(self):
        t0 = asyncio.get_event_loop().time()
        r = await self.sess.get(self.base + "/fluxo", headers=self.h(self.ck))
        primeiro = await r.content.readany()
        t1 = asyncio.get_event_loop().time() - t0
        resto = await r.content.read()
        t2 = asyncio.get_event_loop().time() - t0
        self.assertIn(b"data: 0", primeiro)
        self.assertLess(t1, 0.35, "o primeiro pedaco tem que chegar antes do fim")
        self.assertGreater(t2, 0.7)
        self.assertIn(b"data: 2", primeiro + resto)

    async def test_compressao_e_redirecionamento(self):
        r = await self.sess.get(self.base + "/zip", headers=self.h(self.ck, **{"Accept-Encoding": "gzip"}))
        self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
        self.assertEqual(gzip.decompress(await r.read()), b"ola " * 100)
        r = await self.sess.get(self.base + "/vai", headers=self.h(self.ck), allow_redirects=False)
        self.assertEqual(r.status, 302)
        self.assertEqual(r.headers["Location"], "/destino")

    async def test_upload_grande(self):
        dados = os.urandom(6 * 1024 * 1024)
        r = await self.sess.post(self.base + "/api/v1/files/", data=dados,
                                 headers=self.h(self.ck, Origin="http://" + self.host, **{"Content-Type": "application/octet-stream"}))
        self.assertEqual((await r.json())["tam"], len(dados))

    async def test_websocket(self):
        async with self.sess.ws_connect(self.base + "/ws", headers=self.h(self.ck, Origin="http://" + self.host)) as w:
            await w.send_str("oi")
            self.assertEqual((await w.receive_str()), "eco:oi")
        v = [x for x in self.visto if "ws_origin" in x][-1]
        self.assertEqual(v["ws_origin"], portao.UPSTREAM_ORIGEM)
        self.assertNotIn(par.COOKIE, v["ws_cookie"] or "")

    async def test_websocket_de_outro_site(self):
        with self.assertRaises(aiohttp.WSServerHandshakeError) as e:
            async with self.sess.ws_connect(self.base + "/ws", headers=self.h(self.ck, Origin="http://evil.example")):
                pass
        self.assertEqual(e.exception.status, 403)
        with self.assertRaises(aiohttp.WSServerHandshakeError) as e:
            async with self.sess.ws_connect(self.base + "/ws", headers=self.h(self.ck)):
                pass     # sem Origin
        self.assertEqual(e.exception.status, 403)

    async def test_servicos_pela_mesma_origem(self):
        p = self.svc.port
        r = await self.sess.get(self.base + "/_nous/%d/stats?a=1" % p, headers=self.h(self.ck))
        self.assertEqual(r.status, 200)
        v = self.visto[-1]
        self.assertEqual((v["path"], v["host"], v["xnp"], v["cookie"]), ("/stats?a=1", "127.0.0.1:%d" % p, "1", None))
        r = await self.sess.post(self.base + "/_nous/%d/pull" % p, json={}, headers=self.h(self.ck, Origin="http://" + self.host))
        self.assertEqual(r.status, 200)
        self.assertIsNone(self.visto[-1]["origin"], "o servico nao ve Origin")

    async def test_so_os_servicos_do_nous(self):
        for porta in (8998, 11434, 8080, 22):
            r = await self.sess.get(self.base + "/_nous/%d/" % porta, headers=self.h(self.ck))
            self.assertEqual(r.status, 404, porta)

    async def test_controle_do_celular_nao_passa(self):
        antes = len(self.visto)
        for caminho in ("celular/estado", "celular", "%63elular/estado", "/celular/estado", "./celular/estado",
                        "x/../celular/estado", "CELULAR/ligar", "%2e/celular/estado"):
            r = await self.sess.get(self.base + "/_nous/8990/" + caminho, headers=self.h(self.ck))
            self.assertEqual(r.status, 403, caminho)
        self.assertEqual(len(self.visto), antes)

    async def test_open_webui_fora_do_ar(self):
        await self.up.close()
        r = await self.sess.get(self.base + "/", headers=self.h(self.ck))
        self.assertEqual(r.status, 502)
        self.assertIn("Abra o Nous", await r.text())


if __name__ == "__main__":
    unittest.main()
