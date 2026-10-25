// As ferramentas do agente: esquemas que o modelo ve e a implementacao das de
// arquivo (ler, escrever, editar, procurar). Tudo preso na pasta do projeto:
// caminho que sai dela e' recusado (so' a leitura alcanca tambem os arquivos
// de saida completa que o proprio Nous Code guarda).
//
// O contrato com o modelo (nomes, parametros, descricoes, formato dos
// resultados e mensagens de erro) vem do DeepSeek Harness (dsh-tool-fs,
// dsh-tool-fs-search, dsh-tool-pwsh, dsh-tool-jobs, dsh-tool-web,
// dsh-tool-todo, dsh-tool-ask-user, dsh-plan-mode, dsh-tool-goal,
// dsh-tool-skill, dsh-tool-subagent, dsh-tool-lsp, dsh-tool-present,
// dsh-tool-schedule e dsh-spill-policy; MIT, (c) 2026 DeepSeek), com os
// ajustes para modelo local pequeno: limites menores, edicao tolerante e os
// nomes antigos (read_file, edit_file, run_command...) aceitos como apelidos.

import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

export const IGNORAR = new Set(['.git', 'node_modules', '__pycache__', '.venv', 'venv', 'env', 'dist', 'build',
  '.next', '.nuxt', 'target', '.idea', '.vs', '.vscode', 'coverage', '.cache', '.pytest_cache', '.mypy_cache', 'bin', 'obj',
  '.svn', '.hg', '.bzr', '.jj', '.sl']);
const READ_LIMIT = 2000;             // linhas por leitura (padrao e maximo, como no dsh)
const READ_MAX_LINE = 2000;          // caracteres por linha
const READ_MAX_BYTES = 12 * 1024;    // o dsh usa 50 KiB; o contexto local e' de 16k tokens
const GLOB_MAX = 100;
const GREP_MAX = 100;                // o dsh mostra 250; aqui o resto vai para o arquivo
const MAX_SAIDA_MODELO = 6000;       // caracteres de resultado que voltam ao modelo (o resto vai para arquivo)

/* ------------------------------------------------------------ esquemas */
type Prop = Record<string, unknown>;
const S = (description: string): Prop => ({ type: 'string', description });
const N = (description: string): Prop => ({ type: 'integer', description });
const B = (description: string): Prop => ({ type: 'boolean', description });

function ferr(name: string, description: string, properties: Record<string, Prop>, required: string[] = []) {
  return { type: 'function', function: { name, description, parameters: { type: 'object', properties, required } } };
}

const HORARIO = (ex: string): Prop => ({ type: 'object', properties: {
  time: S(`HH:mm:ss with optional 1-3 fractional digits, for example ${ex}.`),
  time_zone: S('UTC or IANA Area/Location, for example America/Sao_Paulo.') }, required: ['time', 'time_zone'] });
const SELETORES: Record<string, Prop> = {
  at: S('Absolute target: an RFC 3339 date-time with offset, or a local date, time, and IANA time_zone.'),
  every_seconds: N('Fixed-rate interval in whole seconds, at least 60, aligned to the creation time; changing it with schedule_update re-aligns it to the save time.'),
  daily: { ...HORARIO('23:00:00'), description: 'Every day at a local time.' },
  weekly: { type: 'object', description: 'On the given weekdays at a local time.', properties: {
    ...(HORARIO('09:00:00').properties as object), weekdays: { type: 'array', items: { type: 'integer' }, description: 'ISO weekdays, Monday 1 through Sunday 7, without repetitions.' } },
  required: ['time', 'time_zone', 'weekdays'] },
  cron: { type: 'object', description: 'Five-field Vixie cron expression in a time zone.', properties: {
    expression: S('minute hour day-of-month month day-of-week, for example "*/15 9-17 * * 1-5". When both day fields are restricted, a date matches if either one matches.'),
    time_zone: S('UTC or IANA Area/Location, for example America/Sao_Paulo.') }, required: ['expression', 'time_zone'] },
};

