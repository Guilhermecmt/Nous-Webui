// Navegacao de codigo por language server (LSP): definicao, referencias,
// implementacao e hover. Adaptado do DeepSeek Harness (dsh-lsp, dsh-lsp-stdio
// e dsh-tool-lsp, MIT, (c) 2026 DeepSeek): um servidor por projeto, iniciado
// sob demanda; cada consulta abre o arquivo do disco (didOpen), pergunta e
// fecha (didClose), uma por vez. O modelo usa linha e coluna a partir de 1.

import fs from 'node:fs';
import path from 'node:path';
import { spawn, type ChildProcess } from 'node:child_process';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';

export type Operacao = 'goToDefinition' | 'findReferences' | 'goToImplementation' | 'hover';
export const OPERACOES: Operacao[] = ['goToDefinition', 'findReferences', 'goToImplementation', 'hover'];

type Servidor = { nome: string; pacote: string; bin: string; comando: string; args: string[]; linguagens: Record<string, string> };

const SERVIDORES: Servidor[] = [
  { nome: 'typescript', pacote: 'typescript-language-server', bin: 'lib/cli.mjs', comando: 'typescript-language-server', args: ['--stdio'],
    linguagens: { '.ts': 'typescript', '.tsx': 'typescriptreact', '.mts': 'typescript', '.cts': 'typescript',
      '.js': 'javascript', '.jsx': 'javascriptreact', '.mjs': 'javascript', '.cjs': 'javascript' } },
  { nome: 'python', pacote: 'pyright', bin: 'langserver.index.js', comando: 'pyright-langserver', args: ['--stdio'],
    linguagens: { '.py': 'python', '.pyi': 'python' } },
];

const MAX_RESULTADOS = 50;
const OCIOSO_MS = 10 * 60_000;
const ESPERA_MS = 30_000;
const req = createRequire(import.meta.url);

/* O servidor do arquivo, pela extensao. */
export function servidorPara(arquivo: string): Servidor | null {
  const ext = path.extname(arquivo).toLowerCase();
  return SERVIDORES.find((s) => ext in s.linguagens) || null;
}

/* Comando para iniciar: o pacote em node_modules (via node) ou o do PATH. */
function comandoDe(s: Servidor): { cmd: string; args: string[]; shell: boolean } | null {
  try {
    const pkg = req.resolve(s.pacote + '/package.json');
    const js = path.join(path.dirname(pkg), s.bin);
    if (fs.existsSync(js)) return { cmd: process.execPath, args: [js, ...s.args], shell: false };
  } catch { /* nao instalado junto */ }
  const dirs = (process.env.PATH || '').split(path.delimiter);
  for (const d of dirs) {
    for (const ext of process.platform === 'win32' ? ['.cmd', '.exe', ''] : ['']) {
      const full = path.join(d, s.comando + ext);
      if (!d || !fs.existsSync(full)) continue;
      // .cmd no Windows so' roda via shell: a linha vai inteira, sem args separados
      return process.platform === 'win32' ? { cmd: '"' + full + '" ' + s.args.join(' '), args: [], shell: true } : { cmd: full, args: s.args, shell: false };
    }
  }
  return null;
}

export function disponiveis(): { nome: string; ok: boolean }[] {
  return SERVIDORES.map((s) => ({ nome: s.nome, ok: !!comandoDe(s) }));
}

/* ------------------------------------------------------------ conexao JSON-RPC (Content-Length) */
class Conexao {
  private buf = Buffer.alloc(0);
  private seq = 0;
  private pendentes = new Map<number, { ok: (v: unknown) => void; erro: (e: Error) => void }>();
  morta: Error | null = null;
  carregando = 0;                 // tarefas de $/progress abertas (o servidor ainda indexa o projeto)
  ultimoProgresso = Date.now();
  diag = new Map<string, { lista: unknown[]; em: number }>();   // uri -> ultimo publishDiagnostics
  private p: ChildProcess;

