// Partes puras do terminal (`nous`): argumentos, comandos de barra e apelidos,
// valores, Tab e desenho. Nada de servico aqui (veja cli-servidor.test.ts).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { lerArgs } from '../cli/args.ts';
import { COMANDOS, acharComando, completarComando, escolherItem, interpretar, normalizarAlcance, normalizarEsforco, normalizarModo } from '../cli/comandos.ts';
import { completarArquivo, completarLinha } from '../cli/completar.ts';
import { argPrincipal, checklist, corLigada, criarEstilo, fmtTokens, formatarDiff, linhaFerramenta, linhaResultado, mdLinha, rodape, semAnsi } from '../cli/tela.ts';
import { lerEscolhas } from '../cli/turno.ts';
import { diffsDoArquivo } from '../cli/repl.ts';
import { urlJanela } from '../ide.ts';

const sem = criarEstilo(false);
const com = criarEstilo(true);

test('args: -p com pedido, opcoes com valor, --opcao=valor e pedido solto', () => {
  let o = lerArgs(['-p', 'liste os arquivos', '--model', 'qwen3:4b', '--effort', 'high', '--modo', 'editar', '-c']);
  assert.equal(o.imprimir, true);
  assert.equal(o.pedido, 'liste os arquivos');
  assert.equal(o.modelo, 'qwen3:4b');
  assert.equal(o.esforco, 'alto', 'high vira alto (o vocabulario do servico)');
  assert.equal(o.modo, 'editar');
  assert.equal(o.continuar, true);
  o = lerArgs(['--modo=total', '--alcance=pc', 'faca isto', 'e aquilo']);
  assert.equal(o.modo, 'total');
  assert.equal(o.alcance, 'computador');
  assert.equal(o.pedido, 'faca isto e aquilo');
  assert.equal(o.imprimir, false);
  o = lerArgs(['-p', '--modo', 'editar', 'pedido depois das opcoes']);
  assert.equal(o.imprimir, true);
  assert.equal(o.pedido, 'pedido depois das opcoes');
  assert.equal(lerArgs(['--versao']).versao, true);
  assert.equal(lerArgs(['-h']).ajuda, true);
  assert.equal(lerArgs(['--ajuda']).ajuda, true);
});

test('args: valor invalido e opcao desconhecida dao erro em portugues', () => {
  assert.match(lerArgs(['--effort', 'enorme']).erro || '', /raciocínio desconhecido/);
  assert.match(lerArgs(['--modo', 'x']).erro || '', /modo desconhecido/);
  assert.match(lerArgs(['--alcance', 'x']).erro || '', /alcance desconhecido/);
  assert.match(lerArgs(['--nada']).erro || '', /opção desconhecida/);
  assert.match(lerArgs(['--model']).erro || '', /falta o valor/);
});

test('comandos: nomes, apelidos em ingles e sem acento levam ao mesmo comando', () => {
  const casos: [string, string][] = [
    ['/ajuda', 'ajuda'], ['/help', 'ajuda'], ['/model', 'modelo'], ['/modelo', 'modelo'],
    ['/effort', 'effort'], ['/raciocinio', 'effort'], ['/raciocínio', 'effort'],
    ['/modo', 'modo'], ['/permissions', 'modo'], ['/alcance', 'alcance'],
    ['/plano', 'plano'], ['/plan', 'plano'], ['/objetivo', 'objetivo'], ['/goal', 'objetivo'],
    ['/compactar', 'compactar'], ['/compact', 'compactar'],
    ['/contexto', 'contexto'], ['/context', 'contexto'], ['/status', 'contexto'],
    ['/novo', 'novo'], ['/clear', 'novo'], ['/new', 'novo'],
    ['/conversas', 'conversas'], ['/resume', 'conversas'],
    ['/desfazer', 'desfazer'], ['/undo', 'desfazer'],
    ['/mudancas', 'mudancas'], ['/mudanças', 'mudancas'], ['/diff', 'mudancas'],
    ['/exportar', 'exportar'], ['/export', 'exportar'],
    ['/mcp', 'mcp'], ['/skills', 'skills'], ['/ide', 'ide'], ['/padrao', 'padrao'], ['/padrão', 'padrao'],
    ['/sair', 'sair'], ['/exit', 'sair'], ['/quit', 'sair'], ['/MODEL', 'modelo'],
  ];
  for (const [linha, nome] of casos) {
    const l = interpretar(linha);
    assert.equal(l.tipo, 'comando', linha);
    if (l.tipo === 'comando') assert.equal(l.comando.nome, nome, linha);
  }
});

