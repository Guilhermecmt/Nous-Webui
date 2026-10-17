// Nous Code: o servico do painel Codigo (http://127.0.0.1:8998).
// Sem dependencias: so' o Node (>= 22.18, que roda TypeScript direto).
//
//   GET  /health                      {ok, versao}
//   GET  /modelos                     modelos do Ollama que servem para o agente
//   GET  /pastas                      projetos recentes
//   POST /escolher-pasta              abre a janela "Escolher pasta" do Windows
//   GET  /sessoes?pasta=              conversas (de um projeto)
//   POST /sessoes {pasta, modelo?}    nova conversa
//   GET  /sessao?id=                  conversa inteira (eventos + arquivos mudados)
//   POST /sessao/ajustes {id, modelo?, modo?}
//   POST /sessao/apagar {id}
//   POST /mensagem {id, texto}        roda o agente; responde em NDJSON, um evento por linha
//   POST /aprovar {id, pedido, ok, sempre?}
//   POST /parar {id}
//   POST /desfazer {id, arquivo?}     volta os arquivos ao que eram antes da conversa
//
// IDE (a janela propria do Nous Code, servida aqui mesmo):
//   GET  /                            a pagina do IDE (?pasta= abre direto um projeto)
//   GET  /fs/arvore?raiz=&dir=        um nivel da arvore de arquivos
//   GET  /fs/ler?raiz=&caminho=       conteudo de um arquivo
//   POST /fs/salvar|/fs/novo|/fs/renomear|/fs/apagar   (apagar vai para a Lixeira)
//   GET  /fs/arquivos?raiz=           todos os arquivos (Ctrl+P)
//   GET  /fs/buscar?raiz=&q=&regex=&maiusculas=      (Ctrl+Shift+F)
//   GET  /git/status|/git/original    POST /git/commit|/git/descartar
//   POST /abrir-janela {pasta?}       abre o IDE numa janela propria (o Nous usa)
//   WS   /ws                          terminal (PowerShell num ConPTY) e avisos de arquivo mudado
//
// So' aceita o proprio Nous (localhost:8080) como pagina de origem: este servico
// muda arquivos e roda comandos, entao outro site aberto no navegador nao pode
// falar com ele.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { modelos } from './modelo.ts';
import { turno, desfazer, mudancas, type Sessao, type Evento } from './agente.ts';
import * as IDE from './ide.ts';

const PORTA = Number(process.env.NOUS_CODE_PORT || 8998);
const VERSAO = '0.1.0';
const DADOS = path.join(process.env.DATA_DIR || path.join(os.homedir(), 'NousData'), 'code');
const DIR_SESSOES = path.join(DADOS, 'sessoes');
const ARQ_PASTAS = path.join(DADOS, 'pastas.json');
const ORIGENS = new Set(['http://localhost:8080', 'http://127.0.0.1:8080',
  'http://localhost:' + PORTA, 'http://127.0.0.1:' + PORTA]);  // o Nous e a janela do IDE
const MODELO_PADRAO = process.env.NOUS_CODE_MODEL || 'qwen2.5-coder:14b';
fs.mkdirSync(DIR_SESSOES, { recursive: true });

/* ------------------------------------------------------------ sessoes */
const abertas = new Map<string, Sessao>();
const rodando = new Map<string, AbortController>();
const pendentes = new Map<string, (r: { ok: boolean; sempre?: boolean }) => void>();  // "sessao|pedido"

function arqSessao(id: string) {
  if (!/^[a-z0-9]{6,40}$/.test(id)) throw new Error('id invalido');
  return path.join(DIR_SESSOES, id + '.json');
}
function carregar(id: string): Sessao {
  const s = abertas.get(id) || JSON.parse(fs.readFileSync(arqSessao(id), 'utf8')) as Sessao;
  abertas.set(id, s);
  return s;
}
function salvar(s: Sessao) {
  s.atualizado = Date.now();
  const tmp = arqSessao(s.id) + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(s));
  fs.renameSync(tmp, arqSessao(s.id));
}
function listarSessoes(pasta?: string) {
  const out = [];
  for (const n of fs.readdirSync(DIR_SESSOES)) {
    if (!n.endsWith('.json')) continue;
    try {
      const s = JSON.parse(fs.readFileSync(path.join(DIR_SESSOES, n), 'utf8')) as Sessao;
      if (pasta && path.resolve(s.pasta) !== path.resolve(pasta)) continue;
      out.push({ id: s.id, titulo: s.titulo, pasta: s.pasta, atualizado: s.atualizado, rodando: rodando.has(s.id) });
    } catch { /* arquivo quebrado: ignora */ }
  }
  return out.sort((a, b) => b.atualizado - a.atualizado);
}

