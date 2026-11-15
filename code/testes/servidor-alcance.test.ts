// O servico de verdade: o padrao das conversas novas (modo e alcance) e que
// pastas podem ser abertas em cada alcance. NousData e pasta do usuario de teste.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { spawn, type ChildProcess } from 'node:child_process';

let proc: ChildProcess;
let base = '';
const casa = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-srv-casa-'));
const dados = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-srv-alc-'));

function portaLivre(): Promise<number> {
  const tenta = (p: number): Promise<number> => new Promise((ok, erro) => {
    const s = net.createServer();
    s.once('error', () => (p < 9499 ? ok(tenta(p + 1) as unknown as number) : erro(new Error('sem porta livre'))));
    s.listen(p, '127.0.0.1', () => s.close(() => ok(p)));
  });
  return tenta(9400 + Math.floor(Math.random() * 60));
}

before(async () => {
  const porta = await portaLivre();
  base = 'http://127.0.0.1:' + porta;
  proc = spawn(process.execPath, ['servidor.ts'], { cwd: path.resolve(import.meta.dirname, '..'), windowsHide: true, stdio: 'ignore',
    env: { ...process.env, NOUS_CODE_PORT: String(porta), DATA_DIR: dados, USERPROFILE: casa, NOUS_CODE_DIAGNOSTICOS: '0' } });
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

test('padrao: pedir antes e so\' o projeto; a pasta do usuario e o disco inteiro ficam fechados', async () => {
  const a = await api('GET', '/ajustes');
  assert.equal(a.dados.modo, 'perguntar');
  assert.equal(a.dados.alcance, 'projeto');
  assert.equal(path.resolve(a.dados.casa), path.resolve(casa));
  assert.equal((await api('POST', '/sessoes', { pasta: casa })).status, 400);
  assert.equal((await api('POST', '/sessoes', { pasta: path.parse(casa).root })).status, 400);
  const sub = fs.mkdtempSync(path.join(casa, 'proj-'));
  const s = await api('POST', '/sessoes', { pasta: sub });
  assert.equal(s.status, 200);
  const v = await api('GET', '/sessao?id=' + s.dados.id);
  assert.equal(v.dados.modo, 'perguntar');
  assert.equal(v.dados.alcance, 'projeto');
});

test('alcance usuario libera a pasta do usuario; computador libera o disco; conversa nova nasce com o padrao', async () => {
  let a = await api('POST', '/ajustes', { modo: 'total', alcance: 'usuario' });
  assert.equal(a.dados.alcance, 'usuario');
  const s = await api('POST', '/sessoes', { pasta: casa });
  assert.equal(s.status, 200, JSON.stringify(s.dados));
  const v = await api('GET', '/sessao?id=' + s.dados.id);
  assert.equal(v.dados.modo, 'total');
  assert.equal(v.dados.alcance, 'usuario');
  assert.equal((await api('POST', '/sessoes', { pasta: path.parse(casa).root })).status, 400);

  a = await api('POST', '/ajustes', { alcance: 'computador', modo: 'invalido' });
  assert.equal(a.dados.modo, 'total', 'valor invalido nao muda o que estava');
  assert.equal((await api('POST', '/sessoes', { pasta: path.parse(casa).root })).status, 200);
  await api('POST', '/ajustes', { modo: 'perguntar', alcance: 'projeto' });
});

test('a conversa troca o alcance pelos ajustes dela', async () => {
  const sub = fs.mkdtempSync(path.join(casa, 'proj-'));
  const s = await api('POST', '/sessoes', { pasta: sub });
  const r = await api('POST', '/sessao/ajustes', { id: s.dados.id, alcance: 'computador' });
  assert.equal(r.dados.alcance, 'computador');
  assert.equal((await api('GET', '/sessao?id=' + s.dados.id)).dados.alcance, 'computador');
  const x = await api('POST', '/sessao/ajustes', { id: s.dados.id, alcance: 'qualquer' });
  assert.equal(x.dados.alcance, 'computador');
});
