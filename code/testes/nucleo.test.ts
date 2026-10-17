// Testes do nucleo (sem modelo): leitura das chamadas, edicao, diff, caminhos,
// formato das ferramentas (contrato do DeepSeek Harness), lembretes e MCP.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { chamadasNoTexto } from '../modelo.ts';
import { aplicarEdicao, diff, resolver, ler, canonica, NOMES_BASE, NOMES_APELIDOS, glob, buscar, paraModelo, configurar } from '../ferramentas.ts';
import { anunciaSemFazer } from '../agente.ts';

const NOMES = new Set([...NOMES_BASE, ...NOMES_APELIDOS]);

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
  assert.throws(() => aplicarEdicao('x\nx\n', 'x', 'y'), /matched 2 times/);
  assert.throws(() => aplicarEdicao('abc', 'zzz', 'y'), /was not found/);
  assert.throws(() => aplicarEdicao('abc', 'b', 'b'), /must differ/);
});

test('edicao com replace_all troca todas', () => {
  assert.equal(aplicarEdicao('x\nx\n', 'x', 'y', true), 'y\ny\n');
});

test('edicao aceita o trecho copiado com os numeros do read ("12: ")', () => {
  const arq = 'function f() {\n  return 1;\n}\n';
  assert.equal(aplicarEdicao(arq, '2:   return 1;', '2:   return 2;'), 'function f() {\n  return 2;\n}\n');
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
  assert.throws(() => resolver(raiz, '../fora.txt'), /outside the project/);
  assert.throws(() => resolver(raiz, 'C:\\Windows\\win.ini'), /outside the project/);
  assert.equal(resolver(raiz, '/src/a.js'), path.join(raiz, 'src', 'a.js'));
});

test('read no formato do dsh: <path>, "N: texto" e rodape', () => {
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-'));
  fs.writeFileSync(path.join(raiz, 'a.txt'), 'um\r\ndois\ntres\n');
  const t = ler(raiz, { file_path: 'a.txt' });
  assert.equal(t, '<path>a.txt</path>\n<type>file</type>\n<content>\n1: um\n2: dois\n3: tres\n\n(End of file - total 3 lines)\n</content>');
  assert.match(ler(raiz, { file_path: 'a.txt', offset: 2, limit: 1 }), /2: dois\n\n\(Showing lines 2-2 of 3\. Use offset=3 to continue\.\)/);
  assert.throws(() => ler(raiz, { file_path: 'a.txt', offset: 9 }), /offset 9 is out of range/);
  assert.throws(() => ler(raiz, { file_path: 'nao.txt' }), /cannot read "nao.txt": not found/);
});

test('apelidos: nomes e parametros antigos viram o contrato novo', () => {
  assert.deepEqual(canonica('read_file', { path: 'a.js', start_line: 10, end_line: 19 }), { nome: 'read', args: { file_path: 'a.js', offset: 10, limit: 10 } });
  assert.deepEqual(canonica('edit_file', { path: 'a', old_text: 'x', new_text: 'y' }), { nome: 'edit', args: { file_path: 'a', old_string: 'x', new_string: 'y' } });
  assert.deepEqual(canonica('Bash', { command: 'ls', timeout_s: 5 }), { nome: 'pwsh', args: { command: 'ls', timeoutMs: 5000 } });
  assert.deepEqual(canonica('web_search', { query: 'node' }), { nome: 'web_search', args: { queries: ['node'] } });
  assert.equal(canonica('ask_user', { question: 'Qual?', options: ['A', 'B'] }).args.questions instanceof Array, true);
  assert.equal(canonica('Read', {}).nome, 'read');
  assert.equal(canonica('mcp__x__y', {}).nome, 'mcp__x__y');
});

test('glob e grep: formato do dsh', () => {
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-'));
  fs.mkdirSync(path.join(raiz, 'src'));
  fs.mkdirSync(path.join(raiz, 'node_modules'));
  fs.writeFileSync(path.join(raiz, 'src', 'a.ts'), 'export const soma = 1;\nconst x = soma;\n');
  fs.writeFileSync(path.join(raiz, 'node_modules', 'b.ts'), 'soma');
  fs.writeFileSync(path.join(raiz, 'gerado.ts'), 'soma');
  fs.writeFileSync(path.join(raiz, '.gitignore'), 'gerado.ts\n');
  assert.equal(glob(raiz, { pattern: '*.md' }), 'No files found');
  assert.deepEqual(glob(raiz, { pattern: '*.ts' }).split('\n').sort(), ['gerado.ts', 'src/a.ts']);
  assert.equal(buscar(raiz, { pattern: 'soma' }), 'Found 2 matches\n\nsrc/a.ts\nLine 1: export const soma = 1;\nLine 2: const x = soma;');
  assert.equal(buscar(raiz, { pattern: 'nada' }), 'No matches found');
  assert.equal(buscar(raiz, { pattern: 'SOMA' }), 'No matches found');  // maiuscula: diferencia
  assert.throws(() => buscar(raiz, { pattern: 'x', include: '*.ts,*.js' }), /not a comma-separated list/);
});

