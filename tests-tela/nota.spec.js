/* Nous Code: as notas de resposta cortada e de instrucao bloqueada se destacam das
 * comuns. Roda o code/ide/app.js de verdade numa origem de mentira, com Monaco e
 * xterm trocados por casca vazia (o que importa aqui e' a trilha do agente). As
 * frases vem do code/agente.ts: se alguem mudar o texto la', este teste avisa. */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const IDE = path.join(__dirname, '..', 'code', 'ide');
const ORIGEM = 'http://nous-code.teste';
const SAIDA = path.join(__dirname, 'saida');

function frasesDoAgente() {
  const fonte = fs.readFileSync(path.join(__dirname, '..', 'code', 'agente.ts'), 'utf8');
  const cortada = /texto: '(A resposta passou do limite[^']*)'/.exec(fonte);
  const bloqueada = /texto: `(Ignorei as instruções de [^`]*)`/.exec(fonte);
  expect(cortada, 'a frase da resposta cortada sumiu de code/agente.ts').not.toBeNull();
  expect(bloqueada, 'a frase da instrucao bloqueada sumiu de code/agente.ts').not.toBeNull();
  return { cortada: cortada[1], bloqueada: bloqueada[1].replace('${b[1]}', 'AGENTS.md') };
}

const CASCA = `
  const nada = () => new Proxy(function () {}, { get: (a, k) => (k === Symbol.toPrimitive ? () => 0 : k === 'then' ? undefined : nada()), apply: () => nada(), construct: () => nada() });
  window.monaco = nada();
  window.require = function () {};
  window.Terminal = window.Terminal || function () { return nada(); };
  window.FitAddon = window.FitAddon || { FitAddon: function () { return nada(); } };
`;

async function abrirIde(page, eventos) {
  const sessao = { id: 's1', titulo: 'Teste', pasta: 'C:/projeto', eventos, mudancas: [], tarefas: [], rodando: false };
  await page.route(ORIGEM + '/**', (rota) => {
    const u = new URL(rota.request().url());
    const json = (d) => rota.fulfill({ contentType: 'application/json', body: JSON.stringify(d) });
    if (u.pathname === '/') return rota.fulfill({ contentType: 'text/html', body: fs.readFileSync(path.join(IDE, 'index.html'), 'utf8') });
    if (u.pathname === '/ide/app.js') return rota.fulfill({ contentType: 'text/javascript', body: fs.readFileSync(path.join(IDE, 'app.js'), 'utf8') });
    if (u.pathname === '/ide/app.css') return rota.fulfill({ contentType: 'text/css', body: fs.readFileSync(path.join(IDE, 'app.css'), 'utf8') });
    if (u.pathname === '/vendor/monaco/vs/loader.js') return rota.fulfill({ contentType: 'text/javascript', body: CASCA });
    if (u.pathname.startsWith('/vendor/') || u.pathname.startsWith('/marca/')) return rota.fulfill({ status: 200, body: '' });
    if (u.pathname === '/sessoes') return json([{ id: 's1', titulo: 'Teste', pasta: sessao.pasta }]);
    if (u.pathname === '/sessao') return json(sessao);
    return json([]);
  });
  await page.route(/^https:/, (rota) => rota.abort());
  await page.goto(ORIGEM + '/?pasta=C%3A%2Fprojeto');
  await expect(page.locator('#nc-trilha')).toBeVisible();
}

test('cortada e bloqueada se destacam; texto do modelo continua nota comum', async ({ page }) => {
  const f = frasesDoAgente();
  await abrirIde(page, [
    { t: 'voce', texto: 'Crie o arquivo', msg: 0 },
    { t: 'nota', texto: 'Vou olhar o package.json.' },
    { t: 'nota', texto: f.cortada },
    { t: 'nota', texto: f.bloqueada },
    { t: 'nota', texto: 'A resposta passou do limite de tamanho, mas sigo mesmo assim.' },
    { t: 'nota', texto: 'Ignorei as instruções de <b>x</b> porque quis.' },
    { t: 'nota', texto: 'sem frase conhecida', tipo: 'cortada' },
    { t: 'nota', texto: 'tipo que nao existe', tipo: 'outro' },
  ]);

  const cortada = page.locator('.nc-nota[data-nota="cortada"]');
  const bloqueada = page.locator('.nc-nota[data-nota="bloqueada"]');
  await expect(cortada).toHaveCount(2);                 /* a frase do agente e a do campo tipo */
  await expect(bloqueada).toHaveCount(1);
  await expect(cortada.first()).toContainText('Resposta cortada');
  await expect(bloqueada).toContainText('Instrução bloqueada');
  await expect(bloqueada).toContainText('AGENTS.md');

  const comum = page.locator('.nc-nota:not([data-nota])', { hasText: 'Vou olhar' });
  const cor = (l, p) => l.evaluate((e, q) => getComputedStyle(e)[q], p);
  expect(await cor(comum, 'borderLeftWidth')).toBe('0px');
  expect(await cor(cortada.first(), 'borderLeftWidth')).toBe('3px');
  expect(await cor(cortada.first(), 'backgroundColor')).not.toBe(await cor(comum, 'backgroundColor'));
  expect(await cor(cortada.first(), 'borderLeftColor')).not.toBe(await cor(bloqueada, 'borderLeftColor'));

  /* parecido nao e' igual: quem so' cita o assunto segue comum, e sem virar HTML */
  await expect(page.locator('.nc-nota:not([data-nota])', { hasText: 'mas sigo mesmo assim' })).toHaveCount(1);
  await expect(page.locator('.nc-nota:not([data-nota])', { hasText: 'porque quis' })).toHaveCount(1);
  await expect(page.locator('.nc-nota b', { hasText: /^x$/ })).toHaveCount(0);
  await expect(page.locator('.nc-nota:not([data-nota])', { hasText: 'tipo que nao existe' })).toHaveCount(1);

  await page.locator('#nc-agente').screenshot({ path: path.join(SAIDA, 'nous-code-notas.png') });
});
