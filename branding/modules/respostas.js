/* =====================================================================
   Nous - Botoes nas respostas (v2.9). Na fileira de botoes de cada resposta
   (copiar, regenerar...) o Nous poe tres atalhos:
     ✂ Mais curto · 🙂 Mais simples   pedem a reescrita no chat
     📝 Documento                     abre a resposta nos Documentos
   Na ultima resposta ficam sempre visiveis; nas outras, ao passar o mouse
   (igual aos botoes do Open WebUI).
   ===================================================================== */
(function () {
	'use strict';

	var PEDIDOS = {
		curto: ['Reescreva a sua ultima resposta de forma mais curta e direta, mantendo o essencial.',
			'Reescreva este texto de forma mais curta e direta, mantendo o essencial:'],
		simples: ['Explique a sua ultima resposta de um jeito mais simples, com palavras do dia a dia, como para alguem que nao conhece o assunto.',
			'Explique este texto de um jeito mais simples, com palavras do dia a dia, como para alguem que nao conhece o assunto:']
	};

	function injectStyle() {
		if (document.getElementById('nous-rw-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-rw-style';
		st.textContent =
			'.nous-rw{display:inline-flex;gap:2px;align-self:center;margin-left:4px;transition:opacity .15s}' +
			'.nous-rw.nous-rw-hover{opacity:0}[id^="message-"]:hover .nous-rw.nous-rw-hover{opacity:1}' +
			'.nous-rw button{padding:3px 7px;border:none;border-radius:8px;background:none;cursor:pointer;' +
			'font:500 11.5px Inter,system-ui,sans-serif;color:#8a6414;white-space:nowrap}' +
			'.dark .nous-rw button{color:#c8962e}.nous-rw button:hover{background:rgba(200,150,46,.14)}';
		document.head.appendChild(st);
	}

	function ultimaResposta() {
		var all = document.querySelectorAll('.copy-response-button');
		return all.length ? all[all.length - 1].closest('[id^="message-"]') : null;
	}

	/* Markdown original da resposta (pela API do Open WebUI); sem ela, o texto da tela. */
	function conteudo(msgEl, cb) {
		var id = msgEl.id.replace(/^message-/, ''), m = location.pathname.match(/\/c\/([^/?#]+)/), token = '';
		try { token = localStorage.getItem('token') || ''; } catch (e) {}
		function tela() {
			var p = msgEl.querySelector('.markdown-prose');
			cb(p ? markdownDaTela(p) : '');
		}
		if (!m || !token) { tela(); return; }
		fetch('/api/v1/chats/' + m[1], { headers: { Authorization: 'Bearer ' + token } })
			.then(function (r) { return r.json(); }).then(function (c) {
				var msg = c && c.chat && c.chat.history && c.chat.history.messages && c.chat.history.messages[id];
				var txt = msg && typeof msg.content === 'string' ? msg.content : '';
				// tira o pensamento e os marcadores de botao dos filtros do Nous
				txt = txt.replace(/<details[^>]*type="reasoning"[\s\S]*?<\/details>/g, '').replace(/⟦[^⟧]{1,300}⟧/g, '').trim();
				if (txt) cb(txt); else tela();
			}).catch(tela);
	}

	/* Sem a API: refaz um Markdown simples a partir da tela, bloco por bloco
	 * (titulos, paragrafos, listas, citacoes, codigo). */
	function markdownDaTela(root) {
		var out = [];
		(function walk(el) {
			Array.prototype.forEach.call(el.children, function (c) {
				if (c.classList.contains('nous-act-row') || c.dataset.nousAct === '1') return;
				var tag = c.tagName, txt = (c.textContent || '').replace(/\s+/g, ' ').trim();
				if (/^H[1-6]$/.test(tag)) out.push('#'.repeat(Math.min(3, +tag[1])) + ' ' + txt);
				else if (tag === 'P') { if (txt) out.push(txt); }
				else if (tag === 'UL' || tag === 'OL') {
					out.push(Array.prototype.map.call(c.querySelectorAll(':scope > li'), function (li, i) {
						return (tag === 'OL' ? (i + 1) + '. ' : '- ') + li.textContent.replace(/\s+/g, ' ').trim();
					}).join('\n'));
				}
				else if (tag === 'BLOCKQUOTE') out.push('> ' + txt);
				else if (tag === 'PRE') out.push('```\n' + c.textContent.replace(/\n$/, '') + '\n```');
				else if (tag === 'TABLE' || tag === 'HR') out.push(tag === 'HR' ? '---' : c.innerText);
				else walk(c);
			});
		})(root);
		return out.join('\n\n').trim();
	}

	function titulo(texto) {
		var h = texto.match(/^#{1,3}\s+(.+)$/m);
		var t = h ? h[1] : texto.split('\n')[0];
		t = t.replace(/[*_`#>]/g, '').trim();
		return t.length > 60 ? t.slice(0, 57).replace(/\s+\S*$/, '') + '...' : t;
	}

	function acao(tipo, msgEl) {
		if (tipo === 'doc') {
			conteudo(msgEl, function (txt) {
				if (txt && window.NousDocs) window.NousDocs.novo(titulo(txt), txt);
			});
			return;
		}
		var send = window.NousActs && window.NousActs.sendChat;
		if (!send) return;
		if (msgEl === ultimaResposta()) { send(PEDIDOS[tipo][0]); return; }
		conteudo(msgEl, function (txt) { if (txt) send(PEDIDOS[tipo][1] + '\n\n' + txt); });
	}

	function scan() {
		var ultima = ultimaResposta();
		document.querySelectorAll('.copy-response-button').forEach(function (btn) {
			var msg = btn.closest('[id^="message-"]');
			if (!msg) return;
			// o botao vem dentro do Tooltip: a fileira e' o pai do Tooltip
			var row = btn.parentElement;
			if (row && row.children.length === 1 && row.parentElement) row = row.parentElement;
			if (!row) return;
			var box = row.querySelector(':scope > .nous-rw');
			if (!box) {
				box = document.createElement('span');
				box.className = 'nous-rw';
				box.innerHTML = '<button type="button" data-rw="curto" title="Pedir uma versao mais curta">✂ Mais curto</button>' +
					'<button type="button" data-rw="simples" title="Pedir uma explicacao mais simples">🙂 Mais simples</button>' +
					'<button type="button" data-rw="doc" title="Abrir esta resposta nos Documentos para editar e baixar em Word/PDF">📝 Documento</button>';
				box.addEventListener('click', function (e) {
					var b = e.target.closest('[data-rw]');
					if (b) acao(b.getAttribute('data-rw'), msg);
				});
				row.appendChild(box);
			}
			box.classList.toggle('nous-rw-hover', msg !== ultima);
		});
	}

	function start() {
		injectStyle();
		setInterval(scan, 900);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
