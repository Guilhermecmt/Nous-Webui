// Comandos de barra do terminal: nomes, apelidos (em ingles, como no Claude
// Code e no Codex) e a leitura dos valores (raciocinio, modo, alcance).

export type Comando = { nome: string; apelidos: string[]; arg: string; ajuda: string };

export const COMANDOS: Comando[] = [
  { nome: 'ajuda', apelidos: ['help', '?'], arg: '', ajuda: 'Lista os comandos' },
  { nome: 'modelo', apelidos: ['model'], arg: '[nome|número]', ajuda: 'Escolhe o modelo desta conversa (sem argumento: lista para escolher)' },
  { nome: 'effort', apelidos: ['raciocinio', 'raciocínio', 'esforco', 'esforço'], arg: '[auto|desligado|baixo|medio|alto]', ajuda: 'Quanto o modelo raciocina antes de responder' },
  { nome: 'modo', apelidos: ['permissions', 'permissoes', 'permissões'], arg: '[leitura|perguntar|editar|total]', ajuda: 'O que o agente pode fazer sem pedir' },
  { nome: 'alcance', apelidos: ['scope'], arg: '[projeto|usuario|computador]', ajuda: 'Até onde o agente enxerga: só o projeto, sua pasta de usuário ou o PC todo' },
  { nome: 'plano', apelidos: ['plan'], arg: '[pedido|sair]', ajuda: 'Modo plano: o agente investiga e propõe antes de mudar' },
  { nome: 'objetivo', apelidos: ['goal'], arg: '<texto>|pausar|retomar|limpar', ajuda: 'Um objetivo que o agente persegue em rodadas até cumprir' },
  { nome: 'compactar', apelidos: ['compact'], arg: '', ajuda: 'Resume a conversa para liberar contexto' },
  { nome: 'contexto', apelidos: ['context', 'status'], arg: '', ajuda: 'Tokens usados, modelo, pasta e permissões' },
  { nome: 'novo', apelidos: ['nova', 'new', 'clear', 'limpar'], arg: '', ajuda: 'Começa uma conversa nova (mantém modelo e permissões)' },
  { nome: 'conversas', apelidos: ['resume', 'retomar'], arg: '[número]', ajuda: 'Lista as conversas desta pasta e retoma uma' },
  { nome: 'desfazer', apelidos: ['undo'], arg: '[arquivo]', ajuda: 'Volta os arquivos que o agente mudou ao que eram antes' },
  { nome: 'mudancas', apelidos: ['mudanças', 'diff'], arg: '[arquivo]', ajuda: 'Arquivos que o agente mudou nesta conversa (com o diff de um arquivo)' },
  { nome: 'exportar', apelidos: ['export'], arg: '[arquivo.md]', ajuda: 'Salva a conversa em Markdown' },
  { nome: 'mcp', apelidos: [], arg: '[permitir|desligar <nome>]', ajuda: 'Servidores MCP deste projeto' },
  { nome: 'skills', apelidos: ['habilidades'], arg: '', ajuda: 'Skills do projeto; use /nome-da-skill no pedido' },
  { nome: 'internet', apelidos: ['web'], arg: '', ajuda: 'Libera ou bloqueia a internet nesta conversa' },
  { nome: 'ide', apelidos: [], arg: '', ajuda: 'Abre esta conversa na janela do Nous Code' },
  { nome: 'padrao', apelidos: ['padrão', 'defaults'], arg: '[modo|alcance <valor>]', ajuda: 'Permissões e alcance das conversas novas' },
  { nome: 'sair', apelidos: ['exit', 'quit', 'q'], arg: '', ajuda: 'Sai do Nous' },
];

const sem = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

/* Acha o comando pelo nome ou por um apelido (sem diferenca de maiusculas ou acento). */
export function acharComando(nome: string): Comando | undefined {
  const n = sem(nome);
  return COMANDOS.find((c) => sem(c.nome) === n || c.apelidos.some((a) => sem(a) === n));
}

export type Linha =
  | { tipo: 'vazia' }
  | { tipo: 'texto'; texto: string }
  | { tipo: 'comando'; comando: Comando; arg: string }
  | { tipo: 'desconhecido'; nome: string; texto: string };   // /algo que nao e' comando: pode ser uma skill

/* "/model qwen3" -> {comando modelo, arg "qwen3"}. Texto que nao comeca com
 * barra (ou um caminho como /usr/bin) vai direto ao agente. */
