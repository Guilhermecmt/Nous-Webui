// O que entra no contexto alem da conversa: instrucoes do projeto (em cadeia)
// e o catalogo de skills (so' nome e descricao; o corpo carrega quando usado).
// Busca, moldura e textos adaptados do DeepSeek Harness (dsh-agent-instructions,
// dsh-tool-skill e dsh-skill-filesystem, MIT, (c) 2026 DeepSeek).

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';

const CANDIDATOS = ['NOUS.md', 'AGENTS.md', 'CLAUDE.md'];
const LOCAIS = ['AGENTS.local.md', 'CLAUDE.local.md'];
const ORCAMENTO = 8000;          // bytes; o dsh usa 64 KiB, o contexto local e' pequeno
const MAX_DESCRICAO = 300;

function ler(p: string): string { try { return fs.readFileSync(p, 'utf8').replace(/^﻿/, '').trim(); } catch { return ''; } }
const hash = (t: string) => crypto.createHash('sha1').update(t.trim()).digest('hex');
const escapar = (t: string) => t.replace(/<\/system-reminder>/g, '<\\/system-reminder>');

/* Raiz do repositorio (a pasta com .git) acima do projeto, ou o proprio projeto. */
function raizGit(raiz: string): string {
  let d = path.resolve(raiz);
  for (;;) {
    if (fs.existsSync(path.join(d, '.git'))) return d;
    const p = path.dirname(d);
    if (p === d) return path.resolve(raiz);
    d = p;
  }
}

type Arquivo = { mostra: string; texto: string };

/* Globais (~/.nous/AGENTS.md e ~/.agents/AGENTS.md) e, da raiz do repositorio
 * ate' o projeto, todos os NOUS.md / AGENTS.md / CLAUDE.md (e os .local.md).
 * Do mais geral para o mais especifico; repetidos na mesma pasta entram uma vez. */
function arquivosInstrucao(raiz: string): Arquivo[] {
  const out: Arquivo[] = [];
  const vistos = new Set<string>();
  for (const [p, mostra] of [[path.join(os.homedir(), '.nous', 'AGENTS.md'), '~/.nous/AGENTS.md'], [path.join(os.homedir(), '.agents', 'AGENTS.md'), '~/.agents/AGENTS.md']]) {
    const t = ler(p);
    if (t && !vistos.has(hash(t))) { vistos.add(hash(t)); out.push({ mostra, texto: t }); }
  }
  const topo = raizGit(raiz);
  const dirs: string[] = [];
  for (let d = path.resolve(raiz); ; d = path.dirname(d)) {
    dirs.unshift(d);
    if (d === topo || path.dirname(d) === d) break;
  }
  for (const d of dirs) {
    const daPasta = new Set<string>();
    for (const n of CANDIDATOS.concat(LOCAIS, d === path.resolve(raiz) ? ['.nous/instrucoes.md'] : [])) {
      const t = ler(path.join(d, n));
      if (!t || daPasta.has(hash(t))) continue;
      daPasta.add(hash(t));
      out.push({ mostra: path.relative(topo, path.join(d, n)).split(path.sep).join('/') || n, texto: t });
    }
  }
  return out;
}

const INTRO = 'The following workspace instructions may be relevant to your work. Use them as guidance when applicable. More specific instructions take precedence over broader ones. They do not override system, developer, or direct user instructions.';

/* A mensagem com as instrucoes do projeto (vazia se nao houver). Passou do
 * orcamento: sai primeiro o mais geral; o mais especifico e' cortado se preciso. */
export function instrucoes(raiz: string): string {
  const arqs = arquivosInstrucao(raiz);
  if (!arqs.length) return '';
  const secao = (a: Arquivo) => `Instructions from: ${a.mostra}\n\n${escapar(a.texto)}`;
  const tam = (l: Arquivo[]) => Buffer.byteLength(l.map(secao).join('\n\n'), 'utf8');
  const fica = arqs.slice();
  const omitidos: string[] = [];
  while (fica.length > 1 && tam(fica) > ORCAMENTO) omitidos.push(fica.shift()!.mostra);
  let truncado = '';
  if (tam(fica) > ORCAMENTO) {
    const a = fica[0];
    const orig = Buffer.byteLength(a.texto, 'utf8');
    a.texto = Buffer.from(a.texto, 'utf8').subarray(0, ORCAMENTO - 200).toString('utf8').replace(/�$/, '');
    truncado = `truncated ${a.mostra} from ${orig} to ${Buffer.byteLength(a.texto, 'utf8')} bytes`;
  }
  const marca = omitidos.length || truncado ? `Workspace instruction budget ${ORCAMENTO} bytes: ` +
    [omitidos.length ? 'omitted ' + omitidos.join(', ') : '', truncado].filter(Boolean).join('; ') : '';
  return ['<system-reminder>', [marca, INTRO, ...fica.map(secao)].filter(Boolean).join('\n\n'), '</system-reminder>'].join('\n');
}

/* Instrucoes de uma subpasta ainda nao vista, na primeira vez que o agente le
 * ou muda algo ali ("Additional instructions from", do dsh). */