/* ------------------------------------------------------------ pastas */
function pastaValida(p: string): string {
  const abs = path.resolve(String(p || '').trim().replace(/^"|"$/g, ''));
  if (!fs.existsSync(abs) || !fs.statSync(abs).isDirectory()) throw new Error('essa pasta nao existe: ' + abs);
  const proibidas = [process.env.SystemRoot || 'C:\\Windows', process.env.ProgramFiles || 'C:\\Program Files',
    process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)', os.homedir()].map((x) => path.resolve(x).toLowerCase());
  const baixo = abs.toLowerCase();
  if (path.parse(abs).root.toLowerCase() === baixo) throw new Error('escolha a pasta de um projeto, nao o disco inteiro');
  if (proibidas.some((x) => baixo === x || (x !== path.resolve(os.homedir()).toLowerCase() && baixo.startsWith(x + path.sep))))
    throw new Error('essa pasta e' + "'" + ' do sistema; escolha a pasta de um projeto');
  return abs;
}
function lembrarPasta(p: string) {
  let l: string[] = [];
  try { l = JSON.parse(fs.readFileSync(ARQ_PASTAS, 'utf8')); } catch { /* primeira vez */ }
  l = [p].concat(l.filter((x) => path.resolve(x) !== path.resolve(p))).slice(0, 12);
  fs.writeFileSync(ARQ_PASTAS, JSON.stringify(l));
}
function pastasRecentes(): { pasta: string; nome: string }[] {
  try {
    return (JSON.parse(fs.readFileSync(ARQ_PASTAS, 'utf8')) as string[])
      .filter((p) => fs.existsSync(p)).map((p) => ({ pasta: p, nome: path.basename(p) }));
  } catch { return []; }
}
function escolherPasta(): Promise<string | null> {
  const ps = `Add-Type -AssemblyName System.Windows.Forms
$f = New-Object System.Windows.Forms.Form -Property @{TopMost=$true; ShowInTaskbar=$false; WindowState='Minimized'}
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = 'Escolha a pasta do projeto para o Nous Code'
$d.ShowNewFolderButton = $false
if ($d.ShowDialog($f) -eq 'OK') { [Console]::OutputEncoding=[Text.Encoding]::UTF8; Write-Output $d.SelectedPath }`;
  return new Promise((ok) => {
    const p = spawn('powershell.exe', ['-NoProfile', '-STA', '-Command', ps], { windowsHide: false });
    let saida = '';
    p.stdout.on('data', (d) => { saida += d.toString('utf8'); });
    p.on('close', () => ok(saida.trim() || null));
    p.on('error', () => ok(null));
  });
}

/* ------------------------------------------------------------ http */
function origemOk(req: http.IncomingMessage): boolean {
  const host = (req.headers.host || '').replace(/:\d+$/, '').replace(/^\[|\]$/g, '');
  if (!['localhost', '127.0.0.1', '::1'].includes(host)) return false;  // DNS rebinding
  const o = req.headers.origin;
  return !o || ORIGENS.has(o);
}
function cabecalhos(req: http.IncomingMessage, extra: Record<string, string> = {}) {
  const o = req.headers.origin;
  return { 'Access-Control-Allow-Origin': o && ORIGENS.has(o) ? o : 'null', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type', Vary: 'Origin', 'Cache-Control': 'no-store', ...extra };
}
function json(req: http.IncomingMessage, res: http.ServerResponse, status: number, dados: unknown) {
  res.writeHead(status, cabecalhos(req, { 'Content-Type': 'application/json; charset=utf-8' }));
  res.end(JSON.stringify(dados));
}
async function corpo(req: http.IncomingMessage): Promise<Record<string, unknown>> {
  let t = '';
  for await (const p of req) { t += p; if (t.length > 1_000_000) throw new Error('pedido grande demais'); }
  return t ? JSON.parse(t) : {};
}
function novoId() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 8); }