export const ESQUEMAS = [
  ferr('read', 'Read a UTF-8 text file and return line-numbered content.', {
    file_path: S('Path to read, relative to the project folder.'),
    offset: N('1-based first line to return. Defaults to 1.'),
    limit: N(`Maximum number of lines to return. Defaults to ${READ_LIMIT}.`),
  }, ['file_path']),
  ferr('write', 'Create or fully replace a UTF-8 text file.', {
    file_path: S('Path to write, relative to the project folder. Provide `file_path` before `content` in the arguments.'),
    content: S('Full UTF-8 text content to write.'),
  }, ['file_path', 'content']),
  ferr('edit', 'Edit an existing UTF-8 text file by replacing literal text.', {
    file_path: S('Path to edit, relative to the project folder. Provide `file_path` before `old_string` and `new_string` in the arguments.'),
    old_string: S('Literal text to replace.'),
    new_string: S('Literal replacement text. Use an empty string to delete the match.'),
    replace_all: B('Replace all matches. Defaults to false; when false, old_string must appear exactly once.'),
  }, ['file_path', 'old_string', 'new_string']),
  ferr('glob', `Find files, not directories, whose paths match a glob pattern. Returns up to ${GLOB_MAX} paths in modification-time order; a larger result keeps the first paths and reports where the complete list was saved.`, {
    pattern: S('Glob pattern to match file paths against (e.g. "**/*.ts", "src/**/*.test.js"). A pattern with no "/" matches the basename at any depth, so "*" and "*.ts" both search the whole tree; include a separator to anchor the depth.'),
    path: S('Directory to search in. Defaults to the project folder; a relative path resolves against it.'),
  }, ['pattern']),
  ferr('grep', `Search file contents with a regular expression. Returns matching lines with line numbers, grouped by file. Returns up to ${GREP_MAX} matches; a larger result reports where the complete match list was saved.`, {
    pattern: S('Regular expression to search for. Case-insensitive unless it has an uppercase letter.'),
    path: S('File or directory to search. Defaults to the project folder; a relative path resolves against it.'),
    include: S('One glob filter for which files to search (e.g. "*.ts", "*.{js,jsx}"). Not a list; negation is not supported.'),
  }, ['pattern']),
  ferr('list_files', 'List the files and folders of the project as a tree. Start here to understand the project.', {
    path: S('Folder relative to the project root. Default: "."'),
    depth: N('How many levels to show (1-4). Default: 2'),
  }),
  ferr('pwsh', 'Execute a PowerShell command and return its output. Each call runs in a fresh PowerShell process; pass `workdir` instead of using `cd`. Paths use native Windows form (`C:\\...`); read environment variables with `$env:NAME`. Long output is truncated; the full output is saved to a file whose path is reported. On Windows a force-killed command settles as `[exit code: 1]` — treat it as an interruption, not a command failure. Provide `description` before `command` in the arguments. Before any delete or move, verify that the resolved absolute target path is the intended one; never run it against a computed path you have not checked. Do not assign to automatic variables such as `$HOME`.', {
    description: S('Clear, concise description of what this command does in active voice, 5-10 words (shown in the UI). Examples: "ls" → "List files in current directory"; "git status" → "Show working tree status"; "Get-Process" → "List running processes".'),
    command: S('The PowerShell command to execute.'),
    timeoutMs: N('Timeout in milliseconds (default 120000, max 600000). On expiry the command moves to the background as a job instead of being killed.'),
    workdir: S('Working directory for this command. Defaults to the project folder; a relative path is resolved against it.'),
    run_in_background: B('Run in the background and return a job id immediately (collect with job_output, stop with job_kill). No timeout applies.'),
  }, ['description', 'command']),
  ferr('job_output', 'Read a background job: output since the previous read, and its status.', {
    job_id: S('Job id returned by the tool that started the background work.'),
    wait: B('Block until the job finishes or the timeout expires; a timed-out wait leaves the job running. Defaults to false.'),
    timeout_ms: N('Max wait in milliseconds with wait: true. Defaults to 30000, capped at 600000.'),
  }, ['job_id']),
  ferr('job_list', 'List your background jobs (running and finished) with their ids, kinds, and statuses.', {}),
  ferr('job_kill', 'Request cancellation of a running background job.', {
    job_id: S('Job id returned by the tool that started the background work.'),
    reason: S('Optional short reason, recorded in the log.'),
  }, ['job_id']),
  ferr('web_search', 'Search the web for current information. Returns a list of source URLs with snippets.', {
    queries: { type: 'array', items: { type: 'string' }, description: '1–4 search queries; their results are merged.' },
  }, ['queries']),
  ferr('web_fetch', 'Fetch the content of a specific HTTP(S) URL and return it decoded to text.', {
    url: S('The HTTP(S) URL to fetch.'),
    find: S('Optional: a word or phrase; returns only the parts of the page that mention it (saves context on big pages).'),
  }, ['url']),
  ferr('todo_write', 'Record and update a task list to plan multi-step work and show progress; skip it for trivial single-step tasks. Add one todo per concrete step before you start. While work remains, keep the todos being worked on `in_progress`, several only when work runs in parallel. Mark each todo `completed` as soon as it is done.', {
    todos: { type: 'array', description: 'The COMPLETE task list, replacing any previous list.', items: { type: 'object', properties: {
      content: S('What the task is — a short imperative line.'),
      status: { type: 'string', enum: ['pending', 'in_progress', 'completed'], description: 'pending (not started) | in_progress (now) | completed (done).' },
    }, required: ['content', 'status'] } },
  }, ['todos']),
  ferr('ask_user_question', 'Ask the user a concise question when you need confirmation, a choice, or missing information before proceeding.', {
    questions: { type: 'array', description: 'Questions to ask the user before continuing.', items: { type: 'object', properties: {
      id: S('Stable id for this question; echoed in the answer.'),
      question: S('The specific question to ask the user.'),
      header: S('Optional short heading for the question, such as "Confirm" or "Choose Mode".'),
      options: { type: 'array', description: 'Optional choices to show the user. If you recommend one, put it first and append "(Recommended)" to that label.',
        items: { type: 'object', properties: { label: S('Short user-facing option label.'), description: S('One sentence explaining the tradeoff or impact.') }, required: ['label'] } },
      multi_select: B('Whether the user may select more than one option. Defaults to false.'),
    }, required: ['id', 'question'] } },
  }, ['questions']),
  ferr('exit_plan_mode', "Use only in plan mode. Present your plan for the user's review and, on approval, leave plan mode. The user may approve (carry out the plan from your next step) or keep planning — their feedback comes back in the tool result; revise and present again.", {
    plan: S('The complete plan, as markdown, starting with a # heading that names it.'),
  }, ['plan']),
  ferr('create_goal', 'Create a persisted goal that keeps this session working across automatic continuation rounds. Use it when the direct human request is a long-running objective, even if the user did not say "goal"; not for single-turn work.', {
    objective: S('The concrete completion objective inferred from the direct human request.'),
    max_goal_rounds: N('Optional positive limit on automatic continuation rounds (default 20).'),
  }, ['objective']),
  ferr('get_goal', 'Read the current session goal, including the id and revision that update_goal requires.', {}),
  ferr('update_goal', 'Update the current goal.', {
    goal_id: S('Exact id returned by get_goal.'),
    revision: N('Exact positive revision returned by get_goal.'),
    action: { type: 'string', enum: ['edit', 'pause', 'resume', 'complete', 'blocked'], description: 'edit, pause, and resume require a direct human request. complete and blocked are also allowed during an automatic continuation of this goal; blocked is rejected before the configured minimum round count.' },
    objective: S('Replacement objective; valid only with action edit.'),
    max_goal_rounds: N('Replacement cap; valid only with action edit.'),
    blocked_reason: S('Required only with action blocked: the concrete condition that persisted across rounds and blocks progress.'),
  }, ['action']),
  ferr('skill', 'Load the full instructions for a skill. Call it before acting on a task that names or clearly matches a skill in the session skill catalog.', {
    name: S('The exact skill name from the available skills list.'),
  }, ['name']),
  ferr('subagent', 'Delegate a self-contained task to a subagent (a separate agent that works in its own context) so it does not consume this conversation\'s context. By default it is read-only: it can read, glob, grep and list files, but not change anything. With edit=true it may also edit and write files, but only the ones listed in files; it cannot run commands, and it asks for the same approvals as you. The subagent returns its result, not its intermediate steps.', {
    description: S('A short (3-5 word) description of the delegated task, for display.'),
    prompt: S("The complete, self-contained task for the subagent. It does not share this conversation's context, so include everything it needs."),
    edit: B('Set true to let the subagent change files. Requires files. Default false (read-only).'),
    files: { type: 'array', description: 'With edit=true: the files and folders (relative to the project folder) the subagent may change. Everything else is refused.', items: { type: 'string' } },
  }, ['description', 'prompt']),
  ferr('lsp', 'Query a language server for precise code navigation. operation is one of goToDefinition, findReferences, goToImplementation, hover. line and character are one-based UTF-16 cursor coordinates. findReferences includes the declaration.', {
    operation: { type: 'string', enum: ['goToDefinition', 'findReferences', 'goToImplementation', 'hover'], description: 'goToDefinition, findReferences, goToImplementation, or hover.' },
    file_path: S('The source file to query, relative to the project folder.'),
    line: N('One-based line of the cursor.'),
    character: N('One-based UTF-16 column of the cursor.'),
  }, ['operation', 'file_path', 'line', 'character']),
  ferr('present', 'Declare existing files as final deliverables for the user. Use it when the user needs a separate file, especially Office documents, spreadsheets, and slide decks; prefer your final response when that suffices. The user opens the current files; their contents are not copied.', {
    files: { type: 'array', description: 'Usually the 1-2 most important deliverables; at most 4 per call.', items: { type: 'object', properties: {
      path: S('Path of an existing regular file, relative to the project folder.'), description: S('Brief description for the user.') }, required: ['path'] } },
  }, ['files']),
  ferr('schedule_create', 'Create a reminder in the current session that delivers prompt when it becomes due. Supply exactly one timing parameter: after_seconds, at, every_seconds, daily, weekly, or cron. After downtime, a recurring reminder delivers only its latest missed occurrence.', {
    prompt: S('Reminder content to present when the target becomes due.'),
    title: S("Concise task name in the user's language, at most 120 characters. Name only the core action and subject; put scheduling information in the timing parameters and execution instructions in prompt."),
    after_seconds: N('Delay in whole seconds.'),
    ...SELETORES,
  }, ['prompt', 'title']),
  ferr('schedule_list', 'List the active reminders in the current session.', {}),
  ferr('schedule_update', 'Change a reminder in place, keeping its id. Supply a new title, prompt, or at most one timing parameter; omitted fields keep their stored values. To change a relative delay, create a new reminder.', {
    id: S('Schedule id returned by schedule_list.'), title: S('New task name; follow the schedule_create title rules.'), prompt: S('New reminder content.'), ...SELETORES,
  }, ['id']),
  ferr('schedule_delete', 'Delete a reminder in the current session, active or inactive.', { id: S('Exact schedule id.') }, ['id']),
];

