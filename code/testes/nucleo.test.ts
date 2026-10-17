// Testes do nucleo (sem modelo): leitura das chamadas, edicao, diff e caminhos.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chamadasNoTexto } from '../modelo.ts';
import { aplicarEdicao, diff, resolver, ler, NOMES } from '../ferramentas.ts';
import { anunciaSemFazer } from '../agente.ts';

test('chamada em JSON solto (jeito do qwen2.5-coder)', () => {
  const r = chamadasNoTexto('{\n  "name": "read_file",\n  "arguments": {\n    "path": "src/a.js"\n  }\n}', NOMES);
  assert.equal(r.chamadas.length, 1);
  assert.equal(r.chamadas[0].nome, 'read_file');
  assert.deepEqual(r.chamadas[0].args, { path: 'src/a.js' });
  assert.equal(r.resto, '');
});

test('chamada depois de um texto, dentro de ```json', () => {
  const r = chamadasNoTexto('Vou ler o arquivo:\n```json\n{"name": "read_file", "arguments": {"path": "x.ts"}}\n```', NOMES);
  assert.equal(r.chamadas[0].nome, 'read_file');
  assert.equal(r.resto, 'Vou ler o arquivo:');
});

test('<tool_call> e arguments como string', () => {
  const r = chamadasNoTexto('<tool_call>{"name": "search", "arguments": "{\\"pattern\\": \\"foo\\"}"}</tool_call>', NOMES);
  assert.deepEqual(r.chamadas[0].args, { pattern: 'foo' });
});

test('JSON que nao e chamada fica no texto', () => {
  const t = 'Exemplo de config: {"name": "meu-app", "version": "1.0"}';
  const r = chamadasNoTexto(t, NOMES);
  assert.equal(r.chamadas.length, 0);
  assert.equal(r.resto, t);
});

test('chaves dentro de strings nao quebram o JSON', () => {
  const r = chamadasNoTexto('{"name": "edit_file", "arguments": {"path": "a.js", "old_text": "if (x) {", "new_text": "if (y) { // }"}}', NOMES);
  assert.equal(r.chamadas[0].args.new_text, 'if (y) { // }');
});

test('edicao exata, unica', () => {
  assert.equal(aplicarEdicao('a\nb\nc\n', 'b', 'B'), 'a\nB\nc\n');
});

test('edicao recusa trecho repetido e trecho inexistente', () => {
  assert.throws(() => aplicarEdicao('x\nx\n', 'x', 'y'), /2 vezes/);
  assert.throws(() => aplicarEdicao('abc', 'zzz', 'y'), /nao foi encontrado/);
});

test('edicao aceita o trecho copiado com os numeros do read_file', () => {
  const arq = 'function f() {\n  return 1;\n}\n';
  assert.equal(aplicarEdicao(arq, '2|   return 1;', '2|   return 2;'), 'function f() {\n  return 2;\n}\n');
});

test('edicao tolera recuo diferente e mantem o recuo do arquivo', () => {
  const arq = 'if (a) {\n    soma(1);\n    fim();\n}\n';
  const r = aplicarEdicao(arq, 'soma(1);\nfim();', 'soma(2);\nfim();');
  assert.equal(r, 'if (a) {\n    soma(2);\n    fim();\n}\n');
});

test('edicao preserva CRLF', () => {
  assert.equal(aplicarEdicao('a\r\nb\r\n', 'b', 'c'), 'a\r\nc\r\n');
});

test('diff conta linhas', () => {
  const d = diff('a\nb\nc', 'a\nB\nc\nd');
  assert.equal(d.mais, 2);
  assert.equal(d.menos, 1);
  assert.match(d.texto, /^-b$/m);
  assert.match(d.texto, /^\+B$/m);
});

test('caminhos fora do projeto sao recusados', () => {
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-'));
  assert.throws(() => resolver(raiz, '../fora.txt'), /fora do projeto/);
  assert.throws(() => resolver(raiz, 'C:\\Windows\\win.ini'), /fora do projeto/);
  assert.equal(resolver(raiz, '/src/a.js'), path.join(raiz, 'src', 'a.js'));
  fs.writeFileSync(path.join(raiz, 'a.txt'), 'um\ndois\n');
  assert.match(ler(raiz, { path: 'a.txt' }), /^1\| um\n2\| dois/);
});

test('detecta anuncio sem acao', () => {
  assert.ok(anunciaSemFazer('Vamos verificar o package.json:'));
  assert.ok(anunciaSemFazer('Primeiro, vou listar os arquivos.'));
  assert.ok(!anunciaSemFazer('Pronto: corrigi a funcao soma. Rode npm test para conferir.'));
  assert.ok(!anunciaSemFazer('Quer que eu rode os testes?'));
});
