// O `nous`: escolhe entre a conversa interativa e o modo -p (um pedido so').
import fs from 'node:fs';
import path from 'node:path';
import type { Cliente, Evento } from './cliente.ts';
import { ErroApi, garantirServico, pastaCodigo, pastaDados } from './cliente.ts';
import { AJUDA, lerArgs, type Opcoes } from './args.ts';
import { IoImprimir, IoTerminal, type Io } from './io.ts';
import { Repl } from './repl.ts';
import { Renderizador, corLigada, criarEstilo } from './tela.ts';
import { executarTurno, type RespostaPedido } from './turno.ts';

export function versaoTexto(): string {
  let nous = '', codigo = '';
  try { nous = fs.readFileSync(path.join(pastaCodigo(), '..', 'VERSION'), 'utf8').trim(); } catch { /* instalacao sem VERSION */ }
  try { codigo = JSON.parse(fs.readFileSync(path.join(pastaCodigo(), 'package.json'), 'utf8')).version; } catch { /* sem package.json */ }
  return 'nous ' + (nous || '?') + (codigo ? ' (Nous Code ' + codigo + ')' : '');
}

/* O que o modo -p responde sozinho (ninguem para aprovar). Com --modo editar ou total, arquivos e comandos
 * comuns passam; o resto, e qualquer pedido sem essas opcoes, e' recusado. */
export function politicaImprimir(modo?: string): (e: Evento) => RespostaPedido {
  const livre = modo === 'editar' || modo === 'total';
  return (e) => {
    if (livre && (e.tipo === 'arquivo' || (e.tipo === 'comando' && !e.perigo))) return { ok: true };
    if (e.tipo === 'perguntas') return { ok: true, texto: JSON.stringify((e.perguntas || []).map((q: { id: string }) => ({ id: q.id, selected: [] }))) };
    return { ok: false };
  };
}

async function lerEntrada(): Promise<string> {
  if (process.stdin.isTTY) return '';
  const partes: Buffer[] = [];
  for await (const p of process.stdin) partes.push(p as Buffer);
  return Buffer.concat(partes).toString('utf8').trim();
}

/* Um pedido, a resposta final no stdout, a atividade no stderr. */
export async function imprimir(o: Opcoes, pedido: string, cliente: Cliente, pasta: string, io: Io = new IoImprimir()): Promise<number> {
  const est = criarEstilo(corLigada(process.stderr.isTTY));
  const repl = new Repl({ pasta, cliente, io, est, prefs: { modelo: o.modelo, raciocinio: o.esforco, modo: o.modo, alcance: o.alcance } });
  let id: string;
  try {
    if (o.continuar && await repl.abrirUltima()) id = repl.sessao!;
    else id = await repl.garantirSessao();
  } catch (e) {
    io.atividade(est.red('✗ ') + (e instanceof Error ? e.message : String(e)) + '\n');
    return 1;
  }
  const ren = new Renderizador({ saida: (s) => io.saida(s), atividade: (s) => io.atividade(s), est, tty: false, streaming: false, largura: () => io.largura() });
  const r = await executarTurno(cliente, id, pedido, io, ren, { automatico: politicaImprimir(o.modo) });
  if (r.resposta) io.saida(r.resposta.replace(/\s+$/, '') + '\n');
  if (r.erro && !r.resposta) return 1;
  return r.erro || r.interrompido ? 1 : 0;
}

export async function principal(argv: string[]): Promise<number> {
  const o = lerArgs(argv);
  if (o.erro) { process.stderr.write('nous: ' + o.erro + '\n'); return 2; }
  if (o.ajuda) { process.stdout.write(AJUDA + '\n'); return 0; }
  if (o.versao) { process.stdout.write(versaoTexto() + '\n'); return 0; }

  const pasta = path.resolve(o.pasta || process.cwd());
  if (!fs.existsSync(pasta) || !fs.statSync(pasta).isDirectory()) { process.stderr.write('nous: a pasta não existe: ' + pasta + '\n'); return 2; }

  // com texto vindo de um pipe, ou com -p, e' um pedido so'
  const entrada = await lerEntrada();
  const naoInterativo = o.imprimir || !process.stdin.isTTY;
  const pedido = [o.pedido, entrada].filter(Boolean).join('\n\n');
  if (naoInterativo && !pedido) { process.stderr.write('nous: nenhum pedido. Use nous -p "pedido" ou mande o texto pela entrada padrão.\n'); return 2; }

  let cliente: Cliente;
  try {
    cliente = await garantirServico({ aoIniciar: () => process.stderr.write('Ligando o Nous Code…\n') });
  } catch (e) {
    process.stderr.write('nous: ' + (e instanceof Error ? e.message : String(e)) + '\n');
    return 1;
  }

  if (naoInterativo) return imprimir(o, pedido, cliente, pasta);

  const io = new IoTerminal(path.join(pastaDados(), 'cli-historico'));
  const repl = new Repl({ pasta, cliente, io, continuar: o.continuar, pedidoInicial: pedido || undefined,
    prefs: { modelo: o.modelo, raciocinio: o.esforco, modo: o.modo, alcance: o.alcance } });
  try { return await repl.rodar(); }
  catch (e) {
    if (e instanceof ErroApi || e instanceof Error) process.stderr.write('nous: ' + e.message + '\n');
    return 1;
  } finally { io.compactarHistorico(); }
}
