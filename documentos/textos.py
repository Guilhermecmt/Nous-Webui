# -*- coding: utf-8 -*-
"""
Texto de um arquivo que o usuario escolheu (v2.9): .txt/.md/.csv/.json,
.docx (docx2txt), .pdf (pypdf) e .html (bs4) - tudo ja' vem no venv do Open WebUI.

Usado pelos Documentos (abrir arquivo) e pela Memoria (importar o que voce
ja' escreveu sobre si). extrair() devolve (texto, aviso); aviso != "" quando
o arquivo nao tem texto (PDF escaneado, por exemplo).
"""
import io
import os
import re

MAX_BYTES = 20 * 1024 * 1024   # o monitor aceita ate 20 MB por pedido
TIPOS = (".txt", ".md", ".markdown", ".csv", ".json", ".docx", ".pdf", ".html", ".htm")


def _decode(dados):
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return dados.decode(enc)
        except UnicodeDecodeError:
            continue
    return dados.decode("utf-8", "replace")


def extrair(nome, dados):
    ext = os.path.splitext((nome or "").lower())[1]
    if len(dados or b"") > MAX_BYTES:
        raise ValueError("arquivo maior que 20 MB")
    if ext not in TIPOS:
        raise ValueError("tipo de arquivo nao suportado (use .txt, .md, .docx, .pdf ou .html)")
    if ext == ".docx":
        import docx2txt
        texto = docx2txt.process(io.BytesIO(dados))
    elif ext == ".pdf":
        from pypdf import PdfReader
        try:
            r = PdfReader(io.BytesIO(dados))
            texto = "\n\n".join((p.extract_text() or "").strip() for p in r.pages)
        except Exception:
            raise ValueError("nao consegui abrir este PDF (protegido ou corrompido?)")
    elif ext in (".html", ".htm"):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(_decode(dados), "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        texto = soup.get_text("\n")
    else:
        texto = _decode(dados)
    texto = re.sub(r"[ \t]+\n", "\n", texto.replace("\r\n", "\n").replace("\r", "\n"))
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    aviso = ""
    if not texto:
        aviso = ("Nao achei texto neste arquivo." +
                 (" Se for um PDF escaneado (foto do papel), mande a imagem no chat: o Nous le com OCR."
                  if ext == ".pdf" else ""))
    return texto, aviso
