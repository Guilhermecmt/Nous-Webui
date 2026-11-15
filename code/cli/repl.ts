// A conversa interativa do `nous`: o laco de leitura, os comandos de barra e o
// rodape. Tudo passa pelo servico Nous Code (cliente.ts); aqui nao ha agente.
import fs from 'node:fs';
import path from 'node:path';
import { ErroApi, type Cliente, type Evento } from './cliente.ts';
import type { Io } from './io.ts';
import {
  ALCANCES, COMANDOS, ESFORCOS, MODOS, ROTULO_ALCANCE, ROTULO_ESFORCO, ROTULO_MODO, escolherItem, interpretar,
  normalizarAlcance, normalizarEsforco, normalizarModo, type Comando,
} from './comandos.ts';
import { completarLinha } from './completar.ts';
import { Renderizador, criarEstilo, fmtGb, fmtIdade, fmtTokens, formatarDiff, mdLinha, rodape, faseObjetivo, type Estilo } from './tela.ts';
import { executarTurno, type OpcTurno } from './turno.ts';

type Modelo = { nome: string; gb: number; ferramentas: boolean; pensa: boolean; provedor?: string };
type Info = { modelo: string; modo: string; alcance: string; raciocinio: string; tokens: number; limite: number; titulo: string; planejando: boolean;
  internet: boolean | null; mudados: number; objetivo: any };
type Prefs = { modelo?: string; raciocinio?: string; modo?: string; alcance?: string };

export type OpcRepl = { pasta: string; cliente: Cliente; io: Io; est?: Estilo; versao?: string; prefs?: Prefs; continuar?: boolean; pedidoInicial?: string };

const RANGO_ALCANCE: Record<string, number> = { projeto: 0, usuario: 1, computador: 2 };

export class Repl {
  cliente: Cliente;
  io: Io;
  est: Estilo;
  pasta: string;
  sessao: string | null = null;
  prefs: Prefs;
  info: Info | null = null;
  padrao = { modelo: 'qwen2.5-coder:14b', modo: 'perguntar', alcance: 'projeto' };
  private criada = false;                // a conversa foi aberta por este terminal
  private ultimoCtrlC = 0;
  private skillsCache: string[] | null = null;
  private modelosCache: Modelo[] = [];
  private versao: string;
  private sair = false;

  constructor(o: OpcRepl) {
    this.cliente = o.cliente; this.io = o.io; this.pasta = o.pasta;
    this.est = o.est ?? criarEstilo(o.io.tty);
    this.prefs = { ...(o.prefs || {}) };
    this.versao = o.versao || '';
    this.opc = o;
  }
  private opc: OpcRepl;

  /* ------------------------------------------------------------ saida */
  linha(s = '') { this.io.saida(s + '\n'); }
  aviso(s: string) { this.linha(this.est.yellow('! ') + s); }
  erro(s: string) { this.linha(this.est.red('✗ ') + s); }
  nota(s: string) { this.linha(this.est.dim(s)); }

  private erroDe(e: unknown): string {
    if (e instanceof ErroApi) return e.message;
    return e instanceof Error ? e.message : String(e);
  }

  async sim(pergunta: string, padraoSim = false): Promise<boolean> {
    this.io.saida(this.est.yellow('? ') + pergunta + ' ' + this.est.dim(padraoSim ? '[S/n]' : '[s/N]') + ' ');
    const k = await this.io.tecla(['s', 'n', 'y', 'enter']);
    const sim = k === 's' || k === 'y' || (k === 'enter' && padraoSim);
    this.io.saida((sim ? 's' : 'n') + '\n');
    return sim;
  }

  /* ------------------------------------------------------------ conversa */
  async carregarPadroes() {
    try {
      const h = await this.cliente.pedir('GET', '/health');
      if (h.modelo) this.padrao.modelo = h.modelo;
      if (h.versao && !this.versao) this.versao = h.versao;
      const a = await this.cliente.pedir('GET', '/ajustes');
      if (a.modo) this.padrao.modo = a.modo;
      if (a.alcance) this.padrao.alcance = a.alcance;
    } catch { /* usa os padroes de fabrica */ }
  }

  /* A conversa so' e' criada quando precisa (primeiro pedido ou comando que a usa):
   * abrir o terminal e sair sem falar nada nao deixa conversa vazia na lista. */
  async garantirSessao(): Promise<string> {
    if (this.sessao) return this.sessao;
    const corpo: Record<string, unknown> = { pasta: this.pasta };
    if (this.prefs.modelo) corpo.modelo = this.prefs.modelo;
    if (this.prefs.alcance) corpo.alcance = this.prefs.alcance;
    const r = await this.cliente.pedir('POST', '/sessoes', corpo);
    this.sessao = r.id; this.criada = true;
    const aj: Record<string, unknown> = {};
    if (this.prefs.modo) aj.modo = this.prefs.modo;
    if (this.prefs.raciocinio) aj.raciocinio = this.prefs.raciocinio;
    if (Object.keys(aj).length) await this.cliente.pedir('POST', '/sessao/ajustes', { id: this.sessao, ...aj });
    await this.atualizar();
    return this.sessao!;
  }

