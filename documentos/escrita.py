# -*- coding: utf-8 -*-
"""
Documentos (v2.9): escrever ao lado do chat, com a IA propondo mudancas que
voce aceita ou recusa uma a uma.

Guarda em NousData/documentos/<id>.json:
  {id, titulo, texto, criado, atualizado, versoes: [{t, motivo, texto}]}
As versoes sao fotos do texto ANTES de algo grande (mudanca da IA aceita,
restaurar, importar) ou a cada 10 min de escrita; ficam as 25 ultimas.

A IA nunca escreve direto no documento: o modelo reescreve o trecho (o texto
todo ou so' a parte selecionada) e diff() compara palavra por palavra. Cada
diferenca vira uma sugestao (~). Pedir "edicoes" em JSON falhava com modelo
pequeno; reescrever e comparar funciona ate' com um de 4B.
"""
import difflib
import json
import os
import re
import time
import uuid

MAX_VERSOES = 25
VERSAO_A_CADA = 600      # s: foto automatica enquanto escreve
MAX_TRECHO = 24000       # caracteres que o modelo reescreve de uma vez (cabe em 16k de contexto)


def data_dir():
    for env in ("DATA_DIR", "NOUS_DATA_DIR"):
        v = os.environ.get(env)
        if v:
            return v
    return os.path.join(os.path.expanduser("~"), "NousData")


def pasta():
    d = os.path.join(data_dir(), "documentos")
    os.makedirs(d, exist_ok=True)
    return d


def _safe_id(did):
    return re.sub(r"[^0-9A-Za-z-]", "", did or "")[:40]


def _path(did):
    return os.path.join(pasta(), _safe_id(did) + ".json")


def _palavras(texto):
    return len(re.findall(r"\w+", texto or ""))


def ler(did):
    try:
        with open(_path(did), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _gravar(doc):
    p = _path(doc["id"])
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    os.replace(tmp, p)


def listar():
    out = []
    for f in os.listdir(pasta()):
        if not f.endswith(".json"):
            continue
        d = ler(f[:-5])
        if d:
            out.append({"id": d["id"], "titulo": d.get("titulo") or "Sem titulo",
                        "atualizado": d.get("atualizado", 0), "palavras": _palavras(d.get("texto")),
                        "inicio": re.sub(r"\s+", " ", re.sub(r"[#*_>`|-]", "", d.get("texto") or ""))[:120].strip()})
    out.sort(key=lambda x: -x["atualizado"])
    return out


def resumo(doc):
    """O documento com a lista de versoes (sem o texto de cada uma)."""
    vs = [{"i": i, "t": v["t"], "motivo": v.get("motivo", ""), "palavras": _palavras(v.get("texto"))}
          for i, v in enumerate(doc.get("versoes") or [])]
    return {k: doc.get(k) for k in ("id", "titulo", "texto", "criado", "atualizado")} | {"versoes": vs[::-1]}


def salvar(did, titulo, texto, motivo=""):
    """Cria (did vazio) ou atualiza. motivo != "" tira uma foto da versao anterior."""
    agora = int(time.time())
    titulo = re.sub(r"\s+", " ", titulo or "").strip()[:120] or "Sem titulo"
    texto = (texto or "")[:500000]
    doc = ler(did) if did else None
    if not doc:
        doc = {"id": time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6], "criado": agora,
               "texto": "", "versoes": []}
    vs = doc.setdefault("versoes", [])
    anterior = doc.get("texto") or ""
    ultima = vs[-1]["t"] if vs else doc.get("criado", agora)
    if anterior.strip() and anterior != texto and (motivo or agora - ultima >= VERSAO_A_CADA):
        if not vs or vs[-1].get("texto") != anterior:
            vs.append({"t": agora, "motivo": motivo or "enquanto escrevia", "texto": anterior})
            del vs[:-MAX_VERSOES]
    doc.update(titulo=titulo, texto=texto, atualizado=agora)
    _gravar(doc)
    return doc


def versao(did, i):
    doc = ler(did)
    try:
        return (doc.get("versoes") or [])[int(i)].get("texto", "")
    except Exception:
        return None


def apagar(did):
    p = _path(did)
    if os.path.isfile(p):
        os.remove(p)


# ------------------------------------------------------------------- IA

SISTEMA = ("Voce e' um editor de textos cuidadoso. Escreva sempre em portugues do Brasil. "
           "Aplique a instrucao ao TEXTO e devolva SO' o texto resultante, completo, em Markdown "
           "(titulos com #, listas com -). Sem comentarios, sem explicar o que mudou, sem aspas em volta. "
           "Mantenha tudo o que a instrucao nao pede para mudar.")

