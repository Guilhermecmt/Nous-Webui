// Subagente que edita: preso a uma lista de arquivos/pastas, com as mesmas
// permissoes e a mesma aprovacao com diff do agente principal. Ollama de mentira:
// as respostas do roteiro vao, na ordem, para o agente principal e para o subagente.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { estado, ligarFalso, desligarFalso, configurarApoio, chamar, resultados, conteudos, rodar } from './apoio.ts';

process.env.NOUS_CODE_DIAGNOSTICOS = '0';
let A: typeof import('../agente.ts');
before(async () => { await ligarFalso(); await configurarApoio(); A = await import('../agente.ts'); });
after(() => { desligarFalso(); });

function sessao(modo: 'leitura' | 'perguntar' | 'editar' | 'total' = 'editar') {
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-sub-'));
  fs.mkdirSync(path.join(raiz, 'src'));
  fs.writeFileSync(path.join(raiz, 'a.js'), 'const a = 1;\n');
  fs.writeFileSync(path.join(raiz, 'b.js'), 'const b = 1;\n');
  fs.writeFileSync(path.join(raiz, 'src', 'x.js'), 'const x = 1;\n');
  return { raiz, s: A.normalizar({ id: 'sub' + Math.random().toString(36).slice(2, 8), pasta: raiz, modelo: 'falso', modo, tituloAuto: false }) };
}
const ler = (raiz: string, f: string) => fs.readFileSync(path.join(raiz, f), 'utf8');
const delegar = (extra: object) => chamar('subagent', { description: 'mexer', prompt: 'troque o valor', ...extra });

test('o subagente muda o arquivo do escopo; fora dele e\' recusado; o desfazer enxerga', async () => {
  const { raiz, s } = sessao();
  estado.roteiro = [
    delegar({ edit: true, files: ['a.js'] }),
    chamar('read', { file_path: 'a.js' }),                                           // subagente
    chamar('edit', { file_path: 'a.js', old_string: 'a = 1', new_string: 'a = 2' }),
    chamar('edit', { file_path: 'b.js', old_string: 'b = 1', new_string: 'b = 2' }),  // fora do escopo
    'Troquei o a.js; o b.js ficou de fora do meu escopo.',                            // fim do subagente
    'O subagente terminou.'];                                                         // agente principal
  estado.pedidos.length = 0;
  const ev = await rodar(A, s, 'delegue');
  assert.equal(ler(raiz, 'a.js'), 'const a = 2;\n');
  assert.equal(ler(raiz, 'b.js'), 'const b = 1;\n');
  const sub = resultados(ev)[0];
  assert.equal(sub.ok, true);
  assert.match(String(sub.saida), /Subagent finished\. Its closing message:\nTroquei o a\.js/);
  assert.match(String(sub.saida), /Files it changed: a\.js \(\+1 -1\)\./);
  // o subagente recebeu a recusa com o escopo
  const doSub = estado.pedidos.filter((p) => p.messages.some((m) => m.content.includes('You are an editing subagent'))).at(-1)!;
  const ultimos = doSub.messages.map((m) => m.content).join('\n');
  assert.match(ultimos, /POLICY_DENIED: this subagent may only change: a\.js\. "b\.js" is outside that scope/);
  assert.ok(ev.some((e) => e.t === 'sub' && /Mudou a\.js \(\+1 -1\)/.test(String(e.resumo))));
  // fica registrado como mudanca da conversa e o desfazer volta o arquivo
  assert.deepEqual(A.mudancas(s).map((m) => m.arquivo), ['a.js']);
  A.desfazer(s);
  assert.equal(ler(raiz, 'a.js'), 'const a = 1;\n');
});

test('pasta no escopo vale para arquivos novos e antigos dela, mas nao para o resto', async () => {
  const { raiz, s } = sessao();
  estado.roteiro = [
    delegar({ edit: true, files: ['src/'] }),
    chamar('write', { file_path: 'src/novo.js', content: 'export {};\n' }),
    chamar('write', { file_path: 'srcx.js', content: 'nao\n' }),
    'Criei src/novo.js.', 'ok'];
  await rodar(A, s, 'delegue');
  assert.equal(ler(raiz, 'src/novo.js'), 'export {};\n');
  assert.ok(!fs.existsSync(path.join(raiz, 'srcx.js')));
});

test('o subagente tambem tem que ler antes de editar', async () => {
  const { raiz, s } = sessao();
  estado.roteiro = [delegar({ edit: true, files: ['a.js'] }),
    chamar('edit', { file_path: 'a.js', old_string: 'a = 1', new_string: 'a = 9' }), 'Nao consegui.', 'ok'];
  estado.pedidos.length = 0;
  await rodar(A, s, 'delegue');
  assert.equal(ler(raiz, 'a.js'), 'const a = 1;\n');
  assert.ok(estado.pedidos.some((p) => p.messages.some((m) => m.content.includes('file has not been read'))));
});

