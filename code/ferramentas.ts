// As ferramentas do agente: olhar o projeto, mudar arquivos e rodar comandos.
// Tudo preso na pasta do projeto: caminho que sai dela e' recusado.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

export const IGNORAR = new Set(['.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', 'dist', 'build',
  '.next', '.nuxt', 'target', '.idea', '.vs', '.vscode', 'coverage', '.cache', '.pytest_cache', '.mypy_cache', 'bin', 'obj']);
const MAX_LER = 400;          // linhas por leitura
const MAX_SAIDA_MODELO = 6000; // caracteres de resultado que voltam ao modelo

/* Esquemas no formato do Ollama. Nomes e descricoes em ingles: os modelos de
 * codigo foram treinados assim e erram menos. */
export const ESQUEMAS = [
  ferr('list_files', 'List the files and folders of the project as a tree. Start here to understand the project.', {
    path: ['string', 'Folder relative to the project root. Default: "."'],
    depth: ['integer', 'How many levels to show (1-4). Default: 2'],
  }, []),
  ferr('read_file', 'Read a text file. Returns the lines with their numbers ("12| code"). The numbers are NOT part of the file.', {
    path: ['string', 'File path relative to the project root'],
    start_line: ['integer', 'First line to read (default 1)'],
    end_line: ['integer', 'Last line to read (default: start_line + 399)'],
  }, ['path']),
  ferr('search', 'Search a text or regular expression in the project files. Returns "file:line: text" for each match.', {
    pattern: ['string', 'Text or regular expression to find'],
    path: ['string', 'Folder or file to search in. Default: "."'],
  }, ['pattern']),
  ferr('edit_file', 'Change a file by replacing an exact piece of its text. Copy old_text exactly as it is in the file (without the line numbers of read_file). old_text must appear only once; include more lines around it if needed.', {
    path: ['string', 'File path relative to the project root'],
    old_text: ['string', 'The exact current text to replace'],
    new_text: ['string', 'The new text'],
  }, ['path', 'old_text', 'new_text']),
  ferr('write_file', 'Create a new file, or replace a whole file, with the given content.', {
    path: ['string', 'File path relative to the project root'],
    content: ['string', 'The complete content of the file'],
  }, ['path', 'content']),
  ferr('run_command', 'Run a PowerShell command in the project folder (Windows). Use it to run tests, builds, git status, etc. The user approves each command.', {
    command: ['string', 'The PowerShell command'],
    timeout_s: ['integer', 'Seconds before giving up (default 120, max 600)'],
  }, ['command']),
];
export const NOMES = new Set(ESQUEMAS.map((e) => e.function.name));

function ferr(name: string, description: string, props: Record<string, [string, string]>, required: string[]) {
  const properties: Record<string, object> = {};
  for (const [k, [type, desc]] of Object.entries(props)) properties[k] = { type, description: desc };
  return { type: 'function', function: { name, description, parameters: { type: 'object', properties, required } } };
}

