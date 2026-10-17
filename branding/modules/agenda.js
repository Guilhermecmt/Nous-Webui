/* =====================================================================
   Nous - Agenda (v2.7): notas, lembretes, calendario e tarefas agendadas.
   Botao "Agenda" no card Recursos -> painel com 4 abas. Fala com o servico
   local da agenda (127.0.0.1:8996). Avisos (lembretes, compromissos e
   tarefas prontas) aparecem como cartoes no canto da tela.
   Concatenado no loader.js pelo apply_branding.py; usa window.NousUI.
   ===================================================================== */
(function () {
	'use strict';

	var AG_URL = 'http://127.0.0.1:8996';
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var uid = null;
	var ov = null, tab = 'hoje', calMonth = null, calDay = null, editNote = null;
	var DIAS = ['dom', 'seg', 'ter', 'qua', 'qui', 'sex', 'sab'];
	var MESES = ['janeiro', 'fevereiro', 'marco', 'abril', 'maio', 'junho', 'julho',
		'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
	var REPEAT_LABEL = { '': 'Nao repete', diario: 'Todo dia', dias_uteis: 'Dias uteis',
		semanal: 'Toda semana', mensal: 'Todo mes', anual: 'Todo ano' };
	var KIND_LABEL = { pergunta: 'Pergunta ao Nous', pesquisa: 'Pesquisa na web',
		emails: 'Resumo dos e-mails', resumo_dia: 'Bom dia (agenda + e-mails)' };

	/* ---------------------------------------------------------- utilidades */
	function api(method, path, body) {
		var opt = { method: method, headers: {} };
		if (body) {
			body.user_id = uid;
			opt.headers['Content-Type'] = 'application/json';
			opt.body = JSON.stringify(body);
		}
		return fetch(AG_URL + path, opt).then(function (r) {
			return r.json().then(function (d) {
				if (!r.ok) throw new Error(d.error || 'erro');
				return d;
			});
		});
	}
	function qs(path, params) {
		params = params || {};
		params.user_id = uid;
		return path + '?' + Object.keys(params).map(function (k) {
			return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
		}).join('&');
	}
	function d2(n) { return (n < 10 ? '0' : '') + n; }
	function hm(ts) { var d = new Date(ts * 1000); return d2(d.getHours()) + ':' + d2(d.getMinutes()); }
	function dayKey(d) { return d.getFullYear() + '-' + d2(d.getMonth() + 1) + '-' + d2(d.getDate()); }
	function dayLabel(ts, nowTs) {
		var d = new Date(ts * 1000), n = new Date(nowTs * 1000);
		var t0 = new Date(n.getFullYear(), n.getMonth(), n.getDate()).getTime();
		var diff = Math.floor((new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() - t0) / 86400000);
		if (diff === 0) return 'Hoje';
		if (diff === 1) return 'Amanha';
		return DIAS[d.getDay()] + ' ' + d2(d.getDate()) + '/' + d2(d.getMonth() + 1);
	}
	function localInput(ts) {
		var d = new Date(ts * 1000);
		return dayKey(d) + 'T' + d2(d.getHours()) + ':' + d2(d.getMinutes());
	}
	function msg(el, text, bad) {
		if (!el) return;
		el.textContent = text || '';
		el.className = 'nous-ag-msg' + (bad ? ' nous-ag-bad' : '');
	}
	function offline(box) {
		box.innerHTML = '<div class="nous-ag-empty">O servico da agenda nao esta no ar.<br>' +
			'Abra o Nous pelo atalho da area de trabalho e tente de novo.</div>';
	}

	/* ---------------------------------------------------------- estilo */
	function injectStyle() {
		if (document.getElementById('nous-ag-style')) return;
		var g = 'rgba(200,150,46,';
		var css =
			'#nous-agenda-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);' +
			'border-radius:8px;cursor:pointer;background:transparent;color:#e7c069;font-weight:600;font-size:12px}' +
			'#nous-agenda-open:hover{background:' + g + '.12)}' +
			'#nous-ag-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);display:flex;' +
			'align-items:center;justify-content:center;backdrop-filter:blur(3px)}' +
			'#nous-ag-ov.nous-hidden{display:none}' +
			'#nous-ag{width:560px;max-width:95vw;height:82vh;display:flex;flex-direction:column;' +
			'font-family:Inter,system-ui,sans-serif;font-size:13px;color:#eee;background:rgba(18,18,22,.97);' +
			'border:1px solid ' + g + '.4);border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-ag-head{display:flex;align-items:center;gap:8px;padding:14px 16px 8px}' +
			'#nous-ag-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'#nous-ag-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px}' +
			'#nous-ag-tabs{display:flex;gap:4px;padding:0 12px;border-bottom:1px solid ' + g + '.15)}' +
			'.nous-ag-tab{background:none;border:none;border-bottom:2px solid transparent;color:#aaa;' +
			'padding:8px 10px;cursor:pointer;font-size:12px;font-weight:600}' +
			'.nous-ag-tab.on{color:#e7c069;border-bottom-color:#c8962e}' +
			'#nous-ag-body{flex:1;overflow-y:auto;padding:12px 16px 16px}' +
			'#nous-ag-body::-webkit-scrollbar{width:6px}' +
			'#nous-ag-body::-webkit-scrollbar-thumb{background:' + g + '.3);border-radius:4px}' +
			'.nous-ag-h{font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;' +
			'color:#c8962e;margin:12px 0 6px}' +
			'.nous-ag-h:first-child{margin-top:0}' +
			'.nous-ag-item{display:flex;align-items:flex-start;gap:8px;padding:7px 9px;border-radius:9px;' +
			'background:rgba(255,255,255,.04);margin-bottom:5px}' +
			'.nous-ag-item.late{background:rgba(220,60,60,.1)}' +
			'.nous-ag-item.done .nous-ag-tt{text-decoration:line-through;opacity:.5}' +
			'.nous-ag-time{font-variant-numeric:tabular-nums;color:#e7c069;font-size:12px;min-width:44px}' +
			'.nous-ag-main{flex:1;min-width:0}' +
			'.nous-ag-tt{font-weight:600;font-size:13px;word-wrap:break-word}' +
			'.nous-ag-sub{font-size:11px;opacity:.6;margin-top:2px;white-space:pre-wrap;word-wrap:break-word}' +
			'.nous-ag-act{background:none;border:none;color:#888;cursor:pointer;font-size:13px;padding:0 3px}' +
			'.nous-ag-act:hover{color:#e7c069}' +
			'.nous-ag-empty{opacity:.6;text-align:center;padding:18px 8px;font-size:12px;line-height:1.5}' +
			'.nous-ag-form{background:rgba(255,255,255,.03);border:1px solid ' + g + '.2);border-radius:10px;' +
			'padding:10px;margin-bottom:10px}' +
			'.nous-ag-form input,.nous-ag-form select,.nous-ag-form textarea{box-sizing:border-box;width:100%;' +
			'padding:6px 8px;margin:3px 0 7px;background:rgba(255,255,255,.07);border:1px solid ' + g + '.28);' +
			'border-radius:7px;color:#eee;font-size:12px;outline:none;font-family:inherit;color-scheme:dark}' +
			'.nous-ag-form textarea{min-height:60px;resize:vertical}' +
			'.nous-ag-form input[type=checkbox]{width:auto;margin:0 6px 0 0}' +
			'.nous-ag-row{display:flex;gap:8px}.nous-ag-row>*{flex:1}' +
			'.nous-ag-lbl{font-size:11px;opacity:.65}' +
			'.nous-ag-btn{padding:6px 12px;border:1px solid ' + g + '.45);border-radius:8px;cursor:pointer;' +
			'background:' + g + '.18);color:#e7c069;font-weight:600;font-size:12px}' +
			'.nous-ag-btn:hover{background:' + g + '.32)}' +
			'.nous-ag-btn.ghost{background:transparent}' +
			'.nous-ag-msg{font-size:11px;margin-top:6px;opacity:.8}.nous-ag-bad{color:#f08080;opacity:1}' +
			'.nous-ag-hint{font-size:11px;opacity:.55;line-height:1.5;margin:4px 0 8px}' +
			'.nous-ag-cal{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;margin-bottom:10px}' +
			'.nous-ag-cal div{text-align:center;font-size:11px;opacity:.5;padding:2px 0}' +
			'.nous-ag-cal button{position:relative;height:38px;border:1px solid rgba(255,255,255,.06);' +
			'border-radius:7px;background:rgba(255,255,255,.03);color:#ddd;cursor:pointer;font-size:12px}' +
			'.nous-ag-cal button.out{opacity:.3}.nous-ag-cal button.today{border-color:#c8962e;color:#e7c069}' +
			'.nous-ag-cal button.sel{background:' + g + '.25)}' +
			'.nous-ag-cal button i{position:absolute;left:50%;bottom:4px;transform:translateX(-50%);' +
			'width:5px;height:5px;border-radius:50%;background:#c8962e}' +
			'.nous-ag-calhead{display:flex;align-items:center;gap:8px;margin-bottom:8px}' +
			'.nous-ag-calhead b{flex:1;text-align:center;text-transform:capitalize}' +
			'.nous-ag-list{opacity:.9}.nous-ag-chk{display:flex;gap:6px;align-items:center;cursor:pointer;margin:2px 0}' +
			'.nous-ag-chk.on{text-decoration:line-through;opacity:.55}.nous-ag-chk input{accent-color:#c8962e;margin:0}' +
			'#nous-ag-gear{background:none;border:none;color:#888;cursor:pointer;font-size:16px}#nous-ag-gear:hover{color:#e7c069}' +
			'.nous-ag-tag{display:inline-block;font-size:10px;padding:1px 6px;border-radius:9px;' +
			'background:' + g + '.18);color:#e7c069;margin-left:5px;font-weight:600}' +
			'#nous-ag-toasts{position:fixed;top:16px;right:16px;z-index:10002;display:flex;flex-direction:column;gap:8px;' +
			'font-family:Inter,system-ui,sans-serif}' +
			'.nous-ag-toast{width:300px;padding:10px 12px;border-radius:12px;cursor:pointer;color:#eee;font-size:12px;' +
			'background:rgba(18,18,22,.96);border:1px solid ' + g + '.55);box-shadow:0 10px 30px rgba(0,0,0,.45)}' +
			'.nous-ag-toast b{display:block;color:#e7c069;font-size:13px;margin-bottom:3px}' +
			'.nous-ag-toast span{opacity:.75;white-space:pre-wrap}';
		var st = document.createElement('style');
		st.id = 'nous-ag-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	/* ---------------------------------------------------------- painel */
	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-agenda-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-agenda-open';
		b.type = 'button';
		b.textContent = '📅 Agenda';
		b.addEventListener('click', function () { open('hoje'); });
		body.appendChild(b);
	}

	function build() {
		if (ov && document.body.contains(ov)) return;
		ov = document.createElement('div');
		ov.id = 'nous-ag-ov';
		ov.className = 'nous-hidden';
		ov.innerHTML =
			'<div id="nous-ag"><div id="nous-ag-head"><span>📅 Agenda</span>' +
			'<button id="nous-ag-gear" type="button" title="Onde receber os avisos">⚙</button>' +
			'<button id="nous-ag-close" type="button" aria-label="Fechar">&#x2715;</button></div>' +
			'<div id="nous-ag-tabs">' +
			['hoje:Hoje', 'notas:Notas', 'cal:Calendario', 'tarefas:Tarefas'].map(function (t) {
				var p = t.split(':');
				return '<button class="nous-ag-tab" type="button" data-tab="' + p[0] + '">' + p[1] + '</button>';
			}).join('') +
			'</div><div id="nous-ag-body"></div></div>';
		document.body.appendChild(ov);
		ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
		ov.querySelector('#nous-ag-close').addEventListener('click', close);
		ov.querySelector('#nous-ag-gear').addEventListener('click', function () { show('avisos'); });
		ov.querySelectorAll('.nous-ag-tab').forEach(function (b) {
			b.addEventListener('click', function () { show(b.getAttribute('data-tab')); });
		});
	}

	function open(which) {
		(UI.loadUserId || function (cb) { cb(null); })(function (id) {
			uid = id;
			build();
			ov.classList.remove('nous-hidden');
			show(which || tab);
		});
	}
	function close() { if (ov) ov.classList.add('nous-hidden'); }

	function show(which) {
		tab = which === 'avisos' ? tab : which;
		ov.querySelectorAll('.nous-ag-tab').forEach(function (b) {
			b.classList.toggle('on', b.getAttribute('data-tab') === which);
		});
		var box = ov.querySelector('#nous-ag-body');
		if (!uid) {
			box.innerHTML = '<div class="nous-ag-empty">Entre no Nous para usar a agenda.</div>';
			return;
		}
		box.innerHTML = '<div class="nous-ag-empty">Carregando...</div>';
		({ hoje: renderToday, notas: renderNotes, cal: renderCal, tarefas: renderTasks, avisos: renderSettings })[which](box);
	}

	/* ---------------------------------------------------------- Avisos */
	function randomTopic() {
		var a = new Uint8Array(9), s = 'nous-';
		(window.crypto || {}).getRandomValues ? window.crypto.getRandomValues(a) : a.forEach(function (_, i) { a[i] = Math.random() * 255; });
		a.forEach(function (b) { s += 'abcdefghijkmnpqrstuvwxyz23456789'[b % 32]; });
		return s;
	}

	function renderSettings(box) {
		api('GET', qs('/settings')).then(function (d) {
			var s = d.settings;
			box.innerHTML = '<div class="nous-ag-h">Onde receber os avisos</div>' +
				'<div class="nous-ag-hint">Lembretes, compromissos e tarefas prontas sempre aparecem no Windows e aqui no Nous. ' +
				'Se quiser, eles tambem chegam:</div><div class="nous-ag-form">' +
				'<label class="nous-ag-lbl" style="font-size:12px;opacity:1"><input id="nous-ag-se" type="checkbox"' +
				(s.aviso_email === '1' ? ' checked' : '') + '>No seu e-mail (precisa do Assistente de Email conectado)</label></div>' +
				'<div class="nous-ag-form"><b style="font-size:12px">No celular, de graca (app ntfy)</b>' +
				'<div class="nous-ag-hint">1. Instale o app <b>ntfy</b> (Android ou iPhone).<br>2. No app, toque em <b>+</b> e assine o codigo abaixo.<br>' +
				'O codigo funciona como uma senha: quem souber dele recebe seus avisos. As mensagens passam pelo servidor publico ntfy.sh.</div>' +
				'<div class="nous-ag-row"><input id="nous-ag-st" value="' + esc(s.ntfy_topico || '') + '" placeholder="desligado">' +
				'<button class="nous-ag-btn ghost" id="nous-ag-sg" type="button" style="flex:.45">Gerar codigo</button></div>' +
				'<button class="nous-ag-btn" id="nous-ag-ss2" type="button">Salvar</button> ' +
				'<button class="nous-ag-btn ghost" id="nous-ag-tt" type="button">Mandar um teste</button>' +
				'<span class="nous-ag-msg" id="nous-ag-sm2"></span></div>' +
				'<button class="nous-ag-btn ghost" id="nous-ag-back" type="button">Voltar</button>';
			box.querySelector('#nous-ag-sg').addEventListener('click', function () { box.querySelector('#nous-ag-st').value = randomTopic(); });
			box.querySelector('#nous-ag-back').addEventListener('click', function () { show('hoje'); });
			function save() {
				return api('POST', '/settings', { aviso_email: box.querySelector('#nous-ag-se').checked, ntfy_topico: box.querySelector('#nous-ag-st').value.trim() });
			}
			box.querySelector('#nous-ag-ss2').addEventListener('click', function () {
				save().then(function () { msg(box.querySelector('#nous-ag-sm2'), 'Salvo.'); })
					.catch(function (e) { msg(box.querySelector('#nous-ag-sm2'), e.message, true); });
			});
			box.querySelector('#nous-ag-tt').addEventListener('click', function () {
				save().then(function () { return api('POST', '/settings/test', {}); })
					.then(function () { msg(box.querySelector('#nous-ag-sm2'), 'Teste enviado. Chegou?'); })
					.catch(function (e) { msg(box.querySelector('#nous-ag-sm2'), e.message, true); });
			});
		}).catch(function () { offline(box); });
	}

	/* ---------------------------------------------------------- Hoje */
	function renderToday(box) {
		api('GET', qs('/today', { days: 7 })).then(function (d) {
			var groups = {}, order = [];
			function add(key, label, html, ts) {
				if (!groups[key]) { groups[key] = { label: label, items: [] }; order.push(key); }
				groups[key].items.push({ ts: ts, html: html });
			}
			d.notes.forEach(function (n) {
				var ts = n.due_at || n.remind_at, late = ts < d.now;
				var key = late ? '0-late' : '1-' + dayKey(new Date(ts * 1000));
				add(key, late ? 'Atrasados' : dayLabel(ts, d.now),
					'<div class="nous-ag-item' + (late ? ' late' : '') + '">' +
					'<span class="nous-ag-time">' + hm(ts) + '</span>' +
					'<div class="nous-ag-main"><div class="nous-ag-tt">' + esc(n.title || n.body.slice(0, 80)) +
					(n.repeat ? '<span class="nous-ag-tag">' + REPEAT_LABEL[n.repeat] + '</span>' : '') + '</div>' +
					(n.title && n.body ? '<div class="nous-ag-sub">' + esc(n.body) + '</div>' : '') + '</div>' +
					'<button class="nous-ag-act" title="Concluir" data-done="' + n.id + '">✓</button></div>', ts);
			});
			d.events.forEach(function (e) {
				add('1-' + dayKey(new Date(e.occ_start * 1000)), dayLabel(e.occ_start, d.now),
					'<div class="nous-ag-item"><span class="nous-ag-time">' + (e.all_day ? 'dia' : hm(e.occ_start)) + '</span>' +
					'<div class="nous-ag-main"><div class="nous-ag-tt">' + esc(e.title) + '</div>' +
					(e.location ? '<div class="nous-ag-sub">' + esc(e.location) + '</div>' : '') + '</div></div>',
					e.all_day ? e.occ_start - 1 : e.occ_start);
			});
			order.sort();
			var html = quickAddHtml();
			if (!order.length) {
				html += '<div class="nous-ag-empty">Nada marcado para os proximos 7 dias.<br>' +
					'Dica: no chat, diga "me lembre de pagar a luz sexta as 9h".</div>';
			}
			order.forEach(function (k) {
				var g = groups[k];
				g.items.sort(function (a, b) { return a.ts - b.ts; });
				html += '<div class="nous-ag-h">' + g.label + '</div>' + g.items.map(function (i) { return i.html; }).join('');
			});
			box.innerHTML = html;
			bindQuickAdd(box);
			box.querySelectorAll('[data-done]').forEach(function (b) {
				b.addEventListener('click', function () {
					api('POST', '/notes/update', { id: b.getAttribute('data-done'), done: true })
						.then(function () { show('hoje'); });
				});
			});
		}).catch(function () { offline(box); });
	}

	function quickAddHtml() {
		var t = new Date(Date.now() + 3600000);
		t.setMinutes(0);
		return '<div class="nous-ag-form"><div class="nous-ag-row">' +
			'<input id="nous-ag-qt" placeholder="Novo lembrete (ex.: pagar a luz)">' +
			'<input id="nous-ag-qw" type="datetime-local" value="' + localInput(t.getTime() / 1000) + '" style="flex:.8"></div>' +
			'<button class="nous-ag-btn" id="nous-ag-qb" type="button">Adicionar lembrete</button>' +
			'<span class="nous-ag-msg" id="nous-ag-qm"></span></div>';
	}
	function bindQuickAdd(box) {
		var b = box.querySelector('#nous-ag-qb');
		if (!b) return;
		b.addEventListener('click', function () {
			var t = box.querySelector('#nous-ag-qt').value.trim(), w = box.querySelector('#nous-ag-qw').value;
			if (!t) { msg(box.querySelector('#nous-ag-qm'), 'Escreva o lembrete.', true); return; }
			api('POST', '/notes', { title: t, remind_at: w || null, due_at: w || null })
				.then(function () { show('hoje'); })
				.catch(function (e) { msg(box.querySelector('#nous-ag-qm'), e.message, true); });
		});
	}

	/* ---------------------------------------------------------- Notas */
	var CHK = /^(\s*[-*] \[)( |x|X)(\] ?)(.*)$/;

	/* Corpo da nota: linhas "- [ ] item" viram caixas de marcar clicaveis. */
	function bodyHtml(n) {
		if (!n.body) return '';
		var lines = n.body.split('\n'), out = [], hasChk = false;
		lines.slice(0, 40).forEach(function (l, i) {
			var m = l.match(CHK);
			if (m) {
				hasChk = true;
				var on = m[2] !== ' ';
				out.push('<label class="nous-ag-chk' + (on ? ' on' : '') + '"><input type="checkbox" data-chk="' + n.id + ':' + i + '"' +
					(on ? ' checked' : '') + '>' + esc(m[4]) + '</label>');
			} else if (l.trim()) {
				out.push('<div>' + esc(l.length > 300 ? l.slice(0, 300) + '...' : l) + '</div>');
			}
		});
		if (lines.length > 40) out.push('<div>...</div>');
		return '<div class="nous-ag-sub' + (hasChk ? ' nous-ag-list' : '') + '">' + out.join('') + '</div>';
	}

	/* Poe o texto na caixa de mensagem do chat (editor do Open WebUI). */
	function toChat(text) {
		var box = document.getElementById('chat-input') || document.querySelector('#chat-input, textarea');
		if (!box) { alert('Abra uma conversa primeiro.'); return; }
		close();
		box.focus();
		if (box.tagName === 'TEXTAREA') {
			box.value = (box.value ? box.value + '\n' : '') + text;
			box.dispatchEvent(new Event('input', { bubbles: true }));
		} else {
			document.execCommand('insertText', false, text);
		}
	}

	function noteForm(n) {
		n = n || {};
		var rep = Object.keys(REPEAT_LABEL).map(function (k) {
			return '<option value="' + k + '"' + ((n.repeat || '') === k ? ' selected' : '') + '>' + REPEAT_LABEL[k] + '</option>';
		}).join('');
		return '<div class="nous-ag-form" id="nous-ag-nf">' +
			'<input id="nous-ag-nt" placeholder="Titulo" value="' + esc(n.title || '') + '">' +
			'<textarea id="nous-ag-nb" placeholder="Texto da nota">' + esc(n.body || '') + '</textarea>' +
			'<button class="nous-ag-btn ghost" id="nous-ag-nl" type="button" style="margin:-3px 0 8px">☑ Item de lista</button>' +
			'<div class="nous-ag-row"><div><span class="nous-ag-lbl">Avisar em (opcional)</span>' +
			'<input id="nous-ag-nr" type="datetime-local" value="' + (n.remind_at ? localInput(n.remind_at) : '') + '"></div>' +
			'<div><span class="nous-ag-lbl">Repetir</span><select id="nous-ag-np">' + rep + '</select></div></div>' +
			'<button class="nous-ag-btn" id="nous-ag-ns" type="button">' + (n.id ? 'Salvar' : 'Criar nota') + '</button> ' +
			(n.id ? '<button class="nous-ag-btn ghost" id="nous-ag-nc" type="button">Cancelar</button>' : '') +
			'<span class="nous-ag-msg" id="nous-ag-nm"></span></div>';
	}

	function renderNotes(box, query) {
		api('GET', qs('/notes', query ? { q: query } : {})).then(function (d) {
			var html = noteForm(editNote) +
				'<input id="nous-ag-nq" placeholder="Buscar nas notas..." value="' + esc(query || '') + '" ' +
				'style="box-sizing:border-box;width:100%;padding:6px 8px;margin-bottom:8px;background:rgba(255,255,255,.07);' +
				'border:1px solid rgba(200,150,46,.28);border-radius:7px;color:#eee;font-size:12px;outline:none">';
			if (!d.notes.length) html += '<div class="nous-ag-empty">' + (query ? 'Nada encontrado.' : 'Nenhuma nota ainda.') + '</div>';
			d.notes.forEach(function (n) {
				var when = n.remind_at ? '⏰ ' + dayLabel(n.remind_at, Date.now() / 1000) + ' ' + hm(n.remind_at) : '';
				html += '<div class="nous-ag-item' + (n.done ? ' done' : '') + '">' +
					'<button class="nous-ag-act" title="Concluir" data-toggle="' + n.id + '" data-v="' + (n.done ? 0 : 1) + '">' +
					(n.done ? '☑' : '☐') + '</button>' +
					'<div class="nous-ag-main"><div class="nous-ag-tt">' + (n.pinned ? '📌 ' : '') + esc(n.title || '(sem titulo)') +
					(n.tags ? '<span class="nous-ag-tag">' + esc(n.tags) + '</span>' : '') +
					(n.repeat ? '<span class="nous-ag-tag">' + REPEAT_LABEL[n.repeat] + '</span>' : '') + '</div>' +
					(when ? '<div class="nous-ag-sub">' + when + '</div>' : '') +
					bodyHtml(n) +
					'</div>' +
					'<button class="nous-ag-act" title="Usar no chat" data-chat="' + n.id + '">💬</button>' +
					'<button class="nous-ag-act" title="' + (n.pinned ? 'Desafixar' : 'Fixar no topo') + '" data-pin="' + n.id +
					'" data-v="' + (n.pinned ? 0 : 1) + '"' + (n.pinned ? '' : ' style="opacity:.3;filter:grayscale(1)"') + '>📌</button>' +
					'<button class="nous-ag-act" title="Editar" data-edit="' + n.id + '">✎</button>' +
					'<button class="nous-ag-act" title="Apagar" data-del="' + n.id + '">🗑</button></div>';
			});
			box.innerHTML = html;
			var byId = {};
			d.notes.forEach(function (n) { byId[n.id] = n; });
			box.querySelector('#nous-ag-ns').addEventListener('click', function () {
				var r = box.querySelector('#nous-ag-nr').value;
				var p = {
					title: box.querySelector('#nous-ag-nt').value, body: box.querySelector('#nous-ag-nb').value,
					remind_at: r || null, due_at: r || null, repeat: box.querySelector('#nous-ag-np').value || null
				};
				var req = editNote ? api('POST', '/notes/update', Object.assign({ id: editNote.id }, p)) : api('POST', '/notes', p);
				req.then(function () { editNote = null; renderNotes(box, query); })
					.catch(function (e) { msg(box.querySelector('#nous-ag-nm'), e.message, true); });
			});
			var c = box.querySelector('#nous-ag-nc');
			if (c) c.addEventListener('click', function () { editNote = null; renderNotes(box, query); });
			box.querySelector('#nous-ag-nl').addEventListener('click', function () {
				var ta = box.querySelector('#nous-ag-nb');
				ta.value = ta.value + (ta.value && !/\n$/.test(ta.value) ? '\n' : '') + '- [ ] ';
				ta.focus();
			});
			box.querySelectorAll('[data-chk]').forEach(function (cb) {
				cb.addEventListener('change', function () {
					var p = cb.getAttribute('data-chk').split(':'), n = byId[p[0]];
					var lines = n.body.split('\n');
					lines[+p[1]] = lines[+p[1]].replace(CHK, function (_, a, _b, c2, d) { return a + (cb.checked ? 'x' : ' ') + c2 + d; });
					api('POST', '/notes/update', { id: n.id, body: lines.join('\n') }).then(function () { renderNotes(box, query); });
				});
			});
			box.querySelectorAll('[data-chat]').forEach(function (b) {
				b.addEventListener('click', function () {
					var n = byId[b.getAttribute('data-chat')];
					toChat((n.title ? n.title + '\n' : '') + (n.body || ''));
				});
			});
			var q = box.querySelector('#nous-ag-nq'), timer = null;
			q.addEventListener('input', function () {
				clearTimeout(timer);
				timer = setTimeout(function () { renderNotes(box, q.value.trim()); }, 350);
			});
			if (query) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
			box.querySelectorAll('[data-toggle]').forEach(function (b) {
				b.addEventListener('click', function () {
					api('POST', '/notes/update', { id: b.getAttribute('data-toggle'), done: b.getAttribute('data-v') === '1' })
						.then(function () { renderNotes(box, query); });
				});
			});
			box.querySelectorAll('[data-pin]').forEach(function (b) {
				b.addEventListener('click', function () {
					api('POST', '/notes/update', { id: b.getAttribute('data-pin'), pinned: b.getAttribute('data-v') === '1' })
						.then(function () { renderNotes(box, query); });
				});
			});
			box.querySelectorAll('[data-edit]').forEach(function (b) {
				b.addEventListener('click', function () {
					editNote = byId[b.getAttribute('data-edit')];
					renderNotes(box, query);
					box.scrollTop = 0;
				});
			});
			box.querySelectorAll('[data-del]').forEach(function (b) {
				b.addEventListener('click', function () {
					if (!confirm('Apagar esta nota?')) return;
					api('POST', '/notes/delete', { id: b.getAttribute('data-del') })
						.then(function () { renderNotes(box, query); });
				});
			});
		}).catch(function () { offline(box); });
	}

	/* ---------------------------------------------------------- Calendario */
	function renderCal(box) {
		var now = new Date();
		if (!calMonth) calMonth = new Date(now.getFullYear(), now.getMonth(), 1);
		if (!calDay) calDay = dayKey(now);
		var first = new Date(calMonth.getFullYear(), calMonth.getMonth(), 1);
		var gridStart = new Date(first.getTime());
		gridStart.setDate(1 - first.getDay());
		var gridEnd = new Date(gridStart.getTime());
		gridEnd.setDate(gridStart.getDate() + 42);
		Promise.all([
			api('GET', qs('/events', { from: Math.floor(gridStart.getTime() / 1000), to: Math.floor(gridEnd.getTime() / 1000) })),
			api('GET', qs('/subs'))
		]).then(function (res) {
			var evs = res[0].events, subs = res[1].subs, byDay = {};
			evs.forEach(function (e) {
				var k = dayKey(new Date(e.occ_start * 1000));
				(byDay[k] = byDay[k] || []).push(e);
			});
			var html = '<div class="nous-ag-calhead"><button class="nous-ag-btn ghost" data-m="-1" type="button">‹</button>' +
				'<b>' + MESES[calMonth.getMonth()] + ' ' + calMonth.getFullYear() + '</b>' +
				'<button class="nous-ag-btn ghost" data-m="1" type="button">›</button></div><div class="nous-ag-cal">' +
				DIAS.map(function (d) { return '<div>' + d + '</div>'; }).join('');
			for (var i = 0; i < 42; i++) {
				var d = new Date(gridStart.getTime());
				d.setDate(gridStart.getDate() + i);
				var k = dayKey(d);
				html += '<button type="button" data-day="' + k + '" class="' +
					(d.getMonth() !== calMonth.getMonth() ? 'out ' : '') + (k === dayKey(now) ? 'today ' : '') +
					(k === calDay ? 'sel' : '') + '">' + d.getDate() + (byDay[k] ? '<i></i>' : '') + '</button>';
			}
			html += '</div>';
			var sel = calDay.split('-'), selDate = new Date(+sel[0], +sel[1] - 1, +sel[2]);
			html += '<div class="nous-ag-h">' + DIAS[selDate.getDay()] + ' ' + sel[2] + '/' + sel[1] + '</div>';
			var list = byDay[calDay] || [];
			if (!list.length) html += '<div class="nous-ag-empty" style="padding:8px">Nenhum compromisso neste dia.</div>';
			list.forEach(function (e) {
				html += '<div class="nous-ag-item"><span class="nous-ag-time">' + (e.all_day ? 'dia' : hm(e.occ_start)) + '</span>' +
					'<div class="nous-ag-main"><div class="nous-ag-tt">' + esc(e.title) +
					(e.rrule ? '<span class="nous-ag-tag">repete</span>' : '') +
					(e.source !== 'local' ? '<span class="nous-ag-tag">assinatura</span>' : '') + '</div>' +
					(e.location ? '<div class="nous-ag-sub">' + esc(e.location) + '</div>' : '') +
					(e.description ? '<div class="nous-ag-sub">' + esc(e.description.slice(0, 300)) + '</div>' : '') + '</div>' +
					(e.source === 'local' ? '<button class="nous-ag-act" title="Apagar" data-edel="' + e.id + '">🗑</button>' : '') + '</div>';
			});
			html += eventForm() + subsHtml(subs);
			box.innerHTML = html;
			bindCal(box);
		}).catch(function () { offline(box); });
	}

	function eventForm() {
		var rep = Object.keys(REPEAT_LABEL).map(function (k) {
			return '<option value="' + k + '">' + REPEAT_LABEL[k] + '</option>';
		}).join('');
		return '<div class="nous-ag-h">Novo compromisso</div><div class="nous-ag-form">' +
			'<input id="nous-ag-et" placeholder="O que (ex.: Dentista)">' +
			'<div class="nous-ag-row"><div><span class="nous-ag-lbl">Dia</span><input id="nous-ag-ed" type="date" value="' + calDay + '"></div>' +
			'<div><span class="nous-ag-lbl">Inicio</span><input id="nous-ag-es" type="time" value="09:00"></div>' +
			'<div><span class="nous-ag-lbl">Fim</span><input id="nous-ag-ee" type="time" value="10:00"></div></div>' +
			'<div class="nous-ag-row"><div><span class="nous-ag-lbl">Repetir</span><select id="nous-ag-er">' + rep + '</select></div>' +
			'<div><span class="nous-ag-lbl">Avisar</span><select id="nous-ag-ea">' +
			'<option value="">Sem aviso</option><option value="0">Na hora</option><option value="10">10 min antes</option>' +
			'<option value="30" selected>30 min antes</option><option value="60">1 hora antes</option>' +
			'<option value="1440">1 dia antes</option></select></div></div>' +
			'<input id="nous-ag-el" placeholder="Local (opcional)">' +
			'<label class="nous-ag-lbl"><input id="nous-ag-ew" type="checkbox">Dia inteiro</label><br><br>' +
			'<button class="nous-ag-btn" id="nous-ag-eb" type="button">Salvar compromisso</button>' +
			'<span class="nous-ag-msg" id="nous-ag-em"></span></div>';
	}

	function subsHtml(subs) {
		var html = '<div class="nous-ag-h">Outros calendarios</div><div class="nous-ag-form">' +
			'<div class="nous-ag-hint">Traga o Google Agenda, o Outlook ou o iCloud: copie o endereco ' +
			'<b>iCal</b> da sua agenda (no Google: Configuracoes &gt; sua agenda &gt; "Endereco secreto no formato iCal") ' +
			'e cole aqui. O Nous atualiza de hora em hora (so leitura).</div>' +
			'<div class="nous-ag-row"><input id="nous-ag-sn" placeholder="Nome (ex.: Trabalho)" style="flex:.5">' +
			'<input id="nous-ag-su" placeholder="https://... .ics"></div>' +
			'<button class="nous-ag-btn" id="nous-ag-sb" type="button">Assinar</button> ' +
			'<button class="nous-ag-btn ghost" id="nous-ag-ss" type="button">Atualizar agora</button>' +
			'<span class="nous-ag-msg" id="nous-ag-sm"></span>';
		subs.forEach(function (s) {
			var st = s.last_error ? 'erro: ' + s.last_error : (s.last_sync ? 'atualizado ' + dayLabel(s.last_sync, Date.now() / 1000).toLowerCase() + ' ' + hm(s.last_sync) : 'aguardando');
			html += '<div class="nous-ag-item" style="margin-top:6px"><div class="nous-ag-main"><div class="nous-ag-tt">' + esc(s.name) + '</div>' +
				'<div class="nous-ag-sub">' + esc(st) + '</div></div>' +
				'<button class="nous-ag-act" title="Remover" data-sdel="' + s.id + '">🗑</button></div>';
		});
		html += '<div class="nous-ag-row" style="margin-top:8px"><label class="nous-ag-btn ghost" style="text-align:center">' +
			'Importar arquivo .ics<input id="nous-ag-if" type="file" accept=".ics,text/calendar" style="display:none"></label>' +
			'<a class="nous-ag-btn ghost" style="text-align:center;text-decoration:none" href="' +
			AG_URL + qs('/ics/export') + '">Exportar .ics</a></div></div>';
		return html;
	}

	function bindCal(box) {
		box.querySelectorAll('[data-m]').forEach(function (b) {
			b.addEventListener('click', function () {
				calMonth = new Date(calMonth.getFullYear(), calMonth.getMonth() + (+b.getAttribute('data-m')), 1);
				renderCal(box);
			});
		});
		box.querySelectorAll('[data-day]').forEach(function (b) {
			b.addEventListener('click', function () { calDay = b.getAttribute('data-day'); renderCal(box); });
		});
		box.querySelectorAll('[data-edel]').forEach(function (b) {
			b.addEventListener('click', function () {
				if (!confirm('Apagar este compromisso (e as repeticoes)?')) return;
				api('POST', '/events/delete', { id: b.getAttribute('data-edel') }).then(function () { renderCal(box); });
			});
		});
		box.querySelectorAll('[data-sdel]').forEach(function (b) {
			b.addEventListener('click', function () {
				if (!confirm('Remover este calendario do Nous?')) return;
				api('POST', '/subs/delete', { id: b.getAttribute('data-sdel') }).then(function () { renderCal(box); });
			});
		});
		box.querySelector('#nous-ag-eb').addEventListener('click', function () {
			var day = box.querySelector('#nous-ag-ed').value, allDay = box.querySelector('#nous-ag-ew').checked;
			var s = box.querySelector('#nous-ag-es').value || '09:00', e = box.querySelector('#nous-ag-ee').value;
			var p = {
				title: box.querySelector('#nous-ag-et').value, all_day: allDay,
				start_at: allDay ? day : day + 'T' + s, end_at: (!allDay && e && e > s) ? day + 'T' + e : null,
				location: box.querySelector('#nous-ag-el').value, repeat: box.querySelector('#nous-ag-er').value || null,
				remind_min: box.querySelector('#nous-ag-ea').value
			};
			api('POST', '/events', p).then(function () { calDay = day; renderCal(box); })
				.catch(function (err) { msg(box.querySelector('#nous-ag-em'), err.message, true); });
		});
		box.querySelector('#nous-ag-sb').addEventListener('click', function () {
			var m = box.querySelector('#nous-ag-sm');
			msg(m, 'Baixando o calendario...');
			api('POST', '/subs', { name: box.querySelector('#nous-ag-sn').value, url: box.querySelector('#nous-ag-su').value, remind_min: 30 })
				.then(function (d) {
					if (d.imported < 0) msg(m, 'Assinado, mas o endereco nao respondeu. Confira se e o endereco iCal.', true);
					else setTimeout(function () { renderCal(box); }, 300);
				})
				.catch(function (err) { msg(m, err.message, true); });
		});
		box.querySelector('#nous-ag-ss').addEventListener('click', function () {
			var m = box.querySelector('#nous-ag-sm');
			msg(m, 'Atualizando...');
			api('POST', '/subs/sync', {}).then(function () { renderCal(box); })
				.catch(function (err) { msg(m, err.message, true); });
		});
		box.querySelector('#nous-ag-if').addEventListener('change', function (ev) {
			var f = ev.target.files && ev.target.files[0];
			if (!f) return;
			f.text().then(function (txt) {
				return api('POST', '/ics/import', { ics: txt });
			}).then(function (d) {
				alert(d.imported + ' compromisso(s) importado(s).');
				renderCal(box);
			}).catch(function (err) { alert('Nao consegui importar: ' + err.message); });
		});
	}

	/* ---------------------------------------------------------- Tarefas */
	function taskForm(list) {
		var chain = '<option value="">Nada</option>' + (list || []).map(function (t) {
			return '<option value="' + esc(t.id) + '">' + esc(t.name) + '</option>';
		}).join('');
		var kinds = Object.keys(KIND_LABEL).map(function (k) {
			return '<option value="' + k + '">' + KIND_LABEL[k] + '</option>';
		}).join('');
		var wd = ['segunda', 'terca', 'quarta', 'quinta', 'sexta', 'sabado', 'domingo'].map(function (d, i) {
			return '<option value="' + (i + 1) + '">' + d + '</option>';
		}).join('');
		return '<div class="nous-ag-h">Nova tarefa</div><div class="nous-ag-form" id="nous-ag-tf">' +
			'<div class="nous-ag-hint">O Nous faz sozinho, no horario marcado, mesmo com o navegador fechado. ' +
			'O resultado vira uma nota e um aviso.</div>' +
			'<div class="nous-ag-row"><button class="nous-ag-btn ghost" data-tpl="bomdia" type="button">☀ Bom dia as 8h</button>' +
			'<button class="nous-ag-btn ghost" data-tpl="emails" type="button">✉ E-mails as 18h</button></div><br>' +
			'<input id="nous-ag-tn" placeholder="Nome (ex.: Noticias de IA)">' +
			'<span class="nous-ag-lbl">O que fazer</span><select id="nous-ag-tk">' + kinds + '</select>' +
			'<textarea id="nous-ag-tp" placeholder="Ex.: pesquise as principais noticias de inteligencia artificial da semana"></textarea>' +
			'<div class="nous-ag-row"><div><span class="nous-ag-lbl">Quando</span><select id="nous-ag-tq">' +
			'<option value="diario">Todo dia</option><option value="dias_uteis">Segunda a sexta</option>' +
			'<option value="semanal">Toda semana</option><option value="mensal">Todo mes</option>' +
			'<option value="uma_vez">Uma vez</option></select></div>' +
			'<div id="nous-ag-tw-wrap" style="display:none"><span class="nous-ag-lbl">Dia</span><select id="nous-ag-tw">' + wd + '</select></div>' +
			'<div id="nous-ag-tm-wrap" style="display:none"><span class="nous-ag-lbl">Dia do mes</span><input id="nous-ag-tm" type="number" min="1" max="31" value="1"></div>' +
			'<div id="nous-ag-to-wrap" style="display:none"><span class="nous-ag-lbl">Data</span><input id="nous-ag-to" type="date"></div>' +
			'<div><span class="nous-ag-lbl">Hora</span><input id="nous-ag-th" type="time" value="08:00"></div></div>' +
			'<span class="nous-ag-lbl">Quando terminar, rodar em seguida (recebe este resultado)</span>' +
			'<select id="nous-ag-tc">' + chain + '</select>' +
			'<label class="nous-ag-lbl"><input id="nous-ag-te" type="checkbox">Enviar o resultado para o meu e-mail (precisa do Assistente de Email)</label><br><br>' +
			'<button class="nous-ag-btn" id="nous-ag-tb" type="button">Criar tarefa</button>' +
			'<span class="nous-ag-msg" id="nous-ag-tmsg"></span></div>';
	}

	function renderTasks(box) {
		api('GET', qs('/tasks')).then(function (d) {
			var html = '';
			if (!d.tasks.length) html += '<div class="nous-ag-empty">Nenhuma tarefa agendada.</div>';
			var names = {};
			d.tasks.forEach(function (t) { names[t.id] = t.name; });
			d.tasks.forEach(function (t) {
				var running = d.running.indexOf(t.id) >= 0;
				if (t.then_task && names[t.then_task]) t.quando += ' · depois: ' + names[t.then_task];
				var last = running ? 'rodando agora...' : (t.last_run ? 'ultima vez: ' + dayLabel(t.last_run, Date.now() / 1000).toLowerCase() +
					' ' + hm(t.last_run) + (t.last_status === 'erro' ? ' (falhou)' : '') : 'ainda nao rodou');
				html += '<div class="nous-ag-item"><button class="nous-ag-act" title="' + (t.enabled ? 'Pausar' : 'Ativar') +
					'" data-ton="' + t.id + '" data-v="' + (t.enabled ? 0 : 1) + '">' + (t.enabled ? '⏸' : '▶') + '</button>' +
					'<div class="nous-ag-main"><div class="nous-ag-tt">' + esc(t.name) + '<span class="nous-ag-tag">' + KIND_LABEL[t.kind] + '</span></div>' +
					'<div class="nous-ag-sub">' + esc(t.quando) + (t.enabled ? '' : ' (pausada)') + ' · ' + last + '</div>' +
					(t.prompt ? '<div class="nous-ag-sub">' + esc(t.prompt.slice(0, 200)) + '</div>' : '') + '</div>' +
					(t.last_note ? '<button class="nous-ag-act" title="Ver resultado" data-tview="1">📄</button>' : '') +
					'<button class="nous-ag-act" title="Rodar agora" data-trun="' + t.id + '">⚡</button>' +
					'<button class="nous-ag-act" title="Apagar" data-tdel="' + t.id + '">🗑</button></div>';
			});
			box.innerHTML = html + taskForm(d.tasks);
			bindTasks(box, d.running.length > 0);
		}).catch(function () { offline(box); });
	}

	function bindTasks(box, anyRunning) {
		if (anyRunning) setTimeout(function () { if (tab === 'tarefas' && !ov.classList.contains('nous-hidden')) renderTasks(box); }, 4000);
		var q = box.querySelector('#nous-ag-tq');
		function syncWhen() {
			box.querySelector('#nous-ag-tw-wrap').style.display = q.value === 'semanal' ? '' : 'none';
			box.querySelector('#nous-ag-tm-wrap').style.display = q.value === 'mensal' ? '' : 'none';
			box.querySelector('#nous-ag-to-wrap').style.display = q.value === 'uma_vez' ? '' : 'none';
		}
		q.addEventListener('change', syncWhen);
		box.querySelectorAll('[data-tpl]').forEach(function (b) {
			b.addEventListener('click', function () {
				var bd = b.getAttribute('data-tpl') === 'bomdia';
				box.querySelector('#nous-ag-tn').value = bd ? 'Bom dia' : 'Resumo dos e-mails';
				box.querySelector('#nous-ag-tk').value = bd ? 'resumo_dia' : 'emails';
				box.querySelector('#nous-ag-tp').value = '';
				q.value = bd ? 'dias_uteis' : 'diario';
				box.querySelector('#nous-ag-th').value = bd ? '08:00' : '18:00';
				syncWhen();
			});
		});
		box.querySelector('#nous-ag-tb').addEventListener('click', function () {
			var h = box.querySelector('#nous-ag-th').value || '08:00', when = q.value, sched;
			if (when === 'semanal') sched = 'semanal ' + box.querySelector('#nous-ag-tw').value + ' ' + h;
			else if (when === 'mensal') sched = 'mensal ' + box.querySelector('#nous-ag-tm').value + ' ' + h;
			else if (when === 'uma_vez') sched = 'uma_vez ' + box.querySelector('#nous-ag-to').value + 'T' + h;
			else sched = when + ' ' + h;
			api('POST', '/tasks', {
				name: box.querySelector('#nous-ag-tn').value, kind: box.querySelector('#nous-ag-tk').value,
				prompt: box.querySelector('#nous-ag-tp').value, schedule: sched,
				email: box.querySelector('#nous-ag-te').checked, then_task: box.querySelector('#nous-ag-tc').value || null
			}).then(function () { renderTasks(box); })
				.catch(function (e) { msg(box.querySelector('#nous-ag-tmsg'), e.message, true); });
		});
		box.querySelectorAll('[data-ton]').forEach(function (b) {
			b.addEventListener('click', function () {
				api('POST', '/tasks/update', { id: b.getAttribute('data-ton'), enabled: b.getAttribute('data-v') === '1' })
					.then(function () { renderTasks(box); }).catch(function (e) { alert(e.message); });
			});
		});
		box.querySelectorAll('[data-trun]').forEach(function (b) {
			b.addEventListener('click', function () {
				api('POST', '/tasks/run', { id: b.getAttribute('data-trun') }).then(function () { renderTasks(box); });
			});
		});
		box.querySelectorAll('[data-tview]').forEach(function (b) {
			b.addEventListener('click', function () { editNote = null; show('notas'); });
		});
		box.querySelectorAll('[data-tdel]').forEach(function (b) {
			b.addEventListener('click', function () {
				if (!confirm('Apagar esta tarefa?')) return;
				api('POST', '/tasks/delete', { id: b.getAttribute('data-tdel') }).then(function () { renderTasks(box); });
			});
		});
	}

	/* ---------------------------------------------------------- avisos */
	function toastBox() {
		var t = document.getElementById('nous-ag-toasts');
		if (!t) {
			t = document.createElement('div');
			t.id = 'nous-ag-toasts';
			document.body.appendChild(t);
		}
		return t;
	}

	function pollNotifs() {
		if (UI.onAuth && UI.onAuth()) return;
		(UI.loadUserId || function (cb) { cb(null); })(function (id) {
			if (!id) return;
			uid = id;
			fetch(AG_URL + qs('/notifications')).then(function (r) { return r.json(); }).then(function (d) {
				var items = d.items || [];
				if (!items.length) return;
				var box = toastBox();
				items.forEach(function (n) {
					var el = document.createElement('div');
					el.className = 'nous-ag-toast';
					var icon = n.kind === 'tarefa' ? '⚡ ' : n.kind === 'compromisso' ? '📅 ' : '⏰ ';
					el.innerHTML = '<b>' + icon + esc(n.title) + '</b>' + (n.body ? '<span>' + esc(n.body.slice(0, 220)) + '</span>' : '');
					el.addEventListener('click', function () {
						el.remove();
						open(n.kind === 'tarefa' ? 'notas' : 'hoje');
					});
					box.appendChild(el);
					setTimeout(function () { el.remove(); }, 20000);
				});
				api('POST', '/notifications/seen', { ids: items.map(function (n) { return n.id; }) }).catch(function () {});
			}).catch(function () {});
		});
	}

	function start() {
		injectStyle();
		setInterval(ensureButton, 1000);
		setTimeout(pollNotifs, 4000);
		setInterval(pollNotifs, 30000);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
