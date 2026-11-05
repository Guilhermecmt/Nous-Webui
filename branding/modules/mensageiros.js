/* =====================================================================
   Nous - Telegram e WhatsApp (v2.12). Fala com o Nous de qualquer lugar: a
   mensagem chega pelo celular, o modelo responde no computador de casa e a
   resposta volta pelo mesmo app. Desligado por padrao: o texto da conversa passa
   pelos servidores do Telegram ou do WhatsApp, e a tela diz isso antes de ligar.
   Fala com o monitor (rotas /mensageiros/*), que so' atende o computador.
   ===================================================================== */
(function () {
	'use strict';

	if (window.NousUrl && window.NousUrl.noCelular) return;   /* pelo celular este botao nem aparece */

	var MON = window.NousUrl(8990);
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var est = null, cod = null, uid = null, relogio = null, atualiza = null, ocupado = false, aviso = null, visto = null;
	var mostrarWa = false;
	var dlg = UI.dialogo({ id: 'nous-msg', titulo: 'Telegram e WhatsApp', largura: 500, aoFechar: parar });

	var ESTADO_TG = { conectado: ['on', 'Conectado: o bot está ouvindo.'], conflito: ['off', 'Outro programa está usando este bot. Aguardando...'],
		token_invalido: ['erro', 'O Telegram recusou o token. Conecte de novo.'], sem_internet: ['off', 'Sem internet no computador.'] };
	var ESTADO_WA = { conectado: ['on', 'Conectado ao seu WhatsApp.'], reconectando: ['off', 'Conectando...'], instalando: ['off', 'Preparando o WhatsApp (só na primeira vez, pode levar um minuto)...'],
		qr: ['off', 'Leia o QR com o WhatsApp do celular.'], pareando: ['off', 'Quase lá...'], deslogado: ['erro', 'O WhatsApp desconectou este computador. Desligue e ligue de novo para parear.'],
		qr_expirou: ['erro', 'O QR venceu antes de ser lido. Desligue e ligue de novo.'], sem_node: ['erro', 'Falta o Node.js. Instale o Nous Code.'],
		sem_npm: ['erro', 'O Node.js do computador veio sem o npm.'], falha_instalar: ['erro', 'Não consegui baixar a ponte do WhatsApp. Veja a internet e tente de novo.'] };

	function injectStyle() {
		if (document.getElementById('nous-msg-style')) return;
		var g = 'rgba(200,150,46,';
		var st = document.createElement('style');
		st.id = 'nous-msg-style';
		st.textContent =
			'.nous-msg-ol{margin:0 0 10px 18px;padding:0}.nous-msg-ol li{margin:0 0 4px}' +
			'.nous-msg-chk{display:flex;gap:8px;align-items:flex-start;margin:8px 0}.nous-msg-chk input{margin-top:3px}' +
			'#nous-msg-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);border-radius:8px;cursor:pointer;' +
			'background:transparent;color:#e7c069;font-weight:600;font-size:12px}#nous-msg-open:hover{background:' + g + '.12)}';
		document.head.appendChild(st);
	}

	/* ------------------------------------------------------------ rede */
	function chamar(caminho, corpo) {
		var op = corpo === undefined ? { cache: 'no-store' }
			: { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo || {}) };
		return fetch(MON + caminho, op).then(function (r) {
			return r.json().then(function (j) { j._status = r.status; return j; });
		});
	}

	function carregar() {
		return chamar('/mensageiros/estado').then(function (e) {
			est = e;
			/* so' repinta se algo mudou: refazer a tela a cada 3 s apagava o token
			 * que a pessoa estava colando e desmarcava o "Entendi" */
			var marca = JSON.stringify(Object.assign({}, e, { agora: 0 }));
			if (marca !== visto) { visto = marca; pintar(); }
		}).catch(function () { est = null; visto = null; pintar(); });
	}

	function acao(caminho, corpo, aoFim) {
		if (ocupado) return;
		ocupado = true; aviso = null; pintar();
		chamar(caminho, corpo || {}).then(function (r) {
			ocupado = false;
			if (r._status >= 400) { aviso = { erro: true, texto: r.erro || 'Não deu certo.' }; }
			else if (aoFim) aoFim(r);
			if (r.telegram) est = r;
			pintar();
		}).catch(function () { ocupado = false; aviso = { erro: true, texto: 'O Nous não respondeu. Ele está aberto?' }; pintar(); });
	}

	/* ------------------------------------------------------------ pintura */
	function el(tag, cls, texto) {
		var e = document.createElement(tag);
		if (cls) e.className = cls;
		if (texto !== undefined) e.textContent = texto;
		return e;
	}
	function botao(texto, cls, fn, desl) {
		var b = el('button', 'nous-dlg-btn' + (cls ? ' ' + cls : ''), texto);
		b.type = 'button'; b.disabled = !!desl || ocupado;
		b.addEventListener('click', fn);
		return b;
	}
	function ponto(estado, mapa) {
		var e = mapa[estado] || ['off', estado ? 'Estado: ' + estado : 'Iniciando...'];
		var s = el('span');
		s.appendChild(el('i', 'nous-dlg-pt ' + e[0]));
		s.appendChild(document.createTextNode(e[1]));
		return s;
	}
	function restante(expira) {
		var s = Math.max(0, Math.round(expira - (est ? est.agora : 0) - (Date.now() - pintouEm) / 1000));
		return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
	}
	var pintouEm = 0;

	function pintarTempo() {
		var t = document.getElementById('nous-msg-tempo');
		if (t && cod) {
			var s = cod.expira - cod.agora - (Date.now() - cod.em) / 1000;
			if (s <= 0) { cod = null; pintar(); return; }
			t.textContent = 'vale por ' + Math.floor(s / 60) + ':' + ('0' + Math.floor(s % 60)).slice(-2);
		}
	}

	function secaoTelegram(body) {
		var tg = est.telegram;
		body.appendChild(el('div', 'nous-dlg-h', 'Telegram'));
		if (!tg.conectado) {
			var p = el('p');
			p.innerHTML = 'Crie um bot só seu, de graça, e fale com o Nous por ele:';
			body.appendChild(p);
			var ol = el('ol', 'nous-msg-ol');
			['No Telegram do celular, abra o <b>@BotFather</b> e mande <b>/newbot</b>.',
				'Dê um nome e um usuário terminado em <b>bot</b> (ex.: <i>nous_da_ana_bot</i>).',
				'Ele responde com um <b>token</b> (uma linha com números, dois-pontos e letras). Cole abaixo.'].forEach(function (t) {
				var li = el('li'); li.innerHTML = t; ol.appendChild(li);
			});
			body.appendChild(ol);
			var inp = el('input', 'nous-dlg-in');
			inp.type = 'password'; inp.placeholder = '123456789:ABCdef...'; inp.id = 'nous-msg-token'; inp.autocomplete = 'off';
			body.appendChild(inp);
			body.appendChild(botao('Conectar o bot', '', function () {
				acao('/mensageiros/telegram/conectar', { token: inp.value.trim(), user_id: uid }, function () { cod = null; });
			}, !uid));
			return;
		}
		var p2 = el('p');
		p2.appendChild(ponto(tg.estado, ESTADO_TG));
		p2.appendChild(el('span', 'nous-dlg-mut', ' @' + tg.bot));
		body.appendChild(p2);
		if (cod) {
			var qr = el('div', 'nous-dlg-qr');
			if (cod.qr) { var img = el('img'); img.src = 'data:image/svg+xml;base64,' + cod.qr; img.alt = 'QR para abrir o bot'; qr.appendChild(img); }
			var lado = el('div');
			lado.innerHTML = '<p>Leia o QR com a câmera do celular, ou abra este link nele:</p><p><a href="' + esc(cod.link) + '" target="_blank" rel="noopener">' + esc(cod.link) + '</a></p>' +
				'<p class="nous-dlg-mut" id="nous-msg-tempo"></p><p class="nous-dlg-mut">Depois toque em <b>Começar</b> no Telegram. O código vale uma vez só.</p>';
			qr.appendChild(lado);
			body.appendChild(qr);
		} else {
			body.appendChild(botao(tg.pessoas.length ? 'Conectar outro celular' : 'Conectar o meu celular', '', function () {
				acao('/mensageiros/telegram/codigo', { user_id: uid }, function (r) { cod = r; cod.em = Date.now(); });
			}, !uid));
		}
		if (tg.pessoas.length) {
			body.appendChild(el('div', 'nous-dlg-h', 'Quem pode falar com o Nous'));
			tg.pessoas.forEach(function (d) {
				var r = el('div', 'nous-dlg-ap');
				var i = el('div'); i.appendChild(el('b', '', d.nome || 'Sem nome'));
				i.appendChild(el('span', 'nous-dlg-mut', 'desde ' + new Date(d.desde * 1000).toLocaleDateString('pt-BR')));
				r.appendChild(i);
				var b = el('button', '', 'Remover'); b.type = 'button';
				b.addEventListener('click', function () { acao('/mensageiros/telegram/remover', { id: d.id }, function () { carregar(); }); });
				r.appendChild(b);
				body.appendChild(r);
			});
		} else {
			body.appendChild(el('p', 'nous-dlg-mut', 'Ninguém conectado ainda. Quem escrever para o bot sem parear não recebe resposta nenhuma.'));
		}
		body.appendChild(botao('Desconectar o bot', 'perigo', function () {
			UI.confirmar('Quem estava conectado deixa de falar com o Nous.', { titulo: 'Desconectar o bot?', ok: 'Desconectar', perigo: true }).then(function (sim) {
				if (sim) acao('/mensageiros/telegram/desconectar', {}, function () { cod = null; });
			});
		}));
	}

	function secaoWhatsApp(body) {
		var wa = est.whatsapp;
		body.appendChild(el('div', 'nous-dlg-h', 'WhatsApp (experimental)'));
		if (!wa.ligado) {
			if (!mostrarWa) {
				body.appendChild(el('p', 'nous-dlg-mut', 'Fale com o Nous mandando mensagem para o seu próprio número. Funciona, mas o WhatsApp não gosta.'));
				body.appendChild(botao('Quero saber mais', 'sec', function () { mostrarWa = true; pintar(); }));
				return;
			}
			var av = el('div', 'nous-dlg-aviso');
			av.innerHTML = '<b>Leia antes de ligar.</b><br>' +
				'• O WhatsApp não tem um jeito oficial de fazer isto. O Nous usa um programa de código aberto que entra como um <b>aparelho conectado</b> da sua conta, e o WhatsApp pode <b>suspender o número</b> por isso. Use um chip que você pode perder.<br>' +
				'• As suas mensagens para o Nous passam pelo WhatsApp, como qualquer conversa. O modelo continua no seu computador.<br>' +
				'• O Nous só lê o que <b>você</b> escreve para <b>você mesmo</b> (a conversa "Você" no WhatsApp). Mensagens de outras pessoas ele ignora.<br>' +
				'• Precisa do Node.js, que vem com o Nous Code.' + (wa.tem_node ? '' : ' <b>Ainda não está instalado.</b>');
			body.appendChild(av);
			var chk = el('label', 'nous-msg-chk');
			var cb = el('input'); cb.type = 'checkbox'; cb.id = 'nous-msg-aceito';
			chk.appendChild(cb); chk.appendChild(document.createTextNode('Entendi que o número pode ser suspenso e que as mensagens passam pelo WhatsApp.'));
			body.appendChild(chk);
			body.appendChild(botao('Ligar o WhatsApp', '', function () {
				acao('/mensageiros/whatsapp/ligar', { user_id: uid, aceito: cb.checked === true });
			}, !uid || !wa.tem_node));
			return;
		}
		var p = el('p');
		p.appendChild(ponto(wa.estado, ESTADO_WA));
		body.appendChild(p);
		if (wa.qr && wa.estado === 'qr') {
			var qr = el('div', 'nous-dlg-qr');
			var img = el('img'); img.src = 'data:image/svg+xml;base64,' + wa.qr; img.alt = 'QR do WhatsApp'; qr.appendChild(img);
			var lado = el('div');
			lado.innerHTML = '<p>No WhatsApp do celular: <b>Configurações › Aparelhos conectados › Conectar aparelho</b> e leia este QR.</p><p class="nous-dlg-mut">O QR muda a cada ~20 segundos; esta tela acompanha.</p>';
			qr.appendChild(lado);
			body.appendChild(qr);
		}
		if (wa.estado === 'conectado') body.appendChild(el('p', 'nous-dlg-mut', 'Abra a conversa com você mesmo no WhatsApp ("Você") e escreva. A resposta chega lá, com o prefixo 🦉 Nous.'));
		body.appendChild(botao('Desligar o WhatsApp', 'perigo', function () {
			/* o monitor so' apaga a sessao deste computador: nao ha' como sair da lista
			 * de aparelhos daqui, e a pessoa precisa saber disso */
			UI.confirmar('A sessão sai deste computador, mas ele continua na lista de aparelhos da sua conta. Para tirar de lá, ' +
				'abra o WhatsApp no celular, vá em Configurações › Aparelhos conectados e remova este aparelho.',
				{ titulo: 'Desligar o WhatsApp?', ok: 'Desligar', perigo: true }).then(function (sim) {
				if (sim) acao('/mensageiros/whatsapp/desligar');
			});
		}));
	}

	function pintar() { dlg.repintar(pintarCorpo); }

	function pintarCorpo(body) {
		body.innerHTML = '';
		pintouEm = Date.now();
		if (!est) { body.appendChild(el('p', '', 'Não consegui falar com o Nous. Ele está aberto?')); return; }
		var intro = el('p');
		intro.innerHTML = 'Fale com o Nous de qualquer lugar, pelo celular. O modelo continua no seu computador, que precisa estar <b>ligado</b>; só o texto e o áudio da conversa passam pelo Telegram ou pelo WhatsApp.';
		body.appendChild(intro);
		if (aviso) { var a = el('div', 'nous-dlg-aviso' + (aviso.erro ? ' erro' : ''), aviso.texto); body.appendChild(a); }
		secaoTelegram(body);
		secaoWhatsApp(body);
		pintarTempo();
	}

	/* ------------------------------------------------------------ abrir/fechar */
	function abrir() {
		injectStyle();
		dlg.abrir();
		aviso = null;
		if (UI.loadUserId) UI.loadUserId(function (u) { uid = u; pintar(); });
		pintar();
		carregar();
		clearInterval(atualiza); clearInterval(relogio);
		atualiza = setInterval(carregar, 3000);
		relogio = setInterval(pintarTempo, 1000);
	}

	function parar() { clearInterval(atualiza); clearInterval(relogio); }

	/* botao no antigo card Recursos: o painel "Seu Nous" mostra como ferramenta */
	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-msg-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-msg-open';
		b.type = 'button';
		b.textContent = '💬 Telegram e WhatsApp';
		b.addEventListener('click', abrir);
		body.appendChild(b);
	}

	window.NousMensageiros = { open: abrir };

	function start() { injectStyle(); ensureButton(); setInterval(ensureButton, 1500); }
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
