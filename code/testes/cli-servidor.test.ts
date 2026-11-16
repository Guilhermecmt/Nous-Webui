// O terminal (`nous`) contra o servico de verdade (servidor.ts) com um Ollama
// de mentira: autenticacao, modo -p, aprovacoes, /model, /effort, Ctrl+C.
import { test, before, after, beforeEach } from 'node:test';
import http from 'node:http';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import type { ChildProcess } from 'node:child_process';
import { Cliente, ErroApi, garantirServico, lerToken } from '../cli/cliente.ts';
import { lerArgs } from '../cli/args.ts';
import { imprimir, politicaImprimir, prefsDe } from '../cli/principal.ts';
import { Repl } from '../cli/repl.ts';
import { Renderizador, criarEstilo } from '../cli/tela.ts';
import { executarTurno } from '../cli/turno.ts';
import { IoFalso, ligarServico, ollamaFalso, pastaProjeto, semCor } from './apoio-cli.ts';
import { chamar } from './apoio.ts';

const ollama = ollamaFalso([{ name: 'falso', tools: true }, { name: 'qwen3:4b', tools: true, thinking: true }, { name: 'sem-ferramentas' }]);
let srv: Awaited<ReturnType<typeof ligarServico>>;
let cli: Cliente;
const abertos: ChildProcess[] = [];

before(async () => {
  const url = await ollama.ligar();
  srv = await ligarServico(url);
  cli = new Cliente(srv.base, srv.token);
});
after(() => { srv?.proc.kill(); ollama.desligar(); for (const p of abertos) { try { p.kill(); } catch { /* ja saiu */ } } });

beforeEach(() => { ollama.estado.roteiro.length = 0; });   // sobra de um teste nao vale para o outro

const est = criarEstilo(false);
const novoRen = (io: IoFalso, streaming = true) => new Renderizador({ saida: (s) => io.saida(s), atividade: (s) => io.atividade(s), est, tty: false, streaming });
const novoRepl = (pasta: string, io = new IoFalso()) => new Repl({ pasta, cliente: cli, io, est });

test('autenticacao: o token fica em NousData\\code, legivel so por quem usa o PC, e e\' de 256 bits', () => {
  const arq = path.join(srv.dados, 'code', 'cli-token');
  assert.match(fs.readFileSync(arq, 'utf8').trim(), /^[0-9a-f]{64}$/);
  assert.equal(lerToken(path.join(srv.dados, 'code')), srv.token);
  assert.equal(lerToken(path.join(srv.dados, 'nao-existe')), '', 'sem arquivo, sem token');
});

test('autenticacao: origem estranha sem token e token errado sao recusados; com token vale; as origens do Nous seguem iguais', async () => {
  const pede = (h: Record<string, string>, metodo = 'GET') => fetch(srv.base + '/ajustes', { method: metodo, headers: h });
  assert.equal((await pede({ Origin: 'https://site-ruim.example' })).status, 403, 'pagina qualquer nao fala com o servico');
  assert.equal((await pede({ Origin: 'https://site-ruim.example' }, 'OPTIONS')).status, 403, 'nem o preflight');
  assert.equal((await pede({ 'X-Nous-Token': 'errado' })).status, 403, 'token errado');
  assert.equal((await pede({ 'X-Nous-Token': 'a'.repeat(64) })).status, 403, 'token do tamanho certo mas errado');
  assert.equal((await pede({ 'X-Nous-Token': 'a'.repeat(64), Origin: 'http://localhost:8080' })).status, 403, 'token errado nao e\' salvo pela origem boa');
  assert.equal((await pede({ 'X-Nous-Token': srv.token })).status, 200, 'token certo');
  assert.equal((await pede({ 'X-Nous-Token': srv.token, Origin: 'https://site-ruim.example' })).status, 200, 'o terminal nao e\' uma pagina: o token basta');
  assert.equal((await pede({ Origin: 'http://localhost:8080' })).status, 200, 'o Nous continua entrando pela origem');
  assert.equal((await pede({ Origin: 'http://127.0.0.1:' + srv.porta })).status, 200, 'a janela do IDE tambem');
  assert.equal((await pede({})).status, 200, 'sem origem (atalhos do Windows, monitor) como sempre');
  // DNS rebinding: o nome do host continua conferido, mesmo com token
  const status = await new Promise<number>((ok, erro) => {
    const rq = http.request({ host: '127.0.0.1', port: srv.porta, path: '/ajustes', headers: { Host: 'evil.example', 'X-Nous-Token': srv.token } }, (res) => { res.resume(); ok(res.statusCode || 0); });
    rq.on('error', erro); rq.end();
  });
  assert.equal(status, 403);
  // o cabecalho do token nao e' liberado para outros sites pelo CORS
  const cors = await fetch(srv.base + '/ajustes', { method: 'OPTIONS', headers: { Origin: 'http://localhost:8080' } });
  assert.doesNotMatch(cors.headers.get('access-control-allow-headers') || '', /token/i);
});

