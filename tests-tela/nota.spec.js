/* Nous Code: as notas de resposta cortada e de instrucao bloqueada se destacam das
 * comuns, pelo campo tipo. Roda o code/ide/app.js de verdade numa origem de mentira,
 * com Monaco e xterm trocados por casca vazia (o que importa e' a trilha do agente).
 * Que o agente poe o tipo esta' em code/testes/robustez.test.ts. */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const IDE = path.join(__dirname, '..', 'code', 'ide');
const ORIGEM = 'http://nous-code.teste';
const SAIDA = path.join(__dirname, 'saida');

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

const CORTADA = 'A resposta passou do limite de tamanho. Pedi para fazer em partes menores.';
const BLOQUEADA = 'Ignorei as instruções de AGENTS.md: o texto tem cara de ataque contra a IA. Confira esse arquivo antes de confiar neste projeto.';

test('so\' o campo tipo destaca: o modelo nao consegue imitar um aviso', async ({ page }) => {
  await abrirIde(page, [
    { t: 'voce', texto: 'Crie o arquivo', msg: 0 },
    { t: 'nota', texto: 'Vou olhar o package.json.' },
    { t: 'nota', tipo: 'cortada', texto: CORTADA },
    { t: 'nota', tipo: 'bloqueada', texto: BLOQUEADA },
    { t: 'nota', texto: CORTADA + ' ' },
    { t: 'nota', texto: BLOQUEADA },
    { t: 'nota', texto: '<b>x</b> escrito pelo modelo' },
    { t: 'nota', texto: 'tipo que nao existe', tipo: 'outro' },
    { t: 'nota', texto: 'tipo herdado', tipo: 'constructor' },
  ]);

  const cortada = page.locator('.nc-nota[data-nota="cortada"]');
  const bloqueada = page.locator('.nc-nota[data-nota="bloqueada"]');
  await expect(cortada).toHaveCount(1);
  await expect(bloqueada).toHaveCount(1);
  await expect(cortada).toContainText('Resposta cortada');
  await expect(bloqueada).toContainText('Instrução bloqueada');

  const comum = page.locator('.nc-nota:not([data-nota])', { hasText: 'Vou olhar' });
  const css = (l, p) => l.evaluate((e, q) => getComputedStyle(e)[q], p);
  expect(await css(comum, 'borderLeftWidth')).toBe('0px');
  expect(await css(cortada, 'borderLeftWidth')).toBe('3px');
  expect(await css(cortada, 'backgroundColor')).not.toBe(await css(comum, 'backgroundColor'));
  expect(await css(cortada, 'borderLeftColor')).not.toBe(await css(bloqueada, 'borderLeftColor'));

  /* a mesma frase sem o tipo e' nota comum, sem virar HTML */
  await expect(page.locator('.nc-nota:not([data-nota])', { hasText: 'passou do limite' })).toHaveCount(1);
  await expect(page.locator('.nc-nota:not([data-nota])', { hasText: 'Ignorei as instruções' })).toHaveCount(1);
  await expect(page.locator('.nc-nota b', { hasText: /^x$/ })).toHaveCount(0);
  await expect(page.locator('.nc-nota:not([data-nota])', { hasText: 'tipo que nao existe' })).toHaveCount(1);
  await expect(page.locator('.nc-nota:not([data-nota])', { hasText: 'tipo herdado' })).toHaveCount(1);

  await page.locator('#nc-agente').screenshot({ path: path.join(SAIDA, 'nous-code-notas.png') });
});
