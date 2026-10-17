/* =====================================================================
   Nous - Customizacoes de comportamento (gancho oficial de JS)
   O Open WebUI carrega este arquivo no index.html:
       <script src="/static/loader.js" defer crossorigin="use-credentials"></script>
   Ele vem vazio de fabrica, justamente para customizacoes.
   Reaplicado em qualquer maquina por branding/apply_branding.py.

   Recursos:
     - Botao flutuante de tema CLARO/ESCURO na tela inicial.
       (replica fielmente o applyTheme do Open WebUI -
        src/lib/components/chat/Settings/General.svelte - para manter 100%
        de compatibilidade e persistencia via localStorage.theme).
   ===================================================================== */
(function () {
	'use strict';

	/* ---------- Aplicacao de tema (igual ao Open WebUI) ---------- */
	function applyTheme(_theme) {
		var themeToApply =
			_theme === 'oled-dark' ? 'dark' : _theme === 'her' ? 'light' : _theme;
		if (_theme === 'system') {
			themeToApply = window.matchMedia('(prefers-color-scheme: dark)').matches
				? 'dark'
				: 'light';
		}
		if (themeToApply === 'dark' && _theme.indexOf('oled') === -1) {
			var st = document.documentElement.style;
			st.setProperty('--color-gray-800', '#333');
			st.setProperty('--color-gray-850', '#262626');
			st.setProperty('--color-gray-900', '#171717');
			st.setProperty('--color-gray-950', '#0d0d0d');
		}
		['dark', 'light', 'oled-dark']
			.filter(function (e) { return e !== themeToApply; })
			.forEach(function (e) {
				e.split(' ').forEach(function (c) {
					document.documentElement.classList.remove(c);
				});
			});
		themeToApply.split(' ').forEach(function (c) {
			document.documentElement.classList.add(c);
		});
		var meta = document.querySelector('meta[name="theme-color"]');
		if (meta) {
			meta.setAttribute('content', themeToApply === 'dark' ? '#171717' : '#ffffff');
		}
	}

	function isDark() {
		return document.documentElement.classList.contains('dark');
	}

	function setTheme(_theme) {
		try { localStorage.setItem('theme', _theme); } catch (e) {}
		applyTheme(_theme);
		paintToggle();
	}

	/* ---------- Botao flutuante ---------- */
	/* sol = clique leva ao tema claro (estamos no escuro); lua = leva ao escuro */
	var SUN =
		'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
		'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/>' +
		'<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2' +
		'M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>';
	var MOON =
		'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
		'stroke-linecap="round" stroke-linejoin="round">' +
		'<path d="M21 12.79A9 9 0 1 1 11.21 3 7 9 0 0 0 21 12.79z"/></svg>';

	var btn = null;
	var lastDark = null;

	function paintToggle() {
		if (!btn) return;
		var dark = isDark();
		if (dark === lastDark) return;
		lastDark = dark;
		btn.innerHTML = dark ? SUN : MOON;
		btn.setAttribute('aria-label', dark ? 'Mudar para tema claro' : 'Mudar para tema escuro');
		btn.setAttribute('title', dark ? 'Tema claro' : 'Tema escuro');
	}

	function ensureToggle() {
		if (btn && document.body && document.body.contains(btn)) return;
		if (!document.body) return;
		btn = document.createElement('button');
		btn.id = 'nous-theme-toggle';
		btn.type = 'button';
		btn.style.display = 'none';
		lastDark = null;
		btn.addEventListener('click', function () {
			setTheme(isDark() ? 'light' : 'dark');
		});
		document.body.appendChild(btn);
		paintToggle();
	}

	/* ===================== Painel de recursos (Nous Monitor) ===================== */
	var MON_URL = 'http://127.0.0.1:8990';
	var monEl = null, monModels = null, monBtn = null, monBars = {};
	var monCollapsed = false;
	try { monCollapsed = localStorage.getItem('nous-monitor-collapsed') === '1'; } catch (e) {}

	function fmtGB(n) { return (Number(n || 0) / 1073741824).toFixed(1); }

	function injectMonitorStyle() {
		if (document.getElementById('nous-monitor-style')) return;
		var css =
			'#nous-monitor{position:fixed;left:14px;bottom:90px;z-index:9998;width:212px;' +
			'font-family:Inter,system-ui,sans-serif;font-size:12px;color:#eee;' +
			'background:rgba(18,18,22,.82);backdrop-filter:blur(10px);' +
			'border:1px solid rgba(200,150,46,.35);border-radius:12px;' +
			'box-shadow:0 8px 24px rgba(0,0,0,.35);overflow:hidden;user-select:none}' +
			'#nous-mon-head{display:flex;align-items:center;gap:7px;padding:8px 10px;cursor:pointer}' +
			'#nous-mon-title{font-weight:600;letter-spacing:.04em;flex:1}' +
			'.nous-mon-dot{width:7px;height:7px;border-radius:50%;background:#3ad07a;box-shadow:0 0 6px #3ad07a}' +
			'#nous-monitor.nous-mon-off .nous-mon-dot{background:#888;box-shadow:none}' +
			'#nous-mon-caret{width:0;height:0;border-left:4px solid transparent;border-right:4px solid transparent;' +
			'border-top:5px solid #c8962e;transition:transform .2s}' +
			'#nous-monitor.nous-collapsed #nous-mon-caret{transform:rotate(180deg)}' +
			'#nous-monitor.nous-collapsed #nous-mon-body{display:none}' +
			'#nous-mon-body{padding:0 10px 10px;display:flex;flex-wrap:wrap;column-gap:5px}' +
			'#nous-mon-body>*{flex:1 1 100%;min-width:0}' +
			/* atalhos dos paineis (Baixar modelos, Agenda, Habilidades...) em 2 colunas */
			'#nous-mon-body>button:not(#nous-mon-stop){flex:1 1 calc(50% - 5px);font-size:11px!important;' +
			'padding:6px 3px!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}' +
			'.nous-mon-row{display:flex;justify-content:space-between;margin:6px 0 3px;opacity:.85}' +
			'.nous-mon-val{font-variant-numeric:tabular-nums}' +
			'.nous-mon-track{height:6px;border-radius:4px;background:rgba(255,255,255,.1);overflow:hidden}' +
			'.nous-mon-fill{height:100%;width:0;background:linear-gradient(90deg,#c8962e,#e7c069);transition:width .5s}' +
			'.nous-mon-fill2{background:linear-gradient(90deg,#6b7280,#9ca3af)}' +
			'#nous-mon-models{margin:9px 0 4px;display:flex;flex-direction:column;gap:5px}' +
			'.nous-mon-model{display:flex;flex-direction:column;background:rgba(255,255,255,.05);border-radius:7px;padding:5px 7px}' +
			'.nous-mon-model span{opacity:.7;font-size:11px}' +
			'.nous-mon-empty{opacity:.5;font-style:italic;padding:4px 0}' +
			'#nous-mon-stop{width:100%;margin-top:4px;padding:6px;border:0;border-radius:8px;cursor:pointer;' +
			'background:rgba(200,150,46,.18);color:#e7c069;font-weight:600;font-size:12px;transition:background .15s}' +
			'#nous-mon-stop:hover:not(:disabled){background:rgba(200,150,46,.32)}' +
			'#nous-mon-stop:disabled{opacity:.4;cursor:default}' +
			'#nous-store-open{width:100%;margin-top:5px;padding:6px;border:1px solid rgba(200,150,46,.4);' +
			'border-radius:8px;cursor:pointer;background:transparent;color:#e7c069;' +
			'font-weight:600;font-size:12px;transition:background .15s}' +
			'#nous-store-open:hover{background:rgba(200,150,46,.18)}' +
			'#nous-voice-open{width:100%;margin-top:5px;padding:6px;border:1px solid rgba(200,150,46,.25);' +
			'border-radius:8px;cursor:pointer;background:transparent;color:#e7c069;' +
			'font-weight:600;font-size:12px;transition:background .15s}' +
			'#nous-voice-open:hover{background:rgba(200,150,46,.12)}' +
			'#nous-voice-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);' +
			'display:flex;align-items:center;justify-content:center;backdrop-filter:blur(3px)}' +
			'#nous-voice-ov.nous-hidden{display:none}' +
			'#nous-voice-box{width:400px;max-width:92vw;font-family:Inter,system-ui,sans-serif;' +
			'font-size:13px;color:#eee;background:rgba(18,18,22,.97);' +
			'border:1px solid rgba(200,150,46,.4);border-radius:16px;' +
			'box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-voice-head{display:flex;align-items:center;gap:8px;padding:14px 16px 10px}' +
			'#nous-voice-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'#nous-voice-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px;line-height:1}' +
			'#nous-voice-close:hover{color:#eee}' +
			'#nous-voice-body{padding:0 16px 16px}' +
			'#nous-voice-desc{font-size:12px;line-height:1.55;opacity:.8;margin-bottom:12px}' +
			'#nous-voice-status{font-size:12px;margin-bottom:10px}' +
			'.nous-voice-prog{display:flex;flex-direction:column;gap:5px}' +
			'.nous-voice-ptxt{font-size:11px;opacity:.75}' +
			'#nous-voice-btn{width:100%;padding:8px;border:0;border-radius:9px;cursor:pointer;' +
			'background:rgba(200,150,46,.22);color:#e7c069;font-weight:700;font-size:13px;transition:background .15s}' +
			'#nous-voice-btn:hover:not(:disabled){background:rgba(200,150,46,.38)}' +
			'#nous-voice-btn:disabled{opacity:.4;cursor:default}' +
			'#nous-email-open{width:100%;margin-top:5px;padding:6px;border:1px solid rgba(200,150,46,.25);' +
			'border-radius:8px;cursor:pointer;background:transparent;color:#e7c069;' +
			'font-weight:600;font-size:12px;transition:background .15s}' +
			'#nous-email-open:hover{background:rgba(200,150,46,.12)}' +
			'#nous-email-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);' +
			'display:flex;align-items:center;justify-content:center;backdrop-filter:blur(3px)}' +
			'#nous-email-ov.nous-hidden{display:none}' +
			'#nous-email-box{width:460px;max-width:95vw;max-height:85vh;overflow-y:auto;' +
			'font-family:Inter,system-ui,sans-serif;font-size:13px;color:#eee;' +
			'background:rgba(18,18,22,.97);border:1px solid rgba(200,150,46,.4);' +
			'border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.55)}' +
			'#nous-email-head{display:flex;align-items:center;gap:8px;padding:14px 16px 10px;' +
			'border-bottom:1px solid rgba(200,150,46,.15);' +
			'position:sticky;top:0;z-index:1;background:rgba(18,18,22,.97)}' +
			'#nous-email-head span{flex:1;font-weight:700;font-size:15px;color:#e7c069}' +
			'#nous-email-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px;line-height:1}' +
			'#nous-email-close:hover{color:#eee}' +
			'#nous-email-body{padding:14px 16px}' +
			'.nous-email-form input{width:100%;box-sizing:border-box;padding:7px 10px;margin:5px 0 10px;' +
			'background:rgba(255,255,255,.07);border:1px solid rgba(200,150,46,.3);' +
			'border-radius:8px;color:#eee;font-size:12px;outline:none}' +
			'.nous-email-form input:focus{border-color:#c8962e}' +
			'.nous-email-label{font-size:11px;opacity:.7;margin-bottom:2px}' +
			'.nous-email-hint{font-size:11px;opacity:.6;line-height:1.5;margin-bottom:12px}' +
			'.nous-email-btn{width:100%;padding:8px;border:0;border-radius:9px;cursor:pointer;margin-top:6px;' +
			'background:rgba(200,150,46,.22);color:#e7c069;font-weight:700;font-size:13px;transition:background .15s}' +
			'.nous-email-btn:hover:not(:disabled){background:rgba(200,150,46,.38)}' +
			'.nous-email-btn:disabled{opacity:.4;cursor:default}' +
			'.nous-email-btn-danger{background:rgba(200,60,60,.18);color:#f08080}' +
			'.nous-email-btn-danger:hover:not(:disabled){background:rgba(200,60,60,.32)}' +
			'.nous-email-msg{font-size:12px;margin:8px 0;padding:7px 10px;border-radius:7px;' +
			'background:rgba(255,255,255,.06);line-height:1.5}' +
			'.nous-email-row{padding:9px 0;border-bottom:1px solid rgba(255,255,255,.06);cursor:pointer}' +
			'.nous-email-row:hover{background:rgba(200,150,46,.06);border-radius:6px}' +
			'.nous-email-from{font-weight:600;font-size:12px}' +
			'.nous-email-subj{font-size:12px;margin:2px 0}' +
			'.nous-email-cat{display:inline-block;font-size:10px;padding:1px 6px;border-radius:10px;' +
			'background:rgba(200,150,46,.2);color:#e7c069;margin-right:5px}' +
			'.nous-email-summ{font-size:11px;opacity:.7;margin-top:2px}' +
			'.nous-email-back{background:none;border:none;color:#c8962e;cursor:pointer;font-size:12px;' +
			'padding:0 0 10px;display:block}' +
			'.nous-email-back:hover{text-decoration:underline}' +
			'.nous-email-draft{width:100%;box-sizing:border-box;min-height:120px;padding:8px;' +
			'background:rgba(255,255,255,.06);border:1px solid rgba(200,150,46,.25);' +
			'border-radius:8px;color:#eee;font-size:12px;resize:vertical;margin:8px 0}';
		var st = document.createElement('style');
		st.id = 'nous-monitor-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	function buildMonitor() {
		if (monEl && document.body && document.body.contains(monEl)) return;
		if (!document.body) return;
		monEl = document.createElement('div');
		monEl.id = 'nous-monitor';
		monEl.innerHTML =
			'<div id="nous-mon-head"><span class="nous-mon-dot"></span>' +
			'<span id="nous-mon-title">Recursos</span><span id="nous-mon-caret"></span></div>' +
			'<div id="nous-mon-body">' +
			'<div class="nous-mon-row"><span>VRAM (GPU)</span><span class="nous-mon-val" data-k="ded">—</span></div>' +
			'<div class="nous-mon-track"><div class="nous-mon-fill" data-k="ded"></div></div>' +
			'<div class="nous-mon-row"><span>Compartilhada</span><span class="nous-mon-val" data-k="shr">—</span></div>' +
			'<div class="nous-mon-track"><div class="nous-mon-fill nous-mon-fill2" data-k="shr"></div></div>' +
			'<div id="nous-mon-models"></div>' +
			'<button id="nous-mon-stop" type="button" disabled>Parar modelos</button>' +
			'<button id="nous-store-open" type="button">Baixar modelos</button>' +
			'<button id="nous-voice-open" type="button">🎙 Ativar voz em PT-BR</button>' +
			'<button id="nous-email-open" type="button">✉ Assistente de Email</button></div>';
		document.body.appendChild(monEl);
		monModels = monEl.querySelector('#nous-mon-models');
		monBtn = monEl.querySelector('#nous-mon-stop');
		monBars = {
			dedVal: monEl.querySelector('.nous-mon-val[data-k="ded"]'),
			shrVal: monEl.querySelector('.nous-mon-val[data-k="shr"]'),
			dedFill: monEl.querySelector('.nous-mon-fill[data-k="ded"]'),
			shrFill: monEl.querySelector('.nous-mon-fill[data-k="shr"]')
		};
		monEl.querySelector('#nous-mon-head').addEventListener('click', function () {
			monCollapsed = !monCollapsed;
			try { localStorage.setItem('nous-monitor-collapsed', monCollapsed ? '1' : '0'); } catch (e) {}
			monEl.classList.toggle('nous-collapsed', monCollapsed);
		});
		monBtn.addEventListener('click', function () {
			monBtn.disabled = true; monBtn.textContent = 'Liberando…';
			fetch(MON_URL + '/unload', { method: 'POST' })
				.catch(function () {})
				.then(function () { setTimeout(refreshMonitor, 700); });
		});
		monEl.querySelector('#nous-store-open').addEventListener('click', openStore);
		monEl.querySelector('#nous-voice-open').addEventListener('click', openVoice);
		monEl.querySelector('#nous-email-open').addEventListener('click', openEmail);
		monEl.classList.toggle('nous-collapsed', monCollapsed);
	}

	function refreshMonitor() {
		if (!monEl) return;
		fetch(MON_URL + '/stats', { cache: 'no-store' })
			.then(function (r) { return r.json(); })
			.then(function (s) {
				monEl.classList.remove('nous-mon-off');
				var g = s.gpu || {};
				if (g.ded_total) {
					monBars.dedVal.textContent = fmtGB(g.ded_used) + ' / ' + fmtGB(g.ded_total) + ' GB';
					monBars.dedFill.style.width = Math.min(100, 100 * g.ded_used / g.ded_total) + '%';
				}
				if (g.shr_total) {
					monBars.shrVal.textContent = fmtGB(g.shr_used) + ' / ' + fmtGB(g.shr_total) + ' GB';
					monBars.shrFill.style.width = Math.min(100, 100 * g.shr_used / g.shr_total) + '%';
				}
				var models = s.models || [];
				if (!models.length) {
					monModels.innerHTML = '<div class="nous-mon-empty">Nenhum modelo na memoria</div>';
					monBtn.disabled = true; monBtn.textContent = 'Parar modelos';
				} else {
					monModels.innerHTML = models.map(function (m) {
						var left = (m.seconds_left != null) ? (' · libera em ' + m.seconds_left + 's') : '';
						return '<div class="nous-mon-model"><b>' + m.name + '</b><span>' +
							fmtGB(m.vram) + ' GB VRAM' +
							(m.shared > 0 ? ' + ' + fmtGB(m.shared) + ' compart.' : '') +
							left + '</span></div>';
					}).join('');
					monBtn.disabled = false; monBtn.textContent = 'Parar modelos';
				}
			})
			.catch(function () {
				monEl.classList.add('nous-mon-off');
				if (monModels) monModels.innerHTML = '<div class="nous-mon-empty">Monitor offline</div>';
			});
	}

	/* Mostra o botao apenas na tela inicial (rota "/") */
	function onHome() {
		var p = location.pathname;
		return p === '/' || p === '' || p === '/index.html';
	}

	/* Coloca o wordmark "NOUS" no topo, DENTRO do painel de conteudo (o irmao
	   da barra lateral). Sendo filho do painel, ele acompanha a animacao de
	   abrir/fechar a barra lateral via CSS puro -> centralizado e SEM delay.
	   #nous-mark-anchor tem height 0 (nao empurra nada); o NOUS fica absolute
	   no topo dele. Na tela de login (sem #sidebar) usa-se o body::after. */
	function ensureTopWordmark() {
		var sidebar = document.getElementById('sidebar');
		var anchor = document.getElementById('nous-mark-anchor');
		if (!sidebar || !sidebar.parentElement) {        // login / sem shell
			if (anchor) anchor.remove();
			document.body.classList.remove('nous-shell-mark');
			return;
		}
		var shell = sidebar.parentElement;
		var content = null, maxW = -1;                    // painel = irmao mais largo
		for (var i = 0; i < shell.children.length; i++) {
			var c = shell.children[i];
			if (c === sidebar) continue;
			var w = c.getBoundingClientRect().width;
			if (w > maxW) { maxW = w; content = c; }
		}
		if (!content || maxW <= 0) {
			if (anchor) anchor.remove();
			document.body.classList.remove('nous-shell-mark');
			return;
		}
		if (!anchor) {
			anchor = document.createElement('div');
			anchor.id = 'nous-mark-anchor';
			var wm = document.createElement('div');
			wm.id = 'nous-home-wordmark';
			wm.textContent = 'NOUS';
			anchor.appendChild(wm);
		}
		/* mantem como 1o filho do painel (so' re-insere em troca de rota, nunca
		   no toggle da barra -> sem disputa com o Svelte no caso que importa) */
		if (content.firstChild !== anchor) content.insertBefore(anchor, content.firstChild);
		document.body.classList.add('nous-shell-mark');
	}

	/* ====================== Painel "O que o Nous sabe" ====================== */
	var MEM_URL    = 'http://127.0.0.1:8993';
	var memBtnEl   = null;
	var memPanelEl = null;
	var memOpen    = false;
	var _nousUid   = null;   /* user_id do Open WebUI (carregado uma vez) */
	var _activePer = 'default';
	var _personas  = {};
	var _editingId = null;

	/* Obtem user_id via API do Open WebUI (token em localStorage) */
	function loadUserId(cb) {
		if (_nousUid) { cb(_nousUid); return; }
		var token = '';
		try { token = localStorage.getItem('token') || ''; } catch (e) {}
		if (!token) { cb(null); return; }
		fetch('/api/v1/auths/', { headers: { 'Authorization': 'Bearer ' + token } })
			.then(function(r) { return r.json(); })
			.then(function(d) { _nousUid = d.id || null; cb(_nousUid); })
			.catch(function() { cb(null); });
	}

	/* ---- Estilos ---- */
	function injectMemStyle() {
		if (document.getElementById('nous-mem-style')) return;
		var css =
			/* botao flutuante */
			'#nous-mem-btn{position:fixed;right:14px;bottom:90px;z-index:9999;' +
			'width:40px;height:40px;border-radius:50%;border:1.5px solid rgba(200,150,46,.5);' +
			'background:rgba(18,18,22,.82);backdrop-filter:blur(10px);color:#c8962e;' +
			'cursor:pointer;display:flex;align-items:center;justify-content:center;' +
			'box-shadow:0 4px 16px rgba(0,0,0,.3);transition:background .15s}' +
			'#nous-mem-btn:hover{background:rgba(200,150,46,.18)}' +
			'#nous-mem-btn svg{width:20px;height:20px}' +
			/* painel */
			'#nous-mem-panel{position:fixed;right:14px;bottom:140px;z-index:9998;width:300px;' +
			'max-height:520px;display:flex;flex-direction:column;' +
			'font-family:Inter,system-ui,sans-serif;font-size:13px;color:#eee;' +
			'background:rgba(18,18,22,.92);backdrop-filter:blur(12px);' +
			'border:1px solid rgba(200,150,46,.35);border-radius:14px;' +
			'box-shadow:0 12px 32px rgba(0,0,0,.45);overflow:hidden}' +
			'#nous-mem-panel.nous-hidden{display:none}' +
			/* cabecalho */
			'#nous-mem-head{display:flex;align-items:center;gap:8px;padding:10px 12px 8px;' +
			'border-bottom:1px solid rgba(255,255,255,.07)}' +
			'#nous-mem-head span{flex:1;font-weight:700;letter-spacing:.04em;color:#e7c069}' +
			'#nous-mem-close{background:none;border:none;color:#888;cursor:pointer;' +
			'font-size:18px;line-height:1;padding:0 2px}' +
			'#nous-mem-close:hover{color:#eee}' +
			/* seletor de persona */
			'#nous-per-row{display:flex;align-items:center;gap:7px;padding:8px 12px;' +
			'border-bottom:1px solid rgba(255,255,255,.07)}' +
			'#nous-per-row label{font-size:11px;opacity:.6;white-space:nowrap}' +
			'#nous-per-sel{flex:1;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);' +
			'border-radius:7px;color:#eee;padding:4px 7px;font-size:12px;cursor:pointer}' +
			'#nous-per-new{background:rgba(200,150,46,.15);border:1px solid rgba(200,150,46,.4);' +
			'color:#e7c069;border-radius:7px;padding:4px 8px;font-size:11px;cursor:pointer;white-space:nowrap}' +
			'#nous-per-new:hover{background:rgba(200,150,46,.28)}' +
			/* formulario nova persona */
			'#nous-per-form{padding:0 12px 8px;display:none;flex-direction:column;gap:5px;' +
			'border-bottom:1px solid rgba(255,255,255,.07)}' +
			'#nous-per-form.active{display:flex}' +
			'.nous-per-inp{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);' +
			'border-radius:7px;color:#eee;padding:5px 8px;font-size:12px;width:100%;box-sizing:border-box}' +
			'.nous-per-row2{display:flex;gap:6px}' +
			'.nous-per-save{flex:1;background:rgba(200,150,46,.18);border:1px solid rgba(200,150,46,.4);' +
			'color:#e7c069;border-radius:7px;padding:5px;font-size:12px;cursor:pointer}' +
			'.nous-per-save:hover{background:rgba(200,150,46,.32)}' +
			'.nous-per-cancel{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.15);' +
			'color:#aaa;border-radius:7px;padding:5px 10px;font-size:12px;cursor:pointer}' +
			/* lista de memorias */
			'#nous-mem-list{flex:1;overflow-y:auto;padding:6px 8px}' +
			'#nous-mem-list::-webkit-scrollbar{width:5px}' +
			'#nous-mem-list::-webkit-scrollbar-track{background:transparent}' +
			'#nous-mem-list::-webkit-scrollbar-thumb{background:rgba(200,150,46,.3);border-radius:4px}' +
			'.nous-mem-item{display:flex;align-items:flex-start;gap:6px;padding:6px 4px;' +
			'border-bottom:1px solid rgba(255,255,255,.05)}' +
			'.nous-mem-item:last-child{border-bottom:none}' +
			'.nous-mem-text{flex:1;font-size:12px;line-height:1.4;word-break:break-word}' +
			'.nous-mem-acts{display:flex;flex-direction:column;gap:3px;flex-shrink:0}' +
			'.nous-mem-edit,.nous-mem-del{background:none;border:none;cursor:pointer;' +
			'font-size:13px;padding:1px 3px;border-radius:4px;transition:background .1s}' +
			'.nous-mem-edit:hover{background:rgba(200,150,46,.2)}' +
			'.nous-mem-del:hover{background:rgba(220,60,60,.2)}' +
			'.nous-mem-edit-row{display:flex;gap:5px;flex:1}' +
			'.nous-mem-edit-inp{flex:1;background:rgba(255,255,255,.1);border:1px solid rgba(200,150,46,.4);' +
			'border-radius:6px;color:#eee;padding:3px 6px;font-size:12px}' +
			'.nous-mem-save-btn,.nous-mem-cancel-btn{background:none;border:none;cursor:pointer;font-size:13px;padding:2px 5px}' +
			'.nous-mem-empty{opacity:.5;font-style:italic;padding:10px;text-align:center;font-size:12px}' +
			'.nous-mem-loading{opacity:.6;padding:10px;text-align:center;font-size:12px}' +
			/* rodape / adicionar */
			'#nous-mem-foot{padding:8px 10px;border-top:1px solid rgba(255,255,255,.07);' +
			'display:flex;gap:6px}' +
			'#nous-mem-inp{flex:1;background:rgba(255,255,255,.07);' +
			'border:1px solid rgba(255,255,255,.15);border-radius:8px;' +
			'color:#eee;padding:6px 9px;font-size:12px}' +
			'#nous-mem-inp::placeholder{color:#666}' +
			'#nous-mem-add{background:rgba(200,150,46,.18);border:1px solid rgba(200,150,46,.4);' +
			'color:#e7c069;border-radius:8px;padding:6px 10px;font-size:12px;cursor:pointer;' +
			'font-weight:600;white-space:nowrap}' +
			'#nous-mem-add:hover{background:rgba(200,150,46,.32)}' +
			'.nous-mem-pin{opacity:.3;filter:grayscale(1)}.nous-mem-pin.on{opacity:1;filter:none}' +
			'#nous-mem-tidy{width:100%;margin-top:8px;padding:6px;border:1px dashed rgba(200,150,46,.4);border-radius:8px;' +
			'background:transparent;color:#e7c069;cursor:pointer;font-size:12px}' +
			'#nous-mem-tidy:hover{background:rgba(200,150,46,.12)}' +
			'.nous-tidy-g{display:flex;gap:7px;align-items:flex-start;padding:7px 4px;font-size:12px;line-height:1.45;' +
			'border-bottom:1px solid rgba(255,255,255,.06);cursor:pointer}' +
			'.nous-tidy-g i{opacity:.5;font-style:normal}' +
			'.nous-tidy-row{display:flex;gap:6px;margin-top:8px}.nous-tidy-row button{flex:1;padding:6px;border-radius:8px;' +
			'cursor:pointer;border:1px solid rgba(200,150,46,.4);background:rgba(200,150,46,.18);color:#e7c069;font-size:12px}';
		var st = document.createElement('style');
		st.id = 'nous-mem-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	/* ---- Icone cerebro ---- */
	var BRAIN_SVG =
		'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"' +
		' stroke-linecap="round" stroke-linejoin="round">' +
		'<path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1-2.96-3.08' +
		' 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.44-4.66z"/>' +
		'<path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 2.96-3.08' +
		' 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.44-4.66z"/>' +
		'</svg>';

	/* ---- Botao flutuante ---- */
	function ensureMemBtn() {
		if (memBtnEl && document.body && document.body.contains(memBtnEl)) return;
		if (!document.body) return;
		memBtnEl = document.createElement('button');
		memBtnEl.id = 'nous-mem-btn';
		memBtnEl.type = 'button';
		memBtnEl.title = 'O que o Nous sabe';
		memBtnEl.setAttribute('aria-label', 'O que o Nous sabe');
		memBtnEl.innerHTML = BRAIN_SVG;
		memBtnEl.addEventListener('click', toggleMemPanel);
		document.body.appendChild(memBtnEl);
		buildMemPanel();
	}

	/* ---- Construcao do painel ---- */
	function buildMemPanel() {
		if (memPanelEl && document.body && document.body.contains(memPanelEl)) return;
		if (!document.body) return;
		memPanelEl = document.createElement('div');
		memPanelEl.id = 'nous-mem-panel';
		memPanelEl.classList.add('nous-hidden');
		memPanelEl.innerHTML =
			'<div id="nous-mem-head">' +
			'<span>O que o Nous sabe</span>' +
			'<button id="nous-mem-close" type="button" aria-label="Fechar">&#x2715;</button>' +
			'</div>' +
			'<div id="nous-per-row">' +
			'<label>Persona</label>' +
			'<select id="nous-per-sel"></select>' +
			'<button id="nous-per-new" type="button">+ Nova</button>' +
			'</div>' +
			'<div id="nous-per-form">' +
			'<input class="nous-per-inp" id="nous-per-name" type="text" placeholder="Nome da persona (ex.: trabalho)">' +
			'<input class="nous-per-inp" id="nous-per-folder" type="text" placeholder="Pasta de arquivos (opcional)">' +
			'<div class="nous-per-row2">' +
			'<button class="nous-per-save" id="nous-per-create" type="button">Criar persona</button>' +
			'<button class="nous-per-cancel" id="nous-per-cancel" type="button">Cancelar</button>' +
			'</div></div>' +
			'<div id="nous-mem-list"><div class="nous-mem-loading">Carregando...</div></div>' +
			'<div id="nous-mem-foot">' +
			'<input id="nous-mem-inp" type="text" placeholder="Adicionar memoria...">' +
			'<button id="nous-mem-add" type="button">+ Salvar</button>' +
			'</div>';
		document.body.appendChild(memPanelEl);

		memPanelEl.querySelector('#nous-mem-close').addEventListener('click', function() {
			closeMemPanel();
		});
		memPanelEl.querySelector('#nous-per-new').addEventListener('click', function() {
			var f = memPanelEl.querySelector('#nous-per-form');
			f.classList.toggle('active');
		});
		memPanelEl.querySelector('#nous-per-cancel').addEventListener('click', function() {
			memPanelEl.querySelector('#nous-per-form').classList.remove('active');
		});
		memPanelEl.querySelector('#nous-per-create').addEventListener('click', createPersona);
		memPanelEl.querySelector('#nous-per-sel').addEventListener('change', function() {
			switchPersona(this.value);
		});
		memPanelEl.querySelector('#nous-mem-add').addEventListener('click', addMemory);
		memPanelEl.querySelector('#nous-mem-inp').addEventListener('keydown', function(e) {
			if (e.key === 'Enter') addMemory();
		});
	}

	function toggleMemPanel() {
		memOpen = !memOpen;
		if (!memPanelEl) buildMemPanel();
		if (memOpen) {
			memPanelEl.classList.remove('nous-hidden');
			loadUserId(function(uid) {
				if (!uid) {
					memPanelEl.querySelector('#nous-mem-list').innerHTML =
						'<div class="nous-mem-empty">Faca login para ver suas memorias.</div>';
					return;
				}
				loadPersonas(function() { loadMemories(); });
			});
		} else {
			closeMemPanel();
		}
	}

	function closeMemPanel() {
		memOpen = false;
		if (memPanelEl) memPanelEl.classList.add('nous-hidden');
	}

	/* ---- Personas ---- */
	function loadPersonas(cb) {
		fetch(MEM_URL + '/personas', { cache: 'no-store' })
			.then(function(r) { return r.json(); })
			.then(function(data) {
				_personas = data || {};
				var sel = memPanelEl.querySelector('#nous-per-sel');
				fetch(MEM_URL + '/persona?user_id=' + encodeURIComponent(_nousUid), { cache: 'no-store' })
					.then(function(r) { return r.json(); })
					.then(function(d) {
						_activePer = d.persona || 'default';
						renderPersonaSel(sel);
						if (cb) cb();
					})
					.catch(function() { if (cb) cb(); });
			})
			.catch(function() { if (cb) cb(); });
	}

	function renderPersonaSel(sel) {
		if (!sel) return;
		sel.innerHTML = '';
		var keys = Object.keys(_personas).sort(function(a, b) {
			if (a === 'default') return -1;
			if (b === 'default') return 1;
			return a.localeCompare(b);
		});
		keys.forEach(function(k) {
			var opt = document.createElement('option');
			opt.value = k;
			opt.textContent = k === 'default' ? 'Padrao' : k;
			if (k === _activePer) opt.selected = true;
			sel.appendChild(opt);
		});
	}

	function switchPersona(name) {
		if (!_nousUid) return;
		_activePer = name;
		fetch(MEM_URL + '/persona', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ user_id: _nousUid, name: name })
		}).then(function() { loadMemories(); }).catch(function() {});
	}

	function createPersona() {
		var name   = (memPanelEl.querySelector('#nous-per-name').value || '').trim();
		var folder = (memPanelEl.querySelector('#nous-per-folder').value || '').trim();
		if (!name) return;
		fetch(MEM_URL + '/persona/config', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ name: name, folder: folder, description: '' })
		}).then(function() {
			memPanelEl.querySelector('#nous-per-name').value = '';
			memPanelEl.querySelector('#nous-per-folder').value = '';
			memPanelEl.querySelector('#nous-per-form').classList.remove('active');
			loadPersonas(function() { switchPersona(name); });
		}).catch(function() {});
	}

	/* ---- Memorias ---- */
	function loadMemories() {
		if (!_nousUid) return;
		var list = memPanelEl.querySelector('#nous-mem-list');
		list.innerHTML = '<div class="nous-mem-loading">Carregando...</div>';
		fetch(MEM_URL + '/memories?user_id=' + encodeURIComponent(_nousUid) +
			'&persona=' + encodeURIComponent(_activePer), { cache: 'no-store' })
			.then(function(r) { return r.json(); })
			.then(function(mems) { renderMemories(mems); })
			.catch(function() {
				list.innerHTML = '<div class="nous-mem-empty">API offline — inicie o Nous normalmente.</div>';
			});
	}

	function renderMemories(mems) {
		var list = memPanelEl.querySelector('#nous-mem-list');
		_editingId = null;
		if (!mems || !mems.length) {
			list.innerHTML = '<div class="nous-mem-empty">Nenhuma memoria nesta persona.</div>';
			return;
		}
		list.innerHTML = '';
		mems.forEach(function(m) {
			var item = document.createElement('div');
			item.className = 'nous-mem-item';
			item.dataset.id = m.id;
			item.innerHTML =
				'<span class="nous-mem-text">' + _esc(m.text) + '</span>' +
				'<div class="nous-mem-acts">' +
				'<button class="nous-mem-pin' + (m.pinned ? ' on' : '') + '" type="button" title="' +
				(m.pinned ? 'Fixada: entra em toda conversa. Clique para soltar' : 'Fixar: entra em toda conversa') +
				'">&#x1F4CC;</button>' +
				'<button class="nous-mem-edit" title="Editar" type="button">&#x270F;</button>' +
				'<button class="nous-mem-del" title="Deletar" type="button">&#x1F5D1;</button>' +
				'</div>';
			item.querySelector('.nous-mem-pin').addEventListener('click', function() { pinMem(m.id, !m.pinned); });
			item.querySelector('.nous-mem-edit').addEventListener('click', function() { startEdit(item, m); });
			item.querySelector('.nous-mem-del').addEventListener('click', function() { deleteMem(m.id); });
			list.appendChild(item);
		});
		if (mems.length >= 2) {
			var tidy = document.createElement('button');
			tidy.type = 'button';
			tidy.id = 'nous-mem-tidy';
			tidy.textContent = '🧹 Organizar memorias';
			tidy.title = 'O Nous procura memorias repetidas ou que se contradizem e propoe juntar. Voce aprova antes.';
			tidy.addEventListener('click', tidyMemories);
			list.appendChild(tidy);
		}
	}

	function pinMem(id, pinned) {
		if (!_nousUid) return;
		fetch(MEM_URL + '/memories/' + id + '/pin', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ user_id: _nousUid, pinned: pinned })
		}).then(function() { loadMemories(); }).catch(loadMemories);
	}

	/* Faxina: o modelo PROPOE, o usuario marca o que aceita e aplica. */
	function tidyMemories() {
		var list = memPanelEl.querySelector('#nous-mem-list');
		list.innerHTML = '<div class="nous-mem-loading">Lendo as memorias... (pode levar um minuto)</div>';
		fetch(MEM_URL + '/memories/tidy', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ user_id: _nousUid, persona: _activePer })
		}).then(function(r) { return r.json(); }).then(function(d) {
			if (d.error) throw new Error(d.error);
			var gs = d.grupos || [];
			if (!gs.length) {
				list.innerHTML = '<div class="nous-mem-empty">Tudo em ordem: nada repetido nem contraditorio.</div>';
				setTimeout(loadMemories, 2500);
				return;
			}
			list.innerHTML = '<div class="nous-mem-empty" style="text-align:left">Marque o que pode juntar:</div>' +
				gs.map(function(g, i) {
					return '<label class="nous-tidy-g"><input type="checkbox" checked data-g="' + i + '">' +
						'<span><b>' + (g.motivo === 'contradicao' ? 'Contradicao' : 'Repetida') + ':</b> ' +
						g.antes.map(_esc).join(' <i>+</i> ') + '<br>&rarr; <b>' + _esc(g.texto) + '</b></span></label>';
				}).join('') +
				'<div class="nous-tidy-row"><button type="button" id="nous-tidy-ok">Aplicar</button>' +
				'<button type="button" id="nous-tidy-no">Cancelar</button></div>';
			list.querySelector('#nous-tidy-no').addEventListener('click', loadMemories);
			list.querySelector('#nous-tidy-ok').addEventListener('click', function() {
				var sel = [];
				list.querySelectorAll('[data-g]').forEach(function(cb) {
					if (cb.checked) sel.push(gs[+cb.getAttribute('data-g')]);
				});
				fetch(MEM_URL + '/memories/tidy/apply', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ user_id: _nousUid, grupos: sel })
				}).then(loadMemories, loadMemories);
			});
		}).catch(function(e) {
			list.innerHTML = '<div class="nous-mem-empty">' + _esc(e.message || 'Nao consegui organizar agora.') + '</div>';
			setTimeout(loadMemories, 4000);
		});
	}

	function startEdit(item, m) {
		_editingId = m.id;
		var inp = document.createElement('input');
		inp.className = 'nous-mem-edit-inp';
		inp.type = 'text';
		inp.value = m.text;
		var saveBtn   = document.createElement('button');
		saveBtn.type  = 'button';
		saveBtn.className = 'nous-mem-save-btn';
		saveBtn.textContent = '✓';
		saveBtn.title = 'Salvar';
		var cancelBtn = document.createElement('button');
		cancelBtn.type  = 'button';
		cancelBtn.className = 'nous-mem-cancel-btn';
		cancelBtn.textContent = '✕';
		cancelBtn.title = 'Cancelar';
		var row = document.createElement('div');
		row.className = 'nous-mem-edit-row';
		row.appendChild(inp);
		row.appendChild(saveBtn);
		row.appendChild(cancelBtn);
		item.innerHTML = '';
		item.appendChild(row);
		inp.focus();
		saveBtn.addEventListener('click', function() { saveMem(m.id, inp.value); });
		cancelBtn.addEventListener('click', loadMemories);
		inp.addEventListener('keydown', function(e) {
			if (e.key === 'Enter') saveMem(m.id, inp.value);
			if (e.key === 'Escape') loadMemories();
		});
	}

	function saveMem(id, text) {
		text = (text || '').trim();
		if (!text || !_nousUid) { loadMemories(); return; }
		fetch(MEM_URL + '/memories/' + id, {
			method: 'PUT',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ user_id: _nousUid, text: text })
		}).then(function() { loadMemories(); }).catch(loadMemories);
	}

	function deleteMem(id) {
		if (!_nousUid) return;
		fetch(MEM_URL + '/memories/' + id + '?user_id=' + encodeURIComponent(_nousUid), {
			method: 'DELETE'
		}).then(function() { loadMemories(); }).catch(loadMemories);
	}

	function addMemory() {
		var inp  = memPanelEl.querySelector('#nous-mem-inp');
		var text = (inp.value || '').trim();
		if (!text || !_nousUid) return;
		fetch(MEM_URL + '/memories', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ user_id: _nousUid, text: text, persona: _activePer })
		}).then(function() {
			inp.value = '';
			loadMemories();
		}).catch(function() {});
	}

	function _esc(s) {
		return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
	}

	/* ====================== Loja de Modelos (v2.2) ======================
	 * Painel com o catalogo curado servido pelo monitor (8990/catalog):
	 * recomendados para ESTA maquina primeiro, download em 1 clique com
	 * progresso real. O estado do download vive no monitor — pode fechar
	 * e reabrir o painel sem perder nada.
	 * ==================================================================== */
	var storeEl = null, storeOpen = false, storeTimer = null;
	var CAT_LABEL = {
		leve: 'Leve e rapido', conversa: 'Conversa e escrita',
		raciocinio: 'Raciocinio', programacao: 'Programacao'
	};

	function injectStoreStyle() {
		if (document.getElementById('nous-store-style')) return;
		var css =
			'#nous-store-ov{position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.55);' +
			'display:flex;align-items:center;justify-content:center;backdrop-filter:blur(3px)}' +
			'#nous-store-ov.nous-hidden{display:none}' +
			'#nous-store{width:460px;max-width:92vw;max-height:82vh;display:flex;flex-direction:column;' +
			'font-family:Inter,system-ui,sans-serif;font-size:13px;color:#eee;' +
			'background:rgba(18,18,22,.97);border:1px solid rgba(200,150,46,.4);' +
			'border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-store-head{display:flex;align-items:center;gap:8px;padding:14px 16px 10px}' +
			'#nous-store-head span{flex:1;font-weight:700;font-size:15px;letter-spacing:.04em;color:#e7c069}' +
			'#nous-store-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px;line-height:1}' +
			'#nous-store-close:hover{color:#eee}' +
			'#nous-store-hw{padding:0 16px 10px;font-size:12px;opacity:.65;' +
			'border-bottom:1px solid rgba(255,255,255,.07)}' +
			'#nous-store-list{flex:1;overflow-y:auto;padding:10px 12px 14px}' +
			'#nous-store-list::-webkit-scrollbar{width:6px}' +
			'#nous-store-list::-webkit-scrollbar-thumb{background:rgba(200,150,46,.3);border-radius:4px}' +
			'.nous-store-card{border:1px solid rgba(255,255,255,.09);border-radius:12px;' +
			'padding:10px 12px;margin-bottom:8px;background:rgba(255,255,255,.03)}' +
			'.nous-store-card.nous-rec{border-color:rgba(200,150,46,.55);background:rgba(200,150,46,.07)}' +
			'.nous-store-top{display:flex;align-items:center;gap:8px;flex-wrap:wrap}' +
			'.nous-store-name{font-weight:700;font-size:13px}' +
			'.nous-store-badge{font-size:10px;font-weight:600;padding:2px 7px;border-radius:99px;white-space:nowrap}' +
			'.nous-b-rec{background:rgba(200,150,46,.22);color:#e7c069;border:1px solid rgba(200,150,46,.5)}' +
			'.nous-b-ok{background:rgba(255,255,255,.08);color:#bbb;border:1px solid rgba(255,255,255,.15)}' +
			'.nous-b-heavy{background:rgba(220,60,60,.12);color:#e08080;border:1px solid rgba(220,60,60,.35)}' +
			'.nous-b-inst{background:rgba(58,208,122,.14);color:#5fd693;border:1px solid rgba(58,208,122,.4)}' +
			'.nous-b-vis{background:rgba(110,150,230,.14);color:#9db8ee;border:1px solid rgba(110,150,230,.35)}' +
			'.nous-store-desc{margin:5px 0 7px;font-size:12px;line-height:1.45;opacity:.8}' +
			'.nous-store-speed{margin:-3px 0 7px;font-size:11px;opacity:.65}' +
			'.nous-store-speed b{color:#e7c069;font-weight:600}' +
			'.nous-store-row{display:flex;align-items:center;gap:10px}' +
			'.nous-store-size{font-size:11px;opacity:.55;flex:1}' +
			'.nous-store-btn{background:rgba(200,150,46,.18);border:1px solid rgba(200,150,46,.45);' +
			'color:#e7c069;border-radius:8px;padding:5px 14px;font-size:12px;font-weight:600;cursor:pointer;' +
			'transition:background .15s}' +
			'.nous-store-btn:hover{background:rgba(200,150,46,.32)}' +
			'.nous-store-prog{flex:1;display:flex;flex-direction:column;gap:4px}' +
			'.nous-store-ptxt{font-size:11px;opacity:.75;font-variant-numeric:tabular-nums}' +
			'.nous-store-err{font-size:11px;color:#e08080;flex:1}' +
			'.nous-store-empty{opacity:.6;text-align:center;padding:22px 10px;font-size:12px;line-height:1.5}';
		var st = document.createElement('style');
		st.id = 'nous-store-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	function buildStore() {
		if (storeEl && document.body && document.body.contains(storeEl)) return;
		if (!document.body) return;
		injectStoreStyle();
		storeEl = document.createElement('div');
		storeEl.id = 'nous-store-ov';
		storeEl.classList.add('nous-hidden');
		storeEl.innerHTML =
			'<div id="nous-store">' +
			'<div id="nous-store-head"><span>Modelos de IA</span>' +
			'<button id="nous-store-close" type="button" aria-label="Fechar">&#x2715;</button></div>' +
			'<div id="nous-store-hw">Analisando sua maquina...</div>' +
			'<div id="nous-store-list"><div class="nous-store-empty">Carregando catalogo...</div></div>' +
			'</div>';
		document.body.appendChild(storeEl);
		storeEl.addEventListener('click', function (e) {
			if (e.target === storeEl) closeStore();
		});
		storeEl.querySelector('#nous-store-close').addEventListener('click', closeStore);
	}

	function openStore() {
		buildStore();
		if (!storeEl) return;
		storeOpen = true;
		storeEl.classList.remove('nous-hidden');
		storeRefresh();
	}

	function closeStore() {
		storeOpen = false;
		if (storeEl) storeEl.classList.add('nous-hidden');
		if (storeTimer) { clearTimeout(storeTimer); storeTimer = null; }
	}

	function storeRefresh() {
		if (!storeOpen || !storeEl) return;
		fetch(MON_URL + '/catalog', { cache: 'no-store' })
			.then(function (r) { return r.json(); })
			.then(renderStore)
			.catch(function () {
				var list = storeEl.querySelector('#nous-store-list');
				if (list) list.innerHTML =
					'<div class="nous-store-empty">A loja esta indisponivel.<br>' +
					'Abra o Nous pelo atalho da area de trabalho e tente de novo.</div>';
			});
	}

	function _hwLine(hw) {
		if (!hw) return '';
		if (hw.tier === 'cpu') {
			return 'Sua maquina: sem GPU dedicada — modo CPU' +
				(hw.ram_gb ? ' · ' + hw.ram_gb + ' GB de RAM' : '');
		}
		return 'Sua maquina: ' + _esc(hw.gpu_name || 'GPU') + ' · ' + hw.vram_gb + ' GB de VRAM';
	}

	/* Estimativa do monitor (tokens/s) em palavras por segundo: ~0,7 palavra
	 * por token em portugues. Abaixo de ~3 palavras/s a leitura fica arrastada. */
	function _speedTxt(m) {
		var s = m.speed;
		if (!s || !s.tps) return '';
		var wps = Math.max(1, Math.round(s.tps * 0.7));
		var nivel = wps >= 15 ? 'rapido' : wps >= 6 ? 'bom' : wps >= 3 ? 'devagar' : 'muito lento';
		var onde = s.onde === 'misto' ? ' · parte fica na RAM' : s.onde === 'cpu' ? ' · roda no processador' : '';
		return '<div class="nous-store-speed">Velocidade estimada: <b>' + nivel + '</b> (~' + wps +
			' palavras/s)' + onde + '</div>';
	}

	function renderStore(data) {
		if (!storeOpen || !storeEl) return;
		var hwEl = storeEl.querySelector('#nous-store-hw');
		var list = storeEl.querySelector('#nous-store-list');
		if (hwEl) hwEl.textContent = _hwLine(data.hardware);
		if (!data.ollama_online) {
			list.innerHTML =
				'<div class="nous-store-empty">O motor de IA (Ollama) nao esta no ar.<br>' +
				'Abra o Nous pelo atalho da area de trabalho — ele inicia tudo sozinho.</div>';
			/* tenta de novo sozinho: o Ollama costuma subir alguns segundos depois */
			if (storeTimer) clearTimeout(storeTimer);
			storeTimer = setTimeout(storeRefresh, 3000);
			return;
		}
		var models = data.models || [];
		if (!models.length) {
			list.innerHTML = '<div class="nous-store-empty">Catalogo vazio.</div>';
			return;
		}
		list.innerHTML = '';
		var anyPulling = false;
		models.forEach(function (m) {
			var card = document.createElement('div');
			card.className = 'nous-store-card' + (m.fit === 'recomendado' ? ' nous-rec' : '');
			var badges = '';
			if (m.installed) badges += '<span class="nous-store-badge nous-b-inst">Instalado</span>';
			else if (m.fit === 'recomendado') badges += '<span class="nous-store-badge nous-b-rec">Recomendado para sua maquina</span>';
			else if (m.fit === 'ok') badges += '<span class="nous-store-badge nous-b-ok">Roda na sua maquina</span>';
			else badges += '<span class="nous-store-badge nous-b-heavy">Pesado para sua maquina</span>';
			if (m.vision) badges += '<span class="nous-store-badge nous-b-vis">Entende imagens</span>';
			var pull = m.pull;
			var rowHtml;
			if (pull && pull.status === 'baixando') {
				anyPulling = true;
				var pct = Math.round((pull.pct || 0) * 100);
				rowHtml =
					'<div class="nous-store-prog">' +
					'<div class="nous-mon-track"><div class="nous-mon-fill" style="width:' + pct + '%"></div></div>' +
					'<span class="nous-store-ptxt">Baixando... ' + pct + '%' +
					(pull.total_gb ? ' · ' + pull.completed_gb + ' / ' + pull.total_gb + ' GB' : '') +
					'</span></div>';
			} else if (pull && pull.status === 'erro') {
				rowHtml =
					'<span class="nous-store-err">' + _esc(pull.error || 'O download falhou.') + '</span>' +
					'<button class="nous-store-btn" type="button" data-pull="' + _esc(m.tag) + '">Tentar de novo</button>';
			} else if (m.installed) {
				rowHtml = '<span class="nous-store-size">~' + m.download_gb +
					' GB · pronto para usar — selecione no topo da tela</span>';
			} else {
				rowHtml = '<span class="nous-store-size">~' + m.download_gb + ' GB de download · ' +
					(CAT_LABEL[m.category] || m.category) + '</span>' +
					'<button class="nous-store-btn" type="button" data-pull="' + _esc(m.tag) + '">Baixar</button>';
			}
			card.innerHTML =
				'<div class="nous-store-top"><span class="nous-store-name">' + _esc(m.name) + '</span>' +
				badges + '</div>' +
				'<div class="nous-store-desc">' + _esc(m.desc) + '</div>' +
				_speedTxt(m) +
				'<div class="nous-store-row">' + rowHtml + '</div>';
			list.appendChild(card);
		});
		list.querySelectorAll('[data-pull]').forEach(function (b) {
			b.addEventListener('click', function () { startPull(b.getAttribute('data-pull')); });
		});
		if (storeTimer) clearTimeout(storeTimer);
		if (anyPulling) storeTimer = setTimeout(storeRefresh, 2000);
	}

	/* Resolve true se o download comecou (ou ja estava em andamento). */
	function startPull(tag) {
		if (!tag) return Promise.resolve(false);
		return fetch(MON_URL + '/pull', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ model: tag })
		})
			.then(function (r) { return r.json().catch(function () { return {}; }); })
			.then(function (d) { return !!(d.started || d.reason === 'em andamento'); })
			.catch(function () { return false; })
			.then(function (ok) { setTimeout(storeRefresh, 400); return ok; });
	}

	/* ====================== Painel de Voz local (v2.3) ======================
	 * Botao "Ativar voz em PT-BR" no card Recursos abre este painel.
	 * Se a voz ja esta instalada: mostra status e instrucao de uso.
	 * Se nao esta: botao "Ativar" dispara o download via /voice/install.
	 * ======================================================================= */
	var voiceEl = null, voiceOpen = false, voiceTimer = null;

	function buildVoice() {
		if (voiceEl && document.body && document.body.contains(voiceEl)) return;
		if (!document.body) return;
		voiceEl = document.createElement('div');
		voiceEl.id = 'nous-voice-ov';
		voiceEl.classList.add('nous-hidden');
		voiceEl.innerHTML =
			'<div id="nous-voice-box">' +
			'<div id="nous-voice-head"><span>🎙 Conversa por Voz</span>' +
			'<button id="nous-voice-close" type="button" aria-label="Fechar">&#x2715;</button></div>' +
			'<div id="nous-voice-body">' +
			'<div id="nous-voice-desc">Fale com o Nous e ouça a resposta — tudo em português, 100% local, sem internet.<br><br>' +
			'O download inclui o motor de voz Piper (~30 MB) e o modelo de voz pt_BR (~60 MB). ' +
			'O modelo Whisper para entender o que você fala (~150 MB) é baixado automaticamente na primeira vez que usar.</div>' +
			'<div id="nous-voice-status"></div>' +
			'<button id="nous-voice-btn" type="button">Ativar conversa por voz</button>' +
			'</div></div>';
		document.body.appendChild(voiceEl);
		voiceEl.addEventListener('click', function (e) {
			if (e.target === voiceEl) closeVoice();
		});
		voiceEl.querySelector('#nous-voice-close').addEventListener('click', closeVoice);
		voiceEl.querySelector('#nous-voice-btn').addEventListener('click', doVoiceInstall);
	}

	function openVoice() {
		buildVoice();
		if (!voiceEl) return;
		voiceOpen = true;
		voiceEl.classList.remove('nous-hidden');
		voiceRefresh();
	}

	function closeVoice() {
		voiceOpen = false;
		if (voiceEl) voiceEl.classList.add('nous-hidden');
		if (voiceTimer) { clearTimeout(voiceTimer); voiceTimer = null; }
	}

	function voiceRefresh() {
		if (!voiceOpen || !voiceEl) return;
		fetch(MON_URL + '/voice/status', { cache: 'no-store' })
			.then(function (r) { return r.json(); })
			.then(renderVoice)
			.catch(function () {
				var st = voiceEl.querySelector('#nous-voice-status');
				if (st) st.textContent = 'Monitor offline — abra o Nous pelo atalho.';
			});
	}

	/* Rede de seguranca: o backend ja' manda mensagens amigaveis, mas se algum
	 * erro tecnico (stack trace do PowerShell, etc.) vazar, nunca o mostramos
	 * cru ao usuario — trocamos por uma frase generica e acionavel. */
	function _voiceFriendlyErr(msg) {
		var s = String(msg || '').trim();
		if (!s) return 'Nao foi possivel ativar a voz agora. Tente de novo.';
		var techy = /ParserError|CategoryInfo|FullyQualified|MissingEnd|Exception|at line|System\.|\+ ~|\.ps1:|Token|Unexpected/i;
		if (s.length > 160 || techy.test(s)) {
			return 'Nao foi possivel ativar a voz agora. Tente de novo; se persistir, reinicie o Nous.';
		}
		return s;
	}

	function renderVoice(data) {
		if (!voiceOpen || !voiceEl) return;
		var stEl  = voiceEl.querySelector('#nous-voice-status');
		var btn   = voiceEl.querySelector('#nous-voice-btn');
		var inst  = data.install || {};

		// Atualizar o botao do card Recursos
		var cardBtn = document.getElementById('nous-voice-open');

		if (data.ativo) {
			if (stEl) stEl.innerHTML =
				'<span style="color:#5fd693;font-weight:600">✓ Voz ativada!</span><br><br>' +
				'<span style="opacity:.8">Recarregue a página e toque no ícone de <b>telefone</b> no chat para conversar por voz.</span>';
			if (btn) { btn.textContent = 'Voz já ativada'; btn.disabled = true; }
			if (cardBtn) { cardBtn.textContent = '🎙 Voz ativada'; cardBtn.style.color = '#5fd693'; }
			return;
		}

		if (cardBtn) { cardBtn.textContent = '🎙 Ativar voz em PT-BR'; cardBtn.style.color = ''; }

		if (inst.status === 'instalando') {
			var pct = Math.round((inst.pct || 0) * 100);
			if (stEl) stEl.innerHTML =
				'<div class="nous-voice-prog">' +
				'<div class="nous-mon-track"><div class="nous-mon-fill" style="width:' + pct + '%"></div></div>' +
				'<span class="nous-voice-ptxt">' + _esc(inst.step || 'Baixando...') + ' ' + pct + '%</span></div>';
			if (btn) { btn.textContent = 'Instalando...'; btn.disabled = true; }
			voiceTimer = setTimeout(voiceRefresh, 1500);
		} else if (inst.status === 'erro') {
			if (stEl) stEl.innerHTML =
				'<span style="color:#e08080">' + _esc(_voiceFriendlyErr(inst.error)) + '</span>';
			if (btn) { btn.textContent = 'Tentar de novo'; btn.disabled = false; }
		} else {
			if (stEl) stEl.textContent = '';
			if (btn) { btn.textContent = 'Ativar conversa por voz'; btn.disabled = false; }
		}
	}

	function doVoiceInstall() {
		if (!voiceEl) return;
		var btn = voiceEl.querySelector('#nous-voice-btn');
		if (btn) { btn.disabled = true; btn.textContent = 'Iniciando...'; }
		fetch(MON_URL + '/voice/install', { method: 'POST' })
			.catch(function () {})
			.then(function () { setTimeout(voiceRefresh, 800); });
	}

	/* ========================== Painel Email ================================
	 * O painel (contas, caixa, rascunhos, newsletters, contatos) mora em
	 * branding/modules/email.js desde a v2.8; o botao do card Recursos o abre.
	 * ======================================================================= */
	function openEmail() {
		if (window.NousEmail) window.NousEmail.open();
	}

	/* ====================== Assistente de primeiro uso ======================
	 * Se o usuario esta logado e o Ollama nao tem NENHUM modelo de chat,
	 * mostra uma boas-vindas com o modelo recomendado e um botao unico.
	 * Some sozinho (para sempre) depois do primeiro download.
	 * ======================================================================= */
	var wizEl = null, wizShown = false, wizTimer = null;

	function wizCheck() {
		if (wizShown || storeOpen || !onHome() || !document.body) return;
		try { if (sessionStorage.getItem('nous-wizard-skip') === '1') return; } catch (e) {}
		var token = '';
		try { token = localStorage.getItem('token') || ''; } catch (e) {}
		if (!token) return;
		fetch(MON_URL + '/installed', { cache: 'no-store' })
			.then(function (r) { return r.json(); })
			.then(function (data) {
				if (data.online && !(data.chat || []).length && !wizShown && !storeOpen) showWizard();
			})
			.catch(function () {});
	}

	function _wizSkip() {
		try { sessionStorage.setItem('nous-wizard-skip', '1'); } catch (e) {}
		if (wizEl) wizEl.remove();
		wizEl = null;
		if (wizTimer) { clearTimeout(wizTimer); wizTimer = null; }
	}

	function showWizard() {
		wizShown = true;
		fetch(MON_URL + '/catalog', { cache: 'no-store' })
			.then(function (r) { return r.json(); })
			.then(function (data) {
				var models = (data && data.models) || [];
				var rec = null;
				models.forEach(function (m) {
					if (!rec && m.fit === 'recomendado' && !m.installed) rec = m;
				});
				if (!rec) rec = models.length ? models[0] : null;
				if (rec) renderWizard(rec);
				else wizShown = false; /* loja offline: tenta de novo no proximo ciclo */
			})
			.catch(function () { wizShown = false; });
	}

	function renderWizard(rec) {
		injectStoreStyle();
		if (wizEl) wizEl.remove();
		wizEl = document.createElement('div');
		wizEl.id = 'nous-wiz-ov';
		wizEl.setAttribute('style',
			'position:fixed;inset:0;z-index:10010;background:rgba(8,8,10,.78);' +
			'display:flex;align-items:center;justify-content:center;backdrop-filter:blur(5px);' +
			'font-family:Inter,system-ui,sans-serif;color:#eee');
		wizEl.innerHTML =
			'<div style="width:430px;max-width:92vw;background:rgba(18,18,22,.98);' +
			'border:1px solid rgba(200,150,46,.45);border-radius:18px;padding:28px 26px;' +
			'box-shadow:0 20px 60px rgba(0,0,0,.6);text-align:center">' +
			'<img src="/static/favicon.png" alt="" style="width:58px;height:58px;margin-bottom:10px">' +
			'<div style="font-size:19px;font-weight:700;color:#e7c069;letter-spacing:.04em;margin-bottom:6px">' +
			'Bem-vindo ao Nous</div>' +
			'<div style="font-size:13px;opacity:.8;line-height:1.5;margin-bottom:18px">' +
			'Sua IA particular esta quase pronta. Falta um passo:<br>instalar o modelo de inteligencia — ' +
			'gratuito, direto na sua maquina.</div>' +
			'<div class="nous-store-card nous-rec" style="text-align:left;margin-bottom:16px">' +
			'<div class="nous-store-top"><span class="nous-store-name">' + _esc(rec.name) + '</span>' +
			'<span class="nous-store-badge nous-b-rec">Recomendado para sua maquina</span>' +
			(rec.vision ? '<span class="nous-store-badge nous-b-vis">Entende imagens</span>' : '') +
			'</div>' +
			'<div class="nous-store-desc">' + _esc(rec.desc) + ' (~' + rec.download_gb + ' GB de download)</div>' +
			'<div id="nous-wiz-zone" class="nous-store-row"></div>' +
			'</div>' +
			'<div style="display:flex;gap:14px;justify-content:center;font-size:12px">' +
			'<a id="nous-wiz-more" href="javascript:void(0)" style="color:#c8962e;text-decoration:none">ver outros modelos</a>' +
			'<a id="nous-wiz-skip" href="javascript:void(0)" style="color:#777;text-decoration:none">agora nao</a>' +
			'</div></div>';
		document.body.appendChild(wizEl);
		wizEl.querySelector('#nous-wiz-more').addEventListener('click', function () {
			_wizSkip(); openStore();
		});
		wizEl.querySelector('#nous-wiz-skip').addEventListener('click', _wizSkip);
		_wizIdle(rec);
	}

	function _wizIdle(rec) {
		var zone = wizEl && wizEl.querySelector('#nous-wiz-zone');
		if (!zone) return;
		zone.innerHTML =
			'<button class="nous-store-btn" type="button" style="width:100%;padding:9px;font-size:13px">' +
			'Baixar e comecar</button>';
		zone.querySelector('button').addEventListener('click', function () { _wizStart(rec); });
	}

	function _wizStart(rec) {
		_wizProgress(rec);
		startPull(rec.tag).then(function (ok) {
			if (!ok) _wizError(rec, 'Não consegui iniciar o download. Confira a internet e tente de novo.');
		});
	}

	function _wizProgress(rec) {
		var zone = wizEl && wizEl.querySelector('#nous-wiz-zone');
		if (!zone) return;
		zone.innerHTML =
			'<div class="nous-store-prog">' +
			'<div class="nous-mon-track"><div class="nous-mon-fill" id="nous-wiz-fill" style="width:0%"></div></div>' +
			'<span class="nous-store-ptxt" id="nous-wiz-ptxt">Iniciando o download... ' +
			'Pode deixar esta janela aberta — avisamos quando terminar.</span></div>';
		var none = 0;
		function poll() {
			fetch(MON_URL + '/pull/status?model=' + encodeURIComponent(rec.tag), { cache: 'no-store' })
				.then(function (r) { return r.json(); })
				.then(function (st) {
					if (!wizEl) return;
					if (st.status === 'pronto') { _wizDone(rec); return; }
					if (st.status === 'erro') { _wizError(rec, st.error); return; }
					/* "nenhum" = o monitor nao conhece este download (o pedido falhou
					   ou o monitor reiniciou). Antes: "Baixando... 0%" para sempre. */
					if (st.status === 'nenhum' && ++none >= 5) {
						_wizError(rec, 'O download parou. Tente de novo.');
						return;
					}
					var pct = Math.round((st.pct || 0) * 100);
					var fill = wizEl.querySelector('#nous-wiz-fill');
					var txt = wizEl.querySelector('#nous-wiz-ptxt');
					if (fill) fill.style.width = pct + '%';
					if (txt) txt.textContent = 'Baixando... ' + pct + '%' +
						(st.total_gb ? ' · ' + st.completed_gb + ' / ' + st.total_gb + ' GB' : '') +
						' — pode deixar esta janela aberta.';
					wizTimer = setTimeout(poll, 2000);
				})
				.catch(function () { wizTimer = setTimeout(poll, 4000); });
		}
		poll();
	}

	function _wizError(rec, msg) {
		var zone = wizEl && wizEl.querySelector('#nous-wiz-zone');
		if (!zone) return;
		zone.innerHTML =
			'<span class="nous-store-err">' + _esc(msg || 'O download falhou.') + '</span>' +
			'<button class="nous-store-btn" type="button">Tentar de novo</button>';
		zone.querySelector('button').addEventListener('click', function () { _wizStart(rec); });
	}

	function _wizDone(rec) {
		var zone = wizEl && wizEl.querySelector('#nous-wiz-zone');
		if (!zone) return;
		zone.innerHTML =
			'<div style="flex:1;text-align:center">' +
			'<div style="color:#5fd693;font-weight:600;font-size:13px;margin-bottom:8px">' +
			'Tudo pronto! Sua IA foi instalada.</div>' +
			'<button class="nous-store-btn" type="button" style="width:100%;padding:9px;font-size:13px">' +
			'Comecar a conversar</button></div>';
		zone.querySelector('button').addEventListener('click', function () {
			/* Abre o chat JA com o modelo novo: com reload puro o Open WebUI podia
			   escolher o primeiro da lista - as vezes o de embeddings, que nao conversa. */
			location.href = '/?model=' + encodeURIComponent(rec.tag);
		});
	}

	/* ====================== Dica de cadastro na tela de login ====================== *
	 * O Open WebUI fecha o cadastro depois que a primeira conta (admin) e' criada, e  *
	 * novas contas nascem "pendentes". O antigo link "Criar conta" levava a          *
	 * /auth?mode=signup, parametro que o Open WebUI ignora: voltava ao login.        *
	 * Agora: so' na tela de LOGIN (sem campo de nome), explica o caminho real.       *
	 * ============================================================================== */
	function onAuth() {
		return location.pathname === '/auth';
	}

	function ensureSignupLink() {
		var old = document.getElementById('nous-signup-link');
		var form = onAuth() ? document.querySelector('form') : null;
		/* Cadastro aberto (1a conta = administrador) tem campo de nome: sem dica */
		var isLogin = form && !form.querySelector('input[autocomplete="name"]') &&
			form.querySelector('input[type="password"]');
		if (!isLogin) { if (old) old.remove(); return; }
		if (old) return;
		var hint = document.createElement('p');
		hint.id = 'nous-signup-link';
		hint.style.cssText =
			'text-align:center;margin-top:14px;font-size:13px;line-height:1.5;' +
			'font-family:Inter,system-ui,sans-serif;color:#888;';
		hint.innerHTML =
			'Novo por aqui? Peça a quem administra o Nous para criar sua conta em ' +
			'<b style="color:#c8962e;font-weight:600">Painel Admin › Usuários</b>.';
		form.parentNode.insertBefore(hint, form.nextSibling);
	}

	/* ====================== Capability gate (badge VRAM nos modelos) ==================
	 * Mostra um badge colorido ao lado de cada modelo no dropdown do chat:
	 *   🟢 verde  — cabe confortavelmente na VRAM da placa (< 85%)
	 *   🟡 amarelo — cabe mas apertado (85-100% da VRAM)
	 *   🔴 vermelho — nao cabe (maior que a VRAM da placa)
	 *   ⚪ cinza   — sem informacao de tamanho
	 * Dados: /installed (tamanho) + /stats (VRAM total), ambos do monitor.
	 * ================================================================================= */
	var _capModels  = {};   /* { modelName: sizeBytes } */
	/* VRAM TOTAL da placa. Comparar com a livre deixava vermelho justamente o
	   modelo que ja estava carregado (ele mesmo ocupa a VRAM). -1 = sem dado. */
	var _capVramTotal = -1;
	var _capLastFetch = 0;

	function _capRefresh() {
		var now = Date.now();
		if (now - _capLastFetch < 10000) return; /* atualiza a cada 10s */
		_capLastFetch = now;
		fetch(MON_URL + '/stats', { cache: 'no-store' })
			.then(function(r) { return r.json(); })
			.then(function(s) {
				var g = s.gpu || {};
				if (g.ded_total) _capVramTotal = g.ded_total;
			}).catch(function() {});
		/* Tamanhos dos modelos via monitor (que consulta o Ollama) */
		fetch(MON_URL + '/installed', { cache: 'no-store' })
			.then(function(r) { return r.json(); })
			.then(function(data) {
				var models = data.models || [];
				models.forEach(function(m) {
					if (!m.name || !m.size) return;
					_capModels[m.name] = m.size;
					/* Ollama retorna nome com tag; normaliza sem tag para match parcial */
					var base = m.name.split(':')[0];
					if (base) _capModels[base] = m.size;
				});
			}).catch(function() {});
	}

	function _capBadge(modelName) {
		if (_capVramTotal < 0) return '';
		/* Tenta match exato, depois base (sem tag), depois prefixo */
		var sz = _capModels[modelName];
		if (!sz) {
			var base = (modelName || '').split(':')[0];
			sz = _capModels[base];
		}
		if (!sz) return '';
		var ratio = sz / (_capVramTotal || 1);
		var dot, tip;
		if (ratio <= 0.85)      { dot = '#3ad07a'; tip = 'Cabe bem na VRAM'; }
		else if (ratio <= 1.0)  { dot = '#f5a623'; tip = 'Cabe (VRAM apertada)'; }
		else                    { dot = '#e05252'; tip = 'Pode nao caber na VRAM'; }
		return '<span title="' + tip + '" style="display:inline-block;width:8px;height:8px;' +
			'border-radius:50%;background:' + dot + ';margin-left:6px;flex-shrink:0;' +
			'vertical-align:middle;box-shadow:0 0 4px ' + dot + '55"></span>';
	}

	function _capApply() {
		/* Funciona para o dropdown de modelos do Open WebUI (lista de <button> com texto) */
		var items = document.querySelectorAll('[data-nous-cap]');
		items.forEach(function(el) { el.removeAttribute('data-nous-cap'); });

		/* O Open WebUI renderiza os modelos em botoes ou opcoes dentro de um dropdown */
		var candidates = document.querySelectorAll(
			'[aria-label*="Model"], [aria-label*="model"], ' +
			'.model-item, [data-model-id], ' +
			'button[id*="model"], li[id*="model"]'
		);
		/* Fallback: qualquer elemento que tenha um atributo data-value ou similar */
		if (!candidates.length) return;

		candidates.forEach(function(el) {
			if (el.querySelector('.nous-cap-dot')) return; /* ja tem badge */
			var name = el.getAttribute('data-model-id') ||
				el.getAttribute('data-value') ||
				el.getAttribute('value') ||
				(el.textContent || '').trim().split('\n')[0].trim();
			if (!name) return;
			var badge = _capBadge(name);
			if (!badge) return;
			el.setAttribute('data-nous-cap', '1');
			/* Injeta badge como ultimo elemento inline */
			var span = document.createElement('span');
			span.className = 'nous-cap-dot';
			span.innerHTML = badge;
			el.appendChild(span);
		});
	}

	/* Inicia refresh de dados de capacidade periodicamente */
	function startCapGate() {
		_capRefresh();
		setInterval(_capRefresh, 10000);
		setInterval(_capApply, 1000);
	}

	/* ====================== "O que ha de novo" do Open WebUI ======================
	 * Logo apos criar a conta, o Open WebUI abria as notas de versao EM INGLES, com
	 * links do GitHub - a primeira coisa que o leigo via. O modal aparece quando a
	 * conta e' admin e settings.version != versao do servidor. Aqui: fechamos o
	 * modal (o fechar grava a versao) e desligamos showChangelog na conta, para
	 * nao voltar nem depois de um upgrade.
	 * =============================================================================== */
	var CHANGELOG_H3 = /^v\d+\.\d+\.\d+ - \d{4}-\d{2}-\d{2}$/;
	var _clPrefDone = false;

	function suppressChangelog() {
		var hs = document.querySelectorAll('h3');
		for (var i = 0; i < hs.length; i++) {
			if (!CHANGELOG_H3.test((hs[i].textContent || '').trim())) continue;
			/* sobe ate o cartao do modal: o X e' o primeiro botao do cabecalho */
			var box = hs[i].parentElement;
			while (box && box !== document.body && !box.querySelector('h2 + button, h2 ~ button')) box = box.parentElement;
			var close = box && box !== document.body && box.querySelector('h2 ~ button');
			if (close) { close.click(); break; }
		}
		if (_clPrefDone) return;
		var token = '';
		try { token = localStorage.getItem('token') || ''; } catch (e) {}
		if (!token) return;
		_clPrefDone = true;
		var H = { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' };
		/* depois do fechar do modal salvar a versao, para nao disputar a escrita */
		setTimeout(function () {
			fetch('/api/v1/users/user/settings', { headers: H })
				.then(function (r) { return r.ok ? r.json() : null; })
				.then(function (cur) {
					var ui = (cur && cur.ui) || {};
					if (ui.showChangelog === false) return;
					ui.showChangelog = false;
					var body = cur || {};
					body.ui = ui;
					return fetch('/api/v1/users/user/settings/update',
						{ method: 'POST', headers: H, body: JSON.stringify(body) });
				})
				.catch(function () {});
		}, 3000);
	}

	function tick() {
		ensureToggle();
		if (btn) btn.style.display = onHome() ? 'flex' : 'none';
		paintToggle();
		buildMonitor();
		ensureTopWordmark();
		ensureMemBtn();
		ensureSignupLink();
		suppressChangelog();
		/* Tela de login/cadastro: nada de VRAM, modelos ou memoria antes de entrar */
		var auth = onAuth();
		if (monEl) monEl.style.display = auth ? 'none' : '';
		if (memBtnEl) memBtnEl.style.display = auth ? 'none' : '';
	}

	function start() {
		injectMonitorStyle();
		injectMemStyle();
		tick();
		setInterval(tick, 500);
		refreshMonitor();
		setInterval(refreshMonitor, 3000);
		startCapGate();
		/* primeiro uso: oferece o download do modelo se nao ha nenhum */
		setTimeout(wizCheck, 3000);
		setInterval(wizCheck, 12000);
	}

	/* Utilitarios para os modulos em branding/modules/*.js (agenda, skills...),
	 * que o apply_branding.py concatena depois deste arquivo no loader.js. */
	window.NousUI = { loadUserId: loadUserId, esc: _esc, onAuth: onAuth };

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', start);
	} else {
		start();
	}
})();