test('comandos: argumento, texto comum, caminho e skill desconhecida', () => {
  const l = interpretar('/model   qwen3:4b  ');
  assert.ok(l.tipo === 'comando' && l.arg === 'qwen3:4b');
  const p = interpretar('/plano refatore a funcao\ncom duas linhas');
  assert.ok(p.tipo === 'comando' && p.comando.nome === 'plano' && p.arg === 'refatore a funcao\ncom duas linhas');
  assert.deepEqual(interpretar('   '), { tipo: 'vazia' });
  assert.deepEqual(interpretar('conserte o bug'), { tipo: 'texto', texto: 'conserte o bug' });
  assert.equal(interpretar('/usr/bin/node').tipo, 'texto', 'um caminho nao e comando');
  const d = interpretar('/revisar src/x.ts');
  assert.ok(d.tipo === 'desconhecido' && d.nome === 'revisar', 'pode ser uma skill: quem chama decide');
  assert.equal(acharComando('nada'), undefined);
  // nenhum apelido serve para dois comandos (as variantes com e sem acento do mesmo comando valem)
  const dono = new Map<string, string>();
  for (const c of COMANDOS) for (const n of [c.nome, ...c.apelidos]) {
    const k = n.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
    assert.ok(!dono.has(k) || dono.get(k) === c.nome, 'apelido ' + k + ' serve para ' + dono.get(k) + ' e ' + c.nome);
    dono.set(k, c.nome);
  }
});

test('raciocinio, modo e alcance aceitam portugues e ingles', () => {
  assert.equal(normalizarEsforco('low'), 'baixo');
  assert.equal(normalizarEsforco('Medium'), 'medio');
  assert.equal(normalizarEsforco('médio'), 'medio');
  assert.equal(normalizarEsforco('high'), 'alto');
  assert.equal(normalizarEsforco('off'), 'desligado');
  assert.equal(normalizarEsforco('auto'), 'auto');
  assert.equal(normalizarEsforco('xyz'), null);
  assert.equal(normalizarModo('Total'), 'total');
  assert.equal(normalizarModo('ask'), 'perguntar');
  assert.equal(normalizarModo('somente-leitura'), 'leitura');
  assert.equal(normalizarModo('nada'), null);
  assert.equal(normalizarAlcance('usuário'), 'usuario');
  assert.equal(normalizarAlcance('pc'), 'computador');
  assert.equal(normalizarAlcance('projeto'), 'projeto');
  assert.equal(normalizarAlcance('mundo'), null);
});

test('escolherItem: numero, nome exato, trecho unico e ambiguidade', () => {
  const l = [{ n: 'qwen3:14b' }, { n: 'qwen3:4b' }, { n: 'qwen2.5-coder:14b' }];
  const nome = (x: { n: string }) => x.n;
  assert.equal(escolherItem(l, '2', nome).item?.n, 'qwen3:4b');
  assert.equal(escolherItem(l, 'qwen3:4b', nome).item?.n, 'qwen3:4b');
  assert.equal(escolherItem(l, 'coder', nome).item?.n, 'qwen2.5-coder:14b');
  assert.match(escolherItem(l, 'qwen3', nome).erro || '', /mais de um/);
  assert.match(escolherItem(l, '9', nome).erro || '', /1 a 3/);
  assert.match(escolherItem(l, 'zzz', nome).erro || '', /não achei/);
});