  async atualizar(): Promise<Info | null> {
    if (!this.sessao) return (this.info = null);
    const s = await this.cliente.pedir('GET', '/sessao?id=' + this.sessao);
    this.info = { modelo: s.modelo, modo: s.modo, alcance: s.alcance, raciocinio: s.raciocinio, tokens: s.tokens || 0, limite: s.limite || 0, titulo: s.titulo,
      planejando: !!s.planejando, internet: s.internet, mudados: (s.mudancas || []).length, objetivo: s.objetivo };
    return this.info;
  }

  /* Muda um ajuste na conversa; sem conversa ainda, guarda para quando ela nascer. */
  private async ajustar(corpo: Record<string, unknown>, prefs: Prefs = {}) {
    Object.assign(this.prefs, prefs);
    if (!this.sessao) return;
    await this.cliente.pedir('POST', '/sessao/ajustes', { id: this.sessao, ...corpo });
    await this.atualizar();
  }

  private atual() {
    return {
      modelo: this.info?.modelo ?? this.prefs.modelo ?? this.padrao.modelo,
      modo: this.info?.modo ?? this.prefs.modo ?? this.padrao.modo,
      alcance: this.info?.alcance ?? this.prefs.alcance ?? this.padrao.alcance,
      raciocinio: this.info?.raciocinio ?? this.prefs.raciocinio ?? 'auto',
    };
  }

  /* Remove a conversa que este terminal abriu e ninguem usou. */
  private async limparVazia() {
    if (!this.sessao || !this.criada) return;
    try {
      const s = await this.cliente.pedir('GET', '/sessao?id=' + this.sessao);
      if (!(s.eventos || []).some((e: Evento) => e.t === 'voce')) await this.cliente.pedir('POST', '/sessao/apagar', { id: this.sessao });
    } catch { /* fica */ }
  }

  /* ------------------------------------------------------------ pedido ao agente */
  async enviar(texto: string, opc: OpcTurno = {}) {
    let id: string;
    try { id = await this.garantirSessao(); } catch (e) { this.erro(this.erroDe(e)); return; }
    const ren = new Renderizador({ saida: (s) => this.io.saida(s), atividade: (s) => this.io.atividade(s), est: this.est, tty: this.io.tty, streaming: true, largura: () => this.io.largura() });
    await executarTurno(this.cliente, id, texto, this.io, ren, { aoSempreArquivo: async () => {
      await this.ajustar({ modo: 'editar' }, { modo: 'editar' });
      this.nota('  Modo mudado para editar: mudanças dentro do projeto não pedem mais OK.');
    }, ...opc });
    await this.mostrarRodape();
  }

  async mostrarRodape() {
    try {
      const i = await this.atualizar();
      if (i) this.linha('\n' + rodape({ modelo: i.modelo, raciocinio: i.raciocinio, modo: i.modo, tokens: i.tokens, limite: i.limite, mudados: i.mudados }, this.est));
    } catch { /* sem rodape */ }
  }

  /* ------------------------------------------------------------ comandos */
  async skills(): Promise<string[]> {
    if (this.skillsCache) return this.skillsCache;
    try {
      const l = await this.cliente.pedir('GET', '/skills?pasta=' + encodeURIComponent(this.pasta));
      this.skillsCache = l.filter((x: { usuario: boolean }) => x.usuario).map((x: { nome: string }) => x.nome);
    } catch { this.skillsCache = []; }
    return this.skillsCache!;
  }

  async modelos(refrescar = false): Promise<Modelo[]> {
    if (!this.modelosCache.length || refrescar) {
      try {
        const r = await this.cliente.pedir('GET', '/modelos');
        this.modelosCache = r.modelos || [];
        if (r.padrao) this.padrao.modelo = r.padrao;
      } catch (e) { this.erro(this.erroDe(e)); }
    }
    return this.modelosCache;
  }

  async executar(c: Comando, arg: string): Promise<void> {
    switch (c.nome) {
      case 'ajuda': return this.cmdAjuda();
      case 'modelo': return this.cmdModelo(arg);
      case 'effort': return this.cmdEffort(arg);
      case 'modo': return this.cmdModo(arg);
      case 'alcance': return this.cmdAlcance(arg);
      case 'plano': return this.cmdPlano(arg);
      case 'objetivo': return this.cmdObjetivo(arg);
      case 'compactar': return this.cmdCompactar();
      case 'contexto': return this.cmdContexto();
      case 'novo': return this.cmdNovo();
      case 'conversas': return this.cmdConversas(arg);
      case 'desfazer': return this.cmdDesfazer(arg);
      case 'mudancas': return this.cmdMudancas(arg);
      case 'exportar': return this.cmdExportar(arg);
      case 'mcp': return this.cmdMcp(arg);
      case 'skills': return this.cmdSkills();
      case 'internet': return this.cmdInternet();
      case 'ide': return this.cmdIde();
      case 'padrao': return this.cmdPadrao(arg);
      case 'sair': this.sair = true; return;
    }
  }

