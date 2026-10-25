// Tarefas separadas (copia do projeto em worktree do Git): criar, revisar,
// aplicar, recusar quando o projeto mudou, descartar. Git de verdade, pastas temporarias.
import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import * as T from '../tarefas.ts';

const sh = (cwd: string, ...args: string[]) =>
  execFileSync('git', ['-c', 'user.name=Teste', '-c', 'user.email=t@t', ...args], { cwd, encoding: 'utf8', windowsHide: true });
const ler = (...p: string[]) => fs.readFileSync(path.join(...p), 'utf8');
const esc = (...p: string[]) => (c: string) => fs.writeFileSync(path.join(...p), c);

before(() => T.configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-tar-dados-'))));

function repo(arquivos: Record<string, string> = { 'a.txt': 'um\ndois\ntres\n', 'b.txt': 'b\n', 'sub/c.txt': 'c\n' }) {
  const r = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-tar-'));
  sh(r, 'init', '-q'); sh(r, 'config', 'core.autocrlf', 'false');   // nao depender da configuracao desta maquina
  for (const [n, c] of Object.entries(arquivos)) { fs.mkdirSync(path.dirname(path.join(r, n)), { recursive: true }); fs.writeFileSync(path.join(r, n), c); }
  sh(r, 'add', '-A'); sh(r, 'commit', '-q', '-m', 'inicio');
  return r;
}

test('pasta sem Git e repositorio sem commit: mensagem simples, nada criado', async () => {
  const sem = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-tar-sem-'));
  await assert.rejects(T.criar(sem, 'x'), /precisa estar no Git/);
  const vazio = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-tar-vazio-'));
  sh(vazio, 'init', '-q');
  await assert.rejects(T.criar(vazio, 'x'), /nenhum commit/);
});

test('criar, mudar na copia, revisar e aplicar: o projeto so muda no aplicar', async () => {
  const r = repo();
  esc(r, 'a.txt')('um\ndois\ntres\nquatro\n');                 // mudanca nao commitada: tem que ir para a copia
  fs.writeFileSync(path.join(r, 'solto.txt'), 'novo no projeto\n');   // nao rastreado: avisa
  const { tarefa: t, avisos } = await T.criar(r, 'Mexer nos textos');
  assert.ok(fs.existsSync(path.join(t.pasta, 'b.txt')));
  assert.equal(ler(t.pasta, 'a.txt'), 'um\ndois\ntres\nquatro\n');
  assert.ok(!fs.existsSync(path.join(t.pasta, 'solto.txt')));
  assert.ok(avisos.some((a) => /arquivos novos/.test(a)));
  assert.ok(T.abertas(r).some((x) => x.id === t.id));
  assert.equal(T.dePasta(path.join(t.pasta, 'sub'))?.id, t.id);
  assert.deepEqual((await T.revisar(t.id)).arquivos, []);

  // o que o agente faria na copia
  esc(t.pasta, 'a.txt')('um\nDOIS\ntres\nquatro\ncinco\n');
  fs.writeFileSync(path.join(t.pasta, 'novo.txt'), 'x\ny\n');
  fs.unlinkSync(path.join(t.pasta, 'b.txt'));
  const rev = await T.revisar(t.id);
  const por = Object.fromEntries(rev.arquivos.map((a) => [a.arquivo, a]));
  assert.deepEqual(por['a.txt'], { arquivo: 'a.txt', estado: 'mudou', mais: 2, menos: 1 });
  assert.deepEqual(por['novo.txt'], { arquivo: 'novo.txt', estado: 'novo', mais: 2, menos: 0 });
  assert.deepEqual(por['b.txt'], { arquivo: 'b.txt', estado: 'apagado', mais: 0, menos: 1 });
  assert.match(rev.diff, /\+DOIS/);
  // enquanto nao aplica, o projeto esta como estava
  assert.equal(ler(r, 'a.txt'), 'um\ndois\ntres\nquatro\n');
  assert.ok(fs.existsSync(path.join(r, 'b.txt')) && !fs.existsSync(path.join(r, 'novo.txt')));

  const ap = await T.aplicar(t.id);
  assert.equal(ap.ok, true);
  assert.equal(ler(r, 'a.txt'), 'um\nDOIS\ntres\nquatro\ncinco\n');
  assert.equal(ler(r, 'novo.txt'), 'x\ny\n');
  assert.ok(!fs.existsSync(path.join(r, 'b.txt')));
  assert.equal(ler(r, 'solto.txt'), 'novo no projeto\n');          // o que era do projeto fica
  // nada commitado: as mudancas aparecem no Git do projeto para a pessoa decidir
  assert.equal(sh(r, 'log', '--oneline').trim().split('\n').length, 1);
  assert.match(sh(r, 'status', '--porcelain'), /a\.txt/);
  // a copia e o ramo somem
  assert.ok(!fs.existsSync(t.raiz));
  assert.ok(!/nous-tarefa/.test(sh(r, 'branch', '--list')));
  assert.ok(!/copias/.test(sh(r, 'worktree', 'list')));
  assert.ok(!T.abertas(r).some((x) => x.id === t.id));
});

test('projeto mudou nos mesmos trechos: recusa sem tocar em nada; depois descarta', async () => {
  const r = repo();
  const { tarefa: t } = await T.criar(r, 'Conflito');
  esc(t.pasta, 'a.txt')('um\ndois da copia\ntres\n');
  esc(r, 'a.txt')('um\ndois do projeto\ntres\n');                 // a pessoa mexeu na mesma linha
  const ap = await T.aplicar(t.id);
  assert.equal(ap.ok, false);
  assert.match(ap.motivo!, /mudou nos mesmos trechos.*a\.txt.*Nada foi aplicado/s);
  assert.equal(ler(r, 'a.txt'), 'um\ndois do projeto\ntres\n');
  assert.ok(fs.existsSync(t.raiz), 'a copia continua para a pessoa decidir');
  await T.descartar(t.id);
  assert.ok(!fs.existsSync(t.raiz));
  assert.ok(!/nous-tarefa/.test(sh(r, 'branch', '--list')));
  assert.equal(ler(r, 'a.txt'), 'um\ndois do projeto\ntres\n');
});

test('mudancas em arquivos diferentes nao conflitam, mesmo com o projeto andando', async () => {
  const r = repo();
  const { tarefa: t } = await T.criar(r, 'Paralelo');
  esc(t.pasta, 'a.txt')('um\ndois\ntres\nquatro da copia\n');
  esc(r, 'b.txt')('b mudou no projeto\n');
  const ap = await T.aplicar(t.id);
  assert.equal(ap.ok, true);
  assert.equal(ler(r, 'a.txt'), 'um\ndois\ntres\nquatro da copia\n');
  assert.equal(ler(r, 'b.txt'), 'b mudou no projeto\n');
});

test('projeto numa subpasta do repositorio; commit dentro da copia nao atrapalha', async () => {
  const r = repo();
  const { tarefa: t } = await T.criar(path.join(r, 'sub'), 'Sub');
  assert.equal(path.relative(t.raiz, t.pasta), 'sub');
  esc(t.pasta, 'c.txt')('c editado\n');
  sh(t.raiz, 'add', '-A'); sh(t.raiz, 'commit', '-q', '-m', 'dentro da copia');
  fs.writeFileSync(path.join(t.pasta, 'd.txt'), 'd\n');
  const rev = await T.revisar(t.id);
  assert.deepEqual(rev.arquivos.map((a) => a.arquivo).sort(), ['sub/c.txt', 'sub/d.txt']);
  assert.equal((await T.aplicar(t.id)).ok, true);
  assert.equal(ler(r, 'sub/c.txt'), 'c editado\n');
  assert.equal(ler(r, 'sub/d.txt'), 'd\n');
});

test('arquivo com final de linha do Windows (autocrlf) continua assim depois de aplicar', async () => {
  const r = repo();
  sh(r, 'config', 'core.autocrlf', 'true');
  fs.writeFileSync(path.join(r, 'w.txt'), 'a\r\nb\r\nc\r\n');
  sh(r, 'add', '-A'); sh(r, 'commit', '-q', '-m', 'crlf');
  const { tarefa: t } = await T.criar(r, 'CRLF');
  assert.equal(ler(t.pasta, 'w.txt'), 'a\r\nb\r\nc\r\n');
  esc(t.pasta, 'w.txt')('a\r\nB\r\nc\r\nd\r\n');
  const ap = await T.aplicar(t.id);
  assert.equal(ap.ok, true, ap.motivo);
  assert.equal(ler(r, 'w.txt'), 'a\r\nB\r\nc\r\nd\r\n');
});

test('tarefa sem mudancas: aplicar encerra e limpa', async () => {
  const r = repo();
  const { tarefa: t } = await T.criar(r, 'Nada');
  const ap = await T.aplicar(t.id);
  assert.equal(ap.ok, true);
  assert.deepEqual(ap.arquivos, []);
  assert.ok(!fs.existsSync(t.raiz));
});
