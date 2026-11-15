/* =====================================================================
   Nous - Usar no celular (v2.11). Liga e desliga o portao que deixa o celular
   abrir o Nous pelo Wi-Fi de casa (celular/nous_celular.py), mostra o QR com o
   codigo de uso unico e lista os aparelhos pareados, com "Remover".
   Desligado por padrao: so' existe enquanto a pessoa deixa ligado e se desliga
   sozinho quando o Nous fecha. Quem passa no portao usa o Nous inteiro (nao ha'
   login), e a tela diz isso. Fala com o monitor (rotas /celular/*), que so'
   atende o computador: pelo celular este botao nem aparece.
   ===================================================================== */
(function () {
	'use strict';

	if (window.NousUrl && window.NousUrl.noCelular) return;   /* aqui so' o computador manda */

	var MON = window.NousUrl(8990);
	var UI = window.NousUI || {};
	var est = null, qr = null, relogio = null, atualiza = null, ocupado = false, aviso = null, visto = null;
	var dlg = UI.dialogo({ id: 'nous-cel', titulo: 'Usar no celular', largura: 480, aoFechar: parar });

	function injectStyle() {
		if (document.getElementById('nous-cel-style')) return;
		var g = 'rgba(200,150,46,';
		var st = document.createElement('style');
		st.id = 'nous-cel-style';
		st.textContent =
			'.nous-cel-cod{font:700 26px ui-monospace,Consolas,monospace;letter-spacing:.14em;color:var(--nd-texto-ouro)}' +
			'#nous-cel-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);border-radius:8px;cursor:pointer;' +
			'background:transparent;color:#e7c069;font-weight:600;font-size:12px}#nous-cel-open:hover{background:' + g + '.12)}';
		document.head.appendChild(st);
	}

	/* ------------------------------------------------------------ rede */
	function chamar(caminho, corpo) {
		var op = corpo === undefined ? { cache: 'no-store' }
			: { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corpo || {}) };
		return fetch(MON + caminho, op).then(function (r) {
			return r.json().then(function (j) { j._status = r.status; return j; });
		});
	}

	function carregar() {
		return chamar('/celular/estado').then(function (e) {
			est = e;
			/* so' repinta se algo mudou: refazer a tela a cada 3 s comeria cliques.
			 * O minuto entra na conta para o "visto ha'" andar. */
			var marca = JSON.stringify(Object.assign({}, e, { agora: Math.floor((e.agora || 0) / 60) }));
			if (marca !== visto) { visto = marca; pintar(); }
		}).catch(function () { est = null; visto = null; pintar(); });
	}

	/* ------------------------------------------------------------ pintura */
	function el(tag, cls, texto) {
		var e = document.createElement(tag);
		if (cls) e.className = cls;
		if (texto != null) e.textContent = texto;
		return e;
	}
	function botao(texto, cls, fn) {
		var b = el('button', 'nous-dlg-btn' + (cls ? ' ' + cls : ''), texto);
		b.type = 'button';
		b.disabled = ocupado;
		b.addEventListener('click', fn);
		return b;
	}
	function quando(ts, agora) {
		if (!ts) return 'nunca usado';
		var s = Math.max(0, (agora || Date.now() / 1000) - ts);
		if (s < 90) return 'visto agora';
		if (s < 3600) return 'visto há ' + Math.round(s / 60) + ' min';
		if (s < 86400) return 'visto há ' + Math.round(s / 3600) + ' h';
		var d = Math.round(s / 86400);
		return 'visto há ' + d + (d === 1 ? ' dia' : ' dias');
	}

	function pintar() { dlg.repintar(pintarCorpo); }

	function pintarCorpo(b) {
		b.textContent = '';
		if (!est) {
			b.appendChild(el('p', null, 'O monitor do Nous não respondeu. Feche o navegador e abra o Nous pelo atalho da área de trabalho.'));
			return;
		}
		if (est.simulacao) b.appendChild(el('div', 'nous-dlg-aviso', 'Modo de teste: nada é mudado no Windows.'));
		if (aviso) {
			var av = el('div', 'nous-dlg-aviso erro');
			av.appendChild(el('p', null, aviso.texto));
			if (aviso.erro === 'rede_publica') {
				av.appendChild(botao('Abrir as configurações de rede', 'sec', function () { chamar('/celular/abrir-rede', {}); }));
				av.appendChild(el('p', 'nous-dlg-mut', 'Lá, escolha a sua rede Wi-Fi e marque "Rede privada". Depois volte aqui e ligue de novo.'));
			}
			av.lastChild.style.marginBottom = '0';
			b.appendChild(av);
		}
		if (!est.ligado) pintarDesligado(b); else pintarLigado(b);
	}

	function pintarDesligado(b) {
		b.appendChild(el('p', null, 'Use o Nous no celular, em casa, pelo mesmo Wi-Fi do computador. Fica desligado até você ligar aqui, ' +
			'e desliga sozinho quando o Nous fecha.'));
		var seg = el('div', 'nous-dlg-aviso');
		var t = el('p');
		t.innerHTML = '<b>Atenção:</b> não existe senha no Nous. Quem abrir pelo celular usa o seu Nous inteiro, como você: ' +
			'conversas, documentos, agenda e e-mail. Por isso cada celular é ligado por um QR com código de uso único, ' +
			'e só aparelhos da sua rede de casa conseguem tentar.';
		seg.appendChild(t);
		seg.appendChild(el('p', 'nous-dlg-mut', 'Ao ligar, o Windows vai pedir a sua permissão (uma vez) para liberar essa porta só na rede ' +
			'privada, a de casa. Ela é fechada de novo quando você desliga.'));
		seg.lastChild.style.marginBottom = '0';
		b.appendChild(seg);
		if (!est.ip) {
			b.appendChild(el('p', null, 'O computador não parece estar ligado a uma rede. Conecte-o ao mesmo Wi-Fi do celular para continuar.'));
		}
		b.appendChild(botao('Ligar "Usar no celular"', '', ligar));
		b.appendChild(pendencias());
		var ap = est.aparelhos || [];
		if (ap.length) {
			b.appendChild(el('div', 'nous-dlg-h', 'Celulares já ligados'));
			b.appendChild(listaAparelhos(ap));
			b.appendChild(el('p', 'nous-dlg-mut', 'Eles entram direto quando você ligar de novo, sem precisar do QR.'));
		}
		var nao = el('div', 'nous-dlg-h', 'O que não funciona no celular');
		b.appendChild(nao);
		b.appendChild(limites());
	}

	function pendencias() {
		var d = el('div');
		if (est.regra && !est.ligado) {
			d.appendChild(el('p', 'nous-dlg-mut', 'A regra do firewall ficou criada. Se quiser tirá-la, ligue e desligue de novo e aceite o pedido do Windows.'));
		}
		return d;
	}

	function limites() {
		var u = el('ul');
		u.style.cssText = 'margin:0;padding-left:18px;list-style:disc';
		['O endereço é http (sem cadeado): no celular, o microfone e a instalação como aplicativo ficam desligados.',
			'O Nous Code (programação) só abre no computador: ele roda comandos nele.',
			'Só funciona na sua rede de casa, não fora dela.'].forEach(function (x) { u.appendChild(el('li', null, x)); });
		return u;
	}

	function pintarLigado(b) {
		var topo = el('p');
		topo.innerHTML = '<span class="nous-dlg-pt"></span><b>Ligado.</b> Endereço no celular: ';
		topo.appendChild(el('b', null, est.url || '?'));
		b.appendChild(topo);
		if (est.outros_ips && est.outros_ips.length) {
			b.appendChild(el('p', 'nous-dlg-mut', 'Se o celular não abrir, o computador também tem estes endereços: ' + est.outros_ips.map(function (i) {
				return 'http://' + i + ':' + est.porta;
			}).join(', ')));
		}
		var aviso2 = el('div', 'nous-dlg-aviso');
		aviso2.innerHTML = '<b>Lembre:</b> quem entra por aqui usa o seu Nous inteiro. Ligue só celulares seus.';
		b.appendChild(aviso2);

		b.appendChild(el('div', 'nous-dlg-h', 'Ligar um celular novo'));
		var falta = qr ? Math.max(0, Math.round(qr.expira - agoraServidor())) : 0;
		if (qr && falta > 0) {
			var cx = el('div', 'nous-dlg-qr');
			if (qr.qr) {
				var im = el('img');
				im.alt = 'QR para ligar o celular';
				im.src = 'data:image/svg+xml;base64,' + qr.qr;
				cx.appendChild(im);
			}
			var dir = el('div');
			dir.appendChild(el('div', 'nous-dlg-mut', 'Se o QR não abrir, digite este código na tela do celular:'));
			dir.appendChild(el('div', 'nous-cel-cod', qr.codigo));
			var tm = el('div', 'nous-dlg-mut', '');
			tm.id = 'nous-cel-tempo';
			dir.appendChild(tm);
			cx.appendChild(dir);
			b.appendChild(cx);
			b.appendChild(el('p', 'nous-dlg-mut', 'No celular: abra a câmera, leia o QR e toque no link. O código vale uma vez só.'));
			pintarTempo();
		} else {
			b.appendChild(el('p', null, 'Abra o QR, leia com a câmera do celular e pronto. O código vale uma vez só e por 5 minutos.'));
		}
		b.appendChild(botao(qr && falta > 0 ? 'Gerar outro código' : 'Mostrar o QR', '', novoCodigo));

		b.appendChild(el('div', 'nous-dlg-h', 'Celulares ligados'));
		var ap = est.aparelhos || [];
		if (ap.length) b.appendChild(listaAparelhos(ap));
		else b.appendChild(el('p', 'nous-dlg-mut', 'Nenhum ainda.'));
		if (ap.length > 1) b.appendChild(botao('Remover todos', 'perigo', removerTodos));

		b.appendChild(el('div', 'nous-dlg-h', 'Desligar'));
		b.appendChild(botao('Desligar "Usar no celular"', 'sec', desligar));
		b.appendChild(el('div', 'nous-dlg-h', 'O que não funciona no celular'));
		b.appendChild(limites());
	}

	function listaAparelhos(ap) {
		var d = el('div');
		ap.forEach(function (a) {
			var l = el('div', 'nous-dlg-ap');
			var c = el('div');
			c.appendChild(el('b', null, a.nome || 'Aparelho'));
			c.appendChild(el('span', 'nous-dlg-mut', quando(a.ultimo_uso, est.agora) + (a.ip ? ' · ' + a.ip : '')));
			l.appendChild(c);
			var r = el('button', null, 'Remover');
			r.type = 'button';
			r.addEventListener('click', function () { remover(a); });
			l.appendChild(r);
			d.appendChild(l);
		});
		return d;
	}

	/* ------------------------------------------------------------ relogio do codigo */
	var difHora = 0;   /* hora do computador menos a do navegador (a mesma maquina, mas nao custa) */
	function agoraServidor() { return Date.now() / 1000 + difHora; }
	function pintarTempo() {
		var t = document.getElementById('nous-cel-tempo');
		if (!t || !qr) return;
		var f = Math.max(0, Math.round(qr.expira - agoraServidor()));
		if (f <= 0) { qr = null; pintar(); return; }
		t.textContent = 'Vence em ' + Math.floor(f / 60) + ':' + ('0' + (f % 60)).slice(-2);
	}

	/* ------------------------------------------------------------ acoes */
	function ocupar(v) { ocupado = v; pintar(); }

	function ligar() {
		aviso = null;
		ocupar(true);
		chamar('/celular/ligar', {}).then(function (r) {
			ocupado = false;
			if (r.erro) { aviso = r; return carregar(); }
			est = r;
			return novoCodigo();
		}).catch(function () { ocupado = false; aviso = { texto: 'Não consegui ligar. Tente de novo.' }; carregar(); })
			.then(function () { ocupado = false; pintar(); });
	}

	function novoCodigo() {
		aviso = null;
		return chamar('/celular/codigo', {}).then(function (r) {
			if (r.erro) { aviso = r; qr = null; }
			else { qr = r; difHora = (r.agora || Date.now() / 1000) - Date.now() / 1000; }
			pintar();
		}).catch(function () {});
	}

	function desligar() {
		ocupar(true);
		chamar('/celular/desligar', {}).then(function (r) {
			ocupado = false; qr = null; est = r;
			aviso = r.regra_ficou ? { texto: 'O celular foi desligado, mas a regra do firewall continua (você recusou o pedido do Windows). ' +
				'Ela só vale com o portão ligado; para tirá-la, ligue e desligue de novo e aceite.' } : null;
			if (UI.toast) UI.toast('Usar no celular: desligado.');
			return carregar();
		}).catch(function () { ocupado = false; carregar(); });
	}

	function remover(a) {
		var go = UI.confirmar ? UI.confirmar('"' + (a.nome || 'Aparelho') + '" deixa de abrir o Nous e precisa do QR de novo.',
			{ titulo: 'Remover este celular?', ok: 'Remover', perigo: true }) : Promise.resolve(true);
		go.then(function (sim) {
			if (!sim) return;
			chamar('/celular/aparelhos/remover', { id: a.id }).then(carregar);
		});
	}
	function removerTodos() {
		var go = UI.confirmar ? UI.confirmar('Nenhum celular abre mais o Nous até ler um QR novo.',
			{ titulo: 'Remover todos os celulares?', ok: 'Remover todos', perigo: true }) : Promise.resolve(true);
		go.then(function (sim) { if (sim) chamar('/celular/aparelhos/remover-todos', {}).then(carregar); });
	}

	/* ------------------------------------------------------------ janela */
	function abrir() {
		injectStyle();
		dlg.abrir();
		aviso = null;
		pintar();
		carregar();
		clearInterval(atualiza); clearInterval(relogio);
		atualiza = setInterval(carregar, 3000);
		relogio = setInterval(pintarTempo, 1000);
	}

	function parar() { clearInterval(atualiza); clearInterval(relogio); }

	/* botao no antigo card Recursos: o painel "Seu Nous" mostra como ferramenta */
	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-cel-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-cel-open';
		b.type = 'button';
		b.textContent = '📱 Celular';
		b.addEventListener('click', abrir);
		body.appendChild(b);
	}

	window.NousCelular = { open: abrir };

	function start() { injectStyle(); ensureButton(); setInterval(ensureButton, 1500); }
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