  cmdAjuda() {
    const e = this.est;
    this.linha(e.bold('Comandos'));
    const larg = Math.max(...COMANDOS.map((c) => ('/' + c.nome + (c.arg ? ' ' + c.arg : '')).length));
    for (const c of COMANDOS) {
      const cab = '/' + c.nome + (c.arg ? ' ' + c.arg : '');
      const ap = c.apelidos.filter((a) => /^[a-z]/.test(a) && a === a.normalize('NFD').replace(/\p{M}/gu, '')).slice(0, 3);
      this.linha('  ' + e.cyan(cab.padEnd(larg)) + '  ' + c.ajuda + (ap.length ? e.dim('  (' + ap.map((a) => '/' + a).join(' ') + ')') : ''));
    }
    this.linha();
    this.linha('  ' + e.cyan('@arquivo'.padEnd(larg)) + '  Anexa o arquivo ao pedido (Tab completa)');
    this.linha('  ' + e.cyan('/skill'.padEnd(larg)) + '  Usa uma skill do projeto, por exemplo /revisar');
    this.linha('  ' + e.cyan('\\ no fim da linha'.padEnd(larg)) + '  Continua o pedido na linha de baixo (colar vários trechos também funciona)');
    this.linha('  ' + e.cyan('Esc / Ctrl+C'.padEnd(larg)) + '  Interrompe a resposta; Ctrl+C duas vezes com a linha vazia sai');
  }

  /* Lista numerada; devolve o item escolhido (ou null). */
  private async escolher<T>(titulo: string, itens: T[], desenho: (i: T, n: number) => string, nomeDe: (i: T) => string, pergunta: string): Promise<T | null> {
    this.linha(this.est.bold(titulo));
    itens.forEach((i, n) => this.linha('  ' + desenho(i, n + 1)));
    const l = await this.io.linha(this.est.yellow('? ') + pergunta + this.est.dim(' (número ou nome; Enter cancela) ') + '› ');
    if (l.t !== 'linha' || !l.texto.trim()) { this.nota('Nada mudou.'); return null; }
    const r = escolherItem(itens, l.texto, nomeDe);
    if (!r.item) { this.erro(r.erro || 'escolha inválida'); return null; }
    return r.item;
  }

  async cmdModelo(arg: string) {
    const lista = await this.modelos(true);
    const atual = this.atual().modelo;
    if (!lista.length) {
      // sem lista (Ollama fora do ar): aceita o nome digitado
      if (!arg) { this.aviso('Não consegui listar os modelos. O Ollama está aberto? Use /modelo <nome> para trocar mesmo assim.'); return; }
      await this.ajustar({ modelo: arg }, { modelo: arg });
      this.linha('Modelo: ' + this.est.bold(arg));
      return;
    }
    const desenho = (m: Modelo, n: number) => {
      const marca = m.nome === atual ? this.est.green('●') : ' ';
      const flags = [m.ferramentas ? this.est.green('ferramentas') : this.est.red('sem ferramentas'), m.pensa ? this.est.cyan('raciocínio') : ''].filter(Boolean).join(' ');
      return marca + ' ' + String(n).padStart(2) + '  ' + m.nome.padEnd(34) + this.est.dim(fmtGb(m.gb).padStart(8)) + '  ' + flags;
    };
    let escolhido: Modelo | null = null;
    if (arg) {
      const r = escolherItem(lista, arg, (m) => m.nome);
      if (!r.item) { this.erro(r.erro || 'modelo desconhecido'); this.nota('Digite /modelo para ver a lista.'); return; }
      escolhido = r.item;
    } else escolhido = await this.escolher('Modelos instalados', lista, desenho, (m) => m.nome, 'Qual modelo?');
    if (!escolhido) return;
    if (!escolhido.ferramentas && !escolhido.provedor) this.aviso(escolhido.nome + ' não anuncia ferramentas: o agente pode não conseguir ler nem editar arquivos.');
    await this.ajustar({ modelo: escolhido.nome }, { modelo: escolhido.nome });
    this.linha('Modelo: ' + this.est.bold(escolhido.nome) + (escolhido.pensa ? '' : this.est.dim('  (este modelo não tem modo de raciocínio)')));
  }

  async cmdEffort(arg: string) {
    let v: string | null = null;
    if (arg) {
      v = normalizarEsforco(arg);
      if (!v) { this.erro('Raciocínio desconhecido: ' + arg + '. Use auto, desligado, baixo, medio ou alto (ou off, low, medium, high).'); return; }
    } else {
      const atual = this.atual().raciocinio;
      const it = await this.escolher('Raciocínio do modelo', [...ESFORCOS], (x, n) => (x === atual ? this.est.green('●') : ' ') + ' ' + n + '  ' + x.padEnd(10) + this.est.dim(ROTULO_ESFORCO[x]), (x) => x, 'Qual nível?');
      if (!it) return;
      v = it;
    }
    await this.ajustar({ raciocinio: v }, { raciocinio: v });
    this.linha('Raciocínio: ' + this.est.bold(ROTULO_ESFORCO[v]));
  }

