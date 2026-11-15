"""Funcoes puras de traducao entre a API do Ollama e a do llama-server (OpenAI).

Nada aqui faz rede: o servidor (nous_motor.py) chama estas funcoes com os corpos
JSON ja' decodificados e manda o resultado adiante.
"""
import json
import math
import re
import time
from datetime import datetime, timezone

# opcoes do Ollama que o llama-server entende com o mesmo nome
_MESMO_NOME = ("temperature", "top_p", "top_k", "min_p", "typical_p", "repeat_penalty", "repeat_last_n", "seed",
               "stop", "presence_penalty", "frequency_penalty", "mirostat", "mirostat_tau", "mirostat_eta")


def agora_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def opcoes_openai(opcoes, padrao):
    junto = dict(padrao or {})
    junto.update(opcoes or {})
    saida = {k: junto[k] for k in _MESMO_NOME if k in junto and junto[k] is not None}
    n = junto.get("num_predict")
    if isinstance(n, (int, float)) and n >= 0:
        saida["max_tokens"] = int(n)
    return saida


def _formato(fmt):
    if fmt == "json":
        return {"type": "json_object"}
    if isinstance(fmt, dict):
        return {"type": "json_schema", "json_schema": {"name": "saida", "schema": fmt}}
    return None


def _mime(b64):
    for ini, tipo in (("iVBOR", "png"), ("/9j/", "jpeg"), ("R0lG", "gif"), ("UklG", "webp")):
        if b64.startswith(ini):
            return tipo
    return "png"


def _conteudo(msg, modelo):
    imagens = msg.get("images") or []
    texto = msg.get("content") or ""
    if not imagens:
        return texto
    if not modelo.projetor:
        raise ValueError("o modelo %s nao le imagens" % modelo.nome)
    partes = [{"type": "text", "text": texto}] if texto else []
    for b in imagens:
        b = b.split(",", 1)[1] if b.startswith("data:") else b
        partes.append({"type": "image_url", "image_url": {"url": "data:image/%s;base64,%s" % (_mime(b), b)}})
    return partes