/* O que nao muda nada no disco: o que o modo plano e o somente leitura deixam usar. */
export const LEITURA = new Set(['read', 'glob', 'grep', 'list_files', 'job_output', 'job_list', 'web_search', 'web_fetch',
  'todo_write', 'ask_user_question', 'exit_plan_mode', 'create_goal', 'get_goal', 'update_goal', 'skill', 'subagent', 'lsp',
  'present', 'schedule_list']);
export const NOMES_BASE = new Set(ESQUEMAS.map((e) => e.function.name));

/* ------------------------------------------------------------ apelidos */
/* Nomes que modelos treinados em outros agentes usam (Claude Code, OpenCode, a
 * versao anterior do Nous Code) e o nome canonico daqui. */
const APELIDOS: Record<string, string> = {
  read_file: 'read', readfile: 'read', view: 'read', cat: 'read',
  write_file: 'write', create_file: 'write', writefile: 'write',
  edit_file: 'edit', str_replace: 'edit', replace_in_file: 'edit', multiedit: 'edit',
  search: 'grep', search_files: 'grep', find_in_files: 'grep',
  find_files: 'glob', file_search: 'glob',
  ls: 'list_files', list_dir: 'list_files', list_directory: 'list_files',
  run_command: 'pwsh', bash: 'pwsh', shell: 'pwsh', powershell: 'pwsh', execute_command: 'pwsh', run_terminal_cmd: 'pwsh', terminal: 'pwsh',
  ask_user: 'ask_user_question', ask_followup_question: 'ask_user_question', askuserquestion: 'ask_user_question',
  task: 'subagent', agent: 'subagent', todowrite: 'todo_write', webfetch: 'web_fetch', websearch: 'web_search',
  exitplanmode: 'exit_plan_mode',
};
export const NOMES_APELIDOS = Object.keys(APELIDOS);

