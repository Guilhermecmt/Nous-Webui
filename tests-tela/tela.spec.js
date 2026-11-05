/* Painel "Seu Nous" e as janelas de Telegram/WhatsApp e Celular, em cima de um Open
 * WebUI de verdade com o branding aplicado. Confere a cor CALCULADA pelo navegador
 * (a classe certa nao adianta se a cor nao chega) e guarda um screenshot por tema. */
const { test, expect } = require('@playwright/test');
const path = require('path');
const { TEMAS, entrar, medirContraste } = require('./ajuda');

const SAIDA = path.join(__dirname, 'saida');

const JANELAS = [
  { nome: 'telegram-whatsapp', botao: 'nous-msg-open', caixa: '#nous-msg', fundo: '#nous-msg-ov', titulo: 'Telegram e WhatsApp', monitor: { mensageiros: 'conectado' } },
  { nome: 'celular', botao: 'nous-cel-open', caixa: '#nous-cel', fundo: '#nous-cel-ov', titulo: 'Usar no celular', monitor: { celular: 'ligado' } },
];

function botaoDoPainel(page, id) { return page.locator('#nous-pn [data-abre="' + id + '"]'); }

async function abrir(page, j) {
  await botaoDoPainel(page, j.botao).click();
  await expect(page.locator(j.caixa)).toBeVisible();
  await expect(page.locator(j.caixa + '-body')).not.toBeEmpty();
}

test('o painel "Seu Nous" aparece com as ferramentas', async ({ page }) => {
  await entrar(page, TEMAS[0], {});
  await expect(page.locator('#nous-pn-titulo')).toBeVisible();
  await expect(botaoDoPainel(page, 'nous-msg-open')).toBeVisible();
  await expect(botaoDoPainel(page, 'nous-cel-open')).toBeVisible();
  await page.screenshot({ path: path.join(SAIDA, 'painel-seu-nous.png') });
});

for (const tema of TEMAS) {
  for (const j of JANELAS) {
    test(j.nome + ' no tema ' + tema.nome + ': cor, Esc e foco', async ({ page }) => {
      await entrar(page, tema, j.monitor);
      await abrir(page, j);

      const caixa = page.locator(j.caixa);
      await expect(caixa).toHaveAttribute('role', 'dialog');
      await expect(caixa).toHaveAttribute('aria-modal', 'true');
      await expect(page.getByRole('dialog', { name: j.titulo })).toBeVisible();
      expect(await caixa.evaluate((e) => getComputedStyle(e).backgroundColor)).toBe(tema.fundo);

      const contraste = await page.evaluate(medirContraste, j.caixa);
      expect(contraste.length).toBeGreaterThan(3);
      expect(contraste.filter((x) => x.razao < 4.5)).toEqual([]);
      await page.screenshot({ path: path.join(SAIDA, j.nome + '-' + tema.nome + '.png') });

      await page.keyboard.press('Escape');
      await expect(caixa).toBeHidden();
      expect(await page.evaluate(() => document.activeElement.getAttribute('data-abre'))).toBe(j.botao);
    });
  }

  test('caixa de confirmacao no tema ' + tema.nome + ': cor e texto verdadeiro do WhatsApp', async ({ page }) => {
    const m = await entrar(page, tema, { mensageiros: 'conectado' });
    await abrir(page, JANELAS[0]);
    const desligar = page.getByRole('button', { name: 'Desligar o WhatsApp' });
    await desligar.click();

    const cf = page.locator('#nous-cf');
    await expect(cf).toBeVisible();
    await expect(cf).toContainText('A sessão sai deste computador');
    await expect(cf).toContainText('Configurações › Aparelhos conectados');
    await expect(cf).not.toContainText('sai dos aparelhos');
    expect(await cf.evaluate((e) => getComputedStyle(e).backgroundColor)).toBe(tema.fundo);
    expect((await page.evaluate(medirContraste, '#nous-cf')).filter((x) => x.razao < 4.5)).toEqual([]);
    await page.screenshot({ path: path.join(SAIDA, 'confirmar-whatsapp-' + tema.nome + '.png') });

    /* Esc fecha so' a confirmacao: a janela fica e o foco volta para o botao */
    await page.keyboard.press('Escape');
    await expect(cf).toBeHidden();
    await expect(page.locator('#nous-msg')).toBeVisible();
    await expect(desligar).toBeFocused();
    expect(m.recebidos).not.toContain('/mensageiros/whatsapp/desligar');

    await desligar.click();
    await page.locator('#nous-cf button.ok').click();
    await expect.poll(() => m.recebidos).toContain('/mensageiros/whatsapp/desligar');
  });
}

test('o tema trocado com a janela aberta muda a janela junto', async ({ page }) => {
  await entrar(page, TEMAS[0], {});
  await abrir(page, JANELAS[0]);
  await page.evaluate(() => document.documentElement.classList.add('dark'));
  expect(await page.locator('#nous-msg').evaluate((e) => getComputedStyle(e).backgroundColor)).toBe(TEMAS[1].fundo);
});

