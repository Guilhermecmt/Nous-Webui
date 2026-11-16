// A cara do `nous` no terminal: a coruja na abertura, os olhos no "pensando", as cores
// da paleta escolhida e o alcance padrao (o computador inteiro, como no Claude Code).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { CORUJA } from '../cli/coruja.ts';
import { QUADROS, abertura, criarEstilo, misturar, semAnsi } from '../cli/tela.ts';
import { lerArgs } from '../cli/args.ts';
import { ALCANCE_TERMINAL, prefsDe } from '../cli/principal.ts';
import { coresMarca } from '../aparencia.ts';

const CORES = { clara: '#ffc04d', escura: '#f5a623' };   // Maracuja escuro
const PAINEL = ['N O U S   agente no seu computador', '', 'modelo   qwen3:4b', 'pasta    C:\\Users\\ana', 'alcance  o computador inteiro'];

test('a marca usa a cor da paleta (truecolor); sem cor nao pinta; cor invalida volta ao magenta', () => {
  assert.equal(criarEstilo(true, CORES).marca('❯'), '\x1b[38;2;255;192;77m❯\x1b[39m');
  assert.equal(criarEstilo(false, CORES).marca('❯'), '❯');
  assert.equal(criarEstilo(true, { clara: 'roxo', escura: '#000000' }).marca('x'), '\x1b[35mx\x1b[39m');
  assert.equal(criarEstilo(true).marca('x'), '\x1b[35mx\x1b[39m');
});

test('misturar faz o degrade entre duas cores', () => {
  assert.equal(misturar('#000000', '#ffffff', 0), '#000000');
  assert.equal(misturar('#000000', '#ffffff', 1), '#ffffff');
  assert.equal(misturar('#ffc04d', '#f5a623', 0.5), '#fab338');
});

test('abertura: a coruja em degrade com o painel ao lado', () => {
  const ls = abertura(criarEstilo(true, CORES), PAINEL, 120);
  assert.equal(ls.length, Math.max(CORUJA.length, PAINEL.length));
  const limpas = ls.map(semAnsi);
  assert.ok(limpas.some((l) => l.includes('N O U S')));
  assert.ok(limpas.some((l) => /[\u2801-\u28ff]/.test(l)), 'tem o desenho em braille');
  assert.ok(ls[0].includes('\x1b[38;2;255;192;77m'), 'topo na cor clara');
  assert.ok(ls[CORUJA.length - 1].includes('\x1b[38;2;245;166;35m'), 'pe na cor de destaque');
  // o painel fica no meio da altura da coruja
  const iTitulo = limpas.findIndex((l) => l.includes('N O U S'));
  assert.equal(iTitulo, Math.floor((CORUJA.length - PAINEL.length) / 2));
});

test('abertura: terminal estreito ou sem cor mostra so o painel', () => {
  assert.deepEqual(abertura(criarEstilo(true, CORES), PAINEL, 40), PAINEL.map((l) => ' ' + l));
  assert.deepEqual(abertura(criarEstilo(false, CORES), PAINEL, 200), PAINEL.map((l) => ' ' + l));
});

test('os olhos da coruja no lugar do giro: olham para os lados e piscam', () => {
  assert.ok(QUADROS.every((q) => q.length === 3 && q[1] === '▼'));
  for (const q of ['◉▼◉', '◐▼◐', '◑▼◑', '─▼─']) assert.ok(QUADROS.includes(q), q);
  assert.ok(QUADROS.filter((q) => q === '─▼─').length <= 3, 'a piscada e rapida');
});

test('no terminal o padrao e o computador inteiro; --alcance continua valendo', () => {
  assert.equal(ALCANCE_TERMINAL, 'computador');
  assert.equal(prefsDe(lerArgs([])).alcance, 'computador');
  assert.equal(prefsDe(lerArgs(['--alcance', 'projeto'])).alcance, 'projeto');
});

test('as cores do terminal seguem a paleta escolhida no Nous', () => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-cores-'));
  assert.deepEqual(coresMarca(d), { clara: '#e7c069', escura: '#c8962e' });          // sem escolha: Ouro
  fs.writeFileSync(path.join(d, 'aparencia.json'), JSON.stringify({ paleta: 'maracuja' }));
  assert.deepEqual(coresMarca(d), CORES);
});
