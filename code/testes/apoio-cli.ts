// Apoio dos testes do terminal (`nous`): um Ollama de mentira com roteiro, o
// servico de verdade numa porta livre e um "terminal" que segue um roteiro.
import http from 'node:http';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { spawn, type ChildProcess } from 'node:child_process';
import type { AddressInfo } from 'node:net';
import type { Io, Leitura } from '../cli/io.ts';

export type Passo = string | { esperar: true };   // texto da resposta; ou `esperar`: o modelo "pensa" ate' o pedido ser cancelado

/* Ollama de mentira: /api/tags e /api/show para a lista de modelos, /api/chat segue o roteiro. */
export function ollamaFalso(modelos: { name: string; tools?: boolean; thinking?: boolean }[] = [{ name: 'falso', tools: true }]) {
  const estado = { roteiro: [] as Passo[], pedidos: 0, esperando: 0, abortados: 0 };
  const srv = http.createServer((req, res) => {
    let corpo = '';
    req.on('data', (d) => { corpo += d; });
    req.on('end', () => {
      const b = corpo ? JSON.parse(corpo) : {};
      if (req.url === '/api/tags') { res.end(JSON.stringify({ models: modelos.map((m) => ({ name: m.name, size: 2.5e9 })) })); return; }
      if (req.url === '/api/show') {
        const m = modelos.find((x) => x.name === b.model);
        res.end(JSON.stringify({ capabilities: ['completion', ...(m?.tools ? ['tools'] : []), ...(m?.thinking ? ['thinking'] : [])] }));
        return;
      }
      // titulo e resumo (stream:false) nao gastam o roteiro dos pedidos do agente
      if (b.stream === false) { res.end(JSON.stringify({ message: { role: 'assistant', content: 'Conversa de teste' }, done: true })); return; }
      estado.pedidos++;
      const passo = estado.roteiro.shift() ?? 'Pronto.';
      if (typeof passo !== 'string') {
        estado.esperando++;
        res.on('close', () => { estado.abortados++; });
        res.write(JSON.stringify({ message: { role: 'assistant', content: '' }, done: false }) + '\n');
        return;   // fica aberto ate' o cliente desistir
      }
      res.write(JSON.stringify({ message: { role: 'assistant', content: passo }, done: false }) + '\n');
      res.end(JSON.stringify({ message: { role: 'assistant', content: '' }, done: true, done_reason: 'stop', prompt_eval_count: 1200, eval_count: 10 }) + '\n');
    });
  });
  return {
    estado,
    async ligar() { await new Promise<void>((ok) => srv.listen(0, '127.0.0.1', () => ok())); return 'http://127.0.0.1:' + (srv.address() as AddressInfo).port; },
    desligar() { srv.closeAllConnections?.(); srv.close(); },
  };
}

export function portaLivre(): Promise<number> {
  const tenta = (p: number): Promise<number> => new Promise((ok, erro) => {
    const s = net.createServer();
    s.once('error', () => (p < 9699 ? ok(tenta(p + 1) as unknown as number) : erro(new Error('sem porta livre'))));
    s.listen(p, '127.0.0.1', () => s.close(() => ok(p)));
  });
  return tenta(9500 + Math.floor(Math.random() * 100));
}

/* O servico de verdade (servidor.ts) com dados e "pasta do usuario" temporarios. */
export async function ligarServico(ollama: string, extra: Record<string, string> = {}) {
  const porta = await portaLivre();
  const dados = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-cli-dados-'));
  const casa = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-cli-casa-'));
  const env = { ...process.env, NOUS_CODE_PORT: String(porta), DATA_DIR: dados, USERPROFILE: casa, OLLAMA_BASE_URL: ollama,
    NOUS_CODE_MODEL: 'falso', NOUS_CODE_DIAGNOSTICOS: '0', ...extra };
  const proc: ChildProcess = spawn(process.execPath, ['servidor.ts'], { cwd: path.resolve(import.meta.dirname, '..'), windowsHide: true, stdio: 'ignore', env });
  const base = 'http://127.0.0.1:' + porta;
  for (let i = 0; i < 80; i++) {
    try { if ((await fetch(base + '/health')).ok) break; } catch { /* ainda subindo */ }
    await new Promise((ok) => setTimeout(ok, 250));
    if (i === 79) throw new Error('o servico nao subiu');
  }
  return { porta, base, dados, casa, proc, token: fs.readFileSync(path.join(dados, 'code', 'cli-token'), 'utf8').trim() };
}

export function pastaProjeto(arquivos: Record<string, string> = { 'a.txt': 'ola\n' }) {
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-cli-proj-'));
  for (const [n, c] of Object.entries(arquivos)) fs.writeFileSync(path.join(raiz, n), c);
  return raiz;
}

/* Terminal de mentira: teclas e linhas vem de filas, e tudo que sai fica guardado. */
export class IoFalso implements Io {
  tty = true;
  saidas: string[] = [];
  atividades: string[] = [];
  teclas: string[] = [];
  linhas: (string | Leitura)[] = [];
  perguntasTecla: string[][] = [];
  prompts: string[] = [];
  interrupcao: (() => void) | null = null;
  hist: string[] = [];
  largura() { return 100; }
  saida(s: string) { this.saidas.push(s); }
  atividade(s: string) { this.atividades.push(s); }
  async tecla(validas: string[]): Promise<string> {
    this.perguntasTecla.push(validas);
    const k = this.teclas.shift();
    if (k === undefined) throw new Error('tecla inesperada (validas: ' + validas.join(',') + '). Saida ate agora:\n' + this.tudo());
    return k;
  }
  async linha(prompt: string): Promise<Leitura> {
    this.prompts.push(prompt);
    const l = this.linhas.shift();
    if (l === undefined) throw new Error('linha inesperada: ' + prompt);
    return typeof l === 'string' ? { t: 'linha', texto: l } : l;
  }
  aoInterromper(cb: () => void) { this.interrupcao = cb; return () => { this.interrupcao = null; }; }
  historico() { return this.hist; }
  guardar(l: string) { this.hist.unshift(l); }
  tudo() { return this.saidas.join('') + this.atividades.join(''); }
}

export const semCor = (s: string) => s.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '');