test('cliente: sem o token certo a chamada vira um erro em portugues', async () => {
  const ruim = new Cliente(srv.base, 'b'.repeat(64));
  await assert.rejects(ruim.pedir('GET', '/ajustes'), (e: unknown) => e instanceof ErroApi && e.status === 403 && /recusou este terminal/.test(e.message));
});

test('-p: um pedido de ponta a ponta; a resposta vai para o stdout e a atividade para o stderr', async () => {
  const pasta = pastaProjeto({ 'a.txt': 'ola\n', 'b.py': 'x = 1\n' });
  ollama.estado.roteiro.push(chamar('list_files', { path: '.' }), 'Achei a.txt e b.py.');
  const io = new IoFalso();
  const codigo = await imprimir(lerArgs(['-p', 'liste os arquivos']), 'liste os arquivos', cli, pasta, io);
  assert.equal(codigo, 0);
  assert.equal(io.saidas.join(''), 'Achei a.txt e b.py.\n', 'so a resposta final no stdout');
  const ativ = semCor(io.atividades.join(''));
  assert.match(ativ, /● list_files \./, 'a ferramenta aparece como uma linha compacta');
  assert.match(ativ, /⎿ 2 itens/, 'e o resultado resumido');
  // a conversa fica na lista do IDE
  const lista = await cli.pedir('GET', '/sessoes?pasta=' + encodeURIComponent(pasta));
  assert.equal(lista.length, 1);
});

test('-p: sem --modo editar ou total os pedidos de aprovacao sao recusados; com eles passam', async () => {
  const pasta = pastaProjeto();
  ollama.estado.roteiro.push(chamar('read', { file_path: 'a.txt' }), chamar('write', { file_path: 'novo.txt', content: 'oi\n' }), 'Nao consegui gravar.');
  const io = new IoFalso();
  assert.equal(await imprimir(lerArgs(['-p', 'x']), 'crie novo.txt', cli, pasta, io), 0);
  assert.equal(fs.existsSync(path.join(pasta, 'novo.txt')), false, 'recusado sem quem aprovar');
  assert.match(semCor(io.atividades.join('')), /recusado/);
  assert.equal(io.perguntasTecla.length, 0, 'o modo -p nunca espera pela pessoa');

  const pasta2 = pastaProjeto();
  ollama.estado.roteiro.push(chamar('read', { file_path: 'a.txt' }), chamar('write', { file_path: 'novo.txt', content: 'oi\n' }), 'Gravei novo.txt.');
  const io2 = new IoFalso();
  assert.equal(await imprimir(lerArgs(['-p', 'x', '--modo', 'editar']), 'crie novo.txt', cli, pasta2, io2), 0);
  assert.equal(fs.readFileSync(path.join(pasta2, 'novo.txt'), 'utf8'), 'oi\n', '--modo editar libera as mudancas em arquivo');
  assert.equal(io2.saidas.join(''), 'Gravei novo.txt.\n');
});

test('-p: comando perigoso so\' passa em --modo total, e nunca em editar', () => {
  const comum = { t: 'pede', tipo: 'comando', comando: 'npm test' };
  const perigo = { t: 'pede', tipo: 'comando', comando: 'rm -rf x', perigo: 'apaga arquivos' };
  assert.deepEqual(politicaImprimir(undefined)(comum), { ok: false });
  assert.deepEqual(politicaImprimir('perguntar')(comum), { ok: false });
  assert.deepEqual(politicaImprimir('leitura')({ t: 'pede', tipo: 'arquivo' }), { ok: false });
  assert.deepEqual(politicaImprimir('editar')(comum), { ok: true });
  assert.deepEqual(politicaImprimir('editar')(perigo), { ok: false });
  assert.deepEqual(politicaImprimir('total')(perigo), { ok: false }, 'o -p nao libera comando perigoso nem em total');
  assert.deepEqual(politicaImprimir('total')({ t: 'pede', tipo: 'internet', alvo: 'x' }), { ok: false });
});

