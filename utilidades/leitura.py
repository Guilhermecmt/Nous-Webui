# -*- coding: utf-8 -*-
"""
Leitura de arquivos para o Nous: texto de PDF, DOCX, XLSX, HTML e imagens
(OCR local com RapidOCR, que ja' vem no venv do Open WebUI), e decodificacao
de BOLETOS pela linha digitavel (regras FEBRABAN, sem IA: valor, vencimento e
banco saem dos digitos, entao nao ha' "chute" do modelo).

Usado pelo Assistente de Email (anexos) e pelo filtro Nous Leitura (imagens e
boletos no chat).
"""
import io
import re
import zipfile
import datetime

_OCR = {"engine": None}

BANCOS = {
    "001": "Banco do Brasil", "033": "Santander", "041": "Banrisul", "070": "BRB",
    "077": "Inter", "104": "Caixa", "136": "Unicred", "197": "Stone", "208": "BTG Pactual",
    "212": "Banco Original", "237": "Bradesco", "260": "Nubank", "290": "PagBank",
    "323": "Mercado Pago", "336": "C6 Bank", "341": "Itau", "389": "Mercantil",
    "422": "Safra", "633": "Rendimento", "655": "Votorantim", "748": "Sicredi", "756": "Sicoob",
}
SEGMENTOS = {"1": "prefeitura", "2": "saneamento (agua/esgoto)", "3": "energia eletrica e gas",
             "4": "telecomunicacoes", "5": "orgao do governo", "6": "carne ou outro",
             "7": "multa de transito", "9": "uso exclusivo do banco"}


# ------------------------------------------------------------------ OCR

def ocr_image(data):
    """Texto de uma imagem (bytes). Linhas na ordem de leitura."""
    if _OCR["engine"] is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR["engine"] = RapidOCR()
    res, _ = _OCR["engine"](data)
    if not res:
        return ""
    # agrupa por linha (y do topo proximo) e so' depois ordena cada linha por x
    items = sorted(((b[0][1], b[0][0], t) for b, t, c in res if c >= 0.5))
    groups, cur_y = [], None
    for y, x, t in items:
        if cur_y is None or abs(y - cur_y) > 12:
            groups.append([])
            cur_y = y
        groups[-1].append((x, t))
    return "\n".join(" ".join(t for _x, t in sorted(g)) for g in groups)


# ------------------------------------------------------------------ arquivos

