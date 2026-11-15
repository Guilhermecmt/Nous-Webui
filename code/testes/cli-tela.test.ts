// O Renderizador: o que aparece na tela para cada evento do agente.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Renderizador, criarEstilo, semAnsi } from '../cli/tela.ts';

function novo(streaming = true) {
  const saida: string[] = [], ativ: string[] = [];
  const ren = new Renderizador({ saida: (s) => saida.push(s), atividade: (s) => ativ.push(s), est: criarEstilo(false), tty: false, streaming });
  return { ren, saida, ativ, tudo: () => saida.join('') + ativ.join('') };
}

test('resposta aparece aos poucos, por linha, com Markdown leve, e nao se repete no evento final', () => {
  const { ren, saida } = novo();
  ren.evento({ t: 'texto', d: 'Mudei o **arquivo** ' });
  assert.equal(saida.join(''), '', 'ainda sem linha inteira');
  ren.evento({ t: 'texto', d: 'agora.\n- item com `codigo`\n' });
  ren.evento({ t: 'texto', d: 'ultima linha sem quebra' });
  ren.evento({ t: 'resposta', texto: 'Mudei o **arquivo** agora.\n- item com `codigo`\nultima linha sem quebra' });
  ren.encerrar();
  assert.equal(saida.join(''), 'Mudei o arquivo agora.\n• item com codigo\nultima linha sem quebra\n');
  assert.equal(ren.ultimaResposta, 'Mudei o **arquivo** agora.\n- item com `codigo`\nultima linha sem quebra');
});

test('a chamada de ferramenta em JSON que o modelo escreve no texto nao aparece', () => {
  const { ren, tudo } = novo();
  ren.evento({ t: 'texto', d: '{"name": "read", "argum' });
  ren.evento({ t: 'texto', d: 'ents": {"file_path": "a.txt"}}\n' });
  ren.evento({ t: 'limpar' });
  ren.evento({ t: 'ferramenta', id: '1', nome: 'read', args: { file_path: 'a.txt' }, resumo: 'Lendo a.txt' });
  ren.evento({ t: 'resultado', id: '1', ok: true, resumo: '1 linhas', ms: 3 });
  assert.equal(tudo(), '● read a.txt\n  ⎿ 1 linhas\n');
});

test('texto antes da ferramenta fica; o evento "nota" com o mesmo texto nao duplica', () => {
  const { ren, saida, tudo } = novo();
  ren.evento({ t: 'texto', d: 'Vou ler o arquivo.\n' });
  ren.evento({ t: 'nota', texto: 'Vou ler o arquivo.' });
  ren.evento({ t: 'ferramenta', id: '1', nome: 'read', args: { file_path: 'a.txt' }, resumo: 'x' });
  assert.equal(saida.join(''), 'Vou ler o arquivo.\n');
  assert.equal(tudo(), 'Vou ler o arquivo.\n● read a.txt\n');
});

test('raciocinio vira uma linha so\', apagada do texto; resposta sem streaming (nada foi mostrado) aparece inteira', () => {
  const { ren, ativ, saida } = novo();
  ren.evento({ t: 'pensamento', d: 'Hmm, ' });
  ren.evento({ t: 'pensamento', d: 'o usuario quer ler\no arquivo.' });
  ren.evento({ t: 'texto', d: 'Pronto.\n' });
  assert.equal(semAnsi(ativ.join('')), '✻ Hmm, o usuario quer ler o arquivo.\n');
  assert.equal(saida.join(''), 'Pronto.\n');
  ren.evento({ t: 'resposta', texto: 'Pronto.' });
  assert.equal(saida.join(''), 'Pronto.\n', 'ja foi mostrada');
  ren.evento({ t: 'resposta', texto: 'Parei depois de 30 passos.' });
  assert.equal(saida.join(''), 'Pronto.\nParei depois de 30 passos.\n', 'resposta que nao veio em texto aparece');
});

test('codigo em bloco fica como esta, sem Markdown', () => {
  const { ren, saida } = novo();
  ren.evento({ t: 'texto', d: 'Assim:\n```ts\nconst a = **b**;\n```\n' });
  ren.evento({ t: 'resposta', texto: 'x' });
  assert.equal(semAnsi(saida.join('')), 'Assim:\n```ts\n  const a = **b**;\n```\n');
});

test('modo -p (sem streaming): so\' guarda a resposta final; o resto vai para a atividade', () => {
  const { ren, saida, ativ } = novo(false);
  ren.evento({ t: 'texto', d: 'rascunho' });
  ren.evento({ t: 'nota', texto: 'Vou olhar.' });
  ren.evento({ t: 'ferramenta', id: '1', nome: 'grep', args: { pattern: 'x' }, resumo: 'x' });
  ren.evento({ t: 'resposta', texto: 'Achei.' });
  ren.encerrar();
  assert.equal(saida.join(''), '', 'nada no stdout ate o fim');
  assert.equal(ren.ultimaResposta, 'Achei.');
  assert.match(ativ.join(''), /● grep x/);
});

test('diff da edicao automatica, erro, parado, tarefas e fim com as mudancas', () => {
  const { ren, tudo } = novo();
  ren.evento({ t: 'ferramenta', id: '1', nome: 'edit', args: { file_path: 'a.ts' }, resumo: 'x' });
  ren.evento({ t: 'resultado', id: '1', ok: true, resumo: '+1 -1', ms: 4, diff: '@@ -1 +1 @@\n-a\n+b\n' });
  assert.match(tudo(), /⎿ \+1 -1\n {4}@@ -1 \+1 @@\n {4}-a\n {4}\+b\n/);
  ren.evento({ t: 'resultado', id: '2', ok: false, resumo: 'erro', ms: 1, saida: 'cannot edit: not found' });
  assert.match(tudo(), /⎿ erro\n {4}cannot edit: not found/);
  ren.evento({ t: 'erro', texto: 'O Ollama nao respondeu.' });
  assert.equal(ren.erro, 'O Ollama nao respondeu.');
  const p = novo();
  p.ren.evento({ t: 'erro', texto: 'Parado por você.' });
  assert.equal(p.ren.erro, '', 'parar nao e\' falha');
  assert.equal(p.ren.parado, true);
  ren.evento({ t: 'passo', n: 1, tokens: 1234, limite: 16384 });
  ren.evento({ t: 'fim', mudancas: [{ arquivo: 'a.ts', mais: 1, menos: 1 }] });
  assert.equal(ren.tokens, 1234);
  assert.equal(ren.mudancas.length, 1);
});
