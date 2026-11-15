// A entrada do terminal (readline): linhas, continuacao com \, texto colado,
// historico em disco, Tab, Ctrl+C / Ctrl+D e teclas unicas. Usa um terminal de mentira.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { PassThrough } from 'node:stream';
import { IoTerminal } from '../cli/io.ts';

function terminal(arq?: string) {
  const entrada = Object.assign(new PassThrough(), { isTTY: true, setRawMode() { return this; } });
  const sai = Object.assign(new PassThrough(), { isTTY: true, columns: 100 });
  sai.resume();
  const arqHist = arq ?? path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-cli-io-')), 'cli-historico');
  const io = new IoTerminal(arqHist, entrada as unknown as NodeJS.ReadStream, sai as unknown as NodeJS.WriteStream, new PassThrough() as unknown as NodeJS.WriteStream);
  return { io, entrada, sai, arqHist, digita: (s: string) => entrada.write(s) };
}
const espera = (ms: number) => new Promise((ok) => setTimeout(ok, ms));

test('uma linha, e o terminal e de verdade (tty)', async () => {
  const t = terminal();
  assert.equal(t.io.tty, true);
  const p = t.io.linha('> ');
  await espera(20);
  t.digita('ola mundo\r');
  assert.deepEqual(await p, { t: 'linha', texto: 'ola mundo' });
});

test('\\ no fim da linha continua o pedido na linha de baixo', async () => {
  const t = terminal();
  const p = t.io.linha('> ');
  await espera(20);
  t.digita('primeira parte \\\r');
  await espera(60);
  t.digita('segunda parte\r');
  assert.deepEqual(await p, { t: 'linha', texto: 'primeira parte \nsegunda parte' });
});

test('texto colado com varias linhas vira um pedido so\'', async () => {
  const t = terminal();
  const p = t.io.linha('> ');
  await espera(20);
  t.digita('linha um\rlinha dois\rlinha tres\r');
  assert.deepEqual(await p, { t: 'linha', texto: 'linha um\nlinha dois\nlinha tres' });
});

test('Ctrl+C devolve o que estava digitado; Ctrl+D numa linha vazia termina', async () => {
  let t = terminal();
  let p = t.io.linha('> ');
  await espera(20);
  t.digita('rascunho\x03');
  assert.deepEqual(await p, { t: 'ctrl-c', texto: 'rascunho' });
  t = terminal();
  p = t.io.linha('> ');
  await espera(20);
  t.digita('\x03');
  assert.deepEqual(await p, { t: 'ctrl-c', texto: '' });
  t = terminal();
  p = t.io.linha('> ');
  await espera(20);
  t.digita('\x04');
  assert.deepEqual(await p, { t: 'fim' });
});

test('historico: seta para cima volta ao pedido anterior, e fica em disco entre as sessoes', async () => {
  const t = terminal();
  t.io.guardar('primeiro pedido');
  t.io.guardar('segundo\npedido');            // varias linhas: guarda numa so'
  t.io.guardar('primeiro pedido');            // repetido: sobe para o topo, sem duplicar
  assert.deepEqual(t.io.historico(), ['primeiro pedido', 'segundo pedido']);
  const p = t.io.linha('> ');
  await espera(20);
  t.digita('\x1b[A');                          // seta para cima
  await espera(20);
  t.digita('\x1b[A');
  await espera(20);
  t.digita('\r');
  assert.deepEqual(await p, { t: 'linha', texto: 'segundo pedido' });
  // outra sessao do terminal le o mesmo arquivo
  const t2 = terminal(t.arqHist);
  assert.deepEqual(t2.io.historico().slice(0, 2), ['primeiro pedido', 'segundo pedido']);
});

test('Tab chama o completador com a linha e coloca o que ele devolve', async () => {
  const t = terminal();
  const vistas: string[] = [];
  const p = t.io.linha('> ', (linha) => { vistas.push(linha); return [['/modelo'], linha]; });
  await espera(20);
  t.digita('/mo\t');
  await espera(30);
  t.digita('\r');
  assert.deepEqual(await p, { t: 'linha', texto: '/modelo' });
  assert.deepEqual(vistas, ['/mo']);
});

test('uma tecla: letra valida, Enter, Esc e Ctrl+C', async () => {
  const t = terminal();
  let p = t.io.tecla(['s', 'n']);
  await espera(20);
  t.digita('x');            // invalida: ignora
  t.digita('S');            // maiuscula vale
  assert.equal(await p, 's');
  p = t.io.tecla(['s', 'n', 'enter']);
  await espera(20);
  t.digita('\r');
  assert.equal(await p, 'enter');
  p = t.io.tecla(['s', 'n']);
  await espera(20);
  t.digita('\x03');
  assert.equal(await p, 'esc');
  p = t.io.tecla(['s', 'n']);
  await espera(20);
  t.digita('\x1b');
  assert.equal(await p, 'esc');
});

test('durante o turno, Esc e Ctrl+C chamam a interrupcao; ao terminar a escuta sai', async () => {
  const t = terminal();
  let n = 0;
  const desligar = t.io.aoInterromper(() => { n++; });
  await espera(20);
  t.digita('\x1b');
  await espera(700);          // o Esc sozinho espera um pouco para nao confundir com setas
  assert.equal(n, 1);
  t.digita('\x03');
  await espera(30);
  assert.equal(n, 2);
  t.digita('abc');            // o resto das teclas nao interrompe
  await espera(30);
  assert.equal(n, 2);
  desligar();
  t.digita('\x03');
  await espera(30);
  assert.equal(n, 2);
});
