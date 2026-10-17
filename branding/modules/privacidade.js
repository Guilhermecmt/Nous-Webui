/* =====================================================================
   Nous - Dados sensiveis borrados na tela (v2.8). CPF, cartao, senhas e chaves
   de API (sk-..., ghp_..., nvapi-...) aparecem borrados nas conversas; um
   clique revela. Usa a API de destaque do CSS (::highlight): o texto da
   pagina NAO e' alterado (o Svelte continua dono dele) e copiar ainda funciona.
   Liga/desliga em Recursos > Diagnostico. E-mails ficam visiveis por padrao.
   ===================================================================== */
(function () {
	'use strict';

	if (!window.CSS || !CSS.highlights || typeof Highlight === 'undefined') return; /* navegador antigo */

	var PATS = [
		/\b\d{3}\.\d{3}\.\d{3}-\d{2}\b/g,                                         // CPF
		/\b(?:\d{4}[ -]){3}\d{4}\b|\b\d{16}\b/g,                                  // cartao (Luhn abaixo)
		/\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35}|xox[abpr]-[A-Za-z0-9-]{10,}|nvapi-[A-Za-z0-9_-]{20,}|sk-ant-[A-Za-z0-9_-]{20,})\b/g,
		/\b(?:senha|password|pwd|pin)\s*[:=]\s*\S{4,}/gi
	];
	var EMAIL = /\b[\w.+-]+@[\w-]+\.[\w.-]+\b/g;
	var revealed = {};  /* "texto encontrado" -> revelado */

	function on() { try { return localStorage.getItem('nous-privacy') !== '0'; } catch (e) { return true; } }
	function emails() { try { return localStorage.getItem('nous-privacy-email') === '1'; } catch (e) { return false; } }

	function luhn(s) {
		var d = s.replace(/\D/g, ''), sum = 0, alt = false;
		for (var i = d.length - 1; i >= 0; i--) {
			var n = +d[i];
			if (alt) { n *= 2; if (n > 9) n -= 9; }
			sum += n; alt = !alt;
		}
		return d.length >= 13 && sum % 10 === 0;
	}

	function injectStyle() {
		if (document.getElementById('nous-priv-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-priv-style';
		st.textContent = '::highlight(nous-blur){color:transparent;text-shadow:0 0 8px rgba(160,160,160,.95)}';
		document.head.appendChild(st);
	}

	var ranges = [];
	function scan() {
		if (!on()) { CSS.highlights.delete('nous-blur'); ranges = []; return; }
		var out = [];
		document.querySelectorAll('[id^="message-"]').forEach(function (msg) {
			var w = document.createTreeWalker(msg, NodeFilter.SHOW_TEXT);
			var node;
			while ((node = w.nextNode())) {
				var t = node.data;
				if (t.length < 4 || node.parentElement.closest('textarea,input,#chat-input')) continue;
				var pats = emails() ? PATS.concat([EMAIL]) : PATS;
				pats.forEach(function (re) {
					re.lastIndex = 0;
					var m;
					while ((m = re.exec(t))) {
						if (re === PATS[1] && !luhn(m[0])) continue;
						if (revealed[m[0]]) continue;
						var r = new Range();
						r.setStart(node, m.index);
						r.setEnd(node, m.index + m[0].length);
						r.nousText = m[0];
						out.push(r);
					}
				});
			}
		});
		ranges = out;
		CSS.highlights.set('nous-blur', new Highlight(...out));
	}

	/* clique em cima do borrado revela aquele trecho */
	document.addEventListener('click', function (e) {
		if (!ranges.length) return;
		for (var i = 0; i < ranges.length; i++) {
			var rects = ranges[i].getClientRects();
			for (var j = 0; j < rects.length; j++) {
				var b = rects[j];
				if (e.clientX >= b.left && e.clientX <= b.right && e.clientY >= b.top && e.clientY <= b.bottom) {
					revealed[ranges[i].nousText] = 1;
					scan();
					return;
				}
			}
		}
	}, true);

	window.NousPrivacy = { rescan: scan };

	function start() {
		injectStyle();
		setInterval(scan, 1500);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
