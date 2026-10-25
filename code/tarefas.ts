// Tarefas separadas: o agente trabalha numa COPIA do projeto (uma worktree do
// Git em NousData/code/tarefas/copias/<id>) e o projeto de verdade so' muda
// quando a pessoa revisa e aplica. Para quem usa, e' "uma copia segura"; nada
// de ramo, worktree ou patch na tela.
//   criar     -> copia o projeto como esta agora (inclui o que ainda nao foi commitado)
//   revisar   -> arquivos mudados na copia, com + e -, e o diff inteiro
//   aplicar   -> leva as mudancas para o projeto (sem commitar), ou recusa sem tocar em nada
//   descartar -> apaga a copia
// A copia parte de um commit (o HEAD, ou um commit solto feito por `git stash create`
// quando ha mudancas nao commitadas); as mudancas da tarefa sao sempre
// comparadas com esse ponto de partida, mesmo que a pessoa commite dentro da copia.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

export type Tarefa = {
  id: string; titulo: string; criado: number;
  origem: string;        // a pasta do projeto, como foi aberta
  topo: string;          // a raiz do repositorio Git do projeto
  raiz: string;          // a raiz da copia (worktree)
  pasta: string;         // a pasta do projeto dentro da copia (raiz + o caminho de origem dentro de topo)
  ramo: string;          // ramo da copia (nome interno)
  base: string;          // commit de onde a copia partiu
  estado: 'aberta' | 'aplicada' | 'descartada';
};
export type Arquivo = { arquivo: string; estado: 'novo' | 'mudou' | 'apagado'; mais: number; menos: number };

let DIR = '';
export function configurar(dados: string) {
  DIR = path.join(dados, 'tarefas');
  fs.mkdirSync(path.join(DIR, 'copias'), { recursive: true });
}

const arq = (id: string) => {
  if (!/^[a-z0-9]{6,40}$/.test(id)) throw new Error('tarefa invalida');
  return path.join(DIR, id + '.json');
};
const gravar = (t: Tarefa) => fs.writeFileSync(arq(t.id), JSON.stringify(t, null, 1));
export function ler(id: string): Tarefa {
  try { return JSON.parse(fs.readFileSync(arq(id), 'utf8')) as Tarefa; } catch { throw new Error('essa tarefa nao existe mais'); }
}

type R = { ok: boolean; saida: string; erro: string };
function git(cwd: string, args: string[], entrada?: string, env: Record<string, string> = {}): Promise<R> {
  return new Promise((fim) => {
    const p = spawn('git', ['-c', 'core.quotepath=false', ...args], { cwd, windowsHide: true,
      env: { ...process.env, GIT_TERMINAL_PROMPT: '0', LC_ALL: 'C', ...env } });
    const o: Buffer[] = [], e: Buffer[] = [];
    p.stdout.on('data', (d: Buffer) => o.push(d));
    p.stderr.on('data', (d: Buffer) => e.push(d));
    p.on('close', (c) => fim({ ok: c === 0, saida: Buffer.concat(o).toString('utf8'), erro: Buffer.concat(e).toString('utf8') }));
    p.on('error', (x) => fim({ ok: false, saida: '', erro: String(x) }));
    p.stdin.on('error', () => { /* o git saiu antes de ler tudo */ });
    p.stdin.end(entrada === undefined ? undefined : Buffer.from(entrada, 'utf8'));
  });
}
// Caminho como o disco o conhece: expande nomes curtos do Windows (RUNNER~1), que o
// Git nunca devolve; sem isso path.relative(topo, origem) sai com ..\..\ e a copia erra a pasta.
const real = (p: string) => { try { return fs.realpathSync.native(path.resolve(p)); } catch { return path.resolve(p); } };
const mesmo = (a: string, b: string) => real(a).toLowerCase() === real(b).toLowerCase();

