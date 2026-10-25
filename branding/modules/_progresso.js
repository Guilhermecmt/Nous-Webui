/* =====================================================================
   Nous - Progresso dos "Primeiros passos" (v2.11). Guarda, por pessoa, o que ja'
   foi mostrado (dicas dos paineis, licoes, cartoes da primeira conversa) e se
   as dicas estao desligadas ("Pular").
   Onde fica: no SERVIDOR, nas configuracoes da propria conta do Open WebUI
   (campo "nousTour", ao lado de "ui"; o Open WebUI preserva campos que nao
   conhece). Assim vale no celular e em outro navegador, sem login e com login.
   O localStorage e' so' um espelho (abre rapido e funciona sem servidor).
   Se servidor e espelho divergem, vale o mais novo ("t").
   Quem vem da v2.8-v2.10 (dicas ja' vistas no localStorage antigo, "nous-tour-*")
   tem isso migrado para o servidor na primeira visita.
   Carrega antes dos outros modulos (o "_" ordena primeiro): window.NousProgresso.
   ===================================================================== */
(function () {
	'use strict';

	var estado = vazio(), carregado = false, ouvintes = [], timer = null, falhas = 0, chave = 'nous-pp';

	function vazio() {
		/* vistos: {home:1, agenda:1, licoes:1, cartoes:1, ...}; pular: "Pular dicas" ligado;
		   licao: indice da ultima licao aberta; veterano: true = ja' usava o Nous (nunca recebe o tour sozinho) */
		return { v: 1, t: 0, pular: false, vistos: {}, licao: 0, veterano: null };
	}
	function token() { try { return localStorage.getItem('token') || ''; } catch (e) { return ''; } }
	function idDoToken(t) {
		try { return JSON.parse(atob(t.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).id || 'x'; } catch (e) { return 'x'; }
	}
	function limpo(o) {
		var s = vazio();
		if (!o || typeof o !== 'object') return s;
		s.t = Number(o.t) || 0;
		s.pular = o.pular === true;
		s.licao = Math.max(0, parseInt(o.licao, 10) || 0);
		s.veterano = o.veterano === true ? true : (o.veterano === false ? false : null);
		var v = o.vistos && typeof o.vistos === 'object' ? o.vistos : {};
		Object.keys(v).forEach(function (k) { if (v[k]) s.vistos[k] = 1; });
		return s;
	}
	function lerEspelho() {
		try { var r = localStorage.getItem(chave); return r ? limpo(JSON.parse(r)) : null; } catch (e) { return null; }
	}
	function gravarEspelho() { try { localStorage.setItem(chave, JSON.stringify(estado)); } catch (e) {} }
	/* dicas vistas nas versoes 2.8-2.10 (uma chave por dica + "nous-tour-off") */
	function lerAntigo() {
		var s = vazio(), achou = false;
		try {
			for (var i = 0; i < localStorage.length; i++) {
				var k = localStorage.key(i);
				if (!/^nous-tour-/.test(k)) continue;
				if (localStorage.getItem(k) !== '1') continue;
				achou = true;
				if (k === 'nous-tour-off') s.pular = true;
				else s.vistos[k.slice(10)] = 1;
			}
		} catch (e) {}
		if (achou) {
			/* quem ja' viu dicas ja' usava o Nous: nunca recebe o passeio, as licoes e os cartoes de iniciante */
			s.t = Date.now(); s.veterano = true;
			['home', 'licoes', 'cartoes'].forEach(function (k) { s.vistos[k] = 1; });
		}
		return achou ? s : null;
	}
	function H() { return { 'Authorization': 'Bearer ' + token(), 'Content-Type': 'application/json' }; }

	function avisar() { ouvintes.slice().forEach(function (f) { try { f(estado); } catch (e) {} }); }

	function salvar() {
		clearTimeout(timer);
		timer = setTimeout(function () {
			if (!token()) return;
			fetch('/api/v1/users/user/settings/update', { method: 'POST', headers: H(), body: JSON.stringify({ nousTour: estado }) })
				.then(function (r) { if (!r.ok) throw new Error(r.status); falhas = 0; })
				.catch(function () { if (++falhas < 4) { clearTimeout(timer); timer = setTimeout(salvar, 8000 * falhas); } });
		}, 300);
	}
	function mudou() { estado.t = Date.now(); gravarEspelho(); salvar(); avisar(); }

	function carregar() {
		var t = token();
		if (!t) { setTimeout(carregar, 700); return; }   /* sem login o token chega logo depois */
		chave = 'nous-pp:' + idDoToken(t);
		var espelho = lerEspelho();
		fetch('/api/v1/users/user/settings', { headers: H() })
			.then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
			.then(function (cfg) {
				var srv = cfg && cfg.nousTour ? limpo(cfg.nousTour) : null;
				var base = srv, enviar = false;
				if (espelho && (!srv || espelho.t > srv.t)) { base = espelho; enviar = true; }
				if (!base) { base = lerAntigo(); enviar = !!base; }
				estado = base || vazio();
				carregado = true;
				gravarEspelho();
				if (enviar) salvar();
				avisar();
			})
			.catch(function () {
				/* servidor fora do ar: usa o que o navegador lembra e tenta salvar depois */
				estado = espelho || lerAntigo() || vazio();
				carregado = true;
				avisar();
				setTimeout(function () { if (estado.t) salvar(); }, 15000);
			});
	}

	window.NousProgresso = {
		/* false ate' o servidor responder: quem mostra dicas sozinho espera, para nao
		   reabrir o que a pessoa ja' viu (principalmente no celular) */
		carregado: function () { return carregado; },
		visto: function (k) { return !!estado.vistos[k]; },
		marcar: function (k) { if (estado.vistos[k]) return; estado.vistos[k] = 1; mudou(); },
		desmarcar: function (ks) {
			var ch = false;
			(ks || []).forEach(function (k) { if (estado.vistos[k]) { delete estado.vistos[k]; ch = true; } });
			if (ch) mudou();
		},
		pular: function () { return !!estado.pular; },
		setPular: function (b) { if (estado.pular === !!b) return; estado.pular = !!b; mudou(); },
		licao: function () { return estado.licao || 0; },
		setLicao: function (i) { if (estado.licao === i) return; estado.licao = i; mudou(); },
		veterano: function () { return estado.veterano; },
		setVeterano: function (b) { if (estado.veterano === b) return; estado.veterano = b; mudou(); },
		aoMudar: function (f) { ouvintes.push(f); },
		/* "Ver as dicas de novo": liga tudo que aparece sozinho (nao mexe em "veterano") */
		zerar: function () { estado.vistos = {}; estado.pular = false; estado.licao = 0; mudou(); }
	};

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', carregar);
	else carregar();
})();
