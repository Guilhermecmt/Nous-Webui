// Conversa com o modelo pelo /api/chat do Ollama e descobre as chamadas de
// ferramenta da resposta.
//
// Modelos locais pequenos nem sempre usam o canal nativo de ferramentas: o
// qwen2.5-coder:14b, por exemplo, escreve a chamada como JSON no texto
// ({"name": "read_file", "arguments": {...}}) em 100% das vezes. Por isso o texto
// e' a via principal e o tool_calls nativo (qwen3, llama3.1...) entra junto.

export const OLLAMA = process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434';

export type Chamada = { id: string; nome: string; args: Record<string, unknown> };
export type Mensagem = {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string;
  tool_calls?: { function: { name: string; arguments: Record<string, unknown> } }[];
  tool_name?: string;
};
export type Resposta = { texto: string; chamadas: Chamada[]; tokens: number };

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
        try { return { fim: i + 1, valor: JSON.parse(s.slice(inicio, i + 1)) }; } catch { return null; }
      }
    }
  }
  return null;
}

/* Chamadas escritas no texto: JSON solto, em ```json ou entre <tool_call>. */
export function chamadasNoTexto(texto: string, nomes: Set<string>): { chamadas: Chamada[]; resto: string } {
  const chamadas: Chamada[] = [];
  let resto = '';
  let i = 0;
  while (i < texto.length) {
    const j = texto.indexOf('{', i);
    if (j < 0) { resto += texto.slice(i); break; }
    const obj = objetoJson(texto, j);
    const v = obj && obj.valor as { name?: unknown; arguments?: unknown; parameters?: unknown };
    if (obj && v && typeof v.name === 'string' && nomes.has(v.name)) {
      let args = v.arguments ?? v.parameters ?? {};
      if (typeof args === 'string') { try { args = JSON.parse(args); } catch { args = {}; } }
      chamadas.push({ id: novoId(), nome: v.name, args: (args || {}) as Record<string, unknown> });
      resto += texto.slice(i, j);
      i = obj.fim;
    } else {
      resto += texto.slice(i, j + 1);
      i = j + 1;
    }
  }
  resto = resto.replace(/```(?:json)?\s*```/g, '').replace(/<\/?tool_call>/g, '').trim();
  return { chamadas, resto };
}

/* Uma rodada com o modelo. onTexto recebe so' o que e' resposta para a pessoa:
 * enquanto o texto parece o comeco de uma chamada ({, ``` ou <tool_call>), ele
 * fica guardado e so' sai no fim se nao era chamada. */
export async function conversar(
  modelo: string, mensagens: Mensagem[], ferramentas: object[], nomes: Set<string>,
  onTexto: (pedaco: string) => void, sinal: AbortSignal,
): Promise<Resposta> {
  const r = await fetch(OLLAMA + '/api/chat', {
    method: 'POST', signal: sinal,
    body: JSON.stringify({
      model: modelo, messages: mensagens, tools: ferramentas, stream: true,
      options: { num_ctx: 16384, temperature: 0.2, num_predict: 4096 },
    }),
  });
  if (!r.ok || !r.body) throw new Error('o Ollama respondeu ' + r.status + ': ' + (await r.text()).slice(0, 200));

  let texto = '', decidido: 'texto' | 'talvez' | null = null, tokens = 0;
  const nativas: Chamada[] = [];
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
      if (d.error) throw new Error(d.error);
      const m = d.message || {};
      for (const c of m.tool_calls || []) {
        nativas.push({ id: novoId(), nome: c.function?.name, args: c.function?.arguments || {} });
      }
      if (m.content) {
        texto += m.content;
        if (decidido === null) {
          const t = texto.trimStart();
          if (t) decidido = /^(\{|```|<tool_call>)/.test(t) ? 'talvez' : 'texto';
          if (decidido === 'texto') onTexto(texto);
        } else if (decidido === 'texto') onTexto(m.content);
      }
      if (d.done) tokens = (d.prompt_eval_count || 0) + (d.eval_count || 0);
    }
  }
  const { chamadas, resto } = chamadasNoTexto(texto, nomes);
  const todas = nativas.filter((c) => nomes.has(c.nome)).concat(chamadas);
  if (decidido === 'talvez' && !todas.length) onTexto(texto);
  return { texto: todas.length ? resto : texto, chamadas: todas, tokens };
}

/* Modelos instalados que servem para o agente (conversa + ferramentas). */
export async function modelos(): Promise<{ nome: string; gb: number; ferramentas: boolean }[]> {
  const r = await fetch(OLLAMA + '/api/tags');
  const d = await r.json() as { models: { name: string; size: number }[] };
  const out = [];
  for (const m of d.models || []) {
    if (/embed|bge-|nomic/i.test(m.name)) continue;
    let ferramentas = false;
    try {
      const s = await (await fetch(OLLAMA + '/api/show', { method: 'POST', body: JSON.stringify({ model: m.name }) })).json() as { capabilities?: string[] };
      ferramentas = (s.capabilities || []).includes('tools');
    } catch { /* sem detalhes: segue sem marcar */ }
    out.push({ nome: m.name, gb: Math.round(m.size / 1e8) / 10, ferramentas });
  }
  return out;
}
