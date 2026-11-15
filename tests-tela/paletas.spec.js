/* Paletas de cores: a escolha guardada no Nous vale na tela, sem piscar, e o
 * usuario troca pelo painel "Seu Nous" (secao Aparencia) e pelas licoes. */
const { test, expect } = require('@playwright/test');
const path = require('path');
const { TEMAS, entrar } = require('./ajuda');

const SAIDA = path.join(__dirname, 'saida', 'paletas');
const CLARO = TEMAS[0], ESCURO = TEMAS[1];

function acc(page) {
  return page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--nous-acc').trim());
}
function atributo(page) {
  return page.evaluate(() => document.documentElement.getAttribute('data-nous-paleta'));
}
/* captura a tela inteira so' depois que a abertura do Open WebUI sumir */
async function capturar(page, nome) {
  await page.locator('#splash-screen').waitFor({ state: 'detached', timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(SAIDA, nome) });
}

test('aplica a paleta guardada no Nous', async ({ page }) => {
  await entrar(page, CLARO, { paleta: 'pitaya' });
  await expect(page.locator('html')).toHaveAttribute('data-nous-paleta', 'pitaya');
  expect(await acc(page)).toBe('#c2185b');
  /* o painel segue a paleta (fundo da Pitaya clara) */
  const fundo = await page.locator('#nous-pn').evaluate((e) => getComputedStyle(e).backgroundColor);
  expect(fundo).toBe('rgb(252, 249, 251)');
  await capturar(page, 'pitaya-claro.png');
});

test('escuro usa a versao escura da paleta e tinge os cinzas', async ({ page }) => {
  await entrar(page, ESCURO, { paleta: 'maracuja' });
  await expect(page.locator('html')).toHaveAttribute('data-nous-paleta', 'maracuja');
  expect(await acc(page)).toBe('#f5a623');
  const cinza = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--color-gray-900').trim());
  expect(cinza).toContain('315');  /* o matiz da paleta, mesmo com o Open WebUI escrevendo no style do <html> */
  await capturar(page, 'maracuja-escuro.png');
});

test('ouro fica sem atributo e com o dourado de sempre', async ({ page }) => {
  await entrar(page, ESCURO, { paleta: 'ouro' });
  expect(await atributo(page)).toBeNull();
  expect(await acc(page)).toBe('#c8962e');
  const cinza = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--color-gray-900').trim());
  /* o do proprio Open WebUI, intocado: sem croma (as paletas tingidas poem croma e matiz) */
  expect(cinza).toMatch(/^(#171717|oklch\(20% 0 0\))$/);
});

test('sem piscar: a ultima escolha vale antes do monitor responder', async ({ page }) => {
  /* o Nous diz pitaya, mas so' depois de 9 s: ate' la' vale a ultima escolha (ceu) */
  await page.addInitScript(() => localStorage.setItem('nous-paleta', 'ceu'));
  await entrar(page, CLARO, { paleta: 'pitaya', atrasoAparencia: 9000 });
  expect(await atributo(page)).toBe('ceu');
  await expect.poll(() => atributo(page), { timeout: 15000 }).toBe('pitaya');
});

test('monitor fora do ar: fica a ultima escolha e a tela abre', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('nous-paleta', 'mata'));
  await entrar(page, CLARO, { aparenciaFora: true });
  expect(await atributo(page)).toBe('mata');
  await capturar(page, 'mata-claro.png');
});

test('escolher no painel troca na hora e guarda no Nous', async ({ page }) => {
  const m = await entrar(page, CLARO, { paleta: 'ouro' });
  const sec = page.locator('#nous-pn-aparencia');
  await sec.scrollIntoViewIfNeeded();
  await expect(sec.locator('.nous-cor')).toHaveCount(7);
  await expect(sec.locator('.nous-cor[data-id="ouro"]')).toHaveAttribute('aria-pressed', 'true');
  await page.evaluate(() => { window.__semRecarregar = 1; });
  await sec.locator('.nous-cor[data-id="maracuja"]').click();
  await expect(page.locator('html')).toHaveAttribute('data-nous-paleta', 'maracuja');
  await expect(sec.locator('.nous-cor[data-id="maracuja"]')).toHaveAttribute('aria-pressed', 'true');
  await expect.poll(() => m.paleta).toBe('maracuja');
  expect(m.corpos.some((c) => c.caminho === '/aparencia' && c.corpo && c.corpo.paleta === 'maracuja')).toBe(true);
  expect(await page.evaluate(() => window.__semRecarregar)).toBe(1);
  expect(await acc(page)).toBe('#e8930c');
  await sec.screenshot({ path: path.join(SAIDA, 'seletor-claro.png') });
});

test('teclado: Enter escolhe a paleta', async ({ page }) => {
  const m = await entrar(page, ESCURO, { paleta: 'ouro' });
  const cartao = page.locator('#nous-pn-aparencia .nous-cor[data-id="ceu"]');
  await cartao.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('html')).toHaveAttribute('data-nous-paleta', 'ceu');
  await expect.poll(() => m.paleta).toBe('ceu');
});

test('claro, escuro e igual ao Windows no mesmo lugar', async ({ page }) => {
  await entrar(page, CLARO, { paleta: 'pitaya' });
  const modo = page.locator('#nous-pn-aparencia .nous-cores-modo');
  await expect(modo.locator('[data-tema="light"]')).toHaveAttribute('aria-pressed', 'true');
  await modo.locator('[data-tema="dark"]').click();
  await expect(page.locator('html')).toHaveClass(/(^|\s)dark(\s|$)/);
  await expect(modo.locator('[data-tema="dark"]')).toHaveAttribute('aria-pressed', 'true');
  expect(await acc(page)).toBe('#d81b73');
  await page.locator('#nous-pn-aparencia').screenshot({ path: path.join(SAIDA, 'seletor-pitaya-escuro.png') });
});

test('licao das cores nos Primeiros passos', async ({ page }) => {
  await entrar(page, CLARO, { paleta: 'ouro' });
  await page.evaluate(() => window.NousPrimeiros.abrirLicoes({ sempre: true }));
  const jan = page.locator('#nous-pp-jan');
  await expect(jan).toBeVisible();
  for (let i = 0; i < 10; i++) {
    if (await jan.locator('h3', { hasText: 'Escolha as cores' }).count()) break;
    await jan.locator('[data-x=prox]').click();
  }
  await expect(jan.locator('h3')).toHaveText('Escolha as cores');
  await expect(jan.locator('.nous-cor')).toHaveCount(7);
  await jan.locator('.nous-cor[data-id="melancia"]').click();
  await expect(page.locator('html')).toHaveAttribute('data-nous-paleta', 'melancia');
});