test('-p com --model e --effort: valem na conversa criada', async () => {
  const pasta = pastaProjeto();
  ollama.estado.roteiro.push('Oi.');
  const io = new IoFalso();
  assert.equal(await imprimir(lerArgs(['-p', 'oi', '--model', 'qwen3:4b', '--effort', 'low']), 'oi', cli, pasta, io), 0);
  const [s] = await cli.pedir('GET', '/sessoes?pasta=' + encodeURIComponent(pasta));
  const v = await cli.pedir('GET', '/sessao?id=' + s.id);
  assert.equal(v.modelo, 'qwen3:4b');
  assert.equal(v.raciocinio, 'baixo');
});

test('-p --continuar retoma a ultima conversa da pasta', async () => {
  const pasta = pastaProjeto();
  ollama.estado.roteiro.push('Primeira.', 'Segunda.');
  await imprimir(lerArgs(['-p', 'um']), 'primeiro pedido', cli, pasta, new IoFalso());
  await imprimir(lerArgs(['-p', 'dois', '-c']), 'segundo pedido', cli, pasta, new IoFalso());
  const lista = await cli.pedir('GET', '/sessoes?pasta=' + encodeURIComponent(pasta));
  assert.equal(lista.length, 1, 'a mesma conversa');
  const v = await cli.pedir('GET', '/sessao?id=' + lista[0].id);
  assert.deepEqual(v.eventos.filter((e: { t: string }) => e.t === 'voce').map((e: { texto: string }) => e.texto), ['primeiro pedido', 'segundo pedido']);
});

test('aprovacao: sim grava e mostra o diff; nao nao grava; o diff nao se repete no resultado', async () => {
  const pasta = pastaProjeto();
  const repl = novoRepl(pasta);
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  ollama.estado.roteiro.push(chamar('read', { file_path: 'a.txt' }), chamar('edit', { file_path: 'a.txt', old_string: 'ola', new_string: 'ola mundo' }), 'Editei.');
  const io = new IoFalso();
  io.teclas.push('s');
  const r = await executarTurno(cli, id, 'mude o a.txt', io, novoRen(io));
  const saida = semCor(io.tudo());
  assert.match(saida, /Mudar a\.txt\? \+1 −1/, 'o titulo do pedido');
  assert.match(saida, /\+ola mundo/, 'o diff com + e -');
  assert.match(saida, /-ola/);
  assert.match(saida, /\[s\]im {2}\[n\]ão {2}\[a\] sempre/);
  assert.match(saida, /✓ aprovado/);
  assert.equal(fs.readFileSync(path.join(pasta, 'a.txt'), 'utf8'), 'ola mundo\n');
  assert.equal((saida.match(/\+ola mundo/g) || []).length, 1, 'o diff aparece so\' uma vez');
  assert.equal(r.resposta, 'Editei.');
  assert.equal(r.mudancas.length, 1);
  assert.deepEqual(io.perguntasTecla[0], ['s', 'n', 'a', 'y']);

  ollama.estado.roteiro.push(chamar('edit', { file_path: 'a.txt', old_string: 'mundo', new_string: 'planeta' }), 'Ok, nao mudei.');
  const io2 = new IoFalso();
  io2.teclas.push('n');
  await executarTurno(cli, id, 'mude de novo', io2, novoRen(io2));
  assert.equal(fs.readFileSync(path.join(pasta, 'a.txt'), 'utf8'), 'ola mundo\n', 'recusado: nada muda');
  assert.match(semCor(io2.tudo()), /✗ recusado/);
});

