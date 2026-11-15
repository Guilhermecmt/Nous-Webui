"""Baixa e apaga modelos sem o Ollama, no mesmo layout de pasta e com os mesmos eventos do /api/pull.

O registro do Ollama fala o protocolo de registry do Docker: manifesto em
/v2/<ns>/<modelo>/manifests/<tag> e blobs em /v2/<ns>/<modelo>/blobs/<digest>
(com redirecionamento para a CDN). Cada blob e' gravado como sha256-<hex>-partial,
retomado com Range se ja' existir, conferido pelo sha256 e so' entao renomeado.
O manifesto e' gravado por ultimo: modelo pela metade nunca aparece no /api/tags.
"""
import asyncio
import hashlib
import json
import os
import time

import aiohttp

import registro

PADRAO = "https://registry.ollama.ai"
ACEITA = "application/vnd.docker.distribution.manifest.v2+json"
_travas = {}


def _caminho_blob(pasta, digest):
    return os.path.join(pasta, "blobs", digest.replace(":", "-"))


def _partes(nome):
    n = registro.normalizar_nome(nome)
    base, _, tag = n.rpartition(":")
    p = base.split("/")
    if len(p) == 1:
        return None, "library/" + p[0], tag
    if len(p) == 2:
        return None, base, tag
    return p[0], "/".join(p[1:]), tag


def _sha_arquivo(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


async def _baixar_blob(s, base, repo, camada, pasta):
    dig, total = camada["digest"], int(camada.get("size") or 0)
    final = _caminho_blob(pasta, dig)
    status = "pulling " + dig[7:19]
    if os.path.isfile(final):
        yield {"status": status, "digest": dig, "total": total, "completed": total}
        return
    parcial = final + "-partial"
    feito = os.path.getsize(parcial) if os.path.isfile(parcial) else 0
    if total and feito > total:
        os.remove(parcial)
        feito = 0
    yield {"status": status, "digest": dig, "total": total, "completed": feito}
    if not total or feito < total:
        cab = {"Range": "bytes=%d-" % feito} if feito else {}
        async with s.get("%s/v2/%s/blobs/%s" % (base, repo, dig), headers=cab) as r:
            if r.status not in (200, 206):
                raise RuntimeError("o registro respondeu %d ao baixar %s" % (r.status, dig[:19]))
            if feito and r.status == 200:
                feito = 0  # servidor ignorou o Range: recomeca
            ultimo = time.monotonic()
            with open(parcial, "ab" if feito else "wb") as f:
                async for pedaco in r.content.iter_chunked(1 << 20):
                    f.write(pedaco)
                    feito += len(pedaco)
                    if time.monotonic() - ultimo > 0.25:
                        ultimo = time.monotonic()
                        yield {"status": status, "digest": dig, "total": total, "completed": feito}
    yield {"status": status, "digest": dig, "total": total, "completed": feito}


async def puxar(pasta, nome, registry=PADRAO):
    """Gera os eventos do /api/pull do Ollama; o ultimo e' {"status":"success"} ou {"error": ...}."""
    if not registro.nome_valido(nome):
        yield {"error": "nome de modelo invalido: '%s'" % nome}
        return
    host, repo, tag = _partes(nome)
    base = ("https://" + host) if host else registry.rstrip("/")
    chave = (pasta, repo, tag)
    trava = _travas.setdefault(chave, asyncio.Lock())
    async with trava:
        try:
            os.makedirs(os.path.join(pasta, "blobs"), exist_ok=True)
            yield {"status": "pulling manifest"}
            tempo = aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=120)
            async with aiohttp.ClientSession(timeout=tempo) as s:
                async with s.get("%s/v2/%s/manifests/%s" % (base, repo, tag), headers={"Accept": ACEITA}) as r:
                    if r.status == 404:
                        yield {"error": "o modelo '%s' nao existe no registro" % registro.normalizar_nome(nome)}
                        return
                    if r.status != 200:
                        yield {"error": "o registro respondeu %d para '%s'" % (r.status, nome)}
                        return
                    bruto = await r.read()
                man = json.loads(bruto)
                camadas = list(man.get("layers") or [])
                if man.get("config", {}).get("digest"):
                    camadas.append(man["config"])
                for c in camadas:
                    async for ev in _baixar_blob(s, base, repo, c, pasta):
                        yield ev
            yield {"status": "verifying sha256 digest"}
            for c in camadas:
                final = _caminho_blob(pasta, c["digest"])
                if os.path.isfile(final):
                    continue
                parcial = final + "-partial"
                if _sha_arquivo(parcial) != c["digest"][7:]:
                    os.remove(parcial)
                    yield {"error": "o arquivo %s chegou corrompido (sha256 diferente); tente de novo" % c["digest"][:19]}
                    return
                os.replace(parcial, final)
            yield {"status": "writing manifest"}
            destino = registro.caminho_manifesto(pasta, nome)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino + ".tmp", "wb") as f:
                f.write(bruto)
            os.replace(destino + ".tmp", destino)
            yield {"status": "success"}
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError, RuntimeError) as e:
            yield {"error": "falha ao baixar '%s': %s" % (nome, e or type(e).__name__)}


def _digests(caminho_man):
    try:
        with open(caminho_man, encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError):
        return set()
    ds = {c.get("digest") for c in man.get("layers") or []}
    if man.get("config", {}).get("digest"):
        ds.add(man["config"]["digest"])
    return {d for d in ds if d}


def apagar(pasta, nome):
    """Apaga o manifesto e os blobs que nenhum outro manifesto usa. False se o modelo nao existe."""
    if not registro.nome_valido(nome):
        return False
    alvo = registro.caminho_manifesto(pasta, nome)
    if not os.path.isfile(alvo):
        return False
    meus = _digests(alvo)
    os.remove(alvo)
    em_uso = set()
    for _, c in registro._manifestos(pasta):
        em_uso |= _digests(c)
    for d in meus - em_uso:
        try:
            os.remove(_caminho_blob(pasta, d))
        except OSError:
            pass
    d = os.path.dirname(alvo)
    raiz = os.path.join(pasta, "manifests")
    while d.startswith(raiz) and d != raiz:
        try:
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)
    return True
