// A entrada e a saida do terminal. O resto do CLI so' fala com a interface
// `Io`, entao os testes trocam o terminal de verdade por um roteiro.
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';

export type Leitura = { t: 'linha'; texto: string } | { t: 'ctrl-c'; texto: string } | { t: 'fim' };
export type Completador = (linha: string) => [string[], string];

export interface Io {
  tty: boolean;
  largura(): number;
  saida(s: string): void;            // stdout: a resposta
  atividade(s: string): void;        // ferramentas, avisos (stderr no modo -p)
  /* Uma tecla entre `validas` (minusculas); 'esc' quando a pessoa aperta Esc ou Ctrl+C. */
  tecla(validas: string[]): Promise<string>;
  /* Uma linha (ou varias, com \ no fim ou colando). */
  linha(prompt: string, completar?: Completador): Promise<Leitura>;
  /* Esc ou Ctrl+C enquanto o agente trabalha. Devolve quem desliga a escuta. */
  aoInterromper(cb: () => void): () => void;
  historico(): string[];
  guardar(linha: string): void;
}

const MAX_HIST = 500;

export class IoTerminal implements Io {
  tty: boolean;
  private hist: string[] = [];       // do mais novo para o mais antigo
  private arqHist: string;
  private perguntando = false;
  private escuta: (() => void) | null = null;
  private onTecla: ((s: string, k: readline.Key) => void) | null = null;

  private entrada: NodeJS.ReadStream;
  private sai: NodeJS.WriteStream;

  constructor(arqHistorico: string, entrada: NodeJS.ReadStream = process.stdin, sai: NodeJS.WriteStream = process.stdout, err: NodeJS.WriteStream = process.stderr) {
    this.entrada = entrada; this.sai = sai;
    this.tty = !!entrada.isTTY && !!sai.isTTY;
    this.arqHist = arqHistorico;
    try {
      this.hist = fs.readFileSync(arqHistorico, 'utf8').split('\n').filter(Boolean).map((l) => { try { return String(JSON.parse(l)); } catch { return ''; } })
        .filter(Boolean).reverse().slice(0, MAX_HIST);
    } catch { /* primeira vez */ }
    for (const f of [sai, err]) f.on('error', () => { /* pipe fechado: ignora */ });
  }

  largura() { return this.sai.columns || 100; }
  saida(s: string) { this.sai.write(s); }
  atividade(s: string) { this.sai.write(s); }
  historico() { return this.hist; }

  guardar(linha: string) {
    const l = linha.replace(/\s*\n\s*/g, ' ').trim();
    if (!l) return;
    this.hist = [l, ...this.hist.filter((x) => x !== l)].slice(0, MAX_HIST);
    try {
      fs.mkdirSync(path.dirname(this.arqHist), { recursive: true });
      fs.appendFileSync(this.arqHist, JSON.stringify(l) + '\n');
    } catch { /* sem historico em disco: segue */ }
  }

  /* Reescreve o arquivo sem repeticao quando ele cresceu demais. */
  compactarHistorico() {
    try {
      const n = fs.readFileSync(this.arqHist, 'utf8').split('\n').filter(Boolean).length;
      if (n > MAX_HIST * 2) fs.writeFileSync(this.arqHist, [...this.hist].reverse().map((l) => JSON.stringify(l)).join('\n') + '\n');
    } catch { /* nada a fazer */ }
  }

  linha(prompt: string, completar?: Completador): Promise<Leitura> {
    this.perguntando = true;
    return new Promise((resolve) => {
      const rl = readline.createInterface({ input: this.entrada, output: this.sai, terminal: this.tty, history: this.hist.slice(), historySize: MAX_HIST,
        prompt, removeHistoryDuplicates: true, completer: completar ? (l: string) => completar(l) : undefined });
      const acc: string[] = [];
      let feito = false, timer: NodeJS.Timeout | null = null;
      const fim = (r: Leitura) => {
        if (feito) return;
        feito = true;
        if (timer) clearTimeout(timer);
        this.perguntando = false;
        rl.close();
        this.retomarEscuta();
        resolve(r);
      };
      rl.on('line', (l) => {
        if (timer) { clearTimeout(timer); timer = null; }
        if (l.endsWith('\\')) {            // continua na proxima linha
          acc.push(l.slice(0, -1));
          rl.setPrompt('… ');
          rl.prompt();
          return;
        }
        acc.push(l);
        // texto colado chega como varias linhas seguidas: espera um instante para juntar
        timer = setTimeout(() => fim({ t: 'linha', texto: acc.join('\n') }), 25);
      });
      rl.on('SIGINT', () => {
        this.sai.write('\n');
        fim({ t: 'ctrl-c', texto: [...acc, rl.line].join('\n').trim() });
      });
      rl.on('close', () => fim(acc.length ? { t: 'linha', texto: acc.join('\n') } : { t: 'fim' }));
      rl.prompt();
    });
  }

  tecla(validas: string[]): Promise<string> {
    this.perguntando = true;
    return new Promise((resolve) => {
      this.ligarTeclas();
      const on = (str: string | undefined, k: readline.Key) => {
        let r: string | null = null;
        if ((k && k.ctrl && k.name === 'c') || (k && k.name === 'escape')) r = 'esc';
        else {
          const c = (str || '').toLowerCase();
          if (validas.includes(c)) r = c;
          else if (k && k.name === 'return' && validas.includes('enter')) r = 'enter';
        }
        if (r === null) return;
        this.entrada.off('keypress', on);
        this.perguntando = false;
        resolve(r);
      };
      this.entrada.on('keypress', on);
    });
  }

  private ligarTeclas() {
    if (!this.tty) return;
    readline.emitKeypressEvents(this.entrada);
    this.entrada.setRawMode(true);
    this.entrada.resume();
  }
  private retomarEscuta() { if (this.escuta) this.ligarTeclas(); }

  aoInterromper(cb: () => void): () => void {
    if (!this.tty) return () => {};
    this.escuta = cb;
    this.ligarTeclas();
    const on = (_s: string | undefined, k: readline.Key) => {
      if (this.perguntando || !k) return;
      if ((k.ctrl && k.name === 'c') || k.name === 'escape') cb();
    };
    this.onTecla = on;
    this.entrada.on('keypress', on);
    return () => {
      this.entrada.off('keypress', on);
      this.onTecla = null;
      this.escuta = null;
      if (!this.perguntando) { try { this.entrada.setRawMode(false); } catch { /* sem terminal */ } this.entrada.pause(); }
    };
  }
}

/* Modo -p: nada de perguntas; a resposta vai para o stdout e o resto para o stderr. */
export class IoImprimir implements Io {
  tty = false;
  largura() { return process.stderr.columns || 100; }
  saida(s: string) { process.stdout.write(s); }
  atividade(s: string) { process.stderr.write(s); }
  async tecla(): Promise<string> { throw new Error('modo -p nao pergunta'); }
  async linha(): Promise<Leitura> { throw new Error('modo -p nao pergunta'); }
  aoInterromper(cb: () => void) { process.on('SIGINT', cb); return () => { process.off('SIGINT', cb); }; }
  historico() { return []; }
  guardar() {}
}
