/* =====================================================================
   Nous - Botoes nas respostas (v2.8). Os filtros do Nous terminam algumas
   respostas com marcadores:
     ⟦opcao:Rotulo|texto⟧  botao que envia "texto" no chat (sem | = o proprio rotulo)
     ⟦abrir:agenda⟧        abre um painel (agenda, email, habilidades, relatorios,
                           editor, pdf, loja, memoria)
     ⟦tema:claro⟧          muda o tema
     ⟦acao:liberar⟧        descarrega os modelos (libera a placa de video)
   Este modulo esconde o paragrafo dos marcadores e poe botoes ao lado (sem
   reescrever o texto que o Svelte controla). abrir/tema/acao rodam sozinhos
   so' na resposta NOVA (nunca ao reabrir uma conversa antiga).
   ===================================================================== */
(function () {
	'use strict';

	var MON = window.NousUrl(8990);
	var RE = /⟦(opcao|abrir|tema|acao):([^⟧]{1,300})⟧/g;
	var seen = {};   /* "msgid|marcador" ja' visto (nao roda de novo) */
	/* Resposta "nova" = a ultima, vista SEM marcador antes (os filtros poem o
	 * marcador no fim, depois do texto). Conversa antiga aberta pela barra
	 * lateral ja' chega com o marcador: nao dispara nada sozinha. */
	var fresh = {};

	var ABRIR = {
		agenda: function () { if (window.NousAgenda) window.NousAgenda.open('hoje'); },
		email: function () { if (window.NousEmail) window.NousEmail.open(); },
		habilidades: function () { if (window.NousSkills) window.NousSkills.open(); },
		relatorios: function () { if (window.NousReports) window.NousReports.open(); },
		editor: function () { if (window.NousEditor) window.NousEditor.open(); },
		pdf: function () { if (window.NousPdf) window.NousPdf.open(); },
		documentos: function () { if (window.NousDocs) window.NousDocs.open(); },
		codigo: function () { if (window.NousCode) window.NousCode.open(); },
		loja: function () { if (window.NousUI && window.NousUI.openStore) window.NousUI.openStore(); },
		memoria: function () { if (window.NousUI && window.NousUI.openMemory) window.NousUI.openMemory(); },
		diagnostico: function () { if (window.NousDiag) window.NousDiag.open(); },
		galeria: function () { if (window.NousUI && window.NousUI.openGallery) window.NousUI.openGallery(); },
		comparar: function () { if (window.NousCompare) window.NousCompare.open('comparar'); },
		placar: function () { if (window.NousCompare) window.NousCompare.open('placar'); }
	};
	var ROTULO = { agenda: '📅 Abrir Agenda', email: '✉ Abrir Email', habilidades: '🧠 Abrir Habilidades',
		relatorios: '🔎 Abrir Relatorios', editor: '🖼 Abrir Editor', pdf: '📄 Abrir Formularios', documentos: '📝 Abrir Documentos', codigo: '⌨ Abrir o Codigo',
		loja: '⬇ Abrir Loja de modelos', memoria: '💭 O que o Nous sabe', diagnostico: '🩺 Abrir Diagnostico',
		galeria: '🖼 Abrir Galeria', comparar: '⚖ Comparar modelos', placar: '🏆 Ver o placar' };

	function injectStyle() {
		if (document.getElementById('nous-act-style')) return;
		var g = 'rgba(200,150,46,';
		var st = document.createElement('style');
		st.id = 'nous-act-style';
		st.textContent =
			'.nous-act-row{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 4px}' +
			'.nous-act-btn{padding:6px 12px;border:1px solid ' + g + '.5);border-radius:99px;cursor:pointer;' +
			'background:' + g + '.12);color:#c8962e;font:600 12px Inter,system-ui,sans-serif;text-align:left;max-width:100%}' +
			'.dark .nous-act-btn{color:#e7c069}.nous-act-btn:hover{background:' + g + '.26)}' +
			'.nous-act-btn:disabled{opacity:.45;cursor:default}';
		document.head.appendChild(st);
	}

	/* Escreve no campo de mensagem e envia, como se o usuario tivesse digitado. */
	function sendChat(text) {
		var box = document.getElementById('chat-input');
		if (!box) return false;
		box.focus();
		if (box.tagName === 'TEXTAREA') {
			box.value = text;
			box.dispatchEvent(new Event('input', { bubbles: true }));
		} else {
			document.execCommand('selectAll', false, null);
			document.execCommand('insertText', false, text);
		}
		var tries = 0;
		(function click() {
			var b = document.getElementById('send-message-button');
			if (b && !b.disabled) { b.click(); return; }
			if (++tries < 20) setTimeout(click, 100);
		})();
		return true;
	}

	function run(kind, value) {
		if (kind === 'abrir' && ABRIR[value]) ABRIR[value]();
		else if (kind === 'tema' && window.NousUI && window.NousUI.setTheme) window.NousUI.setTheme(value === 'claro' ? 'light' : 'dark');
		else if (kind === 'acao' && value === 'liberar') fetch(MON + '/unload', { method: 'POST' }).catch(function () {});
	}

	function label(kind, value) {
		if (kind === 'opcao') return value.split('|')[0];
		if (kind === 'abrir') return ROTULO[value] || 'Abrir';
		if (kind === 'tema') return value === 'claro' ? '☀ Tema claro' : '🌙 Tema escuro';
		if (kind === 'acao') return '⏏ Liberar a placa de video';
		return value;
	}

	function lastAssistantId() {
		var all = document.querySelectorAll('[id^="message-"]');
		for (var i = all.length - 1; i >= 0; i--) {
			if (all[i].querySelector('.markdown-prose')) return all[i].id;
		}
		return null;
	}

	function scan() {
		var lastId = lastAssistantId();
		if (lastId && fresh[lastId] === undefined) {
			var el = document.getElementById(lastId);
			fresh[lastId] = !!el && el.textContent.indexOf('⟦') < 0;
		}
		document.querySelectorAll('.markdown-prose p, .markdown-prose li').forEach(function (p) {
			if (p.dataset.nousAct === '1' || p.textContent.indexOf('⟦') < 0) return;
			var txt = p.textContent, found = [], m;
			RE.lastIndex = 0;
			while ((m = RE.exec(txt))) found.push([m[1], m[2]]);
			if (!found.length) return;
			// so' esconde o paragrafo se ele for SO' marcadores (texto normal fica)
			if (txt.replace(RE, '').trim()) return;
			var msg = p.closest('[id^="message-"]'), msgId = msg ? msg.id : '?';
			p.dataset.nousAct = '1';
			p.style.display = 'none';
			// o Svelte pode redesenhar o paragrafo: nao duplica a fileira
			var sig = msgId + '|' + txt.trim();
			var old = (msg || document).querySelectorAll('.nous-act-row');
			for (var i = 0; i < old.length; i++) if (old[i].dataset.sig === sig) old[i].remove();
			var row = document.createElement('div');
			row.className = 'nous-act-row';
			row.dataset.sig = sig;
			found.forEach(function (f) {
				var kind = f[0], value = f[1].trim(), key = msgId + '|' + kind + ':' + value;
				var b = document.createElement('button');
				b.type = 'button';
				b.className = 'nous-act-btn';
				b.textContent = label(kind, value);
				b.addEventListener('click', function () {
					if (kind === 'opcao') {
						var parts = value.split('|');
						if (sendChat((parts[1] || parts[0]).trim())) row.querySelectorAll('button').forEach(function (x) { x.disabled = true; });
					} else run(kind, value);
				});
				row.appendChild(b);
				// resposta nova e' a ultima: executa a acao uma vez so'
				if (kind !== 'opcao' && !seen[key] && fresh[msgId] && msgId === lastId) {
					setTimeout(function () { run(kind, value); }, 300);
				}
				seen[key] = 1;
			});
			p.parentNode.insertBefore(row, p.nextSibling);
		});
	}

	function start() {
		injectStyle();
		window.NousActs = { sendChat: sendChat };  /* respostas.js: "Mais curto", "Mais simples" */
		setInterval(scan, 700);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
