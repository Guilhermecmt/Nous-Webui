// O IDE do Nous Code: arquivos, busca, Git, terminal (ConPTY) e a pagina.
// Tudo relativo a uma "raiz" (a pasta do projeto), validada a cada pedido.

import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
import { spawn, execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { WebSocketServer, type WebSocket } from 'ws';
import * as pty from '@lydell/node-pty';
import * as F from './ferramentas.ts';

const AQUI = path.dirname(fileURLToPath(import.meta.url));
const NM = path.join(AQUI, 'node_modules');

/* ------------------------------------------------------------ estaticos */
const TIPOS: Record<string, string> = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon',
  '.ttf': 'font/ttf', '.woff': 'font/woff', '.woff2': 'font/woff2', '.map': 'application/json',
};
const ESTATICOS: [string, string][] = [
  ['/ide/', path.join(AQUI, 'ide')],
  ['/vendor/monaco/', path.join(NM, 'monaco-editor', 'min')],
  ['/vendor/xterm/', path.join(NM, '@xterm', 'xterm')],
  ['/vendor/xterm-fit/', path.join(NM, '@xterm', 'addon-fit', 'lib')],
  ['/marca/', path.join(AQUI, '..', 'branding', 'assets')],
];
export function estatico(url: string, res: http.ServerResponse): boolean {
  let rota = url.split('?')[0];
  if (rota === '/' || rota === '/index.html') rota = '/ide/index.html';
  for (const [pref, dir] of ESTATICOS) {
    if (!rota.startsWith(pref)) continue;
    const abs = path.resolve(dir, decodeURIComponent(rota.slice(pref.length)));
    if (!abs.startsWith(path.resolve(dir) + path.sep) || !fs.existsSync(abs) || fs.statSync(abs).isDirectory()) return false;
    res.writeHead(200, { 'Content-Type': TIPOS[path.extname(abs)] || 'application/octet-stream',
      'Cache-Control': pref === '/ide/' ? 'no-cache' : 'max-age=86400' });
    fs.createReadStream(abs).pipe(res);
    return true;
  }
  return false;
}

/* ------------------------------------------------------------ arquivos */
export function arvore(raiz: string, dir: string) {
  const abs = F.resolver(raiz, dir || '.');
  return fs.readdirSync(abs, { withFileTypes: true })
    .filter((d) => d.name !== '.git')
    .map((d) => ({ nome: d.name, pasta: d.isDirectory(), apagado: d.isDirectory() && F.IGNORAR.has(d.name) }))
    .sort((a, b) => Number(b.pasta) - Number(a.pasta) || a.nome.localeCompare(b.nome, 'pt-BR', { sensitivity: 'base' }));
}

export function lerArquivo(raiz: string, caminho: string) {
  const abs = F.resolver(raiz, caminho);
  const st = fs.statSync(abs);
  if (st.size > 5_000_000) return { grande: true, tamanho: st.size };
  const buf = fs.readFileSync(abs);
  if (buf.subarray(0, 8000).includes(0)) return { binario: true, tamanho: st.size };
  return { conteudo: buf.toString('utf8'), crlf: buf.includes('\r\n') };
}

export function salvar(raiz: string, caminho: string, conteudo: string) { F.gravar(F.resolver(raiz, caminho), conteudo); }

export function criar(raiz: string, caminho: string, pasta: boolean) {
  const abs = F.resolver(raiz, caminho);
  if (fs.existsSync(abs)) throw new Error('ja existe: ' + caminho);
  if (pasta) fs.mkdirSync(abs, { recursive: true });
  else F.gravar(abs, '');
}

export function renomear(raiz: string, de: string, para: string) {
  const a = F.resolver(raiz, de), b = F.resolver(raiz, para);
  if (fs.existsSync(b)) throw new Error('ja existe: ' + para);
  fs.mkdirSync(path.dirname(b), { recursive: true });
  fs.renameSync(a, b);
}

/* Apagar manda para a Lixeira do Windows (da para recuperar). */
export function apagar(raiz: string, caminho: string): Promise<void> {
  const abs = F.resolver(raiz, caminho);
  if (abs === path.resolve(raiz)) return Promise.reject(new Error('nao da para apagar a pasta do projeto'));
  const pasta = fs.statSync(abs).isDirectory();
  const ps = `Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::Delete${pasta ? 'Directory' : 'File'}($env:ALVO, 'OnlyErrorDialogs', 'SendToRecycleBin')`;
  return new Promise((ok, erro) => {
    execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], { env: { ...process.env, ALVO: abs }, windowsHide: true },
      (e) => (e ? erro(new Error('nao consegui apagar: ' + e.message)) : ok()));
  });
}

