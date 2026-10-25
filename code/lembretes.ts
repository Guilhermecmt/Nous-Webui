// Lembretes da conversa (schedule_create/list/update/delete). Semantica,
// mensagens de erro e o texto entregue ao modelo vem do DeepSeek Harness
// (dsh-schedule e dsh-tool-schedule, MIT, (c) 2026 DeepSeek): exatamente um
// seletor de tempo (after_seconds, at, every_seconds, daily, weekly, cron),
// horario local que nao existe no fuso e' pulado, e depois de um tempo
// desligado o lembrete recorrente entrega so' a ultima ocorrencia perdida.
// O servidor confere a cada 15 s e entrega na conversa como um pedido novo.

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

type Tipo = 'after' | 'at' | 'every' | 'daily' | 'weekly' | 'cron';
export type Lembrete = {
  id: string; sessao: string; titulo: string; prompt: string; tipo: Tipo; criado: number; base: number;
  afterSeconds?: number; everySeconds?: number; time?: string; timeZone?: string; weekdays?: number[]; expression?: string;
  quando: number;          // proxima entrega (ms)
  ativo: boolean;
};
type Erro = { code: string; message: string };

const MAX_TITULO = 120;
const MIN_INTERVALO = 60;
let arquivo = '';
let todos: Lembrete[] = [];

export function configurar(dir: string) {
  arquivo = path.join(dir, 'lembretes.json');
  try { todos = JSON.parse(fs.readFileSync(arquivo, 'utf8')); } catch { todos = []; }
}
function salvar() {
  if (!arquivo) return;
  fs.mkdirSync(path.dirname(arquivo), { recursive: true });
  fs.writeFileSync(arquivo + '.tmp', JSON.stringify(todos, null, 1));
  fs.renameSync(arquivo + '.tmp', arquivo);
}

class ErroEntrada extends Error { code: string; constructor(code: string, m: string) { super(m); this.code = code; } }
const erro = (code: string, m: string): never => { throw new ErroEntrada(code, m); };

