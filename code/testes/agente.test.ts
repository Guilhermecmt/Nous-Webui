// Testes das politicas do agente com um "Ollama de mentira": cada pedido ao
// /api/chat devolve a proxima resposta do roteiro. Sem modelo de verdade.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { AddressInfo } from 'node:net';

// as edicoes aqui nao consultam o language server (isso e' testado em diagnosticos.test.ts)
process.env.NOUS_CODE_DIAGNOSTICOS = '0';
let roteiro: string[] = [];
let pedidos: { messages: { role: string; content: string }[] }[] = [];
const falso = http.createServer((req, res) => {
  let corpo = '';
  req.on('data', (d) => { corpo += d; });
  req.on('end', () => {
    const b = JSON.parse(corpo || '{}');
    pedidos.push(b);
    const conteudo = roteiro.shift() ?? 'Pronto.';
    if (b.stream === false) { res.end(JSON.stringify({ message: { role: 'assistant', content: conteudo }, done: true })); return; }
    res.write(JSON.stringify({ message: { role: 'assistant', content: conteudo }, done: false }) + '\n');
    res.end(JSON.stringify({ message: { role: 'assistant', content: '' }, done: true, prompt_eval_count: 100, eval_count: 10 }) + '\n');
  });
});

type Mod = typeof import('../agente.ts');
let A: Mod;
let raiz = '';
before(async () => {
  await new Promise<void>((ok) => falso.listen(0, '127.0.0.1', () => ok()));
  process.env.OLLAMA_BASE_URL = 'http://127.0.0.1:' + (falso.address() as AddressInfo).port;
  A = await import('../agente.ts');
  const J = await import('../jobs.ts');
  J.configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-jobs-')));
  (await import('../ferramentas.ts')).configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-saidas-')));
  (await import('../lembretes.ts')).configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-lem-')));
  (await import('../mcp.ts')).configurar(fs.mkdtempSync(path.join(os.tmpdir(), 'nc-mcp-')));
});
after(() => { falso.close(); });

const chamar = (nome: string, args: object) => JSON.stringify({ name: nome, arguments: args });

function novaSessao(modo: 'leitura' | 'perguntar' | 'editar' | 'total' = 'editar') {
  raiz = fs.mkdtempSync(path.join(os.tmpdir(), 'nc-ag-'));
  fs.writeFileSync(path.join(raiz, 'a.js'), 'const x = 1;\n');
  return A.normalizar({ id: 'teste' + Math.random().toString(36).slice(2, 8), pasta: raiz, modelo: 'falso', modo, tituloAuto: false });
}

async function rodar(s: ReturnType<typeof novaSessao>, pedido: string, respostas: Record<string, object> = {}, origem: 'humano' | 'lembrete' = 'humano') {
  const eventos: Record<string, unknown>[] = [];
  await A.turno(s, pedido, {
    emitir: (e) => eventos.push(e), salvar: () => {}, sinal: new AbortController().signal,
    aprovar: async (e) => { eventos.push(e); return (respostas[String(e.tipo)] as { ok: boolean }) || { ok: true }; },
  }, origem);
  return eventos;
}
const conteudos = (s: { mensagens: { role: string; content: string }[] }, papel: string) => s.mensagens.filter((m) => m.role === papel).map((m) => m.content);
const resultados = (ev: Record<string, unknown>[]) => ev.filter((e) => e.t === 'resultado');

test('editar sem ler antes e\' recusado; depois de ler, passa (nomes antigos ainda valem)', async () => {
  const s = novaSessao();
  roteiro = [chamar('edit_file', { path: 'a.js', old_text: '1', new_text: '2' }), chamar('read', { file_path: 'a.js' }),
    chamar('edit', { file_path: 'a.js', old_string: 'x = 1', new_string: 'x = 2' }), 'Pronto: troquei.'];
  const ev = await rodar(s, 'troque 1 por 2');
  const r = resultados(ev);
  assert.equal(r[0].ok, false);
  assert.equal(conteudos(s, 'tool')[0], 'Error: cannot modify "a.js": file has not been read — read the file, then retry');
  assert.equal(r[2].ok, true);
  assert.equal(conteudos(s, 'tool')[2], 'The file a.js has been updated successfully.');
  assert.equal(fs.readFileSync(path.join(raiz, 'a.js'), 'utf8'), 'const x = 2;\n');
});

