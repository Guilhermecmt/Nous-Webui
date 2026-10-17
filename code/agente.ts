// O laco do agente: modelo -> ferramenta -> modelo, ate' ele responder em texto.
// Cada passo vira um evento para o painel (e fica salvo na sessao). Mudar
// arquivo ou rodar comando para e espera a pessoa aprovar.

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { conversar, type Chamada, type Mensagem } from './modelo.ts';
import * as F from './ferramentas.ts';

export type Evento = Record<string, unknown> & { t: string };
export type Modo = 'perguntar' | 'editar';  // editar = edicoes sem perguntar (comandos sempre perguntam)

export type Sessao = {
  id: string; titulo: string; pasta: string; modelo: string; modo: Modo;
  criado: number; atualizado: number;
  mensagens: Mensagem[];          // o que o modelo ve
  eventos: Evento[];              // o que o painel mostra
  originais: Record<string, string | null>;  // arquivo -> conteudo antes da 1a mudanca (null = nao existia)
  sempre: string[];               // comandos liberados nesta sessao
};

const MAX_PASSOS = 30;
const ORCAMENTO = 42000;  // caracteres de historico (~14k tokens) antes de enxugar

/* ------------------------------------------------------------ prompt */
function instrucoesDoProjeto(raiz: string): string {
  for (const n of ['NOUS.md', 'AGENTS.md', 'CLAUDE.md', '.nous/instrucoes.md']) {
    try {
      const t = fs.readFileSync(path.join(raiz, n), 'utf8').trim();
      if (t) return `\n\n# Project instructions (${n})\n` + t.slice(0, 4000);
    } catch { /* nao tem */ }
  }
  return '';
}

export function sistema(s: Sessao): string {
  let arvore = '';
  try { arvore = F.listar(s.pasta, { path: '.', depth: 2 }); } catch { arvore = '(nao consegui listar)'; }
  if (arvore.length > 3500) arvore = arvore.slice(0, 3500) + '\n...';
  return `You are Nous Code, a coding agent that runs locally on the user's Windows PC.
You work inside the project folder: ${s.pasta}
Today is ${new Date().toISOString().slice(0, 10)}. Shell: PowerShell on Windows ${os.release()}.

# How to work
- To use a tool, reply with ONLY one JSON object, nothing before or after it:
  {"name": "<tool name>", "arguments": { ... }}
- One tool per reply. You will receive the result and then continue.
- When the task is done, or you need something from the user, reply in Brazilian Portuguese, in plain text, without JSON. Be brief: say what you changed and how to check it.
- Look before you change: use list_files, search and read_file to find and read the relevant code first. Never guess the content of a file.
- To change a file, use edit_file with old_text copied exactly from read_file (without the "12| " line numbers). Use write_file only for new files or to rewrite a whole small file.
- Make the smallest change that solves the task and follow the style of the existing code.
- If a tool returns an error, read it and fix your call (for example, read the file again). Do not repeat the same failing call.
- Never run destructive commands (deleting folders, git reset --hard, git push, formatting disks) unless the user asked for exactly that.

# Project files (top levels)
${arvore}${instrucoesDoProjeto(s.pasta)}`;
}

/* ------------------------------------------------------------ contexto */
function enxugar(msgs: Mensagem[]) {
  let total = msgs.reduce((n, m) => n + m.content.length, 0);
  // os 6 ultimos ficam inteiros; resultados antigos de ferramenta encolhem primeiro
  for (let i = 1; i < msgs.length - 6 && total > ORCAMENTO; i++) {
    const m = msgs[i];
    if (m.role === 'tool' && m.content.length > 300) {
      total -= m.content.length - 120;
      m.content = m.content.slice(0, 100) + '\n[resultado antigo omitido para caber no contexto]';
    }
  }
}

/* ------------------------------------------------------------ resumo para o painel */
function resumo(c: Chamada): string {
  const a = c.args;
  switch (c.nome) {
    case 'list_files': return 'Olhando as pastas' + (a.path && a.path !== '.' ? ' em ' + a.path : '');
    case 'read_file': return 'Lendo ' + a.path + (a.start_line ? ` (a partir da linha ${a.start_line})` : '');
    case 'search': return 'Procurando "' + a.pattern + '"';
    case 'edit_file': return 'Editando ' + a.path;
    case 'write_file': return 'Escrevendo ' + a.path;
    case 'run_command': return 'Rodando: ' + a.command;
    default: return c.nome;
  }
}