def _mensagens(msgs, modelo):
    saida, pendentes, n = [], [], 0
    for m in msgs or []:
        papel = m.get("role", "user")
        if papel == "tool":
            nova = {"role": "tool", "content": m.get("content") or ""}
            nova["tool_call_id"] = m.get("tool_call_id") or (pendentes.pop(0) if pendentes else "call_%d" % max(n - 1, 0))
            saida.append(nova)
            continue
        nova = {"role": papel, "content": _conteudo(m, modelo)}
        if papel == "assistant":
            if m.get("thinking"):
                nova["reasoning_content"] = m["thinking"]
            chamadas = []
            for tc in m.get("tool_calls") or []:
                f = tc.get("function", {})
                args = f.get("arguments", {})
                ident = tc.get("id") or "call_%d" % n
                n += 1
                chamadas.append({"id": ident, "type": "function",
                                 "function": {"name": f.get("name", ""),
                                              "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)}})
            if chamadas:
                nova["tool_calls"] = chamadas
                pendentes = [c["id"] for c in chamadas]
        saida.append(nova)
    return saida


def _comum(corpo, modelo, mensagens):
    c = {"model": modelo.nome, "messages": mensagens, "stream": True, "stream_options": {"include_usage": True}}
    c.update(opcoes_openai(corpo.get("options"), modelo.params))
    rf = _formato(corpo.get("format"))
    if rf:
        c["response_format"] = rf
    think = corpo.get("think")
    if isinstance(think, bool):
        c["chat_template_kwargs"] = {"enable_thinking": think}
    elif isinstance(think, str) and think:
        c["chat_template_kwargs"] = {"reasoning_effort": think}
    if corpo.get("tools"):
        c["tools"] = corpo["tools"]
    return c


def pedido_chat(corpo, modelo):
    return _comum(corpo, modelo, _mensagens(corpo.get("messages"), modelo))


def pedido_generate(corpo, modelo):
    msgs = []
    if corpo.get("system"):
        msgs.append({"role": "system", "content": corpo["system"]})
    msgs.append({"role": "user", "content": corpo.get("prompt") or "", "images": corpo.get("images")})
    return _comum(corpo, modelo, _mensagens(msgs, modelo))


class Juntador:
    """Junta os pedacos do stream SSE do llama-server e devolve linhas no formato do Ollama."""

    def __init__(self, nome, tipo, mostrar_pensamento=True):
        self.nome, self.tipo, self.mostrar = nome, tipo, mostrar_pensamento
        self.inicio = time.monotonic_ns()
        self.texto, self.pensamento = [], []
        self.chamadas = {}
        self.emitidas = False
        self.motivo = None
        self.uso, self.tempos = {}, {}

    def _linha(self, conteudo="", pensamento="", chamadas=None, fim=False):
        l = {"model": self.nome, "created_at": agora_iso()}
        if self.tipo == "chat":
            msg = {"role": "assistant", "content": conteudo}
            if pensamento:
                msg["thinking"] = pensamento
            if chamadas:
                msg["tool_calls"] = chamadas
            l["message"] = msg
        else:
            l["response"] = conteudo
            if pensamento:
                l["thinking"] = pensamento
        l["done"] = fim
        return l

    def _chamadas_prontas(self):
        saida = []
        for i in sorted(self.chamadas):
            c = self.chamadas[i]
            try:
                args = json.loads(c["args"]) if c["args"].strip() else {}
            except ValueError:
                args = c["args"]
            saida.append({"id": c["id"], "function": {"index": i, "name": c["nome"], "arguments": args}})
        return saida

    def pedaco(self, evento):
        if evento.get("usage"):
            self.uso = evento["usage"]
        if evento.get("timings"):
            self.tempos = evento["timings"]
        saida = []
        for ch in evento.get("choices") or []:
            d = ch.get("delta") or ch.get("message") or {}
            pens = (d.get("reasoning_content") or "") if self.mostrar else ""
            cont = d.get("content") or ""
            if d.get("reasoning_content"):
                self.pensamento.append(d["reasoning_content"])
            if cont:
                self.texto.append(cont)
            for tc in d.get("tool_calls") or []:
                i = tc.get("index", 0)
                c = self.chamadas.setdefault(i, {"id": "", "nome": "", "args": ""})
                c["id"] = tc.get("id") or c["id"] or "call_%d" % i
                f = tc.get("function") or {}
                c["nome"] += f.get("name") or ""
                a = f.get("arguments")
                c["args"] += a if isinstance(a, str) else (json.dumps(a) if a else "")
            if pens or cont:
                saida.append(self._linha(cont, pens))
            if ch.get("finish_reason"):
                self.motivo = ch["finish_reason"]
                if self.chamadas and not self.emitidas:
                    self.emitidas = True
                    saida.append(self._linha(chamadas=self._chamadas_prontas()))
        return saida

    def _numeros(self):
        tp = self.tempos
        total = time.monotonic_ns() - self.inicio
        return {
            "done_reason": "length" if self.motivo == "length" else "stop",
            "total_duration": max(total, 1),
            "load_duration": 0,
            "prompt_eval_count": int(self.uso.get("prompt_tokens") or tp.get("prompt_n") or 0),
            "prompt_eval_duration": int((tp.get("prompt_ms") or 0) * 1e6),
            "eval_count": int(self.uso.get("completion_tokens") or tp.get("predicted_n") or 0),
            "eval_duration": max(int((tp.get("predicted_ms") or 0) * 1e6), 1),
        }

    def fim(self):
        saida = []
        if self.chamadas and not self.emitidas:
            self.emitidas = True
            saida = self._chamadas_prontas()
        l = self._linha(chamadas=saida, fim=True)
        l.update(self._numeros())
        return l

    def inteiro(self):
        pens = "".join(self.pensamento) if self.mostrar else ""
        l = self._linha("".join(self.texto), pens, self._chamadas_prontas() or None, fim=True)
        l.update(self._numeros())
        return l


def _vetores(dados):
    return [d["embedding"] for d in sorted(dados.get("data") or [], key=lambda d: d.get("index", 0))]


def resposta_embeddings(dados):
    v = _vetores(dados)
    return {"embedding": v[0] if v else []}


def resposta_embed(dados, nome):
    saida = []
    for v in _vetores(dados):
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        saida.append([x / n for x in v])
    return {"model": nome, "embeddings": saida,
            "prompt_eval_count": int((dados.get("usage") or {}).get("prompt_tokens") or 0)}


_DUR = re.compile(r"(-?\d+(?:\.\d+)?)(ms|h|m|s)")


def keep_alive_segundos(valor, padrao):
    """'5m' -> 300; 30 -> 30; 0 -> 0; negativo -> None (para sempre); ausente/ilegivel -> padrao."""
    def ler(v):
        if isinstance(v, bool):
            return False, 0
        if isinstance(v, (int, float)):
            return True, v
        if isinstance(v, str):
            s = v.strip().lower()
            try:
                return True, float(s)
            except ValueError:
                pass
            partes = _DUR.findall(s)
            if partes and _DUR.sub("", s) == "":
                mult = {"h": 3600, "m": 60, "s": 1, "ms": 0.001}
                return True, sum(float(n) * mult[u] for n, u in partes)
        return False, 0

    ok, seg = ler(valor)
    if not ok:
        ok, seg = ler(padrao)
        if not ok:
            seg = 300
    if seg < 0:
        return None
    return int(seg) if float(seg).is_integer() else seg


