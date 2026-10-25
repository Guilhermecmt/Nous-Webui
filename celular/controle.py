# -*- coding: utf-8 -*-
"""
Nous - "Usar no celular": o lado do computador (rotas /celular/* do monitor, 8990).

Liga e desliga o portao (nous_celular.py), cria/remove a regra do firewall, gera o
QR com o codigo de uso unico e lista/remove os aparelhos pareados.

  GET  /celular/estado                 -> ligado?, endereco, rede, firewall, codigo, aparelhos
  POST /celular/ligar                  -> confere a rede, firewall (pede permissao) e sobe o portao
  POST /celular/desligar               -> derruba o portao e tira a regra do firewall
  POST /celular/codigo                 -> novo codigo de uso unico + QR (svg em base64)
  POST /celular/aparelhos/remover      {id}
  POST /celular/aparelhos/remover-todos
  POST /celular/abrir-rede             abre as Configuracoes de rede do Windows

So' o computador pode usar isto: o portao nao repassa /celular/* e o monitor recusa
qualquer pedido que traga o cabecalho X-Nous-Portao.

Modo de simulacao (NOUS_CELULAR_SIMULAR=1, para testes): nada e' mudado no Windows;
o firewall so' escreve o comando que EXECUTARIA em NousData\\celular\\simulado.log.
NOUS_CELULAR_PERFIL_SIMULADO=Public faz a rede parecer Publica.
"""
import asyncio
import base64
import io
import json
import os
import socket
import subprocess
import sys
import time

from aiohttp import web

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import pareamento as par  # noqa: E402

PORTA = 8999
REGRA = "Nous - Usar no celular"
SEM_JANELA = 0x08000000      # CREATE_NO_WINDOW
DESANEXADO = 0x00000008      # DETACHED_PROCESS
NOVO_GRUPO = 0x00000200

_trava = None   # criada no loop (ver _lock)


def _porta():
    return int(os.environ.get("NOUS_CELULAR_PORT", PORTA))


def simulando():
    return os.environ.get("NOUS_CELULAR_SIMULAR") == "1"


def _raiz():
    return os.path.dirname(_HERE)


def _script_firewall():
    return os.path.join(_raiz(), "launchers", "celular-firewall.ps1")


def _ps(args, tempo=90):
    """Roda o PowerShell sem janela. Devolve (codigo, stdout)."""
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"] + args,
                           capture_output=True, text=True, timeout=tempo, creationflags=SEM_JANELA,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


# ------------------------------------------------------------------ rede
def ip_da_rede():
    """O IP do PC na rede de casa: o da interface que sai para a internet (nada e' enviado)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except OSError:
        ip = None
    finally:
        s.close()
    return ip if ip and par.ip_permitido(ip) else None


def outros_ips(principal):
    achados = []
    try:
        for r in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = r[4][0]
            if ip != principal and par.ip_permitido(ip) and not ip.startswith("169.254.") and ip not in achados:
                achados.append(ip)
    except OSError:
        pass
    return achados


def _firewall(acao, ip=None):
    """Chama launchers\\celular-firewall.ps1 e devolve o JSON dele."""
    args = ["-File", _script_firewall(), "-Acao", acao, "-Porta", str(_porta()), "-Dados", par.pasta(_dados())]
    if ip:
        args += ["-Ip", ip]
    prog = _programa()
    if prog:
        args += ["-Programa", prog]
    if simulando():
        args += ["-Simular"]
        if os.environ.get("NOUS_CELULAR_PERFIL_SIMULADO"):
            args += ["-PerfilSimulado", os.environ["NOUS_CELULAR_PERFIL_SIMULADO"]]
    cod, out = _ps(args, tempo=180)
    for linha in reversed((out or "").strip().splitlines()):
        linha = linha.strip()
        if linha.startswith("{"):
            try:
                return json.loads(linha)
            except ValueError:
                break
    return {"erro": "O Windows nao respondeu (%s)" % (out or "").strip()[:120], "regra": False}


def _programa():
    """O programa que de fato escuta (o Python base do venv: o python.exe do venv e' so'
    um redirecionador). Vazio = regra so' por porta."""
    b = getattr(sys, "_base_executable", None) or sys.executable
    return b if b and os.path.exists(b) else ""


