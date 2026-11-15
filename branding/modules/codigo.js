/* =====================================================================
   Nous - Codigo (v2.10). Abre o Nous Code, o IDE com agente de IA local,
   numa janela propria (Monaco, arquivos e abas, busca, Git, terminal e o
   agente ao lado). O IDE e' servido pelo servico Node em code/ (porta 8998);
   aqui fica so' o botao que pede a janela. O atalho "Nous Code" do Menu
   Iniciar faz o mesmo sem passar pelo Nous.
   ===================================================================== */
(function () {
	'use strict';

	var API = window.NousUrl(8998);
	var UI = window.NousUI || {};

	/* tarefa: pedido feito no chat; o Nous Code abre uma conversa nova com ele escrito */
	function open(pasta, tarefa) {
		if (window.NousUrl.noCelular) {   /* pelo celular nao existe: ele roda comandos no computador */
			if (UI.aviso) UI.aviso('O Nous Code só abre no próprio computador, não pelo celular.', 'erro');
			return;
		}
		var corpo = {};
		if (pasta) corpo.pasta = pasta;
		if (tarefa) corpo.tarefa = tarefa;
		fetch(API + '/abrir-janela', { method: 'POST', headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify(corpo) })
			.then(function (r) { if (!r.ok) throw new Error(); if (UI.toast) UI.toast(tarefa ? 'Abrindo o Nous Code com o seu pedido…' : 'Abrindo o Nous Code numa janela própria…'); })
			.catch(function () {
				var msg = 'O Nous Code não está rodando. Ele precisa do Node.js 22.18 ou mais novo: instale com ' +
					'"winget install OpenJS.NodeJS.LTS" e abra o Nous de novo pelo atalho.';
				if (UI.aviso) UI.aviso(msg, 'erro'); else window.alert(msg);
			});
	}

	/* botao no antigo card Recursos: o painel "Seu Nous" mostra como ferramenta */
	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-code-open')) return;
		if (window.NousUrl.noCelular) return;   /* pelo celular o Nous Code nao existe: ele roda comandos no computador */
		var b = document.createElement('button');
		b.id = 'nous-code-open';
		b.type = 'button';
		b.textContent = '⌨ Código';
		b.addEventListener('click', function () { open(); });
		body.appendChild(b);
	}

	window.NousCode = { open: open };

	function start() { ensureButton(); setInterval(ensureButton, 1500); }
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