  constructor(p: ChildProcess) {
    this.p = p;
    p.stdout!.on('data', (d: Buffer) => this.receber(d));
    p.stderr!.on('data', () => { /* log do servidor: ignorado */ });
    const fim = (e: Error) => { this.morta = e; for (const x of this.pendentes.values()) x.erro(e); this.pendentes.clear(); };
    p.on('exit', (c) => fim(new Error('o language server saiu (codigo ' + c + ')')));
    p.on('error', (e) => fim(e));
  }

  private enviar(msg: unknown) {
    const corpo = Buffer.from(JSON.stringify(msg), 'utf8');
    this.p.stdin!.write(Buffer.concat([Buffer.from('Content-Length: ' + corpo.length + '\r\n\r\n', 'ascii'), corpo]));
  }

  private receber(d: Buffer) {
    this.buf = Buffer.concat([this.buf, d]);
    for (;;) {
      const sep = this.buf.indexOf('\r\n\r\n');
      if (sep < 0) return;
      const m = /Content-Length:\s*(\d+)/i.exec(this.buf.toString('ascii', 0, sep));
      if (!m) { this.buf = this.buf.subarray(sep + 4); continue; }
      const ini = sep + 4, fim = ini + Number(m[1]);
      if (this.buf.length < fim) return;
      const txt = this.buf.toString('utf8', ini, fim);
      this.buf = this.buf.subarray(fim);
      let msg: Record<string, unknown>;
      try { msg = JSON.parse(txt); } catch { continue; }
      this.tratar(msg);
    }
  }

  private tratar(msg: Record<string, unknown>) {
    if ('id' in msg && ('result' in msg || 'error' in msg) && !('method' in msg)) {
      const p = this.pendentes.get(Number(msg.id));
      if (!p) return;
      this.pendentes.delete(Number(msg.id));
      const e = msg.error as { message?: string } | undefined;
      if (e) p.erro(new Error(e.message || 'erro do language server'));
      else p.ok(msg.result);
      return;
    }
    if (msg.method === '$/progress') {
      const k = ((msg.params as { value?: { kind?: string } })?.value || {}).kind;
      if (k === 'begin') this.carregando++;
      else if (k === 'end') this.carregando = Math.max(0, this.carregando - 1);
      this.ultimoProgresso = Date.now();
      return;
    }
    if (msg.method === 'textDocument/publishDiagnostics') {
      const pr = msg.params as { uri?: string; diagnostics?: unknown[] } | undefined;
      if (pr?.uri) this.diag.set(chaveUri(pr.uri), { lista: pr.diagnostics || [], em: Date.now() });
      return;
    }
    if ('id' in msg && 'method' in msg) {
      // pedidos do servidor: configuracao vazia, registro e progresso aceitos
      const metodo = String(msg.method);
      if (metodo === 'workspace/configuration') {
        const itens = ((msg.params as { items?: unknown[] })?.items || []).map(() => null);
        this.enviar({ jsonrpc: '2.0', id: msg.id, result: itens });
      } else if (metodo === 'client/registerCapability' || metodo === 'window/workDoneProgress/create' || metodo === 'workspace/workspaceFolders') {
        this.enviar({ jsonrpc: '2.0', id: msg.id, result: null });
      } else {
        this.enviar({ jsonrpc: '2.0', id: msg.id, error: { code: -32601, message: 'method not supported: ' + metodo } });
      }
    }
  }

  pedir(metodo: string, params: unknown, ms = ESPERA_MS): Promise<unknown> {
    if (this.morta) return Promise.reject(this.morta);
    const id = ++this.seq;
    return new Promise((ok, erro) => {
      const t = setTimeout(() => {
        this.pendentes.delete(id);
        this.enviar({ jsonrpc: '2.0', method: '$/cancelRequest', params: { id } });
        erro(new Error('o language server nao respondeu em ' + Math.round(ms / 1000) + 's'));
      }, ms);
      this.pendentes.set(id, { ok: (v) => { clearTimeout(t); ok(v); }, erro: (e) => { clearTimeout(t); erro(e); } });
      this.enviar({ jsonrpc: '2.0', id, method: metodo, params });
    });
  }