  async cmdModo(arg: string) {
    let v: string | null = null;
    const atual = this.atual().modo;
    if (arg) {
      v = normalizarModo(arg);
      if (!v) { this.erro('Modo desconhecido: ' + arg + '. Use leitura, perguntar, editar ou total.'); return; }
    } else {
      const it = await this.escolher('Permissões', [...MODOS], (x, n) => (x === atual ? this.est.green('●') : ' ') + ' ' + n + '  ' + x.padEnd(10) + this.est.dim(ROTULO_MODO[x]), (x) => x, 'Qual modo?');
      if (!it) return;
      v = it;
    }
    if (v === 'total' && atual !== 'total') {
      this.aviso('Acesso total: o agente muda arquivos e roda comandos sem pedir licença. Um modelo local pode errar, e você se responsabiliza pelo que ele fizer.');
      if (!(await this.sim('Liberar?'))) { this.nota('Nada mudou.'); return; }
    }
    await this.ajustar({ modo: v }, { modo: v });
    this.linha('Modo: ' + this.est.bold(ROTULO_MODO[v]));
  }

  async cmdAlcance(arg: string) {
    let v: string | null = null;
    const atual = this.atual().alcance;
    if (arg) {
      v = normalizarAlcance(arg);
      if (!v) { this.erro('Alcance desconhecido: ' + arg + '. Use projeto, usuario ou computador.'); return; }
    } else {
      const it = await this.escolher('Alcance do agente', [...ALCANCES], (x, n) => (x === atual ? this.est.green('●') : ' ') + ' ' + n + '  ' + x.padEnd(11) + this.est.dim(ROTULO_ALCANCE[x]), (x) => x, 'Qual alcance?');
      if (!it) return;
      v = it;
    }
    if (RANGO_ALCANCE[v] > RANGO_ALCANCE[atual]) {
      this.aviso(v === 'usuario'
        ? 'O agente vai poder ler e mudar arquivos em toda a sua pasta de usuário (Documentos, Downloads, Área de Trabalho…). Mudanças fora do projeto continuam pedindo OK, a não ser no acesso total.'
        : 'O agente vai poder ler e mudar arquivos em qualquer lugar do computador que o seu usuário do Windows alcança. Você se responsabiliza pelo que ele fizer.');
      if (!(await this.sim('Liberar?'))) { this.nota('Nada mudou.'); return; }
    }
    try { await this.ajustar({ alcance: v }, { alcance: v }); } catch (e) { this.erro(this.erroDe(e)); return; }
    this.linha('Alcance: ' + this.est.bold(ROTULO_ALCANCE[v]));
  }

  async cmdPlano(arg: string) {
    const sair = /^(sair|off|desligar|desligado|exit)$/i.test(arg);
    try { await this.garantirSessao(); await this.ajustar({ planejando: !sair }); } catch (e) { this.erro(this.erroDe(e)); return; }
    if (sair) { this.linha('Modo plano desligado.'); return; }
    if (arg) { this.nota('Modo plano ligado: o agente investiga e propõe o plano para você aprovar.'); await this.enviar(arg); }
    else this.linha('Modo plano ligado: o próximo pedido vira um plano para você aprovar.');
  }

  async cmdObjetivo(arg: string) {
    try { await this.garantirSessao(); } catch (e) { this.erro(this.erroDe(e)); return; }
    const o = this.info?.objetivo;
    if (!arg) {
      if (!o) this.linha('Sem objetivo. Use /objetivo <texto>, por exemplo: /objetivo todos os testes passando');
      else this.linha(this.est.magenta('◎ ') + o.objective + this.est.dim('  (' + faseObjetivo(o.phase) + ', rodada ' + o.roundsStarted + '/' + o.maxGoalRounds + ')'));
      return;
    }
    if (/^(pausar|retomar)$/i.test(arg)) {
      if (!o) { this.aviso('Não há objetivo.'); return; }
      await this.ajustar({ objetivoAcao: arg.toLowerCase() });
      this.linha('Objetivo ' + (arg.toLowerCase() === 'pausar' ? 'pausado.' : 'retomado.'));
      if (arg.toLowerCase() === 'retomar') await this.enviar('Continue o objetivo.');
      return;
    }
    if (/^(limpar|apagar|remover)$/i.test(arg)) { await this.ajustar({ objetivo: '' }); this.linha('Objetivo removido.'); return; }
    await this.ajustar({ objetivo: arg });
    await this.enviar('Objetivo: ' + arg);
  }