/* ------------------------------------------------------------ criar */
export async function criar(origem: string, titulo: string): Promise<{ tarefa: Tarefa; avisos: string[] }> {
  const t0 = await git(origem, ['rev-parse', '--show-toplevel']);
  if (!t0.ok) throw new Error('Para trabalhar numa cópia separada o projeto precisa estar no Git. Abra o terminal e rode "git init", depois faça o primeiro commit na aba Git.');
  const topo = real(t0.saida.trim());
  const head = await git(topo, ['rev-parse', '--verify', 'HEAD']);
  if (!head.ok) throw new Error('Esse projeto ainda não tem nenhum commit no Git. Faça o primeiro commit (aba Git) para a cópia separada saber de onde partir.');
  const avisos: string[] = [];

  // a copia parte do projeto como esta agora: o HEAD mais o que esta mudado e nao commitado
  let base = head.saida.trim();
  const sujo = await git(topo, ['status', '--porcelain=v1', '--untracked-files=normal']);
  const linhas = sujo.saida.split('\n').filter(Boolean);
  if (linhas.some((l) => !l.startsWith('??'))) {
    let st = await git(topo, ['stash', 'create']);
    if (!st.ok || !st.saida.trim()) {
      st = await git(topo, ['-c', 'user.name=Nous', '-c', 'user.email=nous@localhost', 'stash', 'create']);
    }
    if (st.ok && st.saida.trim()) base = st.saida.trim();
    else avisos.push('Não consegui incluir as mudanças ainda não commitadas; a cópia parte do último commit.');
  }
  if (linhas.some((l) => l.startsWith('??'))) avisos.push('Os arquivos novos que ainda não estão no Git não foram para a cópia.');
  avisos.push('Pastas que o Git ignora (como node_modules) também não vão para a cópia.');

  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  const raiz = path.join(DIR, 'copias', id);
  const ramo = 'nous-tarefa/' + id;
  const w = await git(topo, ['worktree', 'add', '-b', ramo, raiz, base]);
  if (!w.ok) throw new Error('Não consegui criar a cópia separada: ' + (w.erro || w.saida).trim().split('\n').pop());
  const rel = path.relative(topo, real(origem));
  const t: Tarefa = { id, titulo: titulo.trim().slice(0, 80) || 'Tarefa separada', criado: Date.now(), origem: path.resolve(origem), topo, raiz,
    pasta: rel ? path.join(raiz, rel) : raiz, ramo, base, estado: 'aberta' };
  gravar(t);
  return { tarefa: t, avisos };
}

/* ------------------------------------------------------------ consultar */
export function abertas(origem?: string): Tarefa[] {
  const out: Tarefa[] = [];
  if (!DIR || !fs.existsSync(DIR)) return out;
  for (const n of fs.readdirSync(DIR)) {
    if (!n.endsWith('.json')) continue;
    try {
      const t = JSON.parse(fs.readFileSync(path.join(DIR, n), 'utf8')) as Tarefa;
      if (t.estado !== 'aberta' || !fs.existsSync(t.raiz)) continue;
      if (origem && !mesmo(t.origem, origem)) continue;
      out.push(t);
    } catch { /* arquivo quebrado: ignora */ }
  }
  return out.sort((a, b) => b.criado - a.criado);
}

/* A tarefa dona de uma pasta (a pasta da copia ou uma de dentro dela). */
export function dePasta(pasta: string): Tarefa | null {
  const p = real(pasta).toLowerCase();
  return abertas().find((t) => { const r = real(t.raiz).toLowerCase(); return p === r || p.startsWith(r + path.sep); }) || null;
}

/* ------------------------------------------------------------ revisar */
async function preparar(t: Tarefa) {
  if (!fs.existsSync(t.raiz)) throw new Error('a cópia dessa tarefa não existe mais');
  const a = await git(t.raiz, ['add', '-A']);   // so' no indice da copia; o projeto nao e' tocado
  if (!a.ok) throw new Error(a.erro.trim().split('\n').pop() || 'o Git não conseguiu listar as mudanças');
}