test('aprovacao: [a] sempre num arquivo sobe o modo para editar; e a proxima mudanca ja nao pergunta', async () => {
  const pasta = pastaProjeto();
  const io = new IoFalso();
  const repl = novoRepl(pasta, io);
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  ollama.estado.roteiro.push(chamar('read', { file_path: 'a.txt' }), chamar('write', { file_path: 'a.txt', content: 'um\n' }), 'Feito.');
  io.teclas.push('a');
  await repl.enviar('troque o conteudo');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).modo, 'editar', 'sempre = editar sem perguntar');
  assert.match(semCor(io.tudo()), /Modo mudado para editar/);
  assert.equal(fs.readFileSync(path.join(pasta, 'a.txt'), 'utf8'), 'um\n');
  // dentro do projeto, a proxima mudanca ja' nao pergunta
  ollama.estado.roteiro.push(chamar('write', { file_path: 'a.txt', content: 'dois\n' }), 'Feito.');
  await repl.enviar('de novo');
  assert.equal(fs.readFileSync(path.join(pasta, 'a.txt'), 'utf8'), 'dois\n');
  assert.equal(io.teclas.length, 0);
});

test('aprovacao de comando: mostra o comando; esc recusa e para o turno', async () => {
  const pasta = pastaProjeto();
  const repl = novoRepl(pasta);
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  ollama.estado.roteiro.push(chamar('pwsh', { command: 'echo oi', description: 'diz oi' }), 'Depois.');
  const io = new IoFalso();
  io.teclas.push('esc');
  const r = await executarTurno(cli, id, 'rode echo', io, novoRen(io));
  const saida = semCor(io.tudo());
  assert.match(saida, /diz oi/);
  assert.match(saida, /echo oi/);
  assert.equal(r.interrompido, true, 'esc no pedido tambem interrompe');
  const v = await cli.pedir('GET', '/sessao?id=' + id);
  assert.equal(v.rodando, false);
});

test('ask_user_question: opcoes numeradas e a resposta volta ao modelo', async () => {
  const pasta = pastaProjeto();
  const repl = novoRepl(pasta);
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  ollama.estado.roteiro.push(chamar('ask_user_question', { questions: [{ id: 'cor', question: 'Qual cor?', options: [{ label: 'Azul', description: 'frio' }, { label: 'Verde' }] }] }), 'Usei Verde.');
  const io = new IoFalso();
  io.linhas.push('2');
  const r = await executarTurno(cli, id, 'pergunte a cor', io, novoRen(io));
  const saida = semCor(io.tudo());
  assert.match(saida, /Qual cor\?/);
  assert.match(saida, /1\. Azul - frio/);
  assert.match(saida, /2\. Verde/);
  assert.equal(r.resposta, 'Usei Verde.');
  const v = await cli.pedir('GET', '/sessao?id=' + id);
  const resposta = v.eventos.find((e: { t: string }) => e.t === 'aprovado');
  assert.deepEqual(JSON.parse(resposta.texto), [{ id: 'cor', selected: ['Verde'] }]);
});

test('exit_plan_mode: aprovar executa; continuar planejando leva o comentario', async () => {
  const pasta = pastaProjeto();
  const repl = novoRepl(pasta);
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  await cli.pedir('POST', '/sessao/ajustes', { id, planejando: true });
  ollama.estado.roteiro.push(chamar('exit_plan_mode', { plan: '# Plano\n\n- passo um\n- passo dois' }), chamar('exit_plan_mode', { plan: '# Plano 2\n\n- unico passo' }), 'Plano entregue.');
  const io = new IoFalso();
  io.teclas.push('c', 'a');
  io.linhas.push('faca em um passo so');
  await executarTurno(cli, id, 'planeje', io, novoRen(io));
  const saida = semCor(io.tudo());
  assert.match(saida, /Plano proposto/);
  assert.match(saida, /• passo um/);
  const v = await cli.pedir('GET', '/sessao?id=' + id);
  const apr = v.eventos.filter((e: { t: string }) => e.t === 'aprovado');
  assert.equal(apr[0].ok, false);
  assert.equal(apr[0].texto, 'faca em um passo so');
  assert.equal(apr[1].ok, true);
  assert.equal(v.planejando, false, 'aprovado: sai do modo plano');
});

test('todo_write: a lista aparece como checklist', async () => {
  const repl = novoRepl(pastaProjeto());
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  ollama.estado.roteiro.push(chamar('todo_write', { todos: [{ content: 'ler', status: 'completed' }, { content: 'editar', status: 'in_progress' }, { content: 'testar', status: 'pending' }] }), 'Pronto.');
  const io = new IoFalso();
  await executarTurno(cli, id, 'liste', io, novoRen(io));
  assert.match(semCor(io.tudo()), /☒ ler\n {2}◐ editar\n {2}☐ testar/);
});