test('arquivo que mudou no disco depois da leitura: pede para ler de novo', async () => {
  const s = novaSessao();
  roteiro = [chamar('read', { file_path: 'a.js' })];
  await rodar(s, 'leia');
  fs.writeFileSync(path.join(raiz, 'a.js'), 'const x = 9;\n');
  fs.utimesSync(path.join(raiz, 'a.js'), new Date(), new Date(Date.now() + 5000));
  roteiro = [chamar('edit', { file_path: 'a.js', old_string: 'x = 9', new_string: 'x = 3' }), 'ok'];
  const r = resultados(await rodar(s, 'troque'));
  assert.equal(r[0].ok, false);
  assert.match(String(r[0].saida), /cannot edit "a\.js": file changed since it was read — re-read the file, then retry/);
});

test('primeiro pedido leva o contexto de execucao e a hora; modo plano entra no contexto', async () => {
  const s = novaSessao();
  s.planejando = true;
  roteiro = [chamar('write', { file_path: 'b.js', content: 'x' }), chamar('exit_plan_mode', { plan: '# Criar b.js\n1. criar' }), 'Vou implementar.'];
  const ev = await rodar(s, 'planeje');
  const users = conteudos(s, 'user');
  assert.ok(users.some((u) => u.startsWith('Current runtime context. This snapshot supersedes') && u.includes('You are in plan mode.')));
  assert.ok(users.some((u) => /^Time sampled while preparing turn 1, step 1: \d{4}-\d{2}-\d{2}T/.test(u)));
  const r = resultados(ev);
  assert.match(String(r[0].saida), /^POLICY_DENIED: plan mode is active/);
  assert.ok(ev.some((e) => e.t === 'pede' && e.tipo === 'plano'));
  assert.equal(conteudos(s, 'tool')[1], 'Plan approved — plan mode exited; carry out the plan starting with your next step.');
  assert.equal(s.planejando, false);
  assert.ok(!fs.existsSync(path.join(raiz, 'b.js')));
  // no proximo pedido o contexto novo (sem o plano) vai de novo, sem narrar a troca outra vez
  roteiro = ['ok'];
  await rodar(s, 'siga');
  const ultimo = conteudos(s, 'user').filter((u) => u.startsWith('Current runtime context')).at(-1)!;
  assert.ok(!ultimo.includes('You are in plan mode.'));
  assert.ok(!conteudos(s, 'user').some((u) => u.includes('switched this session back')));
});