export async function revisar(id: string): Promise<{ arquivos: Arquivo[]; diff: string; cortado: boolean }> {
  const t = ler(id);
  await preparar(t);
  const nome = await git(t.raiz, ['diff', '--cached', '--name-status', '--no-renames', t.base]);
  const num = await git(t.raiz, ['diff', '--cached', '--numstat', '--no-renames', t.base]);
  const cont = new Map<string, [number, number]>();
  for (const l of num.saida.split('\n').filter(Boolean)) {
    const [m, n, ...c] = l.split('\t');
    cont.set(c.join('\t'), [Number(m) || 0, Number(n) || 0]);
  }
  const arquivos: Arquivo[] = nome.saida.split('\n').filter(Boolean).map((l) => {
    const [s, ...c] = l.split('\t');
    const arquivo = c.join('\t');
    const [mais, menos] = cont.get(arquivo) || [0, 0];
    return { arquivo, estado: s === 'A' ? 'novo' as const : s === 'D' ? 'apagado' as const : 'mudou' as const, mais, menos };
  });
  const d = await git(t.raiz, ['diff', '--cached', '--no-renames', t.base]);
  const MAX = 300_000;
  return { arquivos, diff: d.saida.slice(0, MAX), cortado: d.saida.length > MAX };
}

/* ------------------------------------------------------------ aplicar e descartar */
export async function aplicar(id: string): Promise<{ ok: boolean; arquivos: Arquivo[]; motivo?: string; conflitos?: string[] }> {
  const t = ler(id);
  if (t.estado !== 'aberta') throw new Error('essa tarefa já foi encerrada');
  const { arquivos } = await revisar(id);
  if (!arquivos.length) { await remover(t, 'aplicada'); return { ok: true, arquivos }; }
  const p = await git(t.raiz, ['diff', '--cached', '--binary', '--no-renames', t.base]);
  if (!p.ok) throw new Error('não consegui montar as mudanças: ' + p.erro.trim().split('\n').pop());
  const ver = await git(t.topo, ['apply', '--check', '--whitespace=nowarn', '-'], p.saida);
  if (!ver.ok) {
    const conflitos = [...new Set([...ver.erro.matchAll(/^error: (?:patch failed: )?([^:\n]+?)(?::\d+)?(?::| already exists| does not exist)/gm)].map((m) => m[1]))];
    return { ok: false, arquivos, conflitos, motivo: 'O projeto mudou nos mesmos trechos desde que a cópia foi feita' +
      (conflitos.length ? ' (' + conflitos.slice(0, 4).join(', ') + (conflitos.length > 4 ? ' e mais ' + (conflitos.length - 4) : '') + ')' : '') +
      '. Nada foi aplicado; seu projeto continua como estava.' };
  }
  const ap = await git(t.topo, ['apply', '--whitespace=nowarn', '-'], p.saida);
  if (!ap.ok) return { ok: false, arquivos, motivo: 'Não consegui aplicar as mudanças: ' + (ap.erro.trim().split('\n').pop() || '') };
  await remover(t, 'aplicada');
  return { ok: true, arquivos };
}

export async function descartar(id: string) {
  const t = ler(id);
  if (t.estado === 'aberta') await remover(t, 'descartada');
  return t;
}

async function remover(t: Tarefa, estado: 'aplicada' | 'descartada') {
  const r = await git(t.topo, ['worktree', 'remove', '--force', t.raiz]);
  if (!r.ok && fs.existsSync(t.raiz)) {
    try { fs.rmSync(t.raiz, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); } catch { /* arquivo em uso: o prune abaixo e a proxima tentativa resolvem */ }
  }
  await git(t.topo, ['worktree', 'prune']);
  await git(t.topo, ['branch', '-D', t.ramo]);
  t.estado = estado;
  gravar(t);
}