test('/effort e /model mudam a conversa; apelidos em ingles e valores nos dois idiomas', async () => {
  const pasta = pastaProjeto();
  const io = new IoFalso();
  const repl = novoRepl(pasta, io);
  await repl.carregarPadroes();
  // antes da conversa existir, o ajuste espera e vale quando ela nasce
  await repl.tratar('/effort high');
  assert.equal(repl.sessao, null, 'sem conversa vazia na lista so\' por causa de um ajuste');
  await repl.tratar('/model qwen3:4b');
  const id = await repl.garantirSessao();
  let v = await cli.pedir('GET', '/sessao?id=' + id);
  assert.equal(v.raciocinio, 'alto');
  assert.equal(v.modelo, 'qwen3:4b');
  await repl.tratar('/raciocinio baixo');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).raciocinio, 'baixo');
  await repl.tratar('/effort off');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).raciocinio, 'desligado');
  await repl.tratar('/effort medium');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).raciocinio, 'medio');
  await repl.tratar('/effort enorme');
  assert.match(semCor(io.tudo()), /Raciocínio desconhecido: enorme/);
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).raciocinio, 'medio', 'valor invalido nao muda nada');
  // /model pelo numero e pelo trecho do nome; sem argumento, um menu
  await repl.tratar('/modelo 1');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).modelo, 'falso');
  await repl.tratar('/model qwen');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).modelo, 'qwen3:4b');
  io.linhas.push('falso');
  await repl.tratar('/model');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).modelo, 'falso');
  const tela = semCor(io.tudo());
  assert.match(tela, /Modelos instalados/);
  assert.match(tela, /qwen3:4b.*ferramentas raciocínio/, 'os sinais de cada modelo');
  assert.match(tela, /sem-ferramentas.*sem ferramentas/);
  v = await cli.pedir('GET', '/sessao?id=' + id);
});

test('/modo e /alcance pedem confirmacao antes de liberar mais; recusar nao muda', async () => {
  const io = new IoFalso();
  const repl = novoRepl(pastaProjeto(), io);
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  io.teclas.push('n');
  await repl.tratar('/modo total');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).modo, 'perguntar');
  io.teclas.push('s');
  await repl.tratar('/permissions total');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).modo, 'total');
  await repl.tratar('/modo leitura');   // diminuir nao pergunta
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).modo, 'leitura');
  io.teclas.push('n');
  await repl.tratar('/alcance computador');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).alcance, 'projeto');
  io.teclas.push('s');
  await repl.tratar('/alcance usuario');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).alcance, 'usuario');
  await repl.tratar('/alcance projeto');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).alcance, 'projeto');
  assert.equal(io.teclas.length, 0);
  assert.match(semCor(io.tudo()), /Acesso total: o agente muda arquivos/);
});

test('o alcance do servico decide a pasta: a pasta do usuario e recusada, e --alcance usuario a libera', async () => {
  const repl = novoRepl(srv.casa);
  await repl.carregarPadroes();
  await assert.rejects(repl.garantirSessao(), /sua pasta de usuario inteira.*nous --alcance usuario/);
  const r2 = new Repl({ pasta: srv.casa, cliente: cli, io: new IoFalso(), est, prefs: { alcance: 'usuario' } });
  await r2.carregarPadroes();
  const id = await r2.garantirSessao();
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).alcance, 'usuario');
  assert.equal((await cli.pedir('GET', '/ajustes')).alcance, 'projeto', 'a opcao vale para a conversa; o padrao geral nao muda');
});

test('o `nous` sem opcoes abre na pasta do usuario: o padrao do terminal e o computador inteiro', async () => {
  const repl = new Repl({ pasta: srv.casa, cliente: cli, io: new IoFalso(), est, prefs: prefsDe(lerArgs([])) });
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  const s = await cli.pedir('GET', '/sessao?id=' + id);
  assert.equal(s.alcance, 'computador');
  assert.equal(path.resolve(s.pasta), path.resolve(srv.casa));
  assert.equal(s.modo, (await cli.pedir('GET', '/ajustes')).modo, 'o modo continua o padrao (pede antes de mudar)');
});