def _docx_text(data):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def _xlsx_text(data):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets[:5]:
        out.append(f"# Planilha {ws.title}")
        for row in ws.iter_rows(max_row=300, values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(cells):
                out.append(" | ".join(cells))
    return "\n".join(out)


def _pdf_text(data):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = [(p.extract_text() or "") for p in reader.pages[:60]]
    return "\n\n".join(f"[pagina {i + 1}]\n{t}" for i, t in enumerate(pages) if t.strip())


def extract_text(name, ctype, data, max_chars=40000):
    """Texto de um arquivo; ("", motivo) quando nao da'."""
    n = (name or "").lower()
    ct = (ctype or "").lower()
    try:
        if ct == "application/pdf" or n.endswith(".pdf"):
            text = _pdf_text(data)
            if not text.strip():
                return "", "PDF escaneado (so' imagem): abra a pagina como imagem para ler com OCR"
        elif n.endswith(".docx"):
            text = _docx_text(data)
        elif n.endswith((".xlsx", ".xlsm")):
            text = _xlsx_text(data)
        elif ct.startswith("image/") or n.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
            text = ocr_image(data)
        elif ct in ("text/html",) or n.endswith((".html", ".htm")):
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", data.decode("utf-8", errors="replace")))
        elif ct.startswith("text/") or n.endswith((".txt", ".csv", ".md", ".json", ".xml", ".ics")):
            text = data.decode("utf-8", errors="replace")
        else:
            return "", "tipo de arquivo que o Nous ainda nao le"
    except Exception as e:
        return "", f"nao consegui ler ({e.__class__.__name__})"
    return text[:max_chars], ""


# ------------------------------------------------------------------ boletos

def _mod10(s):
    total, w = 0, 2
    for d in reversed(s):
        p = int(d) * w
        total += p // 10 + p % 10
        w = 1 if w == 2 else 2
    return (10 - total % 10) % 10


def _mod11_arrec(s):
    total, w = 0, 2
    for d in reversed(s):
        total += int(d) * w
        w = 2 if w == 9 else w + 1
    r = total % 11
    return 0 if r in (0, 1) else 11 - r


def _vencimento(fator, hoje=None):
    """Fator FEBRABAN -> data. Base 07/10/1997; em 22/02/2025 o fator voltou a
    1000. Para fatores >= 1000 vale a data mais perto de hoje."""
    hoje = hoje or datetime.date.today()
    if fator == 0:
        return None
    cands = [datetime.date(1997, 10, 7) + datetime.timedelta(days=fator)]
    if fator >= 1000:
        cands.append(datetime.date(2025, 2, 22) + datetime.timedelta(days=fator - 1000))
    return min(cands, key=lambda d: abs((d - hoje).days))


def find_boletos(text):
    """Sequencias de 44/47/48 digitos (com pontos/espacos) que parecem boleto."""
    out = []
    # so' espaco/ponto/hifen entre os digitos, nunca quebra de linha: senao o
    # "12" do horario na linha de cima grudava na linha digitavel (49 digitos)
    for m in re.finditer(r"(?:\d[\d. \t-]{40,70}\d)", text or ""):
        digits = re.sub(r"\D", "", m.group())
        if len(digits) in (44, 47, 48) and digits not in out:
            out.append(digits)
    return out


def decode_boleto(digits, hoje=None):
    """Dados do boleto pela linha digitavel/codigo de barras. {} se invalido."""
    d = re.sub(r"\D", "", digits or "")
    if len(d) == 47 and d[0] != "8":  # boleto bancario (linha digitavel)
        campos = [(d[0:9], d[9]), (d[10:20], d[20]), (d[21:31], d[31])]
        ok = all(_mod10(c) == int(dv) for c, dv in campos)
        fator, valor = int(d[33:37]), int(d[37:47]) / 100
        venc = _vencimento(fator, hoje)
        return {"tipo": "boleto bancario", "banco": BANCOS.get(d[0:3], "banco " + d[0:3]),
                "valor": valor, "vencimento": venc.isoformat() if venc else None,
                "digitos_conferem": ok, "linha": d}
    if len(d) == 48 and d[0] == "8":  # arrecadacao (contas de consumo, tributos)
        blocos = [d[i:i + 12] for i in range(0, 48, 12)]
        barras = "".join(b[:11] for b in blocos)
        tipo_valor = barras[2]
        calc = _mod10 if tipo_valor in "67" else _mod11_arrec
        ok = all(calc(b[:11]) == int(b[11]) for b in blocos)
        valor = int(barras[4:15]) / 100 if tipo_valor in "68" else None
        return {"tipo": "conta/tributo (arrecadacao)", "segmento": SEGMENTOS.get(barras[1], "outro"),
                "valor": valor, "vencimento": None, "digitos_conferem": ok, "linha": d}
    if len(d) == 44 and d[0] != "8":  # codigo de barras bancario lido direto
        fator, valor = int(d[5:9]), int(d[9:19]) / 100
        venc = _vencimento(fator, hoje)
        return {"tipo": "boleto bancario (codigo de barras)", "banco": BANCOS.get(d[0:3], "banco " + d[0:3]),
                "valor": valor, "vencimento": venc.isoformat() if venc else None,
                "digitos_conferem": None, "linha": d}
    return {}


def describe_boleto(b):
    if not b:
        return ""
    partes = [b["tipo"]]
    if b.get("banco"):
        partes.append(b["banco"])
    if b.get("segmento"):
        partes.append(b["segmento"])
    if b.get("valor") is not None:
        partes.append("valor R$ " + f"{b['valor']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    if b.get("vencimento"):
        y, m, dd = b["vencimento"].split("-")
        partes.append(f"vencimento {dd}/{m}/{y}")
    if b.get("digitos_conferem") is False:
        partes.append("ATENCAO: os digitos verificadores NAO conferem (linha digitada/lida errado?)")
    return "; ".join(partes)