for (const j of JANELAS) {
  test(j.nome + ': clique fora fecha e o foco nao sai da janela', async ({ page }) => {
    await entrar(page, TEMAS[0], j.monitor);
    await abrir(page, j);
    const caixa = page.locator(j.caixa);
    await expect(page.locator(j.caixa + '-close')).toBeFocused();

    for (const volta of [false, true]) {
      for (let i = 0; i < 25; i++) {
        await page.keyboard.press(volta ? 'Shift+Tab' : 'Tab');
        expect(await caixa.evaluate((c) => c.contains(document.activeElement) && document.activeElement !== document.body)).toBe(true);
      }
    }

    await page.mouse.click(8, 8);
    await expect(caixa).toBeHidden();
    expect(await page.evaluate(() => document.activeElement.getAttribute('data-abre'))).toBe(j.botao);
  });
}

test('arrastar de dentro para fora da caixa nao fecha', async ({ page }) => {
  await entrar(page, TEMAS[0], {});
  await abrir(page, JANELAS[0]);
  const c = await page.locator('#nous-msg').boundingBox();
  await page.mouse.move(c.x + 40, c.y + 80);
  await page.mouse.down();
  await page.mouse.move(8, 8);
  await page.mouse.up();
  await expect(page.locator('#nous-msg')).toBeVisible();
});

test('o token digitado sobrevive ao vaivem do monitor e a uma repintura de verdade', async ({ page }) => {
  const m = await entrar(page, TEMAS[0], {});
  await abrir(page, JANELAS[0]);
  const token = page.locator('#nous-msg-token');
  await token.click();
  await page.keyboard.type('123:abc');

  /* duas voltas do monitor (3 s cada), sem nada mudar */
  await page.waitForTimeout(6500);
  await expect(token).toHaveValue('123:abc');
  await expect(token).toBeFocused();
  /* o passeio de primeiro uso espera: antes ele abria por cima e levava o foco */
  await expect(page.locator('#nous-tour-card')).toHaveCount(0);

  /* o estado muda: o corpo e' refeito, e o campo e o foco continuam */
  m.extra = { whatsapp: { ligado: true, estado: 'reconectando', tem_node: true, qr: '' } };
  await expect(page.locator('#nous-msg-body')).toContainText('Conectando...', { timeout: 8000 });
  await expect(token).toHaveValue('123:abc');
  await expect(token).toBeFocused();

  await page.keyboard.press('Escape');
  await expect(page.locator('#nous-msg')).toBeHidden();
});

test('a caixa do chat nao rouba o foco da janela', async ({ page }) => {
  await entrar(page, TEMAS[0], {});
  await abrir(page, JANELAS[0]);
  const token = page.locator('#nous-msg-token');
  await token.click();
  await expect(page.locator('#chat-input')).toBeAttached();
  await page.evaluate(() => document.getElementById('chat-input').focus());
  await expect(token).toBeFocused();
});

test('com outra armadilha de foco na tela a pagina nao trava', async ({ page }) => {
  await entrar(page, TEMAS[0], {});
  await abrir(page, JANELAS[0]);
  /* imita o focus-trap do modal do Open WebUI: puxa de volta tudo o que sair dele */
  const voltas = await page.evaluate(async () => {
    const b = document.createElement('button');
    document.body.appendChild(b);
    let n = 0;
    document.addEventListener('focusin', (e) => { if (e.target !== b && n < 500) { n++; b.focus(); } }, true);
    b.focus();
    await new Promise((r) => setTimeout(r, 300));
    return n;
  });
  expect(voltas).toBeLessThan(30);
});

test('Esc funciona quando o elemento com foco some na repintura', async ({ page }) => {
  const m = await entrar(page, TEMAS[0], { mensageiros: 'conectado' });
  await abrir(page, JANELAS[0]);
  await page.getByRole('button', { name: 'Desligar o WhatsApp' }).focus();
  m.mensageiros = 'desligado';
  await expect(page.getByRole('button', { name: 'Desligar o WhatsApp' })).toHaveCount(0, { timeout: 8000 });
  await page.keyboard.press('Escape');
  await expect(page.locator('#nous-msg')).toBeHidden();
});

test('tela estreita: a gaveta fecha ao abrir e o foco volta para a coruja', async ({ page }) => {
  await entrar(page, TEMAS[0], {}, { width: 1000, height: 760 });
  await page.locator('#nous-pn-alca').click();
  await abrir(page, JANELAS[0]);
  await expect(page.locator('#nous-pn')).toBeHidden();
  await page.keyboard.press('Escape');
  await expect(page.locator('#nous-msg')).toBeHidden();
  await expect(page.locator('#nous-pn-alca')).toBeFocused();
});

test('sem monitor a janela avisa em vez de ficar em branco', async ({ page }) => {
  await entrar(page, TEMAS[0], {});
  await page.route(/^http:\/\/127\.0\.0\.1:8990\/mensageiros\//, (r) => r.abort());
  await botaoDoPainel(page, 'nous-msg-open').click();
  await expect(page.locator('#nous-msg-body')).toContainText('Não consegui falar com o Nous');
});