test('/contexto, /novo, /conversas, /mudancas, /desfazer, /exportar', async () => {
  const pasta = pastaProjeto();
  const io = new IoFalso();
  const repl = novoRepl(pasta, io);
  await repl.carregarPadroes();
  ollama.estado.roteiro.push(chamar('read', { file_path: 'a.txt' }), chamar('write', { file_path: 'a.txt', content: 'trocado\n' }), 'Troquei.');
  await cli.pedir('POST', '/ajustes', { modo: 'editar' });
  try { await repl.enviar('troque o a.txt'); } finally { await cli.pedir('POST', '/ajustes', { modo: 'perguntar' }); }
  assert.equal(fs.readFileSync(path.join(pasta, 'a.txt'), 'utf8'), 'trocado\n');
  assert.match(semCor(io.tudo()), /contexto 1,2k de 16,4k \(7%\) · 1 arquivo mudado/, 'o rodape depois do turno');

  io.saidas.length = 0;
  await repl.tratar('/status');
  const ctx = semCor(io.tudo());
  assert.match(ctx, /modelo\s+falso/);
  assert.match(ctx, /pasta\s+/);
  assert.match(ctx, /1,2k de 16,4k tokens \(7%\)/);

  io.saidas.length = 0;
  await repl.tratar('/diff');
  assert.match(semCor(io.tudo()), /a\.txt \+1 −1/);
  io.saidas.length = 0;
  await repl.tratar('/mudancas a.txt');
  assert.match(semCor(io.tudo()), /\+trocado/);

  await repl.tratar('/exportar saida.md');
  assert.match(fs.readFileSync(path.join(pasta, 'saida.md'), 'utf8'), /troque o a\.txt/);

  io.teclas.push('s');
  await repl.tratar('/undo');
  assert.equal(fs.readFileSync(path.join(pasta, 'a.txt'), 'utf8'), 'ola\n', 'desfeito');

  const velha = repl.sessao;
  await repl.tratar('/clear');
  assert.equal(repl.sessao, null);
  io.saidas.length = 0;
  io.linhas.push('1');
  await repl.tratar('/resume');
  assert.equal(repl.sessao, velha, 'voltou para a conversa anterior');
  const tela = semCor(io.tudo());
  assert.match(tela, /Conversa retomada/);
  assert.match(tela, /❯ troque o a\.txt/);
  assert.match(tela, /Troquei\./);
});

test('/padrao, /plano, /objetivo, /compactar, /mcp, /skills e comando desconhecido', async () => {
  const pasta = pastaProjeto();
  fs.mkdirSync(path.join(pasta, '.nous', 'skills', 'revisar'), { recursive: true });
  fs.writeFileSync(path.join(pasta, '.nous', 'skills', 'revisar', 'SKILL.md'), '---\nname: revisar\ndescription: Revisa o codigo\n---\nRevise.\n');
  const io = new IoFalso();
  const repl = novoRepl(pasta, io);
  await repl.carregarPadroes();
  await repl.tratar('/padrao');
  assert.match(semCor(io.tudo()), /modo\s+perguntar/);
  io.teclas.push('n');
  await repl.tratar('/padrao modo total');
  assert.equal((await cli.pedir('GET', '/ajustes')).modo, 'perguntar', 'liberar mais pede confirmacao');

  await repl.tratar('/plano');
  const id = repl.sessao!;
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).planejando, true);
  await repl.tratar('/plan sair');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).planejando, false);

  ollama.estado.roteiro.push('Comecei o objetivo.', 'Concluido.');
  await repl.tratar('/objetivo testes passando');
  const o = (await cli.pedir('GET', '/sessao?id=' + id)).objetivo;
  assert.equal(o.objective, 'testes passando');
  await repl.tratar('/objetivo limpar');
  assert.equal((await cli.pedir('GET', '/sessao?id=' + id)).objetivo, null);

  io.saidas.length = 0;
  await repl.tratar('/compact');
  assert.match(semCor(io.tudo()), /Compactando|ainda é curta/);

  io.saidas.length = 0;
  await repl.tratar('/mcp');
  assert.match(semCor(io.tudo()), /não tem servidores MCP/);

  io.saidas.length = 0;
  await repl.tratar('/skills');
  assert.match(semCor(io.tudo()), /\/revisar\s+Revisa o codigo/);

  io.saidas.length = 0;
  await repl.tratar('/inexistente');
  assert.match(semCor(io.tudo()), /Comando desconhecido: \/inexistente/);

  // /nome-da-skill vai para o agente
  ollama.estado.roteiro.push('Revisado.');
  io.saidas.length = 0;
  await repl.tratar('/revisar a.txt');
  const v = await cli.pedir('GET', '/sessao?id=' + id);
  assert.ok(v.eventos.some((e: { t: string; texto?: string }) => e.t === 'voce' && e.texto === '/revisar a.txt'));
});

