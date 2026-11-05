/* =====================================================================
   Nous - pecas comuns dos paineis (v2.9). Carrega antes dos outros modulos
   (o "_" ordena primeiro) e acrescenta ao window.NousUI:
     toast(texto, {acao, rotulo, tipo: 'ok'|'erro'|'info', ms})
         aviso no canto, com botao opcional ("Desfazer"); some sozinho
     confirmar(texto, {ok, cancelar, perigo, titulo}) -> Promise<boolean>
         caixa no visual do Nous (no lugar do confirm() cinza do navegador);
         o botao repete o verbo ("Apagar", nao "OK")
     dialogo({id, titulo, largura, aoFechar}) -> {abrir, fechar, aberto, repintar}
         janela do Nous que acompanha o tema: Esc e clique fora fecham, o foco
         fica preso dentro e volta ao botao que abriu
   Tema: a classe .nous-tema da' as cores (--nd-*) do tema claro e do escuro, a
   partir dos tokens --pn-* do painel. Toast, confirmar e dialogo ja' usam.
   ===================================================================== */
(function () {
	'use strict';

	var g = 'rgba(200,150,46,';

	function injectStyle() {
		if (document.getElementById('nous-base-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-base-style';
		st.textContent =
			/* cores: as do painel, com reserva porque a tela de entrada nao tem painel.
			 * --nd-texto-ouro e' o ouro que se le' em cima do fundo (ouro claro no escuro) */
			'.nous-tema{--nd-bg:var(--pn-bg,#fff);--nd-alto:var(--pn-alto,#faf6ee);--nd-linha:var(--pn-linha,rgba(138,100,20,.16));' +
			'--nd-ouro:var(--pn-ouro,#a87a1c);--nd-texto-ouro:var(--pn-ouro2,#8a6414);--nd-txt:var(--pn-txt,#2a251e);' +
			'--nd-mut:var(--pn-mut,#7a6f5d);--nd-perigo:#a8322a;--nd-campo:#fff;--nd-veu:rgba(40,30,10,.38);--nd-sombra:rgba(60,45,15,.28)}' +
			'.dark .nous-tema{--nd-bg:var(--pn-bg,#141210);--nd-alto:var(--pn-alto,#1c1916);--nd-linha:var(--pn-linha,rgba(231,192,105,.12));' +
			'--nd-ouro:var(--pn-ouro,#c8962e);--nd-texto-ouro:var(--pn-ouro2,#e7c069);--nd-txt:var(--pn-txt,#ddd5c6);' +
			'--nd-mut:var(--pn-mut,#958a76);--nd-perigo:#f4a3a3;--nd-campo:rgba(0,0,0,.3);--nd-veu:rgba(0,0,0,.55);--nd-sombra:rgba(0,0,0,.55)}' +

			'#nous-toasts{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:10050;display:flex;' +
			'flex-direction:column;gap:8px;align-items:center;pointer-events:none;max-width:92vw}' +
			'.nous-toast{pointer-events:auto;display:flex;align-items:center;gap:10px;padding:9px 12px 9px 14px;border-radius:12px;' +
			'font:500 13px Inter,system-ui,sans-serif;color:var(--nd-txt);background:var(--nd-bg);border:1px solid ' + g + '.45);' +
			'box-shadow:0 10px 30px var(--nd-sombra);animation:nous-toast-in .18s ease-out}' +
			'.nous-toast.erro{border-color:rgba(220,80,80,.6)}.nous-toast.erro .nous-toast-i{color:var(--nd-perigo)}' +
			'.nous-toast-i{color:var(--nd-texto-ouro);font-weight:700}' +
			'.nous-toast button{border:1px solid ' + g + '.5);background:' + g + '.18);color:var(--nd-texto-ouro);border-radius:8px;' +
			'padding:4px 10px;font:600 12px Inter,system-ui,sans-serif;cursor:pointer}.nous-toast button:hover{background:' + g + '.32)}' +
			'.nous-toast.sai{opacity:0;transform:translateY(6px);transition:all .2s}' +
			'@keyframes nous-toast-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}' +
			'#nous-cf-ov{position:fixed;inset:0;z-index:10040;background:var(--nd-veu);display:flex;align-items:center;justify-content:center;' +
			'backdrop-filter:blur(2px)}' +
			'#nous-cf{width:380px;max-width:90vw;padding:18px 18px 14px;border-radius:16px;background:var(--nd-bg);' +
			'border:1px solid ' + g + '.45);box-shadow:0 16px 48px var(--nd-sombra);font:13px/1.55 Inter,system-ui,sans-serif;color:var(--nd-txt)}' +
			'#nous-cf h3{margin:0 0 6px;font:600 15px Cinzel,Georgia,serif;letter-spacing:.04em;color:var(--nd-texto-ouro)}' +
			'#nous-cf p{margin:0 0 14px;opacity:.85}#nous-cf .nous-cf-row{display:flex;gap:8px;justify-content:flex-end}' +
			'#nous-cf button{padding:7px 14px;border-radius:9px;cursor:pointer;font:600 13px Inter,system-ui,sans-serif;' +
			'border:1px solid ' + g + '.45);background:transparent;color:var(--nd-texto-ouro)}' +
			'#nous-cf button.ok{background:' + g + '.25)}#nous-cf button.ok:hover{background:' + g + '.4)}' +
			'#nous-cf button.ok.perigo{background:rgba(200,60,60,.14);border-color:rgba(220,80,80,.6);color:var(--nd-perigo)}' +
			'#nous-cf button.ok.perigo:hover{background:rgba(200,60,60,.28)}' +
			'#nous-cf button:focus-visible{outline:2px solid var(--nd-ouro);outline-offset:2px}' +

			/* dialogo: a moldura e as pecas que as janelas repetiam */
			'.nous-dlg-ov{position:fixed;inset:0;z-index:10001;background:var(--nd-veu);display:flex;align-items:center;' +
			'justify-content:center;backdrop-filter:blur(3px)}.nous-dlg-ov.nous-hidden{display:none}' +
			'.nous-dlg{width:500px;max-width:95vw;max-height:88vh;overflow-y:auto;font:13px/1.55 Inter,system-ui,sans-serif;color:var(--nd-txt);' +
			'background:var(--nd-bg);border:1px solid ' + g + '.4);border-radius:16px;box-shadow:0 16px 48px var(--nd-sombra);outline:none}' +
			'.nous-dlg-head{display:flex;align-items:center;padding:14px 16px 10px;border-bottom:1px solid var(--nd-linha)}' +
			'.nous-dlg-tit{flex:1;font:600 16px Cinzel,Georgia,serif;letter-spacing:.05em;color:var(--nd-texto-ouro)}' +
			'.nous-dlg-x{background:none;border:none;color:var(--nd-mut);cursor:pointer;font-size:19px}.nous-dlg-x:hover{color:var(--nd-txt)}' +
			'.nous-dlg button:focus-visible,.nous-dlg a:focus-visible{outline:2px solid var(--nd-ouro);outline-offset:2px}' +
			'.nous-dlg-corpo{padding:14px 16px 18px}.nous-dlg-corpo p{margin:0 0 10px}' +
			'.nous-dlg-corpo a:not(.no-gold){color:var(--nd-texto-ouro);word-break:break-all}' +
			'.nous-dlg-aviso{padding:10px 12px;border-radius:10px;margin:0 0 12px;border:1px solid ' + g + '.35);background:' + g + '.1)}' +
			'.nous-dlg-aviso.erro{border-color:rgba(220,80,80,.55);background:rgba(200,60,60,.12)}' +
			'.nous-dlg-aviso b{color:var(--nd-texto-ouro)}.nous-dlg-mut{font-size:12px;color:var(--nd-mut)}' +
			'.nous-dlg-btn{padding:8px 14px;border:1px solid ' + g + '.5);border-radius:9px;cursor:pointer;background:' + g + '.16);' +
			'color:var(--nd-texto-ouro);font:600 13px Inter,system-ui,sans-serif;margin:2px 8px 2px 0}.nous-dlg-btn:hover{background:' + g + '.3)}' +
			'.nous-dlg-btn:disabled{opacity:.5;cursor:default}.nous-dlg-btn.sec{background:transparent}' +
			'.nous-dlg-btn.perigo{border-color:rgba(220,80,80,.6);color:var(--nd-perigo);background:transparent}' +
			'.nous-dlg-h{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--nd-texto-ouro);margin:16px 0 6px}' +
			'.nous-dlg-in{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid ' + g + '.35);border-radius:9px;background:var(--nd-campo);' +
			'color:var(--nd-txt);font:13px ui-monospace,Consolas,monospace;margin:4px 0 8px}' +
			'.nous-dlg-qr{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:6px 0 10px}' +
			'.nous-dlg-qr img{width:176px;height:176px;background:#fff;padding:8px;border-radius:10px;image-rendering:pixelated}' +
			'.nous-dlg-ap{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--nd-linha)}' +
			'.nous-dlg-ap div:first-child{flex:1;min-width:0}.nous-dlg-ap b{display:block}' +
			'.nous-dlg-ap button{padding:4px 10px;border:1px solid rgba(220,80,80,.5);border-radius:8px;background:transparent;' +
			'color:var(--nd-perigo);cursor:pointer;font:600 12px Inter,system-ui,sans-serif}' +
			'.nous-dlg-pt{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;background:#3fbf78}' +
			'.nous-dlg-pt.off{background:#888}.nous-dlg-pt.erro{background:#e06060}';
		document.head.appendChild(st);
	}

	function box() {
		var b = document.getElementById('nous-toasts');
		if (!b) {
			b = document.createElement('div');
			b.id = 'nous-toasts';
			b.className = 'nous-tema';
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

	/* ------------------------------------------------------------ teclado
	 * Uma pilha so' para dialogo e confirmar: Esc e Tab valem para o que esta' por
	 * cima (a caixa de confirmacao abre em cima de um dialogo). Fica na window e
	 * nao no dialogo porque a janela e' repintada: se o elemento com foco some, o
	 * foco cai no body e a tecla nem passaria pelo dialogo. */
	var pilha = [];

	function focaveis(caixa) {
		return Array.prototype.filter.call(caixa.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),' +
			'select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])'), function (x) {
			return x.getClientRects().length > 0;
		});
	}

	function tecla(e) {
		var topo = pilha[pilha.length - 1];
		if (!topo || e.isComposing) return;
		if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); topo.esc(); return; }
		if (e.key !== 'Tab') return;
		var f = focaveis(topo.caixa), a = document.activeElement, i = f.indexOf(a);
		e.preventDefault();
		if (!f.length) { topo.caixa.focus(); return; }
		/* o proximo da lista, dando a volta; foco fora dos focaveis comeca pela ponta */
		f[i < 0 ? (e.shiftKey ? f.length - 1 : 0) : (i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
	}

	/* O Open WebUI chama focus() na caixa do chat sozinho (ao montar a tela, ao trocar
	 * de modelo): sem isto o que a pessoa digita aqui vai parar la'. O foco volta para
	 * onde estava. Se quem puxa de volta e' outra armadilha de foco (modal do Open
	 * WebUI), para depois de 20 tentativas por segundo em vez de travar a pagina numa
	 * briga (o Open WebUI sozinho chama focus() 5 vezes em seguida). */
	var puxadas = 0, desde = 0;
	function foco(e) {
		var topo = pilha[pilha.length - 1], t = e.target;
		if (!topo) return;
		if (topo.caixa.contains(t)) { topo.ultimo = t; return; }
		if (t.closest && t.closest('#nous-toasts')) return;   /* o "Desfazer" do aviso */
		var agora = Date.now();
		if (agora - desde > 1000) { desde = agora; puxadas = 0; }
		if (++puxadas > 20) return;
		(topo.ultimo && topo.ultimo.isConnected ? topo.ultimo : topo.caixa).focus();
	}

	function cercar(caixa, esc) {
		var item = { caixa: caixa, esc: esc, ultimo: null };
		if (!pilha.length) {
			window.addEventListener('keydown', tecla, true);
			document.addEventListener('focusin', foco, true);
		}
		pilha.push(item);
		return function () {
			pilha.splice(pilha.indexOf(item), 1);
			if (pilha.length) return;
			window.removeEventListener('keydown', tecla, true);
			document.removeEventListener('focusin', foco, true);
		};
	}

	/* Devolve o foco a quem abriu. O botao do painel pode ter sido refeito (a grade
	 * repinta) ou ter sumido (a gaveta fecha em tela estreita): procura o novo pelo
	 * data-abre, depois a janela de baixo, depois a coruja que reabre o painel. */
	function devolver(origem) {
		var abre = origem && origem.getAttribute && origem.getAttribute('data-abre');
		var topo = pilha[pilha.length - 1];
		var lista = [origem, abre && document.querySelector('[data-abre="' + abre + '"]'), topo && topo.caixa, document.getElementById('nous-pn-alca')];
		for (var i = 0; i < lista.length; i++) {
			var x = lista[i];
			if (!x || !x.isConnected || !x.focus) continue;
			x.focus();
			if (document.activeElement === x) return;
		}
	}

	/* ------------------------------------------------------------ dialogo
	 * Ids a partir de op.id, para os modulos acharem as pecas: <id>-ov (fundo),
	 * <id> (caixa), <id>-head, <id>-tit, <id>-close, <id>-body. */
	function dialogo(op) {
		var ov = null, caixa = null, corpo = null, origem = null, soltar = null;

		function montar() {
			if (ov && document.body.contains(ov)) return;
			ov = document.createElement('div');
			ov.id = op.id + '-ov';
			ov.className = 'nous-dlg-ov nous-tema nous-hidden';
			ov.innerHTML = '<div class="nous-dlg" id="' + op.id + '" role="dialog" aria-modal="true" aria-labelledby="' + op.id + '-tit" tabindex="-1">' +
				'<div class="nous-dlg-head" id="' + op.id + '-head"><span class="nous-dlg-tit" id="' + op.id + '-tit"></span>' +
				'<button class="nous-dlg-x" id="' + op.id + '-close" type="button" aria-label="Fechar">&#x2715;</button></div>' +
				'<div class="nous-dlg-corpo" id="' + op.id + '-body"></div></div>';
			caixa = ov.firstChild;
			corpo = caixa.lastChild;
			if (op.largura) caixa.style.width = op.largura + 'px';
			ov.querySelector('.nous-dlg-tit').textContent = op.titulo;
			ov.querySelector('.nous-dlg-x').addEventListener('click', fechar);
			/* so' o clique que comecou no fundo: arrastar para selecionar um texto
			 * e soltar fora da caixa nao fecha */
			var noFundo = false;
			ov.addEventListener('mousedown', function (e) { noFundo = e.target === ov; });
			ov.addEventListener('click', function (e) { if (e.target === ov && noFundo) fechar(); });
			document.body.appendChild(ov);
		}

		function aberto() { return !!soltar; }

		function abrir() {
			injectStyle();
			if (aberto()) return;
			montar();
			origem = document.activeElement;
			ov.classList.remove('nous-hidden');
			soltar = cercar(caixa, fechar);
			ov.querySelector('.nous-dlg-x').focus();
		}

		function fechar() {
			if (!aberto()) return;
			ov.classList.add('nous-hidden');
			soltar();
			soltar = null;
			if (op.aoFechar) op.aoFechar();
			devolver(origem);
			origem = null;
		}

		/* A janela refaz o corpo quando o estado muda. Sem isto, o foco cairia no
		 * body e o que a pessoa ja' digitou ou marcou sumiria. Campos sao achados
		 * pelo id; botoes, pelo texto. */
		function repintar(fn) {
			if (!aberto()) return;
			var a = document.activeElement, dentro = corpo.contains(a), campos = {};
			var idFoco = dentro ? a.id : '', texto = dentro && a.tagName === 'BUTTON' ? a.textContent : null;
			var cursor = dentro && a.tagName === 'INPUT' ? a.selectionStart : null;
			corpo.querySelectorAll('input[id],textarea[id]').forEach(function (x) { campos[x.id] = x.type === 'checkbox' ? x.checked : x.value; });
			fn(corpo);
			corpo.querySelectorAll('input[id],textarea[id]').forEach(function (x) {
				if (!(x.id in campos)) return;
				if (x.type === 'checkbox') x.checked = campos[x.id]; else x.value = campos[x.id];
			});
			if (!dentro || corpo.contains(document.activeElement)) return;
			var novo = idFoco ? document.getElementById(idFoco) : null;
			if (!novo && texto !== null) {
				novo = Array.prototype.filter.call(corpo.querySelectorAll('button:not([disabled])'), function (b) { return b.textContent === texto; })[0];
			}
			(novo || caixa).focus();
			if (novo && cursor !== null) { try { novo.setSelectionRange(cursor, cursor); } catch (e) {} }
		}

		return { abrir: abrir, fechar: fechar, aberto: aberto, repintar: repintar };
	}

	function confirmar(texto, op) {
		op = op || {};
		injectStyle();
		return new Promise(function (resolve) {
			var ov = document.createElement('div');
			var origem = document.activeElement, soltar = null;
			ov.id = 'nous-cf-ov';
			ov.className = 'nous-tema';
			ov.innerHTML = '<div id="nous-cf" role="alertdialog" aria-modal="true"><h3></h3><p></p><div class="nous-cf-row">' +
				'<button type="button" class="nao"></button><button type="button" class="ok"></button></div></div>';
			ov.querySelector('h3').textContent = op.titulo || 'Tem certeza?';
			ov.querySelector('p').textContent = texto;
			ov.querySelector('.nao').textContent = op.cancelar || 'Cancelar';
			var ok = ov.querySelector('.ok');
			ok.textContent = op.ok || 'Continuar';
			if (op.perigo) ok.classList.add('perigo');
			function fim(v) {
				soltar();
				ov.remove();
				devolver(origem);
				resolve(v);
			}
			ov.addEventListener('click', function (e) { if (e.target === ov) fim(false); });
			ov.querySelector('.nao').addEventListener('click', function () { fim(false); });
			ok.addEventListener('click', function () { fim(true); });
			document.body.appendChild(ov);
			soltar = cercar(ov.firstChild, function () { fim(false); });
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
	ui.dialogo = dialogo;
	ui.pede = pede;
	ui.aviso = aviso;
	if (document.head) injectTitulos();
	else document.addEventListener('DOMContentLoaded', injectTitulos);
})();
