// Servidores MCP (Model Context Protocol): as ferramentas deles entram no
// agente como mcp__<servidor>__<ferramenta>. Nome publico, projecao do
// resultado e instrucoes do servidor adaptados do DeepSeek Harness
// (dsh-mcp-client, MIT, (c) 2026 DeepSeek).
//
// Configuracao no formato do .mcp.json do Claude Code:
//   {"mcpServers": {"nome": {"command": "...", "args": [], "env": {}}}}
//   {"mcpServers": {"nome": {"type": "http", "url": "https://...", "headers": {}}}}
// ~/.nous/mcp.json vale para todos os projetos. O .mcp.json (ou
// .nous/mcp.json) do projeto roda programas de quem fez o projeto: so' liga
// depois que a pessoa permite, e a permissao cai se a configuracao mudar.

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawn, type ChildProcess } from 'node:child_process';

export type Spec = { command?: string; args?: string[]; env?: Record<string, string>; cwd?: string;
  type?: string; url?: string; headers?: Record<string, string>; disabled?: boolean };
export type Servidor = { nome: string; origem: 'global' | 'projeto'; arquivo: string; spec: Spec; hash: string; aprovado: boolean };
export type FerrMcp = { publico: string; servidor: string; nome: string; descricao: string; esquema: Record<string, unknown>; soLeitura: boolean };

const NOME_OK = /^[A-Za-z0-9_-]{1,32}$/;
const INVALIDO = /[^A-Za-z0-9_-]/g;
const MAX_NOME = 64;
const ESPERA_MS = 60_000;

let arqAprovados = path.join(os.homedir(), 'NousData', 'code', 'mcp-aprovados.json');
export function configurar(dirDados: string) { arqAprovados = path.join(dirDados, 'mcp-aprovados.json'); }

function lerJson(p: string): Record<string, unknown> | null {
  try { return JSON.parse(fs.readFileSync(p, 'utf8').replace(/^﻿/, '')); } catch { return null; }
}
function aprovados(): Record<string, string> { return (lerJson(arqAprovados) as Record<string, string>) || {}; }
const chaveAprov = (raiz: string, nome: string) => path.resolve(raiz).toLowerCase() + '::' + nome;

/* Nome que o modelo ve. Igual ao do dsh: mcp__srv__ferr; se precisou trocar
 * caracteres ou cortar, entra um hash para dois nomes nunca colidirem. */
export function nomePublico(servidor: string, nome: string): string {
  const junto = `mcp__${servidor}__${nome}`;
  const norm = junto.replace(INVALIDO, '_');
  if (norm === junto && norm.length <= MAX_NOME) return norm;
  const h = crypto.createHash('sha256').update(servidor + '\0' + nome).digest('hex').slice(0, 12);
  return norm.slice(0, MAX_NOME - 13) + '_' + h;
}

/* ------------------------------------------------------------ configuracao */
export function servidores(raiz: string): Servidor[] {
  const out: Servidor[] = [];
  const ok = aprovados();
  const fontes: [string, 'global' | 'projeto'][] = [
    [path.join(os.homedir(), '.nous', 'mcp.json'), 'global'],
    [path.join(raiz, '.mcp.json'), 'projeto'],
    [path.join(raiz, '.nous', 'mcp.json'), 'projeto'],
  ];
  for (const [arq, origem] of fontes) {
    const j = lerJson(arq);
    const lista = (j?.mcpServers || j?.servers) as Record<string, Spec> | undefined;
    if (!lista || typeof lista !== 'object') continue;
    for (const [nome, spec] of Object.entries(lista)) {
      if (!NOME_OK.test(nome) || !spec || typeof spec !== 'object' || spec.disabled) continue;
      if (out.some((s) => s.nome === nome)) continue;  // o primeiro vence (global antes do projeto)
      const hash = crypto.createHash('sha256').update(JSON.stringify(spec)).digest('hex').slice(0, 16);
      out.push({ nome, origem, arquivo: arq, spec, hash, aprovado: origem === 'global' || ok[chaveAprov(raiz, nome)] === hash });
    }
  }
  return out;
}

