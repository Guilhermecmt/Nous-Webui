/* =====================================================================
   Nous - Comparar modelos (v2.8). Botao "Comparar" no card Recursos -> a
   mesma pergunta para 2 a 4 modelos instalados, um de cada vez, com tempo
   e velocidade medidos pelo monitor (127.0.0.1:8990/compare). O usuario
   vota na melhor (pode ser as cegas) e o placar se acumula.
   A Arena do Open WebUI continua existindo para o duelo de 2 no chat.
   ===================================================================== */
(function () {
	'use strict';

	var MON = 'http://127.0.0.1:8990';
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var LETRAS = ['A', 'B', 'C', 'D'];
	var ov = null, tab = 'comparar';
	var rodada = null;  /* {models, prompt, res: {model: {...}}, votado, cego} */

	function injectStyle() {
		if (document.getElementById('nous-cp-style')) return;
		var g = 'rgba(200,150,46,';
		var st = document.createElement('style');
		st.id = 'nous-cp-style';
		st.textContent =
			'#nous-cmp-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);border-radius:8px;' +
			'cursor:pointer;background:transparent;color:#e7c069;font-weight:600;font-size:12px}#nous-cmp-open:hover{background:' + g + '.12)}' +
			'#nous-cp-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);display:flex;align-items:center;' +
			'justify-content:center;backdrop-filter:blur(3px)}#nous-cp-ov.nous-hidden{display:none}' +
			'#nous-cp{width:1100px;max-width:96vw;max-height:88vh;display:flex;flex-direction:column;font-family:Inter,system-ui,sans-serif;' +
			'font-size:13px;color:#eee;background:rgba(18,18,22,.97);border:1px solid ' + g + '.4);border-radius:16px;' +
			'box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-cp-head{display:flex;align-items:center;gap:6px;padding:12px 16px 10px;border-bottom:1px solid ' + g + '.15)}' +
			'#nous-cp-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'.nous-cp-tab{padding:5px 11px;border:1px solid ' + g + '.25);border-radius:8px;background:transparent;color:#ccc;cursor:pointer;font-size:12px}' +
			'.nous-cp-tab.on{background:' + g + '.2);color:#e7c069;font-weight:600}' +
			'#nous-cp-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px;margin-left:6px}' +
			'#nous-cp-body{flex:1;overflow:auto;padding:12px 16px 16px;display:flex;flex-direction:column;gap:10px}' +
			'.nous-cp-chips{display:flex;flex-wrap:wrap;gap:6px}' +
			'.nous-cp-chip{padding:4px 10px;border:1px solid rgba(255,255,255,.15);border-radius:14px;cursor:pointer;font-size:12px;user-select:none}' +
			'.nous-cp-chip.on{border-color:#c8962e;background:' + g + '.18);color:#e7c069}' +
			'#nous-cp-q{width:100%;box-sizing:border-box;min-height:62px;padding:8px 10px;background:rgba(255,255,255,.05);' +
			'border:1px solid ' + g + '.25);border-radius:9px;color:#eee;font:inherit;resize:vertical;outline:none}' +
			'.nous-cp-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px}' +
			'.nous-cp-btn{padding:6px 14px;border:1px solid ' + g + '.45);border-radius:8px;cursor:pointer;background:' + g + '.18);' +
			'color:#e7c069;font-weight:600;font-size:12px}.nous-cp-btn:disabled{opacity:.4;cursor:default}' +
			'.nous-cp-cols{display:grid;gap:10px;min-height:160px}' +
			'.nous-cp-col{display:flex;flex-direction:column;border:1px solid rgba(255,255,255,.1);border-radius:11px;' +
			'background:rgba(255,255,255,.03);min-width:0}' +
			'.nous-cp-col.win{border-color:#5fd693;box-shadow:0 0 0 1px #5fd693 inset}' +
			'.nous-cp-ch{padding:8px 10px;border-bottom:1px solid rgba(255,255,255,.08);font-weight:700;color:#e7c069;' +
			'white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
			'.nous-cp-st{font-size:11px;opacity:.65;font-weight:400;color:#ccc}' +
			'.nous-cp-tx{flex:1;overflow:auto;padding:9px 10px;white-space:pre-wrap;line-height:1.5;font-size:12.5px;max-height:52vh}' +
			'.nous-cp-ft{padding:7px 10px;border-top:1px solid rgba(255,255,255,.08)}' +
			'.nous-cp-tb{width:100%;border-collapse:collapse;font-size:12.5px}' +
			'.nous-cp-tb th{text-align:left;font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:#c8962e;padding:6px 8px}' +
			'.nous-cp-tb td{padding:7px 8px;border-top:1px solid rgba(255,255,255,.07)}' +
			'.nous-cp-bar{height:6px;border-radius:3px;background:#c8962e;display:inline-block;vertical-align:middle;margin-right:6px}' +
			'.nous-cp-dim{opacity:.6;font-size:12px;line-height:1.6}';
		document.head.appendChild(st);
	}

	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-cmp-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-cmp-open';
		b.type = 'button';
		b.textContent = '⚖ Comparar modelos';
		b.addEventListener('click', function () { open(); });
		body.appendChild(b);
	}

	function api(path, body) {
		return fetch(MON + path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
			: { cache: 'no-store' }).then(function (r) {
			return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || 'falhou'); return d; });
		});
	}

	function open(qual) {
		if (!ov || !document.body.contains(ov)) {
			ov = document.createElement('div');
			ov.id = 'nous-cp-ov';
			ov.innerHTML = '<div id="nous-cp"><div id="nous-cp-head"><span>⚖ Comparar modelos</span>' +
				'<button class="nous-cp-tab" data-t="comparar" type="button">Comparar</button>' +
				'<button class="nous-cp-tab" data-t="placar" type="button">Placar</button>' +
				'<button id="nous-cp-close" type="button" aria-label="Fechar">&#x2715;</button></div><div id="nous-cp-body"></div></div>';
			document.body.appendChild(ov);
			ov.addEventListener('click', function (e) { if (e.target === ov) ov.classList.add('nous-hidden'); });
			ov.querySelector('#nous-cp-close').addEventListener('click', function () { ov.classList.add('nous-hidden'); });
			ov.querySelectorAll('.nous-cp-tab').forEach(function (b) {
				b.addEventListener('click', function () { tab = b.getAttribute('data-t'); render(); });
			});
		}
		if (qual) tab = qual;
		ov.classList.remove('nous-hidden');
		render();
	}

	function render() {
		ov.querySelectorAll('.nous-cp-tab').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-t') === tab); });
		if (tab === 'placar') renderPlacar(); else renderComparar();
	}

	/* ---------------------------------------------------------- comparar */
	var escolhidos = [];
	var cego = true;

	function renderComparar() {
		var box = ov.querySelector('#nous-cp-body');
		if (rodada) { renderRodada(); return; }
		box.innerHTML = '<div class="nous-cp-dim">Carregando os modelos instalados...</div>';
		api('/installed').then(function (d) {
			var chat = d.chat || [];
			if (!d.online) { box.innerHTML = '<div class="nous-cp-dim">O motor de IA (Ollama) nao esta no ar. Abra o Nous pelo atalho.</div>'; return; }
			if (chat.length < 2) {
				box.innerHTML = '<div class="nous-cp-dim">Para comparar e\' preciso ter pelo menos 2 modelos de conversa instalados. ' +
					'Baixe outro na Loja de modelos.</div><div><button class="nous-cp-btn" id="nous-cp-loja" type="button">Abrir a Loja</button></div>';
				box.querySelector('#nous-cp-loja').addEventListener('click', function () {
					ov.classList.add('nous-hidden');
					if (UI.openStore) UI.openStore();
				});
				return;
			}
			escolhidos = escolhidos.filter(function (m) { return chat.indexOf(m) >= 0; });
			if (!escolhidos.length) escolhidos = chat.slice(0, Math.min(3, chat.length));
			box.innerHTML =
				'<div class="nous-cp-dim">Escolha de 2 a 4 modelos. Eles respondem um de cada vez (assim a placa de video ' +
				'fica inteira para cada um e a velocidade medida e\' justa).</div>' +
				'<div class="nous-cp-chips">' + chat.map(function (m) {
					return '<span class="nous-cp-chip' + (escolhidos.indexOf(m) >= 0 ? ' on' : '') + '" data-m="' + esc(m) + '">' + esc(m) + '</span>';
				}).join('') + '</div>' +
				'<textarea id="nous-cp-q" placeholder="A pergunta que todos vao responder. Ex.: Explique juros compostos para uma crianca de 10 anos."></textarea>' +
				'<div class="nous-cp-row"><button class="nous-cp-btn" id="nous-cp-go" type="button">Comparar</button>' +
				'<label style="display:flex;gap:6px;align-items:center;cursor:pointer"><input type="checkbox" id="nous-cp-cego"' +
				(cego ? ' checked' : '') + ' style="accent-color:#c8962e">As cegas (os nomes so\' aparecem depois do voto)</label>' +
				'<span class="nous-cp-dim" id="nous-cp-msg"></span></div>';
			box.querySelectorAll('.nous-cp-chip').forEach(function (c) {
				c.addEventListener('click', function () {
					var m = c.getAttribute('data-m'), i = escolhidos.indexOf(m);
					if (i >= 0) escolhidos.splice(i, 1);
					else if (escolhidos.length < 4) escolhidos.push(m);
					else { box.querySelector('#nous-cp-msg').textContent = 'No maximo 4 de cada vez.'; return; }
					c.classList.toggle('on', escolhidos.indexOf(m) >= 0);
					box.querySelector('#nous-cp-msg').textContent = '';
				});
			});
			box.querySelector('#nous-cp-cego').addEventListener('change', function (e) { cego = e.target.checked; });
			var q = box.querySelector('#nous-cp-q');
			q.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) start(); });
			box.querySelector('#nous-cp-go').addEventListener('click', start);
			function start() {
				var prompt = q.value.trim();
				var msgEl = box.querySelector('#nous-cp-msg');
				if (escolhidos.length < 2) { msgEl.textContent = 'Escolha pelo menos 2 modelos.'; return; }
				if (!prompt) { msgEl.textContent = 'Escreva a pergunta.'; q.focus(); return; }
				var ordem = escolhidos.slice();
				if (cego) ordem.sort(function () { return Math.random() - 0.5; });
				rodada = { models: ordem, prompt: prompt, res: {}, votado: null, cego: cego };
				renderRodada();
				correr(rodada);
			}
		}).catch(function () {
			box.innerHTML = '<div class="nous-cp-dim">O monitor do Nous nao responde. Feche o navegador e abra o Nous pelo atalho.</div>';
		});
	}

	function nome(r, m, i) {
		return r.cego && r.votado === null ? 'Modelo ' + LETRAS[i] : m;
	}

	function correr(r) {
		var i = 0;
		function proximo() {
			if (r !== rodada || i >= r.models.length) { if (r === rodada) renderRodada(); return; }
			var m = r.models[i++];
			r.res[m] = { estado: 'rodando' };
			renderRodada();
			api('/compare/run', { model: m, prompt: r.prompt }).then(function (d) {
				r.res[m] = { estado: 'ok', text: d.text, secs: d.secs, load: d.load, tokens: d.tokens, tps: d.tps };
			}).catch(function (e) {
				r.res[m] = { estado: 'erro', erro: e.message };
			}).then(proximo);
		}
		proximo();
	}

	function fmt(n) { return String(n).replace('.', ','); }

	function renderRodada() {
		if (!ov || tab !== 'comparar') return;
		var r = rodada, box = ov.querySelector('#nous-cp-body');
		var prontos = r.models.filter(function (m) { return r.res[m] && r.res[m].estado !== 'rodando'; }).length;
		var acabou = prontos === r.models.length;
		var okCount = r.models.filter(function (m) { return r.res[m] && r.res[m].estado === 'ok'; }).length;
		var html = '<div class="nous-cp-row"><b style="flex:1;font-weight:600">' + esc(r.prompt) + '</b>' +
			'<button class="nous-cp-btn" id="nous-cp-nova" type="button">Nova comparacao</button></div>' +
			'<div class="nous-cp-cols" style="grid-template-columns:repeat(' + r.models.length + ',minmax(0,1fr))">';
		r.models.forEach(function (m, i) {
			var x = r.res[m] || { estado: 'fila' };
			var st = x.estado === 'fila' ? 'na fila' : x.estado === 'rodando' ? 'respondendo...' : x.estado === 'erro' ? 'erro' :
				fmt(x.secs) + ' s' + (x.tps ? ' · ' + fmt(x.tps) + ' tokens/s' : '') + (x.load >= 1 ? ' · ' + fmt(x.load) + ' s carregando' : '');
			html += '<div class="nous-cp-col' + (r.votado === m ? ' win' : '') + '"><div class="nous-cp-ch">' + esc(nome(r, m, i)) +
				(r.votado === m ? ' ✓' : '') + '<div class="nous-cp-st">' + esc(st) + '</div></div>' +
				'<div class="nous-cp-tx">' + (x.estado === 'ok' ? esc(x.text || '(resposta vazia)') :
					x.estado === 'erro' ? '<span style="color:#f08080">' + esc(x.erro) + '</span>' : '') + '</div>' +
				(acabou && r.votado === null && okCount >= 2 && x.estado === 'ok'
					? '<div class="nous-cp-ft"><button class="nous-cp-btn" data-v="' + esc(m) + '" type="button" style="width:100%">Esta foi a melhor</button></div>' : '') +
				'</div>';
		});
		html += '</div>';
		if (acabou && r.votado === null && okCount >= 2)
			html += '<div class="nous-cp-row"><button class="nous-cp-btn" data-v="" type="button">Empate</button>' +
				'<span class="nous-cp-dim">Seu voto vai para o placar.</span></div>';
		else if (r.votado !== null)
			html += '<div class="nous-cp-row nous-cp-dim">' + (r.votado ? 'Voto registrado: ' + esc(r.votado) + '.' : 'Empate registrado.') +
				' Veja a aba Placar.</div>';
		box.innerHTML = html;
		box.querySelector('#nous-cp-nova').addEventListener('click', function () { rodada = null; renderComparar(); });
		box.querySelectorAll('[data-v]').forEach(function (b) {
			b.addEventListener('click', function () { votar(r, b.getAttribute('data-v')); });
		});
	}

	function votar(r, winner) {
		var ok = r.models.filter(function (m) { return r.res[m] && r.res[m].estado === 'ok'; });
		var tps = {};
		ok.forEach(function (m) { if (r.res[m].tps) tps[m] = r.res[m].tps; });
		api('/compare/vote', { models: ok, winner: winner, tps: tps }).then(function () {
			r.votado = winner;
			renderRodada();
		}).catch(function (e) { alert('Nao deu para registrar o voto: ' + e.message); });
	}

	/* ---------------------------------------------------------- placar */
	function renderPlacar() {
		var box = ov.querySelector('#nous-cp-body');
		box.innerHTML = '<div class="nous-cp-dim">Carregando...</div>';
		api('/compare/score').then(function (d) {
			var p = d.placar || [];
			if (!p.length) {
				box.innerHTML = '<div class="nous-cp-dim">Ainda sem votos. Na aba Comparar, faca a mesma pergunta para alguns modelos ' +
					'e escolha a melhor resposta: o placar mostra qual modelo combina mais com voce e qual e\' mais rapido nesta maquina.</div>';
				return;
			}
			var maxTps = Math.max.apply(null, p.map(function (x) { return x.tps || 0; })) || 1;
			box.innerHTML = '<table class="nous-cp-tb"><tr><th>Modelo</th><th>Vitorias</th><th>Aproveitamento</th><th>Velocidade media</th></tr>' +
				p.map(function (x, i) {
					return '<tr><td>' + (i === 0 && x.vitorias ? '🏆 ' : '') + esc(x.model) + '</td>' +
						'<td>' + x.vitorias + ' de ' + x.jogos + (x.empates ? ' <span class="nous-cp-dim">(' + x.empates + ' empate' + (x.empates > 1 ? 's' : '') + ')</span>' : '') + '</td>' +
						'<td><span class="nous-cp-bar" style="width:' + Math.max(2, x.taxa) + 'px"></span>' + x.taxa + '%</td>' +
						'<td>' + (x.tps ? '<span class="nous-cp-bar" style="background:#5fa8d6;width:' + Math.max(2, Math.round(100 * x.tps / maxTps)) + 'px"></span>' +
							fmt(x.tps) + ' tokens/s' : '—') + '</td></tr>';
				}).join('') + '</table>' +
				'<div class="nous-cp-row"><span class="nous-cp-dim" style="flex:1">Velocidade medida nesta maquina. Um token e\' mais ou menos 3/4 de uma palavra.</span>' +
				'<button class="nous-cp-btn" id="nous-cp-zera" type="button">Zerar placar</button></div>';
			box.querySelector('#nous-cp-zera').addEventListener('click', function () {
				if (!confirm('Apagar todos os votos do placar?')) return;
				api('/compare/reset', {}).then(renderPlacar);
			});
		}).catch(function () {
			box.innerHTML = '<div class="nous-cp-dim">O monitor do Nous nao responde.</div>';
		});
	}

	function start() {
		injectStyle();
		window.NousCompare = { open: open };
		setInterval(ensureButton, 1000);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
