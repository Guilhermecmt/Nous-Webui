/* Nous Code: o IDE. Monaco (o editor do VS Code), arvore de arquivos com abas,
 * busca no projeto, Git, terminal PowerShell de verdade e o agente de IA local
 * ao lado. Tudo fala com o servico em /, na mesma porta (8998). */
(function () {
  'use strict';

  /* ------------------------------------------------------------ util */
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const base = (p) => p.split('/').pop();
  const pai = (p) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '');
  const guardar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* sem armazenamento */ } };
  const lembrar = (k, d) => { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } };

  function api(metodo, rota, corpo) {
    return fetch(rota, { method: metodo, cache: 'no-store', headers: corpo ? { 'Content-Type': 'application/json' } : {},
      body: corpo ? JSON.stringify(corpo) : undefined })
      .then((r) => r.json().then((d) => { if (!r.ok) throw new Error(d.erro || ('erro ' + r.status)); return d; }));
  }
  const qs = (o) => Object.entries(o).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&');

  const SVG = {
    arquivos: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
    busca: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    git: '<circle cx="6" cy="6" r="2.5"/><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="8" r="2.5"/><path d="M6 8.5v7M18 10.5c0 4-6 3-11 5.5"/>',
    term: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
    agente: '<path d="M12 3a7 7 0 0 1 7 7v3a4 4 0 0 1-4 4h-1l-2 3-2-3H9a4 4 0 0 1-4-4v-3a7 7 0 0 1 7-7z"/><circle cx="9.5" cy="10.5" r="1"/><circle cx="14.5" cy="10.5" r="1"/>',
    pasta: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    novoArq: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M12 12v6M9 15h6"/>',
    novaPasta: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM12 10v6M9 13h6"/>',
    recolher: '<path d="m7 15 5-5 5 5"/>', atualizar: '<path d="M20 11a8 8 0 1 0-2 5.3M20 5v6h-6"/>',
    mais: '<path d="M12 5v14M5 12h14"/>', fechar: '<path d="M6 6l12 12M18 6 6 18"/>', lixo: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
  };
  const ic = (n, cls) => '<svg class="ic ' + (cls || '') + '" viewBox="0 0 24 24" aria-hidden="true">' + SVG[n] + '</svg>';

  /* cor e sigla por extensao (a arvore fica legivel sem pacote de icones) */
  const EXT = { js: ['JS', '#e7c069'], mjs: ['JS', '#e7c069'], cjs: ['JS', '#e7c069'], ts: ['TS', '#8fb8c9'], tsx: ['TX', '#8fb8c9'], jsx: ['JX', '#e7c069'],
    py: ['PY', '#8fb8c9'], json: ['{}', '#d9a066'], md: ['MD', '#b5c98a'], html: ['<>', '#e29a8a'], css: ['#', '#b39ddb'], scss: ['#', '#b39ddb'],
    ps1: ['PS', '#8fb8c9'], bat: ['BT', '#958a76'], vbs: ['VB', '#958a76'], sql: ['SQ', '#d9a066'], yml: ['YM', '#e29a8a'], yaml: ['YM', '#e29a8a'],
    svelte: ['SV', '#e29a8a'], vue: ['VU', '#8cc79a'], go: ['GO', '#8fb8c9'], rs: ['RS', '#d9a066'], java: ['JV', '#e29a8a'], cs: ['C#', '#8cc79a'],
    txt: ['TX', '#958a76'], toml: ['TM', '#958a76'], ini: ['IN', '#958a76'], sh: ['SH', '#8cc79a'], xml: ['<>', '#d9a066'] };
  function marcaExt(nome) {
    const e = (nome.split('.').pop() || '').toLowerCase();
    const m = EXT[e];
    return m ? '<span class="nc-ext" style="background:' + m[1] + '">' + m[0] + '</span>' : '<span class="nc-ext" style="background:#3a342b;color:#958a76">·</span>';
  }

  /* ------------------------------------------------------------ estado */
  const st = {
    raiz: null, nomeRaiz: '', abas: [], ativa: null, expandidas: new Set(['']), cacheArvore: new Map(),
    vista: 'arquivos', git: null, sessao: null, rodandoCtrl: null, vivo: null, modelos: [], diag: {},
    ws: null, termId: null, term: null, fit: null, monaco: null, editor: null, diffEd: null, selArvore: null,
  };

  function toast(texto, erro) {
    let t = $('#nc-toast');
    if (!t) { t = document.createElement('div'); t.id = 'nc-toast'; document.body.appendChild(t); }
    t.textContent = texto; t.className = erro ? 'erro' : '';
    clearTimeout(t._t); t._t = setTimeout(() => t.remove(), erro ? 5000 : 2600);
  }

  /* dialogo de texto (nome de arquivo etc.) e de confirmacao */
  function dialogo(pergunta, valor, confirmar) {
    return new Promise((ok) => {
      const d = document.createElement('div');
      d.id = 'nc-dialogo';
      d.innerHTML = '<form><p>' + esc(pergunta) + '</p>' + (confirmar ? '' : '<input value="' + esc(valor || '') + '" spellcheck="false">') +
        '<div class="bt"><button type="button" class="nc-bt borda" data-n>Cancelar</button><button type="submit" class="nc-bt ouro">' +
        esc(confirmar || 'OK') + '</button></div></form>';
      document.body.appendChild(d);
      const inp = $('input', d);
      const fim = (v) => { d.remove(); ok(v); };
      $('form', d).addEventListener('submit', (e) => { e.preventDefault(); fim(confirmar ? true : inp.value.trim()); });
      $('[data-n]', d).addEventListener('click', () => fim(null));
      d.addEventListener('mousedown', (e) => { if (e.target === d) fim(null); });
      d.addEventListener('keydown', (e) => { if (e.key === 'Escape') fim(null); });
      if (inp) { inp.focus(); const p = (valor || '').lastIndexOf('.'); inp.setSelectionRange(0, p > 0 ? p : (valor || '').length); }
      else $('button[type=submit]', d).focus();
    });
  }

  function menu(x, y, itens) {
    $('#nc-menu')?.remove();
    const m = document.createElement('div');
    m.id = 'nc-menu';
    m.innerHTML = itens.map((it, i) => (it === '-' ? '<hr>' : '<button type="button" data-i="' + i + '">' + esc(it[0]) + '</button>')).join('');
    document.body.appendChild(m);
    const r = m.getBoundingClientRect();
    m.style.left = Math.min(x, innerWidth - r.width - 8) + 'px';
    m.style.top = Math.min(y, innerHeight - r.height - 8) + 'px';
    m.addEventListener('click', (e) => { const b = e.target.closest('[data-i]'); if (b) { m.remove(); itens[+b.dataset.i][1](); } });
    setTimeout(() => document.addEventListener('mousedown', function fora(e) { if (!m.contains(e.target)) { m.remove(); document.removeEventListener('mousedown', fora); } }), 0);
  }

  /* ============================================================ tela inicial */
  function telaInicio(aviso) {
    $('#nc')?.classList.add('oculto');
    let el = $('#nc-inicio');
    if (!el) { el = document.createElement('div'); el.id = 'nc-inicio'; document.body.appendChild(el); }
    el.classList.remove('oculto');
    el.innerHTML = '<div>' + (aviso ? '<div class="nc-alerta">' + esc(aviso) + '</div>' : '') +
      '<div class="logo"><img src="/marca/nous_logo.png" alt=""><h1>Nous Code</h1></div>' +
      '<p>Um editor de código com um agente de IA que roda no seu computador. Abra a pasta de um projeto para começar.</p>' +
      '<button class="nc-bt ouro" id="nc-in-escolher" type="button">' + ic('pasta', 'p') + 'Abrir pasta</button>' +
      '<div class="linha"><input id="nc-in-cam" placeholder="ou cole o caminho, por exemplo C:\\dev\\meu-projeto" spellcheck="false">' +
      '<button class="nc-bt borda" id="nc-in-abrir" type="button">Abrir</button></div><div id="nc-in-rec"></div></div>';
    $('#nc-in-escolher').addEventListener('click', function () {
      this.disabled = true; this.textContent = 'Escolha a pasta na janela do Windows';
      api('POST', '/escolher-pasta').then((d) => { if (d.pasta) abrirProjeto(d.pasta); else telaInicio(); }).catch((e) => telaInicio(e.message));
    });
    const cam = $('#nc-in-cam');
    const vai = () => { if (cam.value.trim()) abrirProjeto(cam.value.trim()); };
    $('#nc-in-abrir').addEventListener('click', vai);
    cam.addEventListener('keydown', (e) => { if (e.key === 'Enter') vai(); });
    api('GET', '/pastas').then((l) => {
      if (!l.length) return;
      $('#nc-in-rec').innerHTML = '<p style="margin:0 0 8px;font-size:12.5px">Recentes</p>' + l.map((p) =>
        '<button class="nc-rec" type="button" data-p="' + esc(p.pasta) + '"><b>' + esc(p.nome) + '</b><small>' + esc(p.pasta) + '</small></button>').join('');
      $$('[data-p]', el).forEach((b) => b.addEventListener('click', () => abrirProjeto(b.dataset.p)));
    }).catch(() => {});
  }

  function abrirProjeto(pasta) {
    // valida e registra como recente (cria uma conversa so' se ainda nao houver)
    api('GET', '/sessoes?' + qs({ pasta })).then((l) => {
      const pega = l.length ? Promise.resolve({ id: l[0].id, pasta: l[0].pasta }) :
        api('POST', '/sessoes', { pasta }).then((d) => ({ id: d.id, pasta: null }));
      return pega.then((s) => api('GET', '/sessao?id=' + s.id));
    }).then((s) => {
      st.raiz = s.pasta;
      st.nomeRaiz = s.pasta.split(/[\\/]/).filter(Boolean).pop();
      history.replaceState(null, '', '/?' + qs({ pasta: st.raiz }));
      document.title = st.nomeRaiz + ' - Nous Code';
      $('#nc-inicio')?.classList.add('oculto');
      montar();
      carregarSessao(s);
      restaurarAbas();
    }).catch((e) => telaInicio(e.message));
  }

  /* ============================================================ moldura */
  function montar() {
    let nc = $('#nc');
    if (nc) { nc.classList.remove('oculto'); atualizarTudo(); return; }
    nc = document.createElement('div');
    nc.id = 'nc';
    nc.innerHTML =
      '<header id="nc-topo"><span class="marca"><img src="/marca/nous_logo.png" alt="">Nous Code</span>' +
      '<button class="nc-bt" id="nc-proj" type="button" title="Trocar de projeto">' + ic('pasta', 'p') + '<span></span></button>' +
      '<button class="nc-bt" id="nc-ir" type="button">' + ic('busca', 'p') + '<span>Ir para arquivo</span><kbd>Ctrl+P</kbd></button>' +
      '<button class="nc-bt" id="nc-bt-agente" type="button" title="Mostrar ou esconder o agente (Ctrl+L)">' + ic('agente', 'p') + 'Agente</button></header>' +
      '<nav id="nc-ativ" aria-label="Vistas">' +
      '<button type="button" data-vista="arquivos" title="Arquivos (Ctrl+Shift+E)">' + ic('arquivos') + '</button>' +
      '<button type="button" data-vista="busca" title="Buscar no projeto (Ctrl+Shift+F)">' + ic('busca') + '</button>' +
      '<button type="button" data-vista="git" title="Git (Ctrl+Shift+G)">' + ic('git') + '<span class="conta oculto"></span></button>' +
      '<span class="sp"></span><button type="button" id="nc-ativ-term" title="Terminal (Ctrl+`)">' + ic('term') + '</button></nav>' +
      '<aside id="nc-lado">' +
      '<section class="nc-vista" data-v="arquivos"><div class="nc-cab"><span class="t" id="nc-lado-nome"></span>' +
      '<button type="button" data-a="novoArq" title="Novo arquivo">' + ic('novoArq', 'p') + '</button>' +
      '<button type="button" data-a="novaPasta" title="Nova pasta">' + ic('novaPasta', 'p') + '</button>' +
      '<button type="button" data-a="atualizar" title="Atualizar">' + ic('atualizar', 'p') + '</button>' +
      '<button type="button" data-a="recolher" title="Recolher tudo">' + ic('recolher', 'p') + '</button></div>' +
      '<div class="nc-rola" id="nc-arvore" tabindex="0" role="tree"></div></section>' +
      '<section class="nc-vista oculto" data-v="busca"><div class="nc-cab"><span class="t">Buscar no projeto</span></div>' +
      '<div class="nc-campo"><input id="nc-busca" placeholder="Procurar" spellcheck="false">' +
      '<button type="button" id="nc-busca-aa" title="Diferenciar maiúsculas">Aa</button>' +
      '<button type="button" id="nc-busca-re" title="Expressão regular">.*</button></div>' +
      '<div class="nc-rola" id="nc-busca-res"></div></section>' +
      '<section class="nc-vista oculto" data-v="git"><div class="nc-cab"><span class="t">Controle de versão</span>' +
      '<button type="button" id="nc-git-at" title="Atualizar">' + ic('atualizar', 'p') + '</button></div>' +
      '<div class="nc-rola" id="nc-git"></div></section></aside>' +
      '<div id="nc-arrasta-lado"></div>' +
      '<main id="nc-centro"><div id="nc-abas" role="tablist"></div><div id="nc-trilho" class="oculto"></div>' +
      '<div id="nc-aviso-disco" class="oculto"></div><div id="nc-editor" class="oculto"></div><div id="nc-diff" class="oculto"></div>' +
      '<div id="nc-boas"><img src="/marca/nous_logo.png" alt=""><div class="nc-atalho">' +
      '<span>Ir para arquivo</span><span><kbd>Ctrl+P</kbd></span><span>Buscar no projeto</span><span><kbd>Ctrl+Shift+F</kbd></span>' +
      '<span>Terminal</span><span><kbd>Ctrl+`</kbd></span><span>Pedir ao agente</span><span><kbd>Ctrl+L</kbd></span>' +
      '<span>Salvar</span><span><kbd>Ctrl+S</kbd></span></div></div>' +
      '<div id="nc-arrasta-term" class="oculto"></div><section id="nc-term" class="oculto"><div class="nc-cab"><span class="t">Terminal</span>' +
      '<button type="button" id="nc-term-novo" title="Novo terminal">' + ic('mais', 'p') + '</button>' +
      '<button type="button" id="nc-term-x" title="Fechar o painel">' + ic('fechar', 'p') + '</button></div><div id="nc-term-corpo"></div></section></main>' +
      '<aside id="nc-agente" aria-label="Agente">' +
      '<div id="nc-ag-cab"><b>Agente</b><select id="nc-ag-conv" aria-label="Conversa"></select>' +
      '<button class="nc-bt" type="button" id="nc-ag-menu" title="Opções da conversa" aria-label="Opções da conversa">⋯</button>' +
      '<button class="nc-bt" type="button" id="nc-ag-nova" title="Nova conversa">' + ic('mais', 'p') + '</button></div>' +
      '<div id="nc-ag-opcoes"><select id="nc-ag-modelo" aria-label="Modelo"></select><select id="nc-ag-perm" aria-label="Permissões" title="O que o agente pode fazer sem perguntar"></select>' +
      '<select id="nc-ag-rac" aria-label="Raciocínio" class="oculto"></select>' +
      '<button class="nc-bt borda" id="nc-ag-plano" type="button" aria-pressed="false">Planejar</button></div>' +
      '<div id="nc-ag-ctx"><div class="barra"><i></i></div><span></span><button type="button" id="nc-ag-compactar" title="Resumir a conversa para liberar contexto">compactar</button></div>' +
      '<div id="nc-ag-obj" class="oculto"></div><div id="nc-ag-tarefas" class="oculto"></div>' +
      '<div id="nc-trilha" aria-live="polite"></div><div id="nc-ag-jobs" class="oculto"></div><div id="nc-ag-lem" class="oculto"></div><div id="nc-ag-mud" class="oculto"></div>' +
      '<div id="nc-ag-caixa"><div class="caixa"><textarea id="nc-ag-txt" rows="1" placeholder="Peça ao agente: corrija os testes, explique este arquivo…" aria-label="Pedido ao agente"></textarea>' +
      '<button id="nc-ag-env" type="button">Enviar</button></div><div id="nc-ag-dica">Enter envia, / para comandos, @ para anexar arquivo</div></div></aside>' +
      '<footer id="nc-status"><button type="button" id="nc-st-ramo" title="Git">' + ic('git', 'p') + '<span></span></button>' +
      '<span class="sp"></span><span id="nc-st-pos"></span><span id="nc-st-eol"></span><span id="nc-st-ling"></span>' +
      '<span id="nc-st-modelo" title="Modelo do agente"></span><span title="Servico do Nous Code"><i class="ponto" id="nc-st-ponto"></i></span></footer>';
    document.body.appendChild(nc);

    $('#nc-proj').addEventListener('click', () => {
      if (st.abas.some((a) => a.sujo)) return toast('Salve ou feche os arquivos com mudanças antes de trocar de projeto.', true);
      fecharTudo(); st.raiz = null; history.replaceState(null, '', '/'); telaInicio();
    });
    $('#nc-ir').addEventListener('click', paleta);
    $('#nc-bt-agente').addEventListener('click', () => alternarAgente());
    $$('#nc-ativ [data-vista]').forEach((b) => b.addEventListener('click', () => vista(b.dataset.vista, true)));
    $('#nc-ativ-term').addEventListener('click', () => alternarTerminal());
    $('#nc-term-x').addEventListener('click', () => alternarTerminal(false));
    $('#nc-term-novo').addEventListener('click', () => { fecharTerminal(); abrirTerminal(); });
    $('#nc-st-ramo').addEventListener('click', () => vista('git'));
    $('[data-v=arquivos] .nc-cab').addEventListener('click', (e) => {
      const b = e.target.closest('[data-a]'); if (!b) return;
      const alvo = st.selArvore && st.selArvore.pasta ? st.selArvore.caminho : (st.selArvore ? pai(st.selArvore.caminho) : '');
      ({ novoArq: () => novo(alvo, false), novaPasta: () => novo(alvo, true), atualizar: () => { st.cacheArvore.clear(); desenharArvore(); },
        recolher: () => { st.expandidas = new Set(['']); desenharArvore(); } })[b.dataset.a]();
    });
    ligarBusca();
    $('#nc-git-at').addEventListener('click', atualizarGit);
    ligarAgente();
    ligarArrastos();
    const nc2 = $('#nc');
    if (lembrar('nc-sem-agente', false)) nc2.classList.add('sem-agente');
    if (lembrar('nc-sem-lado', false)) nc2.classList.add('sem-lado');
    document.documentElement.style.setProperty('--lado', lembrar('nc-lado', 260) + 'px');
    document.documentElement.style.setProperty('--term', lembrar('nc-term', 240) + 'px');
    criarEditor();
    conectarWs();
    atualizarTudo();
  }

  function atualizarTudo() {
    $('#nc-proj span').textContent = st.nomeRaiz;
    $('#nc-proj').title = st.raiz + ' (clique para trocar de projeto)';
    $('#nc-lado-nome').textContent = st.nomeRaiz;
    st.cacheArvore.clear();
    desenharArvore();
    atualizarGit();
    vista(st.vista);
    if (st.ws && st.ws.readyState === 1) st.ws.send(JSON.stringify({ t: 'observar', raiz: st.raiz }));
  }

  function vista(v, alternar) {
    const nc = $('#nc');
    if (alternar && st.vista === v && !nc.classList.contains('sem-lado')) { nc.classList.add('sem-lado'); guardar('nc-sem-lado', true); return; }
    nc.classList.remove('sem-lado'); guardar('nc-sem-lado', false);
    st.vista = v;
    $$('#nc-ativ [data-vista]').forEach((b) => b.classList.toggle('on', b.dataset.vista === v));
    $$('#nc-lado .nc-vista').forEach((s) => s.classList.toggle('oculto', s.dataset.v !== v));
    if (v === 'busca') setTimeout(() => $('#nc-busca').focus(), 0);
    if (v === 'git') atualizarGit();
    setTimeout(layout, 0);
  }

  function alternarAgente(mostrar) {
    const nc = $('#nc');
    const vai = mostrar === undefined ? nc.classList.contains('sem-agente') : mostrar;
    nc.classList.toggle('sem-agente', !vai);
    guardar('nc-sem-agente', !vai);
    $('#nc-bt-agente').classList.toggle('on', vai);
    if (vai) setTimeout(() => $('#nc-ag-txt').focus(), 0);
    setTimeout(layout, 0);
  }

  function ligarArrastos() {
    const al = $('#nc-arrasta-lado');
    al.addEventListener('mousedown', (e) => {
      e.preventDefault(); al.classList.add('ativo');
      const mv = (ev) => { const w = Math.max(160, Math.min(560, ev.clientX - 48)); document.documentElement.style.setProperty('--lado', w + 'px'); layout(); };
      const up = (ev) => { al.classList.remove('ativo'); guardar('nc-lado', Math.max(160, Math.min(560, ev.clientX - 48))); removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
      addEventListener('mousemove', mv); addEventListener('mouseup', up);
    });
    const at = $('#nc-arrasta-term');
    at.addEventListener('mousedown', (e) => {
      e.preventDefault(); at.classList.add('ativo');
      const alto = (ev) => Math.max(100, Math.min(innerHeight - 200, innerHeight - 24 - ev.clientY));
      const mv = (ev) => { document.documentElement.style.setProperty('--term', alto(ev) + 'px'); layout(); };
      const up = (ev) => { at.classList.remove('ativo'); guardar('nc-term', alto(ev)); removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
      addEventListener('mousemove', mv); addEventListener('mouseup', up);
    });
  }

  function layout() {
    st.editor && st.editor.layout();
    st.diffEd && st.diffEd.layout();
    if (st.fit && !$('#nc-term').classList.contains('oculto')) {
      try { st.fit.fit(); } catch (e) { /* ainda sem tamanho */ }
    }
  }
  addEventListener('resize', layout);

  /* ============================================================ arvore */
  function listarDir(dir) {
    if (st.cacheArvore.has(dir)) return Promise.resolve(st.cacheArvore.get(dir));
    return api('GET', '/fs/arvore?' + qs({ raiz: st.raiz, dir })).then((l) => { st.cacheArvore.set(dir, l); return l; });
  }

  function marcaGit(caminho) {
    if (!st.git || !st.git.repo) return '';
    const a = st.git.arquivos.find((f) => f.caminho === caminho);
    if (!a) return '';
    const l = a.x === '?' ? 'U' : (a.y !== ' ' ? a.y : a.x);
    return '<span class="g g-' + l + '">' + l + '</span>';
  }

  async function desenharArvore() {
    const box = $('#nc-arvore');
    if (!box || !st.raiz) return;
    const linhas = [];
    async function andar(dir, nivel) {
      let itens;
      try { itens = await listarDir(dir); } catch (e) { return; }
      for (const it of itens) {
        const caminho = dir ? dir + '/' + it.nome : it.nome;
        const aberta = st.expandidas.has(caminho);
        const sel = st.selArvore && st.selArvore.caminho === caminho;
        const ativa = st.ativa && st.abas[st.ativa] && st.abas[st.ativa].caminho === caminho;
        linhas.push('<div class="nc-no' + (sel || ativa ? ' sel' : '') + (it.apagado ? ' apagado' : '') + '" role="treeitem" data-c="' + esc(caminho) +
          '" data-p="' + (it.pasta ? 1 : 0) + '" style="padding-left:' + (8 + nivel * 13) + 'px"' + (it.pasta ? ' aria-expanded="' + aberta + '"' : '') + '>' +
          '<span class="seta">' + (it.pasta ? (aberta ? '▾' : '▸') : '') + '</span>' + (it.pasta ? '' : marcaExt(it.nome)) +
          '<span class="nome">' + esc(it.nome) + '</span>' + (it.pasta ? '' : marcaGit(caminho)) + '</div>');
        if (it.pasta && aberta) await andar(caminho, nivel + 1);
      }
    }
    await andar('', 0);
    box.innerHTML = linhas.join('') || '<div class="nc-vazio">Pasta vazia.</div>';
  }

  function ligarArvore() {
    const box = $('#nc-arvore');
    box.addEventListener('click', (e) => {
      const n = e.target.closest('.nc-no'); if (!n) return;
      const c = n.dataset.c, pasta = n.dataset.p === '1';
      st.selArvore = { caminho: c, pasta };
      if (pasta) { st.expandidas.has(c) ? st.expandidas.delete(c) : st.expandidas.add(c); desenharArvore(); }
      else abrirArquivo(c);
    });
    box.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const n = e.target.closest('.nc-no');
      const c = n ? n.dataset.c : '', pasta = n ? n.dataset.p === '1' : true;
      st.selArvore = n ? { caminho: c, pasta } : null;
      const dir = pasta ? c : pai(c);
      const itens = [['Novo arquivo', () => novo(dir, false)], ['Nova pasta', () => novo(dir, true)]];
      if (n) {
        itens.push('-', ['Renomear', () => renomear(c)], ['Apagar (vai para a Lixeira)', () => apagar(c, pasta)], '-',
          ['Copiar caminho', () => navigator.clipboard.writeText(st.raiz + '\\' + c.replace(/\//g, '\\'))]);
        if (!pasta) itens.push(['Perguntar ao agente sobre este arquivo', () => perguntarSobre(c)]);
        if (pasta) itens.push(['Abrir terminal aqui', () => abrirTerminal(c)]);
      }
      menu(e.clientX, e.clientY, itens);
    });
  }

  async function novo(dir, pasta) {
    const nome = await dialogo(pasta ? 'Nome da nova pasta' : 'Nome do novo arquivo' + (dir ? ' em ' + dir : ''), '');
    if (!nome) return;
    const caminho = (dir ? dir + '/' : '') + nome.replace(/\\/g, '/');
    api('POST', '/fs/novo', { raiz: st.raiz, caminho, pasta }).then(() => {
      st.cacheArvore.clear(); if (dir) st.expandidas.add(dir);
      desenharArvore(); if (!pasta) abrirArquivo(caminho);
    }).catch((e) => toast(e.message, true));
  }

  async function renomear(c) {
    const novoNome = await dialogo('Novo nome', base(c));
    if (!novoNome || novoNome === base(c)) return;
    const para = (pai(c) ? pai(c) + '/' : '') + novoNome;
    api('POST', '/fs/renomear', { raiz: st.raiz, de: c, para }).then(() => {
      st.abas.forEach((a) => { if (a.caminho === c) { a.caminho = para; } });
      st.cacheArvore.clear(); desenharArvore(); desenharAbas();
    }).catch((e) => toast(e.message, true));
  }

  async function apagar(c, pasta) {
    if (!(await dialogo('Apagar ' + (pasta ? 'a pasta ' : '') + c + '? Vai para a Lixeira do Windows.', null, 'Apagar'))) return;
    api('POST', '/fs/apagar', { raiz: st.raiz, caminho: c }).then(() => {
      st.abas.filter((a) => a.caminho === c || a.caminho.startsWith(c + '/')).forEach((a) => fecharAba(st.abas.indexOf(a), true));
      st.cacheArvore.clear(); desenharArvore(); toast(base(c) + ' foi para a Lixeira.');
    }).catch((e) => toast(e.message, true));
  }

  /* ============================================================ editor e abas */
  function criarEditor() {
    const m = st.monaco;
    m.editor.defineTheme('nous', {
      base: 'vs-dark', inherit: true,
      rules: [
        { token: 'comment', foreground: '7d7363', fontStyle: 'italic' }, { token: 'keyword', foreground: 'e7c069' },
        { token: 'string', foreground: 'b5c98a' }, { token: 'number', foreground: 'd9a066' }, { token: 'type', foreground: '8fb8c9' },
        { token: 'delimiter', foreground: 'a89f8c' }, { token: 'tag', foreground: 'e29a8a' }, { token: 'attribute.name', foreground: 'd9a066' },
      ],
      colors: {
        'editor.background': '#141210', 'editor.foreground': '#ddd5c6', 'editorLineNumber.foreground': '#5c5446',
        'editorLineNumber.activeForeground': '#c8962e', 'editor.selectionBackground': '#c8962e44', 'editor.inactiveSelectionBackground': '#c8962e22',
        'editor.lineHighlightBackground': '#1c1916', 'editor.lineHighlightBorder': '#00000000', 'editorCursor.foreground': '#e7c069',
        'editorIndentGuide.background1': '#2a2520', 'editorIndentGuide.activeBackground1': '#4a4134', 'editorWidget.background': '#1c1916',
        'editorWidget.border': '#c8962e55', 'editorSuggestWidget.selectedBackground': '#c8962e33', 'minimap.background': '#141210',
        'scrollbarSlider.background': '#e7c06922', 'scrollbarSlider.hoverBackground': '#e7c06944', 'editor.findMatchHighlightBackground': '#c8962e33',
        'diffEditor.insertedTextBackground': '#5fa36a30', 'diffEditor.removedTextBackground': '#c0573f30',
        'diffEditor.insertedLineBackground': '#5fa36a18', 'diffEditor.removedLineBackground': '#c0573f18',
      },
    });
    st.editor = m.editor.create($('#nc-editor'), {
      theme: 'nous', automaticLayout: false, fontFamily: '"Cascadia Code", "Cascadia Mono", Consolas, monospace', fontSize: 13.5,
      fontLigatures: true, minimap: { enabled: true, scale: 1 }, smoothScrolling: true, cursorSmoothCaretAnimation: 'on',
      renderWhitespace: 'selection', bracketPairColorization: { enabled: true }, guides: { bracketPairs: true }, stickyScroll: { enabled: true },
      scrollBeyondLastLine: false, padding: { top: 8 }, tabSize: 2,
    });
    st.editor.onDidChangeCursorPosition((e) => { $('#nc-st-pos').textContent = 'Ln ' + e.position.lineNumber + ', Col ' + e.position.column; });
    const K = m.KeyMod, C = m.KeyCode;
    st.editor.addCommand(K.CtrlCmd | C.KeyS, () => salvarAtiva());
    st.editor.addCommand(K.CtrlCmd | C.KeyP, () => paleta());
    st.editor.addCommand(K.CtrlCmd | K.Shift | C.KeyF, () => vista('busca'));
    st.editor.addCommand(K.CtrlCmd | C.KeyL, () => { alternarAgente(true); comSelecao(); });
    st.editor.addCommand(K.CtrlCmd | C.KeyW, () => { if (st.ativa !== null) fecharAba(st.ativa); });
    st.editor.addCommand(K.CtrlCmd | C.Backquote, () => alternarTerminal());
    st.editor.addCommand(K.CtrlCmd | C.KeyB, () => vista(st.vista, true));
    st.editor.addAction({ id: 'nous.perguntar', label: 'Perguntar ao agente sobre a seleção', contextMenuGroupId: '1_nous',
      run: () => { alternarAgente(true); comSelecao(); } });
    ligarArvore();
  }

  function linguagem(caminho) {
    const ext = '.' + (caminho.split('.').pop() || '').toLowerCase();
    const l = st.monaco.languages.getLanguages().find((x) => (x.extensions || []).includes(ext) || (x.filenames || []).includes(base(caminho)));
    return l ? l.id : 'plaintext';
  }

  async function abrirArquivo(caminho, linha, coluna, fim) {
    let i = st.abas.findIndex((a) => a.caminho === caminho && a.tipo === 'arquivo');
    if (i < 0) {
      let d;
      try { d = await api('GET', '/fs/ler?' + qs({ raiz: st.raiz, caminho })); } catch (e) { return toast(e.message, true); }
      if (d.binario || d.grande) return toast(base(caminho) + (d.binario ? ' é um arquivo binário.' : ' é grande demais para abrir aqui.'), true);
      const modelo = st.monaco.editor.createModel(d.conteudo, linguagem(caminho), st.monaco.Uri.parse('file:///' + caminho));
      if (d.crlf) modelo.setEOL(st.monaco.editor.EndOfLineSequence.CRLF);
      if (st.diag[caminho]) marcarProblemas(modelo, st.diag[caminho]);
      const aba = { tipo: 'arquivo', caminho, modelo, salvo: modelo.getAlternativeVersionId(), sujo: false, vista: null };
      modelo.onDidChangeContent(() => {
        const s = modelo.getAlternativeVersionId() !== aba.salvo;
        if (s !== aba.sujo) { aba.sujo = s; desenharAbas(); }
      });
      st.abas.push(aba);
      i = st.abas.length - 1;
    }
    ativar(i);
    if (linha) {
      const r = new st.monaco.Range(linha, coluna || 1, linha, fim || coluna || 1);
      st.editor.setSelection(r); st.editor.revealRangeInCenter(r);
    }
    st.editor.focus();
  }

  async function abrirDiff(caminho, novoArq) {
    let i = st.abas.findIndex((a) => a.caminho === caminho && a.tipo === 'diff');
    let orig = '', atual = '';
    try {
      orig = novoArq ? '' : (await api('GET', '/git/original?' + qs({ raiz: st.raiz, caminho }))).conteudo;
      const d = await api('GET', '/fs/ler?' + qs({ raiz: st.raiz, caminho })).catch(() => ({ conteudo: '' }));
      atual = d.conteudo || '';
    } catch (e) { return toast(e.message, true); }
    const lg = linguagem(caminho);
    if (i < 0) {
      st.abas.push({ tipo: 'diff', caminho, a: st.monaco.editor.createModel(orig, lg), b: st.monaco.editor.createModel(atual, lg) });
      i = st.abas.length - 1;
    } else { st.abas[i].a.setValue(orig); st.abas[i].b.setValue(atual); }
    ativar(i);
  }

  function ativar(i) {
    const atual = st.abas[st.ativa];
    if (atual && atual.tipo === 'arquivo') atual.vista = st.editor.saveViewState();
    st.ativa = i;
    const a = st.abas[i];
    $('#nc-boas').classList.toggle('oculto', !!a);
    $('#nc-editor').classList.toggle('oculto', !a || a.tipo !== 'arquivo');
    $('#nc-diff').classList.toggle('oculto', !a || a.tipo !== 'diff');
    $('#nc-trilho').classList.toggle('oculto', !a);
    $('#nc-aviso-disco').classList.add('oculto');
    if (a && a.tipo === 'arquivo') {
      st.editor.setModel(a.modelo);
      if (a.vista) st.editor.restoreViewState(a.vista);
      $('#nc-st-ling').textContent = a.modelo.getLanguageId();
      $('#nc-st-eol').textContent = a.modelo.getEOL() === '\r\n' ? 'CRLF' : 'LF';
      if (a.mudouNoDisco) avisoDisco(a);
    } else if (a && a.tipo === 'diff') {
      if (!st.diffEd) {
        st.diffEd = st.monaco.editor.createDiffEditor($('#nc-diff'), { theme: 'nous', readOnly: true, renderSideBySide: true, automaticLayout: false,
          fontFamily: '"Cascadia Code", Consolas, monospace', fontSize: 13, minimap: { enabled: false }, scrollBeyondLastLine: false });
      }
      st.diffEd.setModel({ original: a.a, modified: a.b });
      $('#nc-st-ling').textContent = 'diff';
    } else { $('#nc-st-ling').textContent = ''; $('#nc-st-eol').textContent = ''; $('#nc-st-pos').textContent = ''; }
    if (a) $('#nc-trilho').innerHTML = esc(st.nomeRaiz) + ' › ' + a.caminho.split('/').map(esc).join(' › ') + (a.tipo === 'diff' ? ' <em>(mudanças desde o último commit)</em>' : '');
    desenharAbas();
    desenharArvore();
    guardarAbas();
    setTimeout(layout, 0);
  }

  function desenharAbas() {
    $('#nc-abas').innerHTML = st.abas.map((a, i) =>
      '<div class="nc-aba' + (i === st.ativa ? ' on' : '') + (a.sujo ? ' sujo' : '') + '" role="tab" data-i="' + i + '" title="' + esc(a.caminho) + '">' +
      (a.tipo === 'diff' ? ic('git', 'p') : marcaExt(base(a.caminho))) + '<span class="nome">' + esc(base(a.caminho)) + '</span>' +
      (a.tipo === 'diff' ? '<em>diff</em>' : '') + '<button class="x" type="button" title="Fechar (Ctrl+W)">×</button></div>').join('');
  }
  document.addEventListener('click', (e) => {
    const aba = e.target.closest('.nc-aba');
    if (!aba) return;
    const i = +aba.dataset.i;
    if (e.target.closest('.x')) fecharAba(i); else ativar(i);
  });
  document.addEventListener('auxclick', (e) => { const aba = e.target.closest('.nc-aba'); if (aba && e.button === 1) fecharAba(+aba.dataset.i); });

  async function fecharAba(i, forcar) {
    const a = st.abas[i];
    if (!a) return;
    if (a.sujo && !forcar) {
      const r = await dialogo(base(a.caminho) + ' tem mudanças não salvas. Fechar mesmo assim?', null, 'Fechar sem salvar');
      if (!r) return;
    }
    if (a.tipo === 'arquivo') a.modelo.dispose(); else { a.a.dispose(); a.b.dispose(); }
    st.abas.splice(i, 1);
    if (!st.abas.length) { st.ativa = null; ativar(null); return; }
    ativar(Math.min(st.ativa > i ? st.ativa - 1 : st.ativa === i ? Math.max(0, i - 1) : st.ativa, st.abas.length - 1));
  }

  function fecharTudo() {
    st.abas.forEach((a) => { if (a.tipo === 'arquivo') a.modelo.dispose(); else { a.a.dispose(); a.b.dispose(); } });
    st.abas = []; st.ativa = null;
  }

  function salvarAtiva() {
    const a = st.abas[st.ativa];
    if (!a || a.tipo !== 'arquivo') return;
    const versao = a.modelo.getAlternativeVersionId();
    api('POST', '/fs/salvar', { raiz: st.raiz, caminho: a.caminho, conteudo: a.modelo.getValue() }).then(() => {
      a.salvo = versao; a.sujo = a.modelo.getAlternativeVersionId() !== versao; a.mudouNoDisco = false;
      delete st.diag[a.caminho]; marcarProblemas(a.modelo, []);  // quem salva assume o arquivo: as marcas do agente saem
      a.ignorarAte = Date.now() + 1500;  // o aviso do disco desta gravacao nao conta
      desenharAbas(); $('#nc-aviso-disco').classList.add('oculto'); atualizarGitDepois();
    }).catch((e) => toast('Não salvou: ' + e.message, true));
  }

  function guardarAbas() {
    if (!st.raiz) return;
    guardar('nc-abas:' + st.raiz, { abas: st.abas.filter((a) => a.tipo === 'arquivo').map((a) => a.caminho),
      ativa: st.abas[st.ativa] && st.abas[st.ativa].tipo === 'arquivo' ? st.abas[st.ativa].caminho : null });
  }
  async function restaurarAbas() {
    const g = lembrar('nc-abas:' + st.raiz, null);
    if (!g) return;
    for (const c of g.abas) { try { await abrirArquivo(c); } catch (e) { /* sumiu */ } }
    const i = st.abas.findIndex((a) => a.caminho === g.ativa);
    if (i >= 0) ativar(i);
  }

  /* arquivo mudou no disco (o agente editou, ou outro programa) */
  function mudouNoDisco(caminhos) {
    const dirs = new Set(caminhos.map(pai));
    let recarregar = false;
    for (const d of dirs) if (st.cacheArvore.has(d)) { st.cacheArvore.delete(d); recarregar = true; }
    caminhos.forEach((c) => { if (!st.cacheArvore.has(pai(c))) recarregar = true; });
    if (recarregar) desenharArvore();
    atualizarGitDepois();
    for (const a of st.abas) {
      if (a.tipo !== 'arquivo' || !caminhos.includes(a.caminho) || (a.ignorarAte && Date.now() < a.ignorarAte)) continue;
      api('GET', '/fs/ler?' + qs({ raiz: st.raiz, caminho: a.caminho })).then((d) => {
        if (d.conteudo === undefined || d.conteudo === a.modelo.getValue()) return;
        if (!a.sujo) {
          const vs = st.abas[st.ativa] === a ? st.editor.saveViewState() : null;
          a.modelo.pushEditOperations([], [{ range: a.modelo.getFullModelRange(), text: d.conteudo }], () => null);
          a.salvo = a.modelo.getAlternativeVersionId(); a.sujo = false;
          if (vs) st.editor.restoreViewState(vs);
          desenharAbas();
        } else { a.mudouNoDisco = true; if (st.abas[st.ativa] === a) avisoDisco(a); }
      }).catch(() => {});
    }
  }
  function avisoDisco(a) {
    const el = $('#nc-aviso-disco');
    el.innerHTML = base(a.caminho) + ' mudou no disco e você tem mudanças não salvas.' +
      '<button class="nc-bt borda" type="button" data-r>Usar a versão do disco</button><button class="nc-bt" type="button" data-m>Manter a minha</button>';
    el.classList.remove('oculto');
    $('[data-r]', el).addEventListener('click', () => {
      api('GET', '/fs/ler?' + qs({ raiz: st.raiz, caminho: a.caminho })).then((d) => {
        a.modelo.setValue(d.conteudo); a.salvo = a.modelo.getAlternativeVersionId(); a.sujo = false; a.mudouNoDisco = false;
        el.classList.add('oculto'); desenharAbas();
      });
    });
    $('[data-m]', el).addEventListener('click', () => { a.mudouNoDisco = false; el.classList.add('oculto'); });
  }

  /* ============================================================ Ctrl+P */
  let cacheArquivos = null;
  function paleta() {
    if ($('#nc-paleta') || !st.raiz) return;
    const p = document.createElement('div');
    p.id = 'nc-paleta';
    p.innerHTML = '<div><input placeholder="Nome do arquivo" spellcheck="false" aria-label="Ir para arquivo"><div class="lista"></div></div>';
    document.body.appendChild(p);
    const inp = $('input', p), lista = $('.lista', p);
    let ops = [], sel = 0;
    const fechar = () => { p.remove(); st.editor && st.editor.focus(); };
    p.addEventListener('mousedown', (e) => { if (e.target === p) fechar(); });
    const carrega = cacheArquivos ? Promise.resolve(cacheArquivos) :
      api('GET', '/fs/arquivos?' + qs({ raiz: st.raiz })).then((l) => (cacheArquivos = l));
    function pontua(c, q) {
      if (!q) return 1;
      const n = c.toLowerCase(), b = base(c).toLowerCase();
      if (b.startsWith(q)) return 1000 - b.length;
      if (b.includes(q)) return 800 - b.length;
      let i = 0, pts = 0;
      for (const ch of n) { if (ch === q[i]) { i++; pts += 2; } if (i === q.length) break; }
      return i === q.length ? pts - n.length / 10 : -1;
    }
    function realce(t, q) {
      if (!q) return esc(t);
      const k = t.toLowerCase().indexOf(q);
      return k < 0 ? esc(t) : esc(t.slice(0, k)) + '<mark>' + esc(t.slice(k, k + q.length)) + '</mark>' + esc(t.slice(k + q.length));
    }
    function desenha() {
      const q = inp.value.trim().toLowerCase().replace(/\\/g, '/');
      carrega.then((l) => {
        const abertas = st.abas.map((a) => a.caminho);
        ops = l.map((c) => [c, pontua(c, q) + (abertas.includes(c) && !q ? 50 : 0)]).filter((x) => x[1] >= 0)
          .sort((a, b) => b[1] - a[1]).slice(0, 60).map((x) => x[0]);
        sel = Math.min(sel, Math.max(0, ops.length - 1));
        lista.innerHTML = ops.map((c, i) => '<div class="nc-op' + (i === sel ? ' on' : '') + '" data-i="' + i + '">' + marcaExt(base(c)) +
          '<b>' + realce(base(c), q) + '</b><small>' + esc(pai(c)) + '</small></div>').join('') || '<div class="nc-vazio">Nenhum arquivo.</div>';
        const on = $('.on', lista); on && on.scrollIntoView({ block: 'nearest' });
      });
    }
    inp.addEventListener('input', () => { sel = 0; desenha(); });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') fechar();
      else if (e.key === 'ArrowDown') { e.preventDefault(); sel = Math.min(ops.length - 1, sel + 1); desenha(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); sel = Math.max(0, sel - 1); desenha(); }
      else if (e.key === 'Enter' && ops[sel]) { const c = ops[sel]; fechar(); abrirArquivo(c); }
    });
    lista.addEventListener('click', (e) => { const o = e.target.closest('[data-i]'); if (o) { const c = ops[+o.dataset.i]; fechar(); abrirArquivo(c); } });
    desenha();
    inp.focus();
  }

  /* ============================================================ busca */
  function ligarBusca() {
    let t = null;
    const roda = () => {
      const q = $('#nc-busca').value;
      const box = $('#nc-busca-res');
      if (!q.trim()) { box.innerHTML = ''; return; }
      box.innerHTML = '<div class="nc-vazio">Procurando…</div>';
      api('GET', '/fs/buscar?' + qs({ raiz: st.raiz, q, regex: $('#nc-busca-re').classList.contains('on') ? 1 : 0,
        maiusculas: $('#nc-busca-aa').classList.contains('on') ? 1 : 0 })).then((l) => {
        if (!l.length) { box.innerHTML = '<div class="nc-vazio">Nada encontrado.</div>'; return; }
        const por = new Map();
        l.forEach((r) => { if (!por.has(r.arquivo)) por.set(r.arquivo, []); por.get(r.arquivo).push(r); });
        box.innerHTML = '<div class="nc-vazio">' + l.length + (l.length >= 1000 ? '+' : '') + ' resultados em ' + por.size + ' arquivos</div>' +
          [...por].map(([arq, rs]) => '<div class="nc-res-arq" data-a="' + esc(arq) + '">' + marcaExt(base(arq)) + esc(base(arq)) +
            '<small>' + esc(pai(arq)) + '</small></div>' + rs.map((r) => {
              const ini = Math.max(0, r.coluna - 1 - 40), tx = r.texto.slice(ini);
              const a = r.coluna - 1 - ini, b = r.fim - 1 - ini;
              return '<div class="nc-res-lin" data-a="' + esc(arq) + '" data-l="' + r.linha + '" data-c="' + r.coluna + '" data-f="' + r.fim + '">' +
                (ini ? '…' : '') + esc(tx.slice(0, a).trimStart()) + '<mark>' + esc(tx.slice(a, b)) + '</mark>' + esc(tx.slice(b)) + '</div>';
            }).join('')).join('');
      }).catch((e) => { box.innerHTML = '<div class="nc-vazio">' + esc(e.message) + '</div>'; });
    };
    $('#nc-busca').addEventListener('input', () => { clearTimeout(t); t = setTimeout(roda, 300); });
    $('#nc-busca').addEventListener('keydown', (e) => { if (e.key === 'Enter') roda(); });
    ['#nc-busca-aa', '#nc-busca-re'].forEach((s) => $(s).addEventListener('click', function () { this.classList.toggle('on'); roda(); }));
    $('#nc-busca-res').addEventListener('click', (e) => {
      const l = e.target.closest('[data-l]');
      if (l) abrirArquivo(l.dataset.a, +l.dataset.l, +l.dataset.c, +l.dataset.f);
      else { const a = e.target.closest('[data-a]'); if (a) abrirArquivo(a.dataset.a); }
    });
  }

  /* ============================================================ git */
  let gitTimer = null;
  function atualizarGitDepois() { clearTimeout(gitTimer); gitTimer = setTimeout(atualizarGit, 600); }
  function atualizarGit() {
    if (!st.raiz) return;
    api('GET', '/git/status?' + qs({ raiz: st.raiz })).then((g) => {
      st.git = g;
      const conta = $('#nc-ativ [data-vista=git] .conta');
      conta.textContent = g.arquivos.length; conta.classList.toggle('oculto', !g.arquivos.length);
      $('#nc-st-ramo span').textContent = g.repo ? g.ramo + (g.arquivos.length ? ' *' : '') : 'sem git';
      desenharGit(); desenharArvore();
    }).catch(() => {});
  }
  function desenharGit() {
    const box = $('#nc-git'), g = st.git;
    if (!box || !g) return;
    if (!g.repo) { box.innerHTML = '<div class="nc-vazio">Esta pasta não é um repositório Git. Para criar um, rode <code>git init</code> no terminal.</div>'; return; }
    const msg = $('#nc-git-msg') ? $('#nc-git-msg').value : '';
    box.innerHTML = '<div class="nc-git-ramo">' + ic('git', 'p') + esc(g.ramo) + '</div>' +
      '<div class="nc-campo"><textarea id="nc-git-msg" rows="2" placeholder="Mensagem do commit (Ctrl+Enter)"></textarea></div>' +
      '<div class="nc-git-acoes"><button class="nc-bt ouro" type="button" id="nc-git-commit"' + (g.arquivos.length ? '' : ' disabled') + '>Commit de tudo</button></div>' +
      (g.arquivos.length ? g.arquivos.map((a) => {
        const l = a.x === '?' ? 'U' : (a.y !== ' ' ? a.y : a.x);
        return '<div class="nc-no" data-g="' + esc(a.caminho) + '" data-l="' + l + '" style="padding-left:13px">' + marcaExt(base(a.caminho)) +
          '<span class="nome">' + esc(base(a.caminho)) + ' <small style="color:var(--mut2)">' + esc(pai(a.caminho)) + '</small></span>' +
          '<span class="g g-' + l + '">' + l + '</span></div>';
      }).join('') : '<div class="nc-vazio">Nada mudou desde o último commit.</div>');
    $('#nc-git-msg').value = msg;
    $('#nc-git-msg').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.ctrlKey) commit(); });
    $('#nc-git-commit').addEventListener('click', commit);
    $$('[data-g]', box).forEach((n) => {
      n.addEventListener('click', () => { if (n.dataset.l === 'D') toast('Arquivo apagado: nada para mostrar no editor.'); else abrirDiff(n.dataset.g, n.dataset.l === 'U' || n.dataset.l === 'A'); });
      n.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        menu(e.clientX, e.clientY, [['Abrir arquivo', () => abrirArquivo(n.dataset.g)], ['Ver mudanças', () => abrirDiff(n.dataset.g, n.dataset.l === 'U')], '-',
          ['Descartar mudanças', async () => {
            if (!(await dialogo('Descartar as mudanças em ' + n.dataset.g + '? ' + (n.dataset.l === 'U' ? 'O arquivo novo vai para a Lixeira.' : 'Ele volta ao último commit.'), null, 'Descartar'))) return;
            api('POST', '/git/descartar', { raiz: st.raiz, caminho: n.dataset.g, novo: n.dataset.l === 'U' }).then(atualizarGit).catch((er) => toast(er.message, true));
          }]]);
      });
    });
  }
  function commit() {
    const m = $('#nc-git-msg').value.trim();
    if (!m) return toast('Escreva a mensagem do commit.', true);
    api('POST', '/git/commit', { raiz: st.raiz, mensagem: m }).then((d) => { $('#nc-git-msg').value = ''; toast('Commit feito: ' + d.resumo); atualizarGit(); })
      .catch((e) => toast(e.message, true));
  }

  /* ============================================================ websocket e terminal */
  function conectarWs() {
    const ws = new WebSocket('ws://' + location.host + '/ws');
    st.ws = ws;
    ws.onopen = () => {
      $('#nc-st-ponto').classList.remove('off');
      if (st.raiz) ws.send(JSON.stringify({ t: 'observar', raiz: st.raiz }));
      if (st.termId) { st.termId = null; if (!$('#nc-term').classList.contains('oculto')) abrirTerminal(); }
    };
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.t === 'fs') { cacheArquivos = null; mudouNoDisco(m.caminhos); }
      else if (m.t === 'term-saida' && m.id === st.termId) st.term.write(m.d);
      else if (m.t === 'term-fim' && m.id === st.termId) { st.term.write('\r\n\x1b[90m[o terminal fechou; clique em + para abrir outro]\x1b[0m\r\n'); st.termId = null; }
      else if (m.t === 'erro') toast(m.texto, true);
      else if (m.t === 'lembrete') toast('Lembrete: ' + (m.titulos || []).join(', '));
      else if (m.t === 'sessao-mudou' || m.t === 'sessao-rodando') {
        // um lembrete rodou a conversa sem a janela: mostra o que aconteceu
        if (st.sessao && m.id === st.sessao.id && !st.rodandoCtrl) recarregarSessao();
        else if (st.raiz && m.t === 'sessao-mudou') listarConversas();
      }
    };
    ws.onclose = () => { $('#nc-st-ponto') && $('#nc-st-ponto').classList.add('off'); setTimeout(conectarWs, 1500); };
  }

  function alternarTerminal(mostrar) {
    const t = $('#nc-term');
    const vai = mostrar === undefined ? t.classList.contains('oculto') : mostrar;
    t.classList.toggle('oculto', !vai);
    $('#nc-arrasta-term').classList.toggle('oculto', !vai);
    $('#nc-ativ-term').classList.toggle('on', vai);
    if (vai) { if (!st.termId) abrirTerminal(); setTimeout(() => { layout(); st.term && st.term.focus(); }, 0); }
    else { setTimeout(layout, 0); st.editor && st.editor.focus(); }
  }

  function abrirTerminal(subpasta) {
    if (!st.term) {
      st.term = new window.Terminal({
        fontFamily: '"Cascadia Mono", "Cascadia Code", Consolas, monospace', fontSize: 13, cursorBlink: true, scrollback: 5000, allowProposedApi: true,
        theme: { background: '#100e0c', foreground: '#ddd5c6', cursor: '#e7c069', cursorAccent: '#100e0c', selectionBackground: '#c8962e55',
          black: '#1c1916', red: '#e29a8a', green: '#8cc79a', yellow: '#e7c069', blue: '#8fb8c9', magenta: '#b39ddb', cyan: '#8fc9c0', white: '#ddd5c6',
          brightBlack: '#6f6656', brightRed: '#f0b3a6', brightGreen: '#a8dbb3', brightYellow: '#f2d48f', brightBlue: '#acd0de', brightMagenta: '#cbb8ec', brightCyan: '#a8ddd5', brightWhite: '#f5efe3' },
      });
      st.fit = new window.FitAddon.FitAddon();
      st.term.loadAddon(st.fit);
      st.term.open($('#nc-term-corpo'));
      st.term.onData((d) => { if (st.termId && st.ws.readyState === 1) st.ws.send(JSON.stringify({ t: 'term-escrever', id: st.termId, d })); });
      st.term.onResize(({ cols, rows }) => { if (st.termId && st.ws.readyState === 1) st.ws.send(JSON.stringify({ t: 'term-tamanho', id: st.termId, cols, rows })); });
      new ResizeObserver(() => layout()).observe($('#nc-term-corpo'));
      st.term.attachCustomKeyEventHandler((e) => {
        if (e.ctrlKey && e.key === '`') return false;  // o atalho global fecha o terminal (aqui so' nao deixa o xterm engolir)
        if (e.type === 'keydown' && e.ctrlKey && e.key === 'c' && st.term.hasSelection()) { navigator.clipboard.writeText(st.term.getSelection()); return false; }
        if (e.type === 'keydown' && e.ctrlKey && e.key === 'v') { navigator.clipboard.readText().then((t) => st.term.paste(t)); return false; }
        return true;
      });
    }
    $('#nc-term').classList.remove('oculto'); $('#nc-arrasta-term').classList.remove('oculto'); $('#nc-ativ-term').classList.add('on');
    setTimeout(() => {
      layout();
      st.termId = 't' + Date.now();
      st.term.reset();
      const raiz = subpasta ? st.raiz + '\\' + subpasta.replace(/\//g, '\\') : st.raiz;
      st.ws.send(JSON.stringify({ t: 'term-abrir', id: st.termId, raiz, cols: st.term.cols, rows: st.term.rows }));
      st.term.focus();
    }, 0);
  }
  function fecharTerminal() { if (st.termId && st.ws.readyState === 1) st.ws.send(JSON.stringify({ t: 'term-fechar', id: st.termId })); st.termId = null; }

  /* ============================================================ agente */
  const PERM = [['leitura', 'Somente leitura'], ['perguntar', 'Pedir antes de mudar'], ['editar', 'Editar sem perguntar'], ['total', 'Acesso total']];
  const RACIOCINIO = [['auto', 'Raciocínio: automático'], ['desligado', 'Raciocínio: desligado'], ['baixo', 'Raciocínio: baixo'], ['medio', 'Raciocínio: médio'], ['alto', 'Raciocínio: alto']];
  const COMANDOS = [
    ['plano', 'Liga o modo plano: o agente investiga e propõe antes de mudar', '[pedido]'],
    ['objetivo', 'Define um objetivo: o agente segue até cumprir', '<texto>'],
    ['compactar', 'Resume a conversa para liberar contexto', ''],
    ['modelo', 'Troca o modelo desta conversa', '<nome>'],
    ['modo', 'Permissões: leitura, perguntar, editar ou total', '<modo>'],
    ['internet', 'Libera ou bloqueia a internet nesta conversa', ''],
    ['contexto', 'Mostra o que o modelo está vendo', ''],
    ['mcp', 'Servidores MCP deste projeto: ver e permitir', ''],
    ['lembretes', 'Mostra os lembretes desta conversa', ''],
    ['renomear', 'Renomeia a conversa', '<título>'],
    ['duplicar', 'Copia a conversa para seguir por outro caminho', ''],
    ['exportar', 'Baixa a conversa em Markdown', ''],
    ['nova', 'Começa uma conversa nova', ''],
    ['ajuda', 'Lista os comandos', ''],
  ];
  let skillsCache = null, pensamento = null;

  const ajustar = (corpo) => api('POST', '/sessao/ajustes', Object.assign({ id: st.sessao.id }, corpo)).then((d) => { Object.assign(st.sessao, d); pintarOpcoes(); return d; });

  function ligarAgente() {
    const txt = $('#nc-ag-txt');
    txt.addEventListener('input', () => { txt.style.height = 'auto'; txt.style.height = Math.min(180, txt.scrollHeight) + 'px'; autocompletar(); });
    txt.addEventListener('keydown', (e) => {
      if (teclaAutocompletar(e)) return;
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); enviar(); }
    });
    txt.addEventListener('blur', () => setTimeout(fecharAc, 150));
    $('#nc-ag-env').addEventListener('click', () => (st.rodandoCtrl ? parar() : enviar()));
    $('#nc-ag-nova').addEventListener('click', novaConversa);
    $('#nc-ag-menu').addEventListener('click', (e) => menuConversa(e.currentTarget));
    $('#nc-ag-conv').addEventListener('change', function () { if (!st.rodandoCtrl) api('GET', '/sessao?id=' + this.value).then(carregarSessao); });
    $('#nc-ag-modelo').addEventListener('change', function () { ajustar({ modelo: this.value }).then((d) => { $('#nc-st-modelo').textContent = d.modelo; }); });
    $('#nc-ag-perm').addEventListener('change', function () { ajustar({ modo: this.value }); });
    $('#nc-ag-rac').addEventListener('change', function () { ajustar({ raciocinio: this.value }); });
    $('#nc-ag-plano').addEventListener('click', () => ajustar({ planejando: !st.sessao.planejando }));
    $('#nc-ag-compactar').addEventListener('click', compactarAgora);
    $('#nc-trilha').addEventListener('click', (e) => {
      const b = e.target.closest('[data-abre]'); if (b) abrirArquivo(b.dataset.abre);
      const d = e.target.closest('[data-duplicar]'); if (d) duplicar(+d.dataset.duplicar);
    });
    api('GET', '/modelos').then((d) => { st.modelos = d.modelos || []; pintarOpcoes(); }).catch(() => {});
  }

  function novaConversa() { return api('POST', '/sessoes', { pasta: st.raiz }).then((d) => api('GET', '/sessao?id=' + d.id)).then(carregarSessao); }

  function pintarOpcoes() {
    const s = st.sessao;
    if (!s || !$('#nc-ag-modelo')) return;
    let l = st.modelos.length ? st.modelos : [{ nome: s.modelo, ferramentas: true }];
    if (!l.some((m) => m.nome === s.modelo)) l = [{ nome: s.modelo, ferramentas: true }].concat(l);
    $('#nc-ag-modelo').innerHTML = l.map((m) => '<option value="' + esc(m.nome) + '"' + (m.nome === s.modelo ? ' selected' : '') + '>' +
      esc(m.provedor ? m.nome.replace('::', ' › ') : m.nome) + (m.ferramentas === false ? ' (sem ferramentas)' : '') + '</option>').join('');
    $('#nc-ag-perm').innerHTML = PERM.map(([v, t]) => '<option value="' + v + '"' + (v === s.modo ? ' selected' : '') + '>' + t + '</option>').join('');
    const pensa = (st.modelos.find((m) => m.nome === s.modelo) || {}).pensa;
    $('#nc-ag-rac').classList.toggle('oculto', !pensa);
    $('#nc-ag-rac').innerHTML = RACIOCINIO.map(([v, t]) => '<option value="' + v + '"' + (v === s.raciocinio ? ' selected' : '') + '>' + t + '</option>').join('');
    const pb = $('#nc-ag-plano');
    pb.setAttribute('aria-pressed', String(!!s.planejando));
    pb.classList.toggle('on', !!s.planejando);
    pb.title = s.planejando ? 'Modo plano ligado: o agente só investiga e propõe um plano. Clique para desligar.' : 'Modo plano: o agente investiga e propõe um plano antes de mudar qualquer coisa';
    $('#nc-st-modelo').textContent = s.modelo;
    $('#nc-agente').classList.toggle('planejando', !!s.planejando);
    pintarObjetivo(s.objetivo);
    pintarTarefas(s.tarefas);
    pintarContexto(s.tokens, s.limite);
    pintarJobs(s.jobs);
    pintarLembretes(s.lembretes);
  }

  function pintarContexto(tokens, limite) {
    limite = limite || 16384;
    const box = $('#nc-ag-ctx');
    if (!box) return;
    const f = Math.min(1, (tokens || 0) / limite);
    $('i', box).style.width = (f * 100).toFixed(1) + '%';
    $('i', box).className = f > 0.75 ? 'alto' : '';
    const k = (n) => (n >= 1000 ? (n / 1000).toFixed(1).replace('.', ',') + ' mil' : String(n || 0));
    $('span', box).textContent = 'Contexto: ' + k(tokens) + ' de ' + k(limite) + ' tokens';
  }

  function pintarObjetivo(o) {
    const box = $('#nc-ag-obj');
    if (!o) { box.classList.add('oculto'); return; }
    box.classList.remove('oculto');
    const texto = o.objective || o.texto || '';
    const fase = o.phase || (o.estado === 'feito' ? 'complete' : 'paused');
    const rodada = o.roundsStarted ? ', rodada ' + o.roundsStarted + ' de ' + o.maxGoalRounds : '';
    const rotulo = { complete: '✓ Objetivo cumprido', paused: 'Objetivo pausado', blocked: 'Objetivo bloqueado' }[fase] ||
      (o.armado ? 'Objetivo' + rodada : 'Objetivo parado' + rodada);
    const pode = fase === 'active' && o.armado ? 'pausar' : fase !== 'complete' ? 'retomar' : '';
    box.className = 'fase-' + fase;
    box.innerHTML = '<span class="' + (fase === 'complete' ? 'ok' : fase === 'blocked' ? 'mau' : '') + '">' + esc(rotulo) + '</span>' + esc(texto) +
      (o.blockedReason ? '<small>' + esc(o.blockedReason.message) + '</small>' : '') +
      (pode ? '<button type="button" class="acao" data-acao="' + pode + '" title="' + (pode === 'pausar' ? 'Para as rodadas automáticas' : 'O agente volta a trabalhar no objetivo no próximo pedido') + '">' +
        (pode === 'pausar' ? 'Pausar' : 'Retomar') + '</button>' : '') +
      '<button type="button" class="x" title="Tirar o objetivo">×</button>';
    $('.x', box).addEventListener('click', () => ajustar({ objetivo: '' }));
    const ac = $('.acao', box);
    if (ac) ac.addEventListener('click', () => ajustar({ objetivoAcao: ac.dataset.acao }).then(() => {
      if (ac.dataset.acao === 'retomar') toast('Objetivo retomado: o agente segue nele no próximo pedido (por exemplo, "continue").');
    }));
  }

  function pintarLembretes(l) {
    const box = $('#nc-ag-lem');
    if (!box) return;
    l = l || [];
    box.classList.toggle('oculto', !l.length);
    const quando = (iso) => {
      const d = new Date(iso), hoje = new Date();
      const h = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
      return d.toDateString() === hoje.toDateString() ? 'hoje, ' + h : d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) + ', ' + h;
    };
    const tipo = { every: 'repete', daily: 'todo dia', weekly: 'toda semana', cron: 'repete' };
    box.innerHTML = l.map((x) => '<div class="l"><i>⏰</i><b>' + esc(x.title) + '</b><span>' + esc(quando(x.scheduledAt)) +
      (tipo[x.kind] ? ' (' + tipo[x.kind] + ')' : '') + '</span><button type="button" data-lem="' + esc(x.id) + '" title="Apagar o lembrete">×</button></div>').join('');
    $$('[data-lem]', box).forEach((b) => b.addEventListener('click', () => api('POST', '/lembretes/apagar', { id: st.sessao.id, lembrete: b.dataset.lem })
      .then(() => api('GET', '/sessao?id=' + st.sessao.id)).then((s) => pintarLembretes(s.lembretes))));
  }

  function recarregarSessao() {
    const t2 = $('#nc-trilha'), embaixo = t2.scrollHeight - t2.scrollTop - t2.clientHeight < 40;
    return api('GET', '/sessao?id=' + st.sessao.id).then((s) => { carregarSessao(s); if (!embaixo) t2.scrollTop = 0; });
  }

  function pintarTarefas(l) {
    const box = $('#nc-ag-tarefas');
    l = l || [];
    if (!l.length) { box.classList.add('oculto'); return; }
    box.classList.remove('oculto');
    const feitas = l.filter((t) => t.status === 'completed').length;
    box.innerHTML = '<div class="tt">Tarefas <span>' + feitas + ' de ' + l.length + '</span></div>' + l.map((t) =>
      '<div class="t ' + t.status + '"><i>' + (t.status === 'completed' ? '✓' : t.status === 'in_progress' ? '›' : '') + '</i>' + esc(t.content) + '</div>').join('');
  }

  function pintarJobs(l) {
    const box = $('#nc-ag-jobs');
    l = (l || []).filter((j) => j.rodando);
    box.classList.toggle('oculto', !l.length);
    box.innerHTML = l.map((j) => '<div class="l"><i class="ponto"></i><code title="' + esc(j.comando) + '">' + esc(j.descricao || j.comando) + '</code><span>' + j.id + '</span>' +
      '<button type="button" data-job="' + j.id + '">Parar</button></div>').join('');
    $$('[data-job]', box).forEach((b) => b.addEventListener('click', () => api('POST', '/jobs/parar', { id: st.sessao.id, job: b.dataset.job })
      .then(() => api('GET', '/sessao?id=' + st.sessao.id)).then((s) => pintarJobs(s.jobs))));
  }

  function carregarSessao(s) {
    st.sessao = s;
    st.vivo = null; pensamento = null;
    pintarOpcoes();
    listarConversas();
    const tr = $('#nc-trilha');
    tr.innerHTML = '';
    s.eventos.forEach((e, i) => evento(e, true, i));
    if (!s.eventos.length) tr.innerHTML = '<div class="nc-nota" data-vazio>Peça o que quiser sobre este projeto. Exemplos:<br>' +
      '"explique como este projeto está organizado"<br>"rode os testes e corrija o que falhar"<br>' +
      '<b>/plano</b> antes do pedido faz o agente propor um plano primeiro. <b>@</b> anexa um arquivo.<br>' +
      'Selecione um trecho no editor e aperte Ctrl+L para perguntar sobre ele.</div>';
    pintarMudancas(s.mudancas);
    estadoEnvio(s.rodando);
    tr.scrollTop = tr.scrollHeight;
  }

  function listarConversas() {
    return api('GET', '/sessoes?' + qs({ pasta: st.raiz })).then((l) => {
      $('#nc-ag-conv').innerHTML = l.map((x) => '<option value="' + x.id + '"' + (x.id === st.sessao.id ? ' selected' : '') + '>' + esc(x.titulo) + '</option>').join('');
    });
  }

  function menuConversa(btn) {
    const r = btn.getBoundingClientRect();
    menu(r.left - 150, r.bottom + 4, [
      ['Renomear', renomearConversa], ['Duplicar a conversa', () => duplicar()], ['Exportar em Markdown', exportarConversa],
      ['Ver o que o modelo está vendo', inspetor], ['Buscar nas conversas', buscarConversas], ['Compactar agora', compactarAgora], '-',
      ['Apagar a conversa', apagarConversa]]);
  }
  async function renomearConversa(titulo) {
    const t = typeof titulo === 'string' && titulo ? titulo : await dialogo('Nome da conversa', st.sessao.titulo);
    if (!t) return;
    api('POST', '/sessao/renomear', { id: st.sessao.id, titulo: t }).then(() => { st.sessao.titulo = t; listarConversas(); });
  }
  function duplicar(ate) {
    api('POST', '/sessao/duplicar', { id: st.sessao.id, ate }).then((d) => api('GET', '/sessao?id=' + d.id)).then((s) => {
      carregarSessao(s); toast(ate === undefined ? 'Conversa duplicada.' : 'Nova conversa a partir deste pedido: o que veio depois ficou na original.');
    }).catch((e) => toast(e.message, true));
  }
  function exportarConversa() {
    const a = document.createElement('a');
    a.href = '/sessao/exportar?id=' + st.sessao.id; a.download = ''; document.body.appendChild(a); a.click(); a.remove();
  }
  async function apagarConversa() {
    if (!(await dialogo('Apagar a conversa "' + st.sessao.titulo + '"? Os arquivos do projeto não mudam.', null, 'Apagar'))) return;
    api('POST', '/sessao/apagar', { id: st.sessao.id }).then(() => api('GET', '/sessoes?' + qs({ pasta: st.raiz })))
      .then((l) => (l.length ? api('GET', '/sessao?id=' + l[0].id).then(carregarSessao) : novaConversa())).catch((e) => toast(e.message, true));
  }
  function compactarAgora() {
    if (st.rodandoCtrl) return toast('Espere o agente terminar para compactar.', true);
    toast('Compactando a conversa…');
    api('POST', '/compactar', { id: st.sessao.id }).then((d) => {
      if (d.evento) { evento(d.evento); pintarContexto(d.evento.depois, d.evento.limite); } else toast('A conversa ainda é curta: nada para compactar.');
    }).catch((e) => toast(e.message, true));
  }
  function modal(titulo, html) {
    const d = document.createElement('div');
    d.id = 'nc-modal';
    d.innerHTML = '<div><div class="cab"><b>' + esc(titulo) + '</b><button type="button" aria-label="Fechar">×</button></div><div class="corpo">' + html + '</div></div>';
    document.body.appendChild(d);
    const fechar = () => d.remove();
    $('.cab button', d).addEventListener('click', fechar);
    d.addEventListener('mousedown', (e) => { if (e.target === d) fechar(); });
    d.addEventListener('keydown', (e) => { if (e.key === 'Escape') fechar(); });
    $('.cab button', d).focus();
    return d;
  }
  function inspetor() {
    api('GET', '/sessao/contexto?id=' + st.sessao.id).then((c) => {
      modal('O que o modelo está vendo (' + (c.tokens || 0) + ' de ' + c.limite + ' tokens no último passo)',
        '<details open><summary>Prompt de sistema</summary><pre>' + esc(c.sistema) + '</pre></details>' +
        c.mensagens.map((m, i) => '<details' + (i >= c.mensagens.length - 4 ? ' open' : '') + '><summary>' + (i + 1) + '. ' + esc(m.role) +
          (m.ferramenta ? ' (' + esc(m.ferramenta) + ')' : '') + ' <small>' + m.content.length + ' caracteres</small></summary><pre>' + esc(m.content) + '</pre></details>').join(''));
    }).catch((e) => toast(e.message, true));
  }
  /* Servidores MCP do projeto (.mcp.json) e globais (~/.nous/mcp.json). Os do
   * projeto rodam programas de quem fez o projeto: so' ligam com permissao. */
  function servidoresMcp() {
    api('GET', '/mcp?' + qs({ pasta: st.raiz })).then((l) => {
      const d = modal('Servidores MCP', l.length ? '<p class="nc-nota">As ferramentas destes servidores entram no agente como <code>mcp__servidor__ferramenta</code>. ' +
        'Os do projeto só ligam depois que você permite; se o arquivo mudar, a permissão cai.</p>' +
        l.map((x) => '<div class="nc-mcp"><b>' + esc(x.nome) + '</b><small>' + (x.origem === 'global' ? 'seu (~/.nous/mcp.json)' : 'do projeto') + '</small>' +
          '<code>' + esc(x.comando) + '</code>' + (x.origem === 'global' ? '<span class="ok">ligado</span>'
            : '<button class="nc-bt ' + (x.aprovado ? 'borda' : 'ouro') + '" type="button" data-mcp="' + esc(x.nome) + '" data-sim="' + (x.aprovado ? '0' : '1') + '">' +
              (x.aprovado ? 'Desligar' : 'Permitir') + '</button>') + '</div>').join('')
        : '<p class="nc-vazio">Nenhum servidor MCP. Crie um <code>.mcp.json</code> na pasta do projeto (o mesmo formato do Claude Code) ou <code>~/.nous/mcp.json</code> para todos os projetos:</p>' +
          '<pre>{\n  "mcpServers": {\n    "nome": { "command": "npx", "args": ["-y", "pacote-do-servidor"] }\n  }\n}</pre>');
      $$('[data-mcp]', d).forEach((b) => b.addEventListener('click', () => api('POST', '/mcp/aprovar', { pasta: st.raiz, nome: b.dataset.mcp, sim: b.dataset.sim === '1' })
        .then(() => { d.remove(); servidoresMcp(); toast(b.dataset.sim === '1' ? 'Permitido: as ferramentas entram no próximo pedido.' : 'Desligado.'); })));
    }).catch((e) => toast(e.message, true));
  }

  async function buscarConversas() {
    const q = await dialogo('Procurar nas conversas deste projeto', '');
    if (!q) return;
    api('GET', '/sessoes/buscar?' + qs({ q, pasta: st.raiz })).then((l) => {
      const d = modal('Conversas com "' + q + '"', l.length ? l.map((x) => '<button type="button" class="nc-rec" data-s="' + x.id + '"><b>' + esc(x.titulo) +
        '</b><small>' + esc(x.trecho || '') + '</small></button>').join('') : '<p class="nc-vazio">Nada encontrado.</p>');
      $$('[data-s]', d).forEach((b) => b.addEventListener('click', () => { d.remove(); api('GET', '/sessao?id=' + b.dataset.s).then(carregarSessao); }));
    });
  }

  function perguntarSobre(caminho) {
    alternarAgente(true);
    const t = $('#nc-ag-txt');
    t.value = 'Sobre @' + caminho + ' ';
    t.focus(); t.setSelectionRange(t.value.length, t.value.length);
  }
  function comSelecao() {
    const a = st.abas[st.ativa];
    const t = $('#nc-ag-txt');
    if (a && a.tipo === 'arquivo') {
      const sel = st.editor.getSelection();
      if (sel && !sel.isEmpty()) {
        const trecho = a.modelo.getValueInRange(sel);
        t.value = 'Em ' + a.caminho + ' (linhas ' + sel.startLineNumber + '-' + sel.endLineNumber + '):\n```\n' + trecho.slice(0, 3000) + '\n```\n';
      } else if (!t.value.trim()) t.value = 'Sobre @' + a.caminho + ' ';
      t.dispatchEvent(new Event('input'));
    }
    t.focus(); t.setSelectionRange(t.value.length, t.value.length);
  }

  /* ---------------- autocompletar: /comandos e @arquivos */
  let ac = null;  // {tipo, ini, itens, sel}
  function fecharAc() { $('#nc-ac')?.remove(); ac = null; }
  function autocompletar() {
    const t = $('#nc-ag-txt');
    const antes = t.value.slice(0, t.selectionStart);
    const mc = antes.match(/^\/([\w.-]*)$/);
    const ma = antes.match(/(?:^|\s)@([\w./\\-]*)$/);
    if (mc) {
      const q = mc[1].toLowerCase();
      const carrega = skillsCache ? Promise.resolve(skillsCache) : api('GET', '/skills?' + qs({ pasta: st.raiz })).then((l) => (skillsCache = l)).catch(() => []);
      carrega.then((sk) => {
        const itens = COMANDOS.map(([n, d, a]) => ({ v: '/' + n + ' ', t: '/' + n, d: d + (a ? ' ' + a : '') }))
          .concat(sk.filter((x) => x.usuario).map((x) => ({ v: '/' + x.nome + ' ', t: '/' + x.nome, d: 'Skill: ' + x.descricao })))
          .filter((x) => x.t.slice(1).toLowerCase().startsWith(q));
        mostrarAc('cmd', 0, itens);
      });
    } else if (ma) {
      const q = ma[1].toLowerCase().replace(/\\/g, '/');
      const carrega = cacheArquivos ? Promise.resolve(cacheArquivos) : api('GET', '/fs/arquivos?' + qs({ raiz: st.raiz })).then((l) => (cacheArquivos = l));
      carrega.then((l) => {
        const itens = l.filter((c) => !q || c.toLowerCase().includes(q)).sort((a, b) => (base(a).toLowerCase().startsWith(q) ? -1 : 0) - (base(b).toLowerCase().startsWith(q) ? -1 : 0))
          .slice(0, 12).map((c) => ({ v: '@' + c + ' ', t: base(c), d: pai(c) }));
        mostrarAc('arq', antes.length - ma[1].length - 1, itens);
      });
    } else fecharAc();
  }
  function mostrarAc(tipo, ini, itens) {
    if (!itens.length) { fecharAc(); return; }
    ac = { tipo, ini, itens, sel: 0 };
    let el = $('#nc-ac');
    if (!el) { el = document.createElement('div'); el.id = 'nc-ac'; $('#nc-ag-caixa').appendChild(el); }
    el.innerHTML = itens.map((x, i) => '<div class="nc-op' + (i === 0 ? ' on' : '') + '" data-i="' + i + '"><b>' + esc(x.t) + '</b><small>' + esc(x.d) + '</small></div>').join('');
    el.onmousedown = (e) => { const o = e.target.closest('[data-i]'); if (o) { e.preventDefault(); escolherAc(+o.dataset.i); } };
  }
  function teclaAutocompletar(e) {
    if (!ac) return false;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      ac.sel = (ac.sel + (e.key === 'ArrowDown' ? 1 : -1) + ac.itens.length) % ac.itens.length;
      $$('#nc-ac .nc-op').forEach((o, i) => o.classList.toggle('on', i === ac.sel));
      return true;
    }
    if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) { e.preventDefault(); escolherAc(ac.sel); return true; }
    if (e.key === 'Escape') { fecharAc(); return true; }
    return false;
  }
  function escolherAc(i) {
    const t = $('#nc-ag-txt');
    const it = ac.itens[i];
    const pos = t.selectionStart;
    if (ac.tipo === 'cmd') t.value = it.v + t.value.slice(pos);
    else t.value = t.value.slice(0, ac.ini) + it.v + t.value.slice(pos);
    const fim = ac.tipo === 'cmd' ? it.v.length : ac.ini + it.v.length;
    fecharAc();
    t.focus(); t.setSelectionRange(fim, fim);
  }

  /* ---------------- comandos de barra */
  function comando(texto) {
    const m = texto.match(/^\/([\w.-]+)\s*([\s\S]*)$/);
    if (!m) return false;
    const [, nome, resto] = m;
    const arg = resto.trim();
    switch (nome.toLowerCase()) {
      case 'plano': ajustar({ planejando: true }).then(() => { if (arg) enviarTexto(arg); else toast('Modo plano ligado: o próximo pedido vira um plano para você aprovar.'); }); return true;
      case 'objetivo':
        if (!arg) { toast('Escreva o objetivo depois do comando, por exemplo: /objetivo todos os testes passando', true); return true; }
        ajustar({ objetivo: arg }).then(() => enviarTexto('Objetivo: ' + arg)); return true;
      case 'compactar': compactarAgora(); return true;
      case 'modelo':
        if (!arg) { $('#nc-ag-modelo').focus(); return true; }
        ajustar({ modelo: arg }).then(() => toast('Modelo: ' + arg)); return true;
      case 'modo': {
        const v = { leitura: 'leitura', perguntar: 'perguntar', editar: 'editar', total: 'total' }[arg.toLowerCase()];
        if (!v) { toast('Use /modo leitura, perguntar, editar ou total.', true); return true; }
        ajustar({ modo: v }).then(() => toast('Permissões: ' + PERM.find((p) => p[0] === v)[1])); return true;
      }
      case 'internet': {
        const novo = st.sessao.internet !== true;
        ajustar({ internet: novo }).then(() => toast(novo ? 'Internet liberada nesta conversa.' : 'Internet bloqueada nesta conversa.')); return true;
      }
      case 'contexto': inspetor(); return true;
      case 'mcp': servidoresMcp(); return true;
      case 'lembretes': {
        const l = st.sessao.lembretes || [];
        if (!l.length) toast('Nenhum lembrete nesta conversa. Peça, por exemplo: "me lembre amanhã às 9h de rodar os testes".');
        else $('#nc-ag-lem').scrollIntoView({ block: 'nearest' });
        return true;
      }
      case 'renomear': renomearConversa(arg); return true;
      case 'duplicar': duplicar(); return true;
      case 'exportar': exportarConversa(); return true;
      case 'nova': novaConversa(); return true;
      case 'ajuda':
        modal('Comandos', '<div class="nc-atalho" style="grid-template-columns:auto 1fr">' + COMANDOS.map(([n, d, a]) =>
          '<span><code>/' + n + (a ? ' ' + esc(a) : '') + '</code></span><span>' + esc(d) + '</span>').join('') +
          '<span><code>@arquivo</code></span><span>Anexa o arquivo ao pedido</span><span><code>/nome-da-skill</code></span><span>Usa uma skill do projeto (.nous/skills)</span></div>');
        return true;
    }
    return false;  // /skill: vai para o agente, que injeta as instrucoes
  }

  /* ---------------- trilha */
  function trilha() { return $('#nc-trilha'); }
  function add(html) {
    const t = trilha();
    const w = document.createElement('div');
    w.innerHTML = html;
    const el = w.firstChild;
    t.insertBefore(el, $('#nc-vivo', t));
    return el;
  }
  function grupoPassos() {
    let ult = trilha().lastElementChild;
    if (ult && ult.id === 'nc-vivo') ult = ult.previousElementSibling;
    return ult && ult.classList.contains('nc-passos') ? ult : add('<div class="nc-passos"></div>');
  }
  function md(texto) {
    return String(texto || '').split(/```[a-zA-Z0-9_-]*\n?/).map((p, i) => {
      if (i % 2) return '<pre><code>' + esc(p.replace(/\n$/, '')) + '</code></pre>';
      const h = esc(p).replace(/`([^`\n]+)`/g, '<code>$1</code>').replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/^#{1,4} (.+)$/gm, '<b>$1</b>');
      return h.split(/\n{2,}/).map((bl) => {
        let out = '', texto = [], itens = [];
        const solta = () => {
          if (texto.length) { out += '<p>' + texto.join('<br>') + '</p>'; texto = []; }
          if (itens.length) { out += '<ul>' + itens.map((x) => '<li>' + x + '</li>').join('') + '</ul>'; itens = []; }
        };
        bl.trim().split('\n').forEach((l) => {
          if (/^\s*(?:[-*]|\d+\.) /.test(l)) { if (texto.length) solta(); itens.push(l.replace(/^\s*(?:[-*]|\d+\.) /, '')); }
          else { if (itens.length) solta(); if (l.trim()) texto.push(l.trim()); }
        });
        solta();
        return out;
      }).join('');
    }).join('');
  }
  function diffHtml(d) {
    return String(d || '').split('\n').map((l) => {
      const c = l[0] === '+' ? 'a' : l[0] === '-' ? 'd' : l.slice(0, 2) === '@@' ? 'h' : '';
      return c ? '<span class="' + c + '">' + esc(l) + '</span>' : esc(l) + '\n';
    }).join('');
  }
  function vivo(txt) {
    let v = $('#nc-vivo', trilha());
    if (!v) { v = document.createElement('div'); v.id = 'nc-vivo'; trilha().appendChild(v); }
    v.innerHTML = '<i></i>' + esc(txt);
  }
  function semVivo() { const v = $('#nc-vivo', trilha()); if (v) v.remove(); }
  function semTexto() { if (st.vivo) { st.vivo.remove(); st.vivo = null; } }
  function fecharPensamento() { if (pensamento) { pensamento.open = false; pensamento = null; } }

  function evento(e, historico, indice) {
    const t = trilha();
    const vz = $('[data-vazio]', t); if (vz) vz.remove();
    switch (e.t) {
      case 'voce': {
        if (e.origem === 'lembrete') { add('<div class="nc-lembrete"><b>⏰ Lembrete</b>' + esc(textoLembrete(e.texto)) + '</div>'); break; }
        // bolha + "Duplicar daqui" no mesmo bloco: o botao nao some quando o mouse desce ate' ele
        const el = add('<div class="nc-voce-w"><div class="nc-voce">' + esc(e.texto) + '</div></div>');
        if (historico && indice !== undefined && typeof e.msg === 'number') {
          const b = document.createElement('button'); b.type = 'button'; b.className = 'dup'; b.dataset.duplicar = indice;
          b.title = 'Começa uma conversa nova a partir daqui (para tentar outro caminho)'; b.textContent = 'Duplicar daqui';
          el.appendChild(b);
        }
        break;
      }
      case 'pensando': fecharPensamento(); vivo('Pensando' + (e.passo > 1 ? ', passo ' + e.passo : '')); break;
      case 'pensamento':
        if (!pensamento) { pensamento = add('<details class="nc-pens"><summary>Raciocínio</summary><div></div></details>'); }
        $('div', pensamento).textContent += e.d;
        break;
      case 'passo':
        pintarContexto(e.tokens, e.limite);
        $('#nc-vivo i') && ($('#nc-vivo').title = e.segundos + ' s, ' + e.tokens + ' tokens');
        break;
      case 'texto': fecharPensamento(); if (!st.vivo) st.vivo = add('<div class="nc-resp"></div>'); st.vivo.textContent += e.d; break;
      case 'limpar': semTexto(); break;
      case 'nota': semTexto(); add('<div class="nc-nota">' + esc(e.texto) + '</div>'); break;
      case 'resposta': semTexto(); fecharPensamento(); add('<div class="nc-resp">' + md(e.texto) + '</div>'); semVivo(); break;
      case 'ferramenta': {
        semTexto(); fecharPensamento();
        const g = grupoPassos();
        const p = document.createElement('div');
        p.className = 'nc-passo';
        p.dataset.id = e.id;
        p.innerHTML = '<button class="cab" type="button"><b>' + esc(e.resumo) + '</b><span class="r"></span></button>';
        const alvo = e.args && (e.args.file_path || e.args.path);
        const arq = alvo && /^(read|edit|write|lsp|read_file|edit_file|write_file)$/.test(e.nome) ? String(alvo).replace(/^[\\/.]+/, '').replace(/\\/g, '/') : '';
        if (arq) { const b = document.createElement('button'); b.className = 'abre'; b.type = 'button'; b.dataset.abre = arq; b.textContent = 'abrir'; $('.cab', p).appendChild(b); }
        g.appendChild(p);
        $('.cab', p).addEventListener('click', (ev) => { if (!ev.target.closest('.abre')) saida(p); });
        break;
      }
      case 'sub': {
        const p = $('.nc-passo[data-id="' + e.id + '"]', t); if (!p) break;
        let l = $('.subs', p); if (!l) { l = document.createElement('div'); l.className = 'subs'; p.insertBefore(l, $('pre', p)); }
        const d = document.createElement('div'); d.textContent = e.resumo; l.appendChild(d);
        break;
      }
      case 'resultado': {
        const el = $('.nc-passo[data-id="' + e.id + '"]', t); if (!el) break;
        el.classList.add(e.ok ? 'ok' : 'falhou');
        $('.r', el).textContent = e.resumo + (e.ms > 1500 ? ', ' + (e.ms / 1000).toFixed(1) + ' s' : '');
        el._saida = e.saida; el._diff = e.diff;
        if (e.diff || (!e.ok && !/^recusado|^bloqueado/.test(e.resumo))) saida(el, true);
        break;
      }
      case 'tarefas': pintarTarefas(e.tarefas); if (st.sessao) st.sessao.tarefas = e.tarefas; break;
      case 'objetivo': pintarObjetivo(e.objetivo); if (st.sessao) st.sessao.objetivo = e.objetivo; break;
      case 'modo-plano': if (st.sessao) { st.sessao.planejando = e.planejando; pintarOpcoes(); } break;
      case 'compactado':
        add('<div class="nc-nota nc-compacto">Conversa ' + (e.modo === 'resumo' ? 'resumida' : 'enxugada') + ' para caber no contexto: ' +
          Math.round(e.antes / 100) / 10 + ' mil → ' + Math.round(e.depois / 100) / 10 + ' mil tokens.</div>');
        break;
      case 'pede': cartaoPedido(e, historico); break;
      case 'lembretes': if (!historico) { if (st.sessao) st.sessao.lembretes = e.lembretes; pintarLembretes(e.lembretes); } break;  // ao recarregar vale a lista do servidor
      case 'entregas': cartaoEntregas(e); break;
      case 'diagnosticos': problemasDaEdicao(e); break;
      case 'mcp-pendente': cartaoMcp(e, historico); break;
      case 'aprovado': resolvido(e.id, e.ok, e.sempre, e.texto); break;
      case 'erro': semTexto(); add('<div class="nc-erro">' + esc(e.texto) + '</div>'); semVivo(); break;
      case 'desfeito': add('<div class="nc-nota">Desfeito: ' + esc((e.arquivos || []).join(', ') || 'nada') + ' voltou ao que era antes.</div>'); break;
      case 'fim': semVivo(); pintarMudancas(e.mudancas); break;
    }
    if (!historico) t.scrollTop = t.scrollHeight;
  }

  /* Erros que a edição do agente criou (o language server achou): sublinhados no
   * editor e uma linha na conversa. Lista vazia limpa as marcas do arquivo. */
  function marcarProblemas(modelo, itens) {
    if (!st.monaco) return;
    st.monaco.editor.setModelMarkers(modelo, 'nous-lsp', itens.map((i) => {
      const w = modelo.getWordAtPosition({ lineNumber: i.linha, column: i.coluna });
      return { severity: st.monaco.MarkerSeverity.Error, message: i.msg + (i.codigo ? ' (' + i.codigo + ')' : ''), source: 'Nous Code',
        startLineNumber: i.linha, startColumn: i.coluna, endLineNumber: i.linha, endColumn: w && w.endColumn > i.coluna ? w.endColumn : i.coluna + 1 };
    }));
  }
  function problemasDaEdicao(e) {
    if (e.itens.length) st.diag[e.arquivo] = e.itens; else delete st.diag[e.arquivo];
    const aba = st.abas.find((a) => a.tipo === 'arquivo' && a.caminho === e.arquivo);
    if (aba) marcarProblemas(aba.modelo, e.itens);
    if (!e.itens.length) return;
    const el = add('<div class="nc-nota nc-diag"><b>' + e.itens.length + (e.itens.length === 1 ? ' problema' : ' problemas') + ' em ' + esc(e.arquivo) + '</b> depois da edição' +
      e.itens.slice(0, 3).map((i) => '<br><a href="#" data-pabre="' + esc(e.arquivo) + '" data-linha="' + i.linha + '">linha ' + i.linha + '</a>: ' + esc(i.msg.slice(0, 140))).join('') + '</div>');
    el.querySelectorAll('a[data-pabre]').forEach((a) => a.addEventListener('click', (ev) => { ev.preventDefault(); abrirArquivo(a.dataset.pabre, Number(a.dataset.linha), 1); }));
  }

  function textoLembrete(t) {
    const um = /reminder_prompt_json: (.+)$/m.exec(t);
    if (um) { try { return JSON.parse(um[1]); } catch (x) { /* segue */ } }
    const varios = /reminders_json: (.+)$/m.exec(t);
    if (varios) { try { return JSON.parse(varios[1]).map((r) => r.reminder_prompt).join(' | '); } catch (x) { /* segue */ } }
    return t;
  }

  /* Arquivos que o agente entregou (present): abrir no editor ou no Windows. */
  function cartaoEntregas(e) {
    semTexto();
    const binario = /\.(docx?|xlsx?|pptx?|pdf|png|jpe?g|gif|webp|zip|odt|ods)$/i;
    const c = add('<div class="nc-entrega"><div class="t">Entregue' + ((e.arquivos || []).length > 1 ? 's' : '') + '</div>' + (e.arquivos || []).map((a) =>
      '<div class="a"><b>' + esc(base(a.caminho)) + '</b>' + (a.descricao ? '<span>' + esc(a.descricao) + '</span>' : '') +
      (binario.test(a.caminho) ? '' : '<button class="nc-bt borda" type="button" data-ed="' + esc(a.caminho) + '">Abrir no editor</button>') +
      '<button class="nc-bt borda" type="button" data-so="' + esc(a.caminho) + '">Abrir no Windows</button></div>').join('') + '</div>');
    $$('[data-ed]', c).forEach((b) => b.addEventListener('click', () => abrirArquivo(b.dataset.ed)));
    $$('[data-so]', c).forEach((b) => b.addEventListener('click', () => api('POST', '/fs/abrir-sistema', { raiz: st.raiz, caminho: b.dataset.so }).catch((x) => toast(x.message, true))));
  }

  /* O projeto tem servidores MCP que ainda nao foram permitidos. */
  function cartaoMcp(e, historico) {
    if (historico) {
      // ao recarregar a conversa: so' mostra se algum ainda espera permissao
      const lugar = add('<div class="nc-mcp-lugar"></div>');
      api('GET', '/mcp?' + qs({ pasta: st.raiz })).then((l) => {
        const falta = (e.servidores || []).filter((x) => l.some((y) => y.nome === x.nome && !y.aprovado));
        if (!falta.length) { lugar.remove(); return; }
        lugar.replaceWith(cartaoMcp(Object.assign({}, e, { servidores: falta })));
      }).catch(() => lugar.remove());
      return lugar;
    }
    const c = add('<div class="nc-pede mcp"><div class="t">Este projeto tem servidores MCP</div>' +
      '<p class="nc-nota">Eles rodam programas definidos no projeto. Só permita se você confia em quem fez o projeto.</p>' +
      (e.servidores || []).map((x) => '<pre>' + esc(x.nome) + ': ' + esc(x.comando) + '</pre>').join('') +
      '<div class="bt"><button class="nc-bt ouro" type="button" data-s>Permitir</button><button class="nc-bt borda" type="button" data-n>Agora não</button></div></div>');
    $('[data-s]', c).addEventListener('click', () => Promise.all((e.servidores || []).map((x) => api('POST', '/mcp/aprovar', { pasta: st.raiz, nome: x.nome, sim: true })))
      .then(() => { c.outerHTML = '<div class="nc-nota">Servidores MCP permitidos: as ferramentas entram no próximo pedido.</div>'; }).catch((x) => toast(x.message, true)));
    $('[data-n]', c).addEventListener('click', () => { c.outerHTML = '<div class="nc-nota">Servidores MCP não ligados. Use /mcp para permitir depois.</div>'; });
    return c;
  }

  /* ask_user_question: uma ou mais perguntas, com opcoes (uma ou varias) e resposta livre. */
  function cartaoPerguntas(e) {
    const html = '<div class="nc-pede perguntas" data-pede="' + e.id + '">' + (e.perguntas || []).map((q, i) =>
      '<div class="q" data-q="' + i + '">' + (q.titulo ? '<small>' + esc(q.titulo) + '</small>' : '') + '<div class="t">' + esc(q.pergunta) + '</div>' +
      (q.opcoes && q.opcoes.length ? '<div class="ops" role="' + (q.multipla ? 'group' : 'radiogroup') + '">' + q.opcoes.map((o) =>
        '<button class="op" type="button" role="' + (q.multipla ? 'checkbox' : 'radio') + '" aria-checked="false" data-op="' + esc(o.label) + '">' +
        '<b>' + esc(o.label) + '</b>' + (o.description ? '<span>' + esc(o.description) + '</span>' : '') + '</button>').join('') + '</div>' : '') +
      '<input class="livre-q" placeholder="' + (q.opcoes && q.opcoes.length ? 'ou escreva outra resposta' : 'sua resposta') + '"></div>').join('') +
      '<div class="bt"><button class="nc-bt ouro" type="button" data-s>Responder</button><button class="nc-bt borda" type="button" data-n>Pular</button></div></div>';
    const card = add(html);
    $$('.q', card).forEach((qd) => {
      const q = e.perguntas[Number(qd.dataset.q)];
      $$('.op', qd).forEach((b) => b.addEventListener('click', () => {
        if (!q.multipla) $$('.op', qd).forEach((x) => x.setAttribute('aria-checked', 'false'));
        b.setAttribute('aria-checked', String(!(q.multipla && b.getAttribute('aria-checked') === 'true')));
        if (!q.multipla && e.perguntas.length === 1 && !$('.livre-q', qd).value.trim()) $('[data-s]', card).click();
      }));
    });
    const resp = (pular) => e.perguntas.map((q, i) => {
      const qd = $('.q[data-q="' + i + '"]', card);
      const r = { id: q.id, selected: pular ? [] : $$('.op[aria-checked="true"]', qd).map((b) => b.dataset.op) };
      const livre = $('.livre-q', qd).value.trim();
      if (livre && !pular) r.custom = livre;
      return r;
    });
    $('[data-s]', card).addEventListener('click', () => responder(e.id, true, false, JSON.stringify(resp(false))));
    $('[data-n]', card).addEventListener('click', () => responder(e.id, true, false, JSON.stringify(resp(true))));
    $$('.livre-q', card).forEach((inp) => inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') $('[data-s]', card).click(); }));
    return card;
  }

  function cartaoPedido(e, historico) {
    semTexto(); fecharPensamento();
    if (e.tipo === 'perguntas') {
      const card = cartaoPerguntas(e);
      semVivo();
      if (!historico) { const f = $('.op, .livre-q', card); if (f) f.focus(); if ($('#nc').classList.contains('sem-agente')) alternarAgente(true); }
      return;
    }
    let html;
    if (e.tipo === 'plano') {
      html = '<div class="nc-pede plano" data-pede="' + e.id + '"><div class="t">Plano proposto</div><div class="nc-resp">' + md(e.plano) + '</div>' +
        '<textarea class="fb" rows="2" placeholder="O que mudar no plano (opcional)"></textarea>' +
        '<div class="bt"><button class="nc-bt ouro" type="button" data-s>Aprovar e executar</button><button class="nc-bt borda" type="button" data-n>Continuar planejando</button></div></div>';
    } else if (e.tipo === 'pergunta') {
      html = '<div class="nc-pede pergunta" data-pede="' + e.id + '"><div class="t">' + esc(e.pergunta) + '</div><div class="bt">' +
        (e.opcoes || []).map((o) => '<button class="nc-bt borda" type="button" data-op="' + esc(o) + '">' + esc(o) + '</button>').join('') + '</div>' +
        '<div class="livre"><input placeholder="ou escreva a sua resposta"><button class="nc-bt ouro" type="button" data-livre>Responder</button></div></div>';
    } else if (e.tipo === 'mcp') {
      html = '<div class="nc-pede" data-pede="' + e.id + '"><div class="t">Usar ' + esc(e.servidor) + ' › ' + esc(String(e.ferramenta).split('__').pop()) + '?</div>' +
        (e.descricao ? '<p class="nc-nota">' + esc(e.descricao) + '</p>' : '') + '<pre>' + esc(JSON.stringify(e.args, null, 1)) + '</pre>' +
        '<div class="bt"><button class="nc-bt ouro" type="button" data-s>Permitir</button><button class="nc-bt borda" type="button" data-sempre>Permitir sempre nesta conversa</button>' +
        '<button class="nc-bt borda" type="button" data-n>Recusar</button></div></div>';
    } else if (e.tipo === 'internet') {
      html = '<div class="nc-pede" data-pede="' + e.id + '"><div class="t">Usar a internet nesta conversa?</div>' +
        '<p class="nc-nota">O agente quer buscar ou ler <b>' + esc(e.alvo) + '</b>. Só o endereço ou a busca saem do seu computador; o código não.</p>' +
        '<div class="bt"><button class="nc-bt ouro" type="button" data-s>Permitir nesta conversa</button><button class="nc-bt borda" type="button" data-n>Não permitir</button></div></div>';
    } else {
      const titulo = e.tipo === 'comando' ? (e.descricao ? esc(e.descricao) : 'Rodar este comando?') : (e.novo ? 'Criar ' : 'Mudar ') + esc(e.arquivo) + '?';
      const det = e.tipo === 'comando' ? '<pre>' + esc(e.comando) + '</pre>' + (e.fundo ? '<p class="nc-nota">Vai rodar em segundo plano.</p>' : '')
        : '<pre class="nc-diff">' + diffHtml(e.diff) + '</pre>';
      html = '<div class="nc-pede" data-pede="' + e.id + '"><div class="t">' + titulo + (e.tipo === 'arquivo' ? '<span>+' + e.mais + ' −' + e.menos + '</span>' : '') + '</div>' + det +
        '<div class="bt"><button class="nc-bt ouro" type="button" data-s>' + (e.tipo === 'comando' ? 'Rodar' : 'Aplicar') + '</button>' +
        (e.tipo === 'comando' ? '<button class="nc-bt borda" type="button" data-sempre>Rodar sempre nesta conversa</button>' : '') +
        '<button class="nc-bt borda" type="button" data-n>Recusar</button></div></div>';
    }
    const card = add(html);
    const s = $('[data-s]', card); if (s) s.addEventListener('click', () => responder(e.id, true, false, e.tipo === 'plano' ? $('.fb', card).value : undefined));
    const n = $('[data-n]', card); if (n) n.addEventListener('click', () => responder(e.id, false, false, e.tipo === 'plano' ? $('.fb', card).value : undefined));
    const sm = $('[data-sempre]', card); if (sm) sm.addEventListener('click', () => responder(e.id, true, true));
    $$('[data-op]', card).forEach((b) => b.addEventListener('click', () => responder(e.id, true, false, b.dataset.op)));
    const lv = $('[data-livre]', card);
    if (lv) {
      const inp = $('.livre input', card);
      const vai = () => { if (inp.value.trim()) responder(e.id, true, false, inp.value.trim()); };
      lv.addEventListener('click', vai);
      inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') vai(); });
    }
    semVivo();
    if (!historico) {
      const foco = $('[data-s], [data-op], .livre input', card); if (foco) foco.focus();
      if ($('#nc').classList.contains('sem-agente')) alternarAgente(true);
    }
  }

  function saida(p, abrir) {
    let pre = $('pre', p);
    if (pre && !abrir) { pre.remove(); return; }
    if (pre || (!p._saida && !p._diff)) return;
    pre = document.createElement('pre');
    if (p._diff) { pre.className = 'nc-diff'; pre.innerHTML = diffHtml(p._diff); } else pre.textContent = p._saida;
    p.appendChild(pre);
  }
  function resolvido(id, ok, sempre, texto) {
    const c = $('[data-pede="' + id + '"]', trilha());
    if (!c) return;
    if (c.classList.contains('plano')) {
      c.classList.add('feito');
      $('.bt', c).outerHTML = '<p class="nc-nota">' + (ok ? 'Você aprovou o plano.' : 'Você pediu para continuar planejando' + (texto ? ': ' + esc(texto) : '.')) + '</p>';
      $('.fb', c)?.remove();
      return;
    }
    if (c.classList.contains('pergunta')) { c.outerHTML = '<div class="nc-nota">' + esc($('.t', c).textContent) + ' <b>' + esc(texto || '') + '</b></div>'; return; }
    if (c.classList.contains('perguntas')) {
      let l = [];
      try { l = JSON.parse(texto || '[]'); } catch (x) { /* resposta antiga */ }
      c.outerHTML = '<div class="nc-nota">' + $$('.q', c).map((qd, i) => {
        const r = l[i] || {};
        const v = (r.selected || []).concat(r.custom ? [r.custom] : []).join(', ');
        return esc($('.t', qd).textContent) + ' <b>' + esc(v || 'pulou') + '</b>';
      }).join('<br>') + '</div>';
      return;
    }
    if (ok) { if (sempre) add('<div class="nc-nota">Liberado: esse comando roda sem perguntar nesta conversa.</div>'); c.remove(); return; }
    c.outerHTML = '<div class="nc-nota">Você recusou: ' + esc($('.t', c).textContent.replace(/\?.*$/, '').replace(/\+\d+ −\d+$/, '')) + '.</div>';
  }
  function pintarMudancas(l) {
    const box = $('#nc-ag-mud');
    l = l || [];
    box.classList.toggle('oculto', !l.length);
    if (!l.length) { box.innerHTML = ''; return; }
    box.innerHTML = '<div class="l"><span>O agente mudou ' + l.length + (l.length === 1 ? ' arquivo' : ' arquivos') + '</span>' +
      '<button class="tudo" type="button" data-tudo>Desfazer tudo</button></div>' + l.map((a) =>
      '<div class="l"><b data-abre="' + esc(a.arquivo) + '">' + esc(a.arquivo) + '</b><span class="n"><span style="color:var(--verde)">+' + a.mais +
      '</span> <span style="color:var(--vermelho)">−' + a.menos + '</span></span><button type="button" data-desf="' + esc(a.arquivo) + '">Desfazer</button></div>').join('');
    $$('[data-abre]', box).forEach((b) => b.addEventListener('click', () => abrirArquivo(b.dataset.abre)));
    $$('[data-desf]', box).forEach((b) => b.addEventListener('click', () => desfazer(b.dataset.desf)));
    $('[data-tudo]', box).addEventListener('click', () => desfazer(null));
  }
  async function desfazer(arq) {
    if (!(await dialogo(arq ? 'Voltar ' + arq + ' ao que era antes desta conversa?' : 'Voltar todos os arquivos que o agente mudou ao que eram antes?', null, 'Desfazer'))) return;
    api('POST', '/desfazer', { id: st.sessao.id, arquivo: arq || undefined }).then((d) => {
      evento({ t: 'desfeito', arquivos: d.desfeitos }); pintarMudancas(d.mudancas);
    }).catch((e) => toast(e.message, true));
  }
  function estadoEnvio(trabalhando) {
    const b = $('#nc-ag-env');
    b.textContent = trabalhando ? 'Parar' : 'Enviar';
    b.classList.toggle('parar', !!trabalhando);
  }

  function enviar() {
    const txt = $('#nc-ag-txt');
    const t = txt.value.trim();
    if (!t || !st.sessao || st.rodandoCtrl) return;
    txt.value = ''; txt.style.height = 'auto'; fecharAc();
    if (t.startsWith('/') && comando(t)) return;
    enviarTexto(t);
  }
  function enviarTexto(t) {
    // salva antes: o agente le do disco
    st.abas.filter((a) => a.sujo).forEach((a) => { ativar(st.abas.indexOf(a)); salvarAtiva(); });
    st.rodandoCtrl = new AbortController();
    estadoEnvio(true); vivo('Pensando');
    fetch('/mensagem', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: st.sessao.id, texto: t }), signal: st.rodandoCtrl.signal })
      .then((r) => {
        if (!r.ok) return r.json().then((d) => { throw new Error(d.erro || 'erro ' + r.status); });
        const leitor = r.body.getReader(), dec = new TextDecoder();
        let buf = '';
        const ler = () => leitor.read().then((x) => {
          if (x.done) return;
          buf += dec.decode(x.value, { stream: true });
          let k;
          while ((k = buf.indexOf('\n')) >= 0) { const linha = buf.slice(0, k); buf = buf.slice(k + 1); if (linha.trim()) evento(JSON.parse(linha)); }
          return ler();
        });
        return ler();
      })
      .catch((e) => { if (e.name !== 'AbortError') evento({ t: 'erro', texto: e.message === 'Failed to fetch' ? 'O Nous Code parou de responder.' : e.message }); })
      .then(() => {
        st.rodandoCtrl = null; estadoEnvio(false); semVivo();
        // recarrega a conversa: titulo do modelo, "Duplicar daqui", jobs e tarefas atualizados
        const t2 = $('#nc-trilha'), embaixo = t2.scrollHeight - t2.scrollTop - t2.clientHeight < 40;
        api('GET', '/sessao?id=' + st.sessao.id).then((s) => { carregarSessao(s); if (!embaixo) t2.scrollTop = 0; });
      });
  }
  function responder(id, ok, sempre, texto) {
    resolvido(id, ok, sempre, texto);
    if (ok || texto) vivo('Trabalhando');
    api('POST', '/aprovar', { id: st.sessao.id, pedido: id, ok, sempre, texto }).catch(() => toast('Esse pedido expirou: o serviço foi reiniciado. Envie o pedido de novo.', true));
  }
  function parar() { api('POST', '/parar', { id: st.sessao.id }).catch(() => {}); }

  /* ============================================================ atalhos globais */
  document.addEventListener('keydown', (e) => {
    if (!st.raiz || $('#nc-dialogo')) return;
    const k = e.key.toLowerCase();
    if (e.ctrlKey && !e.shiftKey && k === 'p') { e.preventDefault(); paleta(); }
    else if (e.ctrlKey && e.shiftKey && k === 'f') { e.preventDefault(); vista('busca'); }
    else if (e.ctrlKey && e.shiftKey && k === 'e') { e.preventDefault(); vista('arquivos'); }
    else if (e.ctrlKey && e.shiftKey && k === 'g') { e.preventDefault(); vista('git'); }
    else if (e.ctrlKey && k === '`') { e.preventDefault(); alternarTerminal(); }
    else if (e.ctrlKey && !e.shiftKey && k === 'l') { e.preventDefault(); alternarAgente(true); comSelecao(); }
    else if (e.ctrlKey && !e.shiftKey && k === 'b' && !e.target.closest('.monaco-editor')) { e.preventDefault(); vista(st.vista, true); }
    else if (e.ctrlKey && k === 's') { e.preventDefault(); salvarAtiva(); }
  });
  addEventListener('beforeunload', (e) => { if (st.abas.some((a) => a.sujo)) { e.preventDefault(); e.returnValue = ''; } });

  /* ============================================================ partida */
  /* O carregador AMD do Monaco 0.57 (obsoleto) carrega o editor mas nem sempre
   * chama o retorno: espera o window.monaco aparecer, o que vier primeiro. */
  let comecou = false;
  function comecar() {
    if (comecou || !window.monaco || !window.monaco.editor) return;
    comecou = true;
    st.monaco = window.monaco;
    $('#nc-carregando').remove();
    const pasta = new URLSearchParams(location.search).get('pasta');
    if (pasta) abrirProjeto(pasta); else telaInicio();
  }
  window.require(['vs/editor/editor.main'], comecar);
  const espera = setInterval(() => { comecar(); if (comecou) clearInterval(espera); }, 50);
})();