test('Tab: comandos, skills, argumentos e @arquivos', () => {
  assert.ok(completarComando('mo').includes('/modelo') && completarComando('mo').includes('/model') && completarComando('mo').includes('/modo'));
  assert.deepEqual(completarComando('sa'), ['/sair']);
  assert.ok(completarComando('rev', ['revisar-codigo']).includes('/revisar-codigo'));
  const raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-cli-tab-'));
  fs.mkdirSync(path.join(raiz, 'src'));
  fs.mkdirSync(path.join(raiz, 'node_modules'));
  fs.writeFileSync(path.join(raiz, 'src', 'main.ts'), '');
  fs.writeFileSync(path.join(raiz, 'src', 'util.ts'), '');
  fs.writeFileSync(path.join(raiz, 'leia.md'), '');
  fs.writeFileSync(path.join(raiz, 'com espaco.txt'), '');
  const ctx = { pasta: raiz, skills: () => ['revisar'], modelos: () => ['qwen3:4b', 'qwen3:14b'] };
  assert.deepEqual(completarArquivo('s', raiz), ['@src/']);
  assert.deepEqual(completarArquivo('src/m', raiz), ['@src/main.ts']);
  assert.ok(!completarArquivo('', raiz).some((x) => x.includes('node_modules')), 'node_modules fica de fora');
  assert.ok(completarArquivo('com', raiz).includes('@"com espaco.txt"'), 'nome com espaco vai entre aspas');
  assert.deepEqual(completarLinha('leia @src/u', ctx), [['@src/util.ts'], '@src/u']);
  assert.ok(completarLinha('/rev', ctx)[0].includes('/revisar'));
  assert.deepEqual(completarLinha('/effort h', ctx), [[], 'h'], 'so os nomes do menu');
  assert.deepEqual(completarLinha('/effort a', ctx), [['auto', 'alto'], 'a']);
  assert.deepEqual(completarLinha('/modelo qwen3:1', ctx), [['qwen3:14b'], 'qwen3:1']);
  assert.deepEqual(completarLinha('/modo t', ctx), [['total'], 't']);
  assert.deepEqual(completarLinha('texto qualquer', ctx), [[], 'texto qualquer']);
});

test('perguntas do agente: numero, varios numeros, texto livre', () => {
  const ops = ['Sim', 'Não', 'Talvez'];
  assert.deepEqual(lerEscolhas('2', ops, false), { selected: ['Não'] });
  assert.deepEqual(lerEscolhas('1, 3', ops, true), { selected: ['Sim', 'Talvez'] });
  assert.deepEqual(lerEscolhas('1,3', ops, false), { selected: ['Sim'] }, 'sem multipla, so a primeira');
  assert.deepEqual(lerEscolhas('', ops, false), { selected: [] });
  assert.deepEqual(lerEscolhas('7', ops, false), { selected: [], custom: '7' }, 'numero fora da lista e resposta livre');
  assert.deepEqual(lerEscolhas('sim', ops, false), { selected: ['Sim'] });
  assert.deepEqual(lerEscolhas('outra coisa', ops, false), { selected: [], custom: 'outra coisa' });
  assert.deepEqual(lerEscolhas('2', [], false), { selected: [], custom: '2' });
});

