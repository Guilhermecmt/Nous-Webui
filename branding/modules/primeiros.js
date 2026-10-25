/* =====================================================================
   Nous - Primeiros passos (v2.11), para quem nunca usou IA.
   Quatro pecas, todas com o progresso salvo no servidor (_progresso.js):
     1. Licoes curtas: o que e' um modelo, a IA pode errar, como pedir bem,
        o que fica no computador, foto e documento. Aparecem no assistente de
        primeiro uso enquanto o modelo baixa (nous-loader.js chama
        NousPrimeiros.licoes) e tambem pelo botao "?". Andam no ritmo da pessoa;
        o download nao depende delas e elas nao somem quando ele termina.
     2. Primeira conversa guiada: cartoes de tarefas do dia a dia na tela
        inicial. Clicar preenche o pedido (nao envia) e um aviso explica; quando
        a resposta termina, outro aviso explica como ler e conferir.
     3. Botao "?" sempre a' mao: reve qualquer parte (licoes, exemplos, como
        mandar foto e documento, passeio pela tela, dicas dos paineis).
     4. O passeio pela tela e' do tour.js (uma fila so'): aqui so' se pede ao
        NousTour para rodar, e os avisos esperam ele terminar.
   Nada disso aparece sozinho para quem ja' usava o Nous (conversas guardadas,
   dicas antigas vistas) nem para quem tocou em "Pular dicas".
   ===================================================================== */
