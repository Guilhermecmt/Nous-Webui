/* globalSetup: aplica o branding e sobe um Open WebUI de verdade na porta 8082, com
 * DATA_DIR temporario e sem Ollama. Devolve a funcao que encerra tudo.
 * O venv vem de OWUI_VENV (precisa ter o open-webui instalado). */
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');

const PORTA = 8082;
const BASE = 'http://127.0.0.1:' + PORTA;
const SAIDA = path.join(__dirname, 'saida');

function portaOcupada(porta) {
  return new Promise((ok) => {
    const s = net.connect(porta, '127.0.0.1');
    s.once('connect', () => { s.destroy(); ok(true); });
    s.once('error', () => ok(false));
  });
}

async function esperarNoAr(filho, limiteMs) {
  const fim = Date.now() + limiteMs;
  while (Date.now() < fim) {
    if (filho.exitCode !== null) throw new Error('O Open WebUI fechou sozinho. Veja ' + path.join(SAIDA, 'owui.log'));
    try { if ((await fetch(BASE + '/health')).ok) return; } catch (e) { /* ainda subindo */ }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error('O Open WebUI nao subiu em ' + limiteMs / 1000 + ' s. Veja ' + path.join(SAIDA, 'owui.log'));
}

module.exports = async function () {
  const venv = process.env.OWUI_VENV;
  if (!venv) throw new Error('Defina OWUI_VENV com a pasta do venv que tem o open-webui.');
  const python = path.join(venv, 'Scripts', 'python.exe');
  const owui = path.join(venv, 'Scripts', 'open-webui.exe');
  if (!fs.existsSync(owui)) throw new Error('Nao achei ' + owui);
  if (await portaOcupada(PORTA)) throw new Error('A porta ' + PORTA + ' ja esta em uso: nao vou mexer em quem esta nela.');

  fs.mkdirSync(SAIDA, { recursive: true });
  const dados = fs.mkdtempSync(path.join(os.tmpdir(), 'nous-tela-'));

  const ap = spawnSync(python, [path.join(__dirname, 'aplicar_branding.py'), dados], { encoding: 'utf8' });
  if (ap.status !== 0) throw new Error('apply_branding falhou:\n' + ap.stdout + ap.stderr);

  const log = fs.openSync(path.join(SAIDA, 'owui.log'), 'w');
  const filho = spawn(owui, ['serve', '--port', String(PORTA), '--host', '127.0.0.1'], {
    stdio: ['ignore', log, log],
    env: Object.assign({}, process.env, {
      DATA_DIR: dados,
      WEBUI_SECRET_KEY: 'so-para-o-teste-de-tela',
      ENABLE_SIGNUP: 'True',
      ENABLE_OLLAMA_API: 'False',
      ENABLE_OPENAI_API: 'False',
      OFFLINE_MODE: 'True',
      HF_HOME: path.join(dados, 'hf'),
      PYTHONIOENCODING: 'utf-8',
    }),
  });

  function encerrar() {
    if (filho.exitCode === null) spawnSync('taskkill', ['/PID', String(filho.pid), '/T', '/F']);
    try { fs.rmSync(dados, { recursive: true, force: true, maxRetries: 5, retryDelay: 500 }); } catch (e) { /* o Windows ainda segura algum arquivo */ }
    fs.closeSync(log);
  }

  try {
    await esperarNoAr(filho, 240000);
    const r = await fetch(BASE + '/api/v1/auths/signup', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Ana Teste', email: 'teste@exemplo.com', password: 'Teste-de-tela-1' }),
    });
    const conta = await r.json();
    if (!conta.token) throw new Error('Cadastro falhou: ' + JSON.stringify(conta));
    process.env.NOUS_TELA_TOKEN = conta.token;
    const cfg = await (await fetch(BASE + '/api/config')).json();
    process.env.NOUS_TELA_VERSAO = cfg.version || '';
    /* conta nova ganha o "O que ha' de novo" do Open WebUI, que cobriria os screenshots */
    await fetch(BASE + '/api/v1/users/user/settings/update', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + conta.token },
      body: JSON.stringify({ ui: { version: cfg.version } }),
    });
  } catch (e) {
    encerrar();
    throw e;
  }
  return encerrar;
};
