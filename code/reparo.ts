// Conserta o que modelo local pequeno costuma errar ao chamar ferramenta: JSON
// quase certo e nome quase certo. Adaptado do Hermes Agent (Nous Research, MIT):
// agent/message_sanitization.py e repair_tool_call em agent/agent_runtime_helpers.py.
// Tudo aqui e' funcao pura, sem modelo e sem disco.

const FECHA: Record<string, string> = { '{': '}', '[': ']' };

function valido(t: string): { ok: true; valor: unknown } | { ok: false } {
  try { return { ok: true, valor: JSON.parse(t) }; } catch { return { ok: false }; }
}

/* Quebra de linha e tabulacao literais dentro de string viram \uXXXX. E' o erro
 * mais comum de modelo local: o `content` de um write com varias linhas. */
function escaparControles(raw: string): string {
  let out = '', emStr = false;
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (emStr && c === '\\' && i + 1 < raw.length) { out += c + raw[++i]; continue; }
    if (c === '"') emStr = !emStr;
    out += emStr && c.charCodeAt(0) < 0x20 ? '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0') : c;
  }
  return out;
}

/* Tira a virgula antes de } ou ]. Diferente do Hermes (uma regex no texto todo),
 * olha so' fora de string: `[1,2,]` dentro de um `content` e' codigo da pessoa. */
function semVirgulaFinal(raw: string): string {
  let out = '', emStr = false;
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (emStr) {
      out += c;
      if (c === '\\' && i + 1 < raw.length) out += raw[++i];
      else if (c === '"') emStr = false;
      continue;
    }
    if (c === '"') emStr = true;
    if (c === ',') {
      let j = i + 1;
      while (j < raw.length && /\s/.test(raw[j])) j++;
      if (raw[j] === '}' || raw[j] === ']') continue;
    }
    out += c;
  }
  return out;
}

/* Fecha { e [ na ordem da pilha, sem contar o que esta' dentro de string. Quem
 * fecha fora de ordem ganha antes os fechamentos que faltavam. Se o texto acaba
 * dentro de uma string, devolve null: esse conteudo se perdeu e nao se adivinha. */
function rebalancear(raw: string): string | null {
  let out = '', emStr = false;
  const pilha: string[] = [];
  for (let i = 0; i < raw.length; i++) {
    const c = raw[i];
    if (emStr) {
      if (c === '\\') { out += c + (raw[++i] ?? ''); continue; }
      if (c === '"') emStr = false;
    } else if (c === '"') emStr = true;
    else if (c in FECHA) pilha.push(c);
    else if ((c === '}' || c === ']') && pilha.some((p) => FECHA[p] === c)) {
      while (FECHA[pilha[pilha.length - 1]] !== c) out += FECHA[pilha.pop()!];
      pilha.pop();
    }
    out += c;
  }
  if (emStr) return null;
  return out + pilha.reverse().map((p) => FECHA[p]).join('');
}

/* JSON de argumentos quebrado -> valor, ou undefined se nao tem conserto. Nao
 * devolve {} como o Hermes: um `write` sem conteudo apagaria o arquivo, e o erro
 * precisa voltar ao modelo. */
export function repararJson(raw: string): unknown {
  const t = raw.trim();
  if (!t) return undefined;
  let r = valido(t);
  if (r.ok) return r.valor;
  r = valido(escaparControles(t));
  if (r.ok) return r.valor;
  let fixo = semVirgulaFinal(t);
  fixo = rebalancear(fixo) ?? fixo;
  const conta = (s: string, c: string) => s.split(c).length - 1;
  for (let i = 0; i < 50; i++) {
    if (valido(fixo).ok) break;
    const sobra = (fixo.endsWith('}') && conta(fixo, '}') > conta(fixo, '{')) || (fixo.endsWith(']') && conta(fixo, ']') > conta(fixo, '['));
    if (!sobra) break;
    fixo = fixo.slice(0, -1);
  }
  r = valido(fixo);
  if (r.ok) return r.valor;
  r = valido(escaparControles(fixo));
  return r.ok ? r.valor : undefined;
}