(function () {
	'use strict';

	var LICOES = [
		{ t: 'O que é um modelo?', h:
			'<p>O <b>modelo</b> é o cérebro da IA. É um arquivo grande, guardado no seu computador, que lê o que você escreve e responde.</p>' +
			'<p>Por isso o download demora: são vários gigabytes. Mas só se baixa <b>uma vez</b>.</p>' +
			'<p>Cada modelo tem o seu jeito: uns respondem mais rápido, outros escrevem com mais capricho. Depois você pode baixar outros na <b>Loja de Modelos</b> e trocar pelo topo da conversa.</p>' },
		{ t: 'A IA pode errar', h:
			'<p>Ela escreve frases que <b>parecem certas</b>, mesmo quando estão erradas. Pode inventar nomes, datas, números e até leis.</p>' +
			'<p>Como conferir:</p>' +
			'<ul><li>Confira números, datas e nomes em outra fonte.</li>' +
			'<li>Peça de novo, de outro jeito. Se a resposta mudar, desconfie.</li>' +
			'<li>Para saúde, dinheiro e leis, use a IA para entender o assunto e <b>confirme com um profissional</b>.</li></ul>' },
		{ t: 'Como pedir bem', h:
			'<p>Quanto mais claro o pedido, melhor a resposta. Diga o que você quer, para quem é e como deve ficar.</p>' +
			'<div class="nous-pp-ex"><div class="fraco"><i>Fraco</i>Escreve um e-mail.</div>' +
			'<div class="bom"><i>Melhor</i>Escreva um e-mail curto e educado para o síndico pedindo o conserto do portão da garagem. Tom amigável, até 5 linhas.</div></div>' +
			'<div class="nous-pp-ex"><div class="fraco"><i>Fraco</i>Me fala de investimento.</div>' +
			'<div class="bom"><i>Melhor</i>Explique a diferença entre poupança e Tesouro Selic, como se eu nunca tivesse investido. Dê um exemplo com R$ 1.000.</div></div>' +
			'<p>Não gostou? Não precisa recomeçar: escreva <b>"mais curto"</b>, <b>"mais simples"</b> ou <b>"explique o segundo ponto"</b>.</p>' },
		{ t: 'O que fica no seu computador', h:
			'<p>O Nous roda a IA <b>aqui</b>, neste computador. Suas conversas, memórias e documentos ficam guardados aqui e não vão para nenhuma empresa.</p>' +
			'<p>Para conversar você <b>não precisa de internet</b>.</p>' +
			'<p>Só sai do computador o que você mandar sair: pesquisar na internet, conectar o e-mail ou o Google Agenda, baixar um modelo novo.</p>' +
			'<p>A <b>Conversa privada</b> vai além: não fica nem no histórico.</p>' },
		{ t: 'Foto e documento', h:
			'<p>Para a IA olhar uma foto ou ler um documento, clique no <b>+</b> ao lado da caixa de mensagem e escolha o arquivo. Também dá para <b>arrastar</b> o arquivo para a conversa ou <b>colar</b> uma imagem com Ctrl+V.</p>' +
			'<p><b>Documentos</b> (PDF, Word, texto): ela lê e responde perguntas sobre o conteúdo.</p>' +
			'<p><b>Fotos</b>: só funcionam com um modelo que <b>entende imagens</b>. Na Loja de Modelos, eles têm esse aviso.</p>', anexo: true }
	];

	var CARTOES = [
		{ i: '✉️', t: 'Escrever uma mensagem', d: 'Um recado educado, sem enrolação',
			p: 'Escreva uma mensagem curta e educada para o meu vizinho, pedindo para ele baixar o volume da música depois das 22h. Tom amigável.',
			e: 'Isso é uma mensagem que você pode copiar e mandar. Ficou formal demais? Escreva "mais simples" ou "mais curto".' },
		{ i: '🧾', t: 'Entender uma conta', d: 'O que significa cada item',
			p: 'Explique em palavras simples o que é cada item de uma conta de luz (consumo, bandeira tarifária, iluminação pública, impostos) e o que posso fazer para pagar menos.',
			e: 'Com a sua conta de verdade, clique no + e envie a foto ou o PDF: a IA explica item por item. Os valores e as regras mudam de lugar para lugar, então confira na própria conta.' },
		{ i: '📅', t: 'Planejar a semana', d: 'Uma tabela simples, dia a dia',
			p: 'Me ajude a planejar minha semana. Trabalho de segunda a sexta, das 9h às 18h, e quero caminhar três vezes e arrumar a casa no sábado. Monte uma tabela simples por dia.',
			e: 'Esse é um rascunho para você ajustar: troque os horários, tire o que não cabe e peça "refaça com mais tempo livre".' },
		{ i: '💡', t: 'Tirar uma dúvida', d: 'Explicado para quem está começando',
			p: 'Qual é a diferença entre poupança e Tesouro Selic? Explique como se eu nunca tivesse investido.',
			e: 'Boa para entender um assunto. Para decidir sobre dinheiro, confirme números e taxas em um site oficial ou com um profissional: a IA pode errar.' }
	];

	var AJUDA = [
		{ k: 'licoes', t: 'Lições curtas', d: 'O que é um modelo, como pedir bem e o que fica no computador.' },
		{ k: 'exemplos', t: 'Exemplos para começar', d: 'Pedidos prontos do dia a dia: é só clicar e enviar.' },
		{ k: 'anexo', t: 'Como mandar foto e documento', d: 'Mostra onde fica o botão para anexar.' },
		{ k: 'passeio', t: 'Passeio pela tela', d: 'Para que serve cada parte do Nous.' },
		{ k: 'paineis', t: 'Dicas de cada painel', d: 'As dicas de Agenda, E-mail, Documentos e do resto voltam a aparecer.' }
	];

	var ov = null, voltarFoco = null, coach = null, cartoesEl = null, forcarCartoes = false, usou = null;
	var P = function () { return window.NousProgresso; };
	var TOUR = function () { return window.NousTour; };

	function visible(id) { var e = document.getElementById(id); return !!e && !e.classList.contains('nous-hidden'); }
	function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
	function reduzido() { return window.matchMedia && window.matchMedia('(prefers-reduced-motion:reduce)').matches; }
	function estreito() { return window.innerWidth < 768; }
	function naTela() { return !(window.NousUI && window.NousUI.onAuth && window.NousUI.onAuth()); }

	/* ------------------------------------------------------------ estilo */
	function injectStyle() {
		if (document.getElementById('nous-pp-style')) return;
		var st = document.createElement('style');
		st.id = 'nous-pp-style';
		var g = 'rgba(200,150,46,';
		st.textContent =
			/* botao "?" : no trilho da esquerda (tela larga) ou abaixo da coruja (estreita) */
			'#nous-pp-aj{position:fixed;z-index:38;left:7px;bottom:58px;width:30px;height:30px;border-radius:50%;padding:0;cursor:pointer;' +
			'border:1.5px solid ' + g + '.7);background:rgba(18,18,22,.92);color:#e7c069;font:700 15px/1 Inter,system-ui,sans-serif;' +
			'box-shadow:0 3px 12px rgba(0,0,0,.3);transition:background .15s,transform .15s}' +
			'#nous-pp-aj:hover{background:' + g + '.3);transform:scale(1.06)}' +
			'#nous-pp-aj:focus-visible,.nous-pp-card:focus-visible,#nous-pp-ov button:focus-visible,#nous-pp-coach button:focus-visible{outline:2px solid #e7c069;outline-offset:2px}' +
			'@media (max-width:767px){#nous-pp-aj{left:auto;right:13px;bottom:auto;top:120px;width:44px;height:44px;font-size:19px}}' +
			/* janela (licoes e menu do "?") */
			'#nous-pp-ov{position:fixed;inset:0;z-index:10020;background:rgba(8,8,10,.72);display:flex;align-items:center;justify-content:center;' +
			'backdrop-filter:blur(4px);font-family:Inter,system-ui,sans-serif;color:#eee}' +
			'#nous-pp-jan{width:520px;max-width:94vw;max-height:92vh;overflow:auto;background:rgba(18,18,22,.98);border:1px solid ' + g + '.45);' +
			'border-radius:18px;padding:20px 22px 18px;box-shadow:0 20px 60px rgba(0,0,0,.6)}' +
			'#nous-pp-jan h2{margin:0 0 4px;font:600 17px Cinzel,Georgia,serif;letter-spacing:.05em;color:#e7c069}' +
			'#nous-pp-jan .sub{font-size:12.5px;opacity:.7;margin-bottom:12px}' +
			'.nous-pp-fecha{float:right;margin:-4px -6px 0 8px;width:32px;height:32px;border-radius:8px;border:0;background:none;color:#bbb;font-size:20px;cursor:pointer}' +
			'.nous-pp-fecha:hover{background:rgba(255,255,255,.08);color:#fff}' +
			'.nous-pp-item{display:block;width:100%;text-align:left;margin:0 0 8px;padding:10px 12px;border-radius:12px;cursor:pointer;color:#eee;' +
			'border:1px solid ' + g + '.35);background:' + g + '.07);font:13px/1.45 Inter,system-ui,sans-serif}' +
			'.nous-pp-item:hover{background:' + g + '.18)}.nous-pp-item b{display:block;color:#e7c069;font-size:13.5px}' +
			'.nous-pp-item span{opacity:.75;font-size:12px}' +
			'.nous-pp-troca{display:flex;align-items:center;gap:10px;margin-top:6px;padding:8px 2px 0;font-size:12.5px;opacity:.9}.nous-pp-troca span{flex:1}' +
			'.nous-pp-troca button{white-space:nowrap;padding:5px 11px;border-radius:8px;border:1px solid ' + g + '.5);background:' + g + '.18);color:#e7c069;font:600 12px Inter,system-ui,sans-serif;cursor:pointer}' +
			/* licoes */
			'.nous-pp-lic{text-align:left;font-size:13.5px;line-height:1.55}' +
			'.nous-pp-lic .topo{display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px;opacity:.8}' +
			'.nous-pp-lic .topo span{flex:1}' +
			'.nous-pp-lic h3{margin:0 0 8px;font:600 16px Inter,system-ui,sans-serif;color:#e7c069;outline:none;border-radius:6px}' +
			'.nous-pp-lic h3:focus-visible{outline:2px solid #e7c069;outline-offset:3px}' +
			'.nous-pp-lic .corpo{min-height:19.5em}.nous-pp-lic .corpo p{margin:0 0 9px}.nous-pp-lic .corpo ul{margin:0 0 9px;padding-left:20px}.nous-pp-lic .corpo li{margin-bottom:4px}' +
			'.nous-pp-lic .corpo b{color:#f0d9a0}' +
			'.nous-pp-ex{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0 0 9px}' +
			'.nous-pp-ex>div{padding:8px 10px;border-radius:10px;font-size:12.5px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1)}' +
			'.nous-pp-ex .bom{border-color:' + g + '.5);background:' + g + '.1)}' +
			'.nous-pp-ex i{display:block;font-style:normal;font-weight:700;font-size:11px;letter-spacing:.05em;text-transform:uppercase;opacity:.7;margin-bottom:2px}' +
			'.nous-pp-ex .bom i{color:#e7c069;opacity:1}' +
			'@media (max-width:767px){.nous-pp-btn,.nous-pp-troca button,#nous-pp-coach button{min-height:44px}.nous-pp-fecha{width:44px;height:44px}.nous-pp-lic .topo .nous-pp-btn{min-height:40px}}' +
			'@media (max-width:480px){.nous-pp-ex{grid-template-columns:1fr}.nous-pp-lic .corpo{min-height:0}}' +
			'.nous-pp-lic .nav{display:flex;align-items:center;gap:8px;margin-top:12px}' +
			'.nous-pp-lic .pontos{flex:1;display:flex;gap:6px;justify-content:center}' +
			'.nous-pp-lic .pontos i{width:7px;height:7px;border-radius:50%;background:rgba(255,255,255,.22)}' +
			'.nous-pp-lic .pontos i.v{background:' + g + '.6)}.nous-pp-lic .pontos i.a{background:#e7c069;transform:scale(1.25)}' +
			'.nous-pp-btn{padding:7px 14px;border-radius:9px;border:1px solid ' + g + '.5);background:' + g + '.2);color:#e7c069;font:600 12.5px Inter,system-ui,sans-serif;cursor:pointer}' +
			'.nous-pp-btn:hover:not(:disabled){background:' + g + '.35)}.nous-pp-btn:disabled{opacity:.35;cursor:default}' +
			'.nous-pp-btn.g{background:transparent;color:#aaa;border-color:rgba(255,255,255,.18)}' +
			'.nous-pp-lic .mostra{margin-top:4px}' +
			/* cartoes da primeira conversa (tela inicial, claro e escuro) */
			'#nous-pp-cartoes{width:100%;max-width:660px;margin:12px auto 0;padding:0 8px;box-sizing:border-box;font-family:Inter,system-ui,sans-serif;text-align:center}' +
			'#nous-pp-cartoes .tit{display:flex;justify-content:center;align-items:baseline;gap:10px;font-size:12.5px;color:#7a7a7a;margin-bottom:8px}' +
			'.dark #nous-pp-cartoes .tit{color:#8c8c8c}' +
			'#nous-pp-cartoes .tit button{border:0;background:none;padding:2px 4px;cursor:pointer;font:12px Inter,system-ui,sans-serif;color:#8a6414;text-decoration:underline;text-underline-offset:2px}' +
			'.dark #nous-pp-cartoes .tit button{color:#c8962e}' +
			'#nous-pp-cartoes .grade{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}' +
			'@media (max-width:480px){#nous-pp-cartoes .grade{grid-template-columns:1fr}}' +
			'.nous-pp-card{display:flex;gap:10px;align-items:flex-start;text-align:left;padding:10px 12px;border-radius:12px;cursor:pointer;color:inherit;' +
			'border:1px solid ' + g + '.45);background:' + g + '.06);font:inherit;transition:background .15s}' +
			'.nous-pp-card:hover{background:' + g + '.16)}.nous-pp-card.on{background:' + g + '.22);border-color:#c8962e}' +
			'.nous-pp-card .ic{font-size:20px;line-height:1.2}.nous-pp-card b{display:block;font-size:13.5px;color:#8a6414}' +
			'.dark .nous-pp-card b{color:#e7c069}.nous-pp-card span.d{display:block;font-size:12px;color:#6b6b6b}.dark .nous-pp-card span.d{color:#9a9a9a}' +
			'#nous-pp-cartoes.escolheu .grade,#nous-pp-cartoes.escolheu .tit{display:none}' +
			'body.nous-pp-cartoes #nous-ini .nous-ini-dica,body.nous-pp-cartoes .nous-pp-sug{display:none!important}' +
			/* avisos que acompanham a primeira conversa (acima da caixa de mensagem) */
			'#nous-pp-coach{max-width:560px;padding:11px 14px;border-radius:12px;background:rgba(18,18,22,.98);' +
			'border:1px solid ' + g + '.6);color:#eee;font:13px/1.5 Inter,system-ui,sans-serif;box-shadow:0 12px 32px rgba(0,0,0,.5);box-sizing:border-box;text-align:left}' +
			'#nous-pp-coach.fixo{position:fixed;z-index:10004}#nous-pp-coach.dentro{margin:0 auto;box-shadow:none}' +
			'#nous-pp-coach.fluxo{margin:6px auto 16px;width:calc(100% - 32px);max-width:760px;box-shadow:0 6px 20px rgba(0,0,0,.35)}' +
			'#nous-pp-coach b{color:#e7c069}#nous-pp-coach ul{margin:6px 0 0;padding-left:18px}#nous-pp-coach li{margin-bottom:3px}' +
			'#nous-pp-coach .r{display:flex;justify-content:flex-end;margin-top:8px}' +
			'#nous-pp-coach button{padding:5px 12px;border-radius:8px;border:1px solid ' + g + '.5);cursor:pointer;background:' + g + '.2);color:#e7c069;font:600 12px Inter,system-ui,sans-serif}' +
			'@media (prefers-reduced-motion:reduce){#nous-pp-aj,.nous-pp-card{transition:none}#nous-pp-aj:hover{transform:none}}';
		document.head.appendChild(st);
	}

	/* ------------------------------------------------------------ licoes */
	/* Monta as licoes dentro de `host`. op.aoFim: terminou a ultima. op.sempre: ignora
	   o ponto onde a pessoa parou (revisao). Devolve {destruir}. */
	function licoes(host, op) {
		op = op || {};
		injectStyle();
		var i = op.sempre ? 0 : Math.min(P() ? P().licao() : 0, LICOES.length - 1);
		host.innerHTML =
			'<section class="nous-pp-lic" aria-label="Lições curtas"><div class="topo"><span id="nous-pp-lic-n" aria-live="polite"></span>' +
			(op.pular ? '<button type="button" class="nous-pp-btn g" data-x="pular">Pular lições</button>' : '') + '</div>' +
			'<h3 tabindex="-1"></h3><div class="corpo"></div><div class="mostra"></div>' +
			'<div class="nav"><button type="button" class="nous-pp-btn g" data-x="ant">Anterior</button>' +
			'<span class="pontos" aria-hidden="true"></span><button type="button" class="nous-pp-btn" data-x="prox"></button></div></section>';
		var sec = host.firstChild, h3 = sec.querySelector('h3'), corpo = sec.querySelector('.corpo'), mostra = sec.querySelector('.mostra'),
			pontos = sec.querySelector('.pontos'), n = sec.querySelector('#nous-pp-lic-n'),
			ant = sec.querySelector('[data-x=ant]'), prox = sec.querySelector('[data-x=prox]');
		pontos.innerHTML = LICOES.map(function () { return '<i></i>'; }).join('');
		function pinta(foco) {
			var l = LICOES[i];
			n.textContent = 'Lição ' + (i + 1) + ' de ' + LICOES.length;
			h3.textContent = l.t;
			corpo.innerHTML = l.h;
			mostra.innerHTML = '';
			if (l.anexo && op.mostrarAnexo) {
				var b = document.createElement('button');
				b.type = 'button'; b.className = 'nous-pp-btn'; b.textContent = 'Mostrar onde fica o +';
				b.addEventListener('click', op.mostrarAnexo);
				mostra.appendChild(b);
			}
			ant.disabled = i === 0;
			prox.textContent = i === LICOES.length - 1 ? 'Terminei' : 'Próxima';
			[].forEach.call(pontos.children, function (d, k) { d.className = k === i ? 'a' : (k < i ? 'v' : ''); });
			if (P() && !op.sempre) P().setLicao(i);
			if (foco) h3.focus();
		}
		ant.addEventListener('click', function () { if (i > 0) { i--; pinta(true); } });
		prox.addEventListener('click', function () {
			if (i < LICOES.length - 1) { i++; pinta(true); return; }
			if (P()) { P().marcar('licoes'); P().setLicao(0); }
			if (op.aoFim) op.aoFim();
		});
		var pu = sec.querySelector('[data-x=pular]');
		if (pu) pu.addEventListener('click', function () { if (P()) { P().marcar('licoes'); P().setLicao(0); } if (op.aoPular) op.aoPular(); });
		sec.addEventListener('keydown', function (e) {
			if (e.altKey || e.ctrlKey || e.metaKey || /^(INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
			if (e.key === 'ArrowRight' && i < LICOES.length - 1) { i++; pinta(true); e.preventDefault(); }
			else if (e.key === 'ArrowLeft' && i > 0) { i--; pinta(true); e.preventDefault(); }
		});
		pinta(false);
		return { atual: function () { return i; } };
	}

	/* ------------------------------------------------------------ janela do "?" */
	function fechaJanela() {
		if (!ov) return;
		document.removeEventListener('keydown', teclaJanela, true);
		ov.remove(); ov = null;
		if (voltarFoco && document.contains(voltarFoco)) voltarFoco.focus();
		voltarFoco = null;
	}
	function teclaJanela(e) {
		if (!ov) return;
		if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); fechaJanela(); return; }
		if (e.key !== 'Tab') return;
		var fs = [].filter.call(ov.querySelectorAll('button:not(:disabled)'), function (b) { return b.offsetParent !== null; });
		if (!fs.length) return;
		var a = document.activeElement, p = fs[0], u = fs[fs.length - 1];
		if (e.shiftKey && (a === p || !ov.contains(a))) { u.focus(); e.preventDefault(); }
		else if (!e.shiftKey && (a === u || !ov.contains(a))) { p.focus(); e.preventDefault(); }
	}
	function abreJanela(titulo, sub) {
		injectStyle();
		var ativo = document.activeElement;
		if (ov) fechaJanela();
		voltarFoco = ativo && ativo !== document.body ? ativo : document.getElementById('nous-pp-aj');
		ov = document.createElement('div');
		ov.id = 'nous-pp-ov';
		ov.innerHTML = '<div id="nous-pp-jan" role="dialog" aria-modal="true" aria-labelledby="nous-pp-tit">' +
			'<button type="button" class="nous-pp-fecha" aria-label="Fechar">×</button><h2 id="nous-pp-tit"></h2><div class="sub"></div><div class="nous-pp-c"></div></div>';
		ov.querySelector('h2').textContent = titulo;
		ov.querySelector('.sub').textContent = sub || '';
		if (!sub) ov.querySelector('.sub').style.display = 'none';
		ov.querySelector('.nous-pp-fecha').addEventListener('click', fechaJanela);
		ov.addEventListener('mousedown', function (e) { if (e.target === ov) fechaJanela(); });
		document.body.appendChild(ov);
		document.addEventListener('keydown', teclaJanela, true);
		return ov.querySelector('.nous-pp-c');
	}

	function abrirLicoes() {
		var c = abreJanela('Lições curtas', 'Cinco minutos para começar bem. Vá no seu ritmo.');
		licoes(c, { sempre: true, aoFim: fechaJanela, mostrarAnexo: function () { fechaJanela(); setTimeout(function () { executar('anexo'); }, 200); } });
		var h = c.querySelector('h3'); if (h) h.focus();
	}

	function abrirMenu() {
		var c = abreJanela('Primeiros passos', 'Escolha o que você quer rever. O botão ? fica sempre à mão.');
		c.innerHTML = AJUDA.map(function (a) {
			return '<button type="button" class="nous-pp-item" data-k="' + a.k + '"><b>' + esc(a.t) + '</b><span>' + esc(a.d) + '</span></button>';
		}).join('') + '<div class="nous-pp-troca"><span id="nous-pp-auto"></span><button type="button" id="nous-pp-auto-b"></button></div>';
		function pintaAuto() {
			var off = P() && P().pular();
			c.querySelector('#nous-pp-auto').textContent = off ? 'As dicas automáticas estão desligadas.' : 'As dicas aparecem sozinhas quando fazem sentido.';
			c.querySelector('#nous-pp-auto-b').textContent = off ? 'Ligar de novo' : 'Desligar';
		}
		pintaAuto();
		c.querySelector('#nous-pp-auto-b').addEventListener('click', function () { if (P()) P().setPular(!P().pular()); pintaAuto(); });
		[].forEach.call(c.querySelectorAll('.nous-pp-item'), function (b) {
			b.addEventListener('click', function () { var k = b.getAttribute('data-k'); fechaJanela(); setTimeout(function () { executar(k); }, 150); });
		});
		var p = c.querySelector('.nous-pp-item'); if (p) p.focus();
	}

	/* o que o menu do "?" faz; algumas coisas precisam da tela inicial: recarrega e continua */
	function executar(k) {
		if (k === 'licoes') { abrirLicoes(); return; }
		var precisaChat = k === 'anexo' || k === 'passeio' || k === 'exemplos';
		if (precisaChat && !document.getElementById('chat-input')) {
			try { sessionStorage.setItem('nous-pp-depois', k); } catch (e) {}
			location.href = '/';
			return;
		}
		if (k === 'exemplos') {
			forcarCartoes = true;
			if (!document.getElementById('nous-ini')) {   /* ja' ha' uma conversa na tela: abre uma nova */
				try { sessionStorage.setItem('nous-pp-depois', 'exemplos'); } catch (e) {}
				location.href = '/';
				return;
			}
			tickCartoes();
			var c = document.getElementById('nous-pp-cartoes');
			if (c && c.scrollIntoView) c.scrollIntoView({ block: 'center', behavior: reduzido() ? 'auto' : 'smooth' });
			var b = c && c.querySelector('.nous-pp-card'); if (b) b.focus();
		} else if (k === 'anexo') { if (TOUR()) TOUR().run('anexo'); }
		else if (k === 'passeio') { if (TOUR()) TOUR().run('home'); }
		else if (k === 'paineis') {
			if (TOUR()) TOUR().reset();
			if (window.NousUI && window.NousUI.toast) window.NousUI.toast('Pronto. A dica de cada painel aparece quando você abri-lo.', { tipo: 'info', ms: 5000 });
		}
	}

	/* ------------------------------------------------------------ botao "?" */
	function montaAjuda() {
		if (document.getElementById('nous-pp-aj') || !document.body || !naTela()) return;
		var b = document.createElement('button');
		b.type = 'button'; b.id = 'nous-pp-aj';
		b.textContent = '?';
		b.title = 'Primeiros passos: rever as dicas e as lições';
		b.setAttribute('aria-label', 'Ajuda: primeiros passos');
		b.setAttribute('aria-haspopup', 'dialog');
		b.addEventListener('click', abrirMenu);
		document.body.appendChild(b);
	}
	/* a gaveta do painel "Seu Nous" (tela estreita) cobre o botao: ele some enquanto ela esta' aberta */
	function ajustaAjuda() {
		var b = document.getElementById('nous-pp-aj');
		if (!b) return;
		var pn = document.getElementById('nous-pn');
		var gaveta = estreito() && pn && !pn.classList.contains('nous-pn-off');
		var esconde = !naTela() || gaveta;
		if (b.hidden !== esconde) b.hidden = esconde;
	}

	/* ------------------------------------------------------------ modelo instalado? */
	/* Sem nenhum modelo de conversa o assistente de primeiro uso (nous-loader.js) vem primeiro:
	   o passeio e os cartoes esperam, para nao brigar com ele. undefined = ainda nao sei;
	   'fora' = o monitor nao respondeu (o assistente tambem nao aparece), segue sem esperar. */
	var temModelo, consultando = false, consultouEm = 0;
	function consultaModelo() {
		if (temModelo === true || consultando || Date.now() - consultouEm < 4000 || !window.NousUrl) return;
		consultando = true; consultouEm = Date.now();
		fetch(window.NousUrl(8990) + '/installed', { cache: 'no-store' })
			.then(function (r) { return r.json(); })
			.then(function (d) { temModelo = !d || !d.online ? 'fora' : ((d.chat || []).length > 0); })
			.catch(function () { temModelo = 'fora'; })
			.then(function () { consultando = false; });
	}
	function modeloPronto() { return temModelo === true || temModelo === 'fora'; }

	/* ------------------------------------------------------------ veterano */
	/* Quem ja' tem conversas (ou dicas antigas vistas) nao e' novato: nada de tour sozinho. */
	var verificando = false;
	function detectaVeterano() {
		var p = P();
		if (!p || !p.carregado() || p.veterano() !== null || verificando) return;
		var t = ''; try { t = localStorage.getItem('token') || ''; } catch (e) {}
		if (!t) return;
		verificando = true;
		fetch('/api/v1/chats/?page=1', { headers: { 'Authorization': 'Bearer ' + t } })
			.then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
			.then(function (lista) {
				var vet = Array.isArray(lista) && lista.length > 0;
				p.setVeterano(vet);
				if (vet) ['home', 'licoes', 'cartoes'].forEach(function (k) { p.marcar(k); });
			})
			.catch(function () { verificando = false; });   /* tenta de novo no proximo ciclo; ate' la' nada aparece sozinho */
	}
	/* pode mostrar coisas de iniciante sozinho? */
	function novato() {
		var p = P();
		return !!p && p.carregado() && p.veterano() === false && !p.pular();
	}

	/* ------------------------------------------------------------ cartoes + avisos */
	function preencher(texto) {
		var box = document.getElementById('chat-input');
		if (!box) return false;
		box.focus();
		if (box.tagName === 'TEXTAREA') { box.value = texto; box.dispatchEvent(new Event('input', { bubbles: true })); }
		else { document.execCommand('selectAll', false, null); document.execCommand('insertText', false, texto); }
		return true;
	}
	function escondeSugestoes(sim) {
		var bs = document.querySelectorAll('button.waterfall');
		[].forEach.call(bs, function (b) {
			var c = b.closest('.max-w-2xl');
			if (c) c.classList.toggle('nous-pp-sug', sim);
		});
		if (!sim) [].forEach.call(document.querySelectorAll('.nous-pp-sug'), function (c) { c.classList.remove('nous-pp-sug'); });
	}
	function tirarCartoes() {
		if (cartoesEl) { cartoesEl.remove(); cartoesEl = null; }
		document.body.classList.remove('nous-pp-cartoes');
		escondeSugestoes(false);
	}
	function sobreTela() {   /* algo por cima da tela inicial? */
		return ['nous-wiz-ov', 'nous-pp-ov', 'nous-ag-ov', 'nous-em-ov', 'nous-sk-ov', 'nous-rp-ov', 'nous-pdf-ov', 'nous-ed-ov', 'nous-store-ov',
			'nous-dg-ov', 'nous-voice-ov', 'nous-cp-ov', 'nous-gal-ov', 'nous-dc-ov'].some(visible);
	}
	function tickCartoes() {
		var ini = document.getElementById('nous-ini');
		var querer = !!ini && naTela() && !sobreTela() && (forcarCartoes || modeloPronto()) && (forcarCartoes || (novato() && !P().visto('cartoes')));
		/* o passeio pela tela vem antes (uma fila so'): os cartoes esperam */
		if (querer && TOUR() && !forcarCartoes && (TOUR().ocupado() || TOUR().pendente())) querer = false;
		if (!querer) {
			if (cartoesEl) {
				/* a conversa comecou com os cartoes na tela: a pessoa ja' experimentou */
				if (!ini && /^\/c\//.test(location.pathname) && usou === null && P()) P().marcar('cartoes');
				tirarCartoes();
			}
			return;
		}
		if (cartoesEl && ini.nextElementSibling === cartoesEl) return;
		tirarCartoes();
		injectStyle();
		cartoesEl = document.createElement('div');
		cartoesEl.id = 'nous-pp-cartoes';
		cartoesEl.setAttribute('role', 'region');
		cartoesEl.setAttribute('aria-label', 'Exemplos para começar');
		cartoesEl.innerHTML = '<div class="tit"><span>Sem ideia do que pedir? Experimente um destes:</span><button type="button" data-x="x">Não mostrar mais</button></div><div class="grade">' +
			CARTOES.map(function (c, k) {
				return '<button type="button" class="nous-pp-card" data-k="' + k + '"><span class="ic" aria-hidden="true">' + c.i + '</span><span><b>' + esc(c.t) + '</b><span class="d">' + esc(c.d) + '</span></span></button>';
			}).join('') + '</div>';
		ini.insertAdjacentElement('afterend', cartoesEl);
		document.body.classList.add('nous-pp-cartoes');
		escondeSugestoes(true);
		cartoesEl.querySelector('[data-x=x]').addEventListener('click', function () {
			forcarCartoes = false;
			if (P()) P().marcar('cartoes');
			tirarCartoes();
			if (window.NousUI && window.NousUI.toast) window.NousUI.toast('Certo. Os exemplos continuam no botão ?.', { tipo: 'info' });
			var b = document.getElementById('nous-pp-aj'); if (b) b.focus();
		});
		[].forEach.call(cartoesEl.querySelectorAll('.nous-pp-card'), function (b) {
			b.addEventListener('click', function () {
				var c = CARTOES[+b.getAttribute('data-k')];
				[].forEach.call(cartoesEl.querySelectorAll('.nous-pp-card'), function (o) { o.classList.toggle('on', o === b); });
				if (preencher(c.p)) { usou = c; mostraCoach('pronto'); }
			});
		});
	}

	/* avisos acima da caixa de mensagem: 1) pedido pronto; 2) como ler a resposta */
	function removeCoach() { if (coach) { coach.remove(); coach = null; } if (cartoesEl) cartoesEl.classList.remove('escolheu'); }
	function posCoach() {
		var caixa = document.getElementById('message-input-container');
		if (!coach || !caixa || !coach.classList.contains('fixo')) return;
		var r = caixa.getBoundingClientRect();
		var w = Math.min(560, Math.max(260, r.width));
		coach.style.width = w + 'px';
		coach.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left + (r.width - w) / 2)) + 'px';
		coach.style.bottom = Math.max(8, window.innerHeight - r.top + 10) + 'px';
	}
	function mensagens() {
		return [].filter.call(document.querySelectorAll('[id^="message-"]'), function (e) { return e.id !== 'message-input-container'; });
	}
	/* "pronto": no lugar dos cartoes (nao tapa nada); "resposta": flutua acima da caixa de mensagem */
	function mostraCoach(qual) {
		removeCoach();
		injectStyle();
		coach = document.createElement('div');
		coach.id = 'nous-pp-coach';
		coach.setAttribute('role', 'region');
		coach.setAttribute('aria-live', 'polite');
		coach.setAttribute('aria-label', 'Dica da primeira conversa');
		coach.dataset.q = qual;
		if (qual === 'pronto' && cartoesEl) {
			coach.className = 'dentro';
			coach.innerHTML = '<div>Pronto: o pedido já está na caixa de mensagem, logo abaixo. Pode <b>trocar qualquer palavra</b>. Quando estiver bom, aperte <b>Enter</b> (ou o botão de enviar).</div>' +
				'<div class="r"><button type="button">Escolher outro exemplo</button></div>';
			cartoesEl.classList.add('escolheu');
			cartoesEl.appendChild(coach);
			coach.querySelector('button').addEventListener('click', function () {
				removeCoach();
				var b = cartoesEl && cartoesEl.querySelector('.nous-pp-card'); if (b) b.focus();
			});
			return;
		}
		/* na propria conversa, depois da ultima resposta: rola junto e nao tapa o texto */
		var ult = mensagens().pop();
		coach.className = ult ? 'dentro fluxo' : 'fixo';
		coach.dataset.n = mensagens().length;
		coach.innerHTML = '<div><b>Esta é a resposta.</b> Três coisas para lembrar:<ul>' +
			'<li>' + esc((usou && usou.e) || 'Leia com calma e confira o que for importante: a IA pode errar.') + '</li>' +
			'<li>Não gostou? Escreva <b>"mais curto"</b>, <b>"mais simples"</b> ou o que quiser mudar. Ela refaz.</li>' +
			'<li>Embaixo da resposta há botões para <b>copiar</b>, <b>ouvir</b> e <b>gerar de novo</b>.</li></ul></div>' +
			'<div class="r"><button type="button">Entendi</button></div>';
		coach.querySelector('button').addEventListener('click', function () {
			removeCoach();
			if (P()) P().marcar('cartoes');
			forcarCartoes = false; usou = null;
			var cx = document.getElementById('chat-input'); if (cx) cx.focus();
		});
		if (ult) ult.insertAdjacentElement('afterend', coach); else document.body.appendChild(coach);
		if (ult && coach.scrollIntoView) coach.scrollIntoView({ block: 'end', behavior: reduzido() ? 'auto' : 'smooth' });
		posCoach();
	}
	/* a resposta terminou? (sem o botao de parar e com os botoes de acao na ultima resposta) */
	function respostaPronta() {
		var parar = document.querySelector('#chat-container button[aria-label="Stop"], #chat-container button[aria-label="Parar"], button#stop-response-button');
		if (parar) return false;
		var texto = document.querySelector('#response-content-container, .chat-assistant');
		return !!texto && !!document.querySelector('.copy-response-button');
	}
	function tickCoach() {
		if (!coach) {
			/* conversa comecou a partir de um cartao: quando a resposta chegar, explica */
			if (usou && !document.getElementById('nous-ini') && /^\/c\//.test(location.pathname) && respostaPronta() &&
				!(TOUR() && TOUR().ocupado())) mostraCoach('resposta');
			return;
		}
		if (!document.contains(coach)) { coach = null; return; }   /* o bloco dos cartoes saiu junto */
		/* a pessoa mandou outra mensagem: o aviso cumpriu o papel */
		if (coach.dataset.q === 'resposta' && (!document.getElementById('message-input-container') || mensagens().length !== +coach.dataset.n)) {
			removeCoach();
			if (P()) P().marcar('cartoes');
			forcarCartoes = false; usou = null;
		}
		else posCoach();
	}

	/* ------------------------------------------------------------ ciclo */
	var depoisFeito = false;
	function tick() {
		montaAjuda();
		ajustaAjuda();
		detectaVeterano();
		consultaModelo();
		if (!depoisFeito && P() && P().carregado()) {
			var d = ''; try { d = sessionStorage.getItem('nous-pp-depois') || ''; } catch (e) {}
			if (d && document.getElementById('chat-input')) {
				depoisFeito = true;
				try { sessionStorage.removeItem('nous-pp-depois'); } catch (e) {}
				setTimeout(function () { executar(d); }, 800);
			}
		}
		if (document.getElementById('chat-input') || cartoesEl) tickCartoes();
		tickCoach();
	}

	window.NousPrimeiros = {
		licoes: licoes,
		/* o assistente de primeiro uso (nous-loader.js) mostra as licoes aqui? */
		deveMostrarLicoes: function () { return novato() && !P().visto('licoes'); },
		abrirLicoes: abrirLicoes, abrirMenu: abrirMenu,
		/* ha' algo meu na tela que um passeio nao deve atropelar? */
		ocupado: function () { return !!ov || !!coach; },
		novato: novato, modeloPronto: modeloPronto
	};

	function start() {
		injectStyle();
		setInterval(tick, 700);
		window.addEventListener('resize', function () { posCoach(); });
	}
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
