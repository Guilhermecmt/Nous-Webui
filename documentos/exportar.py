# -*- coding: utf-8 -*-
"""
Exportar Markdown para Word (.docx) e PDF, sem dependencia nova (v2.9).

  docx(titulo, md) -> bytes   Word de verdade (OOXML escrito a mao: titulos,
                              negrito/italico, listas, citacoes, tabelas, links)
  pdf(titulo, md)  -> bytes   fpdf2 (ja' vem no venv do Open WebUI) com a Arial
                              do Windows, para os acentos e o travessao saírem certos

Usado pelos Documentos (documentos/escrita.py) e pela Pesquisa Profunda
(relatorios). O Markdown passa pelo markdown-it com HTML DESLIGADO: texto que
veio da web ou do modelo nunca vira tag.
"""
import io
import os
import re
import zipfile
from xml.sax.saxutils import escape

from markdown_it import MarkdownIt

_MD = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def _xml(s):
    # caracteres de controle quebram o XML do Word
    return escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s or ""), {'"': "&quot;"})


# ------------------------------------------------------------------- Word

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
<w:sz w:val="23"/><w:lang w:val="pt-BR"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="140" w:line="288" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:b/><w:color w:val="1F2937"/><w:sz w:val="44"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:color w:val="8A6414"/><w:sz w:val="34"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:before="260" w:after="100"/><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:color w:val="8A6414"/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="80"/><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:sz w:val="25"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/>
<w:pPr><w:ind w:left="567"/><w:pBdr><w:left w:val="single" w:sz="12" w:space="8" w:color="C8962E"/></w:pBdr></w:pPr><w:rPr><w:i/><w:color w:val="4B5563"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="0" w:line="240" w:lineRule="auto"/><w:shd w:val="clear" w:color="auto" w:fill="F3F4F6"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="19"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="Hyperlink"><w:name w:val="Hyperlink"/><w:rPr><w:color w:val="1D4ED8"/><w:u w:val="single"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="Tabela"><w:name w:val="Tabela"/><w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:color="BFBFBF"/><w:left w:val="single" w:sz="4" w:color="BFBFBF"/>
<w:bottom w:val="single" w:sz="4" w:color="BFBFBF"/><w:right w:val="single" w:sz="4" w:color="BFBFBF"/>
<w:insideH w:val="single" w:sz="4" w:color="BFBFBF"/><w:insideV w:val="single" w:sz="4" w:color="BFBFBF"/>
</w:tblBorders><w:tblCellMar><w:left w:w="90" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>"""

_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

_CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{t}</dc:title><dc:creator>Nous</dc:creator></cp:coreProperties>"""

_W = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


