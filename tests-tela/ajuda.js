/* O que os testes de tela dividem: entrar no Nous num tema e medir o contraste. */
const { expect } = require('@playwright/test');
const { ligarMonitor } = require('./monitor-falso');

const TEMAS = [
  { nome: 'claro', valor: 'light', fundo: 'rgb(255, 255, 255)' },
  { nome: 'escuro', valor: 'dark', fundo: 'rgb(20, 18, 16)' },
];

async function entrar(page, tema, monitor, tamanho, comAssistente) {
  const m = await ligarMonitor(page, monitor);
  if (tamanho) await page.setViewportSize(tamanho);
  await page.addInitScript(([token, valor, versao, pula]) => {
    localStorage.setItem('token', token);
    localStorage.setItem('theme', valor);
    localStorage.setItem('version', versao);
    if (pula) sessionStorage.setItem('nous-wizard-skip', '1');
  }, [process.env.NOUS_TELA_TOKEN, tema.valor, process.env.NOUS_TELA_VERSAO, !comAssistente]);
  await page.goto('/');
  /* em tela estreita o painel comeca fechado e so' a coruja aparece */
  await expect(page.locator(tamanho ? '#nous-pn-alca' : '#nous-pn')).toBeVisible({ timeout: 30000 });
  await expect(page.locator('html')).toHaveClass(tema.valor === 'dark' ? /(^|\s)dark(\s|$)/ : /^(?!.*\bdark\b)/);
  return m;
}

/* menor contraste entre o texto visivel e o fundo real atras dele: soma as camadas
 * translucidas ate' a caixa e conta a opacidade de quem esta' no caminho */
function medirContraste(sel) {
  const caixa = document.querySelector(sel);
  const rgba = (c) => { const n = c.match(/[\d.]+/g).map(Number); return { r: n[0], g: n[1], b: n[2], a: n.length > 3 ? n[3] : 1 }; };
  const sobre = (c, f) => ({ r: c.r * c.a + f.r * (1 - c.a), g: c.g * c.a + f.g * (1 - c.a), b: c.b * c.a + f.b * (1 - c.a), a: 1 });
  const lum = (c) => { const v = [c.r, c.g, c.b].map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  function camadas(el) {
    const pilha = [];
    let opac = 1;
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      pilha.push(rgba(cs.backgroundColor));
      opac *= Number(cs.opacity);
      if (e === caixa) break;
    }
    return { fundo: pilha.reverse().reduce((f, c) => sobre(c, f), { r: 255, g: 0, b: 255, a: 1 }), opac };
  }
  const achados = [];
  const andar = document.createTreeWalker(caixa, NodeFilter.SHOW_TEXT);
  while (andar.nextNode()) {
    const t = andar.currentNode.textContent.trim(), el = andar.currentNode.parentElement;
    if (!t || !el.getClientRects().length || el.closest('[disabled]') || /^(STYLE|SCRIPT|OPTION)$/.test(el.tagName)) continue;
    const { fundo, opac } = camadas(el);
    const cor = rgba(getComputedStyle(el).color);
    cor.a *= opac;
    const c = sobre(cor, fundo), a = lum(c), b = lum(fundo);
    achados.push({ texto: t.slice(0, 40), razao: Math.round(((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)) * 100) / 100 });
  }
  return achados.sort((x, y) => x.razao - y.razao);
}

module.exports = { TEMAS, entrar, medirContraste };
