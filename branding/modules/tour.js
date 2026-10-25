/* =====================================================================
   Nous - Dicas de primeiro uso (v2.8) e passeio pela tela (v2.11). Na primeira
   vez que a tela inicial ou cada painel aparece, um destaque dourado + um cartao
   explicam o essencial (2 a 7 passos). Uma fila so': uma dica nunca atropela outra
   (nem as licoes e os avisos de primeiros.js, que esperam o passeio e vice-versa).
   Tela estreita (celular): so' as dicas com passos "movel".
   O progresso ("ja' vi", "Pular dicas") fica no servidor (_progresso.js), por pessoa.
   "Pular dicas" desliga todas; o botao "?" (primeiros.js) e Diagnostico > "Ver as
   dicas de novo" religam, e NousTour.run('home' | 'anexo') repete uma sob demanda.
   ===================================================================== */
(function () {
	'use strict';

	var TOURS = {
		/* o passeio pela tela: vai na frente das dicas dos paineis (ordem) */
		home: { ordem: 1,
			when: function () { return !!document.getElementById('chat-input') && !anyPanel() && modeloPronto(); },
			steps: [
				['#message-input-container, #chat-input', 'Converse aqui, em português. Além de perguntas, você pode pedir: "me lembre de pagar a luz sexta às 9h", "manda um e-mail pra Maria..." ou colar a foto de um boleto.'],
				['#input-menu-button', 'O + serve para mandar uma foto ou um documento: escolha o arquivo e depois pergunte sobre ele. Também dá para arrastar o arquivo para a conversa.'],
				['#model-selector-model-button', 'Aqui você escolhe qual modelo, o "cérebro" da IA, responde. Cada modelo que você baixar aparece nesta lista.'],
				['#sidebar-new-chat-button', 'O lápis começa uma conversa nova. As conversas antigas ficam guardadas na barra lateral e você volta a elas quando quiser.'],
				['#nous-pn-head', 'Este é o seu Nous. O anel em volta da coruja mostra quanto da placa de vídeo está em uso; fica dourado quando um modelo está pronto para responder.'],
				['#nous-pn-mem', 'Aqui fica o que o Nous sabe sobre você. Veja, corrija ou apague quando quiser.'],
				['#nous-pn-ferr', 'Agenda, Documentos, E-mail, Editor de fotos e o resto: tudo a um clique.']],
			movel: [
				['#message-input-container, #chat-input', 'Converse aqui, em português. Além de perguntas, você pode pedir: "me lembre de pagar a luz sexta às 9h" ou colar a foto de um boleto.'],
				['#input-menu-button', 'O + serve para mandar uma foto ou um documento: escolha o arquivo e depois pergunte sobre ele.'],
				['#model-selector-model-button', 'Aqui você escolhe qual modelo, o "cérebro" da IA, responde.'],
				['#sidebar-toggle-button', 'Este botão abre a barra lateral: as conversas antigas e a conversa nova.'],
				['#nous-pn-alca', 'A coruja abre o seu Nous: o que ele sabe sobre você, a Agenda, o E-mail, os Documentos e as outras ferramentas.']] },
		/* so' sob demanda ("?" > Como mandar foto e documento) */
		anexo: { manual: true,
			when: function () { return !!document.getElementById('chat-input') && !anyPanel(); },
			steps: [['#input-menu-button', 'Clique no + e escolha o arquivo: uma foto ou um documento (PDF, Word, texto). Depois pergunte sobre ele. Também dá para arrastar o arquivo para a conversa ou colar uma imagem com Ctrl+V. Fotos só funcionam com um modelo que entende imagens.']],
			movel: [['#input-menu-button', 'Toque no + e escolha o arquivo: uma foto, um documento (PDF, Word, texto) ou a câmera. Depois pergunte sobre ele. Fotos só funcionam com um modelo que entende imagens.']] },
		agenda: { when: function () { return visible('nous-ag-ov'); },
			steps: [
				['#nous-ag-tabs', 'Hoje mostra o que vem por aí. Notas guarda listas e lembretes. Calendário traz o Google Agenda. Tarefas faz o Nous trabalhar sozinho no horário.'],
				['#nous-ag-gear', 'Quer o aviso no celular ou no e-mail também? É aqui.']] },
		email: { when: function () { return visible('nous-em-ov'); },
			steps: [
				['#nous-em-tabs', 'Rascunhos guarda o que o chat escreveu esperando o seu OK: o Nous nunca envia sozinho. Newsletters ajuda a sair de listas; Contatos são aprendidos dos seus e-mails.']] },
		skills: { when: function () { return visible('nous-sk-ov'); },
			steps: [['#nous-sk-body', 'Depois de acertar algo numa conversa, diga "aprenda isso": o Nous guarda o passo a passo e usa sozinho da próxima vez. Ou ensine o seu jeito de escrever.']] },
		pdf: { when: function () { return visible('nous-pdf-ov'); },
			steps: [['#nous-pdf-body', 'Escolha um PDF preenchível: o Nous mostra os campos, sugere o que já sabe de você e assina com a sua assinatura. Nada sai do computador.']] },
		editor: { when: function () { return visible('nous-ed-ov'); },
			steps: [['#nous-ed-say', 'Escreva o que quer, do seu jeito: "tira o fundo, deixa mais claro e corta quadrado".'],
				['#nous-ed-side', 'Ou faça na mão: corte, gire, ajuste luz e cor e remova o fundo com IA local. Ctrl+Z desfaz. Também dá para colar uma imagem com Ctrl+V.']] },
		comparar: { when: function () { return visible('nous-cp-ov'); },
			steps: [['#nous-cp-body', 'Faça a mesma pergunta para até 4 modelos e vote na melhor resposta. O placar mostra qual combina mais com você e qual é mais rápido nesta máquina.']] },
		documentos: { when: function () { return visible('nous-dc-ov'); },
			steps: [['#nous-dc-text', 'Escreva aqui, ou cole suas anotações. Salva sozinho e dá para baixar em Word ou PDF.'],
				['#nous-dc-chips', 'Peça para a IA corrigir, deixar formal, encurtar ou transformar tópicos em texto. Ela só sugere: cada mudança aparece riscada e você aceita ou recusa.']] },
		galeria: { when: function () { return visible('nous-gal-ov'); },
			steps: [['#nous-gal-filter', 'Marque as favoritas com ★ e organize em álbuns com 📁. O ✎ abre a imagem no Editor.']] }
	};
	var active = null, atual = null, forcado = false;   /* atual = {k, i}: o passo na tela, para o destaque acompanhar o layout */

	function visible(id) { var e = document.getElementById(id); return !!e && !e.classList.contains('nous-hidden'); }
	/* sem modelo instalado o assistente de primeiro uso vem antes do passeio (primeiros.js sabe) */
	function modeloPronto() { return !window.NousPrimeiros || window.NousPrimeiros.modeloPronto(); }
	function estreita() { return window.innerWidth < 760; }
	function prog() { return window.NousProgresso; }
	/* algum painel do Nous (ou o assistente de primeiro uso) aberto? */
	function anyPanel() {
		return ['nous-wiz-ov', 'nous-ag-ov', 'nous-em-ov', 'nous-sk-ov', 'nous-rp-ov', 'nous-pdf-ov', 'nous-ed-ov',
			'nous-store-ov', 'nous-dg-ov', 'nous-voice-ov', 'nous-cp-ov', 'nous-gal-ov', 'nous-dc-ov', 'nous-pp-ov'].some(visible) || visible('nous-mem-panel');
	}
	function passos(k) { var t = TOURS[k]; return estreita() && t.movel ? t.movel : t.steps; }
	/* o elemento existe e esta' na tela (a gaveta fechada do painel ainda existe, mas fora da vista) */
	function achar(sel) {
		var els = document.querySelectorAll(sel);   /* ha' ids repetidos no Open WebUI (barra recolhida/aberta): vale o que aparece */
		for (var i = 0; i < els.length; i++) {
			var r = els[i].getBoundingClientRect();
			if (r.width > 0 && r.height > 0 && r.right > 0 && r.left < window.innerWidth && r.bottom > 0 && r.top < window.innerHeight) return els[i];
		}
		return null;
	}
	function hide() {
		['nous-tour-halo', 'nous-tour-card'].forEach(function (id) { var e = document.getElementById(id); if (e) e.remove(); });
	}
	/* "ja' vi" so' vale depois que o servidor respondeu e se soube se a pessoa ja' usava o Nous
	   (senao reabriria o que ela ja' viu, principalmente no celular) */
	function pronto() { var p = prog(); return !!p && p.carregado() && p.veterano() !== null; }
	function done(k) { var p = prog(); return !pronto() || p.visto(k) || p.pular(); }
	function mark(k) { var p = prog(); if (p) p.marcar(k); }
	function deste(k) {   /* esta dica serve para esta tela? (celular: so' as que tem passos "movel") */
		return !estreita() || !!TOURS[k].movel;
	}

	function injectStyle() {
		if (document.getElementById('nous-tour-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-tour-style';
		st.textContent =
			'#nous-tour-halo{position:fixed;z-index:10005;border:2px solid #e7c069;border-radius:12px;pointer-events:none;' +
			'box-shadow:0 0 0 4px rgba(200,150,46,.25),0 0 0 9999px rgba(0,0,0,.35);transition:all .25s}' +
			'#nous-tour-card{position:fixed;z-index:10006;width:300px;max-width:88vw;padding:12px 14px;border-radius:12px;' +
			'background:rgba(18,18,22,.98);border:1px solid rgba(200,150,46,.6);color:#eee;font:13px/1.5 Inter,system-ui,sans-serif;' +
			'box-shadow:0 12px 32px rgba(0,0,0,.5)}' +
			'#nous-tour-card b{color:#e7c069}#nous-tour-card .r{display:flex;gap:6px;margin-top:10px;align-items:center}' +
			'#nous-tour-card .r span{flex:1;font-size:11px;opacity:.65}' +
			'#nous-tour-card button{padding:6px 12px;border-radius:8px;border:1px solid rgba(200,150,46,.5);cursor:pointer;' +
			'background:rgba(200,150,46,.2);color:#e7c069;font-weight:600;font-size:12px}' +
			'#nous-tour-card button.g{background:transparent;color:#aaa;border-color:rgba(255,255,255,.2)}' +
			'#nous-tour-card button:focus-visible{outline:2px solid #e7c069;outline-offset:2px}' +
			'@media (max-width:767px){#nous-tour-card button{padding:9px 14px;font-size:13px}}' +
			'@media (prefers-reduced-motion:reduce){#nous-tour-halo{transition:none}}';
		document.head.appendChild(st);
	}

	function end(k) {
		mark(k);
		active = null; atual = null; forcado = false;
		hide();
	}

	function show(k, i) {
		var steps = passos(k);
		var el = null;
		while (i < steps.length && !(el = achar(steps[i][0]))) i++;
		if (!el) { end(k); return; }
		atual = { k: k, i: i };
		var r = el.getBoundingClientRect();
		var halo = document.getElementById('nous-tour-halo') || document.body.appendChild(Object.assign(document.createElement('div'), { id: 'nous-tour-halo' }));
		halo.style.left = (r.left - 6) + 'px'; halo.style.top = (r.top - 6) + 'px';
		halo.style.width = (r.width + 12) + 'px'; halo.style.height = (r.height + 12) + 'px';
		var card = document.getElementById('nous-tour-card') || document.body.appendChild(Object.assign(document.createElement('div'), { id: 'nous-tour-card' }));
		card.setAttribute('role', 'dialog');
		card.setAttribute('aria-label', 'Dica de primeiro uso');
		card.setAttribute('aria-live', 'polite');
		/* os passos que nao estao na tela nao contam no "1 de N" */
		var total = steps.filter(function (s) { return !!achar(s[0]); }).length;
		var n = steps.slice(0, i + 1).filter(function (s) { return !!achar(s[0]); }).length;
		var proximo = i + 1; while (proximo < steps.length && !achar(steps[proximo][0])) proximo++;
		var last = proximo >= steps.length;
		card.innerHTML = '<div>' + steps[i][1].replace(/"([^"]+)"/g, '<b>"$1"</b>') + '</div><div class="r"><span>' + n + ' de ' + total + '</span>' +
			'<button class="g" type="button" data-x="off">' + (forcado ? 'Fechar' : 'Pular dicas') + '</button><button type="button" data-x="next">' + (last ? 'Entendi' : 'Próximo') + '</button></div>';
		posiciona(r, card);
		card.querySelector('[data-x="next"]').onclick = function () { if (last) end(k); else show(k, proximo); };
		card.querySelector('[data-x="off"]').onclick = function () {
			if (!forcado && prog()) prog().setPular(true);
			end(k);
		};
		/* teclado: o foco vai para o botao (Enter avanca), Esc fecha */
		card.querySelector('[data-x="next"]').focus({ preventScroll: true });
	}

	function posiciona(r, card) {
		var cw = Math.min(300, window.innerWidth * 0.88), ch = card.offsetHeight || 120;
		card.style.top = (r.bottom + 14 + ch < window.innerHeight ? r.bottom + 14 : Math.max(10, r.top - ch - 14)) + 'px';
		card.style.left = Math.min(window.innerWidth - cw - 12, Math.max(12, r.left)) + 'px';
	}

	/* a barra lateral e o painel abrem e fecham com animacao: o destaque segue o elemento */
	function acompanhar() {
		if (!active || !atual) return;
		var el = achar(passos(atual.k)[atual.i][0]);
		var halo = document.getElementById('nous-tour-halo'), card = document.getElementById('nous-tour-card');
		if (!el || !halo || !card) return;
		var r = el.getBoundingClientRect();
		halo.style.left = (r.left - 6) + 'px'; halo.style.top = (r.top - 6) + 'px';
		halo.style.width = (r.width + 12) + 'px'; halo.style.height = (r.height + 12) + 'px';
		posiciona(r, card);
	}

	/* ha' dica automatica esperando a vez? (os cartoes da primeira conversa aguardam) */
	function pendente() {
		if (!pronto() || prog().pular() || (window.NousUI && window.NousUI.onAuth && window.NousUI.onAuth())) return false;
		for (var k in TOURS) if (!TOURS[k].manual && deste(k) && !done(k) && TOURS[k].when()) return true;
		return false;
	}

	function tick() {
		// o contexto da dica sumiu (abriu um painel por cima, fechou o painel): recua
		// sem marcar como vista; ela volta quando o contexto voltar
		if (active && !TOURS[active].when()) { hide(); active = null; atual = null; forcado = false; return; }
		if (active || !pronto() || (window.NousUI && window.NousUI.onAuth && window.NousUI.onAuth())) return;
		if (window.NousPrimeiros && window.NousPrimeiros.ocupado()) return;   /* aviso da primeira conversa na tela */
		var ordem = Object.keys(TOURS).sort(function (a, b) { return (TOURS[b].ordem || 0) - (TOURS[a].ordem || 0); });
		for (var j = 0; j < ordem.length; j++) {
			var k = ordem[j];
			if (!TOURS[k].manual && deste(k) && !done(k) && TOURS[k].when()) {
				active = k;
				setTimeout(function () { if (active) show(active, 0); }, 600);  /* deixa o painel terminar de abrir */
				return;
			}
		}
	}

	window.NousTour = {
		/* passeio sob demanda (botao "?"): ignora o "ja' vi" e o "Pular dicas" */
		run: function (k) {
			if (!TOURS[k] || !TOURS[k].when()) return false;
			hide();
			active = k; forcado = true;
			show(k, 0);
			return true;
		},
		ocupado: function () { return !!active; },
		pendente: pendente,
		/* "Ver as dicas de novo": volta tudo que aparece sozinho */
		reset: function () { if (prog()) prog().zerar(); }
	};

	function start() {
		injectStyle();
		setInterval(tick, 1500);
		setInterval(acompanhar, 300);
		document.addEventListener('keydown', function (e) {
			if (e.key === 'Escape' && active && document.getElementById('nous-tour-card')) { e.stopPropagation(); end(active); }
		}, true);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