/* ------------------------------------------------------------ caminhos */
export function resolver(raiz: string, p: unknown): string {
  let rel = String(p ?? '.').trim().replace(/^["']|["']$/g, '') || '.';
  if (path.isAbsolute(rel) && !/^[\\/]/.test(rel)) {
    // absoluto do Windows (C:\...): so' vale se estiver dentro do projeto
  } else {
    rel = rel.replace(/^[\\/]+/, '');
  }
  const abs = path.resolve(raiz, rel);
  const r = path.relative(raiz, abs);
  if (r.startsWith('..') || path.isAbsolute(r)) throw new Error('caminho fora do projeto: ' + String(p));
  return abs;
}
export function relativo(raiz: string, abs: string): string {
  return path.relative(raiz, abs).split(path.sep).join('/') || '.';
}

function textoDe(abs: string): string {
  const st = fs.statSync(abs);
  if (st.isDirectory()) throw new Error('isso e' + "'" + ' uma pasta, nao um arquivo');
  if (st.size > 2_000_000) throw new Error('arquivo grande demais (' + Math.round(st.size / 1e6) + ' MB)');
  const buf = fs.readFileSync(abs);
  if (buf.subarray(0, 8000).includes(0)) throw new Error('arquivo binario, nao da para ler como texto');
  return buf.toString('utf8');
}

/* ------------------------------------------------------------ leitura */
export function listar(raiz: string, a: Record<string, unknown>): string {
  const base = resolver(raiz, a.path);
  const prof = Math.max(1, Math.min(4, Number(a.depth) || 2));
  const linhas: string[] = [];
  let total = 0;
  function andar(dir: string, nivel: number, recuo: string) {
    let itens: fs.Dirent[];
    try { itens = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    itens.sort((x, y) => (Number(y.isDirectory()) - Number(x.isDirectory())) || x.name.localeCompare(y.name));
    for (const it of itens) {
      if (total >= 300) return;
      if (it.isDirectory() && IGNORAR.has(it.name)) continue;
      total++;
      linhas.push(recuo + it.name + (it.isDirectory() ? '/' : ''));
      if (it.isDirectory() && nivel < prof) andar(path.join(dir, it.name), nivel + 1, recuo + '  ');
    }
  }
  andar(base, 1, '');
  if (total >= 300) linhas.push('... (lista cortada em 300 itens; use path para olhar uma pasta)');
  return (relativo(raiz, base) + '/\n' + linhas.join('\n')).trim();
}

export function ler(raiz: string, a: Record<string, unknown>): string {
  const abs = resolver(raiz, a.path);
  const linhas = textoDe(abs).split(/\r?\n/);
  const ini = Math.max(1, Number(a.start_line) || 1);
  const fim = Math.min(linhas.length, Number(a.end_line) || ini + MAX_LER - 1, ini + MAX_LER - 1);
  const larg = String(fim).length;
  const corpo = linhas.slice(ini - 1, fim).map((l, i) => String(ini + i).padStart(larg) + '| ' + l).join('\n');
  const aviso = fim < linhas.length ? `\n... (mostrando ${ini}-${fim} de ${linhas.length} linhas; peca start_line=${fim + 1} para continuar)` : '';
  return corpo + aviso;
}

export function buscar(raiz: string, a: Record<string, unknown>): string {
  const base = resolver(raiz, a.path);
  const pad = String(a.pattern || '');
  if (!pad) throw new Error('pattern vazio');
  let re: RegExp;
  try { re = new RegExp(pad, 'i'); } catch { re = new RegExp(pad.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'); }
  const achados: string[] = [];
  function olhar(abs: string) {
    if (achados.length >= 80) return;
    let st: fs.Stats;
    try { st = fs.statSync(abs); } catch { return; }
    if (st.isDirectory()) {
      if (IGNORAR.has(path.basename(abs)) && abs !== base) return;
      for (const n of fs.readdirSync(abs)) olhar(path.join(abs, n));
      return;
    }
    if (st.size > 1_000_000) return;
    let t: string;
    try { t = textoDe(abs); } catch { return; }
    const ls = t.split(/\r?\n/);
    for (let i = 0; i < ls.length && achados.length < 80; i++) {
      if (re.test(ls[i])) achados.push(relativo(raiz, abs) + ':' + (i + 1) + ': ' + ls[i].trim().slice(0, 200));
    }
  }
  olhar(base);
  if (!achados.length) return 'Nada encontrado para: ' + pad;
  return achados.join('\n') + (achados.length >= 80 ? '\n... (parei em 80 resultados; refine a busca)' : '');
}

/* ------------------------------------------------------------ mudancas */
/* Calcula o arquivo novo de um edit_file sem gravar (para mostrar o diff antes). */
export function aplicarEdicao(atual: string, velho: string, novo: string): string {
  if (!velho) throw new Error('old_text vazio');
  const crlf = atual.includes('\r\n');
  const txt = crlf ? atual.replace(/\r\n/g, '\n') : atual;
  let v = velho.replace(/\r\n/g, '\n');
  let n = novo.replace(/\r\n/g, '\n');
  let quantas = txt.split(v).length - 1;
  if (quantas === 0) {
    // o modelo copiou com os numeros do read_file ("12| ")?
    const semNum = (s: string) => s.replace(/^\s*\d+\| ?/gm, '');
    if (/^\s*\d+\| /m.test(v)) { v = semNum(v); n = semNum(n); quantas = txt.split(v).length - 1; }
  }
  if (quantas === 0) {
    // mesma sequencia de linhas, so' o recuo/espacos diferentes
    const alvo = v.split('\n').map((l) => l.trim());
    const ls = txt.split('\n');
    const achou: number[] = [];
    for (let i = 0; i + alvo.length <= ls.length; i++) {
      if (alvo.every((l, k) => ls[i + k].trim() === l)) achou.push(i);
    }
    if (achou.length === 1) {
      const i = achou[0];
      const recuo = (ls[i].match(/^\s*/) || [''])[0];
      const recuoModelo = (v.split('\n')[0].match(/^\s*/) || [''])[0];
      const novas = n.split('\n').map((l) => (l.startsWith(recuoModelo) ? recuo + l.slice(recuoModelo.length) : l));
      const res = ls.slice(0, i).concat(novas, ls.slice(i + alvo.length)).join('\n');
      return crlf ? res.replace(/\n/g, '\r\n') : res;
    }
    throw new Error(achou.length > 1
      ? 'old_text aparece mais de uma vez; inclua mais linhas em volta para ficar unico'
      : 'old_text nao foi encontrado no arquivo. Leia o arquivo de novo (read_file) e copie o trecho exatamente');
  }
  if (quantas > 1) throw new Error('old_text aparece ' + quantas + ' vezes; inclua mais linhas em volta para ficar unico');
  const res = txt.replace(v, () => n);
  return crlf ? res.replace(/\n/g, '\r\n') : res;
}

/* Diff de linhas (LCS depois de tirar o comeco e o fim iguais), com 3 linhas de
 * contexto. Formato: "@@ -a +b @@", " igual", "-saiu", "+entrou". */
export function diff(antes: string, depois: string): { texto: string; mais: number; menos: number } {
  const a = antes ? antes.replace(/\r\n/g, '\n').split('\n') : [];
  const b = depois.replace(/\r\n/g, '\n').split('\n');
  let ini = 0;
  while (ini < a.length && ini < b.length && a[ini] === b[ini]) ini++;
  let fa = a.length, fb = b.length;
  while (fa > ini && fb > ini && a[fa - 1] === b[fb - 1]) { fa--; fb--; }
  const ma = a.slice(ini, fa), mb = b.slice(ini, fb);
  const ops: [string, string][] = [];
  if (ma.length * mb.length > 4_000_000) {
    ma.forEach((l) => ops.push(['-', l])); mb.forEach((l) => ops.push(['+', l]));
  } else {
    const L = Array.from({ length: ma.length + 1 }, () => new Uint32Array(mb.length + 1));
    for (let i = ma.length - 1; i >= 0; i--) for (let j = mb.length - 1; j >= 0; j--) {
      L[i][j] = ma[i] === mb[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    }
    let i = 0, j = 0;
    while (i < ma.length || j < mb.length) {
      if (i < ma.length && j < mb.length && ma[i] === mb[j]) { ops.push([' ', ma[i]]); i++; j++; }
      else if (i < ma.length && (j >= mb.length || L[i + 1][j] >= L[i][j + 1])) { ops.push(['-', ma[i]]); i++; }  // o que sai vem antes
      else { ops.push(['+', mb[j]]); j++; }
    }
  }
  const antesCtx = a.slice(Math.max(0, ini - 3), ini).map((l) => ' ' + l);
  const depoisCtx = a.slice(fa, fa + 3).map((l) => ' ' + l);
  const corpo = ops.map(([s, l]) => s + l);
  const mais = ops.filter((o) => o[0] === '+').length, menos = ops.filter((o) => o[0] === '-').length;
  const cab = `@@ -${Math.max(1, ini - 2)} +${Math.max(1, ini - 2)} @@`;
  let texto = [cab].concat(antesCtx, corpo, depoisCtx).join('\n');
  if (texto.length > 30000) texto = texto.slice(0, 30000) + '\n... (diff cortado)';
  return { texto, mais, menos };
}

/* ------------------------------------------------------------ comandos */
export function rodar(raiz: string, comando: string, segundos: number, sinal: AbortSignal):
  Promise<{ codigo: number | null; saida: string; tempo: number }> {
  return new Promise((ok) => {
    const t0 = Date.now();
    const ps = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command',
      '[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference="SilentlyContinue"; ' + comando],
    { cwd: raiz, windowsHide: true, env: { ...process.env, NO_COLOR: '1', FORCE_COLOR: '0' } });
    let saida = '';
    const junta = (d: Buffer) => { if (saida.length < 200_000) saida += d.toString('utf8'); };
    ps.stdout.on('data', junta);
    ps.stderr.on('data', junta);
    const matar = () => { try { spawn('taskkill', ['/T', '/F', '/PID', String(ps.pid)], { windowsHide: true }); } catch { /* ja saiu */ } };
    const relogio = setTimeout(() => { saida += '\n[parado: passou de ' + segundos + 's]'; matar(); }, segundos * 1000);
    sinal.addEventListener('abort', matar, { once: true });
    ps.on('close', (codigo) => {
      clearTimeout(relogio);
      ok({ codigo, saida: saida.replace(/\x1b\[[0-9;]*m/g, ''), tempo: Date.now() - t0 });
    });
    ps.on('error', (e) => { clearTimeout(relogio); ok({ codigo: -1, saida: String(e), tempo: Date.now() - t0 }); });
  });
}

/* Corta o texto que volta ao modelo (o contexto de um modelo local e' pequeno). */
export function paraModelo(t: string): string {
  if (t.length <= MAX_SAIDA_MODELO) return t;
  const meio = MAX_SAIDA_MODELO / 2;
  return t.slice(0, meio) + `\n... (${t.length - MAX_SAIDA_MODELO} caracteres omitidos) ...\n` + t.slice(-meio);
}

/* Le o arquivo atual (ou '' se ainda nao existe) para snapshot/diff. */
export function conteudoAtual(abs: string): string | null {
  try { return fs.readFileSync(abs, 'utf8'); } catch { return null; }
}
export function gravar(abs: string, conteudo: string) {
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, conteudo, 'utf8');
}