_DADOS = {"dir": None}


def _dados():
    return _DADOS["dir"]


# ------------------------------------------------------------------ processo do portao
def _vivo(pid):
    try:
        import psutil
        p = psutil.Process(int(pid))
        return "nous_celular" in " ".join(p.cmdline())
    except Exception:  # noqa: BLE001
        return False


def _ler_estado(dd):
    d = par._ler(os.path.join(par.pasta(dd), "estado.json"))
    if d and d.get("pid") and _vivo(d["pid"]):
        return d
    return None


def _responde(porta):
    try:
        c = socket.create_connection(("127.0.0.1", porta), timeout=0.6)
        c.close()
        return True
    except OSError:
        return False


async def _estado_completo(dd, com_rede=True):
    loop = asyncio.get_running_loop()
    st = _ler_estado(dd)
    ligado = bool(st) and _responde(st.get("porta", _porta()))
    ip = ip_da_rede()
    r = {"ligado": ligado, "simulacao": simulando(), "porta": _porta(), "ip": ip,
         "url": ("http://%s:%d" % (ip, _porta())) if ip else None, "outros_ips": outros_ips(ip) if ip else [],
         "aparelhos": par.listar_aparelhos(dd), "codigo_expira": par.codigo_vigente(dd), "agora": time.time(),
         "perfil": None, "regra": None}
    if com_rede:
        fw = await loop.run_in_executor(None, _firewall, "Estado", ip)
        r["perfil"] = fw.get("perfil")
        r["regra"] = bool(fw.get("regra"))
    return r


def _lock():
    if _trava is None:
        globals()["_trava"] = asyncio.Lock()
    return _trava


def _matar(pid):
    try:
        import psutil
        p = psutil.Process(int(pid))
        p.terminate()
        try:
            p.wait(5)
        except Exception:  # noqa: BLE001
            p.kill()
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------ QR
def qr_base64(texto):
    import qrcode
    import qrcode.image.svg
    img = qrcode.make(texto, image_factory=qrcode.image.svg.SvgPathImage, border=2,
                      error_correction=qrcode.constants.ERROR_CORRECT_M)
    buf = io.BytesIO()
    img.save(buf)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ------------------------------------------------------------------ rotas