/* ------------------------------------------------------------ fuso horario sem biblioteca */
function zonaValida(z: unknown): string {
  const s = String(z ?? '');
  try { if (!s) throw new Error(); new Intl.DateTimeFormat('en-US', { timeZone: s }); return s; } catch { return erro('invalid_time_zone', 'time_zone must be UTC or a valid IANA Area/Location name.'); }
}
const fmt = new Map<string, Intl.DateTimeFormat>();
function partes(ms: number, zona: string) {
  let f = fmt.get(zona);
  if (!f) { f = new Intl.DateTimeFormat('en-US', { timeZone: zona, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short' }); fmt.set(zona, f); }
  const p: Record<string, string> = {};
  for (const x of f.formatToParts(new Date(ms))) p[x.type] = x.value;
  const dia = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 }[p.weekday as 'Mon'] || 1;
  return { a: +p.year, m: +p.month, d: +p.day, h: +p.hour % 24, mi: +p.minute, s: +p.second, dia };
}
/* Hora local (a, m, d, h, mi, s) no fuso -> instante; null se nao existe (horario de verao). */
function instante(a: number, m: number, d: number, h: number, mi: number, s: number, zona: string): number | null {
  const chute = Date.UTC(a, m - 1, d, h, mi, s);
  const candidatos: number[] = [];
  for (const k of [-1, 0, 1]) {
    const p = partes(chute + k * 12 * 3600_000, zona);
    const off = Date.UTC(p.a, p.m - 1, p.d, p.h, p.mi, p.s) - (chute + k * 12 * 3600_000);
    const t = chute - off;
    const q = partes(t, zona);
    if (q.a === a && q.m === m && q.d === d && q.h === h && q.mi === mi && q.s === s) candidatos.push(t);
  }
  return candidatos.length ? Math.min(...candidatos) : null;  // repetido: o mais cedo
}
function hora(t: unknown): [number, number, number] {
  const m = /^(\d{2}):(\d{2}):(\d{2})(\.\d{1,3})?$/.exec(String(t ?? ''));
  if (!m || +m[1] > 23 || +m[2] > 59 || +m[3] > 59) return erro('invalid_rule', 'time must be HH:mm:ss with optional 1-3 fractional digits.');
  return [+m[1], +m[2], +m[3]];
}

/* ------------------------------------------------------------ cron (5 campos, Vixie) */
const NOMES_MES = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const NOMES_DIA = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];
function campo(t: string, min: number, max: number, nomes?: string[]): { set: Set<number>; tudo: boolean } {
  const set = new Set<number>();
  const val = (x: string) => {
    const i = nomes ? nomes.indexOf(x.toLowerCase()) : -1;
    const n = i >= 0 ? i + (min === 1 ? 1 : 0) : Number(x);
    if (!Number.isInteger(n) || n < min || n > max) erro('invalid_rule', 'cron.expression has an out-of-range value: ' + x);
    return n;
  };
  for (const parte of t.split(',')) {
    const [faixa, passoT] = parte.split('/');
    const passo = passoT === undefined ? 1 : Number(passoT);
    if (!Number.isInteger(passo) || passo < 1) erro('invalid_rule', 'cron.expression has an invalid step: ' + parte);
    let ini: number, fim: number;
    if (faixa === '*') { ini = min; fim = max; }
    else if (faixa.includes('-')) { const [a, b] = faixa.split('-'); ini = val(a); fim = val(b); }
    else { ini = val(faixa); fim = passoT === undefined ? ini : max; }
    for (let i = ini; i <= fim; i += passo) set.add(i);
  }
  return { set, tudo: t === '*' || t.startsWith('*/') };
}
function cron(expr: string) {
  const f = expr.trim().split(/\s+/);
  if (f.length !== 5) erro('invalid_rule', 'cron.expression must have five fields: minute hour day-of-month month day-of-week.');
  const dow = campo(f[4], 0, 7, NOMES_DIA);
  if (dow.set.has(7)) { dow.set.delete(7); dow.set.add(0); }
  return { mi: campo(f[0], 0, 59), h: campo(f[1], 0, 23), dom: campo(f[2], 1, 31), mes: campo(f[3], 1, 12, NOMES_MES), dow };
}

/* ------------------------------------------------------------ proxima ocorrencia */
export function proxima(l: Lembrete, depois: number): number | null {
  switch (l.tipo) {
    case 'after': case 'at': return l.quando > depois ? l.quando : null;
    case 'every': {
      const p = l.everySeconds! * 1000;
      return l.base + (Math.floor((depois - l.base) / p) + 1) * p;
    }
    default: {
      const zona = l.timeZone!;
      const c = l.tipo === 'cron' ? cron(l.expression!) : null;
      const [hh, mm, ss] = l.tipo === 'cron' ? [0, 0, 0] : hora(l.time);
      const hoje = partes(depois, zona);
      const dia0 = Date.UTC(hoje.a, hoje.m - 1, hoje.d);
      for (let k = 0; k < 366 * 5; k++) {
        const dt = new Date(dia0 + k * 86_400_000);
        const a = dt.getUTCFullYear(), m = dt.getUTCMonth() + 1, d = dt.getUTCDate();
        const sem = dt.getUTCDay() === 0 ? 7 : dt.getUTCDay();
        if (l.tipo === 'weekly' && !l.weekdays!.includes(sem)) continue;
        if (c) {
          if (!c.mes.set.has(m)) continue;
          const okDom = c.dom.set.has(d), okDow = c.dow.set.has(sem % 7);
          // os dois campos de dia restritos: basta um bater (regra do Vixie cron)
          if (!c.dom.tudo && !c.dow.tudo ? !(okDom || okDow) : !(okDom && okDow)) continue;
          for (const h of [...c.h.set].sort((x, y) => x - y)) for (const mi of [...c.mi.set].sort((x, y) => x - y)) {
            const t = instante(a, m, d, h, mi, 0, zona);
            if (t !== null && t > depois) return t;
          }
        } else {
          const t = instante(a, m, d, hh, mm, ss, zona);
          if (t !== null && t > depois) return t;
        }
      }
      return null;
    }
  }
}

/* ------------------------------------------------------------ entrada do modelo */
type Args = Record<string, unknown>;
const SELETORES = ['after_seconds', 'at', 'every_seconds', 'daily', 'weekly', 'cron'];
const tem = (a: Args, k: string) => a[k] !== undefined && a[k] !== null && a[k] !== '' && a[k] !== 0;

function aplicarSeletor(l: Partial<Lembrete>, a: Args, k: string, agora: number) {
  delete l.afterSeconds; delete l.everySeconds; delete l.time; delete l.timeZone; delete l.weekdays; delete l.expression;
  l.base = agora;
  if (k === 'after_seconds') {
    const s = Number(a.after_seconds);
    if (!Number.isSafeInteger(s) || s <= 0) erro('invalid_rule', 'after_seconds must be a positive safe integer.');
    l.tipo = 'after'; l.afterSeconds = s; l.quando = agora + s * 1000;
  } else if (k === 'at') {
    let t: number;
    if (typeof a.at === 'string') {
      if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(a.at)) erro('invalid_rule', 'at must be an explicit-offset string or local calendar object.');
      t = Date.parse(a.at);
    } else if (a.at && typeof a.at === 'object') {
      const o = a.at as Args;
      const zona = zonaValida(o.time_zone);
      const dm = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(o.date ?? ''));
      if (!dm) erro('invalid_rule', 'at.date must be YYYY-MM-DD.');
      const [h, mi, s] = hora(o.time);
      const r = instante(+dm![1], +dm![2], +dm![3], h, mi, s, zona);
      if (r === null) erro('invalid_rule', 'The local at time does not exist in the selected time zone.');
      t = r!;
    } else return erro('invalid_rule', 'at must be an explicit-offset string or local calendar object.');
    if (!Number.isFinite(t)) erro('invalid_rule', 'at must be an explicit-offset string or local calendar object.');
    if (t <= agora) erro('not_future', 'The scheduled time must be strictly in the future.');
    l.tipo = 'at'; l.quando = t;
  } else if (k === 'every_seconds') {
    const s = Number(a.every_seconds);
    if (!Number.isSafeInteger(s)) erro('invalid_rule', 'every_seconds must be a safe integer.');
    if (s < MIN_INTERVALO) erro('frequency_too_high', `every_seconds must be at least ${MIN_INTERVALO}.`);
    l.tipo = 'every'; l.everySeconds = s;
  } else if (k === 'daily' || k === 'weekly') {
    const o = (a[k] || {}) as Args;
    l.tipo = k; l.timeZone = zonaValida(o.time_zone); hora(o.time); l.time = String(o.time);
    if (k === 'weekly') {
      const w = o.weekdays;
      if (!Array.isArray(w) || !w.length || w.some((x) => !Number.isInteger(x) || x < 1 || x > 7)) erro('invalid_rule', 'weekly.weekdays must be a non-empty array of ISO weekday numbers.');
      const vistos = new Set<number>();
      for (const x of w as number[]) { if (vistos.has(x)) erro('invalid_rule', `weekly.weekdays must not repeat weekday ${x}.`); vistos.add(x); }
      l.weekdays = w as number[];
    }
  } else if (k === 'cron') {
    const o = (a.cron || {}) as Args;
    const e = String(o.expression ?? '').trim();
    if (!e) erro('invalid_rule', 'cron.expression must be a non-empty trimmed string.');
    l.tipo = 'cron'; l.timeZone = zonaValida(o.time_zone); cron(e); l.expression = e;
  }
  if (l.tipo !== 'after' && l.tipo !== 'at') {
    const p = proxima(l as Lembrete, agora);
    if (p === null) erro('time_out_of_range', 'The rule has no occurrence in the next five years.');
    l.quando = p!;
  }
}