/* ------------------------------------------------------------ o laco */
export type Ctx = {
  emitir: (e: Evento) => void;
  aprovar: (e: Evento) => Promise<{ ok: boolean; sempre?: boolean }>;
  sinal: AbortSignal;
  salvar: () => void;
};

export async function turno(s: Sessao, pedido: string, ctx: Ctx) {
  const ev = (e: Evento) => { s.eventos.push(e); ctx.emitir(e); };
  if (!s.mensagens.length) s.mensagens.push({ role: 'system', content: '' });
  s.mensagens[0] = { role: 'system', content: sistema(s) };  // arvore e instrucoes sempre atuais
  s.mensagens.push({ role: 'user', content: pedido });
  ev({ t: 'voce', texto: pedido });
  if (s.titulo === 'Nova conversa') s.titulo = pedido.slice(0, 60);

  const vistos = new Map<string, number>();  // acao + resultado -> vezes neste turno
  let empurroes = 0;
  for (let passo = 1; passo <= MAX_PASSOS; passo++) {
    if (ctx.sinal.aborted) break;
    enxugar(s.mensagens);
    ctx.emitir({ t: 'pensando', passo });
    let texto = '';
    const r = await conversar(s.modelo, s.mensagens, F.ESQUEMAS, F.NOMES,
      (p) => { texto += p; ctx.emitir({ t: 'texto', d: p }); }, ctx.sinal);

    if (!r.chamadas.length) {
      s.mensagens.push({ role: 'assistant', content: r.texto });
      // modelo pequeno anuncia ("Vamos verificar o package.json:") e para: empurra
      if (empurroes < 2 && anunciaSemFazer(r.texto)) {
        empurroes++;
        ev({ t: 'nota', texto: r.texto.trim() });
        s.mensagens.push({ role: 'user', content: 'Go on: do it now. Reply with only the JSON of the next tool call. If the task is already done, give your final answer.' });
        continue;
      }
      ev({ t: 'resposta', texto: r.texto.trim() || '(o modelo nao respondeu nada)' });
      ctx.salvar();
      return;
    }
    if (r.texto.trim()) ev({ t: 'nota', texto: r.texto.trim() });
    else if (texto) ctx.emitir({ t: 'limpar' });  // o que foi transmitido era a chamada
    const c = r.chamadas[0];  // uma por vez: modelos pequenos se perdem com varias
    s.mensagens.push({ role: 'assistant', content: JSON.stringify({ name: c.nome, arguments: c.args }) });

    ev({ t: 'ferramenta', id: c.id, nome: c.nome, args: c.args, resumo: resumo(c) });
    const res = await executar(s, c, ctx);
    ev({ t: 'resultado', id: c.id, ok: res.ok, resumo: res.resumo, saida: res.saida.slice(0, 20000), diff: res.diff });
    s.mensagens.push({ role: 'tool', tool_name: c.nome, content: F.paraModelo(res.ok ? res.saida : 'ERROR: ' + res.saida) });
    ctx.salvar();

    // a mesma acao com o mesmo resultado pela 3a vez = andando em circulo
    const chave = c.nome + JSON.stringify(c.args) + '\u0000' + res.saida;
    const n = (vistos.get(chave) || 0) + 1;
    vistos.set(chave, n);
    if (n >= 3) {
      const txt = 'Parei: estava repetindo "' + resumo(c) + '" sem avancar. ' +
        (c.nome === 'run_command' && !res.ok ? 'O comando continua falhando com o mesmo erro; veja a saida acima. ' : '') +
        'Me diga como seguir, ou tente outro modelo.';
      ev({ t: 'resposta', texto: txt });
      s.mensagens.push({ role: 'assistant', content: txt });
      ctx.salvar();
      return;
    }
  }
  if (ctx.sinal.aborted) ev({ t: 'resposta', texto: 'Parado por voce.' });
  else ev({ t: 'resposta', texto: `Parei depois de ${MAX_PASSOS} passos. Diga "continue" se quiser que eu siga.` });
  ctx.salvar();
}

/* "Vamos verificar o arquivo:" / "Primeiro, vou listar..." no fim da resposta,
 * sem a chamada: o modelo disse o que ia fazer e parou. */
