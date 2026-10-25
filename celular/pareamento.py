# -*- coding: utf-8 -*-
"""
Nous - "Usar no celular": pareamento e lista de aparelhos.

Usado pelos dois lados: o portao (nous_celular.py, que troca o codigo por um
cookie) e o monitor (controle.py, que gera o codigo e mostra/remove aparelhos).
Os dois conversam so' por arquivos em NousData\\celular, escritos de forma que
nunca dois processos escrevam o mesmo arquivo:

  codigo.json            o codigo de uso unico em vigor (so' o hash). O monitor
                         cria; o portao apaga ao usar. Um por vez.
  aparelhos\\<id>.json   um arquivo por aparelho pareado: nome, hash do cookie,
                         datas. O portao cria; o monitor apaga ("Remover").
                         O cookie em si (o segredo) nunca fica no disco.

Sem dependencia nova: so' a biblioteca padrao.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import time

COOKIE = "nous_cel"
CODIGO_VALIDADE = 300            # segundos: o QR vale 5 minutos
COOKIE_VALIDADE = 180 * 86400    # o aparelho fica pareado por 180 dias
# sem 0/O/1/I/L: dito em voz alta ou digitado sem confusao (31 simbolos x 8 = ~40 bits)
ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAM_CODIGO = 8
ATUALIZA_USO = 60                # grava "ultimo uso" no maximo 1 vez por minuto


# ------------------------------------------------------------------ pastas
def pasta(data_dir):
    return os.path.join(str(data_dir), "celular")


def _pasta_aparelhos(data_dir):
    return os.path.join(pasta(data_dir), "aparelhos")


def _escrever(caminho, dados):
    """Grava o JSON de uma vez (arquivo temporario + troca): ninguem le' pela metade."""
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".%d.tmp" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    os.replace(tmp, caminho)


