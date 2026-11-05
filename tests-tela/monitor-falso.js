/* Monitor falso: responde dentro do navegador (page.route), entao nenhuma porta do
 * Nous e' aberta, e um Nous de verdade ligado nesta maquina nao recebe nada. Toda
 * chamada as portas 8990-8999 cai aqui. */

const QR = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="5" height="5"/></svg>').toString('base64');

const MENSAGEIROS = {
  desligado: {
    telegram: { conectado: false, estado: '', bot: '', pessoas: [] },
    whatsapp: { ligado: false, estado: '', tem_node: true, qr: '' },
  },
  conectado: {
    telegram: { conectado: true, estado: 'conectado', bot: 'nous_da_ana_bot', pessoas: [{ id: 1, nome: 'Ana', desde: 1760000000 }] },
    whatsapp: { ligado: true, estado: 'conectado', tem_node: true, qr: '' },
  },
};

const CELULAR = {
  desligado: { ligado: false, ip: '192.168.0.10', porta: 8991, aparelhos: [{ id: 'a', nome: 'Celular da Ana', ultimo_uso: 1760000000, ip: '192.168.0.20' }] },
  ligado: {
    ligado: true, ip: '192.168.0.10', porta: 8991, url: 'http://192.168.0.10:8991', outros_ips: [],
    aparelhos: [{ id: 'a', nome: 'Celular da Ana', ultimo_uso: 1760000000, ip: '192.168.0.20' }, { id: 'b', nome: 'Tablet', ultimo_uso: 0 }],
  },
};

/* dados dos paineis, para os testes medirem a tela cheia e nao a tela vazia */
const EMAIL = {
  '/status': { connected: true, accounts: [{ user: 'ana@exemplo.com', padrao: true }] },
  '/inbox': [
    { uid: '1', from: 'Banco <b@exemplo.com>', subject: 'Sua fatura chegou', summary: 'Vence dia 10.', category: 'Importante', unread: true },
    { uid: '2', from: 'Loja <l@exemplo.com>', subject: 'Promoção', category: 'Promoção' },
    { uid: '3', from: 'Spam <s@exemplo.com>', subject: 'Ganhe', category: 'Spam' },
  ],
  '/drafts': { drafts: [] },
};
const HABILIDADES = {
  '/skills': { skills: [{ id: 's', nome: 'Ata de reunião', quando_usar: 'ao resumir reunião', origem: 'conversa', criado: '2026-10-01' }] },
};
const MONITOR = {
  '/diag': { itens: [
    { nome: 'Motor de IA', ok: true, essencial: true, detalhe: 'No ar' },
    { nome: 'Busca na web', ok: false, essencial: true, detalhe: 'Fora do ar', dica: 'Abra o Nous pelo atalho.' },
    { nome: 'Voz', ok: false, essencial: false, detalhe: 'Não instalada' },
  ] },
  '/research': { reports: [{ id: 'r', question: 'Como funciona o Tesouro Selic?', created: 1760000000, n_sources: 4, domains: ['gov.br'] }] },
  '/compare/score': { placar: [] },
  '/docs': { docs: [] },
  '/gallery': { images: [] },
  '/catalog': { ollama_online: true, models: [{ tag: 'modelo-c:3b', name: 'Modelo de teste', desc: 'Rápido para o dia a dia.', fit: 'recomendado', installed: false, download_gb: 2 }] },
};

const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' };

async function ligarMonitor(page, inicio) {
  const m = { mensageiros: 'desligado', celular: 'desligado', extra: {}, recebidos: [], instalados: ['modelo-a', 'modelo-b'] };
  Object.assign(m, inicio);

  await page.route(/^http:\/\/127\.0\.0\.1:899\d\//, (rota) => {
    const pedido = rota.request();
    const url = new URL(pedido.url());
    if (pedido.method() === 'OPTIONS') return rota.fulfill({ status: 204, headers: CORS });
    if (pedido.method() === 'POST') m.recebidos.push(url.pathname);
    const agora = Date.now() / 1000;
    let corpo = {};
    if (url.port === '8995') corpo = EMAIL[url.pathname] || {};
    else if (url.port === '8997') corpo = HABILIDADES[url.pathname] || {};
    else if (MONITOR[url.pathname]) corpo = MONITOR[url.pathname];
    else if (url.pathname === '/stats') corpo = { online: true, gpu: { used: 1, total: 8 }, loaded: [] };
    else if (url.pathname === '/installed') corpo = { online: true, chat: m.instalados };
    else if (url.pathname.startsWith('/mensageiros/')) corpo = Object.assign({}, MENSAGEIROS[m.mensageiros], { agora }, m.extra);
    else if (url.pathname === '/celular/codigo') corpo = { codigo: '123456', expira: agora + 300, agora, qr: QR };
    else if (url.pathname.startsWith('/celular/')) corpo = Object.assign({}, CELULAR[m.celular], { agora });
    return rota.fulfill({ status: 200, headers: CORS, contentType: 'application/json', body: JSON.stringify(corpo) });
  });
  /* fontes e o que mais vier de fora: o teste nao depende de internet */
  await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (rota) => rota.abort());
  return m;
}

module.exports = { ligarMonitor };