def add_routes(app, data_dir_fn):
    def dd():
        d = str(data_dir_fn())
        _DADOS["dir"] = d
        return d

    async def corpo(request):
        try:
            b = await request.json()
            return b if isinstance(b, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    @web.middleware
    async def so_computador(request, handler):
        if request.path.startswith("/celular") and request.headers.get("X-Nous-Portao"):
            return web.json_response({"erro": "Isto so' funciona no computador."}, status=403)
        return await handler(request)

    app.middlewares.insert(0, so_computador)

    async def h_estado(request):
        return web.json_response(await _estado_completo(dd()))

    async def h_ligar(request):
        d = dd()
        async with _lock():
            loop = asyncio.get_running_loop()
            ja = _ler_estado(d)
            if ja and _responde(ja.get("porta", _porta())):
                return web.json_response(await _estado_completo(d))
            ip = ip_da_rede()
            if not ip:
                return web.json_response({"erro": "sem_rede", "texto": "O computador nao parece estar ligado a uma rede (Wi-Fi ou cabo). "
                                          "Conecte-o a mesma rede do celular e tente de novo."}, status=409)
            fw = await loop.run_in_executor(None, _firewall, "Estado", ip)
            if fw.get("perfil") and fw["perfil"] != "Private":
                return web.json_response({"erro": "rede_publica", "perfil": fw["perfil"], "texto":
                                          "O Windows trata esta rede como Publica (a mais fechada, usada em cafes e hoteis). "
                                          "Por seguranca o Nous so' abre o celular em rede Privada. Se esta e' a sua rede de casa, "
                                          "mude o tipo da rede para Privada nas configuracoes do Windows e tente de novo."}, status=409)
            if not fw.get("regra"):
                fw = await loop.run_in_executor(None, _firewall, "Criar", ip)
                if not fw.get("regra"):
                    return web.json_response({"erro": "sem_permissao", "texto":
                                              "O Windows nao liberou a porta. Sem essa permissao o celular nao consegue chegar ao Nous. "
                                              "Tente de novo e escolha Sim quando o Windows pedir."}, status=409)
            cmd = [sys.executable, os.path.join(_HERE, "nous_celular.py"), "--data-dir", d, "--porta", str(_porta())]
            if os.environ.get("NOUS_CELULAR_HOST"):
                cmd += ["--host", os.environ["NOUS_CELULAR_HOST"]]
            if os.environ.get("NOUS_CELULAR_MODO_TESTE") == "1":
                cmd += ["--modo-teste"]
            os.makedirs(par.pasta(d), exist_ok=True)
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=SEM_JANELA | NOVO_GRUPO | DESANEXADO, close_fds=True)
            for _ in range(40):
                await asyncio.sleep(0.25)
                st = _ler_estado(d)
                if st and _responde(st.get("porta", _porta())):
                    break
            else:
                return web.json_response({"erro": "nao_subiu", "texto": "O portao do celular nao abriu. Veja se outro programa "
                                          "usa a porta %d." % _porta()}, status=500)
        return web.json_response(await _estado_completo(d))

    async def h_desligar(request):
        d = dd()
        async with _lock():
            loop = asyncio.get_running_loop()
            st = _ler_estado(d)
            if st:
                _matar(st["pid"])
            try:
                os.remove(os.path.join(par.pasta(d), "estado.json"))
            except OSError:
                pass
            par.queimar_codigo(d)
            fw = await loop.run_in_executor(None, _firewall, "Remover", None)
        r = await _estado_completo(d, com_rede=False)
        r["regra"] = bool(fw.get("regra"))
        r["regra_ficou"] = bool(fw.get("regra"))
        return web.json_response(r)

    async def h_codigo(request):
        d = dd()
        st = _ler_estado(d)
        ip = ip_da_rede()
        if not st or not ip:
            return web.json_response({"erro": "desligado", "texto": "Ligue o celular primeiro."}, status=409)
        cod, expira = par.novo_codigo(d)
        url = "http://%s:%d/_portao/parear#%s" % (ip, st.get("porta", _porta()), cod.replace("-", ""))
        try:
            qr = qr_base64(url)
        except Exception:  # noqa: BLE001
            qr = None
        return web.json_response({"codigo": cod, "expira": expira, "agora": time.time(), "qr": qr,
                                  "endereco": "http://%s:%d" % (ip, st.get("porta", _porta()))})

    async def h_remover(request):
        b = await corpo(request)
        return web.json_response({"ok": par.remover_aparelho(dd(), b.get("id")), "aparelhos": par.listar_aparelhos(dd())})

    async def h_remover_todos(request):
        n = par.remover_todos(dd())
        return web.json_response({"ok": True, "removidos": n, "aparelhos": []})

    async def h_rede(request):
        if not simulando():
            subprocess.Popen(["cmd.exe", "/c", "start", "", "ms-settings:network-wifi"], creationflags=SEM_JANELA)
        return web.json_response({"ok": True})

    app.add_routes([web.get("/celular/estado", h_estado), web.post("/celular/ligar", h_ligar),
                    web.post("/celular/desligar", h_desligar), web.post("/celular/codigo", h_codigo),
                    web.post("/celular/aparelhos/remover", h_remover),
                    web.post("/celular/aparelhos/remover-todos", h_remover_todos),
                    web.post("/celular/abrir-rede", h_rede)])
