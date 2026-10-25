// O servico de verdade (processo separado, porta de teste, NousData de teste):
// criar a tarefa separada, ver a conversa dela, aplicar/descartar pela API e o
// que acontece com as conversas. Git de verdade; o Ollama nao e' usado.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { spawn, execFileSync, type ChildProcess } from 'node:child_process';

const sh = (cwd: string, ...args: string[]) =>
  execFileSync('git', ['-c', 'user.name=Teste', '-c', 'user.email=t@t', ...args], { cwd, encoding: 'utf8', windowsHide: true });

let proc: ChildProcess;
let base = '';
let dados = '';

function portaLivre(): Promise<number> {
  const tenta = (p: number): Promise<number> => new Promise((ok, erro) => {
    const s = net.createServer();
    s.once('error', () => (p < 9399 ? ok(tenta(p + 1) as unknown as number) : erro(new Error('sem porta livre'))));
    s.listen(p, '127.0.0.1', () => s.close(() => ok(p)));
  });
  return tenta(9300 + Math.floor(Math.random() * 60));
}

before(async () => {
  const porta = await portaLivre();
  dados = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-srv-dados-'));
  base = 'http://127.0.0.1:' + porta;
  proc = spawn(process.execPath, ['servidor.ts'], { cwd: path.resolve(import.meta.dirname, '..'), windowsHide: true, stdio: 'ignore',
    env: { ...process.env, NOUS_CODE_PORT: String(porta), DATA_DIR: dados, NOUS_CODE_DIAGNOSTICOS: '0' } });
  for (let i = 0; i < 60; i++) {
    try { if ((await fetch(base + '/health')).ok) return; } catch { /* ainda subindo */ }
    await new Promise((ok) => setTimeout(ok, 250));
  }
  throw new Error('o servico nao subiu');
});
after(() => { proc?.kill(); });

const api = async (m: 'GET' | 'POST', u: string, corpo?: object) => {
  const r = await fetch(base + u, { method: m, headers: { 'Content-Type': 'application/json' }, body: corpo ? JSON.stringify(corpo) : undefined });
  return { status: r.status, dados: await r.json() as Record<string, any> };
};

function projeto() {
  const r = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-srv-proj-'));
  sh(r, 'init', '-q'); sh(r, 'config', 'core.autocrlf', 'false');
  fs.writeFileSync(path.join(r, 'app.js'), 'const v = 1;\n');
  sh(r, 'add', '-A'); sh(r, 'commit', '-q', '-m', 'inicio');
  return r;
}

test('tarefa separada pela API: copia, conversa isolada, revisar e aplicar; a conversa volta ao projeto', async () => {
  const r = projeto();
  const c = await api('POST', '/tarefas', { pasta: r, titulo: 'Trocar o valor' });
  assert.equal(c.status, 200, JSON.stringify(c.dados));
  const t = c.dados.tarefa;
  assert.equal(t.titulo, 'Trocar o valor');
  assert.ok(Array.isArray(c.dados.avisos));
  assert.ok(fs.existsSync(path.join(c.dados.pasta, 'app.js')));

  const s = (await api('GET', '/sessao?id=' + c.dados.id)).dados;
  assert.equal(s.tarefa.id, t.id);
  assert.equal(s.pasta, c.dados.pasta);
  // a conversa da copia aparece quando a pasta da copia e' aberta, e nao nos recentes
  assert.deepEqual((await api('GET', '/sessoes?pasta=' + encodeURIComponent(c.dados.pasta))).dados.map((x: any) => x.id), [c.dados.id]);
  assert.ok(!(await api('GET', '/pastas')).dados.some((p: any) => p.pasta === c.dados.pasta));
  assert.deepEqual((await api('GET', '/tarefas?pasta=' + encodeURIComponent(r))).dados.map((x: any) => x.id), [t.id]);

  fs.writeFileSync(path.join(c.dados.pasta, 'app.js'), 'const v = 2;\n');
  const rev = (await api('GET', '/tarefa/revisao?id=' + t.id)).dados;
  assert.deepEqual(rev.arquivos, [{ arquivo: 'app.js', estado: 'mudou', mais: 1, menos: 1 }]);
  assert.equal(fs.readFileSync(path.join(r, 'app.js'), 'utf8'), 'const v = 1;\n');

  const ap = await api('POST', '/tarefa/aplicar', { id: t.id });
  assert.equal(ap.dados.ok, true);
  assert.equal(path.resolve(ap.dados.origem), path.resolve(r));
  assert.equal(fs.readFileSync(path.join(r, 'app.js'), 'utf8'), 'const v = 2;\n');
  assert.ok(!fs.existsSync(c.dados.pasta));
  // a conversa foi para o projeto, sem a marca de copia
  const depois = (await api('GET', '/sessao?id=' + c.dados.id)).dados;
  assert.equal(depois.tarefa, null);
  assert.equal(path.resolve(depois.pasta), path.resolve(r));
  assert.ok(depois.eventos.some((e: any) => e.t === 'nota' && /foi aplicada ao projeto \(1 arquivo\)/.test(e.texto)));
  assert.deepEqual((await api('GET', '/tarefas?pasta=' + encodeURIComponent(r))).dados, []);
  assert.equal((await api('GET', '/tarefa/revisao?id=' + t.id)).status, 410);
});

test('descartar pela API apaga a copia e nao toca no projeto; pasta sem Git da mensagem simples', async () => {
  const r = projeto();
  const c = await api('POST', '/tarefas', { pasta: r, titulo: 'Experimento' });
  fs.writeFileSync(path.join(c.dados.pasta, 'app.js'), 'lixo\n');
  const d = await api('POST', '/tarefa/descartar', { id: c.dados.tarefa.id });
  assert.equal(d.dados.ok, true);
  assert.ok(!fs.existsSync(c.dados.pasta));
  assert.equal(fs.readFileSync(path.join(r, 'app.js'), 'utf8'), 'const v = 1;\n');
  assert.match(sh(r, 'branch', '--list'), /^\*? *\w+\s*$/);
  const sem = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-srv-sem-'));
  const x = await api('POST', '/tarefas', { pasta: sem, titulo: 'Sem git' });
  assert.notEqual(x.status, 200);
  assert.match(x.dados.erro, /precisa estar no Git/);
});

test('nao cria copia de uma copia', async () => {
  const r = projeto();
  const c = await api('POST', '/tarefas', { pasta: r, titulo: 'Base' });
  const dentro = await api('POST', '/tarefas', { pasta: c.dados.pasta, titulo: 'Copia da copia' });
  assert.equal(dentro.status, 400);
  assert.match(dentro.dados.erro, /já é uma cópia/);
  await api('POST', '/tarefa/descartar', { id: c.dados.tarefa.id });
});