test('continuar planejando devolve o feedback ao modelo', async () => {
  const s = novaSessao();
  s.planejando = true;
  roteiro = [chamar('exit_plan_mode', { plan: 'plano A' }), 'Ok, vou rever.'];
  const ev = await rodar(s, 'planeje', { plano: { ok: false, texto: 'use outra pasta' } });
  assert.equal(s.planejando, true);
  assert.equal(String(resultados(ev)[0].saida), 'The user chose to keep planning; their feedback: use outra pasta');
  assert.match(String(ev.find((e) => e.t === 'pede')?.plano), /^# Plano\n\nplano A$/);
});

test('somente leitura bloqueia comandos; ligar o plano no meio narra a troca', async () => {
  const s = novaSessao('leitura');
  roteiro = [chamar('run_command', { command: 'echo oi' }), 'Entendi.'];
  const r = resultados(await rodar(s, 'rode'));
  assert.match(String(r[0].saida), /^POLICY_DENIED: this conversation is read-only/);
  s.planejando = true;
  roteiro = ['ok'];
  await rodar(s, 'planeje');
  assert.ok(conteudos(s, 'user').includes('The user switched this session to plan mode.'));
});

test('comando que passa do tempo vira job; o fim chega como aviso e job_output le so\' o novo', async () => {
  const s = novaSessao('total');
  roteiro = [chamar('pwsh', { description: 'Espera e escreve', command: 'Write-Output comeco; Start-Sleep -Seconds 6; Write-Output fim', timeoutMs: 3000 }), 'Esperando.'];
  const r = resultados(await rodar(s, 'rode'));
  assert.match(String(r[0].saida), /comeco\n\[still running after 3000ms; moved to background job j1\]\nThe command keeps running in the background/);
  await new Promise((ok) => setTimeout(ok, 5500));
  roteiro = [chamar('job_output', { job_id: 'j1' }), 'ok'];
  const r2 = resultados(await rodar(s, 'veja'));
  assert.ok(conteudos(s, 'user').some((u) => /^background job j1 \(pwsh: Espera e escreve\) finished \[status: completed, exit code: 0\]\. Read its output with job_output\.$/.test(u)));
  assert.match(String(r2[0].saida), /^fim\s*\n\[status: completed, exit code: 0\]$/);
});

test('pwsh em primeiro plano termina com [exit code: N] e nao vira erro', async () => {
  const s = novaSessao('total');
  roteiro = [chamar('pwsh', { description: 'Sai com 3', command: 'Write-Output oi; exit 3' }), 'Viu.'];
  const r = resultados(await rodar(s, 'rode'));
  assert.equal(conteudos(s, 'tool')[0], 'oi\n[exit code: 3]');
  assert.equal(r[0].ok, false);
});

test('todo_write e ask_user_question devolvem no formato do dsh', async () => {
  const s = novaSessao();
  roteiro = [chamar('todo_write', { todos: [{ content: 'ler', status: 'completed' }, { content: 'mudar', status: 'in_progress' }] }),
    chamar('ask_user', { question: 'Qual pasta?', options: ['src', 'lib'] }), 'Certo.'];
  const ev = await rodar(s, 'faca', { perguntas: { ok: true, texto: JSON.stringify([{ id: 'q1', selected: ['lib'] }]) } });
  const r = resultados(ev);
  assert.equal(s.tarefas.length, 2);
  assert.equal(conteudos(s, 'tool')[0], 'Updated todo list: 0 pending, 1 in progress, 1 completed.');
  assert.deepEqual(JSON.parse(String(r[1].saida)), { answers: [{ id: 'q1', selected: ['lib'] }] });
  const pede = ev.find((e) => e.t === 'pede') as { perguntas: { opcoes: { label: string }[] }[] };
  assert.deepEqual(pede.perguntas[0].opcoes.map((o) => o.label), ['src', 'lib']);
});

test('varias chamadas no mesmo passo rodam em ordem', async () => {
  const s = novaSessao();
  roteiro = [chamar('read', { file_path: 'a.js' }) + '\n' + chamar('glob', { pattern: '*.js' }), 'ok'];
  const r = resultados(await rodar(s, 'olhe'));
  assert.equal(r.length, 2);
  assert.match(String(r[1].saida), /^a\.js$/);
});

test('repeticao: avisos do dsh na 3a, 5a e 8a, e para na 10a', async () => {
  const s = novaSessao();
  roteiro = Array(10).fill(chamar('read', { file_path: 'a.js' }));
  const ev = await rodar(s, 'leia muito');
  const avisos = conteudos(s, 'user').filter((u) => /repeating the exact same tool call|Repeated tool call detected/.test(u));
  assert.equal(avisos.length, 3);
  assert.match(avisos[0], /^You are repeating the exact same tool call with identical arguments\./);
  assert.match(avisos[1], /consecutive_calls: 5/);
  assert.ok(ev.some((e) => e.t === 'resposta' && /dez vezes/.test(String(e.texto))));
});

test('@arquivo no pedido anexa o conteudo e conta como lido', async () => {
  const s = novaSessao();
  roteiro = [chamar('edit', { file_path: 'a.js', old_string: 'x = 1', new_string: 'x = 5' }), 'ok'];
  const r = resultados(await rodar(s, 'mude @a.js'));
  assert.ok(pedidos.at(-2)!.messages.some((m) => m.role === 'user' && m.content.includes('<path>a.js</path>\n<type>file</type>\n<content>\n1: const x = 1;')));
  assert.equal(r[0].ok, true);
});

test('objetivo: rodadas automaticas ate\' o modelo concluir, com mensagem de fechamento', async () => {
  const s = novaSessao();
  roteiro = [chamar('create_goal', { objective: 'x vale 3' }), 'Comecei.',
    chamar('read', { file_path: 'a.js' }), chamar('edit', { file_path: 'a.js', old_string: 'x = 1', new_string: 'x = 3' }), 'Rodada 1 feita.',
    chamar('get_goal', {}), chamar('update_goal', { action: 'complete' }), 'Pronto: x vale 3.'];
  const ev = await rodar(s, 'deixe x valendo 3, nao pare ate\' conseguir');
  assert.equal(s.objetivo!.phase, 'complete');
  assert.equal(s.objetivo!.roundsStarted, 2);
  const users = conteudos(s, 'user');
  assert.ok(users.some((u) => u.startsWith('<goal_round>\nObjective: "x vale 3"\nRound: 1/20')));
  assert.ok(users.some((u) => u.startsWith('<goal_complete>')));
  assert.ok(ev.some((e) => e.t === 'resposta' && e.texto === 'Pronto: x vale 3.'));
  assert.equal(fs.readFileSync(path.join(raiz, 'a.js'), 'utf8'), 'const x = 3;\n');
});

test('objetivo: bloquear antes de 3 rodadas e\' recusado; create_goal so\' em pedido da pessoa', async () => {
  const s = novaSessao();
  s.objetivo = A.novoObjetivo('algo dificil');
  roteiro = ['Tentei.', chamar('update_goal', { action: 'blocked', blocked_reason: 'falta acesso' }), chamar('create_goal', { objective: 'outro' }),
    chamar('update_goal', { action: 'pause' }), 'Sigo.', 'Sigo.', 'Sigo.', 'Sigo.'];
  s.objetivo.maxGoalRounds = 2;
  await rodar(s, 'continue');
  const tool = conteudos(s, 'tool');
  assert.match(tool[0], /blocked requires at least 3 consecutive goal rounds; current round is 1/);
  assert.match(tool[1], /requires a direct human turn/);
  assert.match(tool[2], /requires a direct human turn/);
  assert.equal(s.objetivo.phase, 'blocked');
  assert.equal(s.objetivo.blockedReason?.code, 'round-limit');
});

test('lembrete pelo agente e entrega como turno sem aprovacao', async () => {
  const s = novaSessao('perguntar');
  roteiro = [chamar('schedule_create', { title: 'Rodar testes', prompt: 'rode os testes', after_seconds: 60 }), 'Agendei.'];
  const ev = await rodar(s, 'me lembre');
  assert.match(String(resultados(ev)[0].saida), /"kind":"after"/);
  assert.equal((ev.find((e) => e.t === 'lembretes') as { lembretes: unknown[] }).lembretes.length, 1);
  // sem ninguem para aprovar: o comando e' recusado com o texto do dsh
  roteiro = [chamar('pwsh', { description: 'Testes', command: 'npm test' }), 'Nao deu para rodar.'];
  const eventos: Record<string, unknown>[] = [];
  await A.turno(s, '[SCHEDULE REMINDER]\n...', { emitir: (e) => eventos.push(e), salvar: () => {}, sinal: new AbortController().signal,
    aprovar: async () => ({ ok: false, semCanal: true }) }, 'lembrete');
  assert.match(String(resultados(eventos)[0].saida), /requires approval, but no approval channel is available/);
  assert.equal((eventos.find((e) => e.t === 'voce') as { origem: string }).origem, 'lembrete');
});

test('present valida e entrega; lsp valida coordenadas', async () => {
  const s = novaSessao();
  fs.writeFileSync(path.join(raiz, 'relatorio.md'), '# r');
  roteiro = [chamar('present', { files: [{ path: 'relatorio.md', description: 'O relatorio' }] }), chamar('present', { files: [{ path: 'nao.md' }] }),
    chamar('lsp', { operation: 'hover', file_path: 'a.js', line: 0, character: 1 }), 'ok'];
  const ev = await rodar(s, 'entregue');
  const r = resultados(ev);
  assert.match(String(r[0].saida), /^Presented .*relatorio\.md$/);
  assert.deepEqual((ev.find((e) => e.t === 'entregas') as { arquivos: unknown[] }).arquivos, [{ caminho: 'relatorio.md', descricao: 'O relatorio' }]);
  assert.match(String(r[1].saida), /Cannot present nao\.md: file not found/);
  if (r[2]) assert.match(String(r[2].saida), /line must be a positive integer \(one-based\)|unknown tool/);
});

test('/skill no pedido injeta o <skill_content> e o catalogo vai no primeiro pedido', async () => {
  const s = novaSessao();
  fs.mkdirSync(path.join(raiz, '.nous', 'skills', 'revisar'), { recursive: true });
  fs.writeFileSync(path.join(raiz, '.nous', 'skills', 'revisar', 'SKILL.md'), '---\nname: revisar\ndescription: Revisa o codigo\n---\nLeia tudo e liste problemas.');
  roteiro = ['ok'];
  await rodar(s, '/revisar a.js');
  const users = conteudos(s, 'user');
  assert.ok(users.some((u) => u.startsWith('<skill_content name="revisar">') && u.includes('Leia tudo e liste problemas.')));
  assert.ok(users.some((u) => u.includes('<available_skills>\n- `revisar`: Revisa o codigo')));
});

test('ferramenta MCP aprovada vira mcp__srv__ferr e pede OK no modo perguntar', async () => {
  const s = novaSessao('perguntar');
  const srv = path.join(raiz, 'srv.mjs');
  fs.writeFileSync(srv, `import readline from 'node:readline';
const out = (m) => process.stdout.write(JSON.stringify(m) + '\\n');
readline.createInterface({ input: process.stdin }).on('line', (l) => { const m = JSON.parse(l);
  if (m.method === 'initialize') out({ jsonrpc: '2.0', id: m.id, result: { protocolVersion: '2025-06-18', capabilities: {}, serverInfo: { name: 'eco', version: '1' } } });
  else if (m.method === 'tools/list') out({ jsonrpc: '2.0', id: m.id, result: { tools: [{ name: 'eco', description: 'Eco', inputSchema: { type: 'object', properties: { t: { type: 'string' } } } }] } });
  else if (m.method === 'tools/call') out({ jsonrpc: '2.0', id: m.id, result: { content: [{ type: 'text', text: 'eco ' + m.params.arguments.t }] } }); });`);
  fs.writeFileSync(path.join(raiz, '.mcp.json'), JSON.stringify({ mcpServers: { eco: { command: 'node', args: [srv] } } }));
  roteiro = ['ok'];
  const ev1 = await rodar(s, 'oi');
  assert.ok(ev1.some((e) => e.t === 'mcp-pendente'));
  const M = await import('../mcp.ts');
  M.aprovar(raiz, 'eco', true);
  roteiro = [chamar('mcp__eco__eco', { t: 'ola' }), 'ok'];
  const ev = await rodar(s, 'use o eco');
  assert.ok(ev.some((e) => e.t === 'pede' && e.tipo === 'mcp'));
  assert.equal(conteudos(s, 'tool').at(-1), 'eco ola');
  assert.ok(pedidos.some((p) => JSON.stringify(p).includes('"mcp__eco__eco"')));
  M.fecharTodos();
});

test('compactar resume no formato do dsh e esquece o que foi lido', async () => {
  const s = novaSessao();
  roteiro = [chamar('read', { file_path: 'a.js' }), 'ok'];
  await rodar(s, 'leia');
  for (let i = 0; i < 6; i++) s.mensagens.push({ role: 'user', content: 'x'.repeat(100) }, { role: 'assistant', content: 'y' });
  roteiro = ['## Primary Request and Intent\n- ler a.js'];
  const e = await A.compactar(s, { emitir: () => {}, salvar: () => {}, sinal: new AbortController().signal, aprovar: async () => ({ ok: true }) }, true);
  assert.equal(e?.modo, 'resumo');
  const ultimo = pedidos.at(-1)!.messages.at(-1)!.content;
  assert.match(ultimo, /^You are now acting as a compaction engine/);
  const cp = s.mensagens.find((m) => m.content.includes('<compacted-summary>'))!;
  assert.match(cp.content, /^This is an automatically generated checkpoint[\s\S]*<compacted-summary>\n## Primary Request and Intent\n- ler a\.js\n<\/compacted-summary>$/);
  assert.deepEqual(s.lidos, {});
});