  avisar(metodo: string, params: unknown) { if (!this.morta) this.enviar({ jsonrpc: '2.0', method: metodo, params }); }
}

/* ------------------------------------------------------------ uma instancia por servidor + projeto */
type Instancia = { con: Conexao; proc: ChildProcess; pronta: Promise<void>; fila: Promise<unknown>; relogio?: NodeJS.Timeout; raiz: string; aquecido: boolean };
const instancias = new Map<string, Instancia>();

function iniciar(s: Servidor, raiz: string): Instancia {
  const chave = s.nome + '\u0000' + raiz;
  const ja = instancias.get(chave);
  if (ja && !ja.con.morta) return ja;
  const c = comandoDe(s);
  if (!c) throw new Error(`LSP_UNAVAILABLE: no language server for ${s.nome} files is installed (${s.pacote}). ` +
    'Use grep and read instead.');
  const proc = spawn(c.cmd, c.args, { cwd: raiz, shell: c.shell, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  const con = new Conexao(proc);
  const uri = pathToFileURL(raiz).href;
  const pronta = (async () => {
    await con.pedir('initialize', {
      processId: process.pid, rootUri: uri, workspaceFolders: [{ uri, name: path.basename(raiz) }],
      capabilities: {
        general: { positionEncodings: ['utf-16'] },
        workspace: { workspaceFolders: true, configuration: true },
        window: { workDoneProgress: true },
        textDocument: {
          synchronization: { dynamicRegistration: false },
          hover: { contentFormat: ['markdown', 'plaintext'] },
          definition: { linkSupport: true }, implementation: { linkSupport: true }, references: {},
          publishDiagnostics: { relatedInformation: false },
        },
      },
    }, 60_000);
    con.avisar('initialized', {});
  })();
  const inst: Instancia = { con, proc, pronta, fila: Promise.resolve(), raiz, aquecido: false };
  instancias.set(chave, inst);
  proc.on('exit', () => { if (instancias.get(chave) === inst) instancias.delete(chave); });
  return inst;
}

function adiar(inst: Instancia) {
  if (inst.relogio) clearTimeout(inst.relogio);
  inst.relogio = setTimeout(() => encerrar(inst), OCIOSO_MS);
  inst.relogio.unref();
}

function encerrar(inst: Instancia) {
  inst.con.pedir('shutdown', null, 3000).catch(() => {}).finally(() => {
    inst.con.avisar('exit', null);
    setTimeout(() => { try { inst.proc.kill(); } catch { /* ja saiu */ } }, 1000).unref();
  });
}

export function encerrarTodos() { for (const i of instancias.values()) encerrar(i); instancias.clear(); }

/* ------------------------------------------------------------ resultados */
type Local = { arquivo: string; linha: number; coluna: number; trecho: string };

function locais(raiz: string, r: unknown): Local[] {
  const lista = Array.isArray(r) ? r : r ? [r] : [];
  const out: Local[] = [];
  const cache = new Map<string, string[]>();
  for (const x of lista as Record<string, unknown>[]) {
    const uri = String(x.uri ?? x.targetUri ?? '');
    const range = (x.range ?? x.targetSelectionRange ?? x.targetRange) as { start: { line: number; character: number } } | undefined;
    if (!uri.startsWith('file:') || !range) continue;
    const abs = fileURLToPath(uri);
    let ls = cache.get(abs);
    if (!ls) { try { ls = fs.readFileSync(abs, 'utf8').split(/\r?\n/); } catch { ls = []; } cache.set(abs, ls); }
    const rel = path.relative(raiz, abs).split(path.sep).join('/');
    out.push({ arquivo: rel.startsWith('..') ? abs : rel, linha: range.start.line + 1, coluna: range.start.character + 1,
      trecho: (ls[range.start.line] || '').trim().slice(0, 160) });
  }
  return out;
}

function textoHover(r: unknown): string {
  if (!r) return '';
  const c = (r as { contents?: unknown }).contents;
  const um = (x: unknown): string => {
    if (typeof x === 'string') return x;
    const m = x as { language?: string; value?: string } | null;
    if (!m || typeof m !== 'object' || m.value === undefined) return '';
    return m.language ? '```' + m.language + '\n' + m.value + '\n```' : String(m.value);
  };
  return (Array.isArray(c) ? c.map(um) : [um(c)]).filter(Boolean).join('\n\n').trim();
}

/* ------------------------------------------------------------ consulta */
const METODO: Record<Operacao, string> = {
  goToDefinition: 'textDocument/definition', findReferences: 'textDocument/references',
  goToImplementation: 'textDocument/implementation', hover: 'textDocument/hover',
};

export async function consultar(raiz: string, abs: string, op: Operacao, linha: number, coluna: number): Promise<string> {
  if (!OPERACOES.includes(op)) throw new Error('operation must be one of ' + OPERACOES.join(', '));
  const s = servidorPara(abs);
  if (!s) throw new Error('LSP_UNAVAILABLE: no language server handles "' + path.extname(abs) + '" files. Use grep and read instead.');
  const inst = iniciar(s, raiz);
  const texto = fs.readFileSync(abs, 'utf8');
  const uri = pathToFileURL(abs).href;
  const rel = path.relative(raiz, abs).split(path.sep).join('/');
  const vez = inst.fila.then(async () => {
    await inst.pronta;
    adiar(inst);
    inst.con.avisar('textDocument/didOpen', { textDocument: { uri, languageId: s.linguagens[path.extname(abs).toLowerCase()], version: 1, text: texto } });
    try {
      // o servidor carrega o projeto ao abrir o primeiro arquivo: antes disso
      // as referencias viriam so' do arquivo aberto
      const aberto = Date.now();
      const ate = aberto + 20_000;
      while (Date.now() < ate && (inst.con.carregando > 0 || Date.now() - inst.con.ultimoProgresso < 800 || (!inst.aquecido && Date.now() - aberto < 1500))) {
        await new Promise((ok) => setTimeout(ok, 150));
      }
      inst.aquecido = true;
      const pos = { line: Math.max(0, linha - 1), character: Math.max(0, coluna - 1) };
      const params: Record<string, unknown> = { textDocument: { uri }, position: pos };
      if (op === 'findReferences') params.context = { includeDeclaration: true };
      return await inst.con.pedir(METODO[op], params);
    } finally {
      inst.con.avisar('textDocument/didClose', { textDocument: { uri } });
    }
  });
  inst.fila = vez.catch(() => {});
  const r = await vez;
  const onde = `${rel}:${linha}:${coluna}`;
  if (op === 'hover') {
    const h = textoHover(r);
    return h ? h : 'No hover information at ' + onde + '.';
  }
  const l = locais(raiz, r);
  if (!l.length) return `No ${op === 'findReferences' ? 'references' : op === 'goToImplementation' ? 'implementations' : 'definition'} found at ${onde}. ` +
    'Check that line and character point at the symbol name (1-based).';
  const corte = l.slice(0, MAX_RESULTADOS);
  return corte.map((x) => `${x.arquivo}:${x.linha}:${x.coluna}: ${x.trecho}`).join('\n') +
    (l.length > MAX_RESULTADOS ? `\n... (${l.length - MAX_RESULTADOS} more)` : '');
}

/* ------------------------------------------------------------ diagnosticos depois de editar */
export type Diag = { linha: number; coluna: number; codigo: string; msg: string; trecho: string };
const ESPERA_DIAG_MS = 8_000;        // depois de aquecido
const ESPERA_DIAG_1A_MS = 20_000;    // o 1o arquivo carrega o projeto inteiro
const QUIETO_MS = 600;               // sem novo publishDiagnostics por este tempo = terminou

/* Os erros (nao avisos) que o language server acha em `texto`, como se fosse o
 * conteudo de `abs`. `null` quando nao ha servidor ou ele nao respondeu a tempo:
 * a edicao nunca fica esperando por isso. Abre, espera o publishDiagnostics
 * assentar e fecha, na mesma fila das consultas. */
export async function diagnosticar(raiz: string, abs: string, texto: string): Promise<Diag[] | null> {
  const s = servidorPara(abs);
  if (!s || !comandoDe(s)) return null;
  let inst: Instancia;
  try { inst = iniciar(s, raiz); } catch { return null; }
  const uri = pathToFileURL(abs).href;
  const vez = inst.fila.then(async (): Promise<Diag[] | null> => {
    try { await inst.pronta; } catch { return null; }
    adiar(inst);
    inst.con.diag.delete(chaveUri(uri));
    inst.con.avisar('textDocument/didOpen', { textDocument: { uri, languageId: s.linguagens[path.extname(abs).toLowerCase()], version: 1, text: texto } });
    try {
      const ini = Date.now();
      const ate = ini + (inst.aquecido ? ESPERA_DIAG_MS : ESPERA_DIAG_1A_MS);
      for (;;) {
        const d = inst.con.diag.get(chaveUri(uri));
        if (d && Date.now() - d.em >= QUIETO_MS && inst.con.carregando === 0) break;
        if (Date.now() > ate || inst.con.morta) return null;
        await new Promise((ok) => setTimeout(ok, 100));
      }
      inst.aquecido = true;
      const linhas = texto.split(/\r?\n/);
      return (inst.con.diag.get(chaveUri(uri))!.lista as Record<string, unknown>[])
        .filter((x) => x.severity === 1 || x.severity === undefined)
        .map((x) => {
          const r = (x.range as { start: { line: number; character: number } }).start;
          return { linha: r.line + 1, coluna: r.character + 1, codigo: x.code === undefined ? '' : String(x.code),
            msg: String(x.message || '').replace(/\s+/g, ' ').trim(), trecho: (linhas[r.line] || '').trim() };
        });
    } finally {
      inst.con.avisar('textDocument/didClose', { textDocument: { uri } });
      inst.con.diag.delete(chaveUri(uri));
    }
  });
  inst.fila = vez.catch(() => {});
  return vez.catch(() => null);
}

/* Os erros que a edicao introduziu: os de `depois` que `antes` (null = arquivo
 * novo) ainda nao tinha. A comparacao ignora a posicao (a edicao desloca
 * linhas): vale mensagem, codigo e o texto da linha. So' consulta o `antes`
 * quando o `depois` tem erro. */
export async function diagnosticosNovos(raiz: string, abs: string, antes: string | null, depois: string): Promise<Diag[] | null> {
  const dep = await diagnosticar(raiz, abs, depois);
  if (!dep || !dep.length || antes === null) return dep;
  const ant = await diagnosticar(raiz, abs, antes);
  if (!ant) return dep;
  const chave = (d: Diag) => d.codigo + '|' + d.msg + '|' + d.trecho;
  const resto = new Map<string, number>();
  for (const d of ant) resto.set(chave(d), (resto.get(chave(d)) || 0) + 1);
  return dep.filter((d) => {
    const n = resto.get(chave(d)) || 0;
    if (n > 0) { resto.set(chave(d), n - 1); return false; }
    return true;
  });
}

/* O texto curto que volta ao modelo (ate 5 erros, mensagem cortada). */
export function textoDiagnosticos(rel: string, d: Diag[], max = 5): string {
  const l = d.slice(0, max).map((x) => `${rel}:${x.linha}:${x.coluna} error${x.codigo ? ' ' + x.codigo : ''}: ${x.msg.slice(0, 240)}`);
  return `LSP diagnostics introduced by this edit (${d.length}); fix them in your next step, or ignore them if they are unrelated:\n` + l.join('\n') +
    (d.length > max ? `\n... (${d.length - max} more)` : '');
}

/* O mesmo arquivo chega como file:///c%3A/x (servidor) ou file:///C:/x (Node):
 * a chave compara o caminho de verdade (sem diferenca de maiusculas no Windows). */
function chaveUri(uri: string): string {
  try { const p = path.normalize(fileURLToPath(uri)); return process.platform === 'win32' ? p.toLowerCase() : p; } catch { return uri; }
}
