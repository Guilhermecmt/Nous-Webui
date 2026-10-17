/* =====================================================================
   Nous - Habilidades (v2.7). Botao "Habilidades" no card Recursos -> lista
   o que o Nous aprendeu (NousData/skills), com editar, apagar, criar e
   importar de um link do GitHub (SKILL.md), sempre revisando antes de salvar.
   Fala com o servico local 127.0.0.1:8997. Usa window.NousUI.
   ===================================================================== */
(function () {
	'use strict';

	var SK_URL = 'http://127.0.0.1:8997';
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var uid = null, ov = null;
	var ORIGEM = { conversa: 'aprendida no chat', manual: 'criada por voce', importada: 'importada' };

	function api(method, path, body) {
		var opt = { method: method, headers: {} };
		if (body) {
			body.user_id = uid;
			opt.headers['Content-Type'] = 'application/json';
			opt.body = JSON.stringify(body);
		}
		return fetch(SK_URL + path, opt).then(function (r) {
			return r.json().then(function (d) {
				if (!r.ok) throw new Error(d.error || 'erro');
				return d;
			});
		});
	}

	function injectStyle() {
		if (document.getElementById('nous-sk-style')) return;
		var g = 'rgba(200,150,46,';
		var css =
			'#nous-skills-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);' +
			'border-radius:8px;cursor:pointer;background:transparent;color:#e7c069;font-weight:600;font-size:12px}' +
			'#nous-skills-open:hover{background:' + g + '.12)}' +
			'#nous-sk-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);display:flex;' +
			'align-items:center;justify-content:center;backdrop-filter:blur(3px)}' +
			'#nous-sk-ov.nous-hidden{display:none}' +
			'#nous-sk{width:540px;max-width:95vw;max-height:84vh;display:flex;flex-direction:column;' +
			'font-family:Inter,system-ui,sans-serif;font-size:13px;color:#eee;background:rgba(18,18,22,.97);' +
			'border:1px solid ' + g + '.4);border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-sk-head{display:flex;align-items:center;gap:8px;padding:14px 16px 10px;border-bottom:1px solid ' + g + '.15)}' +
			'#nous-sk-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'#nous-sk-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px}' +
			'#nous-sk-body{flex:1;overflow-y:auto;padding:12px 16px 16px}' +
			'.nous-sk-hint{font-size:12px;opacity:.65;line-height:1.55;margin-bottom:10px}' +
			'.nous-sk-item{padding:9px 10px;border-radius:10px;background:rgba(255,255,255,.04);margin-bottom:6px;' +
			'display:flex;gap:8px;align-items:flex-start}' +
			'.nous-sk-main{flex:1;min-width:0;cursor:pointer}' +
			'.nous-sk-name{font-weight:700}' +
			'.nous-sk-sub{font-size:11px;opacity:.6;margin-top:2px}' +
			'.nous-sk-act{background:none;border:none;color:#888;cursor:pointer;font-size:13px}' +
			'.nous-sk-act:hover{color:#e7c069}' +
			'.nous-sk-form input,.nous-sk-form textarea{box-sizing:border-box;width:100%;padding:7px 9px;margin:3px 0 9px;' +
			'background:rgba(255,255,255,.07);border:1px solid ' + g + '.28);border-radius:8px;color:#eee;' +
			'font-size:12px;outline:none;font-family:inherit}' +
			'.nous-sk-form textarea{min-height:220px;resize:vertical;font-family:ui-monospace,Consolas,monospace;line-height:1.5}' +
			'.nous-sk-lbl{font-size:11px;opacity:.65}' +
			'.nous-sk-btn{padding:6px 12px;border:1px solid ' + g + '.45);border-radius:8px;cursor:pointer;' +
			'background:' + g + '.18);color:#e7c069;font-weight:600;font-size:12px;margin-right:6px}' +
			'.nous-sk-btn:hover{background:' + g + '.32)}.nous-sk-btn.ghost{background:transparent}' +
			'.nous-sk-row{display:flex;gap:8px;margin-bottom:10px}.nous-sk-row input{flex:1;margin:0}' +
			'.nous-sk-msg{font-size:11px;margin-left:4px}.nous-sk-bad{color:#f08080}' +
			'.nous-sk-warn{font-size:11px;line-height:1.5;padding:7px 9px;border-radius:8px;margin-bottom:9px;' +
			'background:rgba(220,160,60,.1);border:1px solid rgba(220,160,60,.3)}' +
			'.nous-sk-empty{opacity:.6;text-align:center;padding:16px 8px;font-size:12px;line-height:1.6}';
		var st = document.createElement('style');
		st.id = 'nous-sk-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-skills-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-skills-open';
		b.type = 'button';
		b.textContent = '🧠 Habilidades';
		b.addEventListener('click', open);
		body.appendChild(b);
	}

	function build() {
		if (ov && document.body.contains(ov)) return;
		ov = document.createElement('div');
		ov.id = 'nous-sk-ov';
		ov.className = 'nous-hidden';
		ov.innerHTML = '<div id="nous-sk"><div id="nous-sk-head"><span>🧠 Habilidades</span>' +
			'<button id="nous-sk-close" type="button" aria-label="Fechar">&#x2715;</button></div>' +
			'<div id="nous-sk-body"></div></div>';
		document.body.appendChild(ov);
		ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
		ov.querySelector('#nous-sk-close').addEventListener('click', close);
	}

	function open() {
		(UI.loadUserId || function (cb) { cb(null); })(function (id) {
			uid = id;
			build();
			ov.classList.remove('nous-hidden');
			renderList();
		});
	}
	function close() { if (ov) ov.classList.add('nous-hidden'); }
	function box() { return ov.querySelector('#nous-sk-body'); }

	function renderList() {
		var b = box();
		if (!uid) { b.innerHTML = '<div class="nous-sk-empty">Entre no Nous para ver as habilidades.</div>'; return; }
		b.innerHTML = '<div class="nous-sk-empty">Carregando...</div>';
		api('GET', '/skills?user_id=' + encodeURIComponent(uid)).then(function (d) {
			var html = '<div class="nous-sk-hint">Habilidades sao o <b>jeito</b> que voce gosta que as coisas sejam feitas. ' +
				'Depois de acertar algo numa conversa, diga <b>"aprenda isso"</b>: o Nous guarda o passo a passo e usa ' +
				'sozinho quando um pedido parecido aparecer.</div>' +
				'<div style="margin-bottom:10px"><button class="nous-sk-btn" id="nous-sk-new" type="button">+ Nova habilidade</button>' +
				'<button class="nous-sk-btn ghost" id="nous-sk-imp" type="button">Importar do GitHub</button></div>';
			if (!d.skills.length) html += '<div class="nous-sk-empty">O Nous ainda nao aprendeu nenhuma habilidade.</div>';
			d.skills.forEach(function (s) {
				html += '<div class="nous-sk-item"><div class="nous-sk-main" data-open="' + esc(s.id) + '">' +
					'<div class="nous-sk-name">' + esc(s.nome) + '</div>' +
					'<div class="nous-sk-sub">Usar ' + esc(s.quando_usar) + '</div>' +
					'<div class="nous-sk-sub">' + (ORIGEM[s.origem] || esc(s.origem)) + (s.criado ? ' · ' + esc(s.criado) : '') + '</div></div>' +
					'<button class="nous-sk-act" title="Editar" data-open="' + esc(s.id) + '">✎</button>' +
					'<button class="nous-sk-act" title="Apagar" data-del="' + esc(s.id) + '">🗑</button></div>';
			});
			b.innerHTML = html;
			b.querySelector('#nous-sk-new').addEventListener('click', function () { renderEdit({ origem: 'manual' }); });
			b.querySelector('#nous-sk-imp').addEventListener('click', renderImport);
			b.querySelectorAll('[data-open]').forEach(function (el) {
				el.addEventListener('click', function () {
					api('GET', '/skills/get?user_id=' + encodeURIComponent(uid) + '&id=' + encodeURIComponent(el.getAttribute('data-open')))
						.then(function (r) { renderEdit(r.skill); });
				});
			});
			b.querySelectorAll('[data-del]').forEach(function (el) {
				el.addEventListener('click', function () {
					if (!confirm('Apagar esta habilidade? O Nous deixa de usa-la.')) return;
					api('POST', '/skills/delete', { id: el.getAttribute('data-del') }).then(renderList);
				});
			});
		}).catch(function () {
			b.innerHTML = '<div class="nous-sk-empty">O servico de habilidades nao esta no ar.<br>' +
				'Abra o Nous pelo atalho da area de trabalho e tente de novo.</div>';
		});
	}

	function renderEdit(s) {
		var b = box();
		b.innerHTML = '<div class="nous-sk-form">' +
			(s.origem === 'importada' ? '<div class="nous-sk-warn">Habilidade de fora: leia os passos antes de salvar. ' +
				'Ela vai entrar no contexto do modelo sempre que combinar com um pedido seu.</div>' : '') +
			'<span class="nous-sk-lbl">Nome</span><input id="nous-sk-n" value="' + esc(s.nome || '') + '" placeholder="Ex.: Relatorio semanal de vendas">' +
			'<span class="nous-sk-lbl">Quando usar</span><input id="nous-sk-q" value="' + esc(s.quando_usar || '') +
			'" placeholder="Ex.: quando eu pedir o relatorio semanal de vendas">' +
			'<span class="nous-sk-lbl">Passo a passo (Markdown)</span><textarea id="nous-sk-c" placeholder="1. ...&#10;2. ...">' +
			esc(s.corpo || '') + '</textarea>' +
			'<button class="nous-sk-btn" id="nous-sk-save" type="button">Salvar</button>' +
			'<button class="nous-sk-btn ghost" id="nous-sk-back" type="button">Voltar</button>' +
			'<span class="nous-sk-msg" id="nous-sk-m"></span></div>';
		b.querySelector('#nous-sk-back').addEventListener('click', renderList);
		b.querySelector('#nous-sk-save').addEventListener('click', function () {
			api('POST', '/skills', {
				id: s.id || null, nome: b.querySelector('#nous-sk-n').value, quando_usar: b.querySelector('#nous-sk-q').value,
				corpo: b.querySelector('#nous-sk-c').value, origem: s.origem, fonte: s.fonte, criado: s.criado
			}).then(renderList).catch(function (e) {
				var m = b.querySelector('#nous-sk-m');
				m.textContent = e.message;
				m.className = 'nous-sk-msg nous-sk-bad';
			});
		});
	}

	function renderImport() {
		var b = box();
		b.innerHTML = '<div class="nous-sk-hint">Cole o link de um <b>SKILL.md</b> no GitHub (arquivo ou pasta). ' +
			'O Nous baixa e mostra o conteudo para voce revisar antes de salvar.</div>' +
			'<div class="nous-sk-row"><input id="nous-sk-u" placeholder="https://github.com/.../SKILL.md" ' +
			'style="box-sizing:border-box;padding:7px 9px;background:rgba(255,255,255,.07);border:1px solid rgba(200,150,46,.28);' +
			'border-radius:8px;color:#eee;font-size:12px;outline:none">' +
			'<button class="nous-sk-btn" id="nous-sk-get" type="button">Baixar</button></div>' +
			'<button class="nous-sk-btn ghost" id="nous-sk-back" type="button">Voltar</button>' +
			'<span class="nous-sk-msg" id="nous-sk-m"></span>';
		b.querySelector('#nous-sk-back').addEventListener('click', renderList);
		b.querySelector('#nous-sk-get').addEventListener('click', function () {
			var m = b.querySelector('#nous-sk-m');
			m.textContent = 'Baixando...';
			m.className = 'nous-sk-msg';
			api('POST', '/skills/fetch', { url: b.querySelector('#nous-sk-u').value })
				.then(function (r) { renderEdit(r.skill); })
				.catch(function (e) { m.textContent = e.message; m.className = 'nous-sk-msg nous-sk-bad'; });
		});
	}

	function start() {
		injectStyle();
		window.NousSkills = { open: open };
		setInterval(ensureButton, 1000);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
