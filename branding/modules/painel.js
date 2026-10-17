/* =====================================================================
   Nous - Painel "Seu Nous" (v2.10). Um painel fixo a' direita junta o que
   antes flutuava pela tela (card Recursos, botao da memoria, botao do tema,
   icone do chat temporario):
     - a coruja dentro de um anel que mostra quanto da placa de video esta' em
       uso (dourado quando ha' um modelo carregado) e o que o Nous esta' fazendo
     - Conversa privada (o chat temporario do Open WebUI)
     - Hoje: os proximos lembretes e compromissos da Agenda
     - O que o Nous sabe de voce: as memorias mais recentes
     - Ferramentas: os mesmos botoes do antigo card Recursos, com nome inteiro
   Telas largas (>= 1280px): o painel ocupa espaco e o chat encolhe. Telas
   menores: vira gaveta por cima. Fechado, fica so' a coruja com o anel.
   Tambem arruma o resto da casca: marca maior na barra lateral, estrela no
   lugar de "Definir como padrao", primeiro nome no lugar do nome inteiro.
   ===================================================================== */
(function () {
	'use strict';

	var MON = 'http://127.0.0.1:8990';
	var MEM = 'http://127.0.0.1:8993';
	var AG = 'http://127.0.0.1:8996';
	var LARGO = 1280;
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };

	/* As ferramentas sao os botoes que cada modulo poe no antigo card Recursos:
	 * o painel so' repassa o clique (o card fica escondido, nao some). */
	var FERR = [
		['nous-docs-open', 'Documentos', 'doc'],
		['nous-agenda-open', 'Agenda', 'cal'],
		['nous-email-open', 'E-mail', 'mail'],
		['nous-reports-open', 'Pesquisas', 'globe'],
		['nous-gallery-open', 'Galeria', 'img'],
		['nous-editor-open', 'Editar fotos', 'crop'],
		['nous-pdf-open', 'Formulários', 'form'],
		['nous-skills-open', 'Habilidades', 'spark'],
		['nous-cmp-open', 'Comparar', 'scale'],
		['nous-store-open', 'Modelos', 'store'],
		['nous-voice-open', 'Voz', 'mic'],
		['nous-diag-open', 'Diagnóstico', 'pulse']
	];
	var ICON = {
		doc: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
		cal: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
		mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
		globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
		img: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/>',
		crop: '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>',
		form: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/><path d="m9 15 2 2 4-4"/>',
		spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
		scale: '<path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a4 4 0 0 0 6 0zM19 7l-3 7a4 4 0 0 0 6 0z"/>',
		store: '<path d="M3 9 5 4h14l2 5M4 9v11h16V9M3 9h18M9 20v-6h6v6"/>',
		mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
		pulse: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
		sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
		moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
		fechar: '<path d="m13 6 6 6-6 6M5 6l6 6-6 6"/>',
		olho: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
		estrela: '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2L3 9.6l6.2-.9z"/>'
	};
	function svg(nome, cls) {
		return '<svg class="' + (cls || 'nous-pn-ic') + '" viewBox="0 0 24 24" aria-hidden="true">' + ICON[nome] + '</svg>';
	}

	var el = null, alca = null, aberto = null, uid = null, conteudo = null;
	var stats = null, mems = null, agenda = null, nomeConta = '';

	function ler(k, d) { try { var v = localStorage.getItem(k); return v === null ? d : v; } catch (e) { return d; } }
	function gravar(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
	function largo() { return window.innerWidth >= LARGO; }

	/* ------------------------------------------------------------ estilo */
	function injectStyle() {
		if (document.getElementById('nous-pn-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-pn-style';
		st.textContent =
			/* tokens: noite, ouro velho, ouro claro, pergaminho, bronze apagado */
			':root{--pn-w:300px;--pn-bg:#ffffff;--pn-alto:#faf6ee;--pn-linha:rgba(138,100,20,.16);--pn-ouro:#a87a1c;' +
			'--pn-ouro2:#8a6414;--pn-txt:#2a251e;--pn-mut:#7a6f5d;--pn-trilho:rgba(138,100,20,.14)}' +
			'.dark{--pn-bg:#141210;--pn-alto:#1c1916;--pn-linha:rgba(231,192,105,.12);--pn-ouro:#c8962e;' +
			'--pn-ouro2:#e7c069;--pn-txt:#ddd5c6;--pn-mut:#958a76;--pn-trilho:rgba(231,192,105,.13)}' +

			'#nous-pn{position:fixed;top:0;right:0;bottom:0;width:var(--pn-w);z-index:40;background:var(--pn-bg);' +
			'border-left:1px solid var(--pn-linha);color:var(--pn-txt);font:14px/1.5 Inter,system-ui,sans-serif;' +
			'display:flex;flex-direction:column;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;' +
			'scrollbar-color:var(--pn-trilho) transparent;transition:transform .26s cubic-bezier(.2,.7,.2,1)}' +
			'#nous-pn.nous-pn-off{transform:translateX(100%);visibility:hidden}' +
			'body:not(.nous-pn-fixo) #nous-pn{box-shadow:-21px 0 55px rgba(0,0,0,.28)}' +
			'#nous-pn button{font:inherit;color:inherit;background:none;border:0;cursor:pointer}' +
			'#nous-pn button:focus-visible,#nous-pn-alca:focus-visible,.nous-pn-estrela:focus-visible{outline:2px solid var(--pn-ouro);outline-offset:2px;border-radius:8px}' +
			'.nous-pn-ic{width:18px;height:18px;flex:none;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}' +

			/* cabecalho: a coruja no anel */
			'#nous-pn-head{display:grid;grid-template-columns:55px 1fr auto;gap:13px;align-items:center;padding:21px 13px 21px 21px}' +
			'.nous-pn-anel{position:relative;display:block;width:55px;height:55px}' +
			'.nous-pn-anel svg{position:absolute;inset:0;transform:rotate(-90deg)}' +
			'.nous-pn-anel circle{fill:none;stroke-width:2.5}' +
			'.nous-pn-anel .trilho{stroke:var(--pn-trilho)}' +
			'.nous-pn-anel .uso{stroke:var(--pn-mut);stroke-linecap:round;transition:stroke-dashoffset .8s ease,stroke .4s}' +
			'.nous-pn-anel.vivo .uso{stroke:var(--pn-ouro)}' +
			'.nous-pn-anel img{position:absolute;left:50%;top:50%;width:30px;height:30px;transform:translate(-50%,-50%)}' +
			'#nous-pn-titulo{margin:0;font:600 21px/1.15 Cinzel,Georgia,serif;letter-spacing:.06em;color:var(--pn-ouro2)}' +
			'#nous-pn-estado{font-size:12.5px;line-height:1.45;color:var(--pn-mut);margin-top:5px;font-variant-numeric:tabular-nums}' +
			'#nous-pn-estado b{font-weight:600;color:var(--pn-txt)}' +
			'#nous-pn-liberar{margin-top:5px;padding:0!important;font-size:12.5px!important;font-weight:600!important;color:var(--pn-ouro)!important;text-decoration:underline;text-underline-offset:3px}' +
			'.nous-pn-acoes{display:flex;flex-direction:column;gap:2px;align-self:start}' +
			'.nous-pn-acoes button{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;color:var(--pn-mut)!important}' +
			'.nous-pn-acoes button:hover{background:var(--pn-alto);color:var(--pn-ouro2)!important}' +

			/* secoes */
			'.nous-pn-sec{padding:13px 21px 21px;border-top:1px solid var(--pn-linha)}' +
			'.nous-pn-sec-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:8px}' +
			'.nous-pn-sec-h h3{margin:0;font-size:13.5px;font-weight:600;color:var(--pn-txt)}' +
			'.nous-pn-sec-h button{font-size:12.5px!important;color:var(--pn-ouro)!important;padding:0!important}' +
			'.nous-pn-sec-h button:hover{text-decoration:underline;text-underline-offset:3px}' +
			'.nous-pn-vazio{font-size:13px;color:var(--pn-mut);line-height:1.5}' +

			/* conversa privada */
			'#nous-pn-priv{display:grid;grid-template-columns:auto 1fr auto;gap:13px;align-items:center;width:100%;text-align:left;' +
			'padding:13px!important;border-radius:13px;border:1px solid var(--pn-linha)!important;transition:background .2s,border-color .2s}' +
			'#nous-pn-priv:hover{background:var(--pn-alto)}' +
			'#nous-pn-priv[aria-checked="true"]{border-color:var(--pn-ouro)!important;background:var(--pn-alto)}' +
			'#nous-pn-priv .t{font-size:13.5px;font-weight:500}' +
			'#nous-pn-priv .s{font-size:12px;color:var(--pn-mut);line-height:1.35}' +
			'#nous-pn-priv .nous-pn-ic{color:var(--pn-ouro)}' +
			'.nous-pn-sw{width:34px;height:21px;border-radius:21px;background:var(--pn-trilho);position:relative;transition:background .2s}' +
			'.nous-pn-sw::after{content:"";position:absolute;left:3px;top:3px;width:15px;height:15px;border-radius:50%;background:var(--pn-mut);transition:transform .2s,background .2s}' +
			'[aria-checked="true"] .nous-pn-sw{background:var(--pn-ouro)}' +
			'[aria-checked="true"] .nous-pn-sw::after{transform:translateX(13px);background:#fff}' +

			/* hoje e memorias */
			'.nous-pn-lista{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}' +
			'.nous-pn-lista li{display:grid;grid-template-columns:55px 1fr;gap:8px;padding:5px 0;font-size:13.5px;line-height:1.4}' +
			'.nous-pn-lista .h{font-variant-numeric:tabular-nums;color:var(--pn-ouro2);font-weight:600;font-size:12.5px;padding-top:1px}' +
			'.nous-pn-lista .h.atraso{color:#c0573f}' +
			'.nous-pn-fatos{margin:0;padding:0;list-style:none}' +
			'.nous-pn-fatos li{position:relative;padding:4px 0 4px 13px;font-size:13.5px;line-height:1.45}' +
			'.nous-pn-fatos li::before{content:"";position:absolute;left:0;top:12px;width:5px;height:5px;border-radius:50%;background:var(--pn-ouro)}' +

			/* ferramentas */
			'#nous-pn-ferr .grade{display:grid;grid-template-columns:1fr 1fr;gap:2px 8px}' +
			'#nous-pn-ferr .grade button{display:flex;align-items:center;gap:8px;padding:6px 8px!important;border-radius:8px;text-align:left;font-size:13px!important;line-height:1.3}' +
			'#nous-pn-ferr .grade button:hover{background:var(--pn-alto);color:var(--pn-ouro2)!important}' +
			'#nous-pn-ferr .grade .nous-pn-ic{width:16px;height:16px;color:var(--pn-ouro)}' +

			/* coruja sozinha, com o painel fechado */
			'#nous-pn-alca{position:fixed;right:13px;top:68px;z-index:39;width:44px;height:44px;border-radius:50%;border:0;padding:0;cursor:pointer;' +
			'background:var(--pn-bg);box-shadow:0 5px 21px rgba(0,0,0,.18)}' +
			'#nous-pn-alca .nous-pn-anel{width:44px;height:44px}#nous-pn-alca .nous-pn-anel img{width:24px;height:24px}' +
			'#nous-pn-alca.nous-pn-off{display:none}' +

			/* o chat abre espaco para o painel (so' em tela larga) */
			'body.nous-pn-fixo #chat-container,body.nous-pn-fixo .nous-pn-conteudo{padding-right:var(--pn-w)!important}' +
			'body.nous-pn-fixo #nous-mem-panel{right:calc(var(--pn-w) + 13px)!important;bottom:21px!important}' +
			/* o que o painel substitui */
			'body.nous-pn-on #nous-monitor,body.nous-pn-on #nous-mem-btn,body.nous-pn-on #nous-theme-toggle,' +
			'body.nous-pn-on #nous-home-wordmark,body.nous-pn-on #temporary-chat-button,body.nous-pn-on .nous-pn-def-velho{display:none!important}' +
			'body.nous-pn-on #nous-ini-priv{display:none}' +

			/* casca: marca maior na barra lateral e estrela do modelo padrao */
			'#sidebar .sidebar-new-chat-icon{width:30px!important;height:30px!important;border-radius:0!important}' +
			'#sidebar-webui-name{font:600 21px Cinzel,Georgia,serif!important;letter-spacing:.16em;color:var(--pn-ouro2)!important;padding-left:5px}' +
			'.nous-pn-estrela{display:grid;place-items:center;width:28px;height:28px;margin-left:2px;border-radius:8px;border:0;background:none;cursor:pointer;color:var(--pn-mut);align-self:center}' +
			'.nous-pn-estrela:hover{color:var(--pn-ouro2);background:var(--pn-alto)}' +
			'.nous-pn-estrela .nous-pn-ic{width:17px;height:17px}' +
			'.nous-pn-estrela.on{color:var(--pn-ouro)}.nous-pn-estrela.on .nous-pn-ic{fill:currentColor}' +

			'@media (max-width:640px){#nous-pn{--pn-w:88vw}}' +
			'@media (prefers-reduced-motion:reduce){#nous-pn,.nous-pn-anel .uso,.nous-pn-sw,.nous-pn-sw::after{transition:none!important}}';
		document.head.appendChild(st);
	}

	/* ------------------------------------------------------------ montagem */
	function anel(cls) {
		return '<span class="nous-pn-anel ' + (cls || '') + '"><svg viewBox="0 0 55 55" aria-hidden="true">' +
			'<circle class="trilho" cx="27.5" cy="27.5" r="25.5"/><circle class="uso" cx="27.5" cy="27.5" r="25.5"/></svg>' +
			'<img src="/static/favicon.png" alt=""></span>';
	}

	function build() {
		if (el && document.body.contains(el)) return;
		el = document.createElement('aside');
		el.id = 'nous-pn';
		el.setAttribute('aria-label', 'Seu Nous');
		el.innerHTML =
			'<div id="nous-pn-head">' + anel() +
				'<div><h2 id="nous-pn-titulo">Seu Nous</h2><div id="nous-pn-estado">Conferindo a placa de vídeo…</div>' +
				'<button id="nous-pn-liberar" type="button" hidden>Liberar a placa de vídeo</button></div>' +
				'<div class="nous-pn-acoes"><button id="nous-pn-tema" type="button"></button>' +
				'<button id="nous-pn-fechar" type="button" aria-label="Fechar o painel" title="Fechar o painel">' + svg('fechar') + '</button></div>' +
			'</div>' +
			'<div class="nous-pn-sec" style="border-top:0;padding-top:0">' +
				'<button id="nous-pn-priv" type="button" role="switch" aria-checked="false">' + svg('olho') +
				'<span><span class="t">Conversa privada</span><br><span class="s">Não fica no histórico nem vira memória</span></span>' +
				'<span class="nous-pn-sw" aria-hidden="true"></span></button>' +
			'</div>' +
			'<section class="nous-pn-sec" id="nous-pn-hoje"><div class="nous-pn-sec-h"><h3>Hoje</h3>' +
				'<button type="button" data-abre="nous-agenda-open">Abrir agenda</button></div><div class="corpo"></div></section>' +
			'<section class="nous-pn-sec" id="nous-pn-mem"><div class="nous-pn-sec-h"><h3>O que eu sei de você</h3>' +
				'<button type="button" id="nous-pn-mem-ver">Ver e editar</button></div><div class="corpo"></div></section>' +
			'<section class="nous-pn-sec" id="nous-pn-ferr"><div class="nous-pn-sec-h"><h3>Ferramentas</h3></div><div class="grade"></div></section>';
		document.body.appendChild(el);

		el.querySelector('#nous-pn-fechar').addEventListener('click', function () { abrir(false, true); });
		el.querySelector('#nous-pn-tema').addEventListener('click', function () {
			if (UI.setTheme) UI.setTheme(escuro() ? 'light' : 'dark');
			setTimeout(pintarTema, 60);
		});
		el.querySelector('#nous-pn-liberar').addEventListener('click', liberar);
		el.querySelector('#nous-pn-priv').addEventListener('click', alternarPrivada);
		el.querySelector('#nous-pn-mem-ver').addEventListener('click', function () {
			if (UI.openMemory) UI.openMemory();
			if (!largo()) abrir(false);
		});
		el.addEventListener('click', function (e) {
			var b = e.target.closest('[data-abre]');
			if (!b) return;
			var alvo = document.getElementById(b.getAttribute('data-abre'));
			if (alvo) alvo.click();
			if (!largo()) abrir(false);
		});
		el.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !largo()) { abrir(false); alca.focus(); } });

		alca = document.createElement('button');
		alca.id = 'nous-pn-alca';
		alca.type = 'button';
		alca.setAttribute('aria-label', 'Abrir o painel Seu Nous');
		alca.title = 'Seu Nous';
		alca.innerHTML = anel();
		alca.addEventListener('click', function () { abrir(true, true); });
		document.body.appendChild(alca);

		/* clique fora fecha a gaveta (tela estreita) */
		document.addEventListener('mousedown', function (e) {
			if (largo() || !aberto) return;
			if (el.contains(e.target) || alca.contains(e.target)) return;
			abrir(false);
		});
		pintarTema();
		pintarFerr();
	}

	/* ------------------------------------------------------------ abrir/fechar */
	function abrir(sim, escolhido) {
		aberto = !!sim;
		if (escolhido) gravar('nous-pn', aberto ? '1' : '0');
		el.classList.toggle('nous-pn-off', !aberto);
		alca.classList.toggle('nous-pn-off', aberto);
		document.body.classList.toggle('nous-pn-fixo', aberto && largo());
		if (aberto) { carregarListas(); if (escolhido) el.querySelector('#nous-pn-fechar').focus(); }
	}

	function estadoInicial() {
		/* tela larga: aberto, a nao ser que a pessoa tenha fechado; estreita: fechado */
		abrir(largo() && ler('nous-pn', '1') !== '0');
	}

	/* ------------------------------------------------------------ anel e estado */
	function gb(n) { return (Number(n || 0) / 1073741824).toFixed(1).replace('.', ','); }

	function pintarAnel(frac, vivo) {
		var c = 2 * Math.PI * 25.5;
		document.querySelectorAll('.nous-pn-anel').forEach(function (a) {
			var u = a.querySelector('.uso');
			u.style.strokeDasharray = c.toFixed(1);
			u.style.strokeDashoffset = (c * (1 - Math.max(0.02, Math.min(1, frac)))).toFixed(1);
			a.classList.toggle('vivo', vivo);
		});
	}

	function minutos(s) {
		if (s == null) return '';
		var m = Math.round(s / 60);
		return m <= 1 ? 'sai em menos de 1 minuto' : 'sai em ' + m + ' min';
	}

	function pintarEstado() {
		var est = el.querySelector('#nous-pn-estado');
		var lib = el.querySelector('#nous-pn-liberar');
		if (!stats || !stats.gpu) {
			est.textContent = 'O monitor não respondeu. Abra o Nous pelo atalho para ligá-lo.';
			lib.hidden = true;
			pintarAnel(0, false);
			alca.title = 'Seu Nous';
			return;
		}
		var g = stats.gpu, ms = stats.models || [];
		var frac = g.ded_total ? g.ded_used / g.ded_total : 0;
		var uso = gb(g.ded_used) + ' de ' + gb(g.ded_total) + ' GB em uso';
		if (ms.length) {
			var m = ms[0];
			est.innerHTML = '<b>' + esc(m.name) + ' pronto</b><br>' + minutos(m.seconds_left) + ' da memória';
			lib.hidden = false;
		} else {
			est.innerHTML = '<b>Descansando</b><br>' + uso;
			lib.hidden = true;
		}
		pintarAnel(frac, ms.length > 0);
		alca.title = 'Seu Nous: placa de vídeo com ' + uso;
	}

	function atualizarStats() {
		fetch(MON + '/stats', { cache: 'no-store' })
			.then(function (r) { return r.json(); })
			.then(function (s) { stats = s; })
			.catch(function () { stats = null; })
			.then(function () { if (el) pintarEstado(); });
	}

	function liberar() {
		var lib = el.querySelector('#nous-pn-liberar');
		lib.disabled = true;
		lib.textContent = 'Liberando…';
		fetch(MON + '/unload', { method: 'POST' }).catch(function () {}).then(function () {
			lib.disabled = false;
			lib.textContent = 'Liberar a placa de vídeo';
			setTimeout(atualizarStats, 600);
		});
	}

	/* ------------------------------------------------------------ tema */
	function escuro() { return document.documentElement.classList.contains('dark'); }
	function pintarTema() {
		var b = el && el.querySelector('#nous-pn-tema');
		if (!b) return;
		var e = escuro();
		b.innerHTML = svg(e ? 'sun' : 'moon');
		b.setAttribute('aria-label', e ? 'Usar o tema claro' : 'Usar o tema escuro');
		b.title = b.getAttribute('aria-label');
	}

	/* ------------------------------------------------------------ conversa privada */
	function privada() { return /[?&]temporary-chat=true/.test(location.search); }
	function alternarPrivada() {
		var tb = document.getElementById('temporary-chat-button');
		if (!tb) { location.assign('/?temporary-chat=true'); return; }  /* dentro de uma conversa: abre uma nova, privada */
		tb.click();
		setTimeout(pintarPrivada, 150);
	}
	function pintarPrivada() {
		var b = el.querySelector('#nous-pn-priv');
		var on = privada();
		if (b.getAttribute('aria-checked') !== String(on)) b.setAttribute('aria-checked', String(on));
		var s = b.querySelector('.s');
		var txt = on ? 'Ligada: esta conversa não fica guardada'
			: (document.getElementById('temporary-chat-button') ? 'Não fica no histórico nem vira memória'
				: 'Abre uma conversa nova, sem histórico');
		if (s.textContent !== txt) s.textContent = txt;
	}

	/* ------------------------------------------------------------ hoje */
	function hora(ts) {
		var d = new Date(ts * 1000);
		return ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2);
	}
	function quando(ts, agora) {
		var d = new Date(ts * 1000), h = new Date(agora * 1000);
		var dias = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) -
			new Date(h.getFullYear(), h.getMonth(), h.getDate())) / 86400000);
		if (ts < agora - 60) return { t: 'atrasado', atraso: true };
		if (dias === 0) return { t: hora(ts) };
		if (dias === 1) return { t: 'amanhã' };
		return { t: ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sáb'][d.getDay()] };
	}

	function pintarHoje() {
		var c = el.querySelector('#nous-pn-hoje .corpo');
		if (agenda === 'off') {
			c.innerHTML = '<p class="nous-pn-vazio">A agenda não respondeu. Ela volta quando o Nous for aberto pelo atalho.</p>';
			return;
		}
		if (!agenda) { c.innerHTML = ''; return; }
		var itens = [];
		(agenda.events || []).forEach(function (e) { itens.push({ ts: e.occ_start || e.start_at, t: e.title }); });
		(agenda.notes || []).forEach(function (n) { itens.push({ ts: n.due_at || n.remind_at, t: n.title }); });
		itens = itens.filter(function (i) { return i.ts; }).sort(function (a, b) { return a.ts - b.ts; }).slice(0, 4);
		if (!itens.length) {
			c.innerHTML = '<p class="nous-pn-vazio">Nada marcado para os próximos dias. Escreva no chat: "me lembre de pagar a luz sexta às 9h".</p>';
			return;
		}
		c.innerHTML = '<ul class="nous-pn-lista">' + itens.map(function (i) {
			var q = quando(i.ts, agenda.now || Date.now() / 1000);
			return '<li><span class="h' + (q.atraso ? ' atraso' : '') + '">' + q.t + '</span><span>' + esc(i.t) + '</span></li>';
		}).join('') + '</ul>';
	}

	/* ------------------------------------------------------------ memorias */
	function pintarMem() {
		var c = el.querySelector('#nous-pn-mem .corpo');
		if (mems === 'off') {
			c.innerHTML = '<p class="nous-pn-vazio">A memória não respondeu. Ela volta quando o Nous for aberto pelo atalho.</p>';
			return;
		}
		if (!mems) { c.innerHTML = ''; return; }
		if (!mems.length) {
			c.innerHTML = '<p class="nous-pn-vazio">Ainda não sei nada sobre você. Conte no chat, por exemplo: "eu moro em Recife e trabalho com vendas".</p>';
			return;
		}
		var lista = mems.slice(0, 3);  /* a API ja' manda fixadas primeiro, depois as mais novas */
		c.innerHTML = '<ul class="nous-pn-fatos">' + lista.map(function (m) { return '<li>' + esc(m.text) + '</li>'; }).join('') + '</ul>';
	}

	function carregarListas() {
		var load = UI.loadUserId || function (cb) { cb(null); };
		load(function (id) {
			uid = id;
			if (!uid) { setTimeout(carregarListas, 1500); return; }  /* o token chega logo depois da entrada */
			fetch(MEM + '/memories?user_id=' + encodeURIComponent(uid), { cache: 'no-store' })
				.then(function (r) { return r.json(); })
				.then(function (d) { mems = Array.isArray(d) ? d : 'off'; })
				.catch(function () { mems = 'off'; })
				.then(pintarMem);
			fetch(AG + '/today?days=3&user_id=' + encodeURIComponent(uid), { cache: 'no-store' })
				.then(function (r) { return r.json(); })
				.then(function (d) { agenda = d && (d.events || d.notes) ? d : 'off'; })
				.catch(function () { agenda = 'off'; })
				.then(pintarHoje);
		});
	}

	/* ------------------------------------------------------------ ferramentas */
	function pintarFerr() {
		var g = el.querySelector('#nous-pn-ferr .grade');
		var html = FERR.filter(function (f) { return document.getElementById(f[0]); }).map(function (f) {
			return '<button type="button" data-abre="' + f[0] + '" title="' + f[1] + '">' + svg(f[2]) + '<span>' + f[1] + '</span></button>';
		}).join('');
		if (g.getAttribute('data-h') !== html) { g.innerHTML = html; g.setAttribute('data-h', html); }
	}

	/* ------------------------------------------------------------ casca do Open WebUI */
	function marcarConteudo() {
		var sb = document.getElementById('sidebar');
		var alvo = null;
		if (sb && sb.parentElement) {
			var max = -1;
			for (var i = 0; i < sb.parentElement.children.length; i++) {
				var c = sb.parentElement.children[i];
				if (c === sb || c.id === 'nous-pn') continue;
				var w = c.getBoundingClientRect().width;
				if (w > max) { max = w; alvo = c; }
			}
		}
		/* o Svelte reescreve o class do container ao abrir/fechar a barra lateral */
		if (alvo !== conteudo && conteudo) conteudo.classList.remove('nous-pn-conteudo');
		if (alvo && !alvo.classList.contains('nous-pn-conteudo')) alvo.classList.add('nous-pn-conteudo');
		conteudo = alvo;
	}

	/* "Definir como padrao" vira uma estrela ao lado do nome do modelo */
	var padrao = null;
	function estrela() {
		var def = null, bs = document.querySelectorAll('button');
		for (var i = 0; i < bs.length; i++) {
			if (/^Definir como padr|^Set as default/.test(bs[i].textContent.trim())) { def = bs[i]; break; }
		}
		var velha = document.querySelector('.nous-pn-estrela');
		if (!def) { if (velha) velha.remove(); return; }
		var wrap = def.parentElement;
		wrap.classList.add('nous-pn-def-velho');
		var linha = wrap.previousElementSibling && wrap.previousElementSibling.firstElementChild;
		if (!linha) return;
		if (!velha || velha.parentElement !== linha) {
			if (velha) velha.remove();
			velha = document.createElement('button');
			velha.type = 'button';
			velha.className = 'nous-pn-estrela';
			velha.innerHTML = svg('estrela');
			velha.addEventListener('click', function () {
				var d = document.querySelector('.nous-pn-def-velho button');
				if (d) d.click();
				padrao = modeloAtual();
				pintarEstrela();
			});
			linha.appendChild(velha);
		}
		pintarEstrela();
	}
	function modeloAtual() {
		var m = document.querySelector('.nous-pn-def-velho');
		var linha = m && m.previousElementSibling;
		return linha ? linha.textContent.trim() : '';
	}
	function pintarEstrela() {
		var b = document.querySelector('.nous-pn-estrela');
		if (!b) return;
		var on = !!padrao && modeloAtual() === padrao;
		b.classList.toggle('on', on);
		var t = on ? 'Este é o seu modelo padrão' : 'Usar este modelo sempre';
		if (b.title !== t) { b.title = t; b.setAttribute('aria-label', t); }
	}
	function carregarPadrao() {
		var t = '';
		try { t = localStorage.getItem('token') || ''; } catch (e) {}
		if (!t) return;
		fetch('/api/v1/users/user/settings', { headers: { Authorization: 'Bearer ' + t } })
			.then(function (r) { return r.json(); })
			.then(function (s) { var ms = s && s.ui && s.ui.models; padrao = ms && ms[0] ? ms[0] : null; pintarEstrela(); })
			.catch(function () {});
	}

	/* Nome inteiro cortado na barra lateral vira o primeiro nome */
	function primeiroNome() {
		var b = document.querySelector('#sidebar button[aria-label="Menu do usuário"], #sidebar button[aria-label="User Menu"]');
		var n = b && b.querySelector('div.truncate');
		if (!n) return;
		var t = n.textContent.trim();
		if (t.indexOf(' ') > 0) { nomeConta = t; n.textContent = t.split(/\s+/)[0]; n.title = nomeConta; }
	}

	/* ------------------------------------------------------------ ciclo */
	function emAuth() { return UI.onAuth ? UI.onAuth() : /^\/auth/.test(location.pathname); }

	function tick() {
		if (!document.body) return;
		if (emAuth()) {
			document.body.classList.remove('nous-pn-on', 'nous-pn-fixo');
			if (el) el.classList.add('nous-pn-off');
			if (alca) alca.classList.add('nous-pn-off');
			return;
		}
		build();
		document.body.classList.add('nous-pn-on');
		if (aberto === null) estadoInicial();
		else {
			/* volta da tela /auth (entrada automatica) com o estado de antes */
			el.classList.toggle('nous-pn-off', !aberto);
			alca.classList.toggle('nous-pn-off', aberto);
			document.body.classList.toggle('nous-pn-fixo', aberto && largo());
		}
		marcarConteudo();
		pintarPrivada();
		pintarFerr();
		estrela();
		primeiroNome();
	}

	var largoAntes = null;
	window.addEventListener('resize', function () {
		var l = largo();
		if (l === largoAntes || !el) return;
		largoAntes = l;
		abrir(l && ler('nous-pn', '1') !== '0');
	});
	new MutationObserver(function () { pintarTema(); }).observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

	window.NousPainel = { abrir: function () { if (el) abrir(true, true); }, recarregar: carregarListas };

	function start() {
		injectStyle();
		largoAntes = largo();
		tick();
		setInterval(tick, 700);
		atualizarStats();
		setInterval(atualizarStats, 4000);
		setInterval(function () { if (aberto) carregarListas(); }, 60000);
		setTimeout(carregarPadrao, 1500);
		window.addEventListener('focus', function () { if (aberto) carregarListas(); });
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
