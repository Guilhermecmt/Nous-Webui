// Cliente HTTP do servico Nous Code (servidor.ts), usado pelo terminal.
// O terminal nao roda o agente por conta propria: fala com o mesmo servico do
// IDE, entao conversas, permissoes, MCP, lembretes e historico sao os mesmos.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';

export type Evento = Record<string, any> & { t: string };

export class ErroApi extends Error {
  status: number;
  constructor(status: number, msg: string) { super(msg); this.status = status; this.name = 'ErroApi'; }
}

export const PORTA_PADRAO = 8998;
export const porta = () => Number(process.env.NOUS_CODE_PORT || PORTA_PADRAO);

/* <NousData>\code: a mesma conta que o servidor faz. */
export function pastaDados(): string {
  return path.join(process.env.DATA_DIR || process.env.NOUS_DATA_DIR || path.join(os.homedir(), 'NousData'), 'code');
}

/* O token que o servidor guarda em <NousData>\code\cli-token. Sem o arquivo
 * (servico antigo, primeira vez), vai sem token: o servico aceita pedidos sem
 * origem, como sempre aceitou. */
export function lerToken(dados = pastaDados()): string {
  try {
    const t = fs.readFileSync(path.join(dados, 'cli-token'), 'utf8').trim();
    return /^[0-9a-f]{64}$/.test(t) ? t : '';
  } catch { return ''; }
}

export class Cliente {
  base: string;
  token: string;
  constructor(base: string, token = '') { this.base = base; this.token = token; }

  private cabecalhos(extra: Record<string, string> = {}) {
    return { ...(this.token ? { 'X-Nous-Token': this.token } : {}), ...extra };
  }

  private async falha(r: Response): Promise<never> {
    let msg = 'erro ' + r.status;
    try { const d = await r.json() as { erro?: string }; if (d.erro) msg = d.erro; } catch { /* sem corpo */ }
    msg = msg.replace(/ \(para abrir, mude o Alcance[^)]*\)/,' (para trabalhar aqui, use /alcance usuario na conversa ou nous --alcance usuario)');
    if (r.status === 403) msg = 'o Nous Code recusou este terminal (' + msg + '). Se o serviço foi iniciado com outra pasta de dados, feche-o e rode `nous` de novo.';
    throw new ErroApi(r.status, msg);
  }

  async pedir<T = any>(metodo: 'GET' | 'POST', caminho: string, corpo?: object, sinal?: AbortSignal): Promise<T> {
    let r: Response;
    try {
      r = await fetch(this.base + caminho, { method: metodo, signal: sinal,
        headers: this.cabecalhos(corpo ? { 'Content-Type': 'application/json' } : {}), body: corpo ? JSON.stringify(corpo) : undefined });
    } catch (e) {
      if (sinal?.aborted) throw e;
      throw new ErroApi(0, 'não consegui falar com o Nous Code (' + this.base + ').');
    }
    if (!r.ok) await this.falha(r);
    return await r.json() as T;
  }

  async texto(caminho: string): Promise<string> {
    const r = await fetch(this.base + caminho, { headers: this.cabecalhos() });
    if (!r.ok) await this.falha(r);
    return await r.text();
  }

  /* Um pedido ao agente: a resposta e' NDJSON, um evento por linha, que
   * termina quando o turno acaba (evento "fim"). */
  async *mensagem(id: string, texto: string, sinal?: AbortSignal): AsyncGenerator<Evento> {
    let r: Response;
    try {
      r = await fetch(this.base + '/mensagem', { method: 'POST', signal: sinal,
        headers: this.cabecalhos({ 'Content-Type': 'application/json' }), body: JSON.stringify({ id, texto }) });
    } catch (e) {
      if (sinal?.aborted) return;
      throw new ErroApi(0, 'não consegui falar com o Nous Code (' + this.base + ').');
    }
    if (!r.ok || !r.body) await this.falha(r);
    const dec = new TextDecoder();
    let buf = '';
    try {
      for await (const parte of r.body as unknown as AsyncIterable<Uint8Array>) {
        buf += dec.decode(parte, { stream: true });
        let k: number;
        while ((k = buf.indexOf('\n')) >= 0) {
          const linha = buf.slice(0, k).trim();
          buf = buf.slice(k + 1);
          if (linha) yield JSON.parse(linha) as Evento;
        }
      }
    } catch (e) {
      if (!sinal?.aborted) throw e;
      return;
    }
    if (buf.trim()) yield JSON.parse(buf) as Evento;
  }
}

async function saudavel(base: string, ms = 1500): Promise<{ versao?: string; modelo?: string } | null> {
  try {
    const r = await fetch(base + '/health', { signal: AbortSignal.timeout(ms) });
    const d = await r.json() as { ok?: boolean; versao?: string; modelo?: string };
    return d && d.ok ? d : null;
  } catch { return null; }
}

/* A pasta code/ (onde mora o servidor.ts), contando que este arquivo e' code/cli/cliente.ts. */
export const pastaCodigo = () => path.resolve(import.meta.dirname, '..');

/* Garante o servico no ar: se nao estiver, liga o mesmo que o atalho do Nous
 * Code liga (code/servidor.ts) com o Node que esta rodando o terminal, e espera. */
export async function garantirServico(opc: { aoIniciar?: () => void; aoFilho?: (pid: number) => void; esperaMs?: number } = {}): Promise<Cliente> {
  const base = 'http://127.0.0.1:' + porta();
  const cliente = new Cliente(base, lerToken());
  if (await saudavel(base)) return cliente;
  const servidor = path.join(pastaCodigo(), 'servidor.ts');
  if (!fs.existsSync(servidor)) throw new ErroApi(0, 'não achei o servico do Nous Code (' + servidor + ').');
  if (!fs.existsSync(path.join(pastaCodigo(), 'node_modules', 'ws'))) {
    throw new ErroApi(0, 'faltam as peças do Nous Code (code\\node_modules). Rode o instalar.bat de novo, com internet.');
  }
  opc.aoIniciar?.();
  const filho = spawn(process.execPath, [servidor], { cwd: pastaCodigo(), detached: true, stdio: 'ignore', windowsHide: true, env: process.env });
  if (filho.pid) opc.aoFilho?.(filho.pid);
  let saiu = false;
  filho.on('exit', () => { saiu = true; });
  filho.unref();
  const limite = Date.now() + (opc.esperaMs ?? 20_000);
  while (Date.now() < limite) {
    if (await saudavel(base, 800)) { cliente.token = lerToken(); return cliente; }
    if (saiu && !(await saudavel(base, 800))) break;   // saiu sem subir (outra copia pode ter ganho a porta: testa de novo abaixo)
    await new Promise((ok) => setTimeout(ok, 250));
  }
  if (await saudavel(base)) { cliente.token = lerToken(); return cliente; }
  throw new ErroApi(0, 'o Nous Code não subiu na porta ' + porta() + '. Abra o atalho "Nous Code" uma vez ou reinicie o computador.');
}