function titulo(t: unknown): string {
  const s = String(t ?? '').trim();
  if (!s) erro('invalid_prompt', 'title is required and must be non-empty after trimming.');
  if (s.length > MAX_TITULO) erro('invalid_prompt', `title must be at most ${MAX_TITULO} characters.`);
  return s;
}
function textoPrompt(t: unknown): string {
  const s = String(t ?? '').trim();
  if (!s) erro('invalid_prompt', 'prompt must be non-empty after trimming.');
  return s;
}

export function vista(l: Lembrete) {
  const v: Record<string, unknown> = { id: l.id, title: l.titulo, prompt: l.prompt, scheduledAt: new Date(l.quando).toISOString(),
    state: l.quando <= Date.now() ? 'overdue' : 'scheduled', deliveryMode: 'host', kind: l.tipo };
  if (l.tipo === 'after') v.afterSeconds = l.afterSeconds;
  if (l.tipo === 'every') v.everySeconds = l.everySeconds;
  if (l.tipo === 'daily' || l.tipo === 'weekly') { v.time = l.time; v.timeZone = l.timeZone; }
  if (l.tipo === 'weekly') v.weekdays = l.weekdays;
  if (l.tipo === 'cron') { v.expression = l.expression; v.timeZone = l.timeZone; }
  return v;
}

function protegido<T>(f: () => T): T | Erro {
  try { return f(); } catch (e) {
    if (e instanceof ErroEntrada) return { code: e.code, message: e.message };
    return { code: 'internal_error', message: 'The schedule operation failed.' };
  }
}

