/* =====================================================================
   Nous - Dicas de primeiro uso (v2.8). Na primeira vez que a tela inicial ou
   cada painel aparece, um destaque dourado + um cartao explicam o essencial
   (2 a 3 passos). Uma fila so': uma dica nunca atropela outra. Nada no celular.
   "Pular dicas" desliga todas; Diagnostico > "Ver as dicas de novo" religa.
   ===================================================================== */
(function () {
	'use strict';

	var TOURS = {
		home: { when: function () { return !!document.getElementById('chat-input') && !!document.getElementById('nous-mon-body') && !anyPanel(); },
			steps: [
				['#chat-input', 'Converse aqui, em portugues. Alem de perguntas, voce pode pedir: "me lembre de pagar a luz sexta as 9h", "manda um e-mail pra Maria..." ou colar a foto de um boleto.'],
				['#nous-monitor', 'Este e\' o seu painel: quanto da placa de video esta em uso e os atalhos para Agenda, E-mail, Habilidades, Editor de fotos e mais.'],
				['#nous-mem-btn', 'Aqui fica o que o Nous sabe sobre voce. Veja, corrija ou apague quando quiser.']] },
		agenda: { when: function () { return visible('nous-ag-ov'); },
			steps: [
				['#nous-ag-tabs', 'Hoje mostra o que vem por ai. Notas guarda listas e lembretes. Calendario traz o Google Agenda. Tarefas faz o Nous trabalhar sozinho no horario.'],
				['#nous-ag-gear', 'Quer o aviso no celular ou no e-mail tambem? E\' aqui.']] },
		email: { when: function () { return visible('nous-em-ov'); },
			steps: [
				['#nous-em-tabs', 'Rascunhos guarda o que o chat escreveu esperando o seu OK: o Nous nunca envia sozinho. Newsletters ajuda a sair de listas; Contatos sao aprendidos dos seus e-mails.']] },
		skills: { when: function () { return visible('nous-sk-ov'); },
			steps: [['#nous-sk-body', 'Depois de acertar algo numa conversa, diga "aprenda isso": o Nous guarda o passo a passo e usa sozinho da proxima vez. Ou ensine o seu jeito de escrever.']] },
		pdf: { when: function () { return visible('nous-pdf-ov'); },
			steps: [['#nous-pdf-body', 'Escolha um PDF preenchivel: o Nous mostra os campos, sugere o que ja sabe de voce e assina com a sua assinatura. Nada sai do computador.']] },
		editor: { when: function () { return visible('nous-ed-ov'); },
			steps: [['#nous-ed-say', 'Escreva o que quer, do seu jeito: "tira o fundo, deixa mais claro e corta quadrado".'],
				['#nous-ed-side', 'Ou faca na mao: corte, gire, ajuste luz e cor e remova o fundo com IA local. Ctrl+Z desfaz. Tambem da para colar uma imagem com Ctrl+V.']] },
		comparar: { when: function () { return visible('nous-cp-ov'); },
			steps: [['#nous-cp-body', 'Faca a mesma pergunta para ate\' 4 modelos e vote na melhor resposta. O placar mostra qual combina mais com voce e qual e\' mais rapido nesta maquina.']] },
		documentos: { when: function () { return visible('nous-dc-ov'); },
			steps: [['#nous-dc-text', 'Escreva aqui, ou cole suas anotacoes. Salva sozinho e da para baixar em Word ou PDF.'],
				['#nous-dc-chips', 'Peca para a IA corrigir, deixar formal, encurtar ou transformar topicos em texto. Ela so\' sugere: cada mudanca aparece riscada e voce aceita ou recusa.']] },
		galeria: { when: function () { return visible('nous-gal-ov'); },
			steps: [['#nous-gal-filter', 'Marque as favoritas com ★ e organize em albuns com 📁. O ✎ abre a imagem no Editor.']] }
	};
	var active = null;

	function visible(id) { var e = document.getElementById(id); return !!e && !e.classList.contains('nous-hidden'); }
	/* algum painel do Nous (ou o assistente de primeiro uso) aberto? */
	function anyPanel() {
		return ['nous-wiz-ov', 'nous-ag-ov', 'nous-em-ov', 'nous-sk-ov', 'nous-rp-ov', 'nous-pdf-ov', 'nous-ed-ov',
			'nous-store-ov', 'nous-dg-ov', 'nous-voice-ov', 'nous-cp-ov', 'nous-gal-ov', 'nous-dc-ov'].some(visible) || visible('nous-mem-panel');
	}
	function hide() {
		['nous-tour-halo', 'nous-tour-card'].forEach(function (id) { var e = document.getElementById(id); if (e) e.remove(); });
	}
	function done(k) { try { return localStorage.getItem('nous-tour-' + k) === '1' || localStorage.getItem('nous-tour-off') === '1'; } catch (e) { return true; } }
	function mark(k) { try { localStorage.setItem('nous-tour-' + k, '1'); } catch (e) {} }

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
			'#nous-tour-card .r span{flex:1;font-size:11px;opacity:.55}' +
			'#nous-tour-card button{padding:5px 11px;border-radius:8px;border:1px solid rgba(200,150,46,.5);cursor:pointer;' +
			'background:rgba(200,150,46,.2);color:#e7c069;font-weight:600;font-size:12px}' +
			'#nous-tour-card button.g{background:transparent;color:#999;border-color:rgba(255,255,255,.15)}';
		document.head.appendChild(st);
	}

	function end(k) {
		mark(k);
		active = null;
		hide();
	}

	function show(k, i) {
		var steps = TOURS[k].steps;
		var el = null;
		while (i < steps.length && !(el = document.querySelector(steps[i][0]))) i++;
		if (!el) { end(k); return; }
		var r = el.getBoundingClientRect();
		var halo = document.getElementById('nous-tour-halo') || document.body.appendChild(Object.assign(document.createElement('div'), { id: 'nous-tour-halo' }));
		halo.style.left = (r.left - 6) + 'px'; halo.style.top = (r.top - 6) + 'px';
		halo.style.width = (r.width + 12) + 'px'; halo.style.height = (r.height + 12) + 'px';
		var card = document.getElementById('nous-tour-card') || document.body.appendChild(Object.assign(document.createElement('div'), { id: 'nous-tour-card' }));
		var last = i === steps.length - 1;
		card.innerHTML = '<div>' + steps[i][1].replace(/"([^"]+)"/g, '<b>"$1"</b>') + '</div><div class="r"><span>' + (i + 1) + ' de ' + steps.length + '</span>' +
			'<button class="g" type="button" data-x="off">Pular dicas</button><button type="button" data-x="next">' + (last ? 'Entendi' : 'Proximo') + '</button></div>';
		// cartao abaixo do elemento; se nao couber, acima
		var cw = 300, ch = card.offsetHeight || 120;
		var top = r.bottom + 14 + ch < window.innerHeight ? r.bottom + 14 : Math.max(10, r.top - ch - 14);
		card.style.top = top + 'px';
		card.style.left = Math.min(window.innerWidth - cw - 12, Math.max(12, r.left)) + 'px';
		card.querySelector('[data-x="next"]').onclick = function () { if (last) end(k); else show(k, i + 1); };
		card.querySelector('[data-x="off"]').onclick = function () { try { localStorage.setItem('nous-tour-off', '1'); } catch (e) {} end(k); };
	}

	function tick() {
		// o contexto da dica sumiu (abriu um painel por cima, fechou o painel): recua
		// sem marcar como vista; ela volta quando o contexto voltar
		if (active && !TOURS[active].when()) { hide(); active = null; return; }
		if (active || window.innerWidth < 760 || (window.NousUI && window.NousUI.onAuth && window.NousUI.onAuth())) return;
		for (var k in TOURS) {
			if (!done(k) && TOURS[k].when()) {
				active = k;
				setTimeout(function () { if (active) show(active, 0); }, 600);  /* deixa o painel terminar de abrir */
				return;
			}
		}
	}

	window.NousTour = {
		reset: function () { try { Object.keys(TOURS).forEach(function (k) { localStorage.removeItem('nous-tour-' + k); }); localStorage.removeItem('nous-tour-off'); } catch (e) {} }
	};

	function start() {
		injectStyle();
		setInterval(tick, 1500);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
