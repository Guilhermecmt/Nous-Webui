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

const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' };

async function ligarMonitor(page, inicio) {
  const m = { mensageiros: 'desligado', celular: 'desligado', extra: {}, recebidos: [] };
  Object.assign(m, inicio);

  await page.route(/^http:\/\/127\.0\.0\.1:899\d\//, (rota) => {
    const pedido = rota.request();
    const url = new URL(pedido.url());
    if (pedido.method() === 'OPTIONS') return rota.fulfill({ status: 204, headers: CORS });
    if (pedido.method() === 'POST') m.recebidos.push(url.pathname);
    const agora = Date.now() / 1000;
    let corpo = {};
    if (url.pathname === '/stats') corpo = { online: true, gpu: { used: 1, total: 8 }, loaded: [] };
    else if (url.pathname === '/installed') corpo = { online: true, chat: ['modelo-de-teste'] };
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
