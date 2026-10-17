/* =====================================================================
   Nous - Documentos (v2.9). Escrever ao lado do chat: cartas, curriculos,
   trabalhos, posts. A IA propoe as mudancas (corrigir, deixar formal, mais
   curto, topicos -> texto, continuar ou o que voce pedir) e cada uma aparece
   riscada/sublinhada para voce aceitar ou recusar. Nada muda sem o seu OK.
   Selecione um trecho para mudar so' ele. Salva sozinho, guarda versoes e
   exporta para Word, PDF ou Markdown. Tudo pelo monitor (8990), local.

   Revisao: "2 de 7", setas ‹ ›, Enter aceita, Delete recusa, avanca sozinha
   e conclui quando tudo foi decidido (com Desfazer). Documento vazio mostra
   modelos prontos e "escrever com a IA" a partir de uma descricao.
   ===================================================================== */
(function () {
	'use strict';

	var MON = 'http://127.0.0.1:8990';
	var UI = window.NousUI || {};
	var esc = UI.esc || function (s) { return String(s || ''); };
	var ov = null, cur = null, saveTimer = null, review = null, busy = null, criando = false, docsCache = [];
	var compara = null;   /* {texto}: comparando uma versao antiga com o texto de agora */

	var CHIPS = [['corrigir', '✓ Corrigir portugues'], ['formal', '👔 Mais formal'], ['simples', '🙂 Mais simples'],
		['curto', '✂ Mais curto'], ['topicos', '¶ Topicos em texto'], ['organizar', '☰ Organizar com titulos'],
		['continuar', '➜ Continuar escrevendo']];

	/* Esqueletos prontos (sem IA): o usuario completa os [colchetes]. */
	var MODELOS = {
		carta: ['Carta formal', '[Cidade], [data]\n\nPrezado(a) [nome ou cargo],\n\nVenho por meio desta [motivo da carta].\n\n' +
			'[Explique a situacao em um ou dois paragrafos.]\n\nDesde ja, agradeco a atencao.\n\nAtenciosamente,\n\n[Seu nome]\n[Telefone ou e-mail]'],
		curriculo: ['Curriculo', '# [Seu nome completo]\n\n[Cidade - UF] · [telefone] · [e-mail]\n\n## Objetivo\n\n[Cargo ou area que procura]\n\n' +
			'## Experiencia\n\n- **[Cargo]** — [Empresa], [ano] a [ano]: [o que fazia e resultados]\n\n## Formacao\n\n- [Curso] — [Instituicao], [ano]\n\n' +
			'## Habilidades\n\n- [Habilidade]\n- [Idioma e nivel]'],
		email: ['E-mail profissional', 'Assunto: [assunto]\n\nOla, [nome],\n\n[Uma frase dizendo o motivo do e-mail.]\n\n[Detalhes ou pedido.]\n\n' +
			'Fico a disposicao.\n\nAbraco,\n[Seu nome]'],
		reclamacao: ['Reclamacao', '# Reclamacao — [empresa ou condominio]\n\n**Data:** [data]\n**Protocolo/contrato:** [numero, se houver]\n\n' +
			'## O que aconteceu\n\n[Conte os fatos, com datas.]\n\n## O que ja tentei\n\n[Contatos feitos e respostas.]\n\n## O que peco\n\n[Solucao esperada e prazo.]\n\n[Seu nome] · [contato]'],
		ata: ['Ata de reuniao', '# Ata de reuniao — [assunto]\n\n**Data:** [data] · **Local:** [local]\n**Presentes:** [nomes]\n\n' +
			'## Pauta\n\n1. [Item]\n\n## Decisoes\n\n- [Decisao]\n\n## Proximos passos\n\n- [Tarefa] — [responsavel], ate [data]']
	};

	var g = 'rgba(200,150,46,';

	function injectStyle() {
		if (document.getElementById('nous-dc-style')) return;
		var css =
			'#nous-docs-open{width:100%;margin-top:5px;padding:6px;border:1px solid ' + g + '.25);border-radius:8px;' +
			'cursor:pointer;background:transparent;color:#e7c069;font-weight:600;font-size:12px}#nous-docs-open:hover{background:' + g + '.12)}' +
			'#nous-dc-ov{position:fixed;inset:0;z-index:10001;background:rgba(0,0,0,.55);display:flex;align-items:center;' +
			'justify-content:center;backdrop-filter:blur(3px)}#nous-dc-ov.nous-hidden{display:none}' +
			'#nous-dc{position:relative;width:1040px;max-width:96vw;height:88vh;display:flex;flex-direction:column;font-family:Inter,system-ui,sans-serif;' +
			'font-size:13px;color:#eee;background:rgba(18,18,22,.97);border:1px solid ' + g + '.4);border-radius:16px;' +
			'box-shadow:0 16px 48px rgba(0,0,0,.55);overflow:hidden}' +
			'#nous-dc-head{display:flex;align-items:center;gap:8px;padding:12px 16px 10px;border-bottom:1px solid ' + g + '.15)}' +
			'#nous-dc-head .nous-dc-brand{flex:1;font:600 15px Cinzel,Georgia,serif;letter-spacing:.06em;color:#e7c069}' +
			'#nous-dc-menu{display:none;background:none;border:1px solid ' + g + '.35);border-radius:8px;color:#e7c069;padding:4px 9px;cursor:pointer}' +
			'#nous-dc-close{background:none;border:none;color:#888;cursor:pointer;font-size:19px}#nous-dc-close:hover{color:#eee}' +
			'#nous-dc-main{flex:1;display:flex;min-height:0}' +
			'#nous-dc-side{width:220px;flex-shrink:0;border-right:1px solid rgba(255,255,255,.07);display:flex;flex-direction:column;padding:10px;background:rgba(18,18,22,.99)}' +
			'#nous-dc-find{margin-top:8px;box-sizing:border-box;width:100%;padding:6px 9px;background:rgba(255,255,255,.06);' +
			'border:1px solid rgba(255,255,255,.1);border-radius:8px;color:#eee;font-size:12px;outline:none}#nous-dc-find:focus{border-color:' + g + '.5)}' +
			'#nous-dc-list{flex:1;overflow-y:auto;margin-top:8px}' +
			'.nous-dc-item{padding:7px 8px;border-radius:8px;cursor:pointer;margin-bottom:3px;position:relative;outline:none}' +
			'.nous-dc-item:hover,.nous-dc-item:focus-visible{background:rgba(255,255,255,.06)}.nous-dc-item.on{background:' + g + '.16)}' +
			'.nous-dc-item b{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding-right:16px}' +
			'.nous-dc-item small{font-size:10px;opacity:.55}' +
			'.nous-dc-del{position:absolute;right:4px;top:6px;background:none;border:none;color:#777;cursor:pointer;font-size:11px;opacity:0}' +
			'.nous-dc-item:hover .nous-dc-del,.nous-dc-del:focus{opacity:1}.nous-dc-del:hover{color:#f08080}' +
			'#nous-dc-doc{flex:1;display:flex;flex-direction:column;min-width:0;padding:10px 14px 10px}' +
			'#nous-dc-title{width:100%;box-sizing:border-box;background:transparent;border:none;border-bottom:1px solid rgba(255,255,255,.08);' +
			'color:#fff;font-size:18px;font-weight:700;padding:4px 2px 8px;outline:none}#nous-dc-title:focus{border-color:' + g + '.5)}' +
			'#nous-dc-bar{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:8px 0}' +
			'.nous-dc-seg{display:inline-flex;border:1px solid ' + g + '.4);border-radius:9px;overflow:hidden}' +
			'.nous-dc-seg button{border:none;border-radius:0;margin:0}.nous-dc-seg button+button{border-left:1px solid ' + g + '.25)}' +
			'.nous-dc-btn{padding:5px 10px;border:1px solid ' + g + '.4);border-radius:8px;cursor:pointer;background:' + g + '.14);' +
			'color:#e7c069;font-weight:600;font-size:12px;white-space:nowrap}.nous-dc-btn:hover{background:' + g + '.3)}' +
			'.nous-dc-btn.ghost{background:transparent}.nous-dc-btn:disabled{opacity:.4;cursor:default}' +
			'.nous-dc-btn.on{background:' + g + '.32)}.nous-dc-btn:focus-visible,.nous-dc-chip:focus-visible{outline:2px solid #e7c069;outline-offset:1px}' +
			'#nous-dc-fmt{display:inline-flex;gap:2px}#nous-dc-fmt button{min-width:28px;padding:4px 7px;border:1px solid transparent;border-radius:7px;' +
			'background:transparent;color:#cfcfcf;cursor:pointer;font:600 12px Inter,system-ui,sans-serif}' +
			'#nous-dc-fmt button:hover{border-color:' + g + '.35);color:#e7c069}' +
			'.nous-dc-sp{flex:1}' +
			'#nous-dc-sel{display:none;align-items:center;gap:8px;margin:-2px 0 7px;padding:5px 10px;border-radius:8px;font-size:12px;' +
			'background:' + g + '.1);border:1px dashed ' + g + '.45);color:#e7c069}#nous-dc-sel.on{display:flex}' +
			'#nous-dc-sel button{margin-left:auto;background:none;border:none;color:#e7c069;cursor:pointer;text-decoration:underline;font-size:11px}' +
			'#nous-dc-area{position:relative;flex:1;min-height:0;display:flex}' +
			'#nous-dc-text,#nous-dc-view,#nous-dc-rev{flex:1;min-height:0;box-sizing:border-box;width:100%;padding:14px 16px;border-radius:10px;' +
			'background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);color:#eee;font:14.5px/1.7 Inter,system-ui,sans-serif;overflow-y:auto}' +
			'#nous-dc-text{resize:none;outline:none}#nous-dc-text:focus{border-color:' + g + '.4)}' +
			'#nous-dc-rev{white-space:pre-wrap;word-wrap:break-word}' +
			/* sugestoes */
			'.nous-dc-sg{border-radius:4px;padding:1px 2px;cursor:pointer;transition:box-shadow .15s}' +
			'.nous-dc-sg del{color:#f39b9b;background:rgba(220,60,60,.15);text-decoration:line-through}' +
			'.nous-dc-sg ins{color:#7fe0a6;background:rgba(58,208,122,.15);text-decoration:none}' +
			'.nous-dc-sg.ok del,.nous-dc-sg.no ins{display:none}.nous-dc-sg.ok ins,.nous-dc-sg.no del{background:none;color:inherit;text-decoration:none}' +
			/* decidida: sem folga em volta e so' um sublinhado (verde aceita, cinza recusada) */
			'.nous-dc-sg.ok,.nous-dc-sg.no{padding:0;border-radius:0}.nous-dc-sg.ok{border-bottom:2px solid rgba(58,208,122,.45)}' +
			'.nous-dc-sg.no{border-bottom:2px dotted rgba(160,160,160,.45)}' +
			'.nous-dc-sg:not(.ok):not(.no){outline:1px dashed ' + g + '.5)}' +
			'.nous-dc-sg.atual{box-shadow:0 0 0 2px #e7c069,0 0 14px ' + g + '.45);outline:none!important}' +
			'.nous-dc-yn{display:inline-flex;gap:2px;margin:0 3px;vertical-align:1px}.nous-dc-sg.ok .nous-dc-yn,.nous-dc-sg.no .nous-dc-yn{display:none}' +
			'.nous-dc-yn button{border:none;border-radius:4px;cursor:pointer;font-size:10px;padding:1px 5px;font-weight:700}' +
			'.nous-dc-y{background:rgba(58,208,122,.25);color:#7fe0a6}.nous-dc-n{background:rgba(220,60,60,.22);color:#f39b9b}' +
			'#nous-dc-revbar{display:none;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px;padding:8px 10px;border-radius:10px;' +
			'background:' + g + '.1);border:1px solid ' + g + '.3);font-size:12px}#nous-dc-revbar.on{display:flex}' +
			'#nous-dc-revbar .nous-dc-rt{flex:1;min-width:150px}#nous-dc-revbar kbd{font:10px Inter,sans-serif;opacity:.6;margin-left:3px}' +
			'.nous-dc-nav{min-width:30px}' +
			'.nous-dc-cmp del,#nous-dc-revbar del{color:#f39b9b;background:rgba(220,60,60,.15)}' +
			'.nous-dc-cmp ins,#nous-dc-revbar ins{color:#7fe0a6;background:rgba(58,208,122,.15);text-decoration:underline}' +
			'#nous-dc-why{flex-basis:100%;margin-top:4px;padding:6px 9px;border-radius:8px;background:rgba(0,0,0,.25);color:#eee;font-size:12px;line-height:1.5}' +
			'#nous-dc-why small{opacity:.55}#nous-dc-why i{opacity:.7}' +
			/* IA escrevendo */
			'#nous-dc-busy{position:absolute;inset:0;display:none;align-items:center;justify-content:center;border-radius:10px;' +
			'background:rgba(14,14,18,.72);backdrop-filter:blur(1.5px)}#nous-dc-busy.on{display:flex}' +
			'#nous-dc-busy div{display:flex;flex-direction:column;align-items:center;gap:10px;padding:18px 24px;border-radius:14px;' +
			'background:rgba(18,18,22,.96);border:1px solid ' + g + '.45);text-align:center}' +
			'#nous-dc-busy b{font:600 14px Cinzel,Georgia,serif;letter-spacing:.05em;color:#e7c069}#nous-dc-busy small{opacity:.65}' +
			/* o texto chegando ao vivo, com o fim sempre a vista */
			'#nous-dc-live{width:min(560px,70vw);max-height:38vh;overflow-y:auto;margin:0;padding:10px 12px;border-radius:10px;text-align:left;' +
			'white-space:pre-wrap;word-wrap:break-word;font:13px/1.6 Inter,system-ui,sans-serif;color:#ddd;background:rgba(255,255,255,.04);' +
			'border:1px solid rgba(255,255,255,.08);-webkit-mask-image:linear-gradient(to bottom,transparent,#000 22px)}' +
			'.nous-dc-pulse{width:12px;height:12px;border-radius:50%;background:#e7c069;animation:nous-dc-p 1.2s ease-in-out infinite}' +
			'@keyframes nous-dc-p{0%,100%{opacity:.35;transform:scale(.8)}50%{opacity:1;transform:scale(1.15);box-shadow:0 0 14px #e7c069}}' +
			/* documento vazio */
			'#nous-dc-start{position:absolute;inset:0;display:none;overflow-y:auto;padding:22px;border-radius:10px;pointer-events:none}' +
			'#nous-dc-start.on{display:block}#nous-dc-start>*{pointer-events:auto}' +
			'#nous-dc-start h4{margin:0 0 4px;font:600 15px Cinzel,Georgia,serif;letter-spacing:.05em;color:#e7c069}' +
			'#nous-dc-start p{margin:0 0 14px;font-size:12px;opacity:.6}' +
			'.nous-dc-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px;max-width:640px}' +
			'.nous-dc-card{text-align:left;padding:11px 12px;border-radius:12px;border:1px solid ' + g + '.28);background:rgba(255,255,255,.03);' +
			'color:#eee;cursor:pointer;font:600 12.5px Inter,system-ui,sans-serif}.nous-dc-card:hover{border-color:' + g + '.6);background:' + g + '.08)}' +
			'.nous-dc-card small{display:block;margin-top:3px;font-weight:400;opacity:.55;font-size:11px}' +
			'.nous-dc-card.ia{border-color:' + g + '.55);background:' + g + '.1)}' +
			/* rodape */
			'#nous-dc-foot{display:flex;align-items:center;gap:10px;margin-top:6px;font-size:11px;opacity:.7}' +
			'#nous-dc-save{margin-left:auto;display:inline-flex;align-items:center;gap:5px}' +
			'#nous-dc-save i{width:7px;height:7px;border-radius:50%;background:#3ad07a;display:inline-block}' +
			'#nous-dc-save.pend i{background:#e7c069}#nous-dc-save.erro{color:#f08080}#nous-dc-save.erro i{background:#f08080}' +
			/* IA */
			'#nous-dc-ai{margin-top:8px;border-top:1px solid rgba(255,255,255,.07);padding-top:9px}' +
			'#nous-dc-chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:7px}' +
			'.nous-dc-chip{padding:4px 10px;border-radius:99px;border:1px solid ' + g + '.35);background:transparent;color:#e7c069;font-size:11px;cursor:pointer}' +
			'.nous-dc-chip:hover{background:' + g + '.18)}.nous-dc-chip:disabled{opacity:.4;cursor:default}' +
			'#nous-dc-askrow{display:flex;gap:6px;flex-wrap:wrap}' +
			'#nous-dc-ask,#nous-dc-model{box-sizing:border-box;padding:7px 10px;background:rgba(255,255,255,.07);border:1px solid ' + g + '.28);' +
			'border-radius:8px;color:#eee;font-size:12px;outline:none;color-scheme:dark}#nous-dc-ask{flex:1 1 220px;min-width:0}' +
			'#nous-dc-ask:focus{border-color:#c8962e}#nous-dc-model{max-width:150px}' +
			'#nous-dc-hint{font-size:11px;opacity:.5;margin-top:5px}' +
			'#nous-dc-view h1,#nous-dc-view h2,#nous-dc-view h3{color:#e7c069;margin:.6em 0 .3em}#nous-dc-view p{margin:.5em 0}' +
			'#nous-dc-view h1{font-family:Cinzel,Georgia,serif;letter-spacing:.03em}' +
			'#nous-dc-view blockquote{border-left:3px solid #c8962e;margin:.5em 0;padding-left:10px;opacity:.85}' +
			'#nous-dc-view a{color:#9db8ee}#nous-dc-view code{background:rgba(255,255,255,.08);padding:1px 4px;border-radius:4px}' +
			'.nous-dc-pop{position:absolute;z-index:4;background:rgba(24,24,28,.99);border:1px solid ' + g + '.4);border-radius:10px;' +
			'padding:6px;box-shadow:0 8px 24px rgba(0,0,0,.5);min-width:200px;max-width:340px;max-height:50vh;overflow-y:auto}' +
			'.nous-dc-pop button{display:block;width:100%;text-align:left;background:none;border:none;color:#eee;padding:7px 9px;border-radius:6px;cursor:pointer;font-size:12px}' +
			'.nous-dc-pop button:hover,.nous-dc-pop button:focus-visible{background:' + g + '.18);outline:none}.nous-dc-pop small{opacity:.55}' +
			'.nous-dc-empty{opacity:.55;font-size:12px;line-height:1.6;padding:10px 4px}' +
			'.nous-dc-bad{color:#f08080}' +
			'@media (max-width:760px){#nous-dc{height:94vh;max-width:100vw}#nous-dc-menu{display:block}' +
			'#nous-dc-side{display:none;position:absolute;z-index:5;top:49px;bottom:0;left:0;width:78%;background:#121216;box-shadow:8px 0 24px rgba(0,0,0,.6)}' +
			'#nous-dc.lista #nous-dc-side{display:flex}#nous-dc-fmt,#nous-dc-hint,.nous-dc-k{display:none}#nous-dc-doc{padding:8px 10px}}';
		var st = document.createElement('style');
		st.id = 'nous-dc-style';
		st.textContent = css;
		document.head.appendChild(st);
	}

	function ensureButton() {
		var body = document.getElementById('nous-mon-body');
		if (!body || document.getElementById('nous-docs-open')) return;
		var b = document.createElement('button');
		b.id = 'nous-docs-open';
		b.type = 'button';
		b.textContent = '📝 Documentos';
		b.addEventListener('click', function () { open(); });
		body.appendChild(b);
	}

	function $(sel) { return ov.querySelector(sel); }
	function toast(t, op) { if (UI.toast) UI.toast(t, op); }
	function confirmar(t, op) { return UI.confirmar ? UI.confirmar(t, op) : Promise.resolve(window.confirm(t)); }

	function build() {
		if (ov && document.body.contains(ov)) return;
		ov = document.createElement('div');
		ov.id = 'nous-dc-ov';
		ov.className = 'nous-hidden';
		ov.innerHTML = '<div id="nous-dc" role="dialog" aria-label="Documentos"><div id="nous-dc-head">' +
			'<button id="nous-dc-menu" type="button" aria-label="Meus documentos">☰</button>' +
			'<span class="nous-dc-brand">📝 Documentos</span>' +
			'<button id="nous-dc-close" type="button" aria-label="Fechar">&#x2715;</button></div>' +
			'<div id="nous-dc-main"><div id="nous-dc-side">' +
			'<button class="nous-dc-btn" id="nous-dc-new" type="button">+ Novo documento</button>' +
			'<label class="nous-dc-btn ghost" style="margin-top:5px;text-align:center">📂 Abrir arquivo' +
			'<input id="nous-dc-file" type="file" accept=".txt,.md,.markdown,.docx,.pdf,.html,.htm" style="display:none"></label>' +
			'<input id="nous-dc-find" type="search" placeholder="🔎 Procurar documento" style="display:none">' +
			'<div id="nous-dc-list"></div></div>' +
			'<div id="nous-dc-doc"><input id="nous-dc-title" placeholder="Titulo do documento" maxlength="120">' +
			'<div id="nous-dc-bar">' +
			'<span class="nous-dc-seg"><button class="nous-dc-btn ghost on" id="nous-dc-mode-w" type="button">✍ Escrever</button>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-mode-v" type="button">👁 Ver como fica</button></span>' +
			'<span id="nous-dc-fmt"><button type="button" data-fmt="b" title="Negrito (Ctrl+B)"><b>B</b></button>' +
			'<button type="button" data-fmt="i" title="Italico (Ctrl+I)"><i>I</i></button>' +
			'<button type="button" data-fmt="h" title="Titulo">T</button>' +
			'<button type="button" data-fmt="ul" title="Lista">•</button>' +
			'<button type="button" data-fmt="ol" title="Lista numerada">1.</button></span>' +
			'<span class="nous-dc-sp"></span>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-exp" type="button" aria-haspopup="menu">⬇ Baixar ▾</button>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-vers" type="button" aria-haspopup="menu">🕘 Versoes</button>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-chat" type="button">💬 Usar no chat</button></div>' +
			'<div id="nous-dc-sel"><span></span><button type="button">usar o texto todo</button></div>' +
			'<div id="nous-dc-revbar" role="toolbar" aria-label="Sugestoes da IA"></div>' +
			'<div id="nous-dc-area">' +
			'<textarea id="nous-dc-text" spellcheck="true" lang="pt-BR" aria-label="Texto do documento"></textarea>' +
			'<div id="nous-dc-view" style="display:none"></div><div id="nous-dc-rev" style="display:none" tabindex="-1"></div>' +
			'<div id="nous-dc-start"></div>' +
			'<div id="nous-dc-busy" aria-live="polite"><div><span class="nous-dc-pulse"></span><b id="nous-dc-busyb">A IA esta escrevendo</b>' +
			'<small id="nous-dc-busyt"></small><pre id="nous-dc-live" aria-hidden="true"></pre>' +
			'<button class="nous-dc-btn ghost" id="nous-dc-cancel" type="button">Cancelar</button></div></div>' +
			'</div>' +
			'<div id="nous-dc-foot"><span id="nous-dc-stats"></span><span id="nous-dc-msg"></span>' +
			'<span id="nous-dc-save" aria-live="polite"></span></div>' +
			'<div id="nous-dc-ai"><div id="nous-dc-chips" role="group" aria-label="Pedidos prontos para a IA"></div>' +
			'<div id="nous-dc-askrow"><input id="nous-dc-ask" placeholder="Ou diga o que mudar: &quot;troque voce por senhor&quot;, &quot;deixe mais animado&quot;...">' +
			'<select id="nous-dc-model" title="Modelo que escreve" aria-label="Modelo que escreve"></select>' +
			'<button class="nous-dc-btn" id="nous-dc-go" type="button">✨ Pedir a IA</button></div>' +
			'<div id="nous-dc-hint">A IA so\' sugere: voce aceita ou recusa cada mudanca. <span class="nous-dc-k">Ctrl+S guarda uma versao.</span></div>' +
			'</div></div></div></div>';
		document.body.appendChild(ov);
		ov.addEventListener('click', function (e) { if (e.target === ov) close(); });
		$('#nous-dc-close').addEventListener('click', close);
		$('#nous-dc-menu').addEventListener('click', function () { $('#nous-dc').classList.toggle('lista'); });
		$('#nous-dc-new').addEventListener('click', function () { $('#nous-dc').classList.remove('lista'); novo('', ''); });
		$('#nous-dc-file').addEventListener('change', function (e) {
			var f = e.target.files && e.target.files[0];
			e.target.value = '';
			if (f) importar(f);
		});
		$('#nous-dc-find').addEventListener('input', function () { pintarLista(); });
		$('#nous-dc-title').addEventListener('input', agendarSalvar);
		var ta = $('#nous-dc-text');
		ta.addEventListener('input', function () { agendarSalvar(); contar(); vazio(); });
		['select', 'keyup', 'mouseup', 'blur'].forEach(function (ev) { ta.addEventListener(ev, selecao); });
		ta.addEventListener('keydown', atalhosTexto);
		$('#nous-dc-sel button').addEventListener('click', function () {
			ta.setSelectionRange(ta.selectionEnd, ta.selectionEnd);
			selecao();
			ta.focus();
		});
		$('#nous-dc-fmt').addEventListener('click', function (e) {
			var b = e.target.closest('[data-fmt]');
			if (b) formatar(b.getAttribute('data-fmt'));
		});
		$('#nous-dc-mode-w').addEventListener('click', function () { modo('w'); });
		$('#nous-dc-mode-v').addEventListener('click', function () { modo('v'); });
		$('#nous-dc-exp').addEventListener('click', function (e) { menuExportar(e.currentTarget); });
		$('#nous-dc-vers').addEventListener('click', function (e) { menuVersoes(e.currentTarget); });
		$('#nous-dc-chat').addEventListener('click', usarNoChat);
		$('#nous-dc-cancel').addEventListener('click', cancelar);
		$('#nous-dc-chips').innerHTML = CHIPS.map(function (c) {
			return '<button class="nous-dc-chip" type="button" data-k="' + c[0] + '">' + c[1] + '</button>';
		}).join('');
		$('#nous-dc-chips').addEventListener('click', function (e) {
			var b = e.target.closest('[data-k]');
			if (b) pedir(b.getAttribute('data-k'), b.textContent);
		});
		$('#nous-dc-go').addEventListener('click', function () {
			var t = $('#nous-dc-ask').value.trim();
			if (t) pedir(t, t);
			else $('#nous-dc-ask').focus();
		});
		$('#nous-dc-ask').addEventListener('keydown', function (e) {
			if (e.key === 'Enter' && this.value.trim()) pedir(this.value.trim(), this.value.trim());
		});
		$('#nous-dc-model').addEventListener('change', function () {
			try { localStorage.setItem('nous-docs-model', this.value); } catch (e) {}
		});
		$('#nous-dc-start').addEventListener('click', function (e) {
			var b = e.target.closest('[data-mod]');
			if (!b) return;
			var k = b.getAttribute('data-mod');
			if (k === 'ia') {
				var ask = $('#nous-dc-ask');
				ask.placeholder = 'Descreva o que precisa: "carta pedindo reembolso de uma passagem cancelada"...';
				ask.focus();
				return;
			}
			if (k === 'arquivo') { $('#nous-dc-file').click(); return; }
			if (!$('#nous-dc-title').value.trim()) $('#nous-dc-title').value = MODELOS[k][0];
			ta.value = MODELOS[k][1];
			ta.focus();
			var p = ta.value.indexOf('[');
			if (p >= 0) ta.setSelectionRange(p, ta.value.indexOf(']', p) + 1);
			agendarSalvar(); contar(); vazio(); selecao();
		});
		document.addEventListener('keydown', teclas, true);
	}

	/* ---------------------------------------------------------- teclado */
	function teclas(e) {
		if (!ov || ov.classList.contains('nous-hidden') || document.getElementById('nous-cf-ov')) return;
		if (e.key === 'Escape') {
			if (document.querySelector('.nous-dc-pop')) { fecharPops(); e.stopPropagation(); return; }
			if ($('#nous-dc').classList.contains('lista')) { $('#nous-dc').classList.remove('lista'); e.stopPropagation(); return; }
			if (busy) { cancelar(); e.stopPropagation(); return; }
			if (compara) { fecharComparacao(); e.stopPropagation(); return; }
			e.stopPropagation();
			close();
			return;
		}
		if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 's') {
			e.preventDefault();
			if (!review) salvarAgora('salvo por voce', function () { toast('Versao guardada.'); });
			return;
		}
		if (!review) return;
		var t = e.target;
		if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return;
		if (e.key === 'Enter' || e.key === 'a' || e.key === 'A') { e.preventDefault(); decidir(review.atual, true); }
		else if (e.key === 'Delete' || e.key === 'Backspace' || e.key === 'r' || e.key === 'R') { e.preventDefault(); decidir(review.atual, false); }
		else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); ir(1); }
		else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); ir(-1); }
		else if (e.key === '?') { e.preventDefault(); porque(); }
	}

	function atalhosTexto(e) {
		if (!(e.ctrlKey || e.metaKey) || e.altKey) return;  /* AltGr = Ctrl+Alt no teclado ABNT */
		var k = e.key.toLowerCase();
		if (k === 'b' || k === 'i') { e.preventDefault(); formatar(k); }
	}

	/* -------------------------------------------------------- abrir/fechar */
	/* id: abre esse documento; false: nao abre nenhum sozinho (quem chamou abre) */
	function open(id) {
		build();
		ov.classList.remove('nous-hidden');
		carregarModelos();
		listar(function (docs) {
			if (id) abrir(id);
			else if (id !== false && !cur) {
				if (docs.length) abrir(docs[0].id);
				else novo('', '');
			}
		});
	}

	function close() {
		if (review) {
			confirmar('As sugestoes que voce nao decidiu sao descartadas e o texto fica como estava.',
				{ titulo: 'Fechar sem decidir?', ok: 'Fechar' }).then(function (sim) {
				if (sim) { review = null; fechar(); }
			});
			return;
		}
		fechar();
	}

	function fechar() {
		if (busy) cancelar();
		compara = null;
		salvarAgora();
		fecharPops();
		$('#nous-dc').classList.remove('lista');
		ov.classList.add('nous-hidden');
	}

	/* ------------------------------------------------------------- estado */
	function msg(t, bad) {
		var s = $('#nous-dc-msg');
		s.textContent = t || '';
		s.classList.toggle('nous-dc-bad', !!bad);
		if (bad && t) toast(t, { tipo: 'erro' });
	}

	function salvo(estado) {
		var s = $('#nous-dc-save');
		var txt = { ok: 'Salvo', pend: 'Salvando...', edit: 'Alteracoes nao salvas', erro: 'Nao salvou (o Nous esta aberto?)' }[estado] || '';
		s.className = estado === 'ok' ? '' : estado === 'erro' ? 'erro' : 'pend';
		s.innerHTML = txt ? '<i></i>' + txt : '';
	}

	function contar() {
		var t = $('#nous-dc-text').value, n = (t.match(/[\wÀ-ÿ]+/g) || []).length;
		$('#nous-dc-stats').textContent = n ? n + ' palavra' + (n === 1 ? '' : 's') + ' · ' +
			Math.max(1, Math.round(n / 200)) + ' min de leitura' : '';
	}

	/* Documento vazio: modelos prontos e "escrever com a IA". */
	function vazio() {
		var st = $('#nous-dc-start'), on = !review && $('#nous-dc-text').style.display !== 'none' && !$('#nous-dc-text').value.trim();
		if (on && !st.innerHTML) {
			st.innerHTML = '<h4>Comece de um jeito facil</h4><p>Escreva direto aqui, escolha um modelo ou deixe a IA fazer o primeiro rascunho.</p>' +
				'<div class="nous-dc-cards"><button class="nous-dc-card ia" type="button" data-mod="ia">✨ Escrever com a IA' +
				'<small>Descreva o que precisa e revise o rascunho</small></button>' +
				Object.keys(MODELOS).map(function (k) {
					return '<button class="nous-dc-card" type="button" data-mod="' + k + '">' + esc(MODELOS[k][0]) + '<small>Modelo para completar</small></button>';
				}).join('') +
				'<button class="nous-dc-card" type="button" data-mod="arquivo">📂 Abrir arquivo<small>Word, PDF, texto ou Markdown</small></button></div>';
		}
		st.classList.toggle('on', on);
	}

	function selecao() {
		var ta = $('#nous-dc-text'), box = $('#nous-dc-sel');
		var s = ta.value.slice(ta.selectionStart, ta.selectionEnd);
		var n = (s.match(/[\wÀ-ÿ]+/g) || []).length;
		var on = !review && document.activeElement !== null && n > 0 && ta.style.display !== 'none';
		box.classList.toggle('on', on);
		if (on) box.querySelector('span').textContent = '✂ Trecho selecionado (' + n + ' palavra' + (n === 1 ? '' : 's') + '): a IA mexe so\' nele.';
	}

	function quando(ts) {
		var d = new Date(ts * 1000), hoje = new Date();
		if (d.toDateString() === hoje.toDateString()) return 'hoje ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
		return d.toLocaleDateString('pt-BR');
	}

	/* -------------------------------------------------------------- lista */
	function listar(cb) {
		fetch(MON + '/docs', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
			docsCache = d.docs || [];
			pintarLista();
			if (cb) cb(docsCache);
		}).catch(function () {
			$('#nous-dc-list').innerHTML = '<div class="nous-dc-empty nous-dc-bad">O monitor do Nous nao esta no ar. Abra o Nous pelo atalho.</div>';
			if (cb) cb([]);
		});
	}

	function sem(s) { return String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, ''); }

	function pintarLista() {
		var find = $('#nous-dc-find'), q = sem(find.value.trim()), box = $('#nous-dc-list');
		find.style.display = docsCache.length >= 6 || q ? '' : 'none';
		var docs = docsCache.filter(function (x) { return !q || sem(x.titulo + ' ' + x.inicio).indexOf(q) >= 0; });
		box.innerHTML = docs.length ? docs.map(function (x) {
			return '<div class="nous-dc-item' + (cur && cur.id === x.id ? ' on' : '') + '" tabindex="0" role="button" data-id="' + esc(x.id) +
				'" title="' + esc(x.inicio) + '"><b>' + esc(x.titulo) + '</b><small>' + quando(x.atualizado) + ' · ' + x.palavras + ' palavras</small>' +
				'<button class="nous-dc-del" type="button" title="Apagar" aria-label="Apagar ' + esc(x.titulo) + '" data-del="' + esc(x.id) + '">🗑</button></div>';
		}).join('') : '<div class="nous-dc-empty">' + (q ? 'Nenhum documento com "' + esc(find.value.trim()) + '".' :
			'Nenhum documento ainda.<br>Comece por "+ Novo documento", abra um arquivo ou use o 📝 nas respostas do chat.') + '</div>';
		box.querySelectorAll('[data-id]').forEach(function (el) {
			function vai(e) {
				if (e.target.closest('[data-del]')) return;
				if (review) { msg('Decida as sugestoes primeiro.', true); return; }
				salvarAgora();
				$('#nous-dc').classList.remove('lista');
				abrir(el.getAttribute('data-id'));
			}
			el.addEventListener('click', vai);
			el.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); vai(e); } });
		});
		box.querySelectorAll('[data-del]').forEach(function (b) {
			b.addEventListener('click', function () {
				var id = b.getAttribute('data-del'), x = docsCache.filter(function (d) { return d.id === id; })[0] || {};
				confirmar('"' + (x.titulo || 'Documento') + '" e as versoes dele somem do computador. Nao da para desfazer.',
					{ titulo: 'Apagar documento?', ok: 'Apagar', perigo: true }).then(function (sim) {
					if (!sim) return;
					fetch(MON + '/docs/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: id }) })
						.then(function () {
							toast('Documento apagado.');
							if (cur && cur.id === id) cur = null;
							listar(function (ds) { if (!cur) { if (ds.length) abrir(ds[0].id); else novo('', ''); } });
						});
				});
			});
		});
	}

	function mostrar(doc) {
		cur = doc;
		review = null;
		compara = null;
		$('#nous-dc-title').value = doc.titulo === 'Sem titulo' ? '' : (doc.titulo || '');
		$('#nous-dc-text').value = doc.texto || '';
		modo('w');
		salvo(doc.id ? 'ok' : '');
		msg('');
		contar();
		vazio();
		selecao();
		ov.querySelectorAll('.nous-dc-item').forEach(function (el) { el.classList.toggle('on', el.getAttribute('data-id') === doc.id); });
	}

	function abrir(id) {
		fetch(MON + '/docs/get?id=' + encodeURIComponent(id), { cache: 'no-store' }).then(function (r) { return r.json(); })
			.then(function (d) { if (!d.error) mostrar(d); });
	}

	/* Documento novo (tambem usado pelo chat: "📝 Documento"). */
	function novo(titulo, texto) {
		if (review) { msg('Decida as sugestoes primeiro.', true); return; }
		salvarAgora();
		mostrar({ id: '', titulo: titulo || '', texto: texto || '', versoes: [] });
		if (texto) salvarAgora();
		setTimeout(function () { (titulo ? $('#nous-dc-text') : $('#nous-dc-title')).focus(); }, 50);
	}

	/* ------------------------------------------------------------- salvar */
	function agendarSalvar() {
		if (!cur) return;
		salvo('edit');
		clearTimeout(saveTimer);
		saveTimer = setTimeout(function () { salvarAgora(); }, 1000);
	}

	/* motivo: tira uma foto da versao anterior (antes da IA, de restaurar...) */
	function salvarAgora(motivo, cb) {
		clearTimeout(saveTimer);
		saveTimer = null;
		if (!cur || review) { if (cb) cb(); return; }
		if (criando) { saveTimer = setTimeout(function () { salvarAgora(motivo, cb); }, 400); return; }
		var titulo = $('#nous-dc-title').value.trim(), texto = $('#nous-dc-text').value;
		if (!cur.id && !texto.trim() && !titulo) { if (cb) cb(); return; }
		if (cur.id && !motivo && titulo === (cur.titulo === 'Sem titulo' ? '' : cur.titulo) && texto === cur.texto) {
			salvo('ok');
			if (cb) cb();
			return;
		}
		var novoDoc = !cur.id, alvo = cur;
		criando = novoDoc;  /* sem id ainda: outro salvar agora criaria um segundo documento */
		cur.titulo = titulo || 'Sem titulo';
		cur.texto = texto;
		salvo('pend');
		fetch(MON + '/docs/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ id: cur.id, titulo: titulo, texto: texto, motivo: motivo || '' }) })
			.then(function (r) { return r.json(); }).then(function (d) {
				if (d.error) throw new Error(d.error);
				alvo.id = d.id;
				alvo.versoes = d.versoes;
				if (alvo === cur) salvo('ok');
				if (novoDoc || motivo) listar();
			}).catch(function () { salvo('erro'); })
			.then(function () { criando = false; if (cb) cb(); });
	}

	function modo(m) {
		if (review && m !== 'r') return;
		$('#nous-dc-text').style.display = m === 'w' ? '' : 'none';
		$('#nous-dc-view').style.display = m === 'v' ? '' : 'none';
		$('#nous-dc-rev').style.display = m === 'r' ? '' : 'none';
		$('#nous-dc-revbar').classList.toggle('on', m === 'r');
		$('#nous-dc-fmt').style.visibility = m === 'w' ? '' : 'hidden';
		$('#nous-dc-mode-w').classList.toggle('on', m === 'w');
		$('#nous-dc-mode-v').classList.toggle('on', m === 'v');
		['#nous-dc-mode-w', '#nous-dc-mode-v', '#nous-dc-exp', '#nous-dc-vers', '#nous-dc-chat', '#nous-dc-go']
			.forEach(function (s) { $(s).disabled = m === 'r'; });
		ov.querySelectorAll('.nous-dc-chip').forEach(function (b) { b.disabled = m === 'r'; });
		if (m === 'v') $('#nous-dc-view').innerHTML = markdown($('#nous-dc-text').value) || '<p style="opacity:.5">Documento vazio.</p>';
		vazio();
		selecao();
	}

	/* ------------------------------------------------------- formatacao */
	function formatar(f) {
		var ta = $('#nous-dc-text'), v = ta.value, a = ta.selectionStart, b = ta.selectionEnd;
		var sel = v.slice(a, b), novoTxt, ca, cb;
		if (f === 'b' || f === 'i') {
			var m = f === 'b' ? '**' : '*';
			var dentro = sel || (f === 'b' ? 'texto em negrito' : 'texto em italico');
			novoTxt = m + dentro + m;
			ca = a + m.length; cb = ca + dentro.length;
		} else {
			/* titulo e listas valem para as linhas inteiras da selecao */
			var ini = v.lastIndexOf('\n', a - 1) + 1, fim = v.indexOf('\n', b);
			if (fim < 0) fim = v.length;
			a = ini; b = fim;
			var linhas = v.slice(ini, fim).split('\n');
			novoTxt = linhas.map(function (l, i) {
				var limpa = l.replace(/^(#{1,3}\s+|[-*•]\s+|\d+[.)]\s+)/, '');
				if (f === 'h') return '## ' + limpa;
				if (f === 'ul') return '- ' + limpa;
				return (i + 1) + '. ' + limpa;
			}).join('\n');
			ca = a; cb = a + novoTxt.length;
		}
		ta.focus();
		ta.setRangeText(novoTxt, a, b, 'end');
		ta.setSelectionRange(ca, cb);
		ta.dispatchEvent(new Event('input', { bubbles: true }));
	}

	/* Markdown minimo e seguro para "Ver como fica": escapa tudo antes. */
	function inline(s) {
		return esc(s)
			.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>')
			.replace(/`([^`]+)`/g, '<code>$1</code>')
			.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s"]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
	}
	function markdown(md) {
		var out = [], list = null, para = [];
		function flush() {
			if (para.length) { out.push('<p>' + para.map(inline).join('<br>') + '</p>'); para = []; }
			if (list) { out.push('</' + list + '>'); list = null; }
		}
		(md || '').split('\n').forEach(function (ln) {
			var m;
			if (!ln.trim()) { flush(); return; }
			if ((m = ln.match(/^(#{1,3})\s+(.*)$/))) { flush(); out.push('<h' + m[1].length + '>' + inline(m[2]) + '</h' + m[1].length + '>'); return; }
			if (/^(-{3,}|\*{3,})\s*$/.test(ln)) { flush(); out.push('<hr>'); return; }
			if ((m = ln.match(/^>\s?(.*)$/))) { flush(); out.push('<blockquote>' + inline(m[1]) + '</blockquote>'); return; }
			if ((m = ln.match(/^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/))) {
				var tag = m[1] ? 'ol' : 'ul';
				if (para.length) { out.push('<p>' + para.map(inline).join('<br>') + '</p>'); para = []; }
				if (list !== tag) { if (list) out.push('</' + list + '>'); out.push('<' + tag + '>'); list = tag; }
				out.push('<li>' + inline(m[2]) + '</li>');
				return;
			}
			if (list) { out.push('</' + list + '>'); list = null; }
			para.push(ln);
		});
		flush();
		return out.join('');
	}

	/* ------------------------------------------------------------- modelos */
	function carregarModelos() {
		fetch(MON + '/installed', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (d) {
			var sel = $('#nous-dc-model'), pref = '';
			try { pref = localStorage.getItem('nous-docs-model') || ''; } catch (e) {}
			var chat = (d.chat || []).filter(function (n) { return !/[-:]cloud$/i.test(n); });
			sel.innerHTML = chat.length ? chat.map(function (n) {
				return '<option' + (n === pref ? ' selected' : '') + '>' + esc(n) + '</option>';
			}).join('') : '<option value="">(nenhum modelo)</option>';
		}).catch(function () {});
	}

	/* ------------------------------------------------------------------ IA */
	function travar(on) {
		ov.querySelectorAll('.nous-dc-chip, #nous-dc-go').forEach(function (b) { b.disabled = on; });
	}

	function pedir(instrucao, rotulo) {
		if (busy || review) return;
		fecharComparacao();
		var ta = $('#nous-dc-text');
		if ($('#nous-dc-view').style.display !== 'none') modo('w');
		var texto = ta.value, ini = ta.selectionStart, fim = ta.selectionEnd;
		var sel = fim > ini && texto.slice(ini, fim).trim();
		var atalho = CHIPS.some(function (c) { return c[0] === instrucao; });
		if (!texto.trim() && atalho) {
			msg('O documento esta vazio. Escreva algo ou diga, no campo de baixo, o que a IA deve escrever.', true);
			$('#nous-dc-ask').focus();
			return;
		}
		var ctrl = window.AbortController ? new AbortController() : null, t0 = Date.now();
		busy = { ctrl: ctrl, timer: null, fase: 'espera', vivo: '' };
		var rot = !texto.trim() ? 'Rascunho da IA' : rotulo;
		$('#nous-dc-busy').classList.add('on');
		$('#nous-dc-live').textContent = '';
		$('#nous-dc-live').style.display = 'none';
		function tick() {
			var s = Math.round((Date.now() - t0) / 1000);
			$('#nous-dc-busyb').textContent = busy.fase === 'pensa' ? 'A IA esta pensando' : busy.fase === 'escreve' ? 'A IA esta escrevendo' : 'Preparando o modelo';
			$('#nous-dc-busyt').textContent = (sel ? 'So\' no trecho selecionado · ' : '') + s + ' s' +
				(s > 20 && busy.fase !== 'escreve' ? ' — modelos locais levam ate\' um minuto' : '');
		}
		tick();
		busy.tick = tick;
		busy.timer = setInterval(tick, 500);
		travar(true);
		msg('');
		var body = { texto: texto, instrucao: instrucao, model: $('#nous-dc-model').value, stream: true };
		if (sel) { body.ini = ini; body.fim = fim; }
		var meu = busy;
		fetch(MON + '/docs/ai', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
			signal: ctrl ? ctrl.signal : undefined })
			.then(function (r) {
				if (!r.ok || !r.body || !r.body.getReader) return r.json();
				return lerAoVivo(r, meu);
			}).then(function (d) {
				if (busy !== meu) return;  /* cancelado */
				if (d.error) throw new Error(d.error);
				if (ta.value !== texto) throw new Error('Voce mudou o texto enquanto a IA escrevia. Peca de novo.');
				if (!d.mudancas) { toast('A IA nao sugeriu nenhuma mudanca.', { tipo: 'info' }); return; }
				$('#nous-dc-ask').value = '';
				fimBusy();
				mostrarSugestoes(d, rot);
			}).catch(function (e) {
				if (busy !== meu || (e && e.name === 'AbortError')) return;
				msg(e.message || 'A IA nao respondeu.', true);
			}).then(function () { if (busy === meu) fimBusy(); });
	}

	/* NDJSON do monitor: {"p": n} pensando, {"d": pedaco} texto ao vivo,
	 * {"fim": {...}} pronto ou {"erro": "..."}. Resolve com o mesmo formato
	 * da resposta sem stream ({segs, mudancas} ou {error}). */
	function lerAoVivo(r, meu) {
		var leitor = r.body.getReader(), dec = new TextDecoder(), resto = '', fim = null;
		var live = $('#nous-dc-live');
		function linha(l) {
			if (!l.trim()) return;
			var o;
			try { o = JSON.parse(l); } catch (e) { return; }
			if (busy !== meu) return;
			var antes = busy.fase;
			if (o.p && busy.fase !== 'escreve') busy.fase = 'pensa';
			if (o.d) busy.fase = 'escreve';
			if (busy.fase !== antes && busy.tick) busy.tick();
			if (o.d) {
				busy.vivo += o.d;
				live.style.display = '';
				/* qwen3 e parecidos: o que vem antes do </think> e' raciocinio */
				var t = busy.vivo.indexOf('</think>') >= 0 ? busy.vivo.split('</think>').pop() : busy.vivo.replace(/^<think>[\s\S]*/, '');
				live.textContent = t.trimStart();
				live.scrollTop = live.scrollHeight;
			}
			if (o.fim) fim = o.fim;
			if (o.erro) fim = { error: o.erro };
		}
		function le() {
			return leitor.read().then(function (p) {
				if (p.done) {
					linha(resto);
					return fim || { error: 'A conexao com o monitor caiu. Tente de novo.' };
				}
				var partes = (resto + dec.decode(p.value, { stream: true })).split('\n');
				resto = partes.pop();
				partes.forEach(linha);
				return le();
			});
		}
		return le();
	}

	function fimBusy() {
		if (busy && busy.timer) clearInterval(busy.timer);
		busy = null;
		$('#nous-dc-busy').classList.remove('on');
		if (!review) travar(false);
	}

	function cancelar() {
		if (!busy) return;
		if (busy.ctrl) busy.ctrl.abort();
		fimBusy();
		toast('Pedido cancelado.', { tipo: 'info' });
	}

	/* ------------------------------------------------------------ revisao */
	function idxs() {
		var out = [];
		review.segs.forEach(function (s, i) { if (s.t === '~') out.push(i); });
		return out;
	}

	function mostrarSugestoes(d, rotulo) {
		review = { segs: d.segs, rotulo: rotulo, dec: {}, atual: null, antes: $('#nous-dc-text').value, porque: {} };
		var box = $('#nous-dc-rev'), html = '';
		d.segs.forEach(function (s, i) {
			if (s.t === '=') { html += esc(s.s); return; }
			html += '<span class="nous-dc-sg" data-i="' + i + '" title="Clique para alternar">' +
				(s.a ? '<del>' + esc(s.a) + '</del>' : '') + (s.b ? '<ins>' + esc(s.b) + '</ins>' : '') +
				'<span class="nous-dc-yn"><button class="nous-dc-y" type="button" data-ok="' + i + '" title="Aceitar (Enter)" aria-label="Aceitar">✓</button>' +
				'<button class="nous-dc-n" type="button" data-no="' + i + '" title="Recusar (Delete)" aria-label="Recusar">✕</button></span></span>';
		});
		box.innerHTML = html;
		box.onclick = function (e) {
			var b = e.target.closest('[data-ok],[data-no]'), sg = e.target.closest('.nous-dc-sg');
			if (!sg) return;
			var i = +sg.getAttribute('data-i');
			if (b) decidir(i, b.hasAttribute('data-ok'));
			else if (review.dec[i] !== undefined) decidir(i, !review.dec[i], true);
			else focar(i);
		};
		modo('r');
		msg('');
		focar(idxs()[0]);
		box.focus({ preventScroll: true });
	}

	function focar(i) {
		if (!review || i === undefined || i === null) return;
		review.atual = i;
		ov.querySelectorAll('.nous-dc-sg.atual').forEach(function (el) { el.classList.remove('atual'); });
		var el = $('.nous-dc-sg[data-i="' + i + '"]');
		if (el) {
			el.classList.add('atual');
			el.scrollIntoView({ block: 'center', behavior: 'smooth' });
		}
		barra();
	}

	function ir(passo) {
		var l = idxs(), p = l.indexOf(review.atual);
		focar(l[Math.max(0, Math.min(l.length - 1, (p < 0 ? 0 : p) + passo))]);
	}

	/* "Por que?": regra para acento/pontuacao/maiuscula; o modelo explica o resto */
	function porque() {
		if (!review || review.atual === null) return;
		var i = review.atual, r = review, s = r.segs[i];
		if (r.porque[i] && !r.porque[i].erro) return;
		var ctx = '';
		for (var k = i - 1; k >= 0 && ctx.length < 160; k--) ctx = (r.segs[k].t === '=' ? r.segs[k].s : r.segs[k].a) + ctx;
		ctx = ctx.slice(-160) + (s.a || '') + (r.segs[i + 1] && r.segs[i + 1].t === '=' ? r.segs[i + 1].s.slice(0, 160) : '');
		r.porque[i] = { carregando: true };
		barra();
		fetch(MON + '/docs/porque', { method: 'POST', headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ antes: s.a, depois: s.b, contexto: ctx, model: $('#nous-dc-model').value }) })
			.then(function (x) { return x.json(); }).then(function (d) {
				r.porque[i] = d.error ? { motivo: 'Nao consegui explicar agora.', erro: true } : d;
			}).catch(function () { r.porque[i] = { motivo: 'Nao consegui explicar agora.', erro: true }; })
			.then(function () { if (review === r) barra(); });
	}

	/* decide uma; vai para a proxima pendente; tudo decidido = conclui */
	function decidir(i, ok, ficar) {
		if (!review || i === undefined || i === null) return;
		review.dec[i] = ok;
		var el = $('.nous-dc-sg[data-i="' + i + '"]');
		if (el) { el.classList.toggle('ok', ok); el.classList.toggle('no', !ok); }
		var l = idxs(), pend = l.filter(function (j) { return review.dec[j] === undefined; });
		if (!pend.length) { setTimeout(concluir, 350); barra(); return; }
		if (ficar) { barra(); return; }
		var depois = pend.filter(function (j) { return j > i; });
		focar(depois.length ? depois[0] : pend[0]);
	}

	function barra() {
		var l = idxs(), total = l.length, feitas = Object.keys(review.dec).length;
		var pos = l.indexOf(review.atual) + 1;
		var bar = $('#nous-dc-revbar');
		bar.innerHTML = '<span class="nous-dc-rt"><b>' + esc(review.rotulo) + '</b> · sugestao ' + (pos || 1) + ' de ' + total +
			' · ' + feitas + ' decidida' + (feitas === 1 ? '' : 's') + '</span>' +
			'<button class="nous-dc-btn ghost nous-dc-nav" type="button" data-go="-1" title="Anterior (←)" aria-label="Sugestao anterior">‹</button>' +
			'<button class="nous-dc-btn ghost nous-dc-nav" type="button" data-go="1" title="Proxima (→)" aria-label="Proxima sugestao">›</button>' +
			'<button class="nous-dc-btn" type="button" data-um="1">✓ Aceitar<kbd class="nous-dc-k">Enter</kbd></button>' +
			'<button class="nous-dc-btn ghost" type="button" data-um="0">✕ Recusar<kbd class="nous-dc-k">Del</kbd></button>' +
			'<button class="nous-dc-btn ghost" type="button" id="nous-dc-pq" title="Por que mudar? (tecla ?)">❓ Por que?</button>' +
			'<span class="nous-dc-sp"></span>' +
			'<button class="nous-dc-btn ghost" type="button" data-all="1">Aceitar todas</button>' +
			'<button class="nous-dc-btn ghost" type="button" data-all="0">Recusar todas</button>' +
			'<button class="nous-dc-btn" type="button" id="nous-dc-done">Concluir</button>';
		bar.querySelectorAll('[data-go]').forEach(function (b) { b.addEventListener('click', function () { ir(+b.getAttribute('data-go')); }); });
		bar.querySelector('#nous-dc-pq').addEventListener('click', porque);
		var why = review.porque[review.atual];
		bar.insertAdjacentHTML('beforeend', '<div id="nous-dc-why"' + (why ? '' : ' style="display:none"') + '>' +
			(why ? (why.carregando ? '<i>Pensando no motivo...</i>' : esc(why.motivo) + (why.fonte === 'ia' ? ' <small>(explicacao da IA, pode errar)</small>' : '')) : '') + '</div>');
		bar.querySelectorAll('[data-um]').forEach(function (b) {
			b.addEventListener('click', function () { decidir(review.atual, b.getAttribute('data-um') === '1'); });
		});
		bar.querySelectorAll('[data-all]').forEach(function (b) {
			b.addEventListener('click', function () {
				var ok = b.getAttribute('data-all') === '1';
				l.forEach(function (i) { review.dec[i] = ok; });
				concluir();
			});
		});
		bar.querySelector('#nous-dc-done').addEventListener('click', function () {
			if (feitas >= total) { concluir(); return; }
			confirmar('As ' + (total - feitas) + ' sugestoes que voce nao decidiu ficam como estavam.',
				{ titulo: 'Concluir a revisao?', ok: 'Concluir' }).then(function (sim) { if (sim) concluir(); });
		});
	}

	function concluir() {
		if (!review) return;
		var r = review, texto = '', aceitas = 0;
		r.segs.forEach(function (s, i) {
			if (s.t === '=') texto += s.s;
			else if (r.dec[i] === true) { texto += s.b; aceitas++; }
			else texto += s.a;
		});
		review = null;
		modo('w');
		travar(false);
		var ta = $('#nous-dc-text');
		ta.value = texto;
		contar(); vazio();
		if (!aceitas) { toast('Nada mudou: o texto ficou como estava.', { tipo: 'info' }); return; }
		salvarAgora('antes da IA: ' + r.rotulo.replace(/^[^\wÀ-ú]+\s*/, '').slice(0, 50));
		var antes = r.antes;
		toast(aceitas + ' mudanca' + (aceitas === 1 ? '' : 's') + ' aplicada' + (aceitas === 1 ? '' : 's') + '.', {
			acao: function () {
				if (review) return;
				if (ta.value !== texto) { msg('Voce ja editou depois: use Versoes para voltar.', true); return; }
				ta.value = antes;
				contar(); vazio();
				salvarAgora('antes de desfazer a IA');
				toast('Desfeito: o texto voltou como era.');
			}
		});
	}

	/* ---------------------------------------------------------- menus */
	function fecharPops() { document.querySelectorAll('.nous-dc-pop').forEach(function (p) { p.remove(); }); }

	function pop(anchor, html) {
		fecharPops();
		var p = document.createElement('div');
		p.className = 'nous-dc-pop';
		p.setAttribute('role', 'menu');
		p.innerHTML = html;
		var dc = $('#nous-dc'), r = anchor.getBoundingClientRect(), box = dc.getBoundingClientRect();
		dc.appendChild(p);
		var left = Math.min(r.left - box.left, box.width - p.offsetWidth - 8);
		p.style.left = Math.max(8, left) + 'px';
		p.style.top = (r.bottom - box.top + 4) + 'px';
		var first = p.querySelector('button');
		if (first) first.focus();
		setTimeout(function () {
			document.addEventListener('click', function fora(e) {
				if (!p.contains(e.target)) { p.remove(); document.removeEventListener('click', fora, true); }
			}, true);
		}, 0);
		return p;
	}

	function menuExportar(anchor) {
		var p = pop(anchor, '<button type="button" data-f="docx">📄 Word (.docx)</button><button type="button" data-f="pdf">📕 PDF</button>' +
			'<button type="button" data-f="md">Ⓜ Markdown (.md)</button><button type="button" data-f="copiar">📋 Copiar o texto</button>');
		p.addEventListener('click', function (e) {
			var b = e.target.closest('[data-f]');
			if (!b) return;
			p.remove();
			var f = b.getAttribute('data-f'), texto = $('#nous-dc-text').value, titulo = $('#nous-dc-title').value.trim() || 'Documento';
			if (!texto.trim()) { msg('O documento esta vazio.', true); return; }
			if (f === 'copiar') {
				navigator.clipboard.writeText(texto).then(function () { toast('Texto copiado.'); }, function () { msg('Nao consegui copiar.', true); });
				return;
			}
			var fecha = toast('Gerando o arquivo...', { tipo: 'info', ms: 30000 });
			fetch(MON + '/docs/export', { method: 'POST', headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ titulo: titulo, texto: texto, formato: f }) })
				.then(function (r) {
					if (r.ok) return r.blob();
					return r.json().then(function (d) { throw new Error(d.error || 'falhou'); });
				}).then(function (blob) {
					if (fecha) fecha();
					baixar(blob, titulo + '.' + f);
					toast('Baixado: ' + titulo + '.' + f);
				}).catch(function (e) { if (fecha) fecha(); msg('Nao consegui gerar o arquivo: ' + e.message, true); });
		});
	}

	function baixar(blob, nome) {
		var a = document.createElement('a');
		a.href = URL.createObjectURL(blob);
		a.download = nome.replace(/[\\/:*?"<>|]+/g, ' ');
		document.body.appendChild(a);
		a.click();
		setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
	}

	function menuVersoes(anchor) {
		salvarAgora('', function () {
			var vs = (cur && cur.versoes) || [];
			var p = pop(anchor, vs.length ? vs.map(function (v) {
				return '<button type="button" data-v="' + v.i + '">' + quando(v.t) + ' <small>· ' + esc(v.motivo) + ' · ' + v.palavras + ' palavras</small></button>';
			}).join('') : '<div class="nous-dc-empty">Ainda nao ha versoes. O Nous guarda uma antes de cada mudanca da IA, ' +
				'a cada 10 min de escrita e quando voce aperta Ctrl+S.</div>');
			p.addEventListener('click', function (e) {
				var b = e.target.closest('[data-v]');
				if (!b) return;
				p.remove();
				var v = vs.filter(function (x) { return String(x.i) === b.getAttribute('data-v'); })[0] || {};
				comparar(v);
			});
		});
	}

	/* Antes de voltar: mostra o que muda (riscado sai, sublinhado volta). */
	function comparar(v) {
		var atual = $('#nous-dc-text').value, rot = quando(v.t) + (v.motivo ? ' (' + v.motivo + ')' : '');
		fetch(MON + '/docs/version?id=' + encodeURIComponent(cur.id) + '&i=' + v.i, { cache: 'no-store' })
			.then(function (r) { return r.json(); }).then(function (d) {
				if (d.error) throw new Error(d.error);
				return fetch(MON + '/docs/diff', { method: 'POST', headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ a: atual, b: d.texto }) }).then(function (r) { return r.json(); })
					.then(function (df) { return [d.texto, df]; });
			}).then(function (par) {
				var texto = par[0], df = par[1];
				if (!df.mudancas) { toast('Esta versao e\' igual ao texto de agora.', { tipo: 'info' }); return; }
				compara = { texto: texto };
				$('#nous-dc-rev').innerHTML = df.segs.map(function (s) {
					return s.t === '=' ? esc(s.s) : '<span class="nous-dc-cmp">' + (s.a ? '<del>' + esc(s.a) + '</del>' : '') +
						(s.b ? '<ins>' + esc(s.b) + '</ins>' : '') + '</span>';
				}).join('');
				$('#nous-dc-rev').onclick = null;
				modo('r');
				var bar = $('#nous-dc-revbar');
				bar.innerHTML = '<span class="nous-dc-rt">🕘 <b>Versao de ' + esc(rot) + '</b> · ' + df.mudancas + ' diferenca' +
					(df.mudancas === 1 ? '' : 's') + ': <del>riscado</del> sai, <ins>sublinhado</ins> volta</span>' +
					'<button class="nous-dc-btn" type="button" id="nous-dc-volta">↩ Voltar para esta versao</button>' +
					'<button class="nous-dc-btn ghost" type="button" id="nous-dc-cmpx">Fechar</button>';
				bar.querySelector('#nous-dc-cmpx').addEventListener('click', fecharComparacao);
				bar.querySelector('#nous-dc-volta').addEventListener('click', function () {
					fecharComparacao();
					$('#nous-dc-text').value = texto;
					contar(); vazio();
					salvarAgora('antes de voltar uma versao');
					toast('Voltou para a versao de ' + quando(v.t) + '.', { acao: function () {
						$('#nous-dc-text').value = atual;
						contar(); vazio();
						salvarAgora('antes de desfazer a volta');
					} });
				});
				var first = $('#nous-dc-rev .nous-dc-cmp');
				if (first) first.scrollIntoView({ block: 'center' });
			}).catch(function (e) { msg(e.message, true); });
	}

	function fecharComparacao() {
		if (!compara) return;
		compara = null;
		modo('w');
	}

	/* ---------------------------------------------------- arquivo e chat */
	function importar(file) {
		if (review) return;
		var fecha = toast('Lendo ' + file.name + '...', { tipo: 'info', ms: 30000 });
		fetch(MON + '/docs/import?nome=' + encodeURIComponent(file.name), { method: 'POST', body: file })
			.then(function (r) { return r.json(); }).then(function (d) {
				if (fecha) fecha();
				if (d.error) throw new Error(d.error);
				if (!d.texto) throw new Error(d.aviso || 'Arquivo sem texto.');
				$('#nous-dc').classList.remove('lista');
				novo(d.titulo, d.texto);
				toast('Aberto: ' + file.name);
			}).catch(function (e) { if (fecha) fecha(); msg(e.message, true); });
	}

	function usarNoChat() {
		var texto = $('#nous-dc-text').value.trim();
		if (!texto) { msg('O documento esta vazio.', true); return; }
		var box = document.getElementById('chat-input');
		if (!box) { msg('Abra uma conversa primeiro.', true); return; }
		salvarAgora();
		var titulo = $('#nous-dc-title').value.trim();
		var m = 'Sobre este documento' + (titulo ? ' ("' + titulo + '")' : '') + ':\n\n' + texto + '\n\n';
		fechar();
		box.focus();
		if (box.tagName === 'TEXTAREA') {
			box.value = m;
			box.dispatchEvent(new Event('input', { bubbles: true }));
		} else {
			document.execCommand('selectAll', false, null);
			document.execCommand('insertText', false, m);
		}
		toast('O texto foi para o chat: escreva o seu pedido no fim e envie.', { tipo: 'info' });
	}

	function start() {
		injectStyle();
		window.NousDocs = {
			open: open,
			/* abre um documento novo com este texto (resposta do chat, por exemplo) */
			novo: function (titulo, texto) { open(false); novo(titulo, texto); }
		};
		setInterval(ensureButton, 1000);
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