async function rota(req: http.IncomingMessage, res: http.ServerResponse) {
  const url = new URL(req.url || '/', 'http://localhost');
  const q = (k: string) => url.searchParams.get(k) || '';
  const r = req.method + ' ' + url.pathname;

  if (r === 'GET /health') return json(req, res, 200, { ok: true, versao: VERSAO, modelo: MODELO_PADRAO });

  /* ---- IDE: arquivos, busca, git, janela ---- */
  if (url.pathname.startsWith('/fs/') || url.pathname.startsWith('/git/')) {
    const b = req.method === 'POST' ? await corpo(req) : {};
    const raiz = pastaValida(String(b.raiz || q('raiz')));
    switch (r) {
      case 'GET /fs/arvore': return json(req, res, 200, IDE.arvore(raiz, q('dir')));
      case 'GET /fs/ler': return json(req, res, 200, IDE.lerArquivo(raiz, q('caminho')));
      case 'GET /fs/arquivos': return json(req, res, 200, IDE.todosArquivos(raiz));
      case 'GET /fs/buscar': return json(req, res, 200, IDE.buscar(raiz, q('q'), q('regex') === '1', q('maiusculas') === '1'));
      case 'POST /fs/salvar': IDE.salvar(raiz, String(b.caminho), String(b.conteudo ?? '')); return json(req, res, 200, { ok: true });
      case 'POST /fs/novo': IDE.criar(raiz, String(b.caminho), !!b.pasta); return json(req, res, 200, { ok: true });
      case 'POST /fs/renomear': IDE.renomear(raiz, String(b.de), String(b.para)); return json(req, res, 200, { ok: true });
      case 'POST /fs/apagar': await IDE.apagar(raiz, String(b.caminho)); return json(req, res, 200, { ok: true });
      case 'GET /git/status': return json(req, res, 200, await IDE.gitStatus(raiz));
      case 'GET /git/original': return json(req, res, 200, { conteudo: await IDE.gitOriginal(raiz, q('caminho')) });
      case 'POST /git/commit': return json(req, res, 200, { resumo: await IDE.gitCommit(raiz, String(b.mensagem || '')) });
      case 'POST /git/descartar': await IDE.gitDescartar(raiz, String(b.caminho), !!b.novo); return json(req, res, 200, { ok: true });
    }
  }
  if (r === 'POST /abrir-janela') {
    const b = await corpo(req);
    const pasta = b.pasta ? pastaValida(String(b.pasta)) : undefined;
    return json(req, res, 200, { url: IDE.abrirJanela(PORTA, pasta) });
  }
  if (r === 'GET /modelos') return json(req, res, 200, { padrao: MODELO_PADRAO, modelos: await modelos() });
  if (r === 'GET /pastas') return json(req, res, 200, pastasRecentes());
  if (r === 'POST /escolher-pasta') {
    const p = await escolherPasta();
    if (!p) return json(req, res, 200, { pasta: null });
    return json(req, res, 200, { pasta: pastaValida(p) });
  }
  if (r === 'GET /sessoes') return json(req, res, 200, listarSessoes(q('pasta') || undefined));
  if (r === 'POST /sessoes') {
    const b = await corpo(req);
    const pasta = pastaValida(String(b.pasta || ''));
    const s: Sessao = { id: novoId(), titulo: 'Nova conversa', pasta, modelo: String(b.modelo || MODELO_PADRAO),
      modo: 'perguntar', criado: Date.now(), atualizado: Date.now(), mensagens: [], eventos: [], originais: {}, sempre: [] };
    abertas.set(s.id, s); salvar(s); lembrarPasta(pasta);
    return json(req, res, 200, { id: s.id });
  }
  if (r === 'GET /sessao') {
    const s = carregar(q('id'));
    return json(req, res, 200, { id: s.id, titulo: s.titulo, pasta: s.pasta, modelo: s.modelo, modo: s.modo,
      eventos: s.eventos, mudancas: mudancas(s), rodando: rodando.has(s.id) });
  }
  if (r === 'POST /sessao/ajustes') {
    const b = await corpo(req);
    const s = carregar(String(b.id));
    if (b.modelo) s.modelo = String(b.modelo);
    if (b.modo === 'perguntar' || b.modo === 'editar') s.modo = b.modo;
    salvar(s);
    return json(req, res, 200, { ok: true, modelo: s.modelo, modo: s.modo });
  }
  if (r === 'POST /sessao/apagar') {
    const b = await corpo(req);
    const id = String(b.id);
    if (rodando.has(id)) return json(req, res, 409, { erro: 'a conversa ainda esta rodando' });
    abertas.delete(id);
    fs.rmSync(arqSessao(id), { force: true });
    return json(req, res, 200, { ok: true });
  }
  if (r === 'POST /aprovar') {
    const b = await corpo(req);
    const k = String(b.id) + '|' + String(b.pedido);
    const f = pendentes.get(k);
    if (!f) return json(req, res, 404, { erro: 'nada esperando aprovacao' });
    pendentes.delete(k);
    f({ ok: !!b.ok, sempre: !!b.sempre });
    return json(req, res, 200, { ok: true });
  }
  if (r === 'POST /parar') {
    const b = await corpo(req);
    const id = String(b.id);
    rodando.get(id)?.abort();
    for (const [k, f] of pendentes) if (k.startsWith(id + '|')) { pendentes.delete(k); f({ ok: false }); }
    return json(req, res, 200, { ok: true });
  }
  if (r === 'POST /desfazer') {
    const b = await corpo(req);
    const s = carregar(String(b.id));
    if (rodando.has(s.id)) return json(req, res, 409, { erro: 'pare a conversa antes de desfazer' });
    const feitos = desfazer(s, b.arquivo ? String(b.arquivo) : undefined);
    const e: Evento = { t: 'desfeito', arquivos: feitos };
    s.eventos.push(e);
    s.mensagens.push({ role: 'user', content: '[O usuario desfez as mudancas em: ' + feitos.join(', ') + '. Esses arquivos voltaram ao conteudo original.]' });
    salvar(s);
    return json(req, res, 200, { desfeitos: feitos, mudancas: mudancas(s) });
  }
  if (r === 'POST /mensagem') {
    const b = await corpo(req);
    const s = carregar(String(b.id));
    const texto = String(b.texto || '').trim();
    if (!texto) return json(req, res, 400, { erro: 'mensagem vazia' });
    if (rodando.has(s.id)) return json(req, res, 409, { erro: 'esta conversa ainda esta trabalhando' });
    const ctrl = new AbortController();
    rodando.set(s.id, ctrl);
    res.writeHead(200, cabecalhos(req, { 'Content-Type': 'application/x-ndjson; charset=utf-8' }));
    let aberto = true;
    res.on('close', () => { aberto = false; });  // o painel fechou: o agente segue e salva
    const emitir = (e: Evento) => { if (aberto) res.write(JSON.stringify(e) + '\n'); };
    try {
      await turno(s, texto, {
        emitir, sinal: ctrl.signal, salvar: () => salvar(s),
        aprovar: (e) => new Promise((ok) => {
          s.eventos.push(e);
          emitir(e);
          pendentes.set(s.id + '|' + String(e.id), (r) => {
            s.eventos.push({ t: 'aprovado', id: e.id, ok: r.ok, sempre: !!r.sempre });
            ok(r);
          });
        }),
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      const ev: Evento = { t: 'erro', texto: ctrl.signal.aborted ? 'Parado por voce.' : traduzir(msg) };
      s.eventos.push(ev);
      emitir(ev);
    } finally {
      rodando.delete(s.id);
      salvar(s);
      emitir({ t: 'fim', mudancas: mudancas(s) });
      if (aberto) res.end();
    }
    return;
  }
  json(req, res, 404, { erro: 'rota desconhecida' });
}

function traduzir(msg: string): string {
  if (/ECONNREFUSED|fetch failed/i.test(msg)) return 'O Ollama nao respondeu. Ele esta aberto?';
  if (/not found|pull/i.test(msg)) return 'Esse modelo nao esta instalado. Escolha outro ou baixe na Loja de modelos.';
  return 'Deu erro: ' + msg;
}

const servidor = http.createServer((req, res) => {
  if (!origemOk(req)) { res.writeHead(403, { 'Content-Type': 'application/json' }); res.end('{"erro":"origem recusada"}'); return; }
  if (req.method === 'OPTIONS') { res.writeHead(204, cabecalhos(req)); res.end(); return; }
  if (req.method === 'GET' && IDE.estatico(req.url || '/', res)) return;
  rota(req, res).catch((e) => {
    const msg = e instanceof Error ? e.message : String(e);
    if (!res.headersSent) json(req, res, /ENOENT/.test(msg) ? 404 : 400, { erro: /ENOENT/.test(msg) ? 'conversa nao encontrada' : msg });
    else res.end();
  });
});
servidor.on('error', (e: NodeJS.ErrnoException) => {
  if (e.code === 'EADDRINUSE') { console.error('Nous Code ja esta rodando na porta ' + PORTA); process.exit(0); }
  throw e;
});
IDE.ligarWs(servidor, (o) => !o || ORIGENS.has(o), pastaValida);
servidor.listen(PORTA, '127.0.0.1', () => console.log('Nous Code em http://127.0.0.1:' + PORTA));
