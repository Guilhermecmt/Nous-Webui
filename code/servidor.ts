// Nous Code: o servico do painel Codigo (http://127.0.0.1:8998).
// Sem dependencias: so' o Node (>= 22.18, que roda TypeScript direto).
//
//   GET  /health                      {ok, versao, lsp}
//   GET  /modelos                     modelos do Ollama (e de LM Studio/llama.cpp/vLLM) que servem para o agente
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
//   GET  /mcp?pasta=                  servidores MCP do projeto (e se ja' foram permitidos)
//   POST /mcp/aprovar {pasta, nome, sim}
//   POST /lembretes/apagar {id, lembrete}
//
// Lembretes (schedule_create do agente) vencidos rodam a conversa sozinhos:
// sem ninguem para aprovar, o que pede aprovacao e' recusado (como no dsh).
// IDE (a janela propria do Nous Code, servida aqui mesmo):
//   GET  /                            a pagina do IDE (?pasta= abre direto um projeto)
//   GET  /fs/arvore?raiz=&dir=        um nivel da arvore de arquivos
//   GET  /fs/ler?raiz=&caminho=       conteudo de um arquivo
//   POST /fs/salvar|/fs/novo|/fs/renomear|/fs/apagar   (apagar vai para a Lixeira)
//   POST /fs/abrir-sistema            abre um arquivo no programa padrao do Windows
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
import { modelos, NUM_CTX } from './modelo.ts';
import { turno, desfazer, mudancas, normalizar, aoCarregar, compactar, exportar, novoObjetivo,
  type Sessao, type Evento, type Resposta, type Ctx } from './agente.ts';
import * as F from './ferramentas.ts';
import * as J from './jobs.ts';
import * as L from './lsp.ts';
import * as M from './mcp.ts';
import * as R from './lembretes.ts';
import { skills } from './contexto.ts';
import * as IDE from './ide.ts';

const PORTA = Number(process.env.NOUS_CODE_PORT || 8998);
const VERSAO = '0.3.0';
const DADOS = path.join(process.env.DATA_DIR || path.join(os.homedir(), 'NousData'), 'code');
const DIR_SESSOES = path.join(DADOS, 'sessoes');
const ARQ_PASTAS = path.join(DADOS, 'pastas.json');
const ORIGENS = new Set(['http://localhost:8080', 'http://127.0.0.1:8080',
  'http://localhost:' + PORTA, 'http://127.0.0.1:' + PORTA]);  // o Nous e a janela do IDE
const MODELO_PADRAO = process.env.NOUS_CODE_MODEL || 'qwen2.5-coder:14b';
fs.mkdirSync(DIR_SESSOES, { recursive: true });
// Com o Node portatil do Nous (fora do PATH do sistema), os comandos do agente
// e o terminal tambem precisam achar `node` e `npm`: so' neste processo e nos filhos.
{
  const nodeDir = path.dirname(process.execPath);
  const chave = Object.keys(process.env).find((k) => k.toLowerCase() === 'path') || 'PATH';
  const dirs = (process.env[chave] || '').split(path.delimiter);
  if (!dirs.some((d) => d && path.resolve(d).toLowerCase() === nodeDir.toLowerCase())) {
    process.env[chave] = nodeDir + path.delimiter + (process.env[chave] || '');
  }
}
J.configurar(path.join(DADOS, 'jobs'));
F.configurar(path.join(DADOS, 'saidas'), [path.join(DADOS, 'jobs')]);
M.configurar(DADOS);
R.configurar(DADOS);

/* ------------------------------------------------------------ sessoes */
const abertas = new Map<string, Sessao>();
const rodando = new Map<string, AbortController>();
const pendentes = new Map<string, (r: Resposta) => void>();  // "sessao|pedido"
const filaLembretes = new Map<string, string[]>();  // lembretes que venceram com a conversa ocupada