class _Docx:
    def __init__(self):
        self.body = []
        self.links = []   # (rId, url)
        self.item = False

    def _link_id(self, url):
        rid = "rIdL%d" % (len(self.links) + 1)
        self.links.append((rid, url))
        return rid

    def runs(self, inline, bold=False):
        """Filhos de um token inline -> <w:r>/<w:hyperlink>."""
        out, b, i, link = [], int(bold), 0, None
        buf = []

        def run(text, code=False):
            rpr = ("<w:b/>" if b else "") + ("<w:i/>" if i else "")
            if code:
                rpr += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:shd w:val="clear" w:color="auto" w:fill="F3F4F6"/>'
            if link:
                rpr = '<w:rStyle w:val="Hyperlink"/>' + rpr
            r = '<w:r>%s<w:t xml:space="preserve">%s</w:t></w:r>' % (
                "<w:rPr>%s</w:rPr>" % rpr if rpr else "", _xml(text))
            (buf if link else out).append(r)

        for t in (inline.children or []):
            if t.type == "text":
                run(t.content)
            elif t.type == "code_inline":
                run(t.content, code=True)
            elif t.type in ("softbreak",):
                run(" ")
            elif t.type == "hardbreak":
                (buf if link else out).append("<w:r><w:br/></w:r>")
            elif t.type == "strong_open":
                b += 1
            elif t.type == "strong_close":
                b = max(0, b - 1)
            elif t.type == "em_open":
                i += 1
            elif t.type == "em_close":
                i = max(0, i - 1)
            elif t.type == "link_open":
                href = t.attrs.get("href", "")
                link = href if re.match(r"https?://", href, re.I) else "#"
                buf = []
            elif t.type == "link_close":
                if link and link != "#":
                    out.append('<w:hyperlink r:id="%s">%s</w:hyperlink>' % (self._link_id(link), "".join(buf)))
                else:
                    out.extend(buf)
                link, buf = None, []
            elif t.type == "image":
                run("[imagem: %s]" % (t.content or t.attrs.get("src", "")))
        return "".join(out)

    def para(self, runs, style=None, indent=0, prefix=""):
        ppr = ""
        if style:
            ppr += '<w:pStyle w:val="%s"/>' % style
        if indent:
            ppr += '<w:ind w:left="%d" w:hanging="283"/>' % (indent * 397 + 283)
        pre = '<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % _xml(prefix) if prefix else ""
        self.body.append("<w:p>%s%s%s</w:p>" % ("<w:pPr>%s</w:pPr>" % ppr if ppr else "", pre, runs))

    def table(self, rows):
        if not rows:
            return
        ncol = max(len(r) for r in rows)
        width = 9000 // max(1, ncol)
        grid = "".join('<w:gridCol w:w="%d"/>' % width for _ in range(ncol))
        trs = []
        for ri, (head, cells) in enumerate(rows):
            tcs = []
            for c in cells + [""] * (ncol - len(cells)):
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="F5EBD3"/>' if head else ""
                tcs.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/>%s</w:tcPr><w:p><w:pPr><w:spacing w:after="0"/></w:pPr>%s</w:p></w:tc>'
                           % (width, shade, c))
            trs.append("<w:tr>%s</w:tr>" % "".join(tcs))
        self.body.append('<w:tbl><w:tblPr><w:tblStyle w:val="Tabela"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
                         '<w:tblGrid>%s</w:tblGrid>%s</w:tbl><w:p/>' % (grid, "".join(trs)))

    def bytes(self, title):
        doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document %s><w:body>%s'
               '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1418" w:right="1418" w:bottom="1418" '
               'w:left="1418" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>'
               % (_W, "".join(self.body)))
        rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>']
        for rid, url in self.links:
            rels.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
                        'Target="%s" TargetMode="External"/>' % (rid, _xml(url)))
        rels.append("</Relationships>")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", _CT)
            z.writestr("_rels/.rels", _RELS)
            z.writestr("docProps/core.xml", _CORE.format(t=_xml(title)))
            z.writestr("word/document.xml", doc)
            z.writestr("word/styles.xml", _STYLES)
            z.writestr("word/_rels/document.xml.rels", "".join(rels))
        return buf.getvalue()