export function aprovar(raiz: string, nome: string, sim: boolean) {
  const s = servidores(raiz).find((x) => x.nome === nome);
  if (!s) throw new Error('servidor MCP nao encontrado: ' + nome);
  const ok = aprovados();
  if (sim) ok[chaveAprov(raiz, nome)] = s.hash; else delete ok[chaveAprov(raiz, nome)];
  fs.mkdirSync(path.dirname(arqAprovados), { recursive: true });
  fs.writeFileSync(arqAprovados, JSON.stringify(ok, null, 2));
  if (!sim) fechar(raiz, nome);
}

/* ------------------------------------------------------------ conexao */
interface Transporte {
  pedir(metodo: string, params: unknown, ms?: number): Promise<Record<string, unknown>>;
  avisar(metodo: string, params: unknown): void;
  fechar(): void;
  morto: Error | null;
}

/* stdio: JSON-RPC uma mensagem por linha. */
class Stdio implements Transporte {
  morto: Error | null = null;
  private seq = 0;
  private resto = '';
  private pend = new Map<number, { ok: (v: Record<string, unknown>) => void; erro: (e: Error) => void }>();
  private p: ChildProcess;
  erros = '';

  constructor(spec: Spec, raiz: string) {
    const win = process.platform === 'win32';
    // npx, uvx e afins sao .cmd no Windows: so' rodam pelo shell
    const linha = [spec.command!, ...(spec.args || [])].map((a) => (/[\s"]/.test(a) ? '"' + a.replace(/"/g, '\\"') + '"' : a)).join(' ');
    this.p = spawn(win ? linha : spec.command!, win ? [] : spec.args || [], {
      cwd: spec.cwd ? path.resolve(raiz, spec.cwd) : raiz, shell: win, windowsHide: true,
      env: { ...process.env, ...(spec.env || {}) }, stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.p.stdout!.setEncoding('utf8');
    this.p.stdout!.on('data', (d: string) => {
      this.resto += d;
      let i;
      while ((i = this.resto.indexOf('\n')) >= 0) {
        const l = this.resto.slice(0, i).trim();
        this.resto = this.resto.slice(i + 1);
        if (l) { try { this.tratar(JSON.parse(l)); } catch { /* linha que nao e' JSON-RPC */ } }
      }
    });
    this.p.stderr!.on('data', (d: Buffer) => { this.erros = (this.erros + d.toString('utf8')).slice(-2000); });
    const fim = (e: Error) => { this.morto = e; for (const x of this.pend.values()) x.erro(e); this.pend.clear(); };
    this.p.on('exit', (c) => fim(new Error('o servidor MCP saiu (codigo ' + c + ')' + (this.erros.trim() ? ': ' + this.erros.trim().split('\n').slice(-3).join(' ') : ''))));
    this.p.on('error', (e) => fim(e));
  }

  private tratar(m: Record<string, unknown>) {
    if ('id' in m && !('method' in m)) {
      const p = this.pend.get(Number(m.id));
      if (!p) return;
      this.pend.delete(Number(m.id));
      const e = m.error as { message?: string } | undefined;
      if (e) p.erro(new Error(e.message || 'erro do servidor MCP')); else p.ok((m.result || {}) as Record<string, unknown>);
    } else if ('id' in m && 'method' in m) {
      // ping e pedidos do servidor (sampling, roots...) que nao suportamos
      if (m.method === 'ping') this.escrever({ jsonrpc: '2.0', id: m.id, result: {} });
      else if (m.method === 'roots/list') this.escrever({ jsonrpc: '2.0', id: m.id, result: { roots: [] } });
      else this.escrever({ jsonrpc: '2.0', id: m.id, error: { code: -32601, message: 'not supported' } });
    }
  }

  private escrever(m: unknown) { if (!this.morto) this.p.stdin!.write(JSON.stringify(m) + '\n'); }

  pedir(metodo: string, params: unknown, ms = ESPERA_MS) {
    if (this.morto) return Promise.reject(this.morto);
    const id = ++this.seq;
    return new Promise<Record<string, unknown>>((ok, erro) => {
      const t = setTimeout(() => { this.pend.delete(id); erro(new Error(metodo + ': o servidor MCP nao respondeu em ' + ms / 1000 + 's')); }, ms);
      this.pend.set(id, { ok: (v) => { clearTimeout(t); ok(v); }, erro: (e) => { clearTimeout(t); erro(e); } });
      this.escrever({ jsonrpc: '2.0', id, method: metodo, params });
    });
  }
  avisar(metodo: string, params: unknown) { this.escrever({ jsonrpc: '2.0', method: metodo, params }); }
  fechar() {
    try { this.p.stdin!.end(); } catch { /* ja fechado */ }
    if (process.platform === 'win32' && this.p.pid) { try { spawn('taskkill', ['/T', '/F', '/PID', String(this.p.pid)], { windowsHide: true }); } catch { /* ja saiu */ } }
    else this.p.kill();
  }
}

/* HTTP "streamable": cada pedido e' um POST; a resposta vem em JSON ou SSE. */
class Http implements Transporte {
  morto: Error | null = null;
  private seq = 0;
  private sessao = '';
  private spec: Spec;
  constructor(spec: Spec) { this.spec = spec; }

  private async post(corpo: unknown, ms: number): Promise<Response> {
    const h: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream', ...(this.spec.headers || {}) };
    if (this.sessao) h['Mcp-Session-Id'] = this.sessao;
    const r = await fetch(this.spec.url!, { method: 'POST', headers: h, body: JSON.stringify(corpo), signal: AbortSignal.timeout(ms) });
    const s = r.headers.get('mcp-session-id');
    if (s) this.sessao = s;
    return r;
  }

  async pedir(metodo: string, params: unknown, ms = ESPERA_MS) {
    const id = ++this.seq;
    const r = await this.post({ jsonrpc: '2.0', id, method: metodo, params }, ms);
    if (!r.ok) throw new Error(metodo + ': HTTP ' + r.status);
    const tipo = r.headers.get('content-type') || '';
    let msg: Record<string, unknown> | null = null;
    if (tipo.includes('text/event-stream')) {
      const txt = await r.text();
      for (const bloco of txt.split(/\r?\n\r?\n/)) {
        const dados = bloco.split(/\r?\n/).filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trim()).join('\n');
        if (!dados) continue;
        try { const m = JSON.parse(dados); if (m.id === id) { msg = m; break; } } catch { /* evento que nao e' JSON */ }
      }
    } else msg = await r.json() as Record<string, unknown>;
    if (!msg) throw new Error(metodo + ': resposta vazia do servidor MCP');
    const e = msg.error as { message?: string } | undefined;
    if (e) throw new Error(e.message || 'erro do servidor MCP');
    return (msg.result || {}) as Record<string, unknown>;
  }
  avisar(metodo: string, params: unknown) { this.post({ jsonrpc: '2.0', method: metodo, params }, 15_000).catch(() => {}); }
  fechar() { /* sem processo */ }
}

type Conexao = { t: Transporte; pronta: Promise<void>; ferramentas: FerrMcp[]; instrucoes: string; erro: string };
const conexoes = new Map<string, Conexao>();
const chave = (raiz: string, nome: string) => path.resolve(raiz).toLowerCase() + '::' + nome;

function conectar(raiz: string, s: Servidor): Conexao {
  const k = chave(raiz, s.nome) + '::' + s.hash;
  const ja = conexoes.get(k);
  if (ja && !ja.t.morto) return ja;
  const t: Transporte = s.spec.url ? new Http(s.spec) : new Stdio(s.spec, raiz);
  const c: Conexao = { t, ferramentas: [], instrucoes: '', erro: '', pronta: Promise.resolve() };
  c.pronta = (async () => {
    const ini = await t.pedir('initialize', { protocolVersion: '2025-06-18', capabilities: {}, clientInfo: { name: 'nous-code', version: '0.3.0' } }, 45_000);
    t.avisar('notifications/initialized', {});
    c.instrucoes = typeof ini.instructions === 'string' ? ini.instructions.trim().slice(0, 2000) : '';
    let cursor: unknown;
    const lista: FerrMcp[] = [];
    do {
      const r = await t.pedir('tools/list', cursor ? { cursor } : {});
      for (const f of (r.tools || []) as Record<string, unknown>[]) {
        const nome = String(f.name || '');
        if (!nome) continue;
        const ann = (f.annotations || {}) as { readOnlyHint?: boolean };
        lista.push({ publico: nomePublico(s.nome, nome), servidor: s.nome, nome, descricao: String(f.description || '').slice(0, 1200),
          esquema: (f.inputSchema as Record<string, unknown>) || { type: 'object', properties: {} }, soLeitura: ann.readOnlyHint === true });
      }
      cursor = r.nextCursor;
    } while (cursor);
    c.ferramentas = lista;
  })().catch((e) => { c.erro = e instanceof Error ? e.message : String(e); t.fechar(); });
  conexoes.set(k, c);
  return c;
}

function fechar(raiz: string, nome: string) {
  for (const [k, c] of conexoes) if (k.startsWith(chave(raiz, nome) + '::')) { c.t.fechar(); conexoes.delete(k); }
}
export function fecharTodos() { for (const c of conexoes.values()) c.t.fechar(); conexoes.clear(); }

/* Liga os servidores aprovados do projeto e devolve as ferramentas e as
 * instrucoes de cada um. Servidor que falhou aparece em erros. */
export async function carregar(raiz: string): Promise<{ ferramentas: FerrMcp[]; instrucoes: string; erros: string[]; pendentes: Servidor[] }> {
  const todos = servidores(raiz);
  const ativos = todos.filter((s) => s.aprovado);
  const cons = ativos.map((s) => [s, conectar(raiz, s)] as const);
  await Promise.all(cons.map(([, c]) => c.pronta));
  const ferramentas: FerrMcp[] = [];
  const instr: string[] = [];
  const erros: string[] = [];
  for (const [s, c] of cons) {
    if (c.erro) { erros.push(s.nome + ': ' + c.erro); continue; }
    ferramentas.push(...c.ferramentas);
    if (c.instrucoes) instr.push(`## MCP server "${s.nome}"\n` + c.instrucoes);
  }
  return { ferramentas, instrucoes: instr.join('\n\n'), erros, pendentes: todos.filter((s) => !s.aprovado) };
}

/* Resultado do MCP em texto para o modelo (imagem, audio e recurso viram aviso). */
export function projetar(conteudo: unknown, nome: string): string {
  const out: string[] = [];
  for (const b of (Array.isArray(conteudo) ? conteudo : []) as Record<string, unknown>[]) {
    if (!b || typeof b !== 'object') { out.push('[unsupported MCP content block: expected an object]'); continue; }
    switch (b.type) {
      case 'text': if (b.text !== undefined) out.push(String(b.text)); break;
      case 'image': out.push(`[image result: ${b.mimeType ?? 'unknown media type'}; this model cannot see images]`); break;
      case 'resource_link': out.push(b.name === undefined || b.uri === undefined
        ? '[resource link unavailable: the MCP block is missing its name or URI]' : `Resource link: ${b.name} (${b.uri})`); break;
      case 'audio': out.push(`[audio result unsupported: ${b.mimeType ?? 'unknown media type'}]`); break;
      case 'resource': {
        const r = b.resource as { text?: string; uri?: string } | undefined;
        out.push(r?.text !== undefined ? r.text : '[embedded resource unsupported]'); break;
      }
      default: out.push(`[unsupported MCP content type: ${String(b.type)}]`);
    }
  }
  return out.length ? out.join('\n') : `(${nome} returned no model-visible content)`;
}

export async function chamar(raiz: string, f: FerrMcp, args: Record<string, unknown>, sinal: AbortSignal): Promise<{ ok: boolean; texto: string }> {
  const s = servidores(raiz).find((x) => x.nome === f.servidor && x.aprovado);
  if (!s) throw new Error('MCP server "' + f.servidor + '" is not enabled for this project');
  const c = conectar(raiz, s);
  await c.pronta;
  if (c.erro) throw new Error(c.erro);
  const p = c.t.pedir('tools/call', { name: f.nome, arguments: args }, 5 * 60_000);
  const abortar = new Promise<never>((_, erro) => sinal.addEventListener('abort', () => erro(new Error('aborted')), { once: true }));
  const r = await Promise.race([p, abortar]);
  const texto = projetar(r.content, f.publico);
  const estruturado = r.structuredContent && (!Array.isArray(r.content) || !r.content.length) ? JSON.stringify(r.structuredContent, null, 1) : '';
  return { ok: r.isError !== true, texto: estruturado || texto };
}