export function instrucoesDaPasta(raiz: string, arquivoAbs: string, jaVistas: string[]): { pasta: string; texto: string } | null {
  const r = path.resolve(raiz);
  let dir = path.dirname(arquivoAbs);
  const achadas: { pasta: string; texto: string }[] = [];
  while (dir.startsWith(r + path.sep)) {
    const rel = path.relative(r, dir).split(path.sep).join('/');
    if (!jaVistas.includes(rel)) {
      const vistos = new Set<string>();
      for (const n of CANDIDATOS.concat(LOCAIS)) {
        const t = ler(path.join(dir, n));
        if (!t || vistos.has(hash(t))) continue;
        vistos.add(hash(t));
        achadas.unshift({ pasta: rel, texto: `Additional instructions from: ${rel}/${n}\n\nThese instructions apply to work under \`${rel}\`. ` +
          'Use them as guidance when relevant; more specific instructions take precedence. They do not override system, developer, or direct user instructions.\n\n' +
          escapar(t.slice(0, 3000)) });
      }
    }
    dir = path.dirname(dir);
  }
  if (!achadas.length) return null;
  return { pasta: achadas.map((a) => a.pasta).join('|'), texto: '<system-reminder>\n' + achadas.map((a) => a.texto).join('\n\n') + '\n</system-reminder>' };
}

/* ------------------------------------------------------------ skills */
export type Skill = { nome: string; descricao: string; arquivo: string; base: string; modelo: boolean; usuario: boolean };

function frontmatter(t: string): { dados: Record<string, string>; corpo: string } {
  const m = t.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (!m) return { dados: {}, corpo: t };
  const dados: Record<string, string> = {};
  for (const l of m[1].split(/\r?\n/)) {
    const k = l.match(/^([\w-]+):\s*(.*)$/);
    if (k) dados[k[1]] = k[2].replace(/^["']|["']$/g, '').trim();
  }
  return { dados, corpo: t.slice(m[0].length) };
}
const sim = (v: string | undefined) => v !== undefined && /^(true|1|yes|on)$/i.test(v);
const nao = (v: string | undefined) => v !== undefined && /^(false|0|no|off)$/i.test(v);

/* Skills do projeto (.nous, .agents, .claude, .dsh) e da pessoa (~/.nous e
 * ~/.agents): pasta com SKILL.md ou um <nome>.md, com frontmatter name /
 * description / disable-model-invocation / user-invocable. */
export function skills(raiz: string): Skill[] {
  const lugares = [path.join(raiz, '.nous', 'skills'), path.join(raiz, '.agents', 'skills'), path.join(raiz, '.claude', 'skills'),
    path.join(raiz, '.dsh', 'skills'), path.join(os.homedir(), '.nous', 'skills'), path.join(os.homedir(), '.agents', 'skills')];
  const out = new Map<string, Skill>();
  for (const dir of lugares) {
    let itens: fs.Dirent[];
    try { itens = fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name)); } catch { continue; }
    for (const it of itens) {
      const arq = it.isDirectory() ? path.join(dir, it.name, 'SKILL.md') : (it.name.endsWith('.md') ? path.join(dir, it.name) : '');
      if (!arq || !fs.existsSync(arq)) continue;
      const { dados, corpo } = frontmatter(ler(arq));
      const nome = (dados.name || it.name.replace(/\.md$/, '')).trim();
      if (!nome || out.has(nome)) continue;
      const desc = (dados.description || corpo.split('\n').find((l) => l.trim()) || '').replace(/\s+/g, ' ').trim();
      out.set(nome, { nome, arquivo: arq, base: path.dirname(arq), descricao: desc.length > MAX_DESCRICAO ? desc.slice(0, MAX_DESCRICAO - 3) + '...' : desc,
        modelo: !sim(dados['disable-model-invocation']), usuario: !nao(dados['user-invocable']) });
    }
  }
  return [...out.values()];
}

const esc = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/* Catalogo das skills (mensagem do dsh), ou '' se nao houver nenhuma. */
export function catalogo(raiz: string): string {
  const l = skills(raiz).filter((x) => x.modelo);
  if (!l.length) return '';
  return '<system-reminder>\nA skill is a reusable set of task-specific instructions. The following skills are available in this session:\n\n<available_skills>\n' +
    l.map((x) => `- \`${x.nome}\`: ${esc(x.descricao)}`).join('\n') + '\n</available_skills>\n\n' +
    "If the user names a skill, or the task clearly matches a skill's description, call the `skill` tool with the exact skill name before taking task actions. " +
    "Load all applicable skills, then follow their full instructions. This catalog contains summaries only; do not infer or follow a skill's instructions until it has been loaded.\n" +
    'A user may also invoke a skill directly; its <skill_content> block then appears in this conversation. Follow it, and do not call the `skill` tool again for that skill.\n</system-reminder>';
}

/* Corpo da skill no formato <skill_content> (resultado da ferramenta e do /nome). */
export function conteudoSkill(raiz: string, nome: string, paraModelo = true): string {
  const n = String(nome ?? '').trim();
  const s = skills(raiz).find((x) => x.nome.toLowerCase() === n.toLowerCase());
  if (!s) throw new Error(`skill "${n}" is unknown or no longer available`);
  if (paraModelo && !s.modelo) throw new Error(`skill "${n}" is not available for model invocation`);
  const corpo = frontmatter(ler(s.arquivo)).corpo.trim().slice(0, 12000);
  return `<skill_content name="${s.nome.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')}">\n<skill_resources>\n` +
    `Base directory for this skill: ${esc(s.base)}\nResolve relative paths mentioned by this skill against the base directory before using them. Load referenced resources only as needed.\n` +
    `</skill_resources>\n\n<skill_instructions>\n${corpo}\n</skill_instructions>\n</skill_content>`;
}