const txt = (v: unknown) => (v === undefined || v === null ? undefined : String(v));

/* Nome e argumentos no formato canonico (aceita os parametros antigos). */
export function canonica(nome: string, args: Record<string, unknown>): { nome: string; args: Record<string, unknown> } {
  let n = nome.trim();
  const baixo = n.toLowerCase();
  if (!NOMES_BASE.has(n) && !n.startsWith('mcp__')) n = APELIDOS[baixo] || APELIDOS[baixo.replace(/[_-]/g, '')] || (NOMES_BASE.has(baixo) ? baixo : n);
  const a: Record<string, unknown> = { ...(args || {}) };
  const mover = (de: string, para: string) => { if (a[para] === undefined && a[de] !== undefined) a[para] = a[de]; delete a[de]; };
  if (['read', 'write', 'edit', 'lsp'].includes(n)) { mover('path', 'file_path'); mover('filePath', 'file_path'); mover('filename', 'file_path'); mover('file', 'file_path'); }
  if (n === 'read') {
    if (a.offset === undefined && a.start_line !== undefined) a.offset = a.start_line;
    if (a.limit === undefined && a.end_line !== undefined) a.limit = Math.max(1, Number(a.end_line) - Number(a.offset || 1) + 1);
    delete a.start_line; delete a.end_line;
  }
  if (n === 'edit') { mover('old_text', 'old_string'); mover('new_text', 'new_string'); mover('oldString', 'old_string'); mover('newString', 'new_string'); mover('old_str', 'old_string'); mover('new_str', 'new_string'); }
  if (n === 'write') mover('text', 'content');
  if (n === 'pwsh') {
    mover('cmd', 'command');
    if (a.timeoutMs === undefined && a.timeout_s !== undefined) a.timeoutMs = Number(a.timeout_s) * 1000;
    if (a.timeoutMs === undefined && a.timeout !== undefined) a.timeoutMs = Number(a.timeout) < 1000 ? Number(a.timeout) * 1000 : Number(a.timeout);
    delete a.timeout_s; delete a.timeout;
    mover('background', 'run_in_background'); mover('cwd', 'workdir');
  }
  if (n.startsWith('job_')) { mover('id', 'job_id'); mover('jobId', 'job_id'); }
  if (n === 'web_search') {
    if (a.queries === undefined) a.queries = a.query !== undefined ? [a.query] : a.q !== undefined ? [a.q] : undefined;
    if (typeof a.queries === 'string') a.queries = [a.queries];
    delete a.query; delete a.q;
  }
  if (n === 'ask_user_question' && !Array.isArray(a.questions) && a.question !== undefined) {
    a.questions = [{ id: 'q1', question: a.question, options: (Array.isArray(a.options) ? a.options : []).map((o) => (typeof o === 'string' ? { label: o } : o)) }];
    delete a.question; delete a.options;
  }
  if (n === 'subagent') { mover('task', 'prompt'); if (!a.description) a.description = String(a.prompt || '').slice(0, 40); }
  if (n === 'grep') { mover('query', 'pattern'); mover('regex', 'pattern'); mover('glob', 'include'); }
  return { nome: n, args: a };
}

/* ------------------------------------------------------------ caminhos */
let dirSaida = '';                        // arquivos com a saida completa (spill)
const extrasLeitura: string[] = [];       // pastas fora do projeto que o read/grep alcancam
export function configurar(dirSpill: string, outros: string[] = []) {
  dirSaida = dirSpill;
  fs.mkdirSync(dirSpill, { recursive: true });
  extrasLeitura.length = 0;
  extrasLeitura.push(path.resolve(dirSpill), ...outros.map((x) => path.resolve(x)));
}

const dentro = (base: string, abs: string) => { const r = path.relative(base, abs); return !r.startsWith('..') && !path.isAbsolute(r); };

/* Caminho do modelo -> absoluto dentro do projeto (ou, para leitura, dentro
 * das pastas de saida completa do Nous Code). */
