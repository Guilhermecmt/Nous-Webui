// O que o terminal desenha: cores, linhas de ferramenta, diff, rodape e o
// Renderizador, que transforma os eventos do agente em texto.
import type { Evento } from './cliente.ts';

export type Estilo = Record<'dim' | 'bold' | 'italic' | 'red' | 'green' | 'yellow' | 'blue' | 'cyan' | 'magenta' | 'gray' | 'inv', (s: string) => string>;

export function criarEstilo(cor: boolean): Estilo {
  const f = (a: number, b: number) => (s: string) => (cor ? `\x1b[${a}m${s}\x1b[${b}m` : s);
  return { dim: f(2, 22), bold: f(1, 22), italic: f(3, 23), red: f(31, 39), green: f(32, 39), yellow: f(33, 39), blue: f(34, 39),
    cyan: f(36, 39), magenta: f(35, 39), gray: f(90, 39), inv: f(7, 27) };
}

/* Cor so' quando a saida e' um terminal e a pessoa nao pediu sem cor (NO_COLOR). */
export function corLigada(tty: boolean | undefined, env: NodeJS.ProcessEnv = process.env): boolean {
  if (env.NO_COLOR !== undefined && env.NO_COLOR !== '') return false;
  if (env.FORCE_COLOR && env.FORCE_COLOR !== '0') return true;
  return !!tty && env.TERM !== 'dumb';
}

export const semAnsi = (s: string) => s.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, '');