export function criar(sessao: string, a: Args) {
  return protegido(() => {
    const sel = SELETORES.filter((k) => tem(a, k));
    if (sel.length !== 1) erro('invalid_selector', 'schedule_create accepts exactly one of after_seconds, at, every_seconds, daily, weekly, or cron.');
    const agora = Date.now();
    const l: Partial<Lembrete> = { id: 'sch-' + crypto.randomUUID().slice(0, 8), sessao, prompt: textoPrompt(a.prompt), titulo: titulo(a.title), criado: agora, ativo: true };
    aplicarSeletor(l, a, sel[0], agora);
    todos.push(l as Lembrete);
    salvar();
    return vista(l as Lembrete);
  });
}

export function listar(sessao: string) { return todos.filter((l) => l.sessao === sessao && l.ativo).map(vista); }
export function daSessao(sessao: string) { return todos.filter((l) => l.sessao === sessao && l.ativo); }

export function atualizar(sessao: string, a: Args) {
  return protegido(() => {
    const id = String(a.id ?? '');
    if (!id || id !== id.trim()) erro('invalid_rule', 'schedule_update id must be non-empty without surrounding whitespace.');
    const sel = SELETORES.filter((k) => k !== 'after_seconds' && tem(a, k));
    if (tem(a, 'after_seconds')) erro('invalid_selector', 'schedule_update accepts at most one of at, every_seconds, daily, weekly, or cron.');
    if (sel.length > 1) erro('invalid_selector', 'schedule_update accepts at most one of at, every_seconds, daily, weekly, or cron.');
    if (!sel.length && a.title === undefined && a.prompt === undefined) erro('invalid_selector', 'schedule_update needs a new title, prompt, or one of at, every_seconds, daily, weekly, or cron.');
    const l = todos.find((x) => x.id === id && x.sessao === sessao);
    if (!l) return { id, updated: false, code: 'schedule_not_found' };
    if (!l.ativo) return { id, updated: false, code: 'schedule_ended' };
    const novo: Partial<Lembrete> = { ...l };
    if (a.title !== undefined) novo.titulo = titulo(a.title);
    if (a.prompt !== undefined) novo.prompt = textoPrompt(a.prompt);
    if (sel.length) aplicarSeletor(novo, a, sel[0], Date.now());
    Object.assign(l, novo);
    salvar();
    return vista(l);
  });
}

export function apagar(sessao: string, id: string) {
  return protegido(() => {
    if (!id || id !== id.trim()) erro('invalid_rule', 'schedule_delete id must be non-empty without surrounding whitespace.');
    const i = todos.findIndex((x) => x.id === id && x.sessao === sessao);
    if (i < 0) return { id, deleted: false, code: 'schedule_not_found' };
    todos.splice(i, 1);
    salvar();
    return { id, deleted: true };
  });
}
export function apagarDaSessao(sessao: string) { todos = todos.filter((l) => l.sessao !== sessao); salvar(); }

/* Lembretes vencidos, ja' no texto que vai para a conversa (um por sessao:
 * os avulsos um a um, os recorrentes juntos). Avanca ou encerra cada um. */
export function vencidos(agora = Date.now()): { sessao: string; texto: string; titulos: string[] }[] {
  const porSessao = new Map<string, Lembrete[]>();
  for (const l of todos) if (l.ativo && l.quando <= agora) {
    if (!porSessao.has(l.sessao)) porSessao.set(l.sessao, []);
    porSessao.get(l.sessao)!.push(l);
  }
  const out: { sessao: string; texto: string; titulos: string[] }[] = [];
  for (const [sessao, ls] of porSessao) {
    const avulsos = ls.filter((l) => l.tipo === 'after' || l.tipo === 'at');
    const recorrentes = ls.filter((l) => !avulsos.includes(l));
    const blocos: string[] = avulsos.map((l) => '[SCHEDULE REMINDER]\nThis is a scheduled message from the user\n' +
      `schedule_id_json: ${JSON.stringify(l.id)}\noccurrence_at: ${new Date(l.quando).toISOString()}\nreminder_prompt_json: ${JSON.stringify(l.prompt)}`);
    if (recorrentes.length) {
      blocos.push('[SCHEDULE REMINDER BATCH]\nThis is a scheduled message from the user\nreminders_json: ' +
        JSON.stringify(recorrentes.map((l) => ({ schedule_id: l.id, occurrence_at: new Date(l.quando).toISOString(), reminder_prompt: l.prompt }))));
    }
    for (const l of avulsos) l.ativo = false;
    for (const l of recorrentes) { const p = proxima(l, agora); if (p === null) l.ativo = false; else l.quando = p; }
    out.push({ sessao, texto: blocos.join('\n\n'), titulos: ls.map((l) => l.titulo) });
  }
  if (out.length) salvar();
  return out;
}
