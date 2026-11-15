// A janela do Nous Code segue a paleta de cores escolhida no Nous (NousData/aparencia.json).
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { spawn, type ChildProcess } from 'node:child_process';
import { paletaEscolhida } from '../aparencia.ts';

const dir = () => fs.mkdtempSync(path.join(os.tmpdir(), 'nc-aparencia-'));

test('sem arquivo = ouro', () => {
  assert.equal(paletaEscolhida(dir()), 'ouro');
});

test('le a escolha do arquivo', () => {
  const d = dir();
  fs.writeFileSync(path.join(d, 'aparencia.json'), JSON.stringify({ paleta: 'maracuja' }));
  assert.equal(paletaEscolhida(d), 'maracuja');
});

test('id desconhecido ou arquivo estragado = ouro', () => {
  const d = dir();
  fs.writeFileSync(path.join(d, 'aparencia.json'), JSON.stringify({ paleta: 'abacaxi' }));
  assert.equal(paletaEscolhida(d), 'ouro');
  fs.writeFileSync(path.join(d, 'aparencia.json'), '{nao e json');
  assert.equal(paletaEscolhida(d), 'ouro');
  fs.writeFileSync(path.join(d, 'aparencia.json'), '["ceu"]');
  assert.equal(paletaEscolhida(d), 'ouro');
});

/* ---- o servico de verdade ---- */
let proc: ChildProcess;
let base = '';
const dados = dir();

function portaLivre(): Promise<number> {
  const tenta = (p: number): Promise<number> => new Promise((ok, erro) => {
    const s = net.createServer();
    s.once('error', () => (p < 9599 ? ok(tenta(p + 1) as unknown as number) : erro(new Error('sem porta livre'))));
    s.listen(p, '127.0.0.1', () => s.close(() => ok(p)));
  });
  return tenta(9500 + Math.floor(Math.random() * 60));
}

before(async () => {
  const porta = await portaLivre();
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

test('GET /aparencia segue o arquivo do Nous', async () => {
  let r = await fetch(base + '/aparencia');
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { paleta: 'ouro' });
  fs.writeFileSync(path.join(dados, 'aparencia.json'), JSON.stringify({ paleta: 'ceu' }));
  r = await fetch(base + '/aparencia');
  assert.deepEqual(await r.json(), { paleta: 'ceu' });
  assert.equal(r.headers.get('cache-control'), 'no-store');
});

test('/tema/nous-paletas.css responde text/css com as paletas', async () => {
  const r = await fetch(base + '/tema/nous-paletas.css');
  assert.equal(r.status, 200);
  assert.match(r.headers.get('content-type') || '', /text\/css/);
  assert.match(await r.text(), /\[data-nous-paleta="maracuja"\]/);
  assert.equal((await fetch(base + '/tema/paletas.json')).status, 404);   // so' a folha, nada mais da pasta
});