/* Ratcliff-Obershelp, a mesma conta do difflib.SequenceMatcher.ratio. */
export function semelhanca(a: string, b: string): number {
  if (!a.length && !b.length) return 1;
  const iguais = (x: string, y: string): number => {
    if (!x || !y) return 0;
    let tam = 0, ix = 0, iy = 0;
    let ant = new Array<number>(y.length + 1).fill(0);
    for (let i = 1; i <= x.length; i++) {
      const cur = new Array<number>(y.length + 1).fill(0);
      for (let j = 1; j <= y.length; j++) {
        if (x[i - 1] !== y[j - 1]) continue;
        cur[j] = ant[j - 1] + 1;
        if (cur[j] > tam) { tam = cur[j]; ix = i - tam; iy = j - tam; }
      }
      ant = cur;
    }
    if (!tam) return 0;
    return tam + iguais(x.slice(0, ix), y.slice(0, iy)) + iguais(x.slice(ix + tam), y.slice(iy + tam));
  };
  return (2 * iguais(a, b)) / (a.length + b.length);
}

/* Nome errado de ferramenta -> nome certo, ou null. Trata maiusculas, separadores,
 * CamelCase, sufixo _tool (ate' duas vezes) e, por fim, semelhanca >= 0,7. */
export function repararNome(nome: string, validos: Iterable<string>): string | null {
  const lista = new Set(validos);
  let n = String(nome ?? '');
  for (const sep of ['"', "'", '<', '>']) {
    const i = n.indexOf(sep);
    if (i > 0) n = n.slice(0, i);
  }
  n = n.trim();
  if (!n) return null;
  const norm = (s: string) => s.toLowerCase().replace(/[- ]/g, '_');
  const cobra = (s: string) => s.replace(/(?<!^)(?=[A-Z])/g, '_').toLowerCase();
  const semSufixo = (s: string) => {
    const m = /^(.*?)[_-]?tool$/i.exec(s);
    return m && m[1] ? m[1].replace(/[_-]+$/, '') : null;
  };
  const baixo = n.toLowerCase();
  if (lista.has(baixo)) return baixo;
  if (lista.has(norm(n))) return norm(n);
  const cands = new Set<string>([n, baixo, norm(n), cobra(n)]);
  for (let i = 0; i < 2; i++) {
    for (const c of [...cands]) {
      const s = semSufixo(c);
      if (s) { cands.add(s); cands.add(norm(s)); cands.add(cobra(s)); }
    }
  }
  for (const c of cands) if (lista.has(c)) return c;
  let melhor: string | null = null, nota = 0.7;
  for (const v of lista) {
    const r = semelhanca(baixo, v);
    if (r >= nota) { nota = r; melhor = v; }
  }
  return melhor;
}

/* A sequencia de chaves termina num ciclo A,B,A,B de periodo 2 a 4 repetido tres
 * vezes? Devolve o periodo, ou 0. O periodo 1 ja' tem o aviso de chamada repetida. */
export function periodoDoCiclo(chaves: string[]): number {
  for (let p = 2; p <= 4; p++) {
    if (chaves.length < p * 3) continue;
    const fim = chaves.slice(-p * 3);
    if (new Set(fim.slice(0, p)).size < 2) continue;
    if (fim.every((c, i) => c === fim[i % p])) return p;
  }
  return 0;
}

/* Texto com a cara da saida do read ("12: codigo"), em vez do arquivo de verdade.
 * Tres ou mais linhas numeradas em sequencia e pelo menos 60% do texto. */
export function pareceNumerado(texto: string): boolean {
  const linhas = texto.split('\n').filter((l) => l.trim());
  const nums: number[] = [];
  for (const l of linhas) {
    const m = /^\s*(\d+)(?::|\|)/.exec(l);
    if (m) nums.push(Number(m[1]));
  }
  if (nums.length < 3 || nums.length / linhas.length < 0.6) return false;
  return nums.every((n, i) => i === 0 || n === nums[i - 1] + 1);
}