function arqSessao(id: string) {
  if (!/^[a-z0-9]{6,40}$/.test(id)) throw new Error('id invalido');
  return path.join(DIR_SESSOES, id + '.json');
}
function carregar(id: string): Sessao {
  const s = abertas.get(id) || aoCarregar(normalizar(JSON.parse(fs.readFileSync(arqSessao(id), 'utf8'))));
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

  if (r === 'GET /health') return json(req, res, 200, { ok: true, versao: VERSAO, modelo: MODELO_PADRAO, lsp: L.disponiveis() });

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
      case 'POST /fs/abrir-sistema': IDE.abrirNoSistema(raiz, String(b.caminho)); return json(req, res, 200, { ok: true });
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
    const s: Sessao = normalizar({ id: novoId(), pasta, modelo: String(b.modelo || MODELO_PADRAO) });
    abertas.set(s.id, s); salvar(s); lembrarPasta(pasta);
    return json(req, res, 200, { id: s.id });
  }
  if (r === 'GET /sessao') {
    const s = carregar(q('id'));
    return json(req, res, 200, { id: s.id, titulo: s.titulo, pasta: s.pasta, modelo: s.modelo, modo: s.modo,
      eventos: s.eventos, mudancas: mudancas(s), rodando: rodando.has(s.id), planejando: s.planejando, tarefas: s.tarefas,
      objetivo: s.objetivo, raciocinio: s.raciocinio, internet: s.internet, tokens: s.tokens, limite: NUM_CTX,
      jobs: J.listar(s.id).map((j) => ({ id: j.id, comando: j.comando, descricao: j.descricao, rodando: !j.fim, codigo: j.codigo })),
      lembretes: R.listar(s.id) });
  }
  if (r === 'GET /sessao/contexto') {
    const s = carregar(q('id'));
    return json(req, res, 200, { sistema: s.sistema || '(o prompt de sistema e\' criado no primeiro pedido)', tokens: s.tokens, limite: NUM_CTX,
      mensagens: s.mensagens.slice(1).map((m) => ({ role: m.role, ferramenta: m.tool_name, content: m.content.length > 4000 ? m.content.slice(0, 4000) + '\n[...]' : m.content })) });
  }
  if (r === 'GET /sessao/exportar') {
    const s = carregar(q('id'));
    const nome = (s.titulo.replace(/[^\w\- ]+/g, '').trim() || 'conversa').slice(0, 50) + '.md';
    res.writeHead(200, cabecalhos(req, { 'Content-Type': 'text/markdown; charset=utf-8', 'Content-Disposition': 'attachment; filename="' + nome + '"' }));
    res.end(exportar(s));
    return;
  }
  if (r === 'POST /sessao/renomear') {
    const b = await corpo(req);
    const s = carregar(String(b.id));
    const t = String(b.titulo || '').trim().slice(0, 80);
    if (!t) return json(req, res, 400, { erro: 'titulo vazio' });
    s.titulo = t; s.tituloAuto = false; salvar(s);
    return json(req, res, 200, { ok: true });
  }
  if (r === 'POST /sessao/duplicar') {
    // copia a conversa (ou ate' antes do pedido escolhido) para seguir por outro caminho
    const b = await corpo(req);
    const s = carregar(String(b.id));
    let msgs = s.mensagens, evs = s.eventos;
    if (b.ate !== undefined) {
      const i = Number(b.ate);
      const e = s.eventos[i];
      if (!e || e.t !== 'voce' || typeof e.msg !== 'number') return json(req, res, 400, { erro: 'escolha um pedido seu para duplicar a partir dele' });
      msgs = s.mensagens.slice(0, e.msg); evs = s.eventos.slice(0, i);
    }
    const n = normalizar({ ...JSON.parse(JSON.stringify(s)), id: novoId(), titulo: s.titulo + ' (cópia)', criado: Date.now(),
      mensagens: JSON.parse(JSON.stringify(msgs)), eventos: JSON.parse(JSON.stringify(evs)), originais: {}, lidos: {} });
    abertas.set(n.id, n); salvar(n);
    return json(req, res, 200, { id: n.id });
  }
  if (r === 'GET /sessoes/buscar') {
    const termo = q('q').toLowerCase();
    const out = [];
    for (const it of listarSessoes(q('pasta') || undefined)) {
      const s = carregar(it.id);
      const txt = s.eventos.filter((e) => e.t === 'voce' || e.t === 'resposta').map((e) => String(e.texto)).join('\n');
      const k = txt.toLowerCase().indexOf(termo);
      if (s.titulo.toLowerCase().includes(termo) || k >= 0) out.push({ ...it, trecho: k >= 0 ? txt.slice(Math.max(0, k - 60), k + 100) : '' });
    }
    return json(req, res, 200, out.slice(0, 40));
  }
  if (r === 'GET /skills') {
    const pasta = pastaValida(q('pasta'));
    return json(req, res, 200, skills(pasta).map((x) => ({ nome: x.nome, descricao: x.descricao, usuario: x.usuario })));
  }
  if (r === 'GET /mcp') {
    const pasta = pastaValida(q('pasta'));
    return json(req, res, 200, M.servidores(pasta).map((x) => ({ nome: x.nome, origem: x.origem, arquivo: x.arquivo, aprovado: x.aprovado,
      comando: x.spec.url || [x.spec.command, ...(x.spec.args || [])].join(' ') })));
  }
  if (r === 'POST /mcp/aprovar') {
    const b = await corpo(req);
    M.aprovar(pastaValida(String(b.pasta)), String(b.nome), b.sim !== false);
    return json(req, res, 200, { ok: true });
  }
  if (r === 'POST /lembretes/apagar') {
    const b = await corpo(req);
    return json(req, res, 200, R.apagar(String(b.id), String(b.lembrete)));
  }
  if (r === 'POST /jobs/parar') {
    const b = await corpo(req);
    const j = J.pegar(String(b.id), String(b.job));
    J.matar(j);
    return json(req, res, 200, { ok: true });
  }
  if (r === 'POST /compactar') {
    const b = await corpo(req);
    const s = carregar(String(b.id));
    if (rodando.has(s.id)) return json(req, res, 409, { erro: 'espere o agente terminar' });
    if (s.mensagens.length < 4) return json(req, res, 200, { evento: null });
    const ctrl = new AbortController();
    const e = await compactar(s, { emitir: () => {}, aprovar: async () => ({ ok: false, semCanal: true }), sinal: ctrl.signal, salvar: () => salvar(s) }, true);
    if (e) s.eventos.push(e);
    salvar(s);
    return json(req, res, 200, { evento: e });
  }
  if (r === 'POST /sessao/ajustes') {
    const b = await corpo(req);
    const s = carregar(String(b.id));
    // modo, plano e internet chegam ao modelo no proximo pedido, pelo "runtime context"
    if (b.modelo) s.modelo = String(b.modelo);
    if (['leitura', 'perguntar', 'editar', 'total'].includes(String(b.modo))) s.modo = b.modo as Sessao['modo'];
    if (typeof b.planejando === 'boolean') s.planejando = b.planejando;
    if (['auto', 'desligado', 'baixo', 'medio', 'alto'].includes(String(b.raciocinio))) s.raciocinio = b.raciocinio as Sessao['raciocinio'];
    if (b.internet === null || typeof b.internet === 'boolean') s.internet = b.internet as boolean | null;
    if (b.objetivo !== undefined) {
      // a pessoa cria, troca ou tira o objetivo; o modelo le com get_goal
      const t = String(b.objetivo || '').trim();
      s.objetivo = t ? novoObjetivo(t, Number(b.rodadas) > 0 ? Number(b.rodadas) : undefined) : null;
    }
    if (s.objetivo && (b.objetivoAcao === 'pausar' || b.objetivoAcao === 'retomar')) {
      const o = s.objetivo;
      if (b.objetivoAcao === 'pausar' && o.phase === 'active') { o.phase = 'paused'; o.armado = false; o.revision++; }
      if (b.objetivoAcao === 'retomar' && o.phase !== 'complete') {
        if (o.roundsStarted >= o.maxGoalRounds) o.maxGoalRounds = o.roundsStarted + 10;
        o.phase = 'active'; o.armado = true; delete o.blockedReason; o.revision++;
      }
    }
    salvar(s);
    return json(req, res, 200, { ok: true, modelo: s.modelo, modo: s.modo, planejando: s.planejando, raciocinio: s.raciocinio,
      internet: s.internet, objetivo: s.objetivo });
  }
  if (r === 'POST /sessao/apagar') {
    const b = await corpo(req);
    const id = String(b.id);
    if (rodando.has(id)) return json(req, res, 409, { erro: 'a conversa ainda esta rodando' });
    J.encerrarSessao(id);
    R.apagarDaSessao(id);
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
    f({ ok: !!b.ok, sempre: !!b.sempre, texto: b.texto === undefined ? undefined : String(b.texto).slice(0, 4000) });
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
    res.writeHead(200, cabecalhos(req, { 'Content-Type': 'application/x-ndjson; charset=utf-8' }));
    let aberto = true;
    res.on('close', () => { aberto = false; });  // o painel fechou: o agente segue e salva
    const emitir = (e: Evento) => { if (aberto) res.write(JSON.stringify(e) + '\n'); };
    await rodarTurno(s, texto, 'humano', emitir, (e) => new Promise((ok) => {
      s.eventos.push(e);
      emitir(e);
      pendentes.set(s.id + '|' + String(e.id), (r) => {
        s.eventos.push({ t: 'aprovado', id: e.id, ok: r.ok, sempre: !!r.sempre, texto: r.texto });
        ok(r);
      });
    }));
    if (aberto) res.end();
    return;
  }
  json(req, res, 404, { erro: 'rota desconhecida' });
}