/* 1234 -> "1,2k"; 16384 -> "16,4k". */
export function fmtTokens(n: number): string {
  if (n < 1000) return String(Math.round(n));
  return (Math.round(n / 100) / 10).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'k';
}
export function fmtGb(gb: number): string { return gb ? gb.toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' GB' : ''; }
export function fmtSegundos(ms: number): string { return ms >= 1500 ? (ms / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' s' : ''; }
export function fmtIdade(ts: number, agora = Date.now()): string {
  const s = Math.max(0, Math.round((agora - ts) / 1000));
  if (s < 60) return 'agora há pouco';
  if (s < 3600) return 'há ' + Math.round(s / 60) + ' min';
  if (s < 86400) return 'há ' + Math.round(s / 3600) + ' h';
  return 'há ' + Math.round(s / 86400) + (Math.round(s / 86400) === 1 ? ' dia' : ' dias');
}

/* Diff com + em verde e - em vermelho; passa de `max` linhas, resume. */
export function formatarDiff(diff: string, est: Estilo, max = 40, recuo = '    '): string {
  const linhas = String(diff || '').replace(/\r/g, '').split('\n');
  while (linhas.length && linhas[linhas.length - 1] === '') linhas.pop();
  const mostra = linhas.slice(0, max).map((l) => {
    if (l.startsWith('+++') || l.startsWith('---')) return recuo + est.bold(l);
    if (l[0] === '+') return recuo + est.green(l);
    if (l[0] === '-') return recuo + est.red(l);
    if (l.startsWith('@@')) return recuo + est.cyan(l);
    return recuo + est.dim(l);
  });
  if (linhas.length > max) mostra.push(recuo + est.dim('… mais ' + (linhas.length - max) + ' linhas'));
  return mostra.join('\n');
}

/* O argumento que melhor identifica a chamada, para a linha compacta. */
export function argPrincipal(nome: string, args: Record<string, any> = {}): string {
  const p = (x: unknown) => String(x ?? '').replace(/^\.[\\/]/, '').replace(/\s+/g, ' ').trim();
  switch (nome) {
    case 'read': case 'edit': case 'write': return p(args.file_path) + (args.offset && Number(args.offset) > 1 ? ':' + args.offset : '');
    case 'list_files': return p(args.path || '.');
    case 'glob': return p(args.pattern);
    case 'grep': return p(args.pattern) + (args.include ? ' em ' + p(args.include) : '');
    case 'pwsh': return p(args.command) + (args.run_in_background ? ' (em segundo plano)' : '');
    case 'web_fetch': return p(args.url);
    case 'web_search': return p(Array.isArray(args.queries) ? args.queries.join(' | ') : args.queries);
    case 'subagent': return p(args.description || args.prompt);
    case 'skill': return p(args.name);
    case 'lsp': return p(args.operation) + ' ' + p(args.file_path) + ':' + p(args.line);
    case 'job_output': case 'job_kill': return p(args.job_id);
    default: {
      const v = Object.values(args).find((x) => typeof x === 'string');
      return v ? p(v) : '';
    }
  }
}

const corta = (s: string, n: number) => (s.length > n ? s.slice(0, Math.max(0, n - 1)) + '…' : s);

export function linhaFerramenta(e: Evento, est: Estilo, largura = 100): string {
  const nome = String(e.nome || '');
  const arg = argPrincipal(nome, e.args);
  return est.cyan('●') + ' ' + est.bold(nome.replace(/^mcp__/, 'mcp ').replace(/__/g, ' › ')) + (arg ? ' ' + est.dim(corta(arg, Math.max(20, largura - nome.length - 6))) : '');
}

export function linhaResultado(e: Evento, est: Estilo): string {
  const resumo = String(e.resumo || (e.ok ? 'pronto' : 'falhou'));
  const t = fmtSegundos(Number(e.ms) || 0);
  const txt = '  ⎿ ' + resumo + (t ? ' · ' + t : '');
  return e.ok ? est.dim(txt) : est.red(txt);
}

/* Lista de afazeres do todo_write. */
export function checklist(tarefas: { content: string; status: string }[], est: Estilo): string {
  return tarefas.map((t) => {
    if (t.status === 'completed') return '  ' + est.green('☒') + ' ' + est.dim(t.content);
    if (t.status === 'in_progress') return '  ' + est.yellow('◐') + ' ' + est.bold(t.content);
    return '  ☐ ' + t.content;
  }).join('\n');
}

/* **negrito**, `codigo` e # titulos de uma linha de Markdown. */
export function mdLinha(l: string, est: Estilo): string {
  let t = l;
  const h = /^#{1,6}\s+(.*)$/.exec(t);
  if (h) return est.bold(est.cyan(h[1]));
  t = t.replace(/^(\s*)[-*] /, '$1• ').replace(/\*\*([^*\n]+)\*\*/g, (_m, x) => est.bold(x)).replace(/`([^`\n]+)`/g, (_m, x) => est.cyan(x));
  return t;
}

export type InfoRodape = { modelo: string; raciocinio: string; modo: string; tokens: number; limite: number; mudados?: number };
export function rodape(i: InfoRodape, est: Estilo): string {
  const pct = i.limite ? Math.round((i.tokens / i.limite) * 100) : 0;
  const ctx = i.tokens ? 'contexto ' + fmtTokens(i.tokens) + ' de ' + fmtTokens(i.limite) + ' (' + pct + '%)' : 'contexto vazio';
  const partes = [i.modelo, 'raciocínio ' + (({ auto: 'auto', desligado: 'desligado', baixo: 'baixo', medio: 'médio', alto: 'alto' } as Record<string, string>)[i.raciocinio] || i.raciocinio),
    'modo ' + i.modo, pct >= 80 ? est.yellow(ctx) : ctx];
  if (i.mudados) partes.push(i.mudados + (i.mudados === 1 ? ' arquivo mudado' : ' arquivos mudados'));
  return est.dim(partes.join(' · '));
}

/* ------------------------------------------------------------ giro */
const QUADROS = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
export class Giro {
  private timer: NodeJS.Timeout | null = null;
  private i = 0;
  private texto = '';
  private ini = 0;
  private escrever: (s: string) => void;
  private est: Estilo;
  private ativo: boolean;
  constructor(escrever: (s: string) => void, est: Estilo, ativo: boolean) { this.escrever = escrever; this.est = est; this.ativo = ativo; }
  get rodando() { return this.timer !== null; }
  iniciar(texto: string) {
    this.texto = texto;
    if (!this.ativo) return;
    if (!this.timer) {
      this.ini = Date.now();
      this.timer = setInterval(() => this.pintar(), 90);
      this.timer.unref();
    }
    this.pintar();
  }
  mudar(texto: string) { this.texto = texto; }
  private pintar() {
    const seg = Math.floor((Date.now() - this.ini) / 1000);
    this.escrever('\r\x1b[2K' + this.est.magenta(QUADROS[this.i++ % QUADROS.length]) + ' ' + this.est.dim(this.texto + (seg >= 3 ? ' ' + seg + ' s' : '')));
  }
  parar() {
    if (this.timer) { clearInterval(this.timer); this.timer = null; this.escrever('\r\x1b[2K'); }
  }
}

/* ------------------------------------------------------------ renderizador */
export type OpcRenderizador = {
  saida: (s: string) => void;        // o texto da resposta
  atividade: (s: string) => void;    // ferramentas, resultados, notas (stderr no modo -p)
  est: Estilo;
  tty: boolean;                      // pode redesenhar a linha (giro)
  streaming: boolean;                // mostra a resposta aos poucos; senao so' guarda a final
  largura?: () => number;
};

export class Renderizador {
  ultimaResposta = '';
  diffJaMostrado = new Set<string>();   // ids de pedidos cujo diff a pessoa ja viu na aprovacao
  erro = '';
  parado = false;
  tokens = 0;
  limite = 0;
  mudancas: { arquivo: string; mais: number; menos: number; novo?: boolean }[] = [];
  tarefas: { content: string; status: string }[] = [];
  private o: OpcRenderizador;
  private giro: Giro;
  private linha = '';              // linha da resposta ainda sem \n
  private emFence = false;
  private impresso = false;        // este trecho de texto ja' foi mostrado ao vivo
  private segurando = false;       // o trecho virou chamada de ferramenta em JSON: nao mostra
  private comecou = false;         // ja' mostrou algo do trecho
  private noInicio = true;         // o cursor esta no comeco de uma linha
  private pens = '';

  constructor(o: OpcRenderizador) {
    this.o = o;
    this.giro = new Giro((s) => o.atividade(s), o.est, o.tty && o.streaming);
  }

  get est() { return this.o.est; }
  pausar() { this.parar(); }

  private largura() { return this.o.largura ? this.o.largura() : 100; }

  /* Escreve na atividade garantindo que comece numa linha nova. */
  private ativ(s: string) {
    this.parar();
    if (!this.noInicio && this.o.streaming) { this.o.saida('\n'); this.noInicio = true; }
    this.o.atividade(s + '\n');
  }

  private parar() { this.giro.parar(); }

  private escreverTexto(s: string) {
    this.o.saida(s);
    this.noInicio = s.endsWith('\n');
  }

  private fecharPensamento() {
    if (!this.pens.trim()) { this.pens = ''; return; }
    const um = this.pens.replace(/\s+/g, ' ').trim();
    this.parar();
    this.o.atividade(this.o.est.dim(this.o.est.italic('✻ ' + corta(um, Math.max(30, this.largura() - 6)))) + '\n');
    this.pens = '';
  }

  /* Empurra o texto que chegou: so' linhas inteiras, ja' com o Markdown leve. */
  private texto(d: string) {
    if (!this.o.streaming || this.segurando) return;
    this.parar();
    this.linha += d;
    let k: number;
    while ((k = this.linha.indexOf('\n')) >= 0) {
      const l = this.linha.slice(0, k);
      this.linha = this.linha.slice(k + 1);
      if (!this.emitirLinha(l)) return;
    }
  }
  private emitirLinha(l: string): boolean {
    const t = l.trim();
    if (!this.comecou && t === '') return true;                     // linhas vazias do comeco
    if (!this.emFence && (t.startsWith('{') || t.startsWith('[{'))) { this.segurando = true; this.linha = ''; return false; }  // chamada de ferramenta em JSON
    if (/^```/.test(t)) { this.emFence = !this.emFence; this.escreverTexto(this.o.est.dim(l) + '\n'); }
    else if (this.emFence) this.escreverTexto(this.o.est.gray('  ' + l) + '\n');
    else this.escreverTexto(mdLinha(l, this.o.est) + '\n');
    this.comecou = true; this.impresso = true;
    return true;
  }
  private soltarResto() {
    if (this.linha && !this.segurando) this.emitirLinha(this.linha);
    this.linha = '';
  }
  private novoTrecho() {
    this.linha = ''; this.emFence = false; this.impresso = false; this.segurando = false; this.comecou = false;
  }

  evento(e: Evento) {
    const est = this.o.est;
    switch (e.t) {
      case 'pensando': this.giro.iniciar(e.passo > 1 ? 'Pensando, passo ' + e.passo : 'Pensando'); break;
      case 'pensamento':
        this.pens += String(e.d || '');
        this.giro.mudar('Raciocinando: ' + corta(this.pens.replace(/\s+/g, ' ').trim().slice(-60), 60));
        if (this.giro.rodando) { /* o giro mostra o fim do raciocinio */ }
        break;
      case 'passo': this.tokens = Number(e.tokens) || 0; this.limite = Number(e.limite) || this.limite; break;
      case 'texto': this.fecharPensamento(); this.texto(String(e.d || '')); break;
      case 'limpar': this.soltarResto(); this.novoTrecho(); break;
      case 'nota': {
        this.fecharPensamento(); this.soltarResto();
        const ja = this.impresso; this.novoTrecho();
        const txt = String(e.texto || '');
        if (e.tipo) this.ativ(est.yellow('! ' + txt));
        else if (!ja && this.o.streaming) this.escreverLinhas(txt);
        else if (!ja) this.o.atividade(est.dim(corta(txt, 300)) + '\n');
        break;
      }
      case 'resposta': {
        this.fecharPensamento(); this.soltarResto();
        const ja = this.impresso; this.novoTrecho();
        this.parar();
        this.ultimaResposta = String(e.texto || '');
        if (!ja && this.o.streaming) this.escreverLinhas(this.ultimaResposta);
        break;
      }
      case 'ferramenta': this.fecharPensamento(); this.soltarResto(); this.novoTrecho(); this.ativ(linhaFerramenta(e, est, this.largura())); break;
      case 'sub': this.ativ(est.dim('    ' + corta(String(e.resumo || ''), this.largura() - 6))); break;
      case 'resultado': {
        this.ativ(linhaResultado(e, est));
        if (e.diff && e.ok && !this.diffJaMostrado.has(String(e.id))) this.ativ(formatarDiff(String(e.diff), est, 14));
        else if (!e.ok && e.saida && !/^recusado|^bloqueado/.test(String(e.resumo))) this.ativ(est.dim(String(e.saida).split('\n').slice(0, 4).map((l) => '    ' + corta(l, this.largura() - 6)).join('\n')));
        break;
      }
      case 'tarefas': this.tarefas = e.tarefas || []; if (this.tarefas.length) this.ativ(checklist(this.tarefas, est)); break;
      case 'objetivo': {
        const o = e.objetivo;
        if (o) this.ativ(est.magenta('◎ Objetivo ') + est.dim('(' + faseObjetivo(o.phase) + ', rodada ' + o.roundsStarted + '/' + o.maxGoalRounds + ') ') + o.objective);
        break;
      }
      case 'modo-plano': this.ativ(est.dim(e.planejando ? 'Modo plano ligado.' : 'Modo plano desligado: o agente pode executar.')); break;
      case 'compactado': this.ativ(est.dim('Conversa ' + (e.modo === 'resumo' ? 'resumida' : 'enxugada') + ' para caber no contexto: ' + fmtTokens(e.antes) + ' → ' + fmtTokens(e.depois) + ' tokens.')); break;
      case 'entregas': this.ativ(est.green('✓ Entregue: ') + (e.arquivos || []).map((a: { caminho: string }) => a.caminho).join(', ')); break;
      case 'diagnosticos':
        if ((e.itens || []).length) this.ativ(est.yellow('! ' + e.itens.length + (e.itens.length === 1 ? ' problema' : ' problemas') + ' em ' + e.arquivo + ': ') +
          est.dim(e.itens.slice(0, 3).map((i: { linha: number; msg: string }) => 'linha ' + i.linha + ' ' + corta(i.msg, 80)).join(' | ')));
        break;
      case 'mcp-pendente': this.ativ(est.yellow('! Este projeto tem servidores MCP que ainda não foram permitidos: ') + (e.servidores || []).map((x: { nome: string }) => x.nome).join(', ') + est.dim('  (use /mcp)')); break;
      case 'erro': {
        this.fecharPensamento(); this.soltarResto(); this.novoTrecho();
        const txt = String(e.texto || '');
        if (txt === 'Parado por você.') { this.parado = true; this.ativ(est.dim(txt)); break; }   // nao e' falha: a pessoa pediu
        this.erro = txt; this.ativ(est.red('✗ ' + txt));
        break;
      }
      case 'desfeito': this.ativ(est.dim('Desfeito: ' + ((e.arquivos || []).join(', ') || 'nada') + ' voltou ao que era antes.')); break;
      case 'fim': this.fecharPensamento(); this.soltarResto(); this.novoTrecho(); this.parar(); this.mudancas = e.mudancas || []; break;
    }
  }

  private escreverLinhas(txt: string) {
    this.parar();
    let fence = false;
    for (const l of txt.split('\n')) {
      if (/^\s*```/.test(l)) { fence = !fence; this.escreverTexto(this.o.est.dim(l) + '\n'); }
      else if (fence) this.escreverTexto(this.o.est.gray('  ' + l) + '\n');
      else this.escreverTexto(mdLinha(l, this.o.est) + '\n');
    }
  }

  /* Fecha o giro e deixa o cursor numa linha limpa. */
  encerrar() {
    this.parar();
    this.soltarResto();
    if (!this.noInicio && this.o.streaming) { this.o.saida('\n'); this.noInicio = true; }
  }
}

export function faseObjetivo(f: string): string {
  return ({ active: 'ativo', paused: 'pausado', blocked: 'bloqueado', complete: 'cumprido' } as Record<string, string>)[f] || f;
}