/* Todos os arquivos (para o Ctrl+P). */
export function todosArquivos(raiz: string): string[] {
  const out: string[] = [];
  function andar(dir: string) {
    if (out.length >= 20000) return;
    let itens: fs.Dirent[];
    try { itens = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const it of itens) {
      if (it.isDirectory()) { if (!F.IGNORAR.has(it.name)) andar(path.join(dir, it.name)); }
      else out.push(F.relativo(raiz, path.join(dir, it.name)));
    }
  }
  andar(path.resolve(raiz));
  return out;
}

/* Busca no projeto (Ctrl+Shift+F). */
export function buscar(raiz: string, q: string, regex: boolean, maiusculas: boolean) {
  if (!q) return [];
  const flags = maiusculas ? 'g' : 'gi';
  let re: RegExp;
  try { re = new RegExp(regex ? q : q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), flags); } catch (e) { throw new Error('expressao invalida'); }
  const achados: { arquivo: string; linha: number; coluna: number; fim: number; texto: string }[] = [];
  for (const rel of todosArquivos(raiz)) {
    if (achados.length >= 1000) break;
    const abs = path.join(raiz, rel);
    let t: string;
    try {
      if (fs.statSync(abs).size > 1_000_000) continue;
      const buf = fs.readFileSync(abs);
      if (buf.subarray(0, 8000).includes(0)) continue;
      t = buf.toString('utf8');
    } catch { continue; }
    const ls = t.split(/\r?\n/);
    for (let i = 0; i < ls.length && achados.length < 1000; i++) {
      re.lastIndex = 0;
      const m = re.exec(ls[i]);
      if (m) achados.push({ arquivo: rel, linha: i + 1, coluna: m.index + 1, fim: m.index + 1 + m[0].length, texto: ls[i].slice(0, 300) });
    }
  }
  return achados;
}

/* ------------------------------------------------------------ git */
function git(raiz: string, args: string[], entrada?: string): Promise<{ ok: boolean; saida: string }> {
  return new Promise((ok) => {
    const p = spawn('git', args, { cwd: raiz, windowsHide: true, env: { ...process.env, GIT_TERMINAL_PROMPT: '0', LC_ALL: 'C' } });
    let saida = '';
    p.stdout.on('data', (d) => { saida += d.toString('utf8'); });
    p.stderr.on('data', (d) => { saida += d.toString('utf8'); });
    p.on('close', (c) => ok({ ok: c === 0, saida }));
    p.on('error', (e) => ok({ ok: false, saida: String(e) }));
    if (entrada !== undefined) { p.stdin.write(entrada); p.stdin.end(); }
  });
}

export async function gitStatus(raiz: string) {
  const r = await git(raiz, ['status', '--porcelain=v1', '-b', '-z', '--untracked-files=all']);
  if (!r.ok) return { repo: false, ramo: '', arquivos: [] as { caminho: string; x: string; y: string }[] };
  const partes = r.saida.split('\0').filter(Boolean);
  let ramo = '';
  const arquivos: { caminho: string; x: string; y: string; de?: string }[] = [];
  for (let i = 0; i < partes.length; i++) {
    const p = partes[i];
    if (p.startsWith('## ')) { ramo = p.slice(3).split('...')[0].replace('No commits yet on ', ''); continue; }
    const x = p[0], y = p[1], caminho = p.slice(3);
    const item: { caminho: string; x: string; y: string; de?: string } = { caminho, x, y };
    if (x === 'R' || x === 'C') { item.de = partes[++i]; }
    arquivos.push(item);
  }
  return { repo: true, ramo, arquivos };
}

export async function gitOriginal(raiz: string, caminho: string): Promise<string> {
  F.resolver(raiz, caminho);  // valida
  const r = await git(raiz, ['show', 'HEAD:' + caminho.replace(/\\/g, '/')]);
  return r.ok ? r.saida : '';
}