/* Um turno do agente (pedido da pessoa ou lembrete). Lembrete que venceu
 * enquanto a conversa trabalhava roda logo depois. */
async function rodarTurno(s: Sessao, texto: string, origem: 'humano' | 'lembrete', emitir: (e: Evento) => void, aprovar: Ctx['aprovar']) {
  const ctrl = new AbortController();
  rodando.set(s.id, ctrl);
  IDE.avisarTodos({ t: 'sessao-rodando', id: s.id, rodando: true });
  try {
    await turno(s, texto, { emitir, sinal: ctrl.signal, salvar: () => salvar(s), aprovar }, origem);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    const ev: Evento = { t: 'erro', texto: ctrl.signal.aborted ? 'Parado por você.' : traduzir(msg) };
    s.eventos.push(ev);
    emitir(ev);
  } finally {
    rodando.delete(s.id);
    salvar(s);
    emitir({ t: 'fim', mudancas: mudancas(s) });
    IDE.avisarTodos({ t: 'sessao-rodando', id: s.id, rodando: false });
  }
  const fila = filaLembretes.get(s.id);
  if (fila && fila.length) {
    filaLembretes.delete(s.id);
    setTimeout(() => lembreteEmFundo(s.id, fila.join('\n\n')), 500);
  }
}

/* Lembrete vencido: roda a conversa sem ninguem na tela. O que pede
 * aprovacao e' recusado; a janela aberta recarrega a conversa no fim. */
async function lembreteEmFundo(id: string, texto: string) {
  let s: Sessao;
  try { s = carregar(id); } catch { return; }
  if (rodando.has(id)) { filaLembretes.set(id, (filaLembretes.get(id) || []).concat(texto)); return; }
  await rodarTurno(s, texto, 'lembrete', (e) => { if (e.t === 'resposta' || e.t === 'erro') IDE.avisarTodos({ t: 'sessao-mudou', id }); },
    async () => ({ ok: false, semCanal: true }));
  IDE.avisarTodos({ t: 'sessao-mudou', id, titulo: s.titulo });
}

setInterval(() => {
  for (const v of R.vencidos()) {
    IDE.avisarTodos({ t: 'lembrete', id: v.sessao, titulos: v.titulos });
    lembreteEmFundo(v.sessao, v.texto);
  }
}, 15_000).unref();

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
// language servers e servidores MCP sao processos filhos: saem junto
for (const sinal of ['SIGINT', 'SIGTERM', 'SIGBREAK'] as const) process.on(sinal, () => process.exit(0));
process.on('exit', () => { L.encerrarTodos(); M.fecharTodos(); });
