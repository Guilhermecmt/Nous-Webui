/* =====================================================================
   Nous - Diagnostico (v2.8). "O que esta funcionando?": cada peca do Nous
   (motor de IA, modelos, servicos, busca na web, disco) com ✓/✗ e o que fazer.
   Tambem guarda as opcoes de privacidade na tela e "ver as dicas de novo".
   ===================================================================== */
(function () {
	'use strict';

	var MON = 'http://127.0.0.1:8990';
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var ov = null;

	function injectStyle() {
		if (document.getElementById('nous-dg-style')) return;
		var g = 'rgba(200,150,46,';
		var st = document.createElement('style');
		st.id = 'nous-dg-style';
		st.textContent =
			'#nous-diag-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);border-radius:8px;' +
			'cursor:pointer;background:transparent;color:#e7c069;font-weight:600;font-size:12px}#nous-diag-open:hover{background:' + g + '.12)}' +
			'#nous-dg-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);display:flex;align-items:center;' +
			'justify-content:center;backdrop-filter:blur(3px)}#nous-dg-ov.nous-hidden{display:none}' +
			'#nous-dg{width:480px;max-width:95vw;max-height:84vh;overflow-y:auto;font-family:Inter,system-ui,sans-serif;font-size:13px;' +
			'color:#eee;background:rgba(18,18,22,.97);border:1px solid ' + g + '.4);border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.55)}' +
			'#nous-dg-head{display:flex;align-items:center;padding:14px 16px 10px;border-bottom:1px solid ' + g + '.15)}' +
			'#nous-dg-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'#nous-dg-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px}' +
			'#nous-dg-body{padding:12px 16px 16px}' +
			'.nous-dg-it{display:flex;gap:9px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,.06)}' +
			'.nous-dg-ic{width:20px;text-align:center}.nous-dg-n{font-weight:600}.nous-dg-s{font-size:11px;opacity:.65;line-height:1.45}' +
			'.nous-dg-h{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#c8962e;margin:14px 0 6px}' +
			'.nous-dg-btn{padding:6px 12px;border:1px solid ' + g + '.45);border-radius:8px;cursor:pointer;background:' + g + '.18);' +
			'color:#e7c069;font-weight:600;font-size:12px;margin:4px 6px 0 0}' +
			'.nous-dg-lbl{display:flex;gap:7px;align-items:center;font-size:12px;margin:5px 0;cursor:pointer}' +
			'.nous-dg-lbl input{accent-color:#c8962e}';
		document.head.appendChild(st);
	}

	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-diag-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-diag-open';
		b.type = 'button';
		b.textContent = '🩺 Diagnostico';
		b.addEventListener('click', open);
		body.appendChild(b);
	}

	function get(k, def) { try { var v = localStorage.getItem(k); return v === null ? def : v; } catch (e) { return def; } }
	function set(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

	function open() {
		if (!ov || !document.body.contains(ov)) {
			ov = document.createElement('div');
			ov.id = 'nous-dg-ov';
			ov.innerHTML = '<div id="nous-dg"><div id="nous-dg-head"><span>🩺 Diagnostico</span>' +
				'<button id="nous-dg-close" type="button" aria-label="Fechar">&#x2715;</button></div><div id="nous-dg-body"></div></div>';
			document.body.appendChild(ov);
			ov.addEventListener('click', function (e) { if (e.target === ov) ov.classList.add('nous-hidden'); });
			ov.querySelector('#nous-dg-close').addEventListener('click', function () { ov.classList.add('nous-hidden'); });
		}
		ov.classList.remove('nous-hidden');
		render();
	}

	function render() {
		var box = ov.querySelector('#nous-dg-body');
		box.innerHTML = '<div class="nous-dg-s">Verificando cada parte do Nous...</div>';
		fetch(MON + '/diag', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
			var falhas = d.itens.filter(function (x) { return !x.ok && x.essencial; }).length;
			var html = '<div class="nous-dg-s" style="font-size:12px;opacity:.85;margin-bottom:6px">' +
				(falhas ? '⚠ ' + falhas + ' parte(s) essencial(is) com problema. Veja o que fazer abaixo.' : '✓ Tudo o que e\' essencial esta funcionando.') + '</div>';
			d.itens.forEach(function (x) {
				var ic = x.ok ? '<span style="color:#5fd693">✓</span>' : x.essencial ? '<span style="color:#f08080">✗</span>' : '<span style="opacity:.5">○</span>';
				html += '<div class="nous-dg-it"><div class="nous-dg-ic">' + ic + '</div><div><div class="nous-dg-n">' + esc(x.nome) + '</div>' +
					(x.detalhe ? '<div class="nous-dg-s">' + esc(x.detalhe) + '</div>' : '') +
					(x.dica ? '<div class="nous-dg-s">' + esc(x.dica) + '</div>' : '') + '</div></div>';
			});
			html += controls();
			box.innerHTML = html;
			bind(box);
		}).catch(function () {
			box.innerHTML = '<div class="nous-dg-it"><div class="nous-dg-ic"><span style="color:#f08080">✗</span></div><div>' +
				'<div class="nous-dg-n">Monitor do Nous</div><div class="nous-dg-s">Nao responde. Feche o navegador e abra o Nous pelo atalho ' +
				'da area de trabalho: ele liga tudo de novo. Se continuar, reinicie o computador.</div></div></div>' + controls();
			bind(box);
		});
	}

	function controls() {
		return '<div class="nous-dg-h">Privacidade na tela</div>' +
			'<label class="nous-dg-lbl"><input type="checkbox" id="nous-dg-pv"' + (get('nous-privacy', '1') !== '0' ? ' checked' : '') + '>' +
			'Borrar CPF, cartao, senhas e chaves nas conversas (clique para revelar)</label>' +
			'<label class="nous-dg-lbl"><input type="checkbox" id="nous-dg-pe"' + (get('nous-privacy-email', '0') === '1' ? ' checked' : '') + '>' +
			'Borrar tambem enderecos de e-mail</label>' +
			'<div class="nous-dg-h">Ajuda</div><button class="nous-dg-btn" id="nous-dg-tour" type="button">Ver as dicas de novo</button>' +
			'<button class="nous-dg-btn" id="nous-dg-re" type="button">Verificar de novo</button>';
	}

	function bind(box) {
		box.querySelector('#nous-dg-pv').addEventListener('change', function (e) { set('nous-privacy', e.target.checked ? '1' : '0'); if (window.NousPrivacy) window.NousPrivacy.rescan(); });
		box.querySelector('#nous-dg-pe').addEventListener('change', function (e) { set('nous-privacy-email', e.target.checked ? '1' : '0'); if (window.NousPrivacy) window.NousPrivacy.rescan(); });
		box.querySelector('#nous-dg-tour').addEventListener('click', function () { if (window.NousTour) window.NousTour.reset(); ov.classList.add('nous-hidden'); });
		box.querySelector('#nous-dg-re').addEventListener('click', render);
	}

	function start() {
		injectStyle();
		window.NousDiag = { open: open };
		setInterval(ensureButton, 1000);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
