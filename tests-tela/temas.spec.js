/* Todo painel que acompanha o tema: confere a cor CALCULADA do fundo e o contraste
 * do texto nos dois temas, com um screenshot de cada. Os que viraram NousUI.dialogo
 * tambem conferem Esc e a volta do foco. */
const { test, expect } = require('@playwright/test');
const path = require('path');
const { TEMAS, entrar, medirContraste } = require('./ajuda');

const SAIDA = path.join(__dirname, 'saida', 'temas');
const MINIMO = 4.5;

const DIALOGOS = [
  { nome: 'diagnostico', botao: 'nous-diag-open', caixa: '#nous-dg', espera: '.nous-dg-it' },
  { nome: 'habilidades', botao: 'nous-skills-open', caixa: '#nous-sk', espera: '.nous-sk-item' },
  { nome: 'email', botao: 'nous-email-open', caixa: '#nous-em', espera: '.nous-em-row' },
  { nome: 'formularios', botao: 'nous-pdf-open', caixa: '#nous-pdf', espera: '.nous-pdf-h' },
  { nome: 'comparar', botao: 'nous-cmp-open', caixa: '#nous-cp', espera: '.nous-cp-chip' },
  { nome: 'pesquisas', botao: 'nous-reports-open', caixa: '#nous-rp', espera: '.nous-rp-item' },
];

const PAINEIS = [
  { nome: 'documentos', botao: 'nous-docs-open', caixa: '#nous-dc', espera: '#nous-dc-title' },
  { nome: 'modelos', botao: 'nous-store-open', caixa: '#nous-store', espera: '#nous-store-name' },
  { nome: 'galeria', botao: 'nous-gallery-open', caixa: '#nous-gal-box', espera: '#nous-gal-filter' },
  { nome: 'voz', botao: 'nous-voice-open', caixa: '#nous-voice-box', espera: '#nous-voice-close' },
  { nome: 'memoria', abre: () => window.NousUI.openMemory(), caixa: '#nous-mem-panel', espera: '#nous-mem-inp' },
  { nome: 'licoes', abre: () => window.NousPrimeiros.abrirLicoes({ sempre: true }), caixa: '#nous-pp-jan', espera: '.nous-pp-lic' },
];

async function conferir(page, p, tema) {
  const caixa = page.locator(p.caixa);
  await expect(caixa).toBeVisible();
  await expect(page.locator(p.caixa + ' ' + p.espera).first()).toBeAttached({ timeout: 10000 });
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(SAIDA, p.nome + '-' + tema.nome + '.png') });
  expect(await caixa.evaluate((e) => getComputedStyle(e).backgroundColor)).toBe(tema.fundo);
  const c = await page.evaluate(medirContraste, p.caixa);
  expect(c.length).toBeGreaterThan(0);
  expect(c.filter((x) => x.razao < MINIMO)).toEqual([]);
}

for (const tema of TEMAS) {
  for (const p of DIALOGOS) {
    test(p.nome + ' no tema ' + tema.nome + ': cor, Esc e foco', async ({ page }) => {
      await entrar(page, tema, {});
      await page.locator('#nous-pn [data-abre="' + p.botao + '"]').click();
      await conferir(page, p, tema);
      await expect(page.locator(p.caixa)).toHaveAttribute('role', 'dialog');

      /* a dica de primeiro uso do painel fica por cima: o Esc e' dela primeiro */
      if (await page.locator('#nous-tour-card').count()) {
        await page.keyboard.press('Escape');
        await expect(page.locator('#nous-tour-card')).toHaveCount(0);
        await expect(page.locator(p.caixa)).toBeVisible();
      }
      await page.keyboard.press('Escape');
      await expect(page.locator(p.caixa)).toBeHidden();
      expect(await page.evaluate(() => document.activeElement.getAttribute('data-abre'))).toBe(p.botao);
    });
  }

  for (const p of PAINEIS) {
    test(p.nome + ' no tema ' + tema.nome + ': cor', async ({ page }) => {
      await entrar(page, tema, {});
      if (p.botao) await page.locator('#nous-pn [data-abre="' + p.botao + '"]').click();
      else await page.evaluate(p.abre);
      await conferir(page, p, tema);
    });
  }

  test('dica do passeio no tema ' + tema.nome + ': cor', async ({ page }) => {
    await entrar(page, tema, {});
    await expect(page.locator('#chat-input')).toBeAttached();
    const rodou = await page.evaluate(() => window.NousTour.run('home'));
    expect(rodou).toBe(true);
    await conferir(page, { nome: 'passeio', caixa: '#nous-tour-card', espera: 'button' }, tema);
  });

  test('assistente de primeiro uso no tema ' + tema.nome + ': cor', async ({ page }) => {
    await entrar(page, tema, { instalados: [] }, undefined, true);
    await expect(page.locator('#nous-wiz-box')).toBeVisible({ timeout: 20000 });
    await conferir(page, { nome: 'assistente', caixa: '#nous-wiz-box', espera: 'button' }, tema);
  });
}

test('o editor de fotos segue escuro no tema claro, de proposito', async ({ page }) => {
  await entrar(page, TEMAS[0], {});
  await page.locator('#nous-pn [data-abre="nous-editor-open"]').click();
  const ov = page.locator('#nous-ed-ov');
  await expect(ov).toBeVisible();
  expect(await ov.evaluate((e) => getComputedStyle(e).backgroundColor)).toBe('rgba(8, 8, 10, 0.92)');
  expect(await ov.evaluate((e) => getComputedStyle(e).color)).toBe('rgb(238, 238, 238)');
});

test('a licao do que fica no computador fala do Telegram, opcional', async ({ page }) => {
  await entrar(page, TEMAS[0], {});
  await page.evaluate(() => window.NousPrimeiros.abrirLicoes({ sempre: true }));
  const lic = page.locator('#nous-pp-jan');
  for (let i = 0; i < 3; i++) await lic.getByRole('button', { name: 'Próxima' }).click();
  await expect(lic).toContainText('O que fica no seu computador');
  await expect(lic).toContainText('O Telegram é opcional');
  await expect(lic).toContainText('o texto da conversa passa pelo Telegram');
});

test('foto ampliada segue escura nos dois temas', async ({ page }) => {
  for (const tema of TEMAS) {
    await page.goto('about:blank');
    await page.unrouteAll();
    await entrar(page, tema, {});
    await page.locator('#nous-pn [data-abre="nous-gallery-open"]').click();
    await expect(page.locator('#nous-gal-box')).toBeVisible();
    const fundo = await page.evaluate(() => {
      const e = document.getElementById('nous-gal-lightbox');
      e.classList.remove('nous-hidden');
      return getComputedStyle(e).backgroundColor;
    });
    expect(fundo).toBe('rgba(0, 0, 0, 0.92)');
  }
});
