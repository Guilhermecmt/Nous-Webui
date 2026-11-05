// Conversa com o modelo pelo /api/chat do Ollama (ou por um servidor
// compativel com a API da OpenAI: LM Studio, llama.cpp, vLLM, Jan) e descobre
// as chamadas de ferramenta da resposta.
//
// Modelos locais pequenos nem sempre usam o canal nativo de ferramentas: o
// qwen2.5-coder:14b, por exemplo, escreve a chamada como JSON no texto
// ({"name": "read_file", "arguments": {...}}) em 100% das vezes. Por isso o texto
// e' a via principal e o tool_calls nativo (qwen3, llama3.1...) entra junto.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { repararJson, repararNome } from './reparo.ts';

export const OLLAMA = process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434';

/* Provedores compativeis com OpenAI. O modelo deles aparece como
 * "<provedor>::<id>" (ex.: "lmstudio::qwen2.5-coder-14b-instruct"). O LM Studio
 * entra sozinho quando esta' aberto; outros vao em ~/.nous/provedores.json:
 *   {"llamacpp": {"url": "http://127.0.0.1:8081/v1"}, "vllm": {"url": "...", "chave": "..."}} */
export type Provedor = { url: string; chave?: string };
export const SEP = '::';
function provedores(): Record<string, Provedor> {
  const out: Record<string, Provedor> = { lmstudio: { url: process.env.LMSTUDIO_BASE_URL || 'http://127.0.0.1:1234/v1' } };
  try {
    const j = JSON.parse(fs.readFileSync(path.join(os.homedir(), '.nous', 'provedores.json'), 'utf8').replace(/^\uFEFF/, ''));
    for (const [k, v] of Object.entries(j || {})) {
      const p = v as Provedor;
      if (/^[\w-]+$/.test(k) && p && typeof p.url === 'string') out[k] = { url: p.url.replace(/\/+$/, ''), chave: p.chave };
    }
  } catch { /* sem arquivo: so' o LM Studio */ }
  return out;
}
/* "lmstudio::id" -> provedor + id; nome do Ollama -> null. */
export function provedorDe(modelo: string): { nome: string; p: Provedor; id: string } | null {
  const i = modelo.indexOf(SEP);
  if (i < 0) return null;
  const nome = modelo.slice(0, i);
  const p = provedores()[nome];
  if (!p) throw new Error('provedor de modelo desconhecido: ' + nome + ' (configure em ~/.nous/provedores.json)');
  return { nome, p, id: modelo.slice(i + SEP.length) };
}
function cabecalhosOpenAI(p: Provedor): Record<string, string> {
  return { 'Content-Type': 'application/json', ...(p.chave ? { Authorization: 'Bearer ' + p.chave } : {}) };
}
/* No protocolo da OpenAI o resultado de ferramenta exige tool_call_id; o agente
 * conversa por JSON no texto, entao o resultado vai como mensagem do usuario. */
function mensagensOpenAI(ms: Mensagem[]) {
  return ms.map((m) => m.role === 'tool'
    ? { role: 'user', content: '[' + (m.tool_name || 'tool') + ' result]\n' + m.content }
    : { role: m.role, content: m.content });
}

export type Chamada = { id: string; nome: string; args: Record<string, unknown> };
export type Mensagem = {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: { function: { name: string; arguments: Record<string, unknown> } }[];
  tool_name?: string;
};

let seq = 0;
function novoId(): string { seq += 1; return 'c' + Date.now().toString(36) + seq; }

/* Acha o primeiro objeto JSON balanceado a partir de "inicio" (respeita strings). */
function objetoJson(s: string, inicio: number): { fim: number; valor: unknown } | null {
  let nivel = 0, emStr = false, esc = false;
  for (let i = inicio; i < s.length; i++) {
    const c = s[i];
    if (emStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') emStr = false;
      continue;
    }
    if (c === '"') emStr = true;
    else if (c === '{') nivel++;
    else if (c === '}') {
      nivel--;
      if (nivel === 0) {
        const valor = repararJson(s.slice(inicio, i + 1));
        return valor === undefined ? null : { fim: i + 1, valor };
      }
    }
  }
  // chaves sem fechar: o modelo parou antes do fim do JSON
  const valor = repararJson(s.slice(inicio));
  return valor === undefined ? null : { fim: s.length, valor };
}

