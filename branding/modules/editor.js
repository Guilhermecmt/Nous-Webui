/* =====================================================================
   Nous - Editor de fotos (v2.7). Abre qualquer imagem: arquivo do PC,
   imagem colada (Ctrl+V) ou o botao "Editar" que aparece sobre as imagens
   do chat. Cortar, girar, espelhar, luz/cor, filtros, redimensionar,
   desfazer/refazer, baixar ou copiar. Tudo no navegador; so' o "Remover
   fundo" usa o monitor local (127.0.0.1:8990/image/remove-bg, modelo U2-Net).
   ===================================================================== */
(function () {
	'use strict';

	var MON = 'http://127.0.0.1:8990';
	var ov = null, view = null, vctx = null;
	var base = null;            /* canvas com as edicoes destrutivas (corte, giro, fundo) */
	var adj = null;             /* ajustes nao destrutivos */
	var undo = [], redo = [];
	var crop = null, cropAspect = 0, dragging = null;
	var srcName = 'imagem';
	var hoverChip = null, hoverImg = null;

	var ADJ0 = { brilho: 100, contraste: 100, saturacao: 100, desfoque: 0, temperatura: 0, filtro: '' };
	var FILTROS = {
		'': 'Nenhum', pb: 'Preto e branco', sepia: 'Sepia', vivido: 'Vivido', suave: 'Suave', noir: 'Noir'
	};

	/* ---------------------------------------------------------- estilo */
	function injectStyle() {
		if (document.getElementById('nous-ed-style')) return;
		var g = 'rgba(200,150,46,';
		var css =
			'#nous-editor-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);border-radius:8px;' +
			'cursor:pointer;background:transparent;color:#e7c069;font-weight:600;font-size:12px}' +
			'#nous-editor-open:hover{background:' + g + '.12)}' +
			'#nous-ed-ov{position:fixed;inset:0;z-index:10003;background:rgba(8,8,10,.92);display:flex;flex-direction:column;' +
			'font-family:Inter,system-ui,sans-serif;font-size:12px;color:#eee}' +
			'#nous-ed-ov.nous-hidden{display:none}' +
			'#nous-ed-top{display:flex;align-items:center;gap:6px;padding:10px 14px;border-bottom:1px solid ' + g + '.2);flex-wrap:wrap}' +
			'#nous-ed-top .t{font-weight:700;font-size:14px;color:#e7c069;margin-right:10px}' +
			'#nous-ed-top .sp{flex:1}' +
			'.nous-ed-b{padding:6px 10px;border:1px solid ' + g + '.35);border-radius:8px;background:rgba(255,255,255,.04);' +
			'color:#e7c069;cursor:pointer;font-weight:600;font-size:12px;white-space:nowrap}' +
			'.nous-ed-b:hover:not(:disabled){background:' + g + '.2)}.nous-ed-b:disabled{opacity:.35;cursor:default}' +
			'.nous-ed-b.on{background:' + g + '.3)}.nous-ed-b.main{background:' + g + '.22)}' +
			'#nous-ed-mid{flex:1;display:flex;min-height:0}' +
			'#nous-ed-stage{flex:1;display:flex;align-items:center;justify-content:center;position:relative;min-width:0;padding:16px;' +
			'background-image:linear-gradient(45deg,#1c1c20 25%,transparent 25%),linear-gradient(-45deg,#1c1c20 25%,transparent 25%),' +
			'linear-gradient(45deg,transparent 75%,#1c1c20 75%),linear-gradient(-45deg,transparent 75%,#1c1c20 75%);' +
			'background-size:20px 20px;background-position:0 0,0 10px,10px -10px,-10px 0}' +
			'#nous-ed-view{max-width:100%;max-height:100%;box-shadow:0 8px 30px rgba(0,0,0,.6);cursor:default}' +
			'#nous-ed-view.crop{cursor:crosshair}' +
			'#nous-ed-drop{position:absolute;inset:16px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;' +
			'border:2px dashed ' + g + '.35);border-radius:16px;font-size:14px;opacity:.85;text-align:center;line-height:1.6}' +
			'#nous-ed-side{width:250px;border-left:1px solid ' + g + '.2);padding:12px 14px;overflow-y:auto}' +
			'#nous-ed-side h4{margin:14px 0 6px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#c8962e}' +
			'#nous-ed-side h4:first-child{margin-top:0}' +
			'#nous-ed-side label{display:block;font-size:11px;opacity:.75;margin-top:6px}' +
			'#nous-ed-side input[type=range]{width:100%;accent-color:#c8962e}' +
			'#nous-ed-side select,#nous-ed-side input[type=number]{width:100%;box-sizing:border-box;padding:5px 7px;margin-top:3px;' +
			'background:rgba(255,255,255,.07);border:1px solid ' + g + '.28);border-radius:7px;color:#eee;font-size:12px;color-scheme:dark}' +
			'.nous-ed-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px}' +
			'#nous-ed-msg{font-size:11px;min-height:16px;margin-top:8px;opacity:.85}' +
			'#nous-ed-chip{position:fixed;z-index:9990;padding:4px 9px;border-radius:8px;border:1px solid ' + g + '.6);' +
			'background:rgba(18,18,22,.9);color:#e7c069;font:600 11px Inter,system-ui,sans-serif;cursor:pointer;display:none}' +
			'@media (max-width:760px){#nous-ed-mid{flex-direction:column}#nous-ed-side{width:auto;border-left:0;' +
			'border-top:1px solid ' + g + '.2);max-height:40vh}}';
		var st = document.createElement('style');
		st.id = 'nous-ed-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	/* ---------------------------------------------------------- montagem */
	function build() {
		if (ov && document.body.contains(ov)) return;
		ov = document.createElement('div');
		ov.id = 'nous-ed-ov';
		ov.className = 'nous-hidden';
		var filtros = Object.keys(FILTROS).map(function (k) { return '<option value="' + k + '">' + FILTROS[k] + '</option>'; }).join('');
		ov.innerHTML =
			'<div id="nous-ed-top"><span class="t">🖼 Editor de fotos</span>' +
			'<label class="nous-ed-b">Abrir...<input id="nous-ed-file" type="file" accept="image/*" style="display:none"></label>' +
			'<button class="nous-ed-b" data-a="undo" title="Desfazer (Ctrl+Z)">↶</button>' +
			'<button class="nous-ed-b" data-a="redo" title="Refazer (Ctrl+Y)">↷</button>' +
			'<span class="sp"></span>' +
			'<button class="nous-ed-b" data-a="copy">Copiar</button>' +
			'<button class="nous-ed-b main" data-a="png">Baixar PNG</button>' +
			'<button class="nous-ed-b main" data-a="jpg">Baixar JPG</button>' +
			'<button class="nous-ed-b" data-a="close" title="Fechar (Esc)">✕</button></div>' +
			'<div id="nous-ed-mid"><div id="nous-ed-stage"><canvas id="nous-ed-view"></canvas>' +
			'<div id="nous-ed-drop">Arraste uma imagem para ca, cole com Ctrl+V<br>ou clique em <b>Abrir...</b></div></div>' +
			'<div id="nous-ed-side">' +
			'<h4>Recortar e girar</h4>' +
			'<div class="nous-ed-grid"><button class="nous-ed-b" data-a="crop">✂ Cortar</button>' +
			'<select id="nous-ed-asp"><option value="0">Livre</option><option value="1">1:1</option>' +
			'<option value="1.3333">4:3</option><option value="1.7778">16:9</option><option value="0.5625">9:16</option></select>' +
			'<button class="nous-ed-b" data-a="rotl">⟲ 90°</button><button class="nous-ed-b" data-a="rotr">⟳ 90°</button>' +
			'<button class="nous-ed-b" data-a="fliph">⇋ Espelhar</button><button class="nous-ed-b" data-a="flipv">⇵ Inverter</button></div>' +
			'<button class="nous-ed-b" data-a="cropok" style="width:100%;margin-top:5px;display:none">Aplicar corte</button>' +
			'<h4>Luz e cor</h4>' +
			'<label>Brilho <span data-v="brilho"></span></label><input type="range" min="30" max="200" data-k="brilho">' +
			'<label>Contraste <span data-v="contraste"></span></label><input type="range" min="30" max="200" data-k="contraste">' +
			'<label>Saturacao <span data-v="saturacao"></span></label><input type="range" min="0" max="250" data-k="saturacao">' +
			'<label>Temperatura <span data-v="temperatura"></span></label><input type="range" min="-50" max="50" data-k="temperatura">' +
			'<label>Desfoque <span data-v="desfoque"></span></label><input type="range" min="0" max="20" data-k="desfoque">' +
			'<label>Filtro</label><select id="nous-ed-flt">' + filtros + '</select>' +
			'<button class="nous-ed-b" data-a="reset" style="width:100%;margin-top:8px">Zerar ajustes</button>' +
			'<h4>Inteligencia artificial</h4>' +
			'<button class="nous-ed-b" data-a="rembg" style="width:100%">✨ Remover fundo</button>' +
			'<h4>Tamanho</h4>' +
			'<div class="nous-ed-grid"><input id="nous-ed-w" type="number" min="16" max="8000" title="Largura">' +
			'<input id="nous-ed-h" type="number" min="16" max="8000" title="Altura"></div>' +
			'<button class="nous-ed-b" data-a="resize" style="width:100%;margin-top:5px">Redimensionar</button>' +
			'<div id="nous-ed-msg"></div></div></div>';
		document.body.appendChild(ov);
		view = ov.querySelector('#nous-ed-view');
		view.width = view.height = 0;  /* sem imagem: nada de caixa vazia 300x150 */
		vctx = view.getContext('2d');

		ov.querySelectorAll('[data-a]').forEach(function (b) {
			b.addEventListener('click', function () { action(b.getAttribute('data-a')); });
		});
		ov.querySelector('#nous-ed-file').addEventListener('change', function (e) {
			var f = e.target.files && e.target.files[0];
			if (f) loadBlob(f, f.name);
			e.target.value = '';
		});
		/* o retrato para desfazer e' tirado ANTES do primeiro 'input' de cada arraste */
		var sliding = false;
		ov.querySelectorAll('[data-k]').forEach(function (r) {
			r.addEventListener('input', function () {
				if (!sliding) { pushUndo(); sliding = true; }
				adj[r.getAttribute('data-k')] = +r.value;
				syncLabels();
				render();
			});
			r.addEventListener('change', function () { sliding = false; });
		});
		ov.querySelector('#nous-ed-flt').addEventListener('change', function (e) { pushUndo(); adj.filtro = e.target.value; render(); });
		ov.querySelector('#nous-ed-asp').addEventListener('change', function (e) {
			cropAspect = +e.target.value;
			if (crop) { crop = fitAspect(crop); render(); }
		});
		ov.querySelector('#nous-ed-w').addEventListener('input', function () { linkSize('w'); });
		ov.querySelector('#nous-ed-h').addEventListener('input', function () { linkSize('h'); });
		var stage = ov.querySelector('#nous-ed-stage');
		stage.addEventListener('dragover', function (e) { e.preventDefault(); });
		stage.addEventListener('drop', function (e) {
			e.preventDefault();
			var f = e.dataTransfer.files && e.dataTransfer.files[0];
			if (f && /^image\//.test(f.type)) loadBlob(f, f.name);
		});
		view.addEventListener('mousedown', cropDown);
		window.addEventListener('mousemove', cropMove);
		window.addEventListener('mouseup', function () { dragging = null; });
		document.addEventListener('keydown', onKey);
		document.addEventListener('paste', onPaste);
	}

	function open() {
		build();
		ov.classList.remove('nous-hidden');
		if (!base) { adj = clone(ADJ0); syncControls(); }
	}
	function close() { ov.classList.add('nous-hidden'); setCrop(false); }
	function isOpen() { return ov && !ov.classList.contains('nous-hidden'); }
	function msg(t, bad) {
		var m = ov.querySelector('#nous-ed-msg');
		m.textContent = t || '';
		m.style.color = bad ? '#f08080' : '';
	}
	function clone(o) { return JSON.parse(JSON.stringify(o)); }

	/* ---------------------------------------------------------- carregar */
	function loadBlob(blob, name) {
		open();
		srcName = (name || 'imagem').replace(/\.[a-z0-9]+$/i, '');
		createImageBitmap(blob).then(function (bmp) {
			var c = document.createElement('canvas');
			c.width = bmp.width;
			c.height = bmp.height;
			c.getContext('2d').drawImage(bmp, 0, 0);
			base = c;
			adj = clone(ADJ0);
			undo = []; redo = [];
			setCrop(false);
			ov.querySelector('#nous-ed-drop').style.display = 'none';
			syncControls();
			render();
			msg(c.width + ' x ' + c.height + ' px');
		}).catch(function () { msg('Nao consegui abrir esta imagem.', true); });
	}

	function loadUrl(url, name) {
		open();
		msg('Carregando...');
		fetch(url, { credentials: 'include' })
			.then(function (r) { if (!r.ok) throw new Error(); return r.blob(); })
			.then(function (b) { loadBlob(b, name); })
			.catch(function () {
				msg('Esta imagem vem de outro site e o navegador bloqueou a edicao. Salve no PC e use "Abrir...".', true);
			});
	}

	function onPaste(e) {
		if (!isOpen()) return;
		var items = (e.clipboardData && e.clipboardData.items) || [];
		for (var i = 0; i < items.length; i++) {
			if (items[i].type.indexOf('image/') === 0) {
				loadBlob(items[i].getAsFile(), 'colada');
				e.preventDefault();
				return;
			}
		}
	}

	function onKey(e) {
		if (!isOpen()) return;
		if (e.key === 'Escape') { if (crop) { setCrop(false); render(); } else close(); }
		else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); action('undo'); }
		else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); action('redo'); }
		else if (e.key === 'Enter' && crop) action('cropok');
	}

	/* ---------------------------------------------------------- historico */
	function snapshot() {
		var c = document.createElement('canvas');
		c.width = base.width;
		c.height = base.height;
		c.getContext('2d').drawImage(base, 0, 0);
		return { base: c, adj: clone(adj) };
	}
	function pushUndo() {
		if (!base) return;
		undo.push(snapshot());
		if (undo.length > 20) undo.shift();
		redo = [];
		syncButtons();
	}
	function restore(s) {
		base = s.base;
		adj = s.adj;
		syncControls();
		render();
	}

	/* ---------------------------------------------------------- render */
	function filterString(a) {
		var f = 'brightness(' + a.brilho + '%) contrast(' + a.contraste + '%) saturate(' + a.saturacao + '%)';
		if (a.desfoque) f += ' blur(' + (a.desfoque * Math.max(base.width, base.height) / 1000).toFixed(2) + 'px)';
		if (a.filtro === 'pb') f += ' grayscale(100%)';
		else if (a.filtro === 'sepia') f += ' sepia(85%)';
		else if (a.filtro === 'vivido') f += ' saturate(140%) contrast(110%)';
		else if (a.filtro === 'suave') f += ' contrast(88%) brightness(106%) saturate(85%)';
		else if (a.filtro === 'noir') f += ' grayscale(100%) contrast(140%) brightness(92%)';
		return f;
	}

	/* Desenha base + ajustes em ctx (tamanho do base). Temperatura = camada de
	 * cor em 'soft-light' (laranja aquece, azul esfria), preservando o alfa. */
	function paint(ctx) {
		ctx.clearRect(0, 0, base.width, base.height);
		ctx.filter = filterString(adj);
		ctx.drawImage(base, 0, 0);
		ctx.filter = 'none';
		if (adj.temperatura) {
			ctx.save();
			ctx.globalCompositeOperation = 'soft-light';
			ctx.globalAlpha = Math.min(1, Math.abs(adj.temperatura) / 60);
			ctx.fillStyle = adj.temperatura > 0 ? '#ff9a2e' : '#2e8bff';
			ctx.fillRect(0, 0, base.width, base.height);
			ctx.globalCompositeOperation = 'destination-in';
			ctx.globalAlpha = 1;
			ctx.drawImage(base, 0, 0);
			ctx.restore();
		}
	}

	function render() {
		if (!base) { view.width = view.height = 0; syncButtons(); return; }
		if (view.width !== base.width || view.height !== base.height) {
			view.width = base.width;
			view.height = base.height;
		}
		paint(vctx);
		if (crop) {
			var lw = Math.max(2, base.width / 400);
			vctx.save();
			vctx.fillStyle = 'rgba(0,0,0,.55)';
			vctx.beginPath();
			vctx.rect(0, 0, base.width, base.height);
			vctx.rect(crop.x, crop.y + crop.h, crop.w, -crop.h);
			vctx.fill('evenodd');
			vctx.strokeStyle = '#e7c069';
			vctx.lineWidth = lw;
			vctx.strokeRect(crop.x, crop.y, crop.w, crop.h);
			vctx.restore();
		}
		ov.querySelector('#nous-ed-w').value = base.width;
		ov.querySelector('#nous-ed-h').value = base.height;
		syncButtons();
	}

	function syncLabels() {
		ov.querySelectorAll('[data-v]').forEach(function (s) {
			var k = s.getAttribute('data-v'), v = adj[k];
			s.textContent = k === 'desfoque' ? v : k === 'temperatura' ? (v > 0 ? '+' : '') + v : v + '%';
		});
	}
	function syncControls() {
		ov.querySelectorAll('[data-k]').forEach(function (r) { r.value = adj[r.getAttribute('data-k')]; });
		ov.querySelector('#nous-ed-flt').value = adj.filtro;
		syncLabels();
		syncButtons();
	}
	function syncButtons() {
		var has = !!base;
		ov.querySelectorAll('[data-a]').forEach(function (b) {
			var a = b.getAttribute('data-a');
			if (a === 'close') return;
			if (a === 'undo') b.disabled = !undo.length;
			else if (a === 'redo') b.disabled = !redo.length;
			else b.disabled = !has;
		});
		ov.querySelectorAll('[data-k],#nous-ed-flt,#nous-ed-w,#nous-ed-h,#nous-ed-asp').forEach(function (i) { i.disabled = !has; });
	}

	/* ---------------------------------------------------------- corte */
	function setCrop(on) {
		if (!ov) return;
		crop = on && base ? fitAspect({ x: base.width * 0.1, y: base.height * 0.1, w: base.width * 0.8, h: base.height * 0.8 }) : null;
		view.classList.toggle('crop', !!crop);
		ov.querySelector('[data-a="crop"]').classList.toggle('on', !!crop);
		ov.querySelector('[data-a="cropok"]').style.display = crop ? '' : 'none';
	}
	function fitAspect(r) {
		if (!cropAspect) return r;
		var w = r.w, h = w / cropAspect;
		if (h > base.height) { h = base.height; w = h * cropAspect; }
		if (w > base.width) { w = base.width; h = w / cropAspect; }
		var cx = r.x + r.w / 2, cy = r.y + r.h / 2;
		return clampRect({ x: cx - w / 2, y: cy - h / 2, w: w, h: h });
	}
	function clampRect(r) {
		r.w = Math.min(r.w, base.width);
		r.h = Math.min(r.h, base.height);
		r.x = Math.max(0, Math.min(r.x, base.width - r.w));
		r.y = Math.max(0, Math.min(r.y, base.height - r.h));
		return r;
	}
	function toImg(e) {
		var b = view.getBoundingClientRect();
		return { x: (e.clientX - b.left) * base.width / b.width, y: (e.clientY - b.top) * base.height / b.height };
	}
	function cropDown(e) {
		if (!crop) return;
		var p = toImg(e);
		var inside = p.x > crop.x && p.x < crop.x + crop.w && p.y > crop.y && p.y < crop.y + crop.h;
		dragging = inside ? { mode: 'move', ox: p.x - crop.x, oy: p.y - crop.y } : { mode: 'new', sx: p.x, sy: p.y };
		e.preventDefault();
	}
	function cropMove(e) {
		if (!dragging || !crop) return;
		var p = toImg(e);
		if (dragging.mode === 'move') {
			crop = clampRect({ x: p.x - dragging.ox, y: p.y - dragging.oy, w: crop.w, h: crop.h });
		} else {
			var x0 = Math.max(0, Math.min(dragging.sx, p.x)), y0 = Math.max(0, Math.min(dragging.sy, p.y));
			var w = Math.min(base.width, Math.max(dragging.sx, p.x)) - x0;
			var h = Math.min(base.height, Math.max(dragging.sy, p.y)) - y0;
			if (cropAspect) {
				h = w / cropAspect;
				if (p.y < dragging.sy) y0 = dragging.sy - h;
			}
			if (w > 4 && h > 4) crop = clampRect({ x: x0, y: y0, w: w, h: h });
		}
		render();
	}

	/* ---------------------------------------------------------- acoes */
	function transform(w, h, fn) {
		pushUndo();
		var c = document.createElement('canvas');
		c.width = w;
		c.height = h;
		var ctx = c.getContext('2d');
		ctx.imageSmoothingQuality = 'high';
		fn(ctx);
		base = c;
		render();
	}

	function flatten() {
		var c = document.createElement('canvas');
		c.width = base.width;
		c.height = base.height;
		paint(c.getContext('2d'));
		return c;
	}

	function action(a) {
		if (a === 'close') return close();
		if (a === 'undo' && undo.length) { redo.push(snapshot()); restore(undo.pop()); return; }
		if (a === 'redo' && redo.length) { undo.push(snapshot()); restore(redo.pop()); return; }
		if (!base) return;
		var w = base.width, h = base.height, src = base;
		if (a === 'crop') { setCrop(!crop); render(); }
		else if (a === 'cropok' && crop) {
			var r = { x: Math.round(crop.x), y: Math.round(crop.y), w: Math.round(crop.w), h: Math.round(crop.h) };
			setCrop(false);
			transform(r.w, r.h, function (ctx) { ctx.drawImage(src, r.x, r.y, r.w, r.h, 0, 0, r.w, r.h); });
			msg(r.w + ' x ' + r.h + ' px');
		}
		else if (a === 'rotl' || a === 'rotr') {
			setCrop(false);
			transform(h, w, function (ctx) {
				ctx.translate(h / 2, w / 2);
				ctx.rotate((a === 'rotr' ? 1 : -1) * Math.PI / 2);
				ctx.drawImage(src, -w / 2, -h / 2);
			});
		}
		else if (a === 'fliph' || a === 'flipv') {
			transform(w, h, function (ctx) {
				if (a === 'fliph') { ctx.translate(w, 0); ctx.scale(-1, 1); }
				else { ctx.translate(0, h); ctx.scale(1, -1); }
				ctx.drawImage(src, 0, 0);
			});
		}
		else if (a === 'reset') { pushUndo(); adj = clone(ADJ0); syncControls(); render(); }
		else if (a === 'resize') {
			var nw = +ov.querySelector('#nous-ed-w').value, nh = +ov.querySelector('#nous-ed-h').value;
			if (!(nw >= 16 && nh >= 16 && nw <= 8000 && nh <= 8000)) { msg('Tamanho entre 16 e 8000 px.', true); return; }
			transform(nw, nh, function (ctx) { ctx.drawImage(src, 0, 0, nw, nh); });
			msg(nw + ' x ' + nh + ' px');
		}
		else if (a === 'rembg') removeBg();
		else if (a === 'png' || a === 'jpg') download(a);
		else if (a === 'copy') copy();
	}

	function linkSize(changed) {
		if (!base) return;
		var wi = ov.querySelector('#nous-ed-w'), hi = ov.querySelector('#nous-ed-h');
		if (changed === 'w') hi.value = Math.round(+wi.value * base.height / base.width) || '';
		else wi.value = Math.round(+hi.value * base.width / base.height) || '';
	}

	function removeBg() {
		var b = ov.querySelector('[data-a="rembg"]');
		b.disabled = true;
		msg('Recortando o fundo... (na primeira vez o Nous baixa um modelo de 4,5 MB)');
		base.toBlob(function (blob) {
			fetch(MON + '/image/remove-bg', { method: 'POST', headers: { 'Content-Type': 'image/png' }, body: blob })
				.then(function (r) {
					if (r.ok) return r.blob();
					return r.json().then(function (d) { throw new Error(d.error || 'falhou'); });
				})
				.then(function (png) { return createImageBitmap(png); })
				.then(function (bmp) {
					transform(bmp.width, bmp.height, function (ctx) { ctx.drawImage(bmp, 0, 0); });
					msg('Fundo removido. Baixe em PNG para manter a transparencia.');
				})
				.catch(function (e) {
					msg(e.message === 'Failed to fetch' ? 'O monitor do Nous nao esta no ar.' : e.message, true);
				})
				.then(function () { syncButtons(); });
		}, 'image/png');
	}

	function download(fmt) {
		var c = flatten();
		if (fmt === 'jpg') {  /* JPG nao tem transparencia: fundo branco */
			var j = document.createElement('canvas');
			j.width = c.width;
			j.height = c.height;
			var x = j.getContext('2d');
			x.fillStyle = '#fff';
			x.fillRect(0, 0, j.width, j.height);
			x.drawImage(c, 0, 0);
			c = j;
		}
		c.toBlob(function (blob) {
			var a = document.createElement('a');
			a.href = URL.createObjectURL(blob);
			a.download = srcName + '-editada.' + fmt;
			document.body.appendChild(a);
			a.click();
			setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
		}, fmt === 'jpg' ? 'image/jpeg' : 'image/png', 0.92);
	}

	function copy() {
		if (!window.ClipboardItem || !navigator.clipboard) { msg('Este navegador nao deixa copiar imagens. Use Baixar.', true); return; }
		flatten().toBlob(function (blob) {
			navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
				.then(function () { msg('Copiada! Cole com Ctrl+V no chat ou em outro programa.'); })
				.catch(function () { msg('Nao consegui copiar. Use Baixar.', true); });
		}, 'image/png');
	}

	/* ---------------------------------------------------------- "Editar" nas imagens */
	function ensureChip() {
		if (hoverChip && document.body.contains(hoverChip)) return;
		hoverChip = document.createElement('div');
		hoverChip.id = 'nous-ed-chip';
		hoverChip.textContent = '✎ Editar';
		hoverChip.addEventListener('click', function () {
			if (hoverImg) loadUrl(hoverImg.currentSrc || hoverImg.src, 'imagem');
			hoverChip.style.display = 'none';
		});
		document.body.appendChild(hoverChip);
	}
	function editable(el) {
		if (!el || el.tagName !== 'IMG' || !el.src) return false;
		if (el.closest('#nous-ed-ov,#nous-monitor,#nous-mem-panel,#nous-sidebar,nav,header,#sidebar')) return false;
		var r = el.getBoundingClientRect();
		return r.width >= 140 && r.height >= 100;
	}
	function onHover(e) {
		var t = e.target;
		if (t === hoverChip) return;
		if (!editable(t)) {
			if (hoverChip && !(e.relatedTarget && e.relatedTarget === hoverChip)) hoverChip.style.display = 'none';
			return;
		}
		ensureChip();
		hoverImg = t;
		var r = t.getBoundingClientRect();
		hoverChip.style.left = Math.max(4, r.right - 78) + 'px';
		hoverChip.style.top = Math.max(4, r.top + 8) + 'px';
		hoverChip.style.display = 'block';
	}

	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-editor-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-editor-open';
		b.type = 'button';
		b.textContent = '🖼 Editor de fotos';
		b.addEventListener('click', open);
		body.appendChild(b);
	}

	function start() {
		injectStyle();
		setInterval(ensureButton, 1000);
		document.addEventListener('mouseover', onHover, true);
		window.NousEditor = { open: open, openUrl: loadUrl, openBlob: loadBlob };
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