  async cmdCompactar() {
    if (!this.sessao) { this.nota('Ainda não há conversa para compactar.'); return; }
    this.nota('Compactando…');
    try {
      const r = await this.cliente.pedir('POST', '/compactar', { id: this.sessao });
      if (!r.evento) this.nota('A conversa ainda é curta: nada a compactar.');
      else { this.linha(this.est.dim('Conversa ' + (r.evento.modo === 'resumo' ? 'resumida' : 'enxugada') + ': ' + fmtTokens(r.evento.antes) + ' → ' + fmtTokens(r.evento.depois) + ' tokens.')); await this.atualizar(); }
    } catch (e) { this.erro(this.erroDe(e)); }
  }

  async cmdContexto() {
    const e = this.est;
    const a = this.atual();
    const i = this.sessao ? await this.atualizar().catch(() => null) : null;
    const tok = i?.tokens || 0, lim = i?.limite || 0;
    const pct = lim ? Math.min(100, Math.round((tok / lim) * 100)) : 0;
    const cheio = Math.round(pct / 5);
    const barra = '█'.repeat(cheio) + '░'.repeat(20 - cheio);
    const l = (k: string, v: string) => this.linha('  ' + e.dim(k.padEnd(11)) + v);
    this.linha(e.bold('Contexto'));
    l('modelo', a.modelo);
    l('raciocínio', ROTULO_ESFORCO[a.raciocinio] || a.raciocinio);
    l('modo', a.modo + e.dim(' - ' + ROTULO_MODO[a.modo]));
    l('alcance', a.alcance + e.dim(' - ' + ROTULO_ALCANCE[a.alcance]));
    l('pasta', this.pasta);
    if (i) {
      l('conversa', i.titulo + e.dim('  (' + this.sessao + ')'));
      l('contexto', (pct >= 80 ? e.yellow(barra) : e.cyan(barra)) + ' ' + (tok ? fmtTokens(tok) + ' de ' + fmtTokens(lim) + ' tokens (' + pct + '%)' : 'vazio'));
      if (i.planejando) l('plano', 'ligado');
      if (i.internet !== null) l('internet', i.internet ? 'liberada' : 'bloqueada');
      if (i.mudados) l('mudanças', i.mudados + (i.mudados === 1 ? ' arquivo' : ' arquivos') + e.dim('  (/mudancas)'));
    } else l('conversa', e.dim('ainda não começou'));
  }

  async cmdNovo() {
    await this.limparVazia();
    this.sessao = null; this.info = null; this.criada = false;
    this.linha('Conversa nova. ' + this.est.dim('A anterior continua em /conversas.'));
  }

  async cmdConversas(arg: string) {
    let lista: { id: string; titulo: string; atualizado: number; rodando: boolean }[] = [];
    try { lista = await this.cliente.pedir('GET', '/sessoes?pasta=' + encodeURIComponent(this.pasta)); } catch (e) { this.erro(this.erroDe(e)); return; }
    lista = lista.slice(0, 20);
    if (!lista.length) { this.nota('Nenhuma conversa nesta pasta ainda.'); return; }
    let it: typeof lista[number] | null = null;
    if (arg) {
      const r = escolherItem(lista, arg, (x) => x.titulo);
      if (!r.item) { this.erro(r.erro || 'conversa não encontrada'); return; }
      it = r.item;
    } else {
      it = await this.escolher('Conversas desta pasta', lista, (x, n) => (x.id === this.sessao ? this.est.green('●') : ' ') + ' ' + String(n).padStart(2) + '  ' +
        x.titulo.slice(0, 56).padEnd(56) + this.est.dim(' ' + fmtIdade(x.atualizado)) + (x.rodando ? this.est.yellow(' (rodando)') : ''), (x) => x.titulo, 'Retomar qual?');
    }
    if (!it) return;
    if (it.rodando) { this.aviso('Essa conversa está trabalhando agora (talvez na janela do Nous Code). Espere ela terminar.'); return; }
    await this.limparVazia();
    this.sessao = it.id; this.criada = false;
    await this.retomar();
  }

  /* --continuar: abre a conversa mais recente da pasta que nao esteja trabalhando; as opcoes da linha de comando valem para ela. */
  async abrirUltima(): Promise<boolean> {
    try {
      const l = await this.cliente.pedir('GET', '/sessoes?pasta=' + encodeURIComponent(this.pasta));
      const ultima = l.find((x: { rodando: boolean }) => !x.rodando);
      if (!ultima) return false;
      this.sessao = ultima.id; this.criada = false;
      const aj: Record<string, unknown> = {};
      if (this.prefs.modelo) aj.modelo = this.prefs.modelo;
      if (this.prefs.modo) aj.modo = this.prefs.modo;
      if (this.prefs.raciocinio) aj.raciocinio = this.prefs.raciocinio;
      if (this.prefs.alcance) aj.alcance = this.prefs.alcance;
      if (Object.keys(aj).length) await this.cliente.pedir('POST', '/sessao/ajustes', { id: this.sessao, ...aj });
      await this.atualizar();
      return true;
    } catch (e) { this.erro(this.erroDe(e)); return false; }
  }

