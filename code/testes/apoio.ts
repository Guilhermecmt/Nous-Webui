// Apoio dos testes que precisam do agente inteiro: um "Ollama de mentira"
// (cada pedido ao /api/chat devolve a proxima resposta do roteiro) e uma
// sessao pronta. Quem usa chama `ligarFalso()` antes de importar o agente.
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { AddressInfo } from 'node:net';

export const estado = { roteiro: [] as string[], pedidos: [] as { messages: { role: string; content: string }[] }[] };

const falso = http.createServer((req, res) => {
  let corpo = '';
  req.on('data', (d) => { corpo += d; });
  req.on('end', () => {
    const b = JSON.parse(corpo || '{}');
    estado.pedidos.push(b);
    const conteudo = estado.roteiro.shift() ?? 'Pronto.';
    if (b.stream === false) { res.end(JSON.stringify({ message: { role: 'assistant', content: conteudo }, done: true })); return; }
    res.write(JSON.stringify({ message: { role: 'assistant', content: conteudo }, done: false }) + '\n');
    res.end(JSON.stringify({ message: { role: 'assistant', content: '' }, done: true, prompt_eval_count: 100, eval_count: 10 }) + '\n');
  });
});

export async function ligarFalso() {
  await new Promise<void>((ok) => falso.listen(0, '127.0.0.1', () => ok()));
  process.env.OLLAMA_BASE_URL = 'http://127.0.0.1:' + (falso.address() as AddressInfo).port;
}
export function desligarFalso() { falso.close(); }

/* Pastas de apoio (jobs, saidas, lembretes, mcp) em temporarios. */
export async function configurarApoio() {
  (await import('../jobs.ts')).configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-jobs-')));
  (await import('../ferramentas.ts')).configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-saidas-')));
  (await import('../lembretes.ts')).configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-lem-')));
  (await import('../mcp.ts')).configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-mcp-')));
}

export const chamar = (nome: string, args: object) => JSON.stringify({ name: nome, arguments: args });
export const resultados = (ev: Record<string, unknown>[]) => ev.filter((e) => e.t === 'resultado');
export const conteudos = (s: { mensagens: { role: string; content: string }[] }, papel: string) => s.mensagens.filter((m) => m.role === papel).map((m) => m.content);

/* Roda um pedido; `respostas` decide as aprovacoes por tipo (padrao: sim). */
export async function rodar(A: typeof import('../agente.ts'), s: import('../agente.ts').Sessao, pedido: string, respostas: Record<string, object> = {}) {
  const eventos: Record<string, unknown>[] = [];
  await A.turno(s, pedido, {
    emitir: (e) => eventos.push(e), salvar: () => {}, sinal: new AbortController().signal,
    aprovar: async (e) => { eventos.push(e); return (respostas[String(e.tipo)] as { ok: boolean }) || { ok: true }; },
  });
  return eventos;
}
