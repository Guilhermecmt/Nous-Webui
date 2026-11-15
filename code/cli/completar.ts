// Tab no terminal: /comandos, valores dos comandos e @arquivos.
import fs from 'node:fs';
import path from 'node:path';
import { ALCANCES, ESFORCOS, MODOS, acharComando, completarComando } from './comandos.ts';

export type ContextoCompletar = { pasta: string; skills: () => string[]; modelos: () => string[] };

const IGNORAR = new Set(['node_modules', '.git', '.hg', '.svn', '__pycache__', '.venv', '.next', 'dist', 'build']);

/* @caminho: entradas da pasta que combinam com o que foi digitado. */
export function completarArquivo(fragmento: string, pasta: string, max = 60): string[] {
  const entre = fragmento.startsWith('"');
  const f = (entre ? fragmento.slice(1) : fragmento).replace(/\\/g, '/');
  const k = f.lastIndexOf('/');
  const dirRel = k >= 0 ? f.slice(0, k + 1) : '';
  const prefixo = k >= 0 ? f.slice(k + 1) : f;
  const dirAbs = path.resolve(pasta, dirRel || '.');
  let nomes: fs.Dirent[] = [];
  try { nomes = fs.readdirSync(dirAbs, { withFileTypes: true }); } catch { return []; }
  const p = prefixo.toLowerCase();
  return nomes
    .filter((d) => d.name.toLowerCase().startsWith(p) && (prefixo.startsWith('.') || !d.name.startsWith('.')) && (!IGNORAR.has(d.name) || p === d.name.toLowerCase()))
    .sort((a, b) => Number(b.isDirectory()) - Number(a.isDirectory()) || a.name.localeCompare(b.name))
    .slice(0, max)
    .map((d) => {
      const rel = dirRel + d.name + (d.isDirectory() ? '/' : '');
      return /\s/.test(rel) || entre ? '@"' + rel + (d.isDirectory() ? '' : '"') : '@' + rel;
    });
}

/* Devolve [candidatos, trecho que eles substituem], como o completer do readline pede. */
export function completarLinha(linha: string, ctx: ContextoCompletar): [string[], string] {
  // @arquivo em qualquer ponto da linha
  const arq = /(?:^|\s)@("[^"]*|[^\s"]*)$/.exec(linha);
  if (arq) {
    const frag = arq[1];
    return [completarArquivo(frag, ctx.pasta), '@' + frag];
  }
  // /comando na primeira palavra
  const cmd = /^\/([^\s]*)$/.exec(linha);
  if (cmd) return [completarComando(cmd[1], ctx.skills()), linha];
  // argumento de um comando
  const arg = /^\/(\S+)\s+(.*)$/.exec(linha);
  if (arg) {
    const c = acharComando(arg[1]);
    const frag = arg[2];
    let opcoes: string[] = [];
    if (c) {
      if (c.nome === 'effort') opcoes = [...ESFORCOS];
      else if (c.nome === 'modo') opcoes = [...MODOS];
      else if (c.nome === 'alcance') opcoes = [...ALCANCES];
      else if (c.nome === 'modelo') opcoes = ctx.modelos();
      else if (c.nome === 'mcp') opcoes = ['permitir', 'desligar'];
      else if (c.nome === 'plano') opcoes = ['sair'];
      else if (c.nome === 'objetivo') opcoes = ['pausar', 'retomar', 'limpar'];
      else if (c.nome === 'padrao') opcoes = ['modo', 'alcance'];
    }
    const p = frag.toLowerCase();
    return [opcoes.filter((o) => o.toLowerCase().startsWith(p)), frag];
  }
  return [[], linha];
}
