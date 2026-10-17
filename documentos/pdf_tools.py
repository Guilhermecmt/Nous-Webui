# -*- coding: utf-8 -*-
"""
Formularios PDF e assinatura (pypdf + PIL, que ja' vem no venv do Open WebUI).

  fields(pdf)                      campos preenchiveis (AcroForm): nome, tipo, opcoes, valor
  fill(pdf, values, sig, place)    preenche e, se pedido, carimba a assinatura
                                   place = {"page": n, "pos": "inferior-direita"...} ou
                                           {"field": "Assinatura"} (dentro do campo)
A assinatura e' um PNG desenhado no painel e guardado em NousData/assinatura.png.
"""
import io
import os
import re

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import NameObject, BooleanObject

SIG_FILE = "assinatura.png"
_SIG_NAME = re.compile(r"assinatura|signature|assin\b|sign\b", re.I)


def data_dir():
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def sig_path():
    return os.path.join(data_dir(), SIG_FILE)


def _ft(f):
    t = str(f.get("/FT", ""))
    if t == "/Btn":
        flags = int(f.get("/Ff", 0) or 0)
        return "radio" if flags & (1 << 15) else "checkbox"
    if t == "/Ch":
        return "choice"
    if t == "/Sig":
        return "signature"
    return "text"


def _on_states(field):
    """Nomes do estado "marcado" de uma checkbox/radio (ex.: /Yes, /On, /1)."""
    out = set()
    kids = field.get("/Kids") or [field]
    for k in kids:
        k = k.get_object()
        ap = k.get("/AP")
        if ap and "/N" in ap:
            out |= {str(n) for n in ap["/N"].keys() if str(n) != "/Off"}
    return sorted(out) or ["/Yes"]


def fields(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    raw = reader.get_fields() or {}
    out = []
    for name, f in raw.items():
        if "/Kids" in f and "/FT" not in f:
            continue  # so' um agrupador
        kind = _ft(f)
        item = {"name": name, "type": kind, "value": str(f.get("/V", "") or "").lstrip("/"),
                "label": str(f.get("/TU", "") or name)}
        if kind == "choice":
            item["options"] = [str(o[1] if isinstance(o, list) else o) for o in (f.get("/Opt") or [])]
        if kind in ("checkbox", "radio"):
            item["options"] = [s.lstrip("/") for s in _on_states(f)]
        if _SIG_NAME.search(name) or _SIG_NAME.search(item["label"]):
            item["signature_spot"] = True
        out.append(item)
    return {"pages": len(reader.pages), "fields": out}


def _field_rect(writer, name):
    """(indice da pagina, [x0, y0, x1, y1]) do widget do campo `name`."""
    for i, page in enumerate(writer.pages):
        for a in page.get("/Annots") or []:
            a = a.get_object()
            if a.get("/Subtype") != "/Widget":
                continue
            t = a.get("/T")
            if t is None and a.get("/Parent") is not None:
                t = a["/Parent"].get_object().get("/T")
            if str(t) == name:
                return i, [float(x) for x in a["/Rect"]]
    return None, None


def _stamp(writer, sig_png, page_idx, rect):
    """Carimba o PNG da assinatura dentro de rect [x0, y0, x1, y1] (pontos PDF)."""
    from PIL import Image
    img = Image.open(io.BytesIO(sig_png)).convert("RGBA")
    bbox = img.getbbox()  # corta a margem vazia do desenho
    if bbox:
        img = img.crop(bbox)
    flat = Image.new("RGB", img.size, "white")
    flat.paste(img, mask=img.getchannel("A"))
    buf = io.BytesIO()
    flat.save(buf, "PDF", resolution=72)
    stamp = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
    sw, sh = float(stamp.mediabox.width), float(stamp.mediabox.height)
    x0, y0, x1, y1 = rect
    scale = min((x1 - x0) / sw, (y1 - y0) / sh)
    w, h = sw * scale, sh * scale
    tx = x0 + ((x1 - x0) - w) / 2
    ty = y0 + ((y1 - y0) - h) / 2
    writer.pages[page_idx].merge_transformed_page(stamp, Transformation().scale(scale).translate(tx, ty))


_POS = {"inferior-direita": (0.55, 0.05), "inferior-esquerda": (0.08, 0.05),
        "inferior-centro": (0.32, 0.05), "superior-direita": (0.55, 0.85)}


def fill(pdf_bytes, values=None, sig_png=None, place=None):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter(clone_from=reader)
    values = {k: v for k, v in (values or {}).items() if v not in (None, "")}
    if values and reader.get_fields():
        raw = reader.get_fields()
        fixed = {}
        for k, v in values.items():
            f = raw.get(k)
            if f is not None and _ft(f) in ("checkbox", "radio"):
                on = _on_states(f)
                if v in (True, "true", "sim", "1", "on") or ("/" + str(v)) in on:
                    fixed[k] = ("/" + str(v)) if ("/" + str(v)) in on else on[0]
                else:
                    fixed[k] = "/Off"
            else:
                fixed[k] = str(v)
        for page in writer.pages:
            writer.update_page_form_field_values(page, fixed, auto_regenerate=False)
        # leitores refazem a aparencia dos campos (acentos aparecem certos)
        writer._root_object["/AcroForm"][NameObject("/NeedAppearances")] = BooleanObject(True)
    if sig_png and place:
        if place.get("field"):
            idx, rect = _field_rect(writer, place["field"])
            if rect is None:
                raise ValueError("campo de assinatura nao encontrado")
        else:
            idx = max(0, min(len(writer.pages) - 1, int(place.get("page", len(writer.pages)) or 1) - 1))
            mb = writer.pages[idx].mediabox
            W, H = float(mb.width), float(mb.height)
            fx, fy = _POS.get(place.get("pos"), _POS["inferior-direita"])
            rect = [fx * W, fy * H, fx * W + 0.37 * W, fy * H + 0.09 * H]
        _stamp(writer, sig_png, idx, rect)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
