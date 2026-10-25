// Diagnosticos do language server depois de uma edicao: o modelo recebe so' os
// erros que a edicao introduziu. Usa o typescript-language-server de verdade
// (instalado junto) e o Ollama de mentira; sem o servidor, o teste e' pulado.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { estado, ligarFalso, desligarFalso, configurarApoio, chamar, resultados, conteudos, rodar } from './apoio.ts';

let A: typeof import('../agente.ts');
import * as L from '../lsp.ts';
before(async () => {
  await ligarFalso();
  await configurarApoio();
  A = await import('../agente.ts');
});
after(() => { L.encerrarTodos(); desligarFalso(); });

const temTs = () => L.disponiveis().some((x) => x.nome === 'typescript' && x.ok);

function projeto(arquivos: Record<string, string>) {
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-diag-'));
  fs.writeFileSync(path.join(raiz, 'tsconfig.json'), JSON.stringify({ compilerOptions: { strict: true, target: 'es2022', module: 'esnext', noEmit: true }, include: ['*.ts'] }));
  for (const [n, c] of Object.entries(arquivos)) fs.writeFileSync(path.join(raiz, n), c);
  return A.normalizar({ id: 'diag' + Math.random().toString(36).slice(2, 8), pasta: raiz, modelo: 'falso', modo: 'editar', tituloAuto: false });
}

test('texto curto dos diagnosticos: limite de 5 e mensagem cortada', () => {
  const d = Array.from({ length: 8 }, (_, i) => ({ linha: i + 1, coluna: 2, codigo: '2322', msg: 'x'.repeat(400), trecho: '' }));
  const t = L.textoDiagnosticos('a.ts', d);
  assert.equal(t.split('\n').length, 1 + 5 + 1);
  assert.match(t, /^LSP diagnostics introduced by this edit \(8\)/);
  assert.match(t, /\.\.\. \(3 more\)$/);
  assert.ok(t.split('\n')[1].length < 300);
});

test('a edicao que quebra o tipo devolve o erro ao modelo e o evento ao editor', { skip: !temTs() && 'sem typescript-language-server', timeout: 90_000 }, async () => {
  process.env.NOUS_CODE_DIAGNOSTICOS = '1';
  const s = projeto({ 'a.ts': 'export const n: number = 1;\nexport const m: number = 2;\n' });
  estado.roteiro = [chamar('read', { file_path: 'a.ts' }),
    chamar('edit', { file_path: 'a.ts', old_string: 'n: number = 1', new_string: "n: number = 'um'" }),
    chamar('edit', { file_path: 'a.ts', old_string: "n: number = 'um'", new_string: 'n: number = 3' }),
    'Corrigi.'];
  const ev = await rodar(A, s, 'troque o n');
  const tool = conteudos(s, 'tool');
  assert.match(tool[1], /has been updated successfully\.\n\nLSP diagnostics introduced by this edit \(1\)/);
  assert.match(tool[1], /a\.ts:1:14 error 2322: Type 'string' is not assignable to type 'number'\./);
  // a correcao nao traz nada
  assert.equal(tool[2], 'The file a.ts has been updated successfully.');
  const d = ev.filter((e) => e.t === 'diagnosticos');
  assert.equal(d.length, 2);
  assert.equal((d[0].itens as unknown[]).length, 1);
  assert.equal((d[1].itens as unknown[]).length, 0);
  assert.equal(resultados(ev).every((r) => r.ok), true);
});

test('erro que ja existia antes da edicao nao e repetido; so o novo aparece', { skip: !temTs() && 'sem typescript-language-server', timeout: 90_000 }, async () => {
  process.env.NOUS_CODE_DIAGNOSTICOS = '1';
  const s = projeto({ 'b.ts': "export const velho: number = 'antigo';\nexport const k = 1;\n" });
  estado.roteiro = [chamar('read', { file_path: 'b.ts' }),
    chamar('edit', { file_path: 'b.ts', old_string: 'export const k = 1;', new_string: 'export const k = 1;\nexport const novo: boolean = 5;' }),
    'ok'];
  await rodar(A, s, 'acrescente');
  const t = conteudos(s, 'tool')[1];
  assert.match(t, /introduced by this edit \(1\)/);
  assert.match(t, /b\.ts:3:14 error 2322: Type 'number' is not assignable to type 'boolean'\./);
  assert.ok(!t.includes('antigo') && !t.includes("'string'"));
});

test('arquivo sem language server (ou desligado por variavel) edita normalmente', async () => {
  process.env.NOUS_CODE_DIAGNOSTICOS = '1';
  const s = projeto({ 'nota.txt': 'um\n' });
  estado.roteiro = [chamar('read', { file_path: 'nota.txt' }), chamar('edit', { file_path: 'nota.txt', old_string: 'um', new_string: 'dois' }), 'ok'];
  const ev = await rodar(A, s, 'troque');
  assert.equal(conteudos(s, 'tool')[1], 'The file nota.txt has been updated successfully.');
  assert.ok(!ev.some((e) => e.t === 'diagnosticos'));
  process.env.NOUS_CODE_DIAGNOSTICOS = '0';
  const t = projeto({ 'c.ts': 'export const n: number = 1;\n' });
  estado.roteiro = [chamar('read', { file_path: 'c.ts' }), chamar('edit', { file_path: 'c.ts', old_string: '1', new_string: "'x'" }), 'ok'];
  const ev2 = await rodar(A, t, 'quebre');
  assert.equal(conteudos(t, 'tool')[1], 'The file c.ts has been updated successfully.');
  assert.ok(!ev2.some((e) => e.t === 'diagnosticos'));
});

test('Python (pyright): erro novo volta ao modelo', { skip: !L.disponiveis().some((x) => x.nome === 'python' && x.ok) && 'sem pyright', timeout: 120_000 }, async () => {
  process.env.NOUS_CODE_DIAGNOSTICOS = '1';
  const s = projeto({ 'p.py': 'def soma(a: int, b: int) -> int:\n    return a + b\n' });
  estado.roteiro = [chamar('read', { file_path: 'p.py' }),
    chamar('edit', { file_path: 'p.py', old_string: 'return a + b', new_string: 'return str(a + b)' }), 'ok'];
  await rodar(A, s, 'devolva texto');
  const t = conteudos(s, 'tool')[1];
  assert.match(t, /introduced by this edit \(1\)/);
  assert.match(t, /p\.py:2:12 error [^:]*: .*"str" is not assignable to return type "int"/s);
});
