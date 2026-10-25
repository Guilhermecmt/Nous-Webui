/* =====================================================================
   Nous - Avisos de atualização (v2.11). Avisa quando há versão nova do Nous ou
   de um modelo instalado e atualiza com um clique. Quem procura e aplica é o
   atualizacao/nous-atualizar.ps1 (pelo Nous Monitor, /update/*); o mesmo aviso
   também sai no ícone da bandeja. Procurar é uma ida à internet, no máximo 1 vez
   por dia; para desligar: ícone da bandeja > "Procurar atualizações sozinho".
   ===================================================================== */
(function () {
	'use strict';

	var MON = 'http://127.0.0.1:8990';
	var DIA = 24 * 3600 * 1000;
	var aplicando = false;

	function ls(k, v) {
		try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) {}
		return null;
	}
	/* mostra o aviso de uma coisa no máximo 1 vez por dia */
	function jaAvisei(chave) {
		var t = parseInt(ls('nous-upd-' + chave) || '0', 10);
		return t && Date.now() - t < DIA;
	}
	function marcaAvisado(chave) { ls('nous-upd-' + chave, String(Date.now())); }

	function api(path, body) {
		return fetch(MON + path, body === undefined ? { cache: 'no-store' } :
			{ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
			.then(function (r) { return r.json(); });
	}

	function acompanha(versaoAntes) {
		/* o Nous fecha e abre durante a troca: enquanto não responde, só espera */
		var inicio = Date.now();
		var t = setInterval(function () {
			if (Date.now() - inicio > 25 * 60 * 1000) { clearInterval(t); aplicando = false; return; }
			api('/update/status').then(function (d) {
				var e = d.estado || {};
				if (e.fase === 'falhou' || e.fase === 'revertida') {
					clearInterval(t); aplicando = false;
					window.NousUI.toast(e.mensagem || 'A atualização não deu certo.', { tipo: 'erro', ms: 12000 });
				} else if (e.fase === 'concluida' || (d.versao && d.versao !== versaoAntes)) {
					clearInterval(t);
					window.NousUI.toast(e.mensagem || 'Nous atualizado! Recarregando...', { ms: 4000 });
					setTimeout(function () { location.reload(); }, 1500);
				}
			}).catch(function () { /* servidor reiniciando */ });
		}, 4000);
	}

	function atualizarApp(est, versaoAtual) {
		if (aplicando) return;
		var notas = est.notas ? '\n\nNovidades: ' + est.notas : '';
		window.NousUI.confirmar(
			'O Nous vai de ' + versaoAtual + ' para ' + est.versao_nova + (est.tamanho_mb ? ' (download de ' + est.tamanho_mb + ' MB)' : '') +
			'. Ele fecha por alguns minutos e abre de novo sozinho. Suas conversas e arquivos não são tocados; se algo der errado, ele volta para a versão atual.' + notas,
			{ titulo: 'Atualizar o Nous?', ok: 'Atualizar' }
		).then(function (sim) {
			if (!sim) return;
			api('/update/apply', {}).then(function (r) {
				if (!r.started) { window.NousUI.toast('Não consegui começar agora (' + (r.reason || 'tente de novo') + ').', { tipo: 'erro' }); return; }
				aplicando = true;
				window.NousUI.toast('Atualizando o Nous... pode levar alguns minutos. Esta tela recarrega sozinha.', { tipo: 'info', ms: 15000 });
				acompanha(versaoAtual);
			}).catch(function () { window.NousUI.toast('Não consegui falar com o Nous agora. Tente de novo.', { tipo: 'erro' }); });
		});
	}

	function atualizarModelos(lista) {
		var nomes = lista.map(function (m) { return m.nome; });
		window.NousUI.confirmar(
			'Baixar a versão nova de: ' + nomes.join(', ') + '. Só as partes que mudaram são baixadas; você acompanha na Loja de Modelos.',
			{ titulo: 'Atualizar modelos?', ok: 'Atualizar' }
		).then(function (sim) {
			if (!sim) return;
			Promise.all(nomes.map(function (n) { return api('/update/modelos/atualizar', { model: n }); })).then(function () {
				window.NousUI.toast('Baixando a versão nova dos modelos.', { tipo: 'info', rotulo: 'Ver progresso', acao: function () { window.NousUI.openStore(); }, ms: 9000 });
			}).catch(function () { window.NousUI.toast('Não consegui iniciar o download agora.', { tipo: 'erro' }); });
		});
	}

	function checa() {
		if (aplicando || (window.NousUI.onAuth && window.NousUI.onAuth())) return;
		api('/update/status').then(function (d) {
			var e = d.estado || {};
			if (e.disponivel && e.versao_nova && !jaAvisei('app-' + e.versao_nova)) {
				marcaAvisado('app-' + e.versao_nova);
				window.NousUI.toast('Há uma versão nova do Nous: ' + e.versao_nova + ' (a sua é a ' + d.versao + ').',
					{ tipo: 'info', rotulo: 'Atualizar', acao: function () { atualizarApp(e, d.versao); }, ms: 20000 });
				return;
			}
			var novos = (e.modelos_novos || []).filter(function (m) { return m && m.nome; });
			var chave = 'mod-' + novos.map(function (m) { return m.nome; }).join(',');
			if (novos.length && !jaAvisei(chave)) {
				marcaAvisado(chave);
				window.NousUI.toast(novos.length === 1 ? 'O modelo ' + novos[0].nome + ' tem versão nova.' : novos.length + ' modelos têm versão nova.',
					{ tipo: 'info', rotulo: 'Atualizar', acao: function () { atualizarModelos(novos); }, ms: 20000 });
			}
		}).catch(function () { /* monitor fora do ar: sem aviso */ });
	}

	function start() {
		if (!window.NousUI || !window.NousUI.toast || !window.NousUI.confirmar) return;
		setTimeout(checa, 9000);
		setInterval(checa, 30 * 60 * 1000);
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