  /* Mostra o fim da conversa que acabou de ser aberta. */
  async retomar() {
    if (!this.sessao) return;
    const s = await this.cliente.pedir('GET', '/sessao?id=' + this.sessao);
    await this.atualizar();
    this.linha(this.est.bold('Conversa retomada: ') + s.titulo);
    const evs: Evento[] = s.eventos || [];
    const vozes = evs.map((e, i) => (e.t === 'voce' ? i : -1)).filter((i) => i >= 0);
    const desde = vozes.length > 2 ? vozes[vozes.length - 2] : 0;
    if (desde > 0) this.nota('  … ' + (vozes.length - 2) + ' pedidos anteriores');
    for (const e of evs.slice(desde)) {
      if (e.t === 'voce') this.linha('\n' + this.est.bold(this.est.magenta('❯ ')) + String(e.texto).split('\n')[0].slice(0, 200));
      else if (e.t === 'resposta') for (const l of String(e.texto).split('\n')) this.linha(mdLinha(l, this.est));
      else if (e.t === 'ferramenta') this.linha(this.est.dim('  ● ' + e.resumo));
    }
    if (this.info) this.linha('\n' + rodape({ modelo: this.info.modelo, raciocinio: this.info.raciocinio, modo: this.info.modo, tokens: this.info.tokens, limite: this.info.limite, mudados: this.info.mudados }, this.est));
  }

  private async mudancasDaConversa() {
    const s = await this.cliente.pedir('GET', '/sessao?id=' + this.sessao);
    return { mudancas: (s.mudancas || []) as { arquivo: string; novo: boolean; mais: number; menos: number }[], eventos: (s.eventos || []) as Evento[] };
  }

  async cmdDesfazer(arg: string) {
    if (!this.sessao) { this.nota('Nada a desfazer: a conversa ainda não mudou arquivos.'); return; }
    const { mudancas } = await this.mudancasDaConversa();
    if (!mudancas.length) { this.nota('O agente ainda não mudou arquivos nesta conversa.'); return; }
    let alvo: string | undefined;
    if (arg) {
      const r = escolherItem(mudancas, arg, (m) => m.arquivo);
      if (!r.item) { this.erro(r.erro || 'arquivo não encontrado'); return; }
      alvo = r.item.arquivo;
    }
    for (const m of mudancas.filter((x) => !alvo || x.arquivo === alvo)) this.linha('  ' + (m.novo ? this.est.green('novo ') : '      ') + m.arquivo + ' ' + this.est.green('+' + m.mais) + ' ' + this.est.red('−' + m.menos));
    if (!(await this.sim(alvo ? 'Voltar ' + alvo + ' ao que era antes desta conversa?' : 'Voltar todos esses arquivos ao que eram antes desta conversa?'))) { this.nota('Nada mudou.'); return; }
    try {
      const r = await this.cliente.pedir('POST', '/desfazer', { id: this.sessao, arquivo: alvo });
      this.linha('Desfeito: ' + ((r.desfeitos || []).join(', ') || 'nada'));
      await this.atualizar();
    } catch (e) { this.erro(this.erroDe(e)); }
  }

  async cmdMudancas(arg: string) {
    if (!this.sessao) { this.nota('O agente ainda não mudou arquivos.'); return; }
    const { mudancas, eventos } = await this.mudancasDaConversa();
    if (!mudancas.length) { this.nota('O agente ainda não mudou arquivos nesta conversa.'); return; }
    let alvo = '';
    if (arg) {
      const r = escolherItem(mudancas, arg, (m) => m.arquivo);
      if (!r.item) { this.erro(r.erro || 'arquivo não encontrado'); return; }
      alvo = r.item.arquivo;
    }
    this.linha(this.est.bold('Arquivos mudados nesta conversa'));
    for (const m of mudancas) this.linha('  ' + (m.novo ? this.est.green('novo ') : '      ') + m.arquivo + ' ' + this.est.green('+' + m.mais) + ' ' + this.est.red('−' + m.menos));
    if (!alvo) { this.nota('  /mudancas <arquivo> mostra o diff.'); return; }
    // o diff de cada edicao do arquivo, na ordem em que o agente fez
    const dos = diffsDoArquivo(eventos, alvo);
    if (!dos.length) { this.nota('  (sem diff guardado para ' + alvo + ')'); return; }
    this.linha();
    for (const d of dos) this.linha(formatarDiff(d, this.est, 80, '  '));
  }

