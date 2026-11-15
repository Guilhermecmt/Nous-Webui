// Um turno do agente no terminal: manda o pedido, mostra os eventos que chegam,
// responde aos pedidos de aprovacao e trata Esc / Ctrl+C.
import type { Cliente, Evento } from './cliente.ts';
import type { Io } from './io.ts';
import { formatarDiff, mdLinha, Renderizador, type Estilo } from './tela.ts';

export type RespostaPedido = { ok: boolean; sempre?: boolean; texto?: string; parar?: boolean };

export type OpcTurno = {
  /* Decide sem perguntar (modo -p). Devolve null para perguntar a quem esta no terminal. */
  automatico?: (e: Evento) => RespostaPedido | null;
  /* "sempre" num arquivo: o servidor so' guarda isso para comandos, entao o terminal sobe o modo da conversa. */
  aoSempreArquivo?: () => Promise<void>;
  /* Quanto esperar o servidor encerrar depois de /parar antes de largar o fluxo. */
  esperaParadaMs?: number;
};

export type ResultadoTurno = {
  resposta: string;
  erro: string;
  interrompido: boolean;
  mudancas: Renderizador['mudancas'];
  tokens: number;
  limite: number;
};

const LIMITE_DIFF = 60;

/* ------------------------------------------------------------ perguntas ao usuario */
function cabecalho(est: Estilo, titulo: string, extra = '') {
  return est.yellow('╭ ') + est.bold(titulo) + (extra ? ' ' + extra : '');
}

async function perguntarTecla(io: Io, est: Estilo, rotulo: string, validas: string[]): Promise<string> {
  io.saida(est.yellow('╰ ') + rotulo + ' ');
  const k = await io.tecla(validas);
  io.saida((k === 'esc' ? est.dim('esc') : est.bold(k)) + '\n');
  return k;
}

/* ask_user_question: perguntas com opcoes numeradas (uma ou varias) e resposta livre. */
async function perguntasAoUsuario(e: Evento, io: Io, est: Estilo): Promise<RespostaPedido> {
  const respostas: { id: string; selected: string[]; custom?: string }[] = [];
  for (const q of e.perguntas || []) {
    io.saida(cabecalho(est, q.pergunta, q.titulo ? est.dim('(' + q.titulo + ')') : '') + '\n');
    const ops: { label: string; description?: string }[] = q.opcoes || [];
    ops.forEach((o, i) => io.saida(est.yellow('│ ') + est.cyan(String(i + 1) + '.') + ' ' + est.bold(o.label) + (o.description ? est.dim(' - ' + o.description) : '') + '\n'));
    const dica = ops.length ? (q.multipla ? 'números separados por vírgula, ou texto livre' : 'número, ou texto livre') + '; Enter pula' : 'sua resposta; Enter pula';
    const l = await io.linha(est.yellow('╰ ') + est.dim('(' + dica + ') ') + '› ');
    if (l.t !== 'linha') return { ok: false, parar: l.t === 'ctrl-c' || l.t === 'fim' };
    respostas.push({ id: q.id, ...lerEscolhas(l.texto, ops.map((o) => o.label), !!q.multipla) });
  }
  return { ok: true, texto: JSON.stringify(respostas) };
}

/* "2" ou "1, 3" escolhem opcoes; qualquer outra coisa e' resposta livre. */
export function lerEscolhas(texto: string, opcoes: string[], multipla: boolean): { selected: string[]; custom?: string } {
  const t = texto.trim();
  if (!t) return { selected: [] };
  if (opcoes.length && /^\d+(\s*[,; ]\s*\d+)*$/.test(t)) {
    const idx = t.split(/[,; ]+/).map(Number);
    if (idx.every((i) => i >= 1 && i <= opcoes.length)) {
      const sel = [...new Set(idx)].map((i) => opcoes[i - 1]);
      return { selected: multipla ? sel : sel.slice(0, 1) };
    }
  }
  const igual = opcoes.find((o) => o.toLowerCase() === t.toLowerCase());
  return igual ? { selected: [igual] } : { selected: [], custom: t };
}