test('resultado grande: comeco + [...] + fim, e o resto num arquivo legivel', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-saida-'));
  configurar(dir);
  const t = paraModelo('a'.repeat(5000) + 'MEIO' + 'b'.repeat(5000), 'sessao1', 'pwsh');
  assert.match(t, /\[\.\.\.\]/);
  const arq = /stored at: (.+?)\. Use read/.exec(t)![1];
  assert.ok(fs.readFileSync(arq, 'utf8').includes('MEIO'));
  assert.equal(resolver(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-')), arq, true), arq);
});

test('lembretes: diario, semanal e cron no fuso, e seletor unico', async () => {
  const R = await import('../lembretes.ts');
  R.configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-lem-')));
  const base = { id: 'x', sessao: 's', titulo: 't', prompt: 'p', criado: 0, base: 0, quando: 0, ativo: true };
  const agora = Date.parse('2026-10-17T12:00:00-03:00');  // sabado
  const d = R.proxima({ ...base, tipo: 'daily', time: '09:30:00', timeZone: 'America/Sao_Paulo' }, agora)!;
  assert.equal(new Date(d).toISOString(), '2026-10-18T12:30:00.000Z');
  const w = R.proxima({ ...base, tipo: 'weekly', time: '08:00:00', timeZone: 'America/Sao_Paulo', weekdays: [1, 3] }, agora)!;
  assert.equal(new Date(w).toISOString(), '2026-10-19T11:00:00.000Z');
  const c = R.proxima({ ...base, tipo: 'cron', expression: '*/15 9-17 * * 1-5', timeZone: 'UTC' }, agora)!;
  assert.equal(new Date(c).toISOString(), '2026-10-19T09:00:00.000Z');
  assert.deepEqual(R.criar('s', { prompt: 'p', title: 't' }), { code: 'invalid_selector', message: 'schedule_create accepts exactly one of after_seconds, at, every_seconds, daily, weekly, or cron.' });
  assert.equal((R.criar('s', { prompt: 'p', title: 't', every_seconds: 10 }) as { code: string }).code, 'frequency_too_high');
  const v = R.criar('s', { prompt: 'rodar testes', title: 'Testes', after_seconds: 1 }) as { id: string; kind: string };
  assert.equal(v.kind, 'after');
  const vencidos = R.vencidos(Date.now() + 2000);
  assert.equal(vencidos.length, 1);
  assert.match(vencidos[0].texto, /^\[SCHEDULE REMINDER\]\nThis is a scheduled message from the user\nschedule_id_json: "sch-/);
  assert.equal(R.listar('s').length, 0);
});

test('MCP: nome publico do dsh', async () => {
  const M = await import('../mcp.ts');
  assert.equal(M.nomePublico('github', 'list_issues'), 'mcp__github__list_issues');
  assert.match(M.nomePublico('fs', 'read.file'), /^mcp__fs__read_file_[0-9a-f]{12}$/);
  assert.equal(M.projetar([{ type: 'text', text: 'a' }, { type: 'image', mimeType: 'image/png' }], 'x'), 'a\n[image result: image/png; this model cannot see images]');
});

test('instrucoes do projeto na moldura do dsh', async () => {
  const C = await import('../contexto.ts');
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-'));
  fs.mkdirSync(path.join(raiz, '.git'));
  fs.writeFileSync(path.join(raiz, 'AGENTS.md'), 'Use tabs.');
  fs.writeFileSync(path.join(raiz, 'CLAUDE.md'), 'Use tabs.');  // igual: entra uma vez
  const t = C.instrucoes(raiz);
  assert.match(t, /^<system-reminder>\nThe following workspace instructions may be relevant/);
  assert.equal(t.split('Instructions from:').length - 1, 1);
  fs.mkdirSync(path.join(raiz, 'api'));
  fs.writeFileSync(path.join(raiz, 'api', 'AGENTS.md'), 'Valide a entrada.');
  const sub = C.instrucoesDaPasta(raiz, path.join(raiz, 'api', 'x.ts'), [])!;
  assert.match(sub.texto, /Additional instructions from: api\/AGENTS\.md/);
  assert.equal(C.instrucoesDaPasta(raiz, path.join(raiz, 'api', 'x.ts'), ['api']), null);
});

test('detecta anuncio sem acao', () => {
  assert.ok(anunciaSemFazer('Vamos verificar o package.json:'));
  assert.ok(anunciaSemFazer('Primeiro, vou listar os arquivos.'));
  assert.ok(!anunciaSemFazer('Pronto: corrigi a funcao soma. Rode npm test para conferir.'));
  assert.ok(!anunciaSemFazer('Quer que eu rode os testes?'));
});

test('glob: ** e extensoes', async () => {
  const { globParaRegex } = await import('../ferramentas.ts');
  assert.ok(globParaRegex('src/**/*.ts').test('src/a/b/c.ts'));
  assert.ok(globParaRegex('src/**/*.ts').test('src/c.ts'));
  assert.ok(!globParaRegex('src/*.ts').test('src/a/c.ts'));
  assert.ok(globParaRegex('**/*.{js,ts}').test('x/y.js'));
});

test('html vira texto legivel com links', async () => {
  const { htmlParaTexto } = await import('../web.ts');
  const t = htmlParaTexto('<html><head><title>Doc &amp; API</title><script>x()</script></head><body><h2>Uso</h2><p>Veja <a href="https://ex.com/a">aqui</a>.</p><ul><li>um</li></ul></body></html>');
  assert.match(t, /^# Doc & API/);
  assert.match(t, /## Uso/);
  assert.match(t, /aqui \(https:\/\/ex\.com\/a\)/);
  assert.match(t, /- um/);
  assert.ok(!/x\(\)/.test(t));
});