export function interpretar(linha: string): Linha {
  const t = linha.trim();
  if (!t) return { tipo: 'vazia' };
  const m = /^\/([^\s/\\]+)(?:\s+([\s\S]*))?$/.exec(t);
  if (!m) return { tipo: 'texto', texto: t };
  const c = acharComando(m[1]);
  if (c) return { tipo: 'comando', comando: c, arg: (m[2] || '').trim() };
  return { tipo: 'desconhecido', nome: m[1], texto: t };
}

export const ESFORCOS = ['auto', 'desligado', 'baixo', 'medio', 'alto'] as const;
export const MODOS = ['leitura', 'perguntar', 'editar', 'total'] as const;
export const ALCANCES = ['projeto', 'usuario', 'computador'] as const;

export function normalizarEsforco(v: string): string | null {
  const x = sem(v.trim());
  const mapa: Record<string, string> = { auto: 'auto', automatico: 'auto', padrao: 'auto', default: 'auto',
    desligado: 'desligado', off: 'desligado', none: 'desligado', nenhum: 'desligado', desligar: 'desligado', '0': 'desligado',
    baixo: 'baixo', low: 'baixo', min: 'baixo', '1': 'baixo',
    medio: 'medio', medium: 'medio', med: 'medio', '2': 'medio',
    alto: 'alto', high: 'alto', max: 'alto', '3': 'alto' };
  return mapa[x] ?? null;
}
export function normalizarModo(v: string): string | null {
  const x = sem(v.trim());
  const mapa: Record<string, string> = { leitura: 'leitura', read: 'leitura', readonly: 'leitura', 'somente-leitura': 'leitura',
    perguntar: 'perguntar', ask: 'perguntar', default: 'perguntar', pedir: 'perguntar',
    editar: 'editar', edit: 'editar', acceptedits: 'editar',
    total: 'total', full: 'total', bypass: 'total', yolo: 'total' };
  return mapa[x] ?? null;
}
export function normalizarAlcance(v: string): string | null {
  const x = sem(v.trim());
  const mapa: Record<string, string> = { projeto: 'projeto', project: 'projeto', usuario: 'usuario', user: 'usuario', home: 'usuario',
    computador: 'computador', pc: 'computador', computer: 'computador', all: 'computador' };
  return mapa[x] ?? null;
}

export const ROTULO_ESFORCO: Record<string, string> = { auto: 'automático', desligado: 'desligado', baixo: 'baixo', medio: 'médio', alto: 'alto' };
export const ROTULO_MODO: Record<string, string> = { leitura: 'somente leitura', perguntar: 'pedir antes de mudar', editar: 'editar sem perguntar', total: 'acesso total' };
export const ROTULO_ALCANCE: Record<string, string> = { projeto: 'só o projeto', usuario: 'sua pasta de usuário', computador: 'o computador inteiro' };

/* Escolhe um item de uma lista por numero (1..n), nome exato ou trecho unico. */
export function escolherItem<T>(itens: T[], texto: string, nomeDe: (i: T) => string): { item?: T; erro?: string } {
  const t = texto.trim();
  if (!t) return { erro: 'nada escolhido' };
  if (/^\d+$/.test(t)) {
    const i = Number(t);
    return i >= 1 && i <= itens.length ? { item: itens[i - 1] } : { erro: 'escolha um número de 1 a ' + itens.length };
  }
  const exato = itens.filter((i) => nomeDe(i).toLowerCase() === t.toLowerCase());
  if (exato.length === 1) return { item: exato[0] };
  const parte = itens.filter((i) => nomeDe(i).toLowerCase().includes(t.toLowerCase()));
  if (parte.length === 1) return { item: parte[0] };
  if (parte.length > 1) return { erro: '"' + t + '" serve para mais de um: ' + parte.slice(0, 5).map(nomeDe).join(', ') };
  return { erro: 'não achei "' + t + '"' };
}

/* Candidatos do Tab para a primeira palavra: /comandos (e skills). */
export function completarComando(prefixo: string, skills: string[] = []): string[] {
  const p = sem(prefixo.replace(/^\//, ''));
  const nomes = new Set<string>();
  for (const c of COMANDOS) {
    for (const n of [c.nome, ...c.apelidos]) if (/^[\w-]+$/.test(n) && sem(n).startsWith(p)) nomes.add('/' + n);
  }
  for (const s of skills) if (sem(s).startsWith(p)) nomes.add('/' + s);
  return [...nomes].sort((a, b) => a.length - b.length || a.localeCompare(b));
}