  async cmdExportar(arg: string) {
    if (!this.sessao) { this.nota('Ainda não há conversa para exportar.'); return; }
    try {
      const md = await this.cliente.texto('/sessao/exportar?id=' + this.sessao);
      const titulo = this.info?.titulo || 'conversa';
      const nome = arg || ('conversa-' + (titulo.replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-').toLowerCase().slice(0, 40) || 'nous') + '.md');
      const destino = path.resolve(this.pasta, nome.endsWith('.md') ? nome : nome + '.md');
      fs.writeFileSync(destino, md, 'utf8');
      this.linha('Conversa salva em ' + this.est.bold(destino));
    } catch (e) { this.erro(this.erroDe(e)); }
  }

  async cmdMcp(arg: string) {
    let lista: { nome: string; origem: string; aprovado: boolean; comando: string }[] = [];
    try { lista = await this.cliente.pedir('GET', '/mcp?pasta=' + encodeURIComponent(this.pasta)); } catch (e) { this.erro(this.erroDe(e)); return; }
    const m = /^(permitir|desligar|allow|deny)\s*(.*)$/i.exec(arg);
    if (m) {
      const sim = /^(permitir|allow)$/i.test(m[1]);
      let alvos = lista;
      if (m[2]) {
        const r = escolherItem(lista, m[2], (x) => x.nome);
        if (!r.item) { this.erro(r.erro || 'servidor não encontrado'); return; }
        alvos = [r.item];
      } else if (sim) alvos = lista.filter((x) => !x.aprovado);
      if (sim) {
        this.aviso('Servidores MCP rodam programas definidos no projeto. Só permita se você confia em quem fez o projeto.');
        for (const a of alvos) this.linha('  ' + a.nome + this.est.dim(': ' + a.comando));
        if (!(await this.sim('Permitir?'))) { this.nota('Nada mudou.'); return; }
      }
      for (const a of alvos) await this.cliente.pedir('POST', '/mcp/aprovar', { pasta: this.pasta, nome: a.nome, sim });
      this.linha(sim ? 'Permitido: as ferramentas entram no próximo pedido.' : 'Desligado.');
      return;
    }
    if (!lista.length) { this.nota('Este projeto não tem servidores MCP (.mcp.json ou .nous/mcp.json).'); return; }
    this.linha(this.est.bold('Servidores MCP deste projeto'));
    for (const x of lista) this.linha('  ' + (x.aprovado ? this.est.green('● permitido') : this.est.yellow('○ pendente ')) + '  ' + x.nome + this.est.dim('  ' + x.comando.slice(0, 80)));
    if (lista.some((x) => !x.aprovado)) this.nota('  /mcp permitir <nome> libera um servidor; /mcp desligar <nome> tira.');
  }

  async cmdSkills() {
    this.skillsCache = null;
    let todas: { nome: string; descricao: string; usuario: boolean }[] = [];
    try { todas = await this.cliente.pedir('GET', '/skills?pasta=' + encodeURIComponent(this.pasta)); } catch (e) { this.erro(this.erroDe(e)); return; }
    const l = todas.filter((x) => x.usuario);
    if (!l.length) { this.nota('Nenhuma skill neste projeto nem na sua pasta (.nous/skills).'); return; }
    this.linha(this.est.bold('Skills'));
    for (const x of l) this.linha('  ' + this.est.cyan(('/' + x.nome).padEnd(24)) + (x.descricao || '').slice(0, 80));
    this.nota('  Escreva /nome-da-skill no pedido para usar.');
  }

  async cmdInternet() {
    try {
      await this.garantirSessao();
      const novo = this.info?.internet !== true;
      await this.ajustar({ internet: novo });
      this.linha(novo ? 'Internet liberada nesta conversa.' : 'Internet bloqueada nesta conversa.');
    } catch (e) { this.erro(this.erroDe(e)); }
  }

  async cmdIde() {
    try {
      const id = await this.garantirSessao();
      const r = await this.cliente.pedir('POST', '/abrir-janela', { pasta: this.pasta, sessao: id });
      this.linha('Abri esta conversa na janela do Nous Code. ' + this.est.dim(r.url || ''));
    } catch (e) { this.erro(this.erroDe(e)); }
  }

  async cmdPadrao(arg: string) {
    let a: { modo: string; alcance: string };
    try { a = await this.cliente.pedir('GET', '/ajustes'); } catch (e) { this.erro(this.erroDe(e)); return; }
    const m = /^(modo|alcance)\s+(\S+)$/i.exec(arg);
    if (!m) {
      this.linha(this.est.bold('Padrão das conversas novas'));
      this.linha('  modo     ' + a.modo + this.est.dim(' - ' + ROTULO_MODO[a.modo]));
      this.linha('  alcance  ' + a.alcance + this.est.dim(' - ' + ROTULO_ALCANCE[a.alcance]));
      this.nota('  /padrao modo <valor> ou /padrao alcance <valor> muda (vale também na janela do Nous Code).');
      return;
    }
    const tipo = m[1].toLowerCase();
    const v = tipo === 'modo' ? normalizarModo(m[2]) : normalizarAlcance(m[2]);
    if (!v) { this.erro('Valor desconhecido: ' + m[2]); return; }
    const alarga = tipo === 'modo' ? v === 'total' && a.modo !== 'total' : RANGO_ALCANCE[v] > RANGO_ALCANCE[a.alcance];
    if (alarga) {
      this.aviso(tipo === 'modo' ? 'Toda conversa nova começará em acesso total: o agente muda arquivos e roda comandos sem pedir licença.'
        : 'Toda conversa nova poderá abrir ' + ROTULO_ALCANCE[v] + '.');
      if (!(await this.sim('Liberar?'))) { this.nota('Nada mudou.'); return; }
    }
    await this.cliente.pedir('POST', '/ajustes', { [tipo]: v });
    this.linha('Padrão de ' + tipo + ': ' + this.est.bold(v));
  }

  /* ------------------------------------------------------------ laco */
  private cabecalho() {
    const e = this.est;
    const a = this.atual();
    this.linha();
    this.linha(' ' + e.bold(e.magenta('Nous')) + e.dim(' no terminal' + (this.versao ? '  ·  Nous Code ' + this.versao : '')));
    this.linha(' ' + e.dim('pasta  ') + this.pasta);
    this.linha(' ' + e.dim('modelo ') + a.modelo + e.dim(' · raciocínio ' + (ROTULO_ESFORCO[a.raciocinio] || a.raciocinio) + ' · modo ' + a.modo + ' · alcance ' + a.alcance));
    this.linha(' ' + e.dim('/ajuda lista os comandos · @arquivo anexa · Esc interrompe · Ctrl+C duas vezes sai'));
    this.linha();
  }

  private promptTexto() {
    const plano = this.info?.planejando ? this.est.cyan('plano ') : '';
    return plano + this.est.bold(this.est.magenta('❯')) + ' ';
  }

  /* Uma linha lida: comando, skill desconhecida ou pedido. */
  async tratar(texto: string): Promise<void> {
    const l = interpretar(texto);
    if (l.tipo === 'vazia') return;
    if (l.tipo === 'comando') {
      try { await this.executar(l.comando, l.arg); } catch (e) { this.erro(this.erroDe(e)); }
      return;
    }
    if (l.tipo === 'desconhecido') {
      const sk = await this.skills();
      if (sk.some((s) => s.toLowerCase() === l.nome.toLowerCase())) { await this.enviar(l.texto); return; }
      const parecidos = COMANDOS.map((c) => c.nome).filter((n) => n.startsWith(l.nome.slice(0, 2).toLowerCase()));
      this.erro('Comando desconhecido: /' + l.nome + '.' + (parecidos.length ? ' Quis dizer ' + parecidos.slice(0, 3).map((n) => '/' + n).join(', ') + '?' : '') + this.est.dim(' (/ajuda lista os comandos)'));
      return;
    }
    await this.enviar(l.texto);
  }

  async rodar(): Promise<number> {
    await this.carregarPadroes();
    if (this.opc.continuar) {
      if (!(await this.abrirUltima())) this.aviso('Não há conversa anterior nesta pasta: começando uma nova.');
    }
    if (this.sessao) { try { await this.retomar(); } catch (e) { this.erro(this.erroDe(e)); } }
    else this.cabecalho();

    if (this.opc.pedidoInicial) await this.tratar(this.opc.pedidoInicial);

    while (!this.sair) {
      this.io.saida('\n');
      const l = await this.io.linha(this.promptTexto(), (linha) => completarLinha(linha, {
        pasta: this.pasta, skills: () => this.skillsCache || [], modelos: () => this.modelosCache.map((m) => m.nome) }));
      if (l.t === 'fim') { this.linha(); break; }
      if (l.t === 'ctrl-c') {
        const agora = Date.now();
        if (l.texto) { this.nota('(linha descartada)'); this.ultimoCtrlC = 0; continue; }
        if (agora - this.ultimoCtrlC < 2500) break;
        this.ultimoCtrlC = agora;
        this.nota('Aperte Ctrl+C de novo para sair (ou /sair).');
        continue;
      }
      this.ultimoCtrlC = 0;
      const texto = l.texto.trim();
      if (!texto) continue;
      this.io.guardar(texto);
      if (!this.skillsCache) void this.skills();   // aquece o Tab das skills
      await this.tratar(texto);
    }
    await this.limparVazia();
    return 0;
  }
}

/* Os diffs de um arquivo, na ordem das edicoes do agente (do historico da conversa). */
export function diffsDoArquivo(eventos: Evento[], arquivo: string): string[] {
  const norm = (p: unknown) => String(p ?? '').replace(/\\/g, '/').replace(/^\.\//, '');
  const alvo = norm(arquivo);
  const ids = new Set<string>();
  for (const e of eventos) {
    if (e.t === 'ferramenta' && /^(edit|write)$/.test(String(e.nome)) && norm(e.args?.file_path) === alvo) ids.add(String(e.id));
  }
  return eventos.filter((e) => e.t === 'resultado' && e.diff && ids.has(String(e.id))).map((e) => String(e.diff));
}
