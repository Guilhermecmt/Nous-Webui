// Todo comando do agente roda como um "job" (como no DeepSeek Harness,
// dsh-tool-pwsh + dsh-tool-jobs, MIT, (c) 2026 DeepSeek): em primeiro plano o
// agente espera ate' o tempo limite; passou dele, o comando nao morre, vai para
// segundo plano. job_output le so' o que saiu desde a leitura anterior, e quando
// um job termina sem o agente ter visto o fim, ele recebe um aviso no proximo
// passo. A saida inteira vai para um arquivo; o modelo ve o fim.

import fs from 'node:fs';
import path from 'node:path';
import { spawn, type ChildProcess } from 'node:child_process';

export type Status = 'running' | 'stopping' | 'completed' | 'killed' | 'failed';
export type Job = {
  id: string; comando: string; descricao: string; pasta: string; inicio: number; fim?: number; codigo?: number | null;
  arquivo: string; saida: string; total: number; lido: number; proc: ChildProcess;
  morto: boolean;          // job_kill (ou parar) pediu para encerrar
  visto: boolean;          // o modelo ja' recebeu o resultado final (nao precisa de aviso)
  primeiroPlano: boolean;  // ainda dentro da espera de um pwsh em primeiro plano
};

const MAX_MEMORIA = 256 * 1024;
const MAX_POR_SESSAO = 10;
const jobs = new Map<string, Map<string, Job>>();  // sessao -> id -> job
let dirLogs = '';
export function configurar(dir: string) { dirLogs = dir; fs.mkdirSync(dir, { recursive: true }); }
export function pasta() { return dirLogs; }

function limpar(s: string) { return s.replace(/\x1b\[[0-9;?]*[a-zA-Z]/g, '').replace(/\r\n/g, '\n'); }

export function iniciar(sessao: string, pastaTrabalho: string, comando: string, descricao = ''): Job {
  const daSessao = jobs.get(sessao) || new Map<string, Job>();
  jobs.set(sessao, daSessao);
  const ativos = [...daSessao.values()].filter((j) => !j.fim).length;
  if (ativos >= MAX_POR_SESSAO) {
    throw new Error(`background job limit reached for this owner (limit: ${MAX_POR_SESSAO}); use job_kill to stop an unneeded job, wait for it to finish, then retry`);
  }
  const id = 'j' + (daSessao.size + 1);
  const arquivo = path.join(dirLogs, sessao + '-' + id + '.log');
  const proc = spawn('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command',
    '[Console]::OutputEncoding=[Text.Encoding]::UTF8; $ProgressPreference="SilentlyContinue"; ' + comando],
  { cwd: pastaTrabalho, windowsHide: true, env: { ...process.env, NO_COLOR: '1', FORCE_COLOR: '0' } });
  const job: Job = { id, comando, descricao, pasta: pastaTrabalho, inicio: Date.now(), arquivo, saida: '', total: 0, lido: 0, proc,
    morto: false, visto: false, primeiroPlano: true };
  const log = fs.createWriteStream(arquivo);
  const junta = (d: Buffer) => {
    const t = limpar(d.toString('utf8'));
    log.write(t);
    job.total += t.length;
    job.saida = (job.saida + t).slice(-MAX_MEMORIA);
  };
  proc.stdout?.on('data', junta);
  proc.stderr?.on('data', junta);
  proc.on('close', (c) => { job.fim = Date.now(); job.codigo = c; log.end(); });
  proc.on('error', (e) => { job.fim = Date.now(); job.codigo = -1; junta(Buffer.from(String(e))); log.end(); });
  daSessao.set(id, job);
  return job;
}

/* Espera o job terminar ate' "ms"; devolve se terminou. Parar a conversa mata o job. */
export function esperar(job: Job, ms: number, sinal: AbortSignal): Promise<boolean> {
  if (job.fim) return Promise.resolve(true);
  return new Promise((ok) => {
    const t = setTimeout(() => ok(false), ms);
    job.proc.on('close', () => { clearTimeout(t); ok(true); });
    sinal.addEventListener('abort', () => { clearTimeout(t); matar(job); ok(true); }, { once: true });
  });
}

export function matar(job: Job) {
  job.morto = true;
  if (job.fim) return;
  try { spawn('taskkill', ['/T', '/F', '/PID', String(job.proc.pid)], { windowsHide: true }); } catch { /* ja saiu */ }
}

export function pegar(sessao: string, id: string): Job {
  const k = String(id ?? '').trim();
  if (!k) throw new Error(`invalid job_id: expected a non-empty string, got ${JSON.stringify(id)}`);
  const j = jobs.get(sessao)?.get(k);
  if (!j) throw new Error('unknown job ' + k);
  return j;
}
export function listar(sessao: string): Job[] { return [...(jobs.get(sessao)?.values() || [])]; }
export function encerrarSessao(sessao: string) { for (const j of listar(sessao)) matar(j); }

export function status(j: Job): Status {
  if (!j.fim) return j.morto ? 'stopping' : 'running';
  if (j.morto) return 'killed';
  return j.codigo === -1 ? 'failed' : 'completed';
}
/* "[status: completed, exit code: 0]" (dsh-tool-jobs). */
export function linhaStatus(j: Job): string {
  const s = status(j);
  const det = !j.fim ? (Math.round((Date.now() - j.inicio) / 1000) + 's') : j.morto ? 'killed before exit' : 'exit code: ' + (j.codigo ?? 0);
  return `[status: ${s}, ${det}]`;
}

/* O que saiu desde a ultima leitura (e marca como lido). */
export function novidades(j: Job): string {
  const inicioMem = j.total - j.saida.length;
  let perdido = '';
  if (j.lido < inicioMem) { perdido = `[some output was dropped from memory; full output: ${j.arquivo}]\n`; j.lido = inicioMem; }
  const d = j.saida.slice(j.lido - inicioMem);
  j.lido = j.total;
  if (j.fim) j.visto = true;
  return perdido + d;
}

/* Jobs que terminaram sem o modelo ter visto o fim: avisa uma vez. */
export function avisosPendentes(sessao: string): string[] {
  const out: string[] = [];
  for (const j of listar(sessao)) {
    if (!j.fim || j.visto || j.morto || j.primeiroPlano) continue;
    j.visto = true;
    out.push(`background job ${j.id} (pwsh: ${j.descricao || j.comando.slice(0, 60)}) finished ${linhaStatus(j)}. Read its output with job_output.`);
  }
  return out;
}
