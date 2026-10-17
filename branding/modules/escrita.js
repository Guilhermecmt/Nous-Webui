/* =====================================================================
   Nous - Documentos (v2.9). Escrever ao lado do chat: cartas, curriculos,
   trabalhos, posts. A IA propoe as mudancas (corrigir, deixar formal, mais
   curto, topicos -> texto, continuar ou o que voce pedir) e cada uma aparece
   riscada/sublinhada para voce aceitar ou recusar. Nada muda sem o seu OK.
   Selecione um trecho para mudar so' ele. Salva sozinho, guarda versoes e
   exporta para Word, PDF ou Markdown. Tudo pelo monitor (8990), local.
   ===================================================================== */
(function () {
	'use strict';

	var MON = 'http://127.0.0.1:8990';
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var ov = null, cur = null, saveTimer = null, review = null, busy = false, criando = false;

	var CHIPS = [['corrigir', '✓ Corrigir portugues'], ['formal', '👔 Mais formal'], ['simples', '🙂 Mais simples'],
		['curto', '✂ Mais curto'], ['topicos', '¶ Topicos em texto'], ['organizar', '☰ Organizar com titulos'],
		['continuar', '➜ Continuar escrevendo']];

	function injectStyle() {
		if (document.getElementById('nous-dc-style')) return;
		var g = 'rgba(200,150,46,';
		var css =
			'#nous-docs-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);border-radius:8px;' +
			'cursor:pointer;background:transparent;color:#e7c069;font-weight:600;font-size:12px}#nous-docs-open:hover{background:' + g + '.12)}' +
			'#nous-dc-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);display:flex;align-items:center;' +
			'justify-content:center;backdrop-filter:blur(3px)}#nous-dc-ov.nous-hidden{display:none}' +
			'#nous-dc{width:1000px;max-width:96vw;height:88vh;display:flex;flex-direction:column;font-family:Inter,system-ui,sans-serif;' +
			'font-size:13px;color:#eee;background:rgba(18,18,22,.97);border:1px solid ' + g + '.4);border-radius:16px;' +
			'box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-dc-head{display:flex;align-items:center;padding:12px 16px 10px;border-bottom:1px solid ' + g + '.15)}' +
			'#nous-dc-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'#nous-dc-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px}#nous-dc-close:hover{color:#eee}' +
			'#nous-dc-main{flex:1;display:flex;min-height:0}' +
			'#nous-dc-side{width:210px;flex-shrink:0;border-right:1px solid rgba(255,255,255,.07);display:flex;flex-direction:column;padding:10px}' +
			'#nous-dc-list{flex:1;overflow-y:auto;margin-top:8px}' +
			'.nous-dc-item{padding:7px 8px;border-radius:8px;cursor:pointer;margin-bottom:3px;position:relative}' +
			'.nous-dc-item:hover{background:rgba(255,255,255,.05)}.nous-dc-item.on{background:' + g + '.16)}' +
			'.nous-dc-item b{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:16px}' +
			'.nous-dc-item small{font-size:10px;opacity:.55}' +
			'.nous-dc-del{position:absolute;right:4px;top:6px;background:none;border:none;color:#777;cursor:pointer;font-size:11px;display:none}' +
			'.nous-dc-item:hover .nous-dc-del{display:block}.nous-dc-del:hover{color:#f08080}' +
			'#nous-dc-doc{flex:1;display:flex;flex-direction:column;min-width:0;padding:10px 14px 12px}' +
			'#nous-dc-title{width:100%;box-sizing:border-box;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,.08);' +
			'color:#fff;font-size:18px;font-weight:700;padding:4px 2px 8px;outline:none}#nous-dc-title:focus{border-color:' + g + '.5)}' +
			'#nous-dc-bar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:8px 0}' +
			'.nous-dc-btn{padding:5px 10px;border:1px solid ' + g + '.4);border-radius:8px;cursor:pointer;background:' + g + '.14);' +
			'color:#e7c069;font-weight:600;font-size:12px;white-space:nowrap}.nous-dc-btn:hover{background:' + g + '.3)}' +
			'.nous-dc-btn.ghost{background:transparent}.nous-dc-btn:disabled{opacity:.4;cursor:default}' +
			'.nous-dc-btn.on{background:' + g + '.32)}' +
			'#nous-dc-status{margin-left:auto;font-size:11px;opacity:.55}' +
			'#nous-dc-text,#nous-dc-view,#nous-dc-rev{flex:1;min-height:0;box-sizing:border-box;width:100%;padding:12px 14px;border-radius:10px;' +
			'background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);color:#eee;font:14px/1.65 Inter,system-ui,sans-serif;overflow-y:auto}' +
			'#nous-dc-text{resize:none;outline:none}#nous-dc-text:focus{border-color:' + g + '.4)}' +
			'#nous-dc-rev{white-space:pre-wrap;word-wrap:break-word}' +
			'.nous-dc-sg{border-radius:4px;padding:1px 2px;cursor:pointer}' +
			'.nous-dc-sg del{color:#f39b9b;background:rgba(220,60,60,.15);text-decoration:line-through}' +
			'.nous-dc-sg ins{color:#7fe0a6;background:rgba(58,208,122,.15);text-decoration:none}' +
			'.nous-dc-sg.ok del,.nous-dc-sg.no ins{display:none}.nous-dc-sg.ok ins,.nous-dc-sg.no del{background:none;color:inherit;text-decoration:none}' +
			/* decidida: sem folga em volta e so' um sublinhado (verde aceita, cinza recusada) */
			'.nous-dc-sg.ok,.nous-dc-sg.no{padding:0;border-radius:0}.nous-dc-sg.ok{border-bottom:2px solid rgba(58,208,122,.45)}' +
			'.nous-dc-sg.no{border-bottom:2px dotted rgba(160,160,160,.45)}' +
			'.nous-dc-sg:not(.ok):not(.no){outline:1px dashed ' + g + '.5)}' +
			'.nous-dc-yn{display:inline-flex;gap:2px;margin:0 3px;vertical-align:1px}.nous-dc-sg.ok .nous-dc-yn,.nous-dc-sg.no .nous-dc-yn{display:none}' +
			'.nous-dc-yn button{border:none;border-radius:4px;cursor:pointer;font-size:10px;padding:1px 5px;font-weight:700}' +
			'.nous-dc-y{background:rgba(58,208,122,.25);color:#7fe0a6}.nous-dc-n{background:rgba(220,60,60,.22);color:#f39b9b}' +
			'#nous-dc-revbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px;padding:8px 10px;border-radius:10px;' +
			'background:' + g + '.1);border:1px solid ' + g + '.3);font-size:12px}#nous-dc-revbar span{flex:1}' +
			'#nous-dc-ai{margin-top:10px;border-top:1px solid rgba(255,255,255,.07);padding-top:9px}' +
			'#nous-dc-chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:7px}' +
			'.nous-dc-chip{padding:4px 10px;border-radius:99px;border:1px solid ' + g + '.35);background:transparent;color:#e7c069;font-size:11px;cursor:pointer}' +
			'.nous-dc-chip:hover{background:' + g + '.18)}.nous-dc-chip:disabled{opacity:.4;cursor:default}' +
			'#nous-dc-askrow{display:flex;gap:6px}' +
			'#nous-dc-ask,#nous-dc-model{box-sizing:border-box;padding:7px 10px;background:rgba(255,255,255,.07);border:1px solid ' + g + '.28);' +
			'border-radius:8px;color:#eee;font-size:12px;outline:none;color-scheme:dark}#nous-dc-ask{flex:1}#nous-dc-model{max-width:150px}' +
			'#nous-dc-hint{font-size:11px;opacity:.55;margin-top:5px}' +
			'#nous-dc-view h1,#nous-dc-view h2,#nous-dc-view h3{color:#e7c069;margin:.6em 0 .3em}#nous-dc-view p{margin:.5em 0}' +
			'#nous-dc-view blockquote{border-left:3px solid #c8962e;margin:.5em 0;padding-left:10px;opacity:.85}' +
			'#nous-dc-view a{color:#9db8ee}#nous-dc-view code{background:rgba(255,255,255,.08);padding:1px 4px;border-radius:4px}' +
			'.nous-dc-pop{position:absolute;z-index:3;background:rgba(24,24,28,.99);border:1px solid ' + g + '.4);border-radius:10px;' +
			'padding:6px;box-shadow:0 8px 24px rgba(0,0,0,.5);min-width:180px}' +
			'.nous-dc-pop button{display:block;width:100%;text-align:left;background:none;border:none;color:#eee;padding:6px 8px;border-radius:6px;cursor:pointer;font-size:12px}' +
			'.nous-dc-pop button:hover{background:' + g + '.18)}.nous-dc-pop small{opacity:.55}' +
			'.nous-dc-empty{opacity:.55;font-size:12px;line-height:1.6;padding:10px 4px}' +
			'.nous-dc-bad{color:#f08080}' +
			'@media (max-width:760px){#nous-dc-side{display:none}#nous-dc{height:94vh}}';
		var st = document.createElement('style');
		st.id = 'nous-dc-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-docs-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-docs-open';
		b.type = 'button';
		b.textContent = '📝 Documentos';
		b.addEventListener('click', function () { open(); });
		body.appendChild(b);
	}

	function $(sel) { return ov.querySelector(sel); }

	function build() {
		if (ov && document.body.contains(ov)) return;
		ov = document.createElement('div');
		ov.id = 'nous-dc-ov';
		ov.className = 'nous-hidden';
		ov.innerHTML = '<div id="nous-dc"><div id="nous-dc-head"><span>📝 Documentos</span>' +
			'<button id="nous-dc-close" type="button" aria-label="Fechar">&#x2715;</button></div>' +
			'<div id="nous-dc-main"><div id="nous-dc-side">' +
			'<button class="nous-dc-btn" id="nous-dc-new" type="button">+ Novo documento</button>' +
			'<label class="nous-dc-btn ghost" style="margin-top:5px;text-align:center">📂 Abrir arquivo' +
			'<input id="nous-dc-file" type="file" accept=".txt,.md,.markdown,.docx,.pdf,.html,.htm" style="display:none"></label>' +
			'<div id="nous-dc-list"></div></div>' +
			'<div id="nous-dc-doc"><input id="nous-dc-title" placeholder="Titulo do documento" maxlength="120">' +
			'<div id="nous-dc-bar">' +
			'<button class="nous-dc-btn ghost on" id="nous-dc-mode-w" type="button">✍ Escrever</button>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-mode-v" type="button">👁 Ver como fica</button>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-exp" type="button">⬇ Baixar</button>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-vers" type="button">🕘 Versoes</button>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-chat" type="button">💬 Usar no chat</button>' +
			'<span id="nous-dc-status"></span></div>' +
			'<div id="nous-dc-revbar" style="display:none"></div>' +
			'<textarea id="nous-dc-text" spellcheck="true" lang="pt-BR" placeholder="Escreva aqui... ou cole suas anotacoes e peca para a IA transformar em texto."></textarea>' +
			'<div id="nous-dc-view" style="display:none"></div><div id="nous-dc-rev" style="display:none"></div>' +
			'<div id="nous-dc-ai"><div id="nous-dc-chips"></div>' +
			'<div id="nous-dc-askrow"><input id="nous-dc-ask" placeholder="Ou diga o que mudar: &quot;troque voce por senhor&quot;, &quot;deixe mais animado&quot;...">' +
			'<select id="nous-dc-model" title="Modelo que escreve"></select>' +
			'<button class="nous-dc-btn" id="nous-dc-go" type="button">Pedir a IA</button></div>' +
			'<div id="nous-dc-hint">Dica: selecione um trecho para a IA mexer so\' nele. Ela so\' sugere: voce aceita ou recusa cada mudanca.</div>' +
			'</div></div></div></div>';
		document.body.appendChild(ov);
		ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
		$('#nous-dc-close').addEventListener('click', close);
		$('#nous-dc-new').addEventListener('click', function () { novo('', ''); });
		$('#nous-dc-file').addEventListener('change', function (e) {
			var f = e.target.files && e.target.files[0];
			e.target.value = '';
			if (f) importar(f);
		});
		$('#nous-dc-title').addEventListener('input', agendarSalvar);
		$('#nous-dc-text').addEventListener('input', agendarSalvar);
		$('#nous-dc-mode-w').addEventListener('click', function () { modo('w'); });
		$('#nous-dc-mode-v').addEventListener('click', function () { modo('v'); });
		$('#nous-dc-exp').addEventListener('click', function (e) { menuExportar(e.currentTarget); });
		$('#nous-dc-vers').addEventListener('click', function (e) { menuVersoes(e.currentTarget); });
		$('#nous-dc-chat').addEventListener('click', usarNoChat);
		$('#nous-dc-chips').innerHTML = CHIPS.map(function (c) {
			return '<button class="nous-dc-chip" type="button" data-k="' + c[0] + '">' + c[1] + '</button>';
		}).join('');
		$('#nous-dc-chips').addEventListener('click', function (e) {
			var b = e.target.closest('[data-k]');
			if (b) pedir(b.getAttribute('data-k'), b.textContent);
		});
		$('#nous-dc-go').addEventListener('click', function () {
			var t = $('#nous-dc-ask').value.trim();
			if (t) pedir(t, t);
		});
		$('#nous-dc-ask').addEventListener('keydown', function (e) {
			if (e.key === 'Enter' && this.value.trim()) pedir(this.value.trim(), this.value.trim());
		});
		$('#nous-dc-model').addEventListener('change', function () {
			try { localStorage.setItem('nous-docs-model', this.value); } catch (e) {}
		});
		document.addEventListener('keydown', function (e) {
			if (e.key === 'Escape' && ov && !ov.classList.contains('nous-hidden') && !review && !document.querySelector('.nous-dc-pop')) close();
		});
	}

	/* id: abre esse documento; false: nao abre nenhum sozinho (quem chamou abre) */
	function open(id) {
		build();
		ov.classList.remove('nous-hidden');
		carregarModelos();
		listar(function (docs) {
			if (id) abrir(id);
			else if (id !== false && !cur) {
				if (docs.length) abrir(docs[0].id);
				else novo('', '');
			}
		});
	}

	function close() {
		if (review && !confirm('Fechar sem decidir as sugestoes da IA? O texto fica como estava.')) return;
		review = null;
		salvarAgora();
		fecharPops();
		ov.classList.add('nous-hidden');
	}

	function status(t, bad) {
		var s = $('#nous-dc-status');
		s.textContent = t || '';
		s.classList.toggle('nous-dc-bad', !!bad);
	}

	function quando(ts) {
		var d = new Date(ts * 1000), hoje = new Date();
		if (d.toDateString() === hoje.toDateString()) return 'hoje ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
		return d.toLocaleDateString('pt-BR');
	}

	function listar(cb) {
		fetch(MON + '/docs', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
			var docs = d.docs || [], box = $('#nous-dc-list');
			box.innerHTML = docs.length ? docs.map(function (x) {
				return '<div class="nous-dc-item' + (cur && cur.id === x.id ? ' on' : '') + '" data-id="' + esc(x.id) + '" title="' + esc(x.inicio) + '">' +
					'<b>' + esc(x.titulo) + '</b><small>' + quando(x.atualizado) + ' · ' + x.palavras + ' palavras</small>' +
					'<button class="nous-dc-del" type="button" title="Apagar" data-del="' + esc(x.id) + '">🗑</button></div>';
			}).join('') : '<div class="nous-dc-empty">Seus documentos aparecem aqui.</div>';
			box.querySelectorAll('[data-id]').forEach(function (el) {
				el.addEventListener('click', function (e) {
					if (e.target.closest('[data-del]')) return;
					if (review) { status('Decida as sugestoes primeiro.', true); return; }
					salvarAgora();
					abrir(el.getAttribute('data-id'));
				});
			});
			box.querySelectorAll('[data-del]').forEach(function (b) {
				b.addEventListener('click', function () {
					if (!confirm('Apagar este documento? Nao da para desfazer.')) return;
					var id = b.getAttribute('data-del');
					fetch(MON + '/docs/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: id }) })
						.then(function () { if (cur && cur.id === id) cur = null; listar(function (ds) { if (!cur) { if (ds.length) abrir(ds[0].id); else novo('', ''); } }); });
				});
			});
			if (cb) cb(docs);
		}).catch(function () {
			$('#nous-dc-list').innerHTML = '<div class="nous-dc-empty nous-dc-bad">O monitor do Nous nao esta no ar. Abra o Nous pelo atalho.</div>';
			if (cb) cb([]);
		});
	}

	function mostrar(doc) {
		cur = doc;
		review = null;
		$('#nous-dc-title').value = doc.titulo === 'Sem titulo' ? '' : (doc.titulo || '');
		$('#nous-dc-text').value = doc.texto || '';
		modo('w');
		status(doc.id ? 'Salvo' : '');
		ov.querySelectorAll('.nous-dc-item').forEach(function (el) { el.classList.toggle('on', el.getAttribute('data-id') === doc.id); });
	}

	function abrir(id) {
		fetch(MON + '/docs/get?id=' + encodeURIComponent(id), { cache: 'no-store' }).then(function (r) { return r.json(); })
			.then(function (d) { if (!d.error) mostrar(d); });
	}

	/* Documento novo (tambem usado pelo chat: "📝 Abrir como documento"). */
	function novo(titulo, texto) {
		if (review) { status('Decida as sugestoes primeiro.', true); return; }
		salvarAgora();
		mostrar({ id: '', titulo: titulo || '', texto: texto || '', versoes: [] });
		if (texto) salvarAgora();
		setTimeout(function () { (titulo ? $('#nous-dc-text') : $('#nous-dc-title')).focus(); }, 50);
	}

	function agendarSalvar() {
		if (!cur) return;
		status('Editando...');
		clearTimeout(saveTimer);
		saveTimer = setTimeout(function () { salvarAgora(); }, 1200);
	}

	/* motivo: tira uma foto da versao anterior (antes da IA, de restaurar...) */
	function salvarAgora(motivo, cb) {
		clearTimeout(saveTimer);
		saveTimer = null;
		if (!cur || review) { if (cb) cb(); return; }
		if (criando) { saveTimer = setTimeout(function () { salvarAgora(motivo, cb); }, 400); return; }
		var titulo = $('#nous-dc-title').value.trim(), texto = $('#nous-dc-text').value;
		if (!cur.id && !texto.trim() && !titulo) { if (cb) cb(); return; }
		if (cur.id && !motivo && titulo === (cur.titulo === 'Sem titulo' ? '' : cur.titulo) && texto === cur.texto) {
			status('Salvo');
			if (cb) cb();
			return;
		}
		var novoDoc = !cur.id, alvo = cur;
		criando = novoDoc;  /* sem id ainda: outro salvar agora criaria um segundo documento */
		cur.titulo = titulo || 'Sem titulo';
		cur.texto = texto;
		status('Salvando...');
		fetch(MON + '/docs/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ id: cur.id, titulo: titulo, texto: texto, motivo: motivo || '' }) })
			.then(function (r) { return r.json(); }).then(function (d) {
				if (d.error) throw new Error(d.error);
				alvo.id = d.id;
				alvo.versoes = d.versoes;
				if (alvo === cur) status('Salvo');
				if (novoDoc || motivo) listar();
			}).catch(function () { status('Nao consegui salvar (o monitor esta no ar?)', true); })
			.then(function () { criando = false; if (cb) cb(); });
	}

	function modo(m) {
		if (review && m !== 'r') return;
		$('#nous-dc-text').style.display = m === 'w' ? '' : 'none';
		$('#nous-dc-view').style.display = m === 'v' ? '' : 'none';
		$('#nous-dc-rev').style.display = m === 'r' ? '' : 'none';
		$('#nous-dc-revbar').style.display = m === 'r' ? '' : 'none';
		$('#nous-dc-mode-w').classList.toggle('on', m === 'w');
		$('#nous-dc-mode-v').classList.toggle('on', m === 'v');
		['#nous-dc-mode-w', '#nous-dc-mode-v', '#nous-dc-exp', '#nous-dc-vers', '#nous-dc-chat', '#nous-dc-go']
			.forEach(function (s) { $(s).disabled = m === 'r'; });
		ov.querySelectorAll('.nous-dc-chip').forEach(function (b) { b.disabled = m === 'r'; });
		if (m === 'v') $('#nous-dc-view').innerHTML = markdown($('#nous-dc-text').value) || '<p style="opacity:.5">Documento vazio.</p>';
	}

	/* Markdown minimo e seguro para "Ver como fica": escapa tudo antes. */
	function inline(s) {
		return esc(s)
			.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>')
			.replace(/`([^`]+)`/g, '<code>$1</code>')
			.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s"]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
	}
	function markdown(md) {
		var out = [], list = null, para = [];
		function flush() {
			if (para.length) { out.push('<p>' + para.map(inline).join('<br>') + '</p>'); para = []; }
			if (list) { out.push('</' + list + '>'); list = null; }
		}
		(md || '').split('\n').forEach(function (ln) {
			var m;
			if (!ln.trim()) { flush(); return; }
			if ((m = ln.match(/^(#{1,3})\s+(.*)$/))) { flush(); out.push('<h' + m[1].length + '>' + inline(m[2]) + '</h' + m[1].length + '>'); return; }
			if (/^(-{3,}|\*{3,})\s*$/.test(ln)) { flush(); out.push('<hr>'); return; }
			if ((m = ln.match(/^>\s?(.*)$/))) { flush(); out.push('<blockquote>' + inline(m[1]) + '</blockquote>'); return; }
			if ((m = ln.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/))) {
				var tag = m[1] ? 'ol' : 'ul';
				if (para.length) { out.push('<p>' + para.map(inline).join('<br>') + '</p>'); para = []; }
				if (list !== tag) { if (list) out.push('</' + list + '>'); out.push('<' + tag + '>'); list = tag; }
				out.push('<li>' + inline(m[2]) + '</li>');
				return;
			}
			if (list) { out.push('</' + list + '>'); list = null; }
			para.push(ln);
		});
		flush();
		return out.join('');
	}

	/* ------------------------------------------------------------- modelos */
	function carregarModelos() {
		fetch(MON + '/installed', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
			var sel = $('#nous-dc-model'), pref = '';
			try { pref = localStorage.getItem('nous-docs-model') || ''; } catch (e) {}
			var chat = (d.chat || []).filter(function (n) { return !/[-:]cloud$/i.test(n); });
			sel.innerHTML = chat.length ? chat.map(function (n) {
				return '<option' + (n === pref ? ' selected' : '') + '>' + esc(n) + '</option>';
			}).join('') : '<option value="">(nenhum modelo)</option>';
		}).catch(function () {});
	}

	/* ------------------------------------------------------------------ IA */
	function pedir(instrucao, rotulo) {
		if (busy || review) return;
		var ta = $('#nous-dc-text');
		if ($('#nous-dc-view').style.display !== 'none') modo('w');
		var texto = ta.value, ini = ta.selectionStart, fim = ta.selectionEnd;
		var sel = fim > ini && texto.slice(ini, fim).trim();
		if (!texto.trim() && instrucao !== 'continuar') { status('Escreva algo primeiro (ou cole topicos).', true); ta.focus(); return; }
		busy = true;
		var t0 = Date.now();
		var tick = setInterval(function () {
			status('✨ A IA esta escrevendo' + (sel ? ' (so\' o trecho selecionado)' : '') + '... ' + Math.round((Date.now() - t0) / 1000) + 's');
		}, 500);
		ov.querySelectorAll('.nous-dc-chip, #nous-dc-go').forEach(function (b) { b.disabled = true; });
		var body = { texto: texto, instrucao: instrucao, model: $('#nous-dc-model').value };
		if (sel) { body.ini = ini; body.fim = fim; }
		fetch(MON + '/docs/ai', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
			.then(function (r) { return r.json(); }).then(function (d) {
				if (d.error) throw new Error(d.error);
				if (ta.value !== texto) throw new Error('Voce mudou o texto enquanto a IA escrevia. Peca de novo.');
				if (!d.mudancas) { status('A IA nao sugeriu nenhuma mudanca.'); return; }
				$('#nous-dc-ask').value = '';
				mostrarSugestoes(d, rotulo);
			}).catch(function (e) { status(e.message || 'A IA nao respondeu.', true); })
			.then(function () {
				clearInterval(tick);
				busy = false;
				if (!review) ov.querySelectorAll('.nous-dc-chip, #nous-dc-go').forEach(function (b) { b.disabled = false; });
				if (!review && /escrevendo/.test($('#nous-dc-status').textContent)) status('');
			});
	}

	function mostrarSugestoes(d, rotulo) {
		review = { segs: d.segs, rotulo: rotulo, dec: {} };
		var box = $('#nous-dc-rev'), html = '';
		d.segs.forEach(function (s, i) {
			if (s.t === '=') { html += esc(s.s); return; }
			html += '<span class="nous-dc-sg" data-i="' + i + '" title="Clique para alternar">' +
				(s.a ? '<del>' + esc(s.a) + '</del>' : '') + (s.b ? '<ins>' + esc(s.b) + '</ins>' : '') +
				'<span class="nous-dc-yn"><button class="nous-dc-y" type="button" data-ok="' + i + '" title="Aceitar">✓</button>' +
				'<button class="nous-dc-n" type="button" data-no="' + i + '" title="Recusar">✕</button></span></span>';
		});
		box.innerHTML = html;
		box.onclick = function (e) {
			var b = e.target.closest('[data-ok],[data-no]'), sg = e.target.closest('.nous-dc-sg');
			if (!sg) return;
			var i = sg.getAttribute('data-i');
			if (b) review.dec[i] = b.hasAttribute('data-ok');
			else if (review.dec[i] !== undefined) review.dec[i] = !review.dec[i];
			else return;
			sg.classList.toggle('ok', review.dec[i] === true);
			sg.classList.toggle('no', review.dec[i] === false);
			barra();
		};
		modo('r');
		barra();
		status('');
		var first = box.querySelector('.nous-dc-sg');
		if (first) first.scrollIntoView({ block: 'center' });
	}

	function barra() {
		var total = review.segs.filter(function (s) { return s.t === '~'; }).length;
		var feitas = Object.keys(review.dec).length;
		var bar = $('#nous-dc-revbar');
		bar.innerHTML = '<span><b>' + esc(review.rotulo) + '</b>: ' + total + ' sugest' + (total === 1 ? 'ao' : 'oes') +
			' · ' + feitas + ' decidida' + (feitas === 1 ? '' : 's') + '</span>' +
			'<button class="nous-dc-btn" type="button" data-all="1">✓ Aceitar todas</button>' +
			'<button class="nous-dc-btn ghost" type="button" data-all="0">✕ Recusar todas</button>' +
			'<button class="nous-dc-btn" type="button" id="nous-dc-done">Concluir</button>';
		bar.querySelectorAll('[data-all]').forEach(function (b) {
			b.addEventListener('click', function () {
				var ok = b.getAttribute('data-all') === '1';
				review.segs.forEach(function (s, i) { if (s.t === '~') review.dec[i] = ok; });
				concluir();
			});
		});
		bar.querySelector('#nous-dc-done').addEventListener('click', function () {
			if (feitas < total && !confirm('As ' + (total - feitas) + ' sugestoes que voce nao decidiu ficam como estavam (recusadas). Concluir?')) return;
			concluir();
		});
	}

	function concluir() {
		var r = review, texto = '', aceitas = 0;
		r.segs.forEach(function (s, i) {
			if (s.t === '=') texto += s.s;
			else if (r.dec[i] === true) { texto += s.b; aceitas++; }
			else texto += s.a;
		});
		review = null;
		modo('w');
		$('#nous-dc-text').value = texto;
		if (aceitas) {
			salvarAgora('antes da IA: ' + r.rotulo.replace(/^[^\wÀ-ú]+\s*/, '').slice(0, 50));
			status(aceitas + ' mudanca' + (aceitas === 1 ? '' : 's') + ' aplicada' + (aceitas === 1 ? '' : 's') + '. Versoes guarda o texto de antes.');
		} else status('Nada mudou.');
	}

	/* ---------------------------------------------------------- menus */
	function fecharPops() { document.querySelectorAll('.nous-dc-pop').forEach(function (p) { p.remove(); }); }

	function pop(anchor, html) {
		fecharPops();
		var p = document.createElement('div');
		p.className = 'nous-dc-pop';
		p.innerHTML = html;
		var r = anchor.getBoundingClientRect(), box = $('#nous-dc').getBoundingClientRect();
		p.style.left = (r.left - box.left) + 'px';
		p.style.top = (r.bottom - box.top + 4) + 'px';
		$('#nous-dc').style.position = 'relative';
		$('#nous-dc').appendChild(p);
		setTimeout(function () {
			document.addEventListener('click', function fora(e) {
				if (!p.contains(e.target)) { p.remove(); document.removeEventListener('click', fora, true); }
			}, true);
		}, 0);
		return p;
	}

	function menuExportar(anchor) {
		var p = pop(anchor, '<button type="button" data-f="docx">Word (.docx)</button><button type="button" data-f="pdf">PDF</button>' +
			'<button type="button" data-f="md">Markdown (.md)</button><button type="button" data-f="copiar">Copiar o texto</button>');
		p.addEventListener('click', function (e) {
			var b = e.target.closest('[data-f]');
			if (!b) return;
			p.remove();
			var f = b.getAttribute('data-f'), texto = $('#nous-dc-text').value, titulo = $('#nous-dc-title').value.trim() || 'Documento';
			if (f === 'copiar') {
				navigator.clipboard.writeText(texto).then(function () { status('Texto copiado.'); }, function () { status('Nao consegui copiar.', true); });
				return;
			}
			status('Gerando o arquivo...');
			fetch(MON + '/docs/export', { method: 'POST', headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ titulo: titulo, texto: texto, formato: f }) })
				.then(function (r) {
					if (r.ok) return r.blob();
					return r.json().then(function (d) { throw new Error(d.error || 'falhou'); });
				}).then(function (blob) {
					baixar(blob, titulo + '.' + f);
					status('Baixado.');
				}).catch(function (e) { status(e.message, true); });
		});
	}

	function baixar(blob, nome) {
		var a = document.createElement('a');
		a.href = URL.createObjectURL(blob);
		a.download = nome.replace(/[\\/:*?"<>|]+/g, ' ');
		document.body.appendChild(a);
		a.click();
		setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
	}

	function menuVersoes(anchor) {
		salvarAgora('', function () {
			var vs = (cur && cur.versoes) || [];
			var p = pop(anchor, vs.length ? vs.map(function (v) {
				return '<button type="button" data-v="' + v.i + '">' + quando(v.t) + ' <small>· ' + esc(v.motivo) + ' · ' + v.palavras + ' palavras</small></button>';
			}).join('') : '<div class="nous-dc-empty">Ainda nao ha versoes. Antes de cada mudanca da IA (e a cada 10 min de escrita) o Nous guarda uma.</div>');
			p.addEventListener('click', function (e) {
				var b = e.target.closest('[data-v]');
				if (!b) return;
				p.remove();
				if (!confirm('Voltar para esta versao? O texto de agora fica guardado em Versoes.')) return;
				fetch(MON + '/docs/version?id=' + encodeURIComponent(cur.id) + '&i=' + b.getAttribute('data-v'), { cache: 'no-store' })
					.then(function (r) { return r.json(); }).then(function (d) {
						if (d.error) throw new Error(d.error);
						$('#nous-dc-text').value = d.texto;
						salvarAgora('antes de voltar uma versao');
					}).catch(function (e) { status(e.message, true); });
			});
		});
	}

	/* ---------------------------------------------------- arquivo e chat */
	function importar(file) {
		if (review) return;
		status('Lendo ' + file.name + '...');
		fetch(MON + '/docs/import?nome=' + encodeURIComponent(file.name), { method: 'POST', body: file })
			.then(function (r) { return r.json(); }).then(function (d) {
				if (d.error) throw new Error(d.error);
				if (!d.texto) throw new Error(d.aviso || 'Arquivo sem texto.');
				novo(d.titulo, d.texto);
				status('Aberto: ' + file.name);
			}).catch(function (e) { status(e.message, true); });
	}

	function usarNoChat() {
		var texto = $('#nous-dc-text').value.trim();
		if (!texto) return;
		var box = document.getElementById('chat-input');
		if (!box) { status('Abra uma conversa primeiro.', true); return; }
		salvarAgora();
		var titulo = $('#nous-dc-title').value.trim();
		var msg = 'Sobre este documento' + (titulo ? ' ("' + titulo + '")' : '') + ':\n\n' + texto + '\n\n';
		ov.classList.add('nous-hidden');
		box.focus();
		if (box.tagName === 'TEXTAREA') {
			box.value = msg;
			box.dispatchEvent(new Event('input', { bubbles: true }));
		} else {
			document.execCommand('selectAll', false, null);
			document.execCommand('insertText', false, msg);
		}
	}

	function start() {
		injectStyle();
		window.NousDocs = {
			open: open,
			/* abre um documento novo com este texto (resposta do chat, por exemplo) */
			novo: function (titulo, texto) { open(false); novo(titulo, texto); }
		};
		setInterval(ensureButton, 1000);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