def _ler(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ quem pode entrar
def ip_permitido(ip):
    """So' rede de casa: IPv4 privado (RFC 1918) ou link-local (169.254/16) e IPv6
    ULA (fc00::/7) ou link-local (fe80::/10). Loopback, IP publico e lixo: nao."""
    try:
        a = ipaddress.ip_address(str(ip).split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a.is_loopback or a.is_multicast or a.is_unspecified:
        return False
    if isinstance(a, ipaddress.IPv4Address):
        return any(a in ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16"))
    return a in ipaddress.ip_network("fc00::/7") or a in ipaddress.ip_network("fe80::/10")


def host_permitido(host, nomes=()):
    """O cabecalho Host so' pode ser o IP do PC na rede de casa (ou o nome dele).
    Barra DNS rebinding: um dominio de fora apontado para ca' chega com Host: dominio."""
    h = (host or "").strip().lower()
    if not h:
        return False
    if h.startswith("["):                       # [fe80::1]:8999
        h = h[1:].split("]", 1)[0]
    elif h.count(":") == 1:                     # 192.168.1.5:8999
        h = h.split(":", 1)[0]
    try:
        ipaddress.ip_address(h.split("%", 1)[0])
        return ip_permitido(h)             # e' um IP: so' vale o da rede de casa
    except ValueError:
        pass
    h = h[:-6] if h.endswith(".local") else h
    return h in {str(n).lower() for n in nomes if n}


# ------------------------------------------------------------------ codigo de uso unico
def _hash(texto):
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def normalizar_codigo(texto):
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())


def formatar_codigo(codigo):
    return codigo[:TAM_CODIGO // 2] + "-" + codigo[TAM_CODIGO // 2:]


def novo_codigo(data_dir, agora=None):
    """Cria o codigo (o anterior deixa de valer). Devolve (codigo 'ABCD-EFGH', expira_em)."""
    agora = time.time() if agora is None else agora
    cod = "".join(secrets.choice(ALFABETO) for _ in range(TAM_CODIGO))
    expira = agora + CODIGO_VALIDADE
    _escrever(os.path.join(pasta(data_dir), "codigo.json"), {"hash": _hash(cod), "expira": expira, "criado": agora})
    return formatar_codigo(cod), expira


def codigo_vigente(data_dir, agora=None):
    """Quando o codigo atual vence (epoch) ou None."""
    agora = time.time() if agora is None else agora
    d = _ler(os.path.join(pasta(data_dir), "codigo.json"))
    return d["expira"] if d and d.get("expira", 0) > agora else None


def queimar_codigo(data_dir):
    try:
        os.remove(os.path.join(pasta(data_dir), "codigo.json"))
    except OSError:
        pass


def nome_do_aparelho(ua):
    ua = ua or ""
    so = ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua
          else "Windows" if "Windows" in ua else "Mac" if "Macintosh" in ua else "Linux" if "Linux" in ua else "Aparelho")
    nav = ("Edge" if "Edg/" in ua or "EdgA/" in ua else "Firefox" if "Firefox/" in ua or "FxiOS" in ua
           else "Chrome" if "Chrome/" in ua or "CriOS" in ua else "Safari" if "Safari/" in ua else "")
    return (so + (" - " + nav if nav else "")).strip()


def trocar_codigo(data_dir, codigo, ua="", ip="", agora=None):
    """Troca o codigo pelo cookie do aparelho. Uso unico: o codigo e' apagado ANTES de
    criar o aparelho, certo ou nao o resto. Devolve o valor do cookie ou None."""
    agora = time.time() if agora is None else agora
    caminho = os.path.join(pasta(data_dir), "codigo.json")
    d = _ler(caminho)
    if not d:
        return None
    cod = normalizar_codigo(codigo)
    if len(cod) != TAM_CODIGO or d.get("expira", 0) <= agora:
        if d.get("expira", 0) <= agora:
            queimar_codigo(data_dir)
        return None
    if not hmac.compare_digest(_hash(cod), str(d.get("hash", ""))):
        return None
    try:
        os.remove(caminho)                      # quem apagar primeiro leva; o outro falha
    except OSError:
        return None
    aid = secrets.token_hex(6)
    segredo = secrets.token_urlsafe(32)         # 256 bits
    _escrever(os.path.join(_pasta_aparelhos(data_dir), aid + ".json"), {
        "id": aid, "nome": nome_do_aparelho(ua), "hash": _hash(segredo),
        "criado": agora, "ultimo_uso": agora, "ip": str(ip)})
    return aid + "." + segredo


# ------------------------------------------------------------------ aparelhos
_ID = re.compile(r"^[0-9a-f]{12}$")


def aparelho_do_cookie(data_dir, valor, agora=None):
    """O aparelho dono do cookie, ou None. Lido do disco a cada chamada: 'Remover' no PC
    vale na proxima requisicao do celular."""
    agora = time.time() if agora is None else agora
    try:
        aid, segredo = str(valor or "").split(".", 1)
    except ValueError:
        return None
    if not _ID.match(aid) or not segredo or len(segredo) > 100:
        return None
    caminho = os.path.join(_pasta_aparelhos(data_dir), aid + ".json")
    d = _ler(caminho)
    if not d or not hmac.compare_digest(_hash(segredo), str(d.get("hash", ""))):
        return None
    if agora - d.get("criado", 0) > COOKIE_VALIDADE:
        return None
    return d, caminho


def marcar_uso(caminho, d, ip, agora=None):
    agora = time.time() if agora is None else agora
    if agora - d.get("ultimo_uso", 0) >= ATUALIZA_USO or d.get("ip") != str(ip):
        d["ultimo_uso"] = agora
        d["ip"] = str(ip)
        try:
            _escrever(caminho, d)
        except OSError:
            pass


def listar_aparelhos(data_dir):
    pa = _pasta_aparelhos(data_dir)
    out = []
    try:
        nomes = os.listdir(pa)
    except OSError:
        return out
    for n in nomes:
        if n.endswith(".json"):
            d = _ler(os.path.join(pa, n))
            if d and _ID.match(str(d.get("id", ""))):
                out.append({k: d.get(k) for k in ("id", "nome", "criado", "ultimo_uso", "ip")})
    return sorted(out, key=lambda x: x.get("criado") or 0)


def remover_aparelho(data_dir, aid):
    if not _ID.match(str(aid or "")):
        return False
    try:
        os.remove(os.path.join(_pasta_aparelhos(data_dir), aid + ".json"))
        return True
    except OSError:
        return False


def remover_todos(data_dir):
    n = 0
    for a in listar_aparelhos(data_dir):
        n += 1 if remover_aparelho(data_dir, a["id"]) else 0
    return n


# ------------------------------------------------------------------ freio contra tentativa em massa
class Freio:
    """Tentativas erradas de codigo. Por IP: 5 erros = 5 minutos de espera (dobra a cada
    bloqueio, ate 1 hora). No total: 10 erros com o mesmo codigo e ele e' queimado (precisa
    gerar outro no computador); com 40 bits e codigo de 5 minutos, adivinhar nao e' viavel."""

    def __init__(self, por_ip=5, no_total=10, espera=300, relogio=time.time):
        self.por_ip, self.no_total, self.espera, self.relogio = por_ip, no_total, espera, relogio
        self.erros = {}      # ip -> (contagem, bloqueado_ate, nivel)
        self.total = 0

    def bloqueado(self, ip):
        e = self.erros.get(ip)
        agora = self.relogio()
        return max(0, int(e[1] - agora)) if e and e[1] > agora else 0

    def falhou(self, ip):
        """Devolve True se esta falha queimou o codigo."""
        agora = self.relogio()
        c, ate, nivel = self.erros.get(ip, (0, 0, 0))
        c += 1
        if c >= self.por_ip:
            ate, c, nivel = agora + min(self.espera * (2 ** nivel), 3600), 0, nivel + 1
        self.erros[ip] = (c, ate, nivel)
        if len(self.erros) > 2000:     # nao cresce sem fim
            self.erros = {k: v for k, v in self.erros.items() if v[1] > agora}
        self.total += 1
        if self.total >= self.no_total:
            self.total = 0
            return True
        return False

    def novo_codigo(self):
        self.total = 0

    def acertou(self, ip):
        self.erros.pop(ip, None)
        self.total = 0
