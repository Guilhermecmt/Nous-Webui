# -*- coding: utf-8 -*-
"""
Relatorio visual da Pesquisa Profunda: transforma o relatorio em Markdown numa
pagina HTML propria (sumario, citacoes [n] clicaveis, cartoes de fontes,
pronta para imprimir/salvar em PDF) e guarda na biblioteca em
<DATA_DIR>/research/<id>.html + <id>.json.

Seguranca: o texto vem de paginas da web via LLM. Todo HTML cru e' escapado
ANTES do Markdown, so' links http(s) sobrevivem, e o monitor serve a pagina
com uma CSP sem scripts.
"""
import os
import re
import json
import html
import time
import uuid
import datetime
import urllib.parse

import markdown

_MESES = ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
          "agosto", "setembro", "outubro", "novembro", "dezembro"]


def data_dir():
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def library_dir():
    d = os.path.join(data_dir(), "research")
    os.makedirs(d, exist_ok=True)
    return d


def _domain(url):
    try:
        h = urllib.parse.urlparse(url).hostname or ""
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""


def _split_sources(md):
    """Tira a secao '## Fontes' do corpo (as fontes viram cartoes)."""
    m = re.search(r"^#{1,3}\s*Fontes\s*$", md, re.M | re.I)
    return (md[:m.start()].rstrip(), md[m.end():]) if m else (md, "")


def _safe_links(body_html):
    def fix(m):
        href = html.unescape(m.group(1))
        if href.startswith("#") or re.match(r"https?://", href, re.I):
            return f'href="{html.escape(href, quote=True)}"'
        return 'href="#"'
    body_html = re.sub(r'href="([^"]*)"', fix, body_html)
    # links externos abrem em outra aba, sem passar o endereco do Nous
    return body_html.replace('<a href="http', '<a rel="noopener noreferrer" target="_blank" href="http')


def _render_body(md, n_sources):
    # 1) escapa HTML cru: nada do que veio da web vira tag. So' '<' e '&' abrem
    #    HTML; '>' fica, senao as citacoes em bloco ("> texto") do Markdown quebram.
    safe = md.replace("&", "&amp;").replace("<", "&lt;")
    out = markdown.markdown(safe, extensions=["tables", "sane_lists", "toc"],
                            extension_configs={"toc": {"permalink": False}})
    # o escape acima e' refeito pelo Markdown em blocos de codigo: desfaz o duplo
    out = out.replace("&amp;lt;", "&lt;").replace("&amp;amp;", "&amp;")
    out = _safe_links(out)

    # 2) citacoes [n] e [n, m] viram links para o cartao da fonte
    def cite(m):
        nums = [int(x) for x in re.findall(r"\d+", m.group(0))]
        if not nums or any(n < 1 or n > n_sources for n in nums):
            return m.group(0)
        return "".join(f'<a class="cite" href="#fonte-{n}">{n}</a>' for n in nums)
    out = re.sub(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\](?!\()", cite, out)
    return out


def _toc(body_html):
    items = re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body_html)
    if len(items) < 2:
        return ""
    lis = "".join(f'<li class="l{lvl}"><a href="#{hid}">{re.sub("<[^>]+>", "", txt)}</a></li>'
                  for lvl, hid, txt in items)
    return f'<nav class="toc"><b>Neste relatorio</b><ol>{lis}</ol></nav>'


_CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1f;--mut:#6b6b70;--card:#fff;--line:#e8e4da;--gold:#a8791c;--gold2:#c8962e;--chip:#f4efe3}
@media (prefers-color-scheme:dark){:root{--bg:#121216;--fg:#ececec;--mut:#9a9aa2;--card:#1b1b20;--line:#2b2b31;--gold:#e7c069;--gold2:#c8962e;--chip:#25221b}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 Georgia,'Iowan Old Style',serif}
.wrap{max-width:1080px;margin:0 auto;padding:40px 20px 80px;display:grid;grid-template-columns:minmax(0,1fr) 240px;gap:40px}
header{grid-column:1/-1;border-bottom:1px solid var(--line);padding-bottom:22px}
.kicker{font:600 12px/1 Inter,system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:var(--gold)}
h1{font-size:34px;line-height:1.2;margin:12px 0 14px}
.meta{display:flex;flex-wrap:wrap;gap:8px;font:13px Inter,system-ui,sans-serif;color:var(--mut)}
.chip{background:var(--chip);border:1px solid var(--line);border-radius:99px;padding:3px 10px}
article h2{font-size:23px;margin:34px 0 8px;padding-top:6px;border-top:1px solid var(--line)}
article>:first-child{margin-top:0;padding-top:0;border-top:0}
article h3{font-size:18px;margin:24px 0 6px}
article p,article li{max-width:68ch}
article table{border-collapse:collapse;font:14px Inter,system-ui,sans-serif;margin:14px 0}
article th,article td{border:1px solid var(--line);padding:6px 10px;text-align:left}
article code{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:14px}
article blockquote{margin:14px 0;padding:4px 16px;border-left:3px solid var(--gold2);color:var(--mut)}
a{color:var(--gold)}
a.cite{display:inline-block;min-width:18px;padding:0 4px;margin:0 1px;border-radius:5px;background:var(--chip);
 border:1px solid var(--line);font:600 11px/17px Inter,system-ui,sans-serif;text-align:center;text-decoration:none;vertical-align:2px}
aside{position:sticky;top:20px;align-self:start;font:13px/1.5 Inter,system-ui,sans-serif}
.toc ol{list-style:none;padding:0;margin:8px 0 0}.toc li{margin:5px 0}.toc li.l3{padding-left:12px}
.toc a{color:var(--mut);text-decoration:none}.toc a:hover{color:var(--gold)}
.sources{grid-column:1/-1;border-top:1px solid var(--line);padding-top:10px}
.sources h2{font-size:23px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.src{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;
 font:13px/1.45 Inter,system-ui,sans-serif;scroll-margin-top:20px}
.src:target{border-color:var(--gold2);box-shadow:0 0 0 3px rgba(200,150,46,.2)}
.src .n{display:inline-flex;width:22px;height:22px;border-radius:6px;align-items:center;justify-content:center;
 background:var(--gold2);color:#111;font-weight:700;font-size:11px;margin-right:8px}
.src .t{font-weight:600}.src .d{color:var(--mut);margin:4px 0}.src p{margin:6px 0 0;color:var(--mut)}
footer{grid-column:1/-1;color:var(--mut);font:12px Inter,system-ui,sans-serif;text-align:center;margin-top:30px}
@media (max-width:820px){.wrap{grid-template-columns:1fr}aside{position:static}}
@media print{aside{display:none}.wrap{display:block}body{background:#fff;color:#000}a.cite{border:0;background:none}}
"""


def build_html(question, report_md, sources, meta):
    body_md, _ = _split_sources(report_md or "")
    n = len(sources)
    body = _render_body(body_md, n)
    toc = _toc(body)
    created = datetime.datetime.fromtimestamp(meta["created"])
    data = f"{created.day} de {_MESES[created.month - 1]} de {created.year}, {created:%H:%M}"
    domains = sorted({_domain(s.get("url", "")) for s in sources} - {""})
    words = len(re.findall(r"\w+", body_md))
    cards = []
    for i, s in enumerate(sources, 1):
        url = s.get("url", "")
        safe_url = url if re.match(r"https?://", url, re.I) else "#"
        snippet = (s.get("snippet") or s.get("content") or s.get("text") or "").strip()
        snippet = re.sub(r"\s+", " ", re.sub(r"<[^>]{0,200}>", "", snippet))
        if len(snippet) > 220:
            snippet = snippet[:220].rstrip(" .,;") + "..."
        cards.append(
            f'<div class="src" id="fonte-{i}"><span class="n">{i}</span>'
            f'<a class="t" rel="noopener noreferrer" target="_blank" href="{html.escape(safe_url, quote=True)}">'
            f'{html.escape(s.get("title") or url or "Fonte")}</a>'
            f'<div class="d">{html.escape(_domain(url))}</div>'
            + (f"<p>{html.escape(snippet)}</p>" if snippet else "") + "</div>")
    q = html.escape(question)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{q[:90]} - Pesquisa Nous</title><style>{_CSS}</style></head><body><div class="wrap">
<header><div class="kicker">Pesquisa Profunda · Nous</div><h1>{q}</h1>
<div class="meta"><span class="chip">{data}</span><span class="chip">{n} fontes</span>
<span class="chip">{len(domains)} sites</span><span class="chip">~{max(1, round(words / 200))} min de leitura</span>
<span class="chip">modelo {html.escape(meta.get("model") or "local")}</span></div></header>
<article>{body}</article><aside>{toc}</aside>
<section class="sources"><h2>Fontes</h2><div class="grid">{"".join(cards)}</div></section>
<footer>Gerado localmente pelo Nous. Confira as fontes antes de decisoes importantes.</footer>
</div></body></html>"""


def save(question, report_md, sources, model=None):
    """Grava o relatorio na biblioteca. Devolve o id."""
    rid = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    meta = {"id": rid, "question": question[:500], "created": int(time.time()),
            "model": model or "", "n_sources": len(sources),
            "domains": sorted({_domain(s.get("url", "")) for s in sources} - {""})[:20]}
    d = library_dir()
    with open(os.path.join(d, rid + ".html"), "w", encoding="utf-8") as f:
        f.write(build_html(question, report_md, sources, meta))
    # o Markdown e' o que vira Word/PDF (monitor /research/export)
    body, _ = _split_sources(report_md or "")
    fontes = "\n".join(f"{i}. [{s.get('title') or s.get('url') or 'Fonte'}]({s.get('url', '')})"
                       for i, s in enumerate(sources, 1))
    with open(os.path.join(d, rid + ".md"), "w", encoding="utf-8") as f:
        f.write(f"# {question}\n\n{body}\n\n## Fontes\n\n{fontes}\n" if sources else f"# {question}\n\n{body}\n")
    with open(os.path.join(d, rid + ".json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return rid


def como_markdown(rid):
    """Markdown do relatorio. Os anteriores a v2.9 so' tem o HTML: tira o texto dele."""
    base = os.path.join(library_dir(), _safe_id(rid))
    if os.path.isfile(base + ".md"):
        with open(base + ".md", encoding="utf-8") as f:
            return f.read()
    if not os.path.isfile(base + ".html"):
        return None
    from bs4 import BeautifulSoup
    with open(base + ".html", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    for tag in soup(["style", "aside", "footer"]):
        tag.decompose()
    for a in soup.select("a.cite"):
        a.replace_with(f"[{a.get_text(strip=True)}]")
    out = []
    for el in soup.find_all(["h1", "h2", "h3", "p", "li", "a"]):
        if el.name == "a" and "t" not in (el.get("class") or []):
            continue  # so' o titulo dos cartoes de fonte
        txt = re.sub(r"\s+([.,;:!?)])", r"\1", re.sub(r"\s+", " ", el.get_text(" "))).strip()
        if not txt:
            continue
        if el.name in ("h1", "h2", "h3"):
            out.append("#" * int(el.name[1]) + " " + txt)
        elif el.name == "li":
            out.append("- " + txt)
        elif el.name == "a":
            out.append(f"- [{txt}]({el.get('href', '')})")
        elif not el.find_parent("div", class_="src"):
            out.append(txt)
    return "\n\n".join(out)


def list_reports(limit=200):
    d = library_dir()
    out = []
    for f in sorted(os.listdir(d), reverse=True):
        if f.endswith(".json"):
            try:
                with open(os.path.join(d, f), encoding="utf-8") as fh:
                    out.append(json.load(fh))
            except Exception:
                continue
        if len(out) >= limit:
            break
    return out


def _safe_id(rid):
    return re.sub(r"[^0-9A-Za-z-]", "", rid or "")[:40]


def report_path(rid):
    p = os.path.join(library_dir(), _safe_id(rid) + ".html")
    return p if os.path.isfile(p) else None


def delete(rid):
    for ext in (".html", ".md", ".json"):
        p = os.path.join(library_dir(), _safe_id(rid) + ext)
        if os.path.isfile(p):
            os.remove(p)