test('Ctrl+C / Esc: para o turno pelo caminho do /parar e a conversa fica livre', async () => {
  const pasta = pastaProjeto();
  const repl = novoRepl(pasta);
  await repl.carregarPadroes();
  const id = await repl.garantirSessao();
  const chamadas: string[] = [];
  const espiao = new Cliente(srv.base, srv.token);
  const pedir = espiao.pedir.bind(espiao);
  espiao.pedir = (async (m: 'GET' | 'POST', c: string, corpo?: object, sinal?: AbortSignal) => { chamadas.push(m + ' ' + c); return pedir(m, c, corpo, sinal); }) as typeof espiao.pedir;

  ollama.estado.roteiro.push({ esperar: true });
  const antes = ollama.estado.esperando;
  const io = new IoFalso();
  const turno = executarTurno(espiao, id, 'pense para sempre', io, novoRen(io));
  for (let i = 0; i < 100 && ollama.estado.esperando === antes; i++) await new Promise((ok) => setTimeout(ok, 50));
  assert.equal(ollama.estado.esperando, antes + 1, 'o modelo comecou a pensar');
  assert.ok(io.interrupcao, 'o terminal escuta Esc e Ctrl+C durante o turno');
  io.interrupcao!();
  const r = await turno;
  assert.equal(r.interrompido, true);
  assert.ok(chamadas.includes('POST /parar'), 'chamou o /parar do servico: ' + chamadas.join(', '));
  assert.match(semCor(io.tudo()), /Interrompendo…/);
  assert.match(semCor(io.tudo()), /Parado por você\./);
  assert.equal(io.interrupcao, null, 'a escuta termina com o turno');
  assert.equal(r.erro, '', 'parar nao e\' falha');
  const v = await cli.pedir('GET', '/sessao?id=' + id);
  assert.equal(v.rodando, false);
  // e a conversa segue funcionando
  ollama.estado.roteiro.push('Voltei.');
  const io2 = new IoFalso();
  const r2 = await executarTurno(cli, id, 'oi', io2, novoRen(io2));
  assert.equal(r2.resposta, 'Voltei.');
});

test('garantirServico: liga o servico sozinho quando ele nao esta no ar', async () => {
  const antes = { ...process.env };
  const porta = srv.porta + 150;
  const dados = fs.mkdtempSync(path.join(srv.dados, 'auto-'));
  Object.assign(process.env, { NOUS_CODE_PORT: String(porta), DATA_DIR: dados, USERPROFILE: srv.casa, OLLAMA_BASE_URL: 'http://127.0.0.1:1', NOUS_CODE_DIAGNOSTICOS: '0' });
  let pid = 0, avisou = false;
  try {
    const c = await garantirServico({ aoIniciar: () => { avisou = true; }, aoFilho: (p) => { pid = p; } });
    assert.equal(avisou, true);
    assert.ok(pid > 0);
    assert.equal(c.base, 'http://127.0.0.1:' + porta);
    assert.match(c.token, /^[0-9a-f]{64}$/, 'leu o token que o servico acabou de criar');
    assert.equal((await c.pedir('GET', '/health')).ok, true);
    // ja' no ar: nao liga outro
    avisou = false;
    await garantirServico({ aoIniciar: () => { avisou = true; } });
    assert.equal(avisou, false);
  } finally {
    if (pid) { try { process.kill(pid); } catch { /* ja saiu */ } }
    for (const k of Object.keys(process.env)) if (!(k in antes)) delete process.env[k];
    Object.assign(process.env, antes);
  }
});
