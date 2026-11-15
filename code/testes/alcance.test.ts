// Alcance (projeto | usuario | computador): ate' onde as ferramentas de arquivo
// vao, e quem pede OK quando o agente muda algo fora da pasta do projeto.
// A "pasta do usuario" e' um temporario (USERPROFILE de mentira).
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { ligarFalso, desligarFalso, configurarApoio, estado, chamar, resultados, rodar } from './apoio.ts';

process.env.NOUS_CODE_DIAGNOSTICOS = '0';
const casa = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-casa-'));
const fora = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-fora-'));   // fora da "pasta do usuario"
process.env.USERPROFILE = casa;

type Mod = typeof import('../agente.ts');
let A: Mod;
let F: typeof import('../ferramentas.ts');
before(async () => {
  await ligarFalso();
  await configurarApoio();
  A = await import('../agente.ts');
  F = await import('../ferramentas.ts');
});
after(() => desligarFalso());

function sessao(modo: 'leitura' | 'perguntar' | 'editar' | 'total', alcance: 'projeto' | 'usuario' | 'computador') {
  const raiz = fs.mkdtempSync(path.join(casa, 'proj-'));
  fs.writeFileSync(path.join(raiz, 'a.txt'), 'dentro\n');
  return { raiz, s: A.normalizar({ id: 'alc' + Math.random().toString(36).slice(2, 8), pasta: raiz, modelo: 'falso', modo, alcance, tituloAuto: false }) };
}

test('resolver: projeto recusa fora; usuario so\' dentro da pasta do usuario; computador vai a qualquer lugar; ~ e\' a pasta do usuario', () => {
  const raiz = fs.mkdtempSync(path.join(casa, 'proj-'));
  const naCasa = path.join(casa, 'Documentos', 'x.txt');
  const longe = path.join(fora, 'y.txt');
  assert.throws(() => F.resolver(raiz, naCasa), /outside the project folder/);
  assert.equal(F.resolver(raiz, naCasa, false, 'usuario'), naCasa);
  assert.throws(() => F.resolver(raiz, longe, false, 'usuario'), /outside the user folder/);
  assert.equal(F.resolver(raiz, longe, false, 'computador'), longe);
  assert.equal(F.resolver(raiz, '~/Documentos/x.txt', false, 'usuario'), naCasa);
  // sem alcance maior, "~" continua sendo so' um nome de pasta dentro do projeto
  assert.equal(F.resolver(raiz, '~/x.txt'), path.join(raiz, '~', 'x.txt'));
});

test('normalizar: alcance invalido vira projeto; tarefa separada fica sempre no projeto', () => {
  assert.equal(A.normalizar({ id: 'n1', pasta: casa, alcance: 'tudo' as never }).alcance, 'projeto');
  assert.equal(A.normalizar({ id: 'n2', pasta: casa }).alcance, 'projeto');
  assert.equal(A.normalizar({ id: 'n3', pasta: casa, alcance: 'computador', isolada: true }).alcance, 'projeto');
  assert.equal(A.normalizar({ id: 'n4', pasta: casa, alcance: 'usuario' }).alcance, 'usuario');
});

test('contexto de execucao conta ao modelo ate\' onde ele vai', () => {
  assert.match(A.contextoExecucao(sessao('perguntar', 'projeto').s), /file policy: workspace-write/);
  assert.match(A.contextoExecucao(sessao('editar', 'usuario').s), /user-folder-write[\s\S]*file changes outside it, commands/);
  const t = A.contextoExecucao(sessao('total', 'computador').s);
  assert.match(t, /full-access/);
  assert.match(t, /anywhere on this computer/);
  assert.match(t, /takes responsibility/);
});

test('alcance projeto: ler um arquivo fora do projeto e\' recusado', async () => {
  const { s } = sessao('total', 'projeto');
  const arq = path.join(fora, 'segredo.txt');
  fs.writeFileSync(arq, 'nao\n');
  estado.roteiro = [chamar('read', { file_path: arq }), 'ok'];
  const r = resultados(await rodar(A, s, 'leia'));
  assert.equal(r[0].ok, false);
  assert.match(String(r[0].saida), /outside the project folder/);
});

test('computador + editar: dentro do projeto muda sem perguntar; fora pede OK (marcado "fora") e a recusa vale', async () => {
  const { raiz, s } = sessao('editar', 'computador');
  const arq = path.join(fora, 'notas.txt');
  fs.writeFileSync(arq, 'velho\n');
  estado.roteiro = [chamar('read', { file_path: 'a.txt' }), chamar('edit', { file_path: 'a.txt', old_string: 'dentro', new_string: 'mudou' }),
    chamar('read', { file_path: arq }), chamar('edit', { file_path: arq, old_string: 'velho', new_string: 'novo' }), 'pronto'];
  const ev = await rodar(A, s, 'mude os dois', { arquivo: { ok: false } });
  const pedidos = ev.filter((e) => e.t === 'pede');
  assert.equal(pedidos.length, 1, 'so\' a mudanca de fora pede OK');
  assert.equal(pedidos[0].fora, true);
  assert.equal(fs.readFileSync(path.join(raiz, 'a.txt'), 'utf8'), 'mudou\n');
  assert.equal(fs.readFileSync(arq, 'utf8'), 'velho\n');
});

test('usuario + total: muda fora do projeto (na pasta do usuario) sem perguntar; fora da pasta do usuario continua recusado', async () => {
  const { s } = sessao('total', 'usuario');
  const naCasa = path.join(casa, 'lista.txt');
  const longe = path.join(fora, 'longe.txt');
  estado.roteiro = [chamar('write', { file_path: '~/lista.txt', content: 'oi\n' }), chamar('write', { file_path: longe, content: 'x' }), 'pronto'];
  const ev = await rodar(A, s, 'escreva');
  assert.equal(ev.filter((e) => e.t === 'pede').length, 0);
  assert.equal(fs.readFileSync(naCasa, 'utf8'), 'oi\n');
  const r = resultados(ev);
  assert.equal(r[1].ok, false);
  assert.match(String(r[1].saida), /outside the user folder/);
  assert.equal(fs.existsSync(longe), false);
});

test('desfazer volta o arquivo de fora do projeto, mesmo depois de o alcance diminuir', async () => {
  const { s } = sessao('total', 'computador');
  const arq = path.join(fora, 'desfaz.txt');
  fs.writeFileSync(arq, 'original\n');
  estado.roteiro = [chamar('read', { file_path: arq }), chamar('write', { file_path: arq, content: 'trocado\n' }), 'pronto'];
  await rodar(A, s, 'troque');
  assert.equal(fs.readFileSync(arq, 'utf8'), 'trocado\n');
  assert.equal(A.mudancas(s).length, 1);
  s.alcance = 'projeto';
  assert.deepEqual(A.desfazer(s), [arq]);
  assert.equal(fs.readFileSync(arq, 'utf8'), 'original\n');
});

test('somente leitura com alcance maior le fora do projeto, mas nao muda', async () => {
  const { s } = sessao('leitura', 'computador');
  const arq = path.join(fora, 'ler.txt');
  fs.writeFileSync(arq, 'conteudo\n');
  estado.roteiro = [chamar('read', { file_path: arq }), chamar('write', { file_path: arq, content: 'x' }), 'ok'];
  const r = resultados(await rodar(A, s, 'leia e mude'));
  assert.equal(r[0].ok, true);
  assert.match(String(r[0].saida), /conteudo/);
  assert.equal(r[1].ok, false);
  assert.equal(fs.readFileSync(arq, 'utf8'), 'conteudo\n');
});