export function resolver(raiz: string, p: unknown, leitura = false): string {
  let rel = String(p ?? '.').trim().replace(/^["']|["']$/g, '') || '.';
  if (!(path.isAbsolute(rel) && !/^[\\/]/.test(rel))) rel = rel.replace(/^[\\/]+/, '');
  const abs = path.resolve(raiz, rel);
  if (dentro(raiz, abs)) return abs;
  if (leitura && extrasLeitura.some((b) => dentro(b, abs))) return abs;
  throw new Error('path is outside the project folder: ' + String(p));
}
export function relativo(raiz: string, abs: string): string {
  if (!dentro(raiz, abs)) return abs;
  return path.relative(raiz, abs).split(path.sep).join('/') || '.';
}

function textoDe(abs: string, mostra: string): string {
  let st: fs.Stats;
  try { st = fs.statSync(abs); } catch { throw new Error(`cannot read "${mostra}": not found`); }
  if (!st.isFile()) throw new Error(`cannot read "${mostra}": not a regular file`);
  if (st.size > 10_000_000) throw new Error(`cannot read "${mostra}": file too large (${Math.round(st.size / 1e6)} MB)`);
  const buf = fs.readFileSync(abs);
  if (buf.subarray(0, 8192).includes(0)) throw new Error(`cannot read "${mostra}": binary file`);
  return buf.toString('utf8');
}

/* ------------------------------------------------------------ saida grande -> arquivo (dsh-spill-policy) */
let seqSaida = 0;
export function guardar(sessao: string, nome: string, conteudo: string): string | null {
  if (!dirSaida) return null;
  try {
    const dir = path.join(dirSaida, sessao.replace(/[^\w-]/g, '') || 'x');
    fs.mkdirSync(dir, { recursive: true });
    const arq = path.join(dir, `${nome.replace(/[^\w-]/g, '_')}-${Date.now().toString(36)}${++seqSaida}.txt`);
    fs.writeFileSync(arq, conteudo, 'utf8');
    return arq;
  } catch { return null; }
}

/* Corta o resultado que volta ao modelo: comeco + [...] + fim, e a saida
 * inteira fica num arquivo que o modelo pode ler com read/grep. */
export function paraModelo(t: string, sessao = '', nome = 'resultado'): string {
  if (t.length <= MAX_SAIDA_MODELO) return t;
  const arq = sessao ? guardar(sessao, nome, t) : null;
  const cabeca = Math.ceil((MAX_SAIDA_MODELO - 400) / 2), cauda = Math.floor((MAX_SAIDA_MODELO - 400) / 2);
  const omitidos = Buffer.byteLength(t.slice(cabeca, t.length - cauda), 'utf8');
  return t.slice(0, cabeca) + '\n\n[...]\n\n' + t.slice(-cauda) + '\n\n(' + `Omitted ${omitidos} bytes.` +
    (arq ? ` Full formatted result stored at: ${arq}. Use read with offset/limit, or grep this path to search within it.)` : ')');
}

/* ------------------------------------------------------------ read */
/* Formato do dsh: <path>/<type>/<content> com "N: texto" e um rodape. */
export function ler(raiz: string, a: Record<string, unknown>): string {
  const fp = txt(a.file_path);
  if (!fp || !fp.trim()) throw new Error('file_path must be a non-empty string');
  const abs = resolver(raiz, fp, true);
  const mostra = relativo(raiz, abs);
  const offset = a.offset === undefined || a.offset === null || a.offset === '' ? 1 : Number(a.offset);
  const limit = a.limit === undefined || a.limit === null || a.limit === '' ? READ_LIMIT : Number(a.limit);
  if (!Number.isInteger(offset) || offset < 1) throw new Error('offset must be a positive integer');
  if (!Number.isInteger(limit) || limit < 1) throw new Error('limit must be a positive integer');
  if (limit > READ_LIMIT) throw new Error(`limit must be less than or equal to ${READ_LIMIT}`);
  const linhas = textoDe(abs, mostra).split('\n').map((l) => l.replace(/\r$/, ''));
  if (linhas.length > 1 && linhas[linhas.length - 1] === '') linhas.pop();
  const total = linhas[0] === '' && linhas.length === 1 ? 0 : linhas.length;
  if (offset > total && !(total === 0 && offset === 1)) throw new Error(`offset ${offset} is out of range for "${mostra}" (${total} lines)`);
  const out: string[] = [];
  let bytes = 0, cortadoPorBytes = false, fim = offset - 1;
  for (let i = offset - 1; i < total && out.length < limit; i++) {
    let l = linhas[i];
    if (l.length > READ_MAX_LINE) l = l.substring(0, READ_MAX_LINE) + `... (line truncated to ${READ_MAX_LINE} chars)`;
    const linha = `${i + 1}: ${l}`;
    const b = Buffer.byteLength(linha, 'utf8') + (out.length ? 1 : 0);
    if (bytes + b > READ_MAX_BYTES && out.length) { cortadoPorBytes = true; break; }
    bytes += b;
    out.push(linha);
    fim = i + 1;
  }
  const rodape = cortadoPorBytes ? `(Output capped. Showing lines ${offset}-${fim}. Use offset=${fim + 1} to continue.)`
    : fim < total ? `(Showing lines ${offset}-${fim} of ${total}. Use offset=${fim + 1} to continue.)`
      : `(End of file - total ${total} lines)`;
  const corpo = out.length ? out.join('\n') + '\n\n' + rodape : rodape;
  return `<path>${mostra}</path>\n<type>file</type>\n<content>\n${corpo}\n</content>`;
}

/* ------------------------------------------------------------ list_files (nosso) */
export function listar(raiz: string, a: Record<string, unknown>): string {
  const base = resolver(raiz, a.path);
  const prof = Math.max(1, Math.min(4, Number(a.depth) || 2));
  const linhas: string[] = [];
  let total = 0;
  function andar(dir: string, nivel: number, recuo: string) {
    let itens: fs.Dirent[];
    try { itens = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    itens.sort((x, y) => (Number(y.isDirectory()) - Number(x.isDirectory())) || x.name.localeCompare(y.name));
    for (const it of itens) {
      if (total >= 300) return;
      if (it.isDirectory() && IGNORAR.has(it.name)) continue;
      total++;
      linhas.push(recuo + it.name + (it.isDirectory() ? '/' : ''));
      if (it.isDirectory() && nivel < prof) andar(path.join(dir, it.name), nivel + 1, recuo + '  ');
    }
  }
  andar(base, 1, '');
  if (total >= 300) linhas.push('... (list cut at 300 entries; pass path to look inside one folder)');
  return (relativo(raiz, base) + '/\n' + linhas.join('\n')).trim();
}

/* ------------------------------------------------------------ glob */
/* Padrao glob -> RegExp: ** (qualquer pasta), * (sem /), ?, {a,b}, [abc]. */
export function globParaRegex(g: string, maiusculas = false): RegExp {
  let r = '';
  const p = g.replace(/\\/g, '/').replace(/^\.\//, '');
  for (let i = 0; i < p.length; i++) {
    const c = p[i];
    if (c === '*') {
      if (p[i + 1] === '*') {
        const barra = p[i + 2] === '/';
        r += barra ? '(?:.*/)?' : '.*';
        i += barra ? 2 : 1;
      } else r += '[^/]*';
    } else if (c === '?') r += '[^/]';
    else if (c === '{') {
      const f = p.indexOf('}', i);
      if (f < 0) { r += '\\{'; continue; }
      r += '(?:' + p.slice(i + 1, f).split(',').map((x) => x.replace(/[.+^$()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*')).join('|') + ')';
      i = f;
    } else if (c === '[') {
      const f = p.indexOf(']', i);
      if (f < 0) { r += '\\['; continue; }
      r += '[' + p.slice(i + 1, f).replace(/^!/, '^').replace(/\\/g, '\\\\') + ']';
      i = f;
    } else r += /[.+^$()|\]\\]/.test(c) ? '\\' + c : c;
  }
  return new RegExp('^' + r + '$', maiusculas ? '' : 'i');
}

/* Arquivos sob "base" (sem as pastas ignoradas), com o mtime. */
function arquivosDe(base: string, gitignore?: (rel: string) => boolean, raiz = base): { abs: string; rel: string; mt: number }[] {
  const out: { abs: string; rel: string; mt: number }[] = [];
  const andar = (dir: string) => {
    let itens: fs.Dirent[];
    try { itens = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const it of itens) {
      const abs = path.join(dir, it.name);
      const rel = path.relative(raiz, abs).split(path.sep).join('/');
      if (it.isDirectory()) { if (!IGNORAR.has(it.name) && !(gitignore && gitignore(rel + '/'))) andar(abs); continue; }
      if (!it.isFile() || (gitignore && gitignore(rel))) continue;
      let mt = 0;
      try { mt = fs.statSync(abs).mtimeMs; } catch { /* sumiu */ }
      out.push({ abs, rel, mt });
      if (out.length > 50_000) return;
    }
  };
  if (fs.existsSync(base) && fs.statSync(base).isFile()) {
    out.push({ abs: base, rel: path.relative(raiz, base).split(path.sep).join('/'), mt: fs.statSync(base).mtimeMs });
  } else andar(base);
  return out;
}

export function glob(raiz: string, a: Record<string, unknown>, sessao = ''): string {
  const pad = String(a.pattern ?? '').trim();
  if (!pad) throw new Error('pattern must be a non-empty string');
  if (a.path !== undefined && a.path !== null && !String(a.path).trim()) throw new Error('path must be a non-empty string when given');
  const base = resolver(raiz, a.path ?? '.', true);
  const re = globParaRegex(pad.includes('/') ? pad.replace(/^\.\//, '') : '**/' + pad);
  const achados = arquivosDe(base).filter((x) => re.test(path.relative(base, x.abs).split(path.sep).join('/')))
    .sort((x, y) => y.mt - x.mt).map((x) => relativo(raiz, x.abs));
  if (!achados.length) return 'No files found';
  if (achados.length <= GLOB_MAX) return achados.join('\n');
  const arq = sessao ? guardar(sessao, 'glob-results', achados.join('\n')) : null;
  const rec = arq ? `Full sorted result stored at: ${arq}. Use read with offset/limit, or grep this path to search within it.`
    : 'The complete result could not be saved; narrow pattern or path to see more.';
  return achados.slice(0, GLOB_MAX).join('\n') + `\n\n(Showing ${GLOB_MAX} of ${achados.length} paths. ${rec})`;
}

/* ------------------------------------------------------------ grep */
/* .gitignore da raiz, do jeito simples: padroes sem "!" (o grep do dsh, via
 * ripgrep, respeita o .gitignore). */
function lerGitignore(raiz: string): ((rel: string) => boolean) | undefined {
  let t: string;
  try { t = fs.readFileSync(path.join(raiz, '.gitignore'), 'utf8'); } catch { return undefined; }
  // cada pasta e' testada ao descer a arvore, entao basta casar o proprio caminho
  const res: { re: RegExp; soPasta: boolean }[] = [];
  for (let l of t.split(/\r?\n/)) {
    l = l.trim();
    if (!l || l.startsWith('#') || l.startsWith('!')) continue;
    const soPasta = l.endsWith('/');
    l = l.replace(/\/+$/, '');
    const ancorado = l.startsWith('/') || l.includes('/');
    try { res.push({ re: globParaRegex(ancorado ? l.replace(/^\//, '') : '**/' + l), soPasta }); } catch { /* padrao estranho */ }
  }
  return res.length ? (rel: string) => {
    const pasta = rel.endsWith('/');
    const r = rel.replace(/\/$/, '');
    return res.some((x) => (!x.soPasta || pasta) && x.re.test(r));
  } : undefined;
}

export function buscar(raiz: string, a: Record<string, unknown>, sessao = ''): string {
  const pad = String(a.pattern ?? '');
  if (!pad) throw new Error('pattern must be a non-empty string');
  if (a.path !== undefined && a.path !== null && !String(a.path).trim()) throw new Error('path must be a non-empty string when given');
  const inc = a.include === undefined || a.include === null || a.include === '' ? '' : String(a.include).trim();
  if (inc.startsWith('!')) throw new Error('include must be a positive glob filter; negated patterns ("!…") are not supported');
  if (inc && /,/.test(inc) && !/\{.*,.*\}/.test(inc)) throw new Error('include must be one glob, not a comma-separated list (use {a,b} alternation instead)');
  const base = resolver(raiz, a.path ?? '.', true);
  let re: RegExp;
  const flags = /[A-Z]/.test(pad.replace(/\\[A-Za-z]/g, '')) ? '' : 'i';  // smart case
  try { re = new RegExp(pad, flags); } catch (e) { throw new Error('grep pattern rejected: ' + (e instanceof Error ? e.message : String(e))); }
  const filtro = inc ? globParaRegex(inc.includes('/') ? inc : '**/' + inc) : null;
  const gi = dentro(raiz, base) ? lerGitignore(raiz) : undefined;
  const porArquivo = new Map<string, string[]>();
  let total = 0;
  for (const f of arquivosDe(base, gi, dentro(raiz, base) ? raiz : base)) {
    if (filtro && !filtro.test(f.rel)) continue;
    let st: fs.Stats;
    try { st = fs.statSync(f.abs); } catch { continue; }
    if (st.size > 2_000_000) continue;
    let t: string;
    try { const buf = fs.readFileSync(f.abs); if (buf.subarray(0, 8192).includes(0)) continue; t = buf.toString('utf8'); } catch { continue; }
    const ls = t.split('\n');
    for (let i = 0; i < ls.length; i++) {
      const l = ls[i].replace(/\r$/, '');
      if (!re.test(l)) continue;
      const k = relativo(raiz, f.abs);
      if (!porArquivo.has(k)) porArquivo.set(k, []);
      porArquivo.get(k)!.push(`Line ${i + 1}: ${l.length > 2000 ? l.slice(0, 2000) + ' (line truncated)' : l}`);
      total++;
    }
    if (total > 20_000) break;
  }
  if (!total) return 'No matches found';
  const corpo = (lim: number) => {
    const blocos: string[] = [];
    let n = 0;
    for (const [k, ls] of porArquivo) {
      if (n >= lim) break;
      const pega = ls.slice(0, lim - n);
      n += pega.length;
      blocos.push(k + '\n' + pega.join('\n'));
    }
    return blocos.join('\n\n');
  };
  if (total <= GREP_MAX) return `Found ${total} ${total === 1 ? 'match' : 'matches'}\n\n` + corpo(GREP_MAX);
  const arq = sessao ? guardar(sessao, 'grep-results', `Found ${total} matches\n\n` + corpo(Infinity)) : null;
  const rec = arq ? `Full grep result stored at: ${arq}. Use read with offset/limit, or grep this path to search within it.`
    : 'The complete result could not be saved; narrow pattern, path, or include to see more.';
  return `Found ${GREP_MAX} of ${total} matches\n\n` + corpo(GREP_MAX) + `\n\n(${rec})`;
}

/* ------------------------------------------------------------ edit */
/* Calcula o arquivo novo de um edit sem gravar (para mostrar o diff antes).
 * Literal como no dsh; quando nao acha, tenta o que modelo pequeno costuma
 * errar: copiar com os numeros de linha do read ("12: ") ou com outro recuo. */
export function aplicarEdicao(atual: string, velho: string, novo: string, todas = false, mostra = 'the file'): string {
  if (!velho) throw new Error('old_string must be a non-empty string. To add text, put an existing line in old_string and repeat it in new_string with the new text, or use write for the whole file');
  if (velho === novo) throw new Error('old_string and new_string must differ');
  const crlf = atual.includes('\r\n');
  const txt = crlf ? atual.replace(/\r\n/g, '\n') : atual;
  let v = velho.replace(/\r\n/g, '\n');
  let n = novo.replace(/\r\n/g, '\n');
  const volta = (s: string) => (crlf ? s.replace(/\n/g, '\r\n') : s);
  let quantas = txt.split(v).length - 1;
  if (quantas === 0) {
    // copiado com os numeros do read ("12: " ou o antigo "12| ")?
    const linhasV = v.split('\n').filter((l) => l.trim());
    for (const re of [/^\s*\d+: ?/, /^\s*\d+\| ?/]) {
      if (linhasV.length && linhasV.every((l) => re.test(l))) {
        const sem = (s: string) => s.split('\n').map((l) => l.replace(re, '')).join('\n');
        v = sem(v);
        if (n.split('\n').filter((l) => l.trim()).every((l) => re.test(l))) n = sem(n);
        quantas = txt.split(v).length - 1;
        break;
      }
    }
  }
  if (quantas === 0) {
    // mesma sequencia de linhas, so' o recuo/espacos diferentes
    const alvo = v.split('\n').map((l) => l.trim());
    while (alvo.length && !alvo[alvo.length - 1]) alvo.pop();
    while (alvo.length && !alvo[0]) alvo.shift();
    const ls = txt.split('\n');
    const achou: number[] = [];
    if (alvo.length) for (let i = 0; i + alvo.length <= ls.length; i++) {
      if (alvo.every((l, k) => ls[i + k].trim() === l)) achou.push(i);
    }
    if (achou.length === 1 || (achou.length > 1 && todas)) {
      const recuoModelo = (v.split('\n').find((l) => l.trim()) || '').match(/^\s*/)![0];
      let res = ls.slice();
      for (const i of achou.slice().reverse()) {
        const recuo = (ls[i].match(/^\s*/) || [''])[0];
        const novas = n.replace(/^\n+|\n+$/g, '').split('\n').map((l) => (l.startsWith(recuoModelo) ? recuo + l.slice(recuoModelo.length) : l));
        res = res.slice(0, i).concat(n === '' ? [] : novas, res.slice(i + alvo.length));
      }
      return volta(res.join('\n'));
    }
    if (achou.length > 1) throw new Error(`old_string matched ${achou.length} times in "${mostra}"; provide a more specific old_string or set replace_all to true`);
    throw new Error(`old_string was not found in "${mostra}". Read the file again and copy the text exactly (without the line numbers)`);
  }
  if (quantas > 1 && !todas) throw new Error(`old_string matched ${quantas} times in "${mostra}"; provide a more specific old_string or set replace_all to true`);
  return volta(todas ? txt.split(v).join(n) : txt.replace(v, () => n));
}

/* Diff de linhas (LCS depois de tirar o comeco e o fim iguais), com 3 linhas de
 * contexto. Formato: "@@ -a +b @@", " igual", "-saiu", "+entrou". */
export function diff(antes: string, depois: string): { texto: string; mais: number; menos: number } {
  const a = antes ? antes.replace(/\r\n/g, '\n').split('\n') : [];
  const b = depois.replace(/\r\n/g, '\n').split('\n');
  let ini = 0;
  while (ini < a.length && ini < b.length && a[ini] === b[ini]) ini++;
  let fa = a.length, fb = b.length;
  while (fa > ini && fb > ini && a[fa - 1] === b[fb - 1]) { fa--; fb--; }
  const ma = a.slice(ini, fa), mb = b.slice(ini, fb);
  const ops: [string, string][] = [];
  if (ma.length * mb.length > 4_000_000) {
    ma.forEach((l) => ops.push(['-', l])); mb.forEach((l) => ops.push(['+', l]));
  } else {
    const L = Array.from({ length: ma.length + 1 }, () => new Uint32Array(mb.length + 1));
    for (let i = ma.length - 1; i >= 0; i--) for (let j = mb.length - 1; j >= 0; j--) {
      L[i][j] = ma[i] === mb[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    }
    let i = 0, j = 0;
    while (i < ma.length || j < mb.length) {
      if (i < ma.length && j < mb.length && ma[i] === mb[j]) { ops.push([' ', ma[i]]); i++; j++; }
      else if (i < ma.length && (j >= mb.length || L[i + 1][j] >= L[i][j + 1])) { ops.push(['-', ma[i]]); i++; }  // o que sai vem antes
      else { ops.push(['+', mb[j]]); j++; }
    }
  }
  const antesCtx = a.slice(Math.max(0, ini - 3), ini).map((l) => ' ' + l);
  const depoisCtx = a.slice(fa, fa + 3).map((l) => ' ' + l);
  const corpo = ops.map(([s, l]) => s + l);
  const mais = ops.filter((o) => o[0] === '+').length, menos = ops.filter((o) => o[0] === '-').length;
  const cab = `@@ -${Math.max(1, ini - 2)} +${Math.max(1, ini - 2)} @@`;
  let texto = [cab].concat(antesCtx, corpo, depoisCtx).join('\n');
  if (texto.length > 30000) texto = texto.slice(0, 30000) + '\n... (diff cortado)';
  return { texto, mais, menos };
}

/* ------------------------------------------------------------ comandos (usado pelo IDE) */
export function rodar(raiz: string, comando: string, segundos: number, sinal: AbortSignal):
  Promise<{ codigo: number | null; saida: string; tempo: number }> {
  return new Promise((ok) => {
    const t0 = Date.now();
    const ps = spawn('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command',
      '[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference="SilentlyContinue"; ' + comando],
    { cwd: raiz, windowsHide: true, env: { ...process.env, NO_COLOR: '1', FORCE_COLOR: '0' } });
    let saida = '';
    const junta = (d: Buffer) => { if (saida.length < 200_000) saida += d.toString('utf8'); };
    ps.stdout.on('data', junta);
    ps.stderr.on('data', junta);
    const matar = () => { try { spawn('taskkill', ['/T', '/F', '/PID', String(ps.pid)], { windowsHide: true }); } catch { /* ja saiu */ } };
    const relogio = setTimeout(() => { saida += '\n[parado: passou de ' + segundos + 's]'; matar(); }, segundos * 1000);
    sinal.addEventListener('abort', matar, { once: true });
    ps.on('close', (codigo) => {
      clearTimeout(relogio);
      ok({ codigo, saida: saida.replace(/\x1b\[[0-9;]*m/g, ''), tempo: Date.now() - t0 });
    });
    ps.on('error', (e) => { clearTimeout(relogio); ok({ codigo: -1, saida: String(e), tempo: Date.now() - t0 }); });
  });
}

/* Le o arquivo atual (ou null se ainda nao existe) para snapshot/diff. */
export function conteudoAtual(abs: string): string | null {
  try { return fs.readFileSync(abs, 'utf8'); } catch { return null; }
}
export function gravar(abs: string, conteudo: string) {
  fs.mkdirSync(path.dirname(abs), { recursive: true });
  fs.writeFileSync(abs, conteudo, 'utf8');
}
