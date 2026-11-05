/* =====================================================================
   Nous - Relatorios (v2.7). Botao "Relatorios" no card Recursos -> a
   biblioteca da Pesquisa Profunda (relatorios visuais salvos pelo monitor,
   127.0.0.1:8990/research). Cada um abre numa aba propria; desde a v2.9
   tambem baixa em PDF ou Word (/research/export).
   ===================================================================== */
(function () {
	'use strict';

	var MON = window.NousUrl(8990);
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var ov = null;
	var dlg = UI.dialogo({ id: 'nous-rp', titulo: '🔎 Relatorios de pesquisa' });

	function injectStyle() {
		if (document.getElementById('nous-rp-style')) return;
		var g = 'rgba(200,150,46,';
		var css =
			'#nous-reports-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);' +
			'border-radius:8px;cursor:pointer;background:transparent;color:var(--nd-texto-ouro);font-weight:600;font-size:12px}' +
			'#nous-reports-open:hover{background:' + g + '.12)}' +
			'#nous-rp{width:600px;max-width:95vw;max-height:80vh;display:flex;flex-direction:column;font-family:Inter,system-ui,sans-serif;' +
			'font-size:13px;color:var(--nd-txt);background:var(--nd-bg);border:1px solid ' + g + '.4);border-radius:16px;' +
			'box-shadow:0 16px 48px var(--nd-sombra);overflow:hidden}' +
			'#nous-rp-head{display:flex;align-items:center;padding:14px 16px 10px;border-bottom:1px solid ' + g + '.15)}' +
			'#nous-rp-head span{flex:1;font:600 15px Cinzel,Georgia,serif;letter-spacing:.05em;color:var(--nd-texto-ouro)}' +
			'.nous-rp-acts{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end;align-self:center;max-width:52%}' +
			'#nous-rp-body{overflow-y:auto;padding:12px 16px 16px}' +
			'.nous-rp-item{display:flex;gap:8px;align-items:flex-start;padding:9px 10px;border-radius:10px;' +
			'background:rgba(var(--nd-tom),.04);margin-bottom:6px}' +
			'.nous-rp-item a{flex:1;color:var(--nd-txt);text-decoration:none}.nous-rp-item a:hover b{color:var(--nd-texto-ouro)}' +
			'.nous-rp-sub{font-size:11px;color:var(--nd-mut);margin-top:3px}' +
			'.nous-rp-del{background:none;border:none;color:var(--nd-mut);cursor:pointer}.nous-rp-del:hover{color:var(--nd-perigo)}' +
			'.nous-rp-exp{align-self:center;padding:3px 8px;border:1px solid ' + g + '.35);border-radius:7px;background:transparent;' +
			'color:var(--nd-texto-ouro);font-size:11px;font-weight:600;cursor:pointer}.nous-rp-exp:hover{background:' + g + '.16)}' +
			'.nous-rp-empty{color:var(--nd-mut);text-align:center;padding:18px 8px;font-size:12px;line-height:1.6}';
		var st = document.createElement('style');
		st.id = 'nous-rp-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-reports-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-reports-open';
		b.type = 'button';
		b.textContent = '🔎 Relatorios';
		b.addEventListener('click', open);
		body.appendChild(b);
	}

	function open() {
		ov = dlg.abrir();
		render();
	}

	function render() {
		var box = ov.querySelector('#nous-rp-body');
		box.innerHTML = '<div class="nous-rp-empty">Carregando...</div>';
		fetch(MON + '/research', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
			var list = d.reports || [];
			if (!list.length) {
				box.innerHTML = '<div class="nous-rp-empty">Nenhum relatorio ainda.<br>Escolha "Pesquisa Profunda (Nous)" ' +
					'no seletor de modelos e faca uma pergunta: o relatorio completo aparece aqui.</div>';
				return;
			}
			box.innerHTML = list.map(function (r) {
				var dt = new Date(r.created * 1000);
				return '<div class="nous-rp-item"><a target="_blank" rel="noopener" href="' + MON + '/research/view?id=' +
					encodeURIComponent(r.id) + '"><b>' + esc(r.question) + '</b><div class="nous-rp-sub">' +
					dt.toLocaleDateString('pt-BR') + ' ' + dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) +
					' · ' + r.n_sources + ' fontes' + (r.domains && r.domains.length ? ' · ' + esc(r.domains.slice(0, 3).join(', ')) : '') +
					'</div></a><span class="nous-rp-acts">' +
					'<button class="nous-rp-exp" type="button" title="Conversar com a IA sobre este relatorio" data-exp="chat" data-rid="' + esc(r.id) + '">💬 Conversar</button>' +
					'<button class="nous-rp-exp" type="button" title="Baixar em PDF" data-exp="pdf" data-rid="' + esc(r.id) + '">PDF</button>' +
					'<button class="nous-rp-exp" type="button" title="Baixar em Word" data-exp="docx" data-rid="' + esc(r.id) + '">Word</button>' +
					'<button class="nous-rp-exp" type="button" title="Abrir nos Documentos para editar" data-exp="doc" data-rid="' + esc(r.id) + '">✎ Editar</button>' +
					'<button class="nous-rp-exp" type="button" title="Copiar o texto com as fontes" data-exp="copiar" data-rid="' + esc(r.id) + '">📋</button>' +
					'<button class="nous-rp-del" type="button" title="Apagar" aria-label="Apagar relatorio" data-id="' + esc(r.id) + '">🗑</button></span></div>';
			}).join('');
			function toast(t, op) { if (UI.toast) UI.toast(t, op); else if (op && op.tipo === 'erro') window.alert(t); }
			box.querySelectorAll('[data-exp]').forEach(function (b) {
				b.addEventListener('click', function () {
					var fmt = b.getAttribute('data-exp'), rid = b.getAttribute('data-rid'), old = b.textContent;
					var q = (list.filter(function (x) { return x.id === rid; })[0] || {}).question || 'Pesquisa';
					var md = fmt === 'doc' || fmt === 'copiar' || fmt === 'chat';
					b.disabled = true;
					b.textContent = '...';
					fetch(MON + '/research/export?id=' + encodeURIComponent(rid) + '&formato=' + (md ? 'md' : fmt))
						.then(function (r) {
							if (r.ok) return md ? r.text() : r.blob();
							return r.json().then(function (d) { throw new Error(d.error || 'falhou'); });
						}).then(function (res) {
							if (fmt === 'doc') {
								if (!window.NousDocs) throw new Error('os Documentos nao carregaram');
								dlg.fechar();
								window.NousDocs.novo(q.slice(0, 100), res);
								return;
							}
							if (fmt === 'chat') {
								var box = document.getElementById('chat-input');
								if (!box) throw new Error('abra uma conversa primeiro');
								dlg.fechar();
								var m = 'Quero conversar sobre esta pesquisa que o Nous fez:\n\n' + res + '\n\nMinha pergunta: ';
								box.focus();
								if (box.tagName === 'TEXTAREA') {
									box.value = m;
									box.dispatchEvent(new Event('input', { bubbles: true }));
								} else {
									document.execCommand('selectAll', false, null);
									document.execCommand('insertText', false, m);
								}
								toast('O relatorio foi para o chat: escreva a sua pergunta no fim e envie.', { tipo: 'info' });
								return;
							}
							if (fmt === 'copiar') {
								return navigator.clipboard.writeText(res).then(function () { toast('Relatorio copiado, com as fontes.'); });
							}
							var a = document.createElement('a');
							a.href = URL.createObjectURL(res);
							a.download = q.slice(0, 80).replace(/[\\/:*?"<>|]+/g, ' ').trim() + '.' + fmt;
							document.body.appendChild(a);
							a.click();
							setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
							toast('Baixado em ' + (fmt === 'pdf' ? 'PDF' : 'Word') + '.');
						}).catch(function (e) { toast('Nao consegui: ' + e.message, { tipo: 'erro' }); })
						.then(function () { b.disabled = false; b.textContent = old; });
				});
			});
			box.querySelectorAll('[data-id]').forEach(function (b) {
				b.addEventListener('click', function () {
					var pede = UI.confirmar ? UI.confirmar('O relatorio some da biblioteca e do computador.',
						{ titulo: 'Apagar relatorio?', ok: 'Apagar', perigo: true }) : Promise.resolve(window.confirm('Apagar este relatorio?'));
					pede.then(function (sim) {
						if (!sim) return;
						fetch(MON + '/research/delete', {
							method: 'POST', headers: { 'Content-Type': 'application/json' },
							body: JSON.stringify({ id: b.getAttribute('data-id') })
						}).then(function () { toast('Relatorio apagado.'); render(); });
					});
				});
			});
		}).catch(function () {
			box.innerHTML = '<div class="nous-rp-empty">O monitor do Nous nao esta no ar.</div>';
		});
	}

	function start() {
		injectStyle();
		window.NousReports = { open: open };
		setInterval(ensureButton, 1000);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