/* Chamada com argumentos em texto ou em objeto. Sem conserto: entra em invalidas. */
function argumentos(nome: string, args: unknown, invalidas: string[]): Record<string, unknown> | null {
  let a: unknown = args ?? {};
  if (typeof a === 'string') {
    a = a.trim() ? repararJson(a) : {};
    if (a === undefined) { invalidas.push(`the arguments of tool "${nome}" are not valid JSON`); return null; }
  }
  if (typeof a !== 'object' || a === null || Array.isArray(a)) { invalidas.push(`the arguments of tool "${nome}" must be a JSON object`); return null; }
  return a as Record<string, unknown>;
}

/* Chamada pelo canal nativo: conserta o nome; nome sem conserto volta ao modelo. */
function nativa(nome: string, args: unknown, nomes: Set<string>, invalidas: string[]): Chamada | null {
  const n = nomes.has(nome) ? nome : repararNome(nome, nomes);
  if (!n) { invalidas.push(`tool "${nome}" does not exist`); return null; }
  const a = argumentos(n, args, invalidas);
  return a ? { id: novoId(), nome: n, args: a } : null;
}

/* Chamadas escritas no texto: JSON solto, em ```json ou entre <tool_call>. */
export function chamadasNoTexto(texto: string, nomes: Set<string>): { chamadas: Chamada[]; resto: string; invalidas: string[] } {
  const chamadas: Chamada[] = [];
  const invalidas: string[] = [];
  let resto = '';
  let i = 0;
  while (i < texto.length) {
    const j = texto.indexOf('{', i);
    if (j < 0) { resto += texto.slice(i); break; }
    const obj = objetoJson(texto, j);
    const v = obj && obj.valor as { name?: unknown; arguments?: unknown; parameters?: unknown };
    // nome so' e' consertado com "arguments" junto: {"name": "Maria"} e' dado, nao chamada
    const temArgs = !!v && typeof v === 'object' && ('arguments' in v || 'parameters' in v);
    const nome = obj && v && typeof v.name === 'string' ? (nomes.has(v.name) ? v.name : temArgs ? repararNome(v.name, nomes) : null) : null;
    if (obj && nome) {
      const args = argumentos(nome, v!.arguments ?? v!.parameters, invalidas);
      if (args) chamadas.push({ id: novoId(), nome, args });
      resto += texto.slice(i, j);
      i = obj.fim;
    } else if (obj && temArgs && typeof v!.name === 'string') {
      invalidas.push(`tool "${v!.name}" does not exist`);
      resto += texto.slice(i, j);
      i = obj.fim;
    } else {
      resto += texto.slice(i, j + 1);
      i = j + 1;
    }
  }
  resto = resto.replace(/```(?:json)?\s*```/g, '').replace(/<\/?tool_call>/g, '').trim();
  // comecou como chamada e nao virou nada: JSON sem conserto (em geral cortado)
  if (!chamadas.length && !invalidas.length && /^\s*(?:```(?:json)?\s*|<tool_call>\s*)?\{\s*"(?:name|tool|function)"\s*:/.test(texto)) {
    invalidas.push('your tool call was not valid JSON');
    resto = '';
  }
  return { chamadas, resto, invalidas };
}

/* O erro que veio do servidor e' de contexto? Falta de memoria tambem diz
 * "exceed", e compactar tudo nao resolve isso. */
function estourouContexto(erro: string, extra = false): boolean {
  if (/\b(?:memory|vram|cuda|oom)\b/i.test(erro)) return false;
  return (extra ? /context|too long|exceed|maximum/i : /context|too long|exceed/i).test(erro);
}

/* Fecha a rodada: junta as chamadas, separa o que precisa voltar ao modelo e
 * solta o texto retido se ele era resposta mesmo. */
function fechar(texto: string, nativas: Chamada[], invNativas: string[], cortada: boolean, retido: boolean, o: Opcoes, tokens: number, prompt: number, t0: number): Resposta {
  const { chamadas, resto, invalidas } = chamadasNoTexto(texto, o.nomes);
  const todas = nativas.concat(chamadas);
  // JSON de exemplo no meio de uma explicacao nao e' chamada errada
  const inv = invNativas.concat(todas.length || resto.length <= 200 ? invalidas : []);
  if (retido && !todas.length && !inv.length && !cortada) o.onTexto(texto);
  return { texto: todas.length || inv.length ? resto : texto, chamadas: todas, invalidas: inv, cortada, tokens, prompt, segundos: (Date.now() - t0) / 1000 };
}

/* Contexto do Ollama para o agente: o mesmo do resto do Nous. */
export const NUM_CTX = 16384;

/* Pedido maior que o contexto (o Ollama corta ou recusa): o agente compacta e tenta de novo. */
export class ContextoCheio extends Error {}

export type Opcoes = {
  modelo: string; mensagens: Mensagem[]; ferramentas: object[]; nomes: Set<string>;
  onTexto: (pedaco: string) => void; onPensamento?: (pedaco: string) => void;
  sinal: AbortSignal; think?: boolean | 'low' | 'medium' | 'high';
};
export type Resposta = {
  texto: string; chamadas: Chamada[];
  invalidas: string[];   // chamadas sem conserto, ja' no texto que volta ao modelo
  cortada: boolean;      // parou no limite de saida (done_reason/finish_reason "length")
  tokens: number; prompt: number; segundos: number;
};

/* Uma rodada com o modelo. onTexto recebe so' o que e' resposta para a pessoa:
 * enquanto o texto parece o comeco de uma chamada ({, ``` ou <tool_call>), ele
 * fica guardado e so' sai no fim se nao era chamada. O raciocinio (think) vem
 * a parte, em onPensamento. */
export async function conversar(o: Opcoes): Promise<Resposta> {
  const pv = provedorDe(o.modelo);
  if (pv) return conversarOpenAI(o, pv);
  const t0 = Date.now();
  const corpo: Record<string, unknown> = {
    model: o.modelo, messages: o.mensagens, tools: o.ferramentas, stream: true,
    options: { num_ctx: NUM_CTX, temperature: 0.2, num_predict: 4096 },
  };
  if (o.think !== undefined) corpo.think = o.think;
  const r = await fetch(OLLAMA + '/api/chat', { method: 'POST', signal: o.sinal, body: JSON.stringify(corpo) });
  if (!r.ok || !r.body) {
    const erro = (await r.text()).slice(0, 300);
    if (estourouContexto(erro)) throw new ContextoCheio(erro);
    // modelo sem suporte a think: tenta de novo sem ele
    if (o.think !== undefined && /think/i.test(erro)) return conversar({ ...o, think: undefined });
    throw new Error('o Ollama respondeu ' + r.status + ': ' + erro);
  }

  let texto = '', decidido: 'texto' | 'talvez' | null = null, tokens = 0, prompt = 0, cortada = false;
  const nativas: Chamada[] = [];
  const invalidas: string[] = [];
  const leitor = r.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let k: number;
    while ((k = buf.indexOf('\n')) >= 0) {
      const linha = buf.slice(0, k).trim();
      buf = buf.slice(k + 1);
      if (!linha) continue;
      const d = JSON.parse(linha);
      if (d.error) throw estourouContexto(d.error) ? new ContextoCheio(d.error) : new Error(d.error);
      const m = d.message || {};
      if (m.thinking && o.onPensamento) o.onPensamento(m.thinking);
      for (const c of m.tool_calls || []) {
        const ch = nativa(String(c.function?.name ?? ''), c.function?.arguments, o.nomes, invalidas);
        if (ch) nativas.push(ch);
      }
      if (m.content) {
        texto += m.content;
        if (decidido === null) {
          const t = texto.trimStart();
          if (t) decidido = /^(\{|```|<tool_call>)/.test(t) ? 'talvez' : 'texto';
          if (decidido === 'texto') o.onTexto(texto);
        } else if (decidido === 'texto') o.onTexto(m.content);
      }
      if (d.done) { prompt = d.prompt_eval_count || 0; tokens = prompt + (d.eval_count || 0); cortada = d.done_reason === 'length'; }
    }
  }
  // um <think>...</think> que vazou no texto (modelos que sempre pensam) sai da resposta
  texto = texto.replace(/^\s*<think>[\s\S]*?<\/think>\s*/, '');
  return fechar(texto, nativas, invalidas, cortada, decidido === 'talvez', o, tokens, prompt, t0);
}

/* Mesma rodada num servidor compativel com OpenAI (SSE de chat/completions). */
async function conversarOpenAI(o: Opcoes, pv: { nome: string; p: Provedor; id: string }): Promise<Resposta> {
  const t0 = Date.now();
  const corpo: Record<string, unknown> = {
    model: pv.id, messages: mensagensOpenAI(o.mensagens), tools: o.ferramentas, stream: true,
    temperature: 0.2, max_tokens: 4096, stream_options: { include_usage: true },
  };
  if (typeof o.think === 'string') corpo.reasoning_effort = o.think;
  const r = await fetch(pv.p.url + '/chat/completions', { method: 'POST', signal: o.sinal, headers: cabecalhosOpenAI(pv.p), body: JSON.stringify(corpo) });
  if (!r.ok || !r.body) {
    const erro = (await r.text()).slice(0, 300);
    if (estourouContexto(erro, true)) throw new ContextoCheio(erro);
    throw new Error(pv.nome + ' respondeu ' + r.status + ': ' + erro);
  }
  let texto = '', decidido: 'texto' | 'talvez' | null = null, tokens = 0, prompt = 0, cortada = false;
  const parciais = new Map<number, { nome: string; args: string }>();
  const leitor = r.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await leitor.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let k: number;
    while ((k = buf.indexOf('\n')) >= 0) {
      const linha = buf.slice(0, k).trim();
      buf = buf.slice(k + 1);
      if (!linha.startsWith('data:')) continue;
      const dados = linha.slice(5).trim();
      if (dados === '[DONE]') continue;
      let d;
      try { d = JSON.parse(dados); } catch { continue; }
      if (d.error) throw new Error(d.error.message || String(d.error));
      if (d.usage) { prompt = d.usage.prompt_tokens || 0; tokens = d.usage.total_tokens || prompt + (d.usage.completion_tokens || 0); }
      if (d.choices?.[0]?.finish_reason === 'length') cortada = true;
      const delta = d.choices?.[0]?.delta || {};
      const pens = delta.reasoning_content || delta.reasoning;
      if (pens && o.onPensamento) o.onPensamento(pens);
      for (const c of delta.tool_calls || []) {
        const x = parciais.get(c.index ?? 0) || { nome: '', args: '' };
        if (c.function?.name) x.nome += c.function.name;
        if (c.function?.arguments) x.args += c.function.arguments;
        parciais.set(c.index ?? 0, x);
      }
      if (delta.content) {
        texto += delta.content;
        if (decidido === null) {
          const t = texto.trimStart();
          if (t) decidido = /^(\{|```|<tool_call>)/.test(t) ? 'talvez' : 'texto';
          if (decidido === 'texto') o.onTexto(texto);
        } else if (decidido === 'texto') o.onTexto(delta.content);
      }
    }
  }
  texto = texto.replace(/^\s*<think>[\s\S]*?<\/think>\s*/, '');
  const invalidas: string[] = [];
  const nativas = [...parciais.values()].map((x) => nativa(x.nome, x.args, o.nomes, invalidas)).filter((c): c is Chamada => !!c);
  return fechar(texto, nativas, invalidas, cortada, decidido === 'talvez', o, tokens, prompt, t0);
}

/* Pedido simples, sem ferramentas e sem stream (resumo da compactacao, titulos). */
export async function completar(modelo: string, mensagens: Mensagem[], sinal: AbortSignal, maxTokens = 1200, ferramentas?: object[]): Promise<string> {
  const pv = provedorDe(modelo);
  if (pv) {
    const r = await fetch(pv.p.url + '/chat/completions', { method: 'POST', signal: sinal, headers: cabecalhosOpenAI(pv.p), body: JSON.stringify({
      model: pv.id, messages: mensagensOpenAI(mensagens), stream: false, temperature: 0.2, max_tokens: maxTokens }) });
    const d = await r.json() as { choices?: { message?: { content?: string } }[]; error?: { message?: string } };
    if (d.error) throw new Error(d.error.message || 'erro do provedor');
    return (d.choices?.[0]?.message?.content || '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
  }
  const r = await fetch(OLLAMA + '/api/chat', { method: 'POST', signal: sinal, body: JSON.stringify({
    model: modelo, messages: mensagens, stream: false, think: false, ...(ferramentas ? { tools: ferramentas } : {}),
    options: { num_ctx: NUM_CTX, temperature: 0.2, num_predict: maxTokens } }) });
  const d = await r.json() as { message?: { content?: string }; error?: string };
  if (d.error) {
    if (/think/i.test(d.error)) {
      const r2 = await fetch(OLLAMA + '/api/chat', { method: 'POST', signal: sinal, body: JSON.stringify({
        model: modelo, messages: mensagens, stream: false, options: { num_ctx: NUM_CTX, temperature: 0.2, num_predict: maxTokens } }) });
      const d2 = await r2.json() as { message?: { content?: string } };
      return (d2.message?.content || '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
    }
    throw new Error(d.error);
  }
  return (d.message?.content || '').replace(/<think>[\s\S]*?<\/think>/g, '').trim();
}

/* Modelos instalados que servem para o agente (conversa + ferramentas): os do
 * Ollama e os dos provedores compativeis com OpenAI que estiverem no ar. */
export type InfoModelo = { nome: string; gb: number; ferramentas: boolean; pensa: boolean; provedor?: string };
export async function modelos(): Promise<InfoModelo[]> {
  const out: InfoModelo[] = [];
  await Promise.all(Object.entries(provedores()).map(async ([nome, p]) => {
    try {
      const r = await fetch(p.url + '/models', { headers: cabecalhosOpenAI(p), signal: AbortSignal.timeout(1500) });
      const d = await r.json() as { data?: { id: string }[] };
      for (const m of d.data || []) {
        if (/embed/i.test(m.id)) continue;
        out.push({ nome: nome + SEP + m.id, gb: 0, ferramentas: true, pensa: false, provedor: nome });
      }
    } catch { /* provedor fora do ar */ }
  }));
  let d: { models: { name: string; size: number }[] } = { models: [] };
  try { d = await (await fetch(OLLAMA + '/api/tags')).json() as typeof d; } catch { /* Ollama fora do ar */ }
  for (const m of d.models || []) {
    if (/embed|bge-|nomic/i.test(m.name)) continue;
    let ferramentas = false, pensa = false;
    try {
      const s = await (await fetch(OLLAMA + '/api/show', { method: 'POST', body: JSON.stringify({ model: m.name }) })).json() as { capabilities?: string[] };
      ferramentas = (s.capabilities || []).includes('tools');
      pensa = (s.capabilities || []).includes('thinking');
    } catch { /* sem detalhes: segue sem marcar */ }
    out.push({ nome: m.name, gb: Math.round(m.size / 1e8) / 10, ferramentas, pensa });
  }
  return out;
}
