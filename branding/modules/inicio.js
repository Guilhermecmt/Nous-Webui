/* =====================================================================
   Nous - Tela inicial (v2.10). O Nous abre direto no chat, sem login, e o chat
   vazio recebe a pessoa: saudacao pelo nome e pela hora, uma frase sobre a
   privacidade, uma dica do Nous (muda a cada visita) e o botao "Conversa
   privada" (o chat temporario do Open WebUI: nao fica no historico e o
   filtro de memoria nao aprende nada dele).
   Sem login, o "Sair" do menu da conta some: ele so' levaria de volta ao chat.
   ===================================================================== */
(function () {
	'use strict';

	var DICAS = [
		'escreva <b>"abre meus documentos"</b> para escrever com a IA ao lado.',
		'diga <b>"me lembre de pagar a luz sexta às 9h"</b> e o Windows avisa na hora.',
		'solte um PDF, foto ou boleto aqui e pergunte sobre ele.',
		'escolha <b>Pesquisa Profunda (Nous)</b> no topo para um relatório com fontes.',
		'embaixo de cada resposta: <b>✂ Mais curto</b> e <b>🙂 Mais simples</b>.',
		'diga <b>"aprenda isso"</b> e o Nous guarda o passo a passo para a próxima vez.',
		'escreva <b>"abre a loja"</b> para ver os modelos que rodam melhor na sua máquina.',
		'escreva <b>"abre minhas memórias"</b> para ver, corrigir ou apagar o que o Nous sabe de você.',
		'<b>"tema escuro"</b> ou <b>"tema claro"</b> muda as cores na hora.',
		'<b>Conversa privada</b> não fica no histórico nem vira memória.'
	];
	var dica = DICAS[Math.floor(Math.random() * DICAS.length)];
	var nome = null;        /* primeiro nome da conta; '' = sem nome */
	var semLogin = false;

	function injectStyle() {
		if (document.getElementById('nous-ini-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-ini-style';
		st.textContent =
			'#nous-ini{display:flex;flex-direction:column;align-items:center;gap:7px;margin:14px 16px 2px;' +
			'font-family:Inter,system-ui,sans-serif;text-align:center;max-width:560px}' +
			'#nous-ini h2{margin:0;font:600 28px/1.2 Cinzel,Georgia,serif;letter-spacing:.04em;color:#8a6414}' +
			'.dark #nous-ini h2{color:#e7c069}' +
			'#nous-ini .nous-ini-sub{font-size:14.5px;line-height:1.45;color:#5f5f5f}' +
			'.dark #nous-ini .nous-ini-sub{color:#a8a8a8}' +
			'#nous-ini .nous-ini-dica{font-size:12.5px;line-height:1.45;color:#7a7a7a}' +
			'.dark #nous-ini .nous-ini-dica{color:#8c8c8c}' +
			'#nous-ini .nous-ini-dica b{font-weight:600;color:#8a6414}.dark #nous-ini .nous-ini-dica b{color:#c8962e}' +
			'#nous-ini-priv{margin-top:4px;display:inline-flex;align-items:center;gap:6px;padding:5px 13px;' +
			'border:1px solid rgba(200,150,46,.45);border-radius:999px;background:none;cursor:pointer;' +
			'font:500 12.5px Inter,system-ui,sans-serif;color:#8a6414;transition:background .15s}' +
			'.dark #nous-ini-priv{color:#c8962e}' +
			'#nous-ini-priv:hover{background:rgba(200,150,46,.12)}' +
			'#nous-ini-priv.on{background:rgba(200,150,46,.2);border-color:#c8962e}' +
			'#nous-ini-priv svg{width:14px;height:14px}' +
			'@media (max-width:640px){#nous-ini h2{font-size:23px}#nous-ini .nous-ini-sub{font-size:13.5px}}';
		document.head.appendChild(st);
	}

	function token() { try { return localStorage.getItem('token') || ''; } catch (e) { return ''; } }

	function carregar() {
		fetch('/api/config').then(function (r) { return r.json(); })
			.then(function (c) { semLogin = !!(c && c.features && c.features.auth === false); })
			.catch(function () {});
		tentarNome();
	}

	function tentarNome() {
		var t = token();
		if (!t) { setTimeout(tentarNome, 1000); return; }   /* sem login o token chega logo depois */
		fetch('/api/v1/auths/', { headers: { 'Authorization': 'Bearer ' + t } })
			.then(function (r) { return r.json(); })
			.then(function (d) {
				var n = ((d && d.name) || '').trim().split(/\s+/)[0] || '';
				nome = (n === 'User') ? '' : n;
				var h = document.querySelector('#nous-ini h2');
				if (h) h.textContent = saudacao();
			})
			.catch(function () { nome = ''; });
	}

	function saudacao() {
		var h = new Date().getHours();
		var s = h >= 5 && h < 12 ? 'Bom dia' : (h >= 12 && h < 18 ? 'Boa tarde' : 'Boa noite');
		return nome ? s + ', ' + nome : s;
	}

	function privada() { return /[?&]temporary-chat=true/.test(location.search); }

	var OLHO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
		'<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
	var OLHO_X = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
		'<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><line x1="4" y1="20" x2="20" y2="4"/></svg>';

	function pintarPriv(btn) {
		var on = privada();
		btn.classList.toggle('on', on);
		btn.innerHTML = on ? OLHO_X + 'Conversa privada ligada' : OLHO + 'Conversa privada';
		btn.title = on ? 'Clique para voltar à conversa normal'
			: 'Não fica no histórico nem vira memória';
	}

	function montar() {
		var div = document.createElement('div');
		div.id = 'nous-ini';
		div.innerHTML = '<h2></h2>' +
			'<div class="nous-ini-sub">Sua IA particular. Tudo o que você escreve fica neste computador.</div>' +
			'<div class="nous-ini-dica">Dica: ' + dica + '</div>';
		div.querySelector('h2').textContent = saudacao();
		var tb = document.getElementById('temporary-chat-button');
		if (tb) {
			var btn = document.createElement('button');
			btn.type = 'button';
			btn.id = 'nous-ini-priv';
			pintarPriv(btn);
			btn.addEventListener('click', function () {
				var alvo = document.getElementById('temporary-chat-button');
				if (!alvo) return;
				alvo.click();
				setTimeout(function () { pintarPriv(btn); }, 150);
			});
			div.appendChild(btn);
		}
		return div;
	}

	/* A fileira do avatar do modelo no chat vazio; o bloco entra logo abaixo. */
	function fileiraAvatar() {
		var rows = document.querySelectorAll('div.w-fit.max-w-xl.justify-center');
		for (var i = 0; i < rows.length; i++) if (rows[i].querySelector('img')) return rows[i];
		return null;
	}

	function tick() {
		var row = fileiraAvatar();
		var atual = document.getElementById('nous-ini');
		if (!row) { if (atual) atual.remove(); return; }
		if (!atual || atual.previousElementSibling !== row) {
			if (atual) atual.remove();
			atual = montar();
			row.insertAdjacentElement('afterend', atual);
		}
		var btn = document.getElementById('nous-ini-priv');
		if (btn && btn.classList.contains('on') !== privada()) pintarPriv(btn);
		if (!document.getElementById('temporary-chat-button') && btn) btn.remove();
	}

	/* Sem login, "Sair" so' levaria de volta ao chat: some do menu da conta. E o
	   aviso "Voce agora esta logado" da entrada automatica nao faz sentido. */
	function semSair() {
		if (!semLogin) return;
		var avisos = document.querySelectorAll('[data-sonner-toast]');
		for (var j = 0; j < avisos.length; j++) {
			if (/agora est[aá] logado|now logged in/i.test(avisos[j].textContent)) avisos[j].style.display = 'none';
		}
		/* menu da conta (0.12: [role=menu] com Espaço de Trabalho/Notas): "Sair"
		   e' o ultimo botao, em qualquer idioma */
		var alvos = [];
		var menus = document.querySelectorAll('[role="menu"]');
		for (var m = 0; m < menus.length; m++) {
			if (!menus[m].querySelector('a[href="/workspace"], a[href="/notes"]')) continue;
			var bs = menus[m].querySelectorAll('button');
			if (bs.length) alvos.push(bs[bs.length - 1]);
		}
		/* versoes antigas: botao com o texto do rotulo */
		var itens = document.querySelectorAll('button[type="button"] > div.truncate');
		for (var i = 0; i < itens.length; i++) {
			var t = itens[i].textContent.trim();
			if (t === 'Sair' || t === 'Sign Out') alvos.push(itens[i].parentElement);
		}
		for (var k = 0; k < alvos.length; k++) {
			var b = alvos[k];
			b.style.display = 'none';
			var hr = b.previousElementSibling;
			if (hr && hr.tagName === 'HR') hr.style.display = 'none';
		}
	}

	var agendado = false;
	function aoMudar() {
		if (agendado) return;
		agendado = true;
		requestAnimationFrame(function () { agendado = false; semSair(); tick(); });
	}

	function start() {
		injectStyle();
		carregar();
		setInterval(tick, 600);
		new MutationObserver(aoMudar).observe(document.body, { childList: true, subtree: true });
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
