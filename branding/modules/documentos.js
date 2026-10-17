/* =====================================================================
   Nous - Formularios PDF (v2.8). Abre um PDF preenchivel, mostra os campos,
   sugere valores com o que o Nous sabe de voce (Memoria; voce revisa), e
   carimba sua assinatura (desenhada uma vez, guardada no NousData) no campo
   de assinatura ou numa posicao da pagina. Tudo local, pelo monitor (8990).
   ===================================================================== */
(function () {
	'use strict';

	var MON = 'http://127.0.0.1:8990';
	var MEM = 'http://127.0.0.1:8993';
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var ov = null, pdfB64 = null, pdfName = 'documento', info = null;

	function injectStyle() {
		if (document.getElementById('nous-pdf-style')) return;
		var g = 'rgba(200,150,46,';
		var css =
			'#nous-pdf-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);border-radius:8px;' +
			'cursor:pointer;background:transparent;color:#e7c069;font-weight:600;font-size:12px}#nous-pdf-open:hover{background:' + g + '.12)}' +
			'#nous-pdf-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);display:flex;align-items:center;' +
			'justify-content:center;backdrop-filter:blur(3px)}#nous-pdf-ov.nous-hidden{display:none}' +
			'#nous-pdf{width:560px;max-width:95vw;max-height:86vh;display:flex;flex-direction:column;font-family:Inter,system-ui,sans-serif;' +
			'font-size:13px;color:#eee;background:rgba(18,18,22,.97);border:1px solid ' + g + '.4);border-radius:16px;' +
			'box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-pdf-head{display:flex;align-items:center;padding:14px 16px 10px;border-bottom:1px solid ' + g + '.15)}' +
			'#nous-pdf-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'#nous-pdf-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px}' +
			'#nous-pdf-body{overflow-y:auto;padding:12px 16px 16px}' +
			'.nous-pdf-h{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#c8962e;margin:14px 0 6px}' +
			'.nous-pdf-f{display:flex;gap:8px;align-items:center;margin-bottom:6px}.nous-pdf-f label{width:38%;font-size:11px;opacity:.75;word-wrap:break-word}' +
			'.nous-pdf-f input,.nous-pdf-f select,.nous-pdf-sel{flex:1;box-sizing:border-box;padding:6px 8px;background:rgba(255,255,255,.07);' +
			'border:1px solid ' + g + '.28);border-radius:7px;color:#eee;font-size:12px;outline:none;color-scheme:dark}' +
			'.nous-pdf-f input[type=checkbox]{flex:0;accent-color:#c8962e}' +
			'.nous-pdf-btn{padding:6px 12px;border:1px solid ' + g + '.45);border-radius:8px;cursor:pointer;background:' + g + '.18);' +
			'color:#e7c069;font-weight:600;font-size:12px;margin:3px 5px 3px 0}.nous-pdf-btn:hover{background:' + g + '.32)}' +
			'.nous-pdf-btn.ghost{background:transparent}.nous-pdf-btn:disabled{opacity:.4}' +
			'.nous-pdf-hint{font-size:11px;opacity:.6;line-height:1.5;margin:4px 0 8px}.nous-pdf-msg{font-size:11px}.nous-pdf-bad{color:#f08080}' +
			'#nous-pdf-pad{width:100%;height:140px;background:#fff;border-radius:8px;touch-action:none;cursor:crosshair;display:block}' +
			'#nous-pdf-sigimg{max-height:70px;background:#fff;border-radius:6px;padding:4px}';
		var st = document.createElement('style');
		st.id = 'nous-pdf-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-pdf-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-pdf-open';
		b.type = 'button';
		b.textContent = '📄 Formularios PDF';
		b.addEventListener('click', open);
		body.appendChild(b);
	}

	function open() {
		if (!ov || !document.body.contains(ov)) {
			ov = document.createElement('div');
			ov.id = 'nous-pdf-ov';
			ov.innerHTML = '<div id="nous-pdf"><div id="nous-pdf-head"><span>📄 Formularios PDF</span>' +
				'<button id="nous-pdf-close" type="button" aria-label="Fechar">&#x2715;</button></div><div id="nous-pdf-body"></div></div>';
			document.body.appendChild(ov);
			ov.addEventListener('click', function (e) { if (e.target === ov) ov.classList.add('nous-hidden'); });
			ov.querySelector('#nous-pdf-close').addEventListener('click', function () { ov.classList.add('nous-hidden'); });
		}
		ov.classList.remove('nous-hidden');
		renderStart();
	}
	function body() { return ov.querySelector('#nous-pdf-body'); }

	function renderStart() {
		body().innerHTML = '<div class="nous-pdf-hint">Escolha um PDF preenchivel (formularios de cadastro, contratos, ' +
			'requerimentos). O Nous mostra os campos, sugere o que ja sabe de voce e assina com a sua assinatura. Nada sai do computador.</div>' +
			'<label class="nous-pdf-btn">Escolher PDF<input id="nous-pdf-file" type="file" accept="application/pdf,.pdf" style="display:none"></label>' +
			'<div class="nous-pdf-h">Sua assinatura</div><div id="nous-pdf-sig"></div>';
		body().querySelector('#nous-pdf-file').addEventListener('change', function (ev) {
			var f = ev.target.files && ev.target.files[0];
			if (f) loadPdf(f);
		});
		renderSig(body().querySelector('#nous-pdf-sig'));
	}

	function loadPdf(file) {
		pdfName = file.name.replace(/\.pdf$/i, '');
		body().innerHTML = '<div class="nous-pdf-hint">Lendo o PDF...</div>';
		file.arrayBuffer().then(function (buf) {
			var bytes = new Uint8Array(buf), bin = '';
			for (var i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
			pdfB64 = btoa(bin);
			return fetch(MON + '/pdf/fields', { method: 'POST', body: buf }).then(function (r) { return r.json(); });
		}).then(function (d) {
			if (d.error) throw new Error(d.error);
			info = d;
			renderForm();
		}).catch(function (e) {
			body().innerHTML = '<div class="nous-pdf-msg nous-pdf-bad">' + esc(e.message) + '</div>';
			setTimeout(renderStart, 3000);
		});
	}

	function renderForm() {
		var flds = info.fields.filter(function (f) { return f.type !== 'signature'; });
		var html = '<div style="font-weight:700">' + esc(pdfName) + '.pdf</div><div class="nous-pdf-hint">' + info.pages + ' pagina(s) · ' +
			flds.length + ' campo(s) preenchivel(is)</div>';
		if (!flds.length) html += '<div class="nous-pdf-hint">Este PDF nao tem campos preenchiveis. Voce ainda pode assina-lo.</div>';
		else html += '<button class="nous-pdf-btn ghost" id="nous-pdf-auto" type="button">✨ Preencher com o que o Nous sabe de mim</button>' +
			'<span class="nous-pdf-msg" id="nous-pdf-am"></span>';
		flds.forEach(function (f, i) {
			var input;
			if (f.type === 'checkbox') input = '<input type="checkbox" data-i="' + i + '"' + (f.value && f.value !== 'Off' ? ' checked' : '') + '>';
			else if (f.type === 'choice' || f.type === 'radio') input = '<select data-i="' + i + '"><option value=""></option>' +
				(f.options || []).map(function (o) { return '<option' + (o === f.value ? ' selected' : '') + '>' + esc(o) + '</option>'; }).join('') + '</select>';
			else input = '<input data-i="' + i + '" value="' + esc(f.value) + '"' + (f.signature_spot ? ' placeholder="(a assinatura vai aqui)" disabled' : '') + '>';
			html += '<div class="nous-pdf-f"><label title="' + esc(f.name) + '">' + esc(f.label) + '</label>' + input + '</div>';
		});
		var spots = info.fields.filter(function (f) { return f.signature_spot || f.type === 'signature'; });
		var opts = '<option value="">Nao assinar</option>' + spots.map(function (f) {
			return '<option value="field:' + esc(f.name) + '" selected>No campo "' + esc(f.label) + '"</option>';
		}).join('');
		for (var p = info.pages; p >= 1; p--) {
			['inferior-direita', 'inferior-esquerda', 'inferior-centro'].forEach(function (pos) {
				opts += '<option value="page:' + p + ':' + pos + '">Pagina ' + p + ', ' + pos.replace('-', ' ') + '</option>';
			});
		}
		html += '<div class="nous-pdf-h">Assinatura</div><div id="nous-pdf-sig"></div>' +
			'<select class="nous-pdf-sel" id="nous-pdf-place" style="width:100%;margin:6px 0">' + opts + '</select>' +
			'<div style="margin-top:8px"><button class="nous-pdf-btn" id="nous-pdf-go" type="button">Gerar PDF preenchido</button>' +
			'<button class="nous-pdf-btn ghost" id="nous-pdf-other" type="button">Outro PDF</button><span class="nous-pdf-msg" id="nous-pdf-gm"></span></div>';
		body().innerHTML = html;
		renderSig(body().querySelector('#nous-pdf-sig'));
		body().querySelector('#nous-pdf-other').addEventListener('click', renderStart);
		var auto = body().querySelector('#nous-pdf-auto');
		if (auto) auto.addEventListener('click', function () { autofill(flds); });
		body().querySelector('#nous-pdf-go').addEventListener('click', function () { generate(flds); });
	}

	function autofill(flds) {
		var m = body().querySelector('#nous-pdf-am');
		m.textContent = ' Lendo suas memorias...';
		(UI.loadUserId || function (cb) { cb(null); })(function (uid) {
			if (!uid) { m.textContent = ' Entre no Nous primeiro.'; return; }
			fetch(MEM + '/memories?user_id=' + encodeURIComponent(uid) + '&persona=all').then(function (r) { return r.json(); })
				.then(function (mems) {
					var facts = (mems || []).map(function (x) { return x.text; });
					if (!facts.length) throw new Error('O Nous ainda nao sabe nada sobre voce (veja "O que o Nous sabe").');
					m.textContent = ' Pensando...';
					return fetch(MON + '/pdf/autofill', { method: 'POST', headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify({ fields: flds, facts: facts }) }).then(function (r) { return r.json(); });
				}).then(function (d) {
					if (d.error) throw new Error(d.error);
					var n = 0;
					flds.forEach(function (f, i) {
						var el = body().querySelector('[data-i="' + i + '"]');
						if (el && d.values[f.name] && !el.value && !el.disabled) { el.value = d.values[f.name]; el.style.borderColor = '#c8962e'; n++; }
					});
					m.textContent = n ? ' ' + n + ' campo(s) sugerido(s), em dourado. Confira antes de gerar.' : ' Nada que eu saiba combina com estes campos.';
				}).catch(function (e) { m.innerHTML = ' <span class="nous-pdf-bad">' + esc(e.message) + '</span>'; });
		});
	}

	function generate(flds) {
		var values = {};
		flds.forEach(function (f, i) {
			var el = body().querySelector('[data-i="' + i + '"]');
			if (!el || el.disabled) return;
			values[f.name] = el.type === 'checkbox' ? (el.checked ? 'true' : 'Off') : el.value;
		});
		var pv = body().querySelector('#nous-pdf-place').value, place = null;
		if (pv.indexOf('field:') === 0) place = { field: pv.slice(6) };
		else if (pv.indexOf('page:') === 0) { var p = pv.split(':'); place = { page: +p[1], pos: p[2] }; }
		var m = body().querySelector('#nous-pdf-gm');
		m.textContent = ' Gerando...';
		fetch(MON + '/pdf/fill', { method: 'POST', headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ pdf: pdfB64, values: values, place: place }) })
			.then(function (r) {
				if (r.ok) return r.blob();
				return r.json().then(function (d) { throw new Error(d.error || 'falhou'); });
			}).then(function (blob) {
				var a = document.createElement('a');
				a.href = URL.createObjectURL(blob);
				a.download = pdfName + '-preenchido.pdf';
				document.body.appendChild(a);
				a.click();
				setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
				m.innerHTML = ' <span style="color:#5fd693">✓ Baixado.</span>';
			}).catch(function (e) { m.innerHTML = ' <span class="nous-pdf-bad">' + esc(e.message) + '</span>'; });
	}

	/* ---------------------------------------------------------- assinatura */
	function renderSig(el) {
		fetch(MON + '/pdf/signature', { cache: 'no-store' }).then(function (r) {
			var ct = r.headers.get('Content-Type') || '';
			return ct.indexOf('image/') === 0 ? r.blob() : null;
		}).then(function (blob) {
			if (blob) {
				el.innerHTML = '<img id="nous-pdf-sigimg" alt="assinatura"><br>' +
					'<button class="nous-pdf-btn ghost" id="nous-pdf-redo" type="button">Desenhar de novo</button>' +
					'<button class="nous-pdf-btn ghost" id="nous-pdf-del" type="button">Apagar assinatura</button>';
				el.querySelector('#nous-pdf-sigimg').src = URL.createObjectURL(blob);
				el.querySelector('#nous-pdf-redo').addEventListener('click', function () { drawPad(el); });
				el.querySelector('#nous-pdf-del').addEventListener('click', function () {
					if (confirm('Apagar sua assinatura salva?')) fetch(MON + '/pdf/signature/delete', { method: 'POST' }).then(function () { renderSig(el); });
				});
			} else drawPad(el);
		}).catch(function () { el.innerHTML = '<div class="nous-pdf-msg nous-pdf-bad">O monitor do Nous nao esta no ar.</div>'; });
	}

	function drawPad(el) {
		el.innerHTML = '<div class="nous-pdf-hint">Desenhe sua assinatura com o mouse (ou o dedo, na tela de toque). Ela fica so neste computador.</div>' +
			'<canvas id="nous-pdf-pad"></canvas><button class="nous-pdf-btn" id="nous-pdf-sv" type="button">Salvar assinatura</button>' +
			'<button class="nous-pdf-btn ghost" id="nous-pdf-clr" type="button">Limpar</button>';
		var c = el.querySelector('#nous-pdf-pad'), ctx, drawing = false, any = false;
		setTimeout(function () {
			c.width = c.clientWidth * 2;
			c.height = c.clientHeight * 2;
			ctx = c.getContext('2d');
			ctx.lineWidth = 5; ctx.lineCap = 'round'; ctx.lineJoin = 'round'; ctx.strokeStyle = '#13207a';
		}, 0);
		function pt(e) { var r = c.getBoundingClientRect(); return [(e.clientX - r.left) * 2, (e.clientY - r.top) * 2]; }
		c.addEventListener('pointerdown', function (e) { drawing = true; any = true; c.setPointerCapture(e.pointerId); var p = pt(e); ctx.beginPath(); ctx.moveTo(p[0], p[1]); });
		c.addEventListener('pointermove', function (e) { if (!drawing) return; var p = pt(e); ctx.lineTo(p[0], p[1]); ctx.stroke(); });
		c.addEventListener('pointerup', function () { drawing = false; });
		el.querySelector('#nous-pdf-clr').addEventListener('click', function () { ctx.clearRect(0, 0, c.width, c.height); any = false; });
		el.querySelector('#nous-pdf-sv').addEventListener('click', function () {
			if (!any) { alert('Desenhe a assinatura primeiro.'); return; }
			c.toBlob(function (blob) {
				fetch(MON + '/pdf/signature', { method: 'POST', body: blob }).then(function () { renderSig(el); });
			}, 'image/png');
		});
	}

	function start() {
		injectStyle();
		window.NousPdf = { open: open };
		setInterval(ensureButton, 1000);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