# atalhos dos botoes do painel (o texto livre do usuario tambem vale)
ATALHOS = {
    "corrigir": "Corrija ortografia, acentuacao, pontuacao e concordancia. Nao mude o estilo nem o conteudo.",
    "formal": "Deixe o texto mais formal e profissional, sem mudar o que ele diz.",
    "simples": "Reescreva com palavras simples e frases curtas, para qualquer pessoa entender.",
    "curto": "Deixe o texto mais curto e direto (cerca de metade), mantendo as informacoes importantes.",
    "topicos": "Transforme os topicos e anotacoes em texto corrido, bem escrito, em paragrafos.",
    "organizar": "Organize o texto com titulos (##) e listas onde ajudar a leitura. Nao corte conteudo.",
    "continuar": "Continue escrevendo a partir do fim do texto, no mesmo tom (um ou dois paragrafos). "
                 "Devolva o texto original inteiro seguido da continuacao.",
}


def prompt(texto, instrucao, ini=None, fim=None):
    """(mensagens, prefixo, alvo, sufixo). Com selecao, so' o trecho e' reescrito."""
    instrucao = ATALHOS.get(instrucao, instrucao or "").strip()[:2000]
    if ini is not None and fim is not None and 0 <= ini < fim <= len(texto):
        pre, alvo, suf = texto[:ini], texto[ini:fim], texto[fim:]
        contexto = (texto[max(0, ini - 1500):ini] + "[...TRECHO...]" + texto[fim:fim + 1500]).strip()
        user = (f"INSTRUCAO: {instrucao}\n\nO trecho faz parte de um documento maior. "
                f"Contexto em volta (NAO devolva):\n{contexto}\n\n"
                f"TRECHO para reescrever:\n<<<\n{alvo}\n>>>\n\nDevolva so' o trecho reescrito.")
    elif not texto.strip():
        # documento vazio + pedido livre: "escreva uma carta pedindo reembolso..."
        if instrucao in ATALHOS.values():
            raise ValueError("O documento esta vazio. Escreva algo, cole topicos ou diga o que quer que a IA escreva.")
        pre, alvo, suf = "", texto, ""
        user = (f"Escreva do zero o texto pedido abaixo, completo e pronto para usar, em Markdown. "
                f"Onde faltar um dado (nome, data, valor), deixe entre colchetes, ex.: [seu nome].\n\nPEDIDO: {instrucao}")
    else:
        pre, alvo, suf = "", texto, ""
        user = f"INSTRUCAO: {instrucao}\n\nTEXTO:\n<<<\n{alvo}\n>>>"
    if len(alvo) > MAX_TRECHO:
        raise ValueError("Trecho grande demais para o modelo de uma vez. Selecione uma parte do texto e peca de novo.")
    return [{"role": "system", "content": SISTEMA}, {"role": "user", "content": user}], pre, alvo, suf


def sem_pensar(msgs, model):
    """O qwen3 pensa em voz alta mesmo com think=False (centenas de tokens em
    ingles antes da resposta); "/no_think" no fim do pedido desliga isso nele."""
    if "qwen3" in (model or "").lower() and msgs and msgs[-1].get("role") == "user":
        msgs[-1]["content"] = msgs[-1]["content"].rstrip() + "\n/no_think"
    return msgs


