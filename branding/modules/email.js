/* =====================================================================
   Nous - Assistente de Email (v2.8). Abas: Caixa, Rascunhos, Newsletters,
   Contatos e Contas. Regra: NADA e' enviado sem o clique do usuario; o chat
   ("manda um e-mail pra Maria...") so' cria rascunhos que aparecem aqui.
   Fala com o servico local 127.0.0.1:8995. Usa window.NousUI.
   ===================================================================== */
(function () {
	'use strict';

	var EM = 'http://127.0.0.1:8995';
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var ov = null, tab = 'caixa', account = null, accounts = [], current = null;

	function api(method, path, body) {
		var opt = { method: method, headers: {} };
		if (body) {
			if (account && body.account === undefined) body.account = account;
			opt.headers['Content-Type'] = 'application/json';
			opt.body = JSON.stringify(body);
		}
		return fetch(EM + path, opt).then(function (r) {
			return r.json().then(function (d) {
				if (!r.ok) throw new Error((d && d.error) || 'erro');
				return d;
			});
		});
	}
	function q(path, params) {
		params = params || {};
		if (account) params.account = account;
		var k = Object.keys(params);
		return path + (k.length ? '?' + k.map(function (x) { return encodeURIComponent(x) + '=' + encodeURIComponent(params[x]); }).join('&') : '');
	}
	function addrOf(from) { var m = (from || '').match(/<([^>]+)>/); return m ? m[1] : (from || '').trim(); }
	function nameOf(from) { return (from || '').replace(/<[^>]+>/, '').replace(/"/g, '').trim() || addrOf(from); }
	function box() { return ov.querySelector('#nous-em-body'); }
	function loading(t) { box().innerHTML = '<div class="nous-em-empty">' + (t || 'Carregando...') + '</div>'; }
	function fail(e) { box().innerHTML = '<div class="nous-em-empty nous-em-bad">' + esc(e.message || 'O servico de e-mail nao esta no ar. Abra o Nous pelo atalho.') + '</div>'; }
	function d2(n) { return (n < 10 ? '0' : '') + n; }
	function localInput(ts) {
		var d = new Date(ts * 1000);
		return d.getFullYear() + '-' + d2(d.getMonth() + 1) + '-' + d2(d.getDate()) + 'T' + d2(d.getHours()) + ':' + d2(d.getMinutes());
	}

	/* ---------------------------------------------------------- estilo */
	function injectStyle() {
		if (document.getElementById('nous-em-style')) return;
		var g = 'rgba(200,150,46,';
		var css =
			'#nous-em-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);display:flex;align-items:center;' +
			'justify-content:center;backdrop-filter:blur(3px)}#nous-em-ov.nous-hidden{display:none}' +
			'#nous-em{width:600px;max-width:95vw;height:84vh;display:flex;flex-direction:column;font-family:Inter,system-ui,sans-serif;' +
			'font-size:13px;color:#eee;background:rgba(18,18,22,.97);border:1px solid ' + g + '.4);border-radius:16px;' +
			'box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-em-head{display:flex;align-items:center;gap:8px;padding:14px 16px 8px}' +
			'#nous-em-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'#nous-em-acc{background:rgba(255,255,255,.07);border:1px solid ' + g + '.3);border-radius:7px;color:#eee;font-size:11px;padding:3px 6px;color-scheme:dark}' +
			'#nous-em-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px}' +
			'#nous-em-tabs{display:flex;gap:2px;padding:0 12px;border-bottom:1px solid ' + g + '.15);flex-wrap:wrap}' +
			'.nous-em-tab{background:none;border:none;border-bottom:2px solid transparent;color:#aaa;padding:8px 9px;cursor:pointer;font-size:12px;font-weight:600}' +
			'.nous-em-tab.on{color:#e7c069;border-bottom-color:#c8962e}' +
			'.nous-em-badge{display:inline-block;min-width:16px;padding:0 4px;margin-left:4px;border-radius:8px;background:#c8962e;color:#111;font-size:10px}' +
			'#nous-em-body{flex:1;overflow-y:auto;padding:12px 16px 16px}' +
			'.nous-em-row{padding:8px 9px;border-radius:9px;background:rgba(255,255,255,.04);margin-bottom:5px;cursor:pointer}' +
			'.nous-em-row:hover{background:' + g + '.08)}.nous-em-row.unread .nous-em-subj{font-weight:700}' +
			'.nous-em-top{display:flex;gap:6px;align-items:center}.nous-em-from{font-size:12px;font-weight:600;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
			'.nous-em-subj{font-size:12px;margin:2px 0}.nous-em-sub{font-size:11px;opacity:.6;line-height:1.45}' +
			'.nous-em-cat{font-size:10px;padding:1px 6px;border-radius:9px;background:' + g + '.2);color:#e7c069;white-space:nowrap}' +
			'.nous-em-cat.imp{background:rgba(220,80,60,.25);color:#f3a08f}.nous-em-cat.spam{opacity:.5}' +
			'.nous-em-btn{padding:6px 11px;border:1px solid ' + g + '.45);border-radius:8px;cursor:pointer;background:' + g + '.18);' +
			'color:#e7c069;font-weight:600;font-size:12px;margin:3px 4px 3px 0}.nous-em-btn:hover{background:' + g + '.32)}' +
			'.nous-em-btn.ghost{background:transparent}.nous-em-btn.danger{border-color:rgba(220,80,80,.5);color:#f08080;background:transparent}' +
			'.nous-em-btn:disabled{opacity:.4;cursor:default}' +
			'.nous-em-box{background:rgba(255,255,255,.04);border-radius:10px;padding:9px 11px;margin:8px 0;font-size:12px;line-height:1.55;white-space:pre-wrap;word-wrap:break-word}' +
			'.nous-em-form input,.nous-em-form textarea,.nous-em-form select{box-sizing:border-box;width:100%;padding:7px 9px;margin:3px 0 8px;' +
			'background:rgba(255,255,255,.07);border:1px solid ' + g + '.28);border-radius:8px;color:#eee;font-size:12px;outline:none;font-family:inherit;color-scheme:dark}' +
			'.nous-em-form textarea{min-height:170px;resize:vertical;line-height:1.5}' +
			'.nous-em-lbl{font-size:11px;opacity:.65}.nous-em-msg{font-size:11px;margin-left:4px}.nous-em-bad{color:#f08080}.nous-em-ok{color:#5fd693}' +
			'.nous-em-empty{opacity:.65;text-align:center;padding:18px 8px;font-size:12px;line-height:1.6}' +
			'.nous-em-hint{font-size:11px;opacity:.6;line-height:1.5;margin:2px 0 8px}' +
			'.nous-em-st{font-size:10px;padding:1px 6px;border-radius:9px;margin-left:6px}' +
			'.nous-em-st.pendente{background:' + g + '.25);color:#e7c069}.nous-em-st.agendado{background:rgba(110,150,230,.2);color:#9db8ee}' +
			'.nous-em-st.enviado{background:rgba(58,208,122,.15);color:#5fd693}.nous-em-st.erro{background:rgba(220,60,60,.2);color:#f08080}';
		var st = document.createElement('style');
		st.id = 'nous-em-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	/* ---------------------------------------------------------- montagem */
	function build() {
		if (ov && document.body.contains(ov)) return;
		ov = document.createElement('div');
		ov.id = 'nous-em-ov';
		ov.className = 'nous-hidden';
		ov.innerHTML = '<div id="nous-em"><div id="nous-em-head"><span>✉ Assistente de Email</span>' +
			'<select id="nous-em-acc" title="Conta" style="display:none"></select>' +
			'<button id="nous-em-close" type="button" aria-label="Fechar">&#x2715;</button></div>' +
			'<div id="nous-em-tabs">' + ['caixa:Caixa', 'rascunhos:Rascunhos', 'news:Newsletters', 'contatos:Contatos', 'contas:Contas']
				.map(function (t) { var p = t.split(':'); return '<button class="nous-em-tab" type="button" data-tab="' + p[0] + '">' + p[1] + '</button>'; }).join('') +
			'</div><div id="nous-em-body"></div></div>';
		document.body.appendChild(ov);
		ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
		ov.querySelector('#nous-em-close').addEventListener('click', close);
		ov.querySelectorAll('.nous-em-tab').forEach(function (b) {
			b.addEventListener('click', function () { show(b.getAttribute('data-tab')); });
		});
		ov.querySelector('#nous-em-acc').addEventListener('change', function (e) { account = e.target.value; show(tab); });
	}

	function open(which) {
		build();
		ov.classList.remove('nous-hidden');
		loading('Verificando contas...');
		fetch(EM + '/status', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
			accounts = d.accounts || [];
			if (!account || !accounts.some(function (a) { return a.user === account; })) {
				var p = accounts.filter(function (a) { return a.padrao; })[0];
				account = p ? p.user : null;
			}
			var sel = ov.querySelector('#nous-em-acc');
			sel.style.display = accounts.length > 1 ? '' : 'none';
			sel.innerHTML = accounts.map(function (a) { return '<option value="' + esc(a.user) + '"' + (a.user === account ? ' selected' : '') + '>' + esc(a.user) + '</option>'; }).join('');
			show(d.connected ? (which || 'caixa') : 'contas');
		}).catch(fail);
		badge();
	}
	function close() { ov.classList.add('nous-hidden'); }

	function show(which) {
		tab = which;
		ov.querySelectorAll('.nous-em-tab').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-tab') === which); });
		({ caixa: renderInbox, rascunhos: renderDrafts, news: renderNews, contatos: renderContacts, contas: renderAccounts })[which]();
	}

	function badge() {
		api('GET', '/drafts').then(function (d) {
			var n = d.drafts.filter(function (x) { return x.status === 'pendente'; }).length;
			var t = ov && ov.querySelector('[data-tab="rascunhos"]');
			if (t) t.innerHTML = 'Rascunhos' + (n ? '<span class="nous-em-badge">' + n + '</span>' : '');
		}).catch(function () {});
	}

	/* ---------------------------------------------------------- Caixa */
	function renderInbox() {
		if (!account) { renderAccounts(); return; }
		loading('Lendo a caixa de entrada... (a IA local classifica cada e-mail)');
		api('GET', q('/inbox')).then(function (msgs) {
			if (!msgs.length) { box().innerHTML = '<div class="nous-em-empty">Caixa de entrada vazia.</div>'; return; }
			var order = { 'Importante': 0, 'Pode esperar': 1, 'Notificação': 2, 'Promoção': 3, 'Spam': 4 };
			var html = '<button class="nous-em-btn" id="nous-em-new" type="button">+ Novo e-mail</button>' +
				'<button class="nous-em-btn ghost" id="nous-em-reload" type="button">Atualizar</button>';
			msgs.slice().sort(function (a, b) { return (order[a.category] || 2) - (order[b.category] || 2); }).forEach(function (m) {
				var cls = m.category === 'Importante' ? ' imp' : m.category === 'Spam' ? ' spam' : '';
				html += '<div class="nous-em-row' + (m.unread ? ' unread' : '') + '" data-uid="' + esc(m.uid) + '">' +
					'<div class="nous-em-top"><span class="nous-em-from">' + esc(nameOf(m.from)) + '</span>' +
					(m.category ? '<span class="nous-em-cat' + cls + '">' + esc(m.category) + '</span>' : '') + '</div>' +
					'<div class="nous-em-subj">' + esc(m.subject) + '</div>' +
					(m.summary ? '<div class="nous-em-sub">' + esc(m.summary) + '</div>' : '') + '</div>';
			});
			box().innerHTML = html;
			box().querySelector('#nous-em-new').addEventListener('click', function () { compose({}); });
			box().querySelector('#nous-em-reload').addEventListener('click', renderInbox);
			box().querySelectorAll('[data-uid]').forEach(function (r) {
				r.addEventListener('click', function () { openMsg(r.getAttribute('data-uid')); });
			});
		}).catch(fail);
	}

	function openMsg(uid) {
		loading('Abrindo e resumindo...');
		api('GET', q('/message', { uid: uid })).then(function (m) {
			current = m;
			var unsub = (m.list_unsubscribe || '').match(/<([^>]+)>/g) || [];
			var html = '<button class="nous-em-btn ghost" id="nous-em-back" type="button">← Caixa</button>' +
				'<div style="font-weight:700;margin-top:6px">' + esc(m.subject) + '</div>' +
				'<div class="nous-em-sub">De: ' + esc(m.from) + ' · ' + esc(m.date) + '</div>' +
				(m.summary ? '<div class="nous-em-box"><b>Resumo:</b> ' + esc(m.summary) + '</div>' : '') +
				(m.invite ? '<div class="nous-em-box">📅 Este e-mail tem um <b>convite de calendario</b>. ' +
					'<button class="nous-em-btn" id="nous-em-invite" type="button">Adicionar a minha Agenda</button><span class="nous-em-msg" id="nous-em-im"></span></div>' : '') +
				(m.attachments && m.attachments.length ? '<div class="nous-em-lbl" style="margin-top:6px">Anexos</div>' +
					m.attachments.map(function (a) {
						return '<div class="nous-em-box" style="white-space:normal">📎 ' + esc(a.name) + ' <span class="nous-em-sub">(' + Math.max(1, Math.round(a.size / 1024)) + ' KB)</span><br>' +
							'<a class="nous-em-btn ghost" style="text-decoration:none;display:inline-block" href="' + EM + q('/attachment', { uid: uid, idx: a.idx }) + '">Baixar</a>' +
							'<button class="nous-em-btn" type="button" data-read="' + a.idx + '">Ler com o Nous</button><div data-out="' + a.idx + '"></div></div>';
					}).join('') : '') +
				'<div class="nous-em-box" style="max-height:240px;overflow-y:auto">' + esc((m.body || '').slice(0, 6000)) + '</div>' +
				'<button class="nous-em-btn" id="nous-em-reply" type="button">✍ Rascunhar resposta</button>' +
				(unsub.length ? '<button class="nous-em-btn ghost" id="nous-em-unsub" type="button">Descadastrar desta lista</button>' : '') +
				'<span class="nous-em-msg" id="nous-em-rm"></span>';
			box().innerHTML = html;
			box().querySelector('#nous-em-back').addEventListener('click', renderInbox);
			box().querySelector('#nous-em-reply').addEventListener('click', function () {
				var b = this, msg = box().querySelector('#nous-em-rm');
				b.disabled = true; msg.textContent = 'Escrevendo com a IA local...';
				fetch(EM + q('/draft', { uid: uid }), { method: 'POST' }).then(function (r) { return r.json(); }).then(function (d) {
					compose({ to: addrOf(m.from), to_name: nameOf(m.from), subject: /^re:/i.test(m.subject) ? m.subject : 'Re: ' + m.subject,
						body: d.draft || '', in_reply_to: m.message_id });
				}).catch(function () { b.disabled = false; msg.textContent = 'Nao consegui gerar.'; });
			});
			var inv = box().querySelector('#nous-em-invite');
			if (inv) inv.addEventListener('click', function () {
				(UI.loadUserId || function (cb) { cb(null); })(function (uidUser) {
					api('POST', '/invite/add', { uid: uid, user_id: uidUser }).then(function (d) {
						box().querySelector('#nous-em-im').innerHTML = '<span class="nous-em-ok">✓ ' + d.imported + ' compromisso(s) na Agenda.</span>';
					}).catch(function (e) { box().querySelector('#nous-em-im').innerHTML = '<span class="nous-em-bad">' + esc(e.message) + '</span>'; });
				});
			});
			var un = box().querySelector('#nous-em-unsub');
			if (un) un.addEventListener('click', function () { unsubscribe(nameOf(m.from), unsub.map(function (x) { return x.slice(1, -1); })); });
			box().querySelectorAll('[data-read]').forEach(function (b) {
				b.addEventListener('click', function () {
					var idx = b.getAttribute('data-read'), out = box().querySelector('[data-out="' + idx + '"]');
					b.disabled = true; out.innerHTML = '<div class="nous-em-sub">Lendo o arquivo...</div>';
					api('POST', '/attachment/read', { uid: uid, idx: +idx }).then(function (d) {
						out.innerHTML = (d.boletos.length ? '<div class="nous-em-box">💳 <b>Boleto:</b> ' + d.boletos.map(esc).join('<br>') + '</div>' : '') +
							'<div class="nous-em-box">' + esc(d.summary) + '</div>';
					}).catch(function (e) { b.disabled = false; out.innerHTML = '<div class="nous-em-sub nous-em-bad">' + esc(e.message) + '</div>'; });
				});
			});
		}).catch(fail);
	}

	function unsubscribe(sender, links) {
		var mail = links.filter(function (l) { return /^mailto:/i.test(l); })[0];
		var web = links.filter(function (l) { return /^https?:/i.test(l); })[0];
		var link = mail || web;
		if (!link) return;
		if (!confirm('Descadastrar de "' + sender + '"?' + (mail ? '\n\nO Nous vai enviar um e-mail de descadastro em seu nome.' : '\n\nVai abrir a pagina de descadastro do remetente.'))) return;
		api('POST', '/unsubscribe', { link: link }).then(function (d) {
			if (d.how === 'link') window.open(d.url, '_blank', 'noopener');
			else alert(d.message);
		}).catch(function (e) { alert(e.message); });
	}

	/* ---------------------------------------------------------- Escrever */
	function compose(d) {
		api('GET', '/contacts').then(function (c) { return c.contacts; }).catch(function () { return []; }).then(function (contacts) {
			box().innerHTML = '<button class="nous-em-btn ghost" id="nous-em-back2" type="button">← Voltar</button>' +
				'<div class="nous-em-form" style="margin-top:6px"><span class="nous-em-lbl">Para</span>' +
				'<input id="nous-em-to" list="nous-em-dl" value="' + esc(d.to || '') + '" placeholder="nome@exemplo.com">' +
				'<datalist id="nous-em-dl">' + contacts.filter(function (x) { return x.email; }).map(function (x) {
					return '<option value="' + esc(x.email) + '">' + esc(x.name) + '</option>';
				}).join('') + '</datalist>' +
				'<span class="nous-em-lbl">Assunto</span><input id="nous-em-su" value="' + esc(d.subject || '') + '">' +
				'<span class="nous-em-lbl">Mensagem</span><textarea id="nous-em-bo">' + esc(d.body || '') + '</textarea>' +
				'<div class="nous-em-hint">Revise antes de enviar. Rascunhos ficam em "Rascunhos" ate voce mandar.</div>' +
				'<button class="nous-em-btn" id="nous-em-send" type="button">Enviar agora</button>' +
				'<button class="nous-em-btn ghost" id="nous-em-save" type="button">Salvar rascunho</button>' +
				'<span class="nous-em-msg" id="nous-em-cm"></span></div>';
			box().querySelector('#nous-em-back2').addEventListener('click', function () { show(d.id ? 'rascunhos' : 'caixa'); });
			function payload() {
				return { to: box().querySelector('#nous-em-to').value.trim(), subject: box().querySelector('#nous-em-su').value,
					body: box().querySelector('#nous-em-bo').value, to_name: d.to_name || '', in_reply_to: d.in_reply_to || null };
			}
			function save() {
				var p = payload();
				return d.id ? api('POST', '/drafts/update', Object.assign({ id: d.id }, p)).then(function (r) { return r.draft; })
					: api('POST', '/drafts', p).then(function (r) { d.id = r.draft.id; return r.draft; });
			}
			box().querySelector('#nous-em-save').addEventListener('click', function () {
				save().then(function () { badge(); show('rascunhos'); })
					.catch(function (e) { box().querySelector('#nous-em-cm').innerHTML = '<span class="nous-em-bad">' + esc(e.message) + '</span>'; });
			});
			box().querySelector('#nous-em-send').addEventListener('click', function () {
				var p = payload();
				if (!confirm('Enviar este e-mail para ' + p.to + '?')) return;
				save().then(function (dr) { return api('POST', '/drafts/send', { id: dr.id }); })
					.then(function () { badge(); box().innerHTML = '<div class="nous-em-empty nous-em-ok">✓ E-mail enviado.</div>'; })
					.catch(function (e) { box().querySelector('#nous-em-cm').innerHTML = '<span class="nous-em-bad">' + esc(e.message) + '</span>'; });
			});
		});
	}

	/* ---------------------------------------------------------- Rascunhos */
	function renderDrafts() {
		loading();
		api('GET', '/drafts').then(function (d) {
			var html = '<div class="nous-em-hint">Rascunhos esperando voce. Os pedidos de e-mail feitos no chat aparecem aqui: ' +
				'o Nous nunca envia sozinho.</div>';
			if (!d.drafts.length) html += '<div class="nous-em-empty">Nenhum rascunho.</div>';
			d.drafts.forEach(function (x) {
				var when = x.status === 'agendado' && x.send_at ? ' · envia ' + new Date(x.send_at * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
				html += '<div class="nous-em-row" style="cursor:default"><div class="nous-em-top"><span class="nous-em-from">Para: ' + esc(x.to_name ? x.to_name + ' <' + x.to + '>' : x.to) + '</span>' +
					'<span class="nous-em-st ' + x.status + '">' + x.status + '</span></div>' +
					'<div class="nous-em-subj">' + esc(x.subject) + '</div>' +
					'<div class="nous-em-sub">' + esc((x.body || '').slice(0, 220)) + (x.body && x.body.length > 220 ? '...' : '') + when +
					(x.origem === 'chat' ? ' · pedido no chat' : '') + (x.error ? '<br><span class="nous-em-bad">' + esc(x.error) + '</span>' : '') + '</div>' +
					(x.status !== 'enviado' ? '<div style="margin-top:5px"><button class="nous-em-btn" data-send="' + x.id + '" type="button">Enviar</button>' +
						'<button class="nous-em-btn ghost" data-edit="' + x.id + '" type="button">Editar</button>' +
						'<input type="datetime-local" data-when="' + x.id + '" value="' + localInput(Date.now() / 1000 + 3600) + '" ' +
						'style="background:rgba(255,255,255,.07);border:1px solid rgba(200,150,46,.28);border-radius:7px;color:#eee;font-size:11px;padding:4px;color-scheme:dark">' +
						'<button class="nous-em-btn ghost" data-sched="' + x.id + '" type="button">Agendar</button>' +
						'<button class="nous-em-btn danger" data-del="' + x.id + '" type="button">Apagar</button></div>' : '') + '</div>';
			});
			box().innerHTML = html;
			var byId = {};
			d.drafts.forEach(function (x) { byId[x.id] = x; });
			box().querySelectorAll('[data-send]').forEach(function (b) {
				b.addEventListener('click', function () {
					var x = byId[b.getAttribute('data-send')];
					if (!confirm('Enviar para ' + x.to + '?\n\nAssunto: ' + x.subject)) return;
					b.disabled = true;
					api('POST', '/drafts/send', { id: x.id }).then(function () { badge(); renderDrafts(); })
						.catch(function (e) { alert(e.message); renderDrafts(); });
				});
			});
			box().querySelectorAll('[data-edit]').forEach(function (b) {
				b.addEventListener('click', function () { compose(byId[b.getAttribute('data-edit')]); });
			});
			box().querySelectorAll('[data-sched]').forEach(function (b) {
				b.addEventListener('click', function () {
					var id = b.getAttribute('data-sched'), v = box().querySelector('[data-when="' + id + '"]').value;
					api('POST', '/drafts/schedule', { id: id, send_at: Math.floor(new Date(v).getTime() / 1000) })
						.then(function () { badge(); renderDrafts(); }).catch(function (e) { alert(e.message); });
				});
			});
			box().querySelectorAll('[data-del]').forEach(function (b) {
				b.addEventListener('click', function () {
					if (!confirm('Apagar este rascunho?')) return;
					api('POST', '/drafts/delete', { id: b.getAttribute('data-del') }).then(function () { badge(); renderDrafts(); });
				});
			});
		}).catch(fail);
	}

	/* ---------------------------------------------------------- Newsletters */
	function renderNews() {
		if (!account) { renderAccounts(); return; }
		loading('Procurando listas e newsletters nos ultimos 80 e-mails...');
		api('GET', q('/newsletters')).then(function (d) {
			var html = '<div class="nous-em-hint">Remetentes que mandam e-mail em massa e oferecem descadastro. ' +
				'Nada e\' apagado nem movido: voce escolhe de quais sair.</div>';
			if (!d.newsletters.length) html += '<div class="nous-em-empty">Nenhuma lista encontrada.</div>';
			d.newsletters.forEach(function (n, i) {
				html += '<div class="nous-em-row" style="cursor:default"><div class="nous-em-top"><span class="nous-em-from">' + esc(nameOf(n.sender)) + '</span>' +
					'<span class="nous-em-cat">' + n.count + ' e-mail(s)</span></div><div class="nous-em-sub">' + esc(n.last_subject) + '</div>' +
					'<button class="nous-em-btn ghost" data-un="' + i + '" type="button">Descadastrar</button></div>';
			});
			box().innerHTML = html;
			box().querySelectorAll('[data-un]').forEach(function (b) {
				b.addEventListener('click', function () {
					var n = d.newsletters[+b.getAttribute('data-un')];
					unsubscribe(nameOf(n.sender), [n.mailto, n.http].filter(Boolean));
				});
			});
		}).catch(fail);
	}

	/* ---------------------------------------------------------- Contatos */
	function renderContacts(query) {
		api('GET', '/contacts' + (query ? '?q=' + encodeURIComponent(query) : '')).then(function (d) {
			var html = '<div class="nous-em-hint">O Nous aprende contatos dos e-mails que voce recebe. Com eles, no chat: ' +
				'"manda um e-mail pra Maria...".</div><div class="nous-em-form">' +
				'<input id="nous-em-cq" placeholder="Buscar..." value="' + esc(query || '') + '">' +
				'<div style="display:flex;gap:6px"><input id="nous-em-cn" placeholder="Nome"><input id="nous-em-ce" placeholder="e-mail"></div>' +
				'<button class="nous-em-btn" id="nous-em-cadd" type="button">Adicionar</button>' +
				'<label class="nous-em-btn ghost">Importar .vcf<input id="nous-em-cimp" type="file" accept=".vcf,text/vcard" style="display:none"></label>' +
				'<a class="nous-em-btn ghost" style="text-decoration:none" href="' + EM + '/contacts/export">Exportar .vcf</a></div>';
			if (!d.contacts.length) html += '<div class="nous-em-empty">Nenhum contato ainda. Abra a Caixa para o Nous aprender.</div>';
			d.contacts.forEach(function (c) {
				html += '<div class="nous-em-row" style="cursor:default;display:flex;gap:6px;align-items:center"><div style="flex:1;min-width:0">' +
					'<div class="nous-em-from">' + esc(c.name || '(sem nome)') + '</div><div class="nous-em-sub">' + esc(c.email) +
					(c.phone ? ' · ' + esc(c.phone) : '') + (c.seen ? ' · ' + c.seen + ' e-mail(s)' : '') + '</div></div>' +
					'<button class="nous-em-btn ghost" data-write="' + esc(c.email) + '" data-n="' + esc(c.name) + '" type="button">✉</button>' +
					'<button class="nous-em-btn danger" data-cdel="' + c.id + '" type="button">🗑</button></div>';
			});
			box().innerHTML = html;
			var cq = box().querySelector('#nous-em-cq'), t = null;
			cq.addEventListener('input', function () { clearTimeout(t); t = setTimeout(function () { renderContacts(cq.value.trim()); }, 350); });
			if (query) { cq.focus(); cq.setSelectionRange(cq.value.length, cq.value.length); }
			box().querySelector('#nous-em-cadd').addEventListener('click', function () {
				api('POST', '/contacts', { name: box().querySelector('#nous-em-cn').value, email: box().querySelector('#nous-em-ce').value })
					.then(function () { renderContacts(query); }).catch(function (e) { alert(e.message); });
			});
			box().querySelector('#nous-em-cimp').addEventListener('change', function (ev) {
				var f = ev.target.files && ev.target.files[0];
				if (f) f.text().then(function (txt) { return api('POST', '/contacts/import', { vcf: txt }); })
					.then(function (r) { alert(r.imported + ' contato(s) importado(s).'); renderContacts(); });
			});
			box().querySelectorAll('[data-write]').forEach(function (b) {
				b.addEventListener('click', function () { compose({ to: b.getAttribute('data-write'), to_name: b.getAttribute('data-n') }); });
			});
			box().querySelectorAll('[data-cdel]').forEach(function (b) {
				b.addEventListener('click', function () {
					if (confirm('Apagar este contato?')) api('POST', '/contacts/delete', { id: +b.getAttribute('data-cdel') }).then(function () { renderContacts(query); });
				});
			});
		}).catch(fail);
	}

	/* ---------------------------------------------------------- Contas */
	function renderAccounts() {
		var html = '';
		if (accounts.length) {
			html += '<div class="nous-em-lbl">Contas conectadas</div>';
			accounts.forEach(function (a) {
				html += '<div class="nous-em-row" style="cursor:default;display:flex;gap:6px;align-items:center"><div style="flex:1">' +
					'<div class="nous-em-from">' + esc(a.user) + (a.padrao ? ' <span class="nous-em-cat">padrao</span>' : '') + '</div>' +
					'<div class="nous-em-sub">' + esc(a.imap) + '</div></div>' +
					(a.padrao ? '' : '<button class="nous-em-btn ghost" data-def="' + esc(a.user) + '" type="button">Tornar padrao</button>') +
					'<button class="nous-em-btn danger" data-rm="' + esc(a.user) + '" type="button">Remover</button></div>';
			});
		}
		html += '<div class="nous-em-lbl" style="margin-top:10px">' + (accounts.length ? 'Adicionar outra conta' : 'Conectar sua conta de e-mail') + '</div>' +
			'<div class="nous-em-hint">Tudo e\' processado pelo modelo local: seus e-mails nao saem da maquina.</div>' +
			'<div class="nous-em-form"><span class="nous-em-lbl">Endereco de e-mail</span><input id="nous-em-addr" type="email" placeholder="voce@gmail.com">' +
			'<span class="nous-em-lbl">Senha de aplicativo (nao a senha principal)</span><input id="nous-em-pwd" type="password" placeholder="xxxx xxxx xxxx xxxx">' +
			'<div class="nous-em-hint">Gere em: Gmail > Seguranca > Senhas de app. Outlook > Conta > Seguranca > Senha de app.</div>' +
			'<button class="nous-em-btn" id="nous-em-conn" type="button">Conectar</button><span class="nous-em-msg" id="nous-em-cerr"></span></div>';
		box().innerHTML = html;
		box().querySelector('#nous-em-conn').addEventListener('click', function () {
			var b = this, err = box().querySelector('#nous-em-cerr');
			b.disabled = true; err.textContent = 'Testando a conexao...';
			api('POST', '/connect', { user: box().querySelector('#nous-em-addr').value.trim(), app_password: box().querySelector('#nous-em-pwd').value.trim(), account: null })
				.then(function (d) { account = d.user; open('caixa'); })
				.catch(function (e) { b.disabled = false; err.innerHTML = '<span class="nous-em-bad">' + esc(e.message) + '</span>'; });
		});
		box().querySelectorAll('[data-def]').forEach(function (b) {
			b.addEventListener('click', function () { api('POST', '/accounts/default', { account: b.getAttribute('data-def') }).then(function () { open('contas'); }); });
		});
		box().querySelectorAll('[data-rm]').forEach(function (b) {
			b.addEventListener('click', function () {
				if (!confirm('Remover a conta ' + b.getAttribute('data-rm') + ' do Nous?')) return;
				api('POST', '/disconnect', { account: b.getAttribute('data-rm') }).then(function () { account = null; open('contas'); });
			});
		});
	}

	function start() {
		injectStyle();
		window.NousEmail = { open: open };
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