test('desenho: diff colorido, linha de ferramenta, resultado, checklist, rodape', () => {
  const diff = '@@ -1,2 +1,2 @@\n ficou\n-velho\n+novo\n';
  const d = formatarDiff(diff, com, 40, '');
  assert.match(d, /\x1b\[32m\+novo\x1b\[39m/, 'adicionado em verde');
  assert.match(d, /\x1b\[31m-velho\x1b\[39m/, 'removido em vermelho');
  assert.equal(semAnsi(formatarDiff(diff, com, 40, '> ')), '> @@ -1,2 +1,2 @@\n>  ficou\n> -velho\n> +novo');
  assert.match(semAnsi(formatarDiff('+a\n'.repeat(50), sem, 10, '')), /… mais 40 linhas/);
  assert.equal(semAnsi(linhaFerramenta({ t: 'ferramenta', nome: 'read', args: { file_path: './src/x.ts' } }, com)), '● read src/x.ts');
  assert.equal(semAnsi(linhaFerramenta({ t: 'ferramenta', nome: 'pwsh', args: { command: 'npm test' } }, com)), '● pwsh npm test');
  assert.equal(semAnsi(linhaFerramenta({ t: 'ferramenta', nome: 'mcp__git__status', args: {} }, com)), '● mcp git › status');
  assert.equal(argPrincipal('grep', { pattern: 'foo', include: '*.ts' }), 'foo em *.ts');
  assert.equal(semAnsi(linhaResultado({ t: 'resultado', ok: true, resumo: '12 linhas', ms: 3400 }, com)), '  ⎿ 12 linhas · 3,4 s');
  assert.match(linhaResultado({ t: 'resultado', ok: false, resumo: 'falhou', ms: 5 }, com), /\x1b\[31m/);
  assert.equal(semAnsi(checklist([{ content: 'a', status: 'completed' }, { content: 'b', status: 'in_progress' }, { content: 'c', status: 'pending' }], com)),
    '  ☒ a\n  ◐ b\n  ☐ c');
  assert.equal(fmtTokens(950), '950');
  assert.equal(fmtTokens(1234), '1,2k');
  assert.equal(fmtTokens(16384), '16,4k');
  assert.equal(semAnsi(rodape({ modelo: 'qwen3:4b', raciocinio: 'medio', modo: 'perguntar', tokens: 1234, limite: 16384, mudados: 2 }, com)),
    'qwen3:4b · raciocínio médio · modo perguntar · contexto 1,2k de 16,4k (8%) · 2 arquivos mudados');
  assert.equal(mdLinha('## Titulo', sem), 'Titulo');
  assert.equal(mdLinha('- item com `codigo` e **negrito**', sem), '• item com codigo e negrito');
});

test('cor: so em terminal, e NO_COLOR desliga', () => {
  assert.equal(corLigada(true, {}), true);
  assert.equal(corLigada(false, {}), false);
  assert.equal(corLigada(true, { NO_COLOR: '1' }), false);
  assert.equal(corLigada(true, { TERM: 'dumb' }), false);
  assert.equal(corLigada(false, { FORCE_COLOR: '1' }), true);
});

test('/mudancas <arquivo>: os diffs vem das edicoes do historico', () => {
  const ev = [
    { t: 'ferramenta', id: 'a', nome: 'edit', args: { file_path: 'src\\x.ts' } },
    { t: 'resultado', id: 'a', ok: true, diff: '+um' },
    { t: 'ferramenta', id: 'b', nome: 'edit', args: { file_path: 'outro.ts' } },
    { t: 'resultado', id: 'b', ok: true, diff: '+dois' },
    { t: 'ferramenta', id: 'c', nome: 'write', args: { file_path: './src/x.ts' } },
    { t: 'resultado', id: 'c', ok: true, diff: '+tres' },
  ];
  assert.deepEqual(diffsDoArquivo(ev, 'src/x.ts'), ['+um', '+tres']);
  assert.deepEqual(diffsDoArquivo(ev, 'nada.ts'), []);
});

test('IDE: a janela abre a conversa pedida pelo terminal', () => {
  assert.equal(urlJanela(8998), 'http://127.0.0.1:8998/');
  assert.equal(urlJanela(8998, 'C:\\p'), 'http://127.0.0.1:8998/?pasta=C%3A%5Cp');
  assert.equal(urlJanela(8998, 'C:\\p', undefined, 'abc123xyz'), 'http://127.0.0.1:8998/?pasta=C%3A%5Cp&sessao=abc123xyz');
  assert.equal(urlJanela(8998, undefined, undefined, 'abc123xyz'), 'http://127.0.0.1:8998/', 'sem pasta nao ha o que abrir');
});

test('launchers/nous.cmd: acha o Node, roda de qualquer pasta (com espaco e acento) e devolve o codigo de saida', { skip: process.platform !== 'win32' }, async () => {
  const { spawnSync } = await import('node:child_process');
  const cmd = path.resolve(import.meta.dirname, '..', '..', 'launchers', 'nous.cmd');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'nc cli ação-'));
  const roda = (...args: string[]) => spawnSync('cmd.exe', ['/d', '/c', cmd, ...args], { cwd: dir, encoding: 'utf8', windowsHide: true });
  const v = roda('--versao');
  assert.equal(v.status, 0, v.stderr);
  assert.match(v.stdout, /^nous \d+\.\d+\.\d+ \(Nous Code \d+\.\d+\.\d+\)/);
  const a = roda('--ajuda');
  assert.equal(a.status, 0);
  assert.match(a.stdout, /nous -p "pedido"/);
  const e = roda('--modo', 'xyz');
  assert.equal(e.status, 2, 'o codigo de saida do CLI chega a quem chamou o .cmd');
  assert.match(e.stderr, /modo desconhecido: xyz/);
});
