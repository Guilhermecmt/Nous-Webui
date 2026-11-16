// Argumentos da linha de comando do `nous`.
import { normalizarAlcance, normalizarEsforco, normalizarModo } from './comandos.ts';

export type Opcoes = {
  ajuda: boolean;
  versao: boolean;
  imprimir: boolean;          // -p: um turno e sai
  pedido: string;             // texto do pedido (do -p ou dos argumentos soltos)
  modelo?: string;
  esforco?: string;           // ja' no vocabulario do servidor (auto, desligado, baixo, medio, alto)
  modo?: string;
  alcance?: string;
  continuar: boolean;
  pasta?: string;
  erro?: string;
};

export const AJUDA = `Nous no terminal: o agente de programação do Nous (Nous Code) na pasta onde você está.

Uso:
  nous                       abre uma conversa nesta pasta
  nous "faça isto"           abre a conversa já com o primeiro pedido
  nous -p "pedido"           um pedido só: a resposta vai para a saída padrão
  tipo texto | nous -p "resuma isto"

Opções:
  -p, --print [pedido]       modo não interativo (também com texto pela entrada padrão)
  -m, --model <nome>         modelo (veja /model dentro da conversa)
      --effort <nível>       raciocínio: auto, desligado, baixo, medio, alto (ou off, low, medium, high)
      --modo <modo>          permissões: leitura, perguntar, editar, total
      --alcance <alcance>    projeto, usuario ou computador (no terminal o padrão é o computador inteiro)
  -c, --continuar            retoma a última conversa desta pasta
  -C, --pasta <pasta>        trabalha em outra pasta
  -v, --versao               mostra a versão
  -h, --ajuda                esta ajuda

No modo -p os pedidos de aprovação são recusados, a não ser com --modo editar
(arquivos e comandos comuns) ou --modo total. Dentro da conversa, /ajuda lista
os comandos.`;

const VALOR = new Set(['-m', '--model', '--modelo', '--effort', '--esforco', '--raciocinio', '--modo', '--permissions', '--alcance', '-C', '--pasta']);

export function lerArgs(argv: string[]): Opcoes {
  const o: Opcoes = { ajuda: false, versao: false, imprimir: false, pedido: '', continuar: false };
  const soltos: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    let a = argv[i];
    let valor: string | undefined;
    const eq = /^(--[\w-]+)=([\s\S]*)$/.exec(a);
    if (eq) { a = eq[1]; valor = eq[2]; }
    if (a === '--') { soltos.push(...argv.slice(i + 1)); break; }
    if (a === '-h' || a === '--ajuda' || a === '--help') { o.ajuda = true; continue; }
    if (a === '-v' || a === '--versao' || a === '--version' || a === '-V') { o.versao = true; continue; }
    if (a === '-c' || a === '--continuar' || a === '--continue') { o.continuar = true; continue; }
    if (a === '-p' || a === '--print' || a === '--imprimir') {
      o.imprimir = true;
      // -p "pedido": o proximo argumento e' o pedido, se nao for outra opcao
      if (valor === undefined && i + 1 < argv.length && !argv[i + 1].startsWith('-')) valor = argv[++i];
      if (valor) soltos.push(valor);
      continue;
    }
    if (VALOR.has(a)) {
      if (valor === undefined) {
        if (i + 1 >= argv.length) { o.erro = 'falta o valor de ' + a; return o; }
        valor = argv[++i];
      }
      if (a === '-m' || a === '--model' || a === '--modelo') o.modelo = valor;
      else if (a === '--effort' || a === '--esforco' || a === '--raciocinio') {
        const n = normalizarEsforco(valor);
        if (!n) { o.erro = 'raciocínio desconhecido: ' + valor + ' (use auto, desligado, baixo, medio ou alto)'; return o; }
        o.esforco = n;
      } else if (a === '--modo' || a === '--permissions') {
        const n = normalizarModo(valor);
        if (!n) { o.erro = 'modo desconhecido: ' + valor + ' (use leitura, perguntar, editar ou total)'; return o; }
        o.modo = n;
      } else if (a === '--alcance') {
        const n = normalizarAlcance(valor);
        if (!n) { o.erro = 'alcance desconhecido: ' + valor + ' (use projeto, usuario ou computador)'; return o; }
        o.alcance = n;
      } else o.pasta = valor;
      continue;
    }
    if (a.startsWith('-') && a.length > 1) { o.erro = 'opção desconhecida: ' + a + ' (veja nous --ajuda)'; return o; }
    soltos.push(a);
  }
  o.pedido = soltos.join(' ').trim();
  return o;
}