def _sem_acento(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def porque_regra(antes, depois):
    """Explicacao certa, sem modelo, para as mudancas pequenas e comuns.
    None = precisa do modelo (o modelo pequeno erra essas faceis)."""
    a, b = antes.strip(), depois.strip()
    if a == b:
        return "So' espaco ou quebra de linha."
    if a and b and a.lower() == b.lower():
        return "Maiuscula/minuscula: " + ("comeco de frase ou nome proprio pede maiuscula." if b[:1].isupper() else "aqui vai minuscula.")
    if a and b and _sem_acento(a) == _sem_acento(b):
        return f'Acentuacao: o certo e\' "{b}".'
    so_pont = re.compile(r"^[\s.,;:!?…\"'()—–-]*$")
    if so_pont.match(a) and so_pont.match(b):
        if "," in b and "," not in a:
            return "Pontuacao: a virgula separa as partes da frase (ex.: antes de \"mas\")."
        return "Pontuacao: ajuste de sinais (virgula, ponto ou travessao)."
    if a and b and _sem_acento(a).lower() == _sem_acento(b).lower():
        return f'Acentuacao e maiuscula: o certo e\' "{b}".'
    if a and b and len(a.split()) == 1 and len(b.split()) == 1 and difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.75:
        return f'Ortografia ou concordancia: o certo aqui e\' "{b}".'
    return None


def prompt_porque(antes, depois, contexto=""):
    """Pede UMA frase explicando a sugestao (botao "Por que?" da revisao)."""
    if not antes.strip():
        mudanca = f'Foi ACRESCENTADO: "{depois}"'
    elif not depois.strip():
        mudanca = f'Foi APAGADO: "{antes}"'
    else:
        mudanca = f'Trocou "{antes}" por "{depois}"'
    return ("Um revisor de textos sugeriu esta mudanca num texto em portugues.\n"
            f"{mudanca}\n" + (f"Trecho em volta: {contexto}\n" if contexto.strip() else "") +
            "\nExplique em UMA frase curta (ate' 20 palavras), em portugues simples, por que a mudanca "
            "melhora o texto (ex.: \"'Esta' leva acento: e' o verbo estar.\"). "
            'Responda so\' com JSON: {"motivo": "..."}')


_ABERTURA = re.compile(r"^\s*(?:aqui est[aá]|segue|claro[,!]|texto (?:revisado|reescrito|corrigido))[^\n]{0,80}:\s*\n", re.I)


def limpar(resposta, alvo):
    """Tira o que o modelo poe em volta do texto (pensamento, cercas, '<<<', 'Aqui esta:')."""
    r = (resposta or "").rsplit("</think>", 1)[-1].strip()
    r = _ABERTURA.sub("", r, count=1).strip()
    r = re.sub(r"^```(?:markdown|md|text)?\s*\n(.*?)\n```\s*$", r"\1", r, flags=re.S)
    r = r.replace("<<<", "").replace(">>>", "").strip()
    # mantem as quebras de linha das pontas do trecho original (selecao no meio do texto)
    lead = re.match(r"\s*", alvo).group(0)
    trail = alvo[len(alvo.rstrip()):]
    return lead + r.strip() + trail


_TOK = re.compile(r"\s+|\w+|[^\w\s]", re.U)
_PARAGRAFO = re.compile(r"(\n[ \t]*\n\s*)")
REESCRITO = 0.55   # abaixo disto o paragrafo foi reescrito: uma sugestao so' para ele


def _palavra_a_palavra(a_txt, b_txt):
    a, b = _TOK.findall(a_txt), _TOK.findall(b_txt)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if sm.ratio() < REESCRITO:
        # "levar bolo" -> "e' preciso levar um bolo": picado palavra a palavra
        # ninguem entende; o paragrafo novo inteiro e' a sugestao
        return [{"t": "~", "a": a_txt, "b": b_txt}]
    segs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            segs.append({"t": "=", "s": "".join(a[i1:i2]), "_n": i2 - i1})
        else:
            segs.append({"t": "~", "a": "".join(a[i1:i2]), "b": "".join(b[j1:j2])})
    return segs


def diff(antes, depois, pre="", suf=""):
    """Segmentos [{"t":"="|"~", ...}]: "=" texto igual (s); "~" sugestao (a -> b).
    Primeiro por paragrafo, depois palavra a palavra dentro do que mudou.
    Mudancas separadas so' por um espaco ou uma palavra viram uma sugestao so'
    (sugestao picada demais cansa)."""
    pa, pb = _PARAGRAFO.split(antes), _PARAGRAFO.split(depois)
    segs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, pa, pb, autojunk=False).get_opcodes():
        if tag == "equal":
            segs.append({"t": "=", "s": "".join(pa[i1:i2]), "_n": 99})
        else:
            segs.extend(_palavra_a_palavra("".join(pa[i1:i2]), "".join(pb[j1:j2])))
    # junta  ~ =(curto) ~  ->  ~   e  = =  ->  =
    out = []
    for s in segs:
        if (s["t"] == "~" and len(out) >= 2 and out[-1]["t"] == "=" and out[-2]["t"] == "~"
                and (out[-1]["_n"] <= 2 or not out[-1]["s"].strip()) and "\n" not in out[-1]["s"]):
            mid = out.pop()["s"]
            prev = out[-1]
            prev["a"] += mid + s["a"]
            prev["b"] += mid + s["b"]
        elif s["t"] == "=" and out and out[-1]["t"] == "=":
            out[-1]["s"] += s["s"]
            out[-1]["_n"] = 99
        elif s["t"] == "~" and out and out[-1]["t"] == "~":
            out[-1]["a"] += s["a"]
            out[-1]["b"] += s["b"]
        else:
            out.append(s)
    out = [s for s in out if s["t"] == "~" or s["s"]]
    for s in out:
        s.pop("_n", None)
    if pre:
        out.insert(0, {"t": "=", "s": pre})
    if suf:
        out.append({"t": "=", "s": suf})
    return out