export function anunciaSemFazer(t: string): boolean {
  const fim = t.trim().split(/\n+/).slice(-2).join(' ').toLowerCase();
  if (!fim) return false;
  if (/[:：]\s*$/.test(fim)) return true;
  return /\b(vamos|vou|primeiro,|em seguida|agora,?\s+(vou|vamos)|let me|i will|i'll)\b/.test(fim) && !/\?\s*$/.test(fim);
}

type Res = { ok: boolean; resumo: string; saida: string; diff?: string };

async function executar(s: Sessao, c: Chamada, ctx: Ctx): Promise<Res> {
  const a = c.args;
  try {
    switch (c.nome) {
      case 'list_files': {
        const t = F.listar(s.pasta, a);
        return { ok: true, resumo: (t.split('\n').length - 1) + ' itens', saida: t };
      }
      case 'read_file': {
        const t = F.ler(s.pasta, a);
        return { ok: true, resumo: t.split('\n').length + ' linhas', saida: t };
      }
      case 'search': {
        const t = F.buscar(s.pasta, a);
        const n = t.startsWith('Nada encontrado') ? 0 : t.split('\n').length;
        return { ok: true, resumo: n ? n + ' resultados' : 'nada encontrado', saida: t };
      }
      case 'edit_file':
      case 'write_file': {
        const abs = F.resolver(s.pasta, a.path);
        const rel = F.relativo(s.pasta, abs);
        const atual = F.conteudoAtual(abs);
        let novo: string;
        if (c.nome === 'edit_file') {
          if (atual === null) throw new Error('o arquivo ' + rel + ' nao existe; use write_file para criar');
          novo = F.aplicarEdicao(atual, String(a.old_text ?? ''), String(a.new_text ?? ''));
        } else {
          novo = String(a.content ?? '');
        }
        if (atual !== null && novo === atual) return { ok: true, resumo: 'nada mudou', saida: 'The file already had this content.' };
        const d = F.diff(atual || '', novo);
        if (s.modo !== 'editar') {
          const r = await ctx.aprovar({ t: 'pede', id: c.id, tipo: 'arquivo', arquivo: rel, novo: atual === null, diff: d.texto, mais: d.mais, menos: d.menos });
          if (!r.ok) return { ok: false, resumo: 'recusado', saida: 'The user rejected this change. Ask what they want instead, or try another approach.' };
        }
        if (!(rel in s.originais)) s.originais[rel] = atual;
        F.gravar(abs, novo);
        return { ok: true, resumo: `+${d.mais} -${d.menos}`, saida: (atual === null ? 'Created ' : 'Changed ') + rel + ` (+${d.mais} -${d.menos} lines).`, diff: d.texto };
      }
      case 'run_command': {
        const cmd = String(a.command || '').trim();
        if (!cmd) throw new Error('command vazio');
        const seg = Math.max(5, Math.min(600, Number(a.timeout_s) || 120));
        if (!s.sempre.includes(cmd)) {
          const r = await ctx.aprovar({ t: 'pede', id: c.id, tipo: 'comando', comando: cmd });
          if (!r.ok) return { ok: false, resumo: 'recusado', saida: 'The user did not allow this command. Ask what they want instead.' };
          if (r.sempre) s.sempre.push(cmd);
        }
        const r = await F.rodar(s.pasta, cmd, seg, ctx.sinal);
        const saida = (r.saida.trim() || '(sem saida)') + `\n[codigo de saida: ${r.codigo}]`;
        return { ok: r.codigo === 0, resumo: (r.codigo === 0 ? 'ok' : 'erro ' + r.codigo) + ' em ' + (r.tempo / 1000).toFixed(1) + 's', saida };
      }
    }
    throw new Error('ferramenta desconhecida: ' + c.nome);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, resumo: 'erro', saida: msg };
  }
}

/* Volta os arquivos ao que eram antes da sessao (todos ou um). */
export function desfazer(s: Sessao, arquivo?: string): string[] {
  const feitos: string[] = [];
  for (const rel of Object.keys(s.originais)) {
    if (arquivo && rel !== arquivo) continue;
    const abs = F.resolver(s.pasta, rel);
    const orig = s.originais[rel];
    if (orig === null) { try { fs.unlinkSync(abs); } catch { /* ja nao existe */ } }
    else F.gravar(abs, orig);
    delete s.originais[rel];
    feitos.push(rel);
  }
  return feitos;
}

/* Arquivos mudados na sessao, com +/- em relacao ao original. */
export function mudancas(s: Sessao): { arquivo: string; novo: boolean; mais: number; menos: number }[] {
  return Object.keys(s.originais).map((rel) => {
    const atual = F.conteudoAtual(F.resolver(s.pasta, rel)) || '';
    const d = F.diff(s.originais[rel] || '', atual);
    return { arquivo: rel, novo: s.originais[rel] === null, mais: d.mais, menos: d.menos };
  });
}