test('modo perguntar: o subagente pede aprovacao com diff, e a recusa vale', async () => {
  const { raiz, s } = sessao('perguntar');
  estado.roteiro = [delegar({ edit: true, files: ['a.js'] }),
    chamar('read', { file_path: 'a.js' }),
    chamar('edit', { file_path: 'a.js', old_string: 'a = 1', new_string: 'a = 7' }),
    'O usuario recusou.', 'ok'];
  estado.pedidos.length = 0;
  const ev = await rodar(A, s, 'delegue', { arquivo: { ok: false } });
  const pede = ev.find((e) => e.t === 'pede' && e.tipo === 'arquivo')!;
  assert.equal(pede.arquivo, 'a.js');
  assert.match(String(pede.diff), /\+const a = 7;/);
  assert.equal(ler(raiz, 'a.js'), 'const a = 1;\n');
  assert.ok(estado.pedidos.some((p) => p.messages.some((m) => m.content.includes('the user rejected tool "edit" for a.js'))));
  // aprovando, muda
  const { raiz: r2, s: s2 } = sessao('perguntar');
  estado.roteiro = [delegar({ edit: true, files: ['a.js'] }), chamar('read', { file_path: 'a.js' }),
    chamar('edit', { file_path: 'a.js', old_string: 'a = 1', new_string: 'a = 7' }), 'Feito.', 'ok'];
  const ev2 = await rodar(A, s2, 'delegue', { arquivo: { ok: true } });
  assert.ok(ev2.some((e) => e.t === 'pede' && e.tipo === 'arquivo'));
  assert.equal(ler(r2, 'a.js'), 'const a = 7;\n');
});

test('somente leitura e modo plano nao deixam o subagente editar; leitura continua', async () => {
  const { raiz, s } = sessao('leitura');
  estado.roteiro = [delegar({ edit: true, files: ['a.js'] }), 'ok'];
  estado.pedidos.length = 0;
  const r = resultados(await rodar(A, s, 'delegue'));
  assert.match(String(r[0].saida), /^POLICY_DENIED: this conversation is read-only: a subagent cannot change files\./);
  assert.equal(estado.pedidos.length, 2, 'o subagente nem chegou a rodar');
  const { s: p } = sessao();
  p.planejando = true;
  estado.roteiro = [delegar({ edit: true, files: ['a.js'] }), 'ok'];
  const r2 = resultados(await rodar(A, p, 'delegue'));
  assert.match(String(r2[0].saida), /^POLICY_DENIED: plan mode is active: a subagent cannot change files now/);
  // so' leitura em modo plano segue permitido
  estado.roteiro = [delegar({}), chamar('read', { file_path: 'a.js' }), 'Achei.', 'ok'];
  const r3 = resultados(await rodar(A, p, 'investigue'));
  assert.equal(r3[0].ok, true);
  assert.equal(ler(raiz, 'a.js'), 'const a = 1;\n');
});

test('edit=true sem files, ou com o projeto inteiro, e\' recusado; sem edit o subagente continua so leitura', async () => {
  const { raiz, s } = sessao();
  estado.roteiro = [delegar({ edit: true }), delegar({ edit: true, files: ['.'] }), delegar({ edit: true, files: ['../fora.txt'] }), 'ok'];
  const r = resultados(await rodar(A, s, 'delegue'));
  assert.match(String(r[0].saida), /needs files/);
  assert.match(String(r[1].saida), /not the whole project/);
  assert.equal(r[2].ok, false);
  estado.roteiro = [delegar({}), chamar('edit', { file_path: 'a.js', old_string: 'a = 1', new_string: 'a = 3' }), 'Nao posso editar.', 'ok'];
  estado.pedidos.length = 0;
  await rodar(A, s, 'delegue');
  assert.equal(ler(raiz, 'a.js'), 'const a = 1;\n');
  assert.ok(!conteudos(s, 'tool').some((t) => t.includes('Files it changed: a.js')));
});

test('em tarefa separada (isolada) o subagente pode receber o projeto inteiro', async () => {
  const { raiz, s } = sessao();
  s.isolada = true;
  estado.roteiro = [delegar({ edit: true, files: ['.'] }), chamar('read', { file_path: 'b.js' }),
    chamar('edit', { file_path: 'b.js', old_string: 'b = 1', new_string: 'b = 5' }), 'Feito.', 'ok'];
  await rodar(A, s, 'delegue');
  assert.equal(ler(raiz, 'b.js'), 'const b = 5;\n');
});
