/* =====================================================================
   Nous - pecas comuns dos paineis (v2.9). Carrega antes dos outros modulos
   (o "_" ordena primeiro) e acrescenta ao window.NousUI:
     toast(texto, {acao, rotulo, tipo: 'ok'|'erro'|'info', ms})
         aviso no canto, com botao opcional ("Desfazer"); some sozinho
     confirmar(texto, {ok, cancelar, perigo, titulo}) -> Promise<boolean>
         caixa no visual do Nous (no lugar do confirm() cinza do navegador);
         o botao repete o verbo ("Apagar", nao "OK")
   ===================================================================== */
(function () {
	'use strict';

	var g = 'rgba(200,150,46,';

	function injectStyle() {
		if (document.getElementById('nous-base-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-base-style';
		st.textContent =
			'#nous-toasts{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:10050;display:flex;' +
			'flex-direction:column;gap:8px;align-items:center;pointer-events:none;max-width:92vw}' +
			'.nous-toast{pointer-events:auto;display:flex;align-items:center;gap:10px;padding:9px 12px 9px 14px;border-radius:12px;' +
			'font:500 13px Inter,system-ui,sans-serif;color:#eee;background:rgba(18,18,22,.97);border:1px solid ' + g + '.45);' +
			'box-shadow:0 10px 30px rgba(0,0,0,.45);animation:nous-toast-in .18s ease-out}' +
			'.nous-toast.erro{border-color:rgba(220,80,80,.6)}.nous-toast.erro .nous-toast-i{color:#f08080}' +
			'.nous-toast-i{color:#e7c069;font-weight:700}' +
			'.nous-toast button{border:1px solid ' + g + '.5);background:' + g + '.18);color:#e7c069;border-radius:8px;' +
			'padding:4px 10px;font:600 12px Inter,system-ui,sans-serif;cursor:pointer}.nous-toast button:hover{background:' + g + '.32)}' +
			'.nous-toast.sai{opacity:0;transform:translateY(6px);transition:all .2s}' +
			'@keyframes nous-toast-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}' +
			'#nous-cf-ov{position:fixed;inset:0;z-index:10040;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;' +
			'backdrop-filter:blur(2px)}' +
			'#nous-cf{width:380px;max-width:90vw;padding:18px 18px 14px;border-radius:16px;background:rgba(18,18,22,.98);' +
			'border:1px solid ' + g + '.45);box-shadow:0 16px 48px rgba(0,0,0,.6);font:13px/1.55 Inter,system-ui,sans-serif;color:#eee}' +
			'#nous-cf h3{margin:0 0 6px;font:600 15px Cinzel,Georgia,serif;letter-spacing:.04em;color:#e7c069}' +
			'#nous-cf p{margin:0 0 14px;opacity:.85}#nous-cf .nous-cf-row{display:flex;gap:8px;justify-content:flex-end}' +
			'#nous-cf button{padding:7px 14px;border-radius:9px;cursor:pointer;font:600 13px Inter,system-ui,sans-serif;' +
			'border:1px solid ' + g + '.45);background:transparent;color:#e7c069}' +
			'#nous-cf button.ok{background:' + g + '.25)}#nous-cf button.ok:hover{background:' + g + '.4)}' +
			'#nous-cf button.ok.perigo{background:rgba(200,60,60,.25);border-color:rgba(220,80,80,.6);color:#f4a3a3}' +
			'#nous-cf button.ok.perigo:hover{background:rgba(200,60,60,.4)}' +
			'#nous-cf button:focus-visible{outline:2px solid #e7c069;outline-offset:2px}';
		document.head.appendChild(st);
	}

	function box() {
		var b = document.getElementById('nous-toasts');
		if (!b) {
			b = document.createElement('div');
			b.id = 'nous-toasts';
			b.setAttribute('role', 'status');
			b.setAttribute('aria-live', 'polite');
			document.body.appendChild(b);
		}
		return b;
	}

	function toast(texto, op) {
		op = op || {};
		injectStyle();
		var t = document.createElement('div');
		t.className = 'nous-toast' + (op.tipo === 'erro' ? ' erro' : '');
		var icone = op.tipo === 'erro' ? '!' : op.tipo === 'info' ? 'i' : '✓';
		t.innerHTML = '<span class="nous-toast-i">' + icone + '</span><span></span>';
		t.children[1].textContent = texto;
		var timer;
		function fecha() {
			clearTimeout(timer);
			t.classList.add('sai');
			setTimeout(function () { t.remove(); }, 220);
		}
		if (op.acao) {
			var b = document.createElement('button');
			b.type = 'button';
			b.textContent = op.rotulo || 'Desfazer';
			b.addEventListener('click', function () { fecha(); op.acao(); });
			t.appendChild(b);
		}
		box().appendChild(t);
		timer = setTimeout(fecha, op.ms || (op.acao ? 7000 : 3500));
		return fecha;
	}

	function confirmar(texto, op) {
		op = op || {};
		injectStyle();
		return new Promise(function (resolve) {
			var ov = document.createElement('div');
			ov.id = 'nous-cf-ov';
			ov.innerHTML = '<div id="nous-cf" role="alertdialog" aria-modal="true"><h3></h3><p></p><div class="nous-cf-row">' +
				'<button type="button" class="nao"></button><button type="button" class="ok"></button></div></div>';
			ov.querySelector('h3').textContent = op.titulo || 'Tem certeza?';
			ov.querySelector('p').textContent = texto;
			ov.querySelector('.nao').textContent = op.cancelar || 'Cancelar';
			var ok = ov.querySelector('.ok');
			ok.textContent = op.ok || 'Continuar';
			if (op.perigo) ok.classList.add('perigo');
			function fim(v) {
				document.removeEventListener('keydown', tecla, true);
				ov.remove();
				resolve(v);
			}
			function tecla(e) {
				if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); fim(false); }
			}
			document.addEventListener('keydown', tecla, true);
			ov.addEventListener('click', function (e) { if (e.target === ov) fim(false); });
			ov.querySelector('.nao').addEventListener('click', function () { fim(false); });
			ok.addEventListener('click', function () { fim(true); });
			document.body.appendChild(ov);
			(op.perigo ? ov.querySelector('.nao') : ok).focus();
		});
	}

	/* pede(texto): o confirmar() pronto para os paineis antigos. A 1a frase
	 * (ate' o "?") vira o titulo, o resto o texto; o botao repete o verbo e
	 * apagar/remover/descadastrar ficam vermelhos. */
	function pede(texto, op) {
		texto = String(texto || '');
		var i = texto.indexOf('?'), titulo = i > 0 ? texto.slice(0, i + 1) : texto, resto = i > 0 ? texto.slice(i + 1).trim() : '';
		var verbo = (titulo.match(/^(Apagar|Remover|Enviar|Descadastrar|Zerar|Excluir)/i) || [])[1];
		var perigo = /^(Apagar|Remover|Descadastrar|Zerar|Excluir)/i.test(titulo);
		if (/nao pode ser desfeit|não pode ser desfeit/i.test(texto)) perigo = true;
		return confirmar(resto || (perigo ? 'Nao da para desfazer.' : ''), Object.assign({
			titulo: titulo, ok: verbo ? verbo.charAt(0).toUpperCase() + verbo.slice(1).toLowerCase() : 'Continuar', perigo: perigo
		}, op || {}));
	}

	/* aviso(texto, tipo): o alert() dos paineis antigos virou toast */
	function aviso(texto, tipo) {
		texto = String(texto || '');
		if (!tipo) tipo = /\b(nao|não|erro|falhou|primeiro|indisponivel)\b/i.test(texto) ? 'erro' : 'ok';
		return toast(texto, { tipo: tipo, ms: tipo === 'erro' ? 6000 : 3500 });
	}

	/* titulos de todos os paineis na fonte da marca (Cinzel, a do NOUS) */
	function injectTitulos() {
		if (document.getElementById('nous-titulos-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-titulos-style';
		st.textContent = ['voice', 'email', 'gal', 'mem', 'store', 'ag', 'cp', 'dg', 'pdf', 'em', 'sk', 'rp', 'ed'].map(function (k) {
			return '#nous-' + k + '-head span:first-of-type';
		}).join(',') + '{font-family:Cinzel,Georgia,serif!important;font-weight:600!important;letter-spacing:.05em}';
		document.head.appendChild(st);
	}

	/* ja' na carga: os outros modulos guardam a referencia do NousUI */
	var ui = window.NousUI = window.NousUI || {};
	ui.toast = toast;
	ui.confirmar = confirmar;
	ui.pede = pede;
	ui.aviso = aviso;
	if (document.head) injectTitulos();
	else document.addEventListener('DOMContentLoaded', injectTitulos);
})();