export async function gitCommit(raiz: string, mensagem: string) {
  if (!mensagem.trim()) throw new Error('escreva a mensagem do commit');
  const a = await git(raiz, ['add', '-A']);
  if (!a.ok) throw new Error(a.saida.trim());
  const c = await git(raiz, ['commit', '-F', '-'], mensagem);
  if (!c.ok) throw new Error(/nothing to commit/.test(c.saida) ? 'nada para commitar' : c.saida.trim().slice(0, 400));
  return c.saida.split('\n')[0];
}

export async function gitDescartar(raiz: string, caminho: string, novo: boolean) {
  F.resolver(raiz, caminho);
  if (novo) return apagar(raiz, caminho);
  const r = await git(raiz, ['checkout', 'HEAD', '--', caminho]);
  if (!r.ok) throw new Error(r.saida.trim());
}

/* ------------------------------------------------------------ janela */
/* Abre o IDE numa janela propria (modo app do Edge; Chrome se nao houver Edge). */
export function abrirJanela(porta: number, pasta?: string) {
  const url = `http://127.0.0.1:${porta}/` + (pasta ? '?pasta=' + encodeURIComponent(pasta) : '');
  const cands = [
    path.join(process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Google', 'Chrome', 'Application', 'chrome.exe'),
    path.join(process.env.LOCALAPPDATA || '', 'Google', 'Chrome', 'Application', 'chrome.exe'),
  ];
  const exe = cands.find((c) => fs.existsSync(c));
  if (exe) spawn(exe, ['--app=' + url, '--window-size=1600,1000'], { detached: true, stdio: 'ignore' }).unref();
  else spawn('cmd.exe', ['/c', 'start', '', url], { detached: true, stdio: 'ignore', windowsHide: true }).unref();
  return url;
}

/* ------------------------------------------------------------ websocket: terminal + mudancas no disco */
export function ligarWs(servidor: http.Server, origemOk: (o?: string) => boolean, pastaValida: (p: string) => string) {
  const wss = new WebSocketServer({ noServer: true });
  servidor.on('upgrade', (req, sock, cabeca) => {
    if (!req.url || !req.url.startsWith('/ws') || !origemOk(req.headers.origin)) { sock.destroy(); return; }
    wss.handleUpgrade(req, sock, cabeca, (ws) => conexao(ws));
  });

  function conexao(ws: WebSocket) {
    const terms = new Map<string, pty.IPty>();
    let vigia: fs.FSWatcher | null = null;
    let pend = new Set<string>(), relogio: NodeJS.Timeout | null = null;
    const manda = (m: object) => { if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(m)); };

    ws.on('message', (bruto) => {
      let m: Record<string, unknown>;
      try { m = JSON.parse(String(bruto)); } catch { return; }
      const id = String(m.id || '');
      try {
        if (m.t === 'observar') {
          vigia?.close();
          const raiz = pastaValida(String(m.raiz));
          vigia = fs.watch(raiz, { recursive: true }, (_ev, nome) => {
            if (!nome) return;
            const rel = String(nome).split(path.sep).join('/');
            if (rel.split('/').some((p) => p === '.git' || F.IGNORAR.has(p))) return;
            pend.add(rel);
            if (!relogio) relogio = setTimeout(() => { manda({ t: 'fs', caminhos: [...pend] }); pend = new Set(); relogio = null; }, 250);
          });
        } else if (m.t === 'term-abrir') {
          const raiz = pastaValida(String(m.raiz));
          const p = pty.spawn('powershell.exe', ['-NoLogo'], {
            name: 'xterm-256color', cols: Number(m.cols) || 100, rows: Number(m.rows) || 24, cwd: raiz,
            env: { ...process.env, TERM_PROGRAM: 'NousCode' } as Record<string, string>,
          });
          terms.set(id, p);
          p.onData((d) => manda({ t: 'term-saida', id, d }));
          p.onExit(({ exitCode }) => { terms.delete(id); manda({ t: 'term-fim', id, codigo: exitCode }); });
        } else if (m.t === 'term-escrever') terms.get(id)?.write(String(m.d));
        else if (m.t === 'term-tamanho') terms.get(id)?.resize(Math.max(10, Number(m.cols)), Math.max(3, Number(m.rows)));
        else if (m.t === 'term-fechar') { terms.get(id)?.kill(); terms.delete(id); }
      } catch (e) {
        manda({ t: 'erro', id, texto: e instanceof Error ? e.message : String(e) });
      }
    });
    ws.on('close', () => {
      vigia?.close();
      for (const p of terms.values()) { try { p.kill(); } catch { /* ja saiu */ } }
    });
  }
}