def docx(titulo, md):
    d = _Docx()
    toks = _MD.parse(md or "")
    if titulo and not re.match(r"\s*#\s", md or ""):
        d.para('<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % _xml(titulo), "Title")
    lists = []        # pilha: ["ul"] ou ["ol", n]
    quote = 0
    rows, row, in_head = None, None, False
    i = 0
    while i < len(toks):
        t = toks[i]
        tp = t.type
        if tp == "heading_open":
            lvl = int(t.tag[1])
            first = not d.body
            style = "Title" if (lvl == 1 and first) else "Heading%d" % min(3, lvl if lvl > 1 else 1)
            d.para(d.runs(toks[i + 1]), style)
            i += 3
            continue
        if tp == "bullet_list_open":
            lists.append(["ul"])
        elif tp == "ordered_list_open":
            lists.append(["ol", int(t.attrs.get("start", 1) or 1) - 1])
        elif tp in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
        elif tp == "list_item_open":
            if lists and lists[-1][0] == "ol":
                lists[-1][1] += 1
            d.item = True  # o proximo paragrafo leva o marcador
        elif tp == "blockquote_open":
            quote += 1
        elif tp == "blockquote_close":
            quote -= 1
        elif tp == "paragraph_open" and rows is None:
            inline = toks[i + 1]
            runs = d.runs(inline)
            if lists:
                prefix = ""
                if d.item:
                    top = lists[-1]
                    prefix = ("%d. " % top[1]) if top[0] == "ol" else "•  "
                    d.item = False
                d.para(runs, None, indent=len(lists), prefix=prefix or "   ")
            else:
                d.para(runs, "Quote" if quote else None)
            i += 3
            continue
        elif tp in ("fence", "code_block"):
            for line in (t.content or "").rstrip("\n").split("\n"):
                d.para('<w:r><w:t xml:space="preserve">%s</w:t></w:r>' % _xml(line), "Code")
            d.body.append("<w:p/>")
        elif tp == "hr":
            d.body.append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="C8962E"/></w:pBdr></w:pPr></w:p>')
        elif tp == "table_open":
            rows = []
        elif tp == "thead_open":
            in_head = True
        elif tp == "thead_close":
            in_head = False
        elif tp == "tr_open":
            row = []
        elif tp == "tr_close":
            rows.append((in_head, row))
        elif tp in ("th_open", "td_open"):
            row.append(d.runs(toks[i + 1], bold=tp == "th_open"))
            i += 3
            continue
        elif tp == "table_close":
            d.table(rows)
            rows = None
        i += 1
    if not d.body:
        d.para("")
    return d.bytes(titulo or "Documento")


# ------------------------------------------------------------------- PDF

_FONTES = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _pdf_font(pdf):
    """Arial do Windows (Unicode). Sem ela, Helvetica e troca o que nao e' Latin-1."""
    faces = {"": "arial.ttf", "B": "arialbd.ttf", "I": "ariali.ttf", "BI": "arialbi.ttf"}
    try:
        for style, f in faces.items():
            pdf.add_font("Nous", style, os.path.join(_FONTES, f))
        return "Nous", None
    except Exception:
        return "helvetica", lambda s: s.encode("latin-1", "replace").decode("latin-1")


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")


def pdf(titulo, md):
    from fpdf import FPDF
    doc = FPDF(format="A4")
    doc.set_margins(20, 18, 20)
    doc.set_auto_page_break(True, margin=18)
    fam, fix = _pdf_font(doc)
    doc.set_title(titulo or "Documento")
    doc.set_creator("Nous")
    doc.add_page()
    md = _EMOJI.sub("", md or "")   # a Arial nao tem emoji: some em vez de virar quadrado
    if fix:
        md, titulo = fix(md), fix(titulo or "")
    body = _MD.render(md)
    if titulo and not re.match(r"\s*#\s", md):
        body = "<h1>%s</h1>" % escape(titulo) + body
    # fpdf2 nao conhece <code>/<pre> com fonte propria: vira texto normal
    body = re.sub(r"</?(code|pre)>", "", body)
    # a quebra de linha entre blocos vira linha em branco no fpdf2 (sobrava
    # um buraco depois das tabelas)
    body = re.sub(r"(</?(?:table|thead|tbody|tr|th|td|ul|ol|li|p|h\d|blockquote)>)\n", r"\1", body)
    from fpdf.fonts import TextStyle
    ouro, cinza = (138, 100, 20), (75, 85, 99)
    estilos = {"h1": TextStyle(fam, "B", 20, ouro, t_margin=0, b_margin=2),
               "h2": TextStyle(fam, "B", 15, ouro, t_margin=4, b_margin=1),
               "h3": TextStyle(fam, "B", 12.5, (31, 41, 55), t_margin=3, b_margin=0),
               "blockquote": TextStyle(fam, "I", 11, cinza, l_margin=8),
               "a": TextStyle(color=(29, 78, 216), underline=True)}
    doc.set_font(fam, size=11)
    doc.write_html(body, font_family=fam, li_prefix_color=ouro,
                   table_line_separators=True, tag_styles=estilos)
    return bytes(doc.output())