/* Mostra o pedido, le a resposta de quem esta no terminal. */
export async function responderPedido(e: Evento, io: Io, est: Estilo, opc: OpcTurno = {}): Promise<RespostaPedido> {
  const cancelou = (): RespostaPedido => ({ ok: false, parar: true });
  switch (e.tipo) {
    case 'arquivo': {
      io.saida('\n' + cabecalho(est, (e.novo ? 'Criar ' : 'Mudar ') + e.arquivo + '?', est.green('+' + e.mais) + ' ' + est.red('−' + e.menos) + (e.fora ? ' ' + est.yellow('(fora do projeto)') : '')) + '\n');
      io.saida(formatarDiff(String(e.diff || ''), est, LIMITE_DIFF, est.yellow('│ ')).replace(/^/gm, '') + '\n');
      const k = await perguntarTecla(io, est, est.bold('[s]') + 'im  ' + est.bold('[n]') + 'ão  ' + est.bold('[a]') + ' sempre (modo editar)?', ['s', 'n', 'a', 'y']);
      if (k === 'esc') return cancelou();
      if (k === 'n') return { ok: false };
      if (k === 'a') await opc.aoSempreArquivo?.();
      return { ok: true, sempre: k === 'a' };
    }
    case 'comando': {
      io.saida('\n' + cabecalho(est, e.descricao && e.descricao !== e.comando ? String(e.descricao) : 'Rodar este comando?') + '\n');
      io.saida(String(e.comando).split('\n').map((l) => est.yellow('│ ') + est.cyan(l)).join('\n') + '\n');
      if (e.perigo) io.saida(est.yellow('│ ') + est.red('Atenção: este comando ' + e.perigo + '. Pode não ter volta.') + '\n');
      if (e.fundo) io.saida(est.yellow('│ ') + est.dim('Vai rodar em segundo plano.') + '\n');
      const k = await perguntarTecla(io, est, est.bold('[s]') + 'im  ' + est.bold('[n]') + 'ão  ' + est.bold('[a]') + ' sempre nesta conversa?', ['s', 'n', 'a', 'y']);
      if (k === 'esc') return cancelou();
      return k === 'n' ? { ok: false } : { ok: true, sempre: k === 'a' };
    }
    case 'mcp': {
      io.saida('\n' + cabecalho(est, 'Usar ' + e.servidor + ' › ' + String(e.ferramenta).split('__').pop() + '?') + '\n');
      if (e.descricao) io.saida(est.yellow('│ ') + est.dim(String(e.descricao)) + '\n');
      io.saida(JSON.stringify(e.args, null, 1).split('\n').map((l) => est.yellow('│ ') + est.dim(l)).join('\n') + '\n');
      const k = await perguntarTecla(io, est, est.bold('[s]') + 'im  ' + est.bold('[n]') + 'ão  ' + est.bold('[a]') + ' sempre nesta conversa?', ['s', 'n', 'a', 'y']);
      if (k === 'esc') return cancelou();
      return k === 'n' ? { ok: false } : { ok: true, sempre: k === 'a' };
    }
    case 'internet': {
      io.saida('\n' + cabecalho(est, 'Usar a internet nesta conversa?') + '\n');
      io.saida(est.yellow('│ ') + 'O agente quer buscar ou ler ' + est.bold(String(e.alvo)) + est.dim(' (só o endereço ou a busca saem do computador)') + '\n');
      const k = await perguntarTecla(io, est, est.bold('[s]') + 'im  ' + est.bold('[n]') + 'ão?', ['s', 'n', 'a', 'y']);
      if (k === 'esc') return cancelou();
      return { ok: k !== 'n' };
    }
    case 'perguntas': return perguntasAoUsuario(e, io, est);
    case 'pergunta': {
      io.saida('\n' + cabecalho(est, String(e.pergunta)) + '\n');
      const ops: string[] = e.opcoes || [];
      ops.forEach((o, i) => io.saida(est.yellow('│ ') + est.cyan(String(i + 1) + '.') + ' ' + o + '\n'));
      const l = await io.linha(est.yellow('╰ ') + '› ');
      if (l.t !== 'linha') return cancelou();
      const r = lerEscolhas(l.texto, ops, false);
      return { ok: true, texto: r.selected[0] || r.custom || '' };
    }
    case 'plano': {
      io.saida('\n' + cabecalho(est, 'Plano proposto') + '\n');
      let fence = false;
      for (const l of String(e.plano || '').split('\n')) {
        if (/^\s*```/.test(l)) fence = !fence;
        io.saida(est.yellow('│ ') + (fence ? est.gray(l) : mdLinha(l, est)) + '\n');
      }
      const k = await perguntarTecla(io, est, est.bold('[a]') + 'provar e executar  ' + est.bold('[c]') + 'ontinuar planejando?', ['a', 's', 'c', 'n']);
      if (k === 'esc') return cancelou();
      if (k === 'a' || k === 's') return { ok: true };
      const l = await io.linha(est.yellow('╰ ') + est.dim('o que mudar no plano (Enter para só continuar) ') + '› ');
      return { ok: false, texto: l.t === 'linha' ? l.texto.trim() : '' };
    }
    default:
      return { ok: false };
  }
}

/* ------------------------------------------------------------ o turno */
export async function executarTurno(cliente: Cliente, id: string, texto: string, io: Io, ren: Renderizador, opc: OpcTurno = {}): Promise<ResultadoTurno> {
  const est = ren.est;
  const ctrl = new AbortController();
  let interrompido = false;

  const parar = () => {
    if (interrompido) { ctrl.abort(); return; }           // de novo: larga o fluxo
    interrompido = true;
    ren.pausar();
    io.atividade(est.dim('\nInterrompendo…') + '\n');
    cliente.pedir('POST', '/parar', { id }).catch(() => { /* o servico ja' parou */ });
    setTimeout(() => ctrl.abort(), opc.esperaParadaMs ?? 8000).unref();   // o servidor encerra o fluxo; se nao, largamos
  };
  const desligar = io.aoInterromper(parar);

  try {
    for await (const e of cliente.mensagem(id, texto, ctrl.signal)) {
      if (e.t === 'pede') {
        ren.pausar();
        if (e.tipo === 'arquivo') ren.diffJaMostrado.add(String(e.id));
        const auto = opc.automatico?.(e) ?? null;
        const r = auto ?? await responderPedido(e, io, est, opc);
        if (r.parar) parar();
        if (!interrompido || r.parar) {
          try { await cliente.pedir('POST', '/aprovar', { id, pedido: e.id, ok: r.ok, sempre: !!r.sempre, texto: r.texto }); }
          catch { /* /parar ja' resolveu o pedido */ }
        }
        if (auto) io.atividade(est.dim(r.ok ? '  ✓ aprovado automaticamente' : '  ✗ recusado (sem quem aprovar)') + '\n');
        else io.saida(r.ok ? est.dim('  ✓ aprovado') + '\n' : est.dim('  ✗ recusado') + '\n');
        continue;
      }
      ren.evento(e);
    }
  } catch (err) {
    if (!ctrl.signal.aborted) ren.evento({ t: 'erro', texto: err instanceof Error ? err.message : String(err) });
  } finally {
    desligar();
    ren.encerrar();
  }
  return { resposta: ren.ultimaResposta, erro: ren.erro, interrompido, mudancas: ren.mudancas, tokens: ren.tokens, limite: ren.limite };
}
