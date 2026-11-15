# Paletas de cores escolhíveis + ícone legível

Desenho aprovado pelo dono em 15/11/2026. O estudo visual que originou as paletas
está fora do git, em `C:\dev\pessoal\nous-teste\paletas\paletas.html`.

## Por quê

O dono não está mais gostando tanto do preto com dourado. Quis testar outras
paletas, gostou de todas e pediu que **o usuário escolha** qual usar. O ícone da
bandeja aparecia como ruído colorido. A coruja dourada fica, mas tem de ser
legível em qualquer fundo.

## Objetivos

- Sete paletas escolhíveis: Ouro (atual, padrão), Pitaya, Maracujá, Melancia,
  Ametista e Sol, Céu e Flamingo, Mata. Cada uma tem versão clara e escura, com os
  valores do estudo (todos passam 4,5:1 no texto, no botão e no link).
- A escolha vale para a instalação inteira e muda, juntos: tela principal (Open
  WebUI e os painéis do Nous), janela do Nous Code, página de pareamento do
  celular, tela de carregamento e relatórios de pesquisa.
- Troca na hora, sem recarregar a página.
- Claro, escuro ou igual ao Windows continua como hoje, independente da paleta.
- Ícone novo: selo escuro quadrado com a coruja dourada. Traço mais grosso só nos
  tamanhos pequenos e, de 16 a 24 px, a coruja sem a coroa. O arquivo `.ico` passa a
  ser legível pela bandeja (quadros pequenos em BMP). A bolinha de estado fica
  menor (34%).

## Fora

- As cores do comando `nous` no terminal (está no branch `feat/nous-motor`, ainda
  não mesclado).
- Paleta por usuário do Open WebUI: o Nous é pessoal, a escolha é da instalação.
- Misturar paletas ou criar uma paleta própria.
- Recolorir a coruja: ela é dourada em todas as paletas.

## O que não pode acontecer

- Piscar o dourado antes de a paleta escolhida aparecer, a cada página aberta.
- Algum painel continuar dourado numa paleta que não é Ouro (cor esquecida no código).
- Texto ilegível em alguma combinação de paleta com claro ou escuro.
- A paleta Ouro ficar diferente do que é hoje.

## Abordagens consideradas

1. **Variáveis de cor + escolha guardada no Nous (escolhida).** Todas as cores viram
   variáveis com nome (`--nous-*`), uma folha de estilos gerada traz as sete paletas
   e a escolha fica em `NousData\aparencia.json`, servida pelo monitor e lida pelo
   Nous Code. Tudo segue a mesma escolha.
2. Variáveis de cor + escolha só no navegador (`localStorage`): mais simples, mas o
   Nous Code (outra origem), o celular e a tela de carregamento ficariam com outra
   cor. Recusada.
3. Gerar uma folha de estilos por paleta na instalação: o usuário não conseguiria
   trocar depois. Recusada.

## Desenho

- **Fonte única:** `branding/paletas.json` traz, por paleta, nome, inspiração, as
  amostras, os valores de `claro` e `escuro` e o tom dos cinzas (matiz e croma em
  OKLCH). `branding/gerar_paletas.py` produz `branding/nous-paletas.css`
  (versionado) com:
  - os valores da paleta Ouro em `:root` e em `.dark` (padrão, sem atributo);
  - um bloco por paleta em `[data-nous-paleta="x"]` (claro) e em
    `.dark[data-nous-paleta="x"], .dark [data-nous-paleta="x"]` (escuro). O seletor
    também funciona dentro de um elemento qualquer, o que permite desenhar a prévia
    de cada paleta no próprio seletor;
  - a sobreposição dos cinzas do Open WebUI (`--color-gray-50` a `--color-gray-950`,
    que o 0.12 declara em OKLCH com croma 0) com o matiz da paleta. A paleta Ouro
    mantém croma 0, igual a hoje.
- **Variáveis:** `--nous-bg`, `--nous-lado`, `--nous-alto`, `--nous-linha`,
  `--nous-txt`, `--nous-mut`, `--nous-acc`, `--nous-acc-rgb` (trio para os tons
  translúcidos), `--nous-on-acc`, `--nous-acc-txt`, `--nous-sec`, `--nous-on-sec`,
  `--nous-det`, `--nous-on-det`, `--nous-ok`, `--nous-perigo`. As variáveis locais
  que já existem (`--nd-*`, `--pn-*`, as do Nous Code, as do celular) passam a
  apontar para elas, e as cores fixas que sobrarem no código viram variáveis.
- **Onde fica a escolha:** `NousData\aparencia.json` (`{"paleta": "pitaya"}`). Para
  o monitor (8990): `GET /aparencia` devolve a escolha e a lista de paletas;
  `POST /aparencia` grava, só com uma paleta conhecida. O Nous Code lê o mesmo
  arquivo pelo próprio servidor (8998). A página do celular e os relatórios
  recebem a paleta do servidor que os serve.
- **Sem piscar:** o `loader.js` aplica na hora a última paleta guardada em
  `localStorage` (`nous-paleta`) e depois confere com o monitor. Se o monitor
  disser outra, troca e atualiza o `localStorage`.
- **Onde escolher:** seção "Aparência" no painel "Seu Nous", com um cartão por
  paleta (prévia pequena desenhada com as próprias variáveis), mais o claro, escuro
  ou igual ao Windows. Os "Primeiros passos" ganham a lição "Escolha as cores", com
  o mesmo seletor, e o menu "?" ganha a entrada "Cores do Nous".
- **Nous Code:** fica sempre no escuro, usando a versão escura da paleta. O tema do
  editor (Monaco) e do terminal (xterm) é recalculado das variáveis quando a paleta
  muda. A janela confere a escolha ao ganhar foco.
- **Ícone:** `branding/gerar_icone.py` gera `nous.ico` com o selo em 16, 20, 24, 32,
  40, 48, 64, 128 e 256 px (quadros pequenos em BMP, o de 256 em PNG) e
  `nous-selo.png`. `apply_branding.py` usa o selo no `favicon.ico`, no `favicon.svg`,
  no `favicon-96x96.png`, no `apple-touch-icon.png` e nos ícones do app do celular.
  A logo e a tela de abertura continuam com a coruja sem fundo.
  `bandeja.ps1` desenha a bolinha com 34% do tamanho.

## Fica com quem constrói

Nomes internos, a ordem das tarefas, como cada módulo troca as cores fixas por
variáveis, o desenho do cartão de prévia, o texto exato da lição e os testes,
desde que cumpram os objetivos acima.

---

# Plano de execução

> **Para quem executa:** siga tarefa por tarefa (`- [ ]`). O desenho está acima. Os
> valores das paletas vêm do estudo (`nous-teste\paletas\paletas.html`, array `P`) e
> são copiados para `branding/paletas.json` na Tarefa 1.

**Objetivo:** sete paletas escolhíveis em todo o Nous e um ícone legível.

**Arquitetura:**
- `paletas.json` → `gerar_paletas.py` → duas folhas de estilo: `nous-paletas.css`
  (escuro pela classe `.dark`) e `nous-paletas-auto.css` (escuro por
  `prefers-color-scheme`, para páginas sem o JavaScript de tema).
- A escolha fica em `NousData\aparencia.json`. Quem a serve é `monitor/aparencia.py`,
  e o servidor do Nous Code lê o mesmo arquivo.
- Cada tela troca as cores fixas pelas variáveis `--nous-*`.

**Ferramentas:**
- Python 3.11 (aiohttp, Pillow 12.3, do venv `nous-teste\owui-012`);
- JavaScript puro nos módulos;
- TypeScript no Nous Code (`node --test`);
- Playwright em `tests-tela`.

## Restrições globais

- **Dependências e download:** nenhuma dependência nova de pip ou npm. O download
  total tem de ser pequeno (o dono está no 5G): só `npm ci --prefer-offline`, ou cópia
  do `node_modules` de outro worktree.
- **Nunca contra o app instalado:** nada de rodar launcher ou instalador do branch
  contra `%LOCALAPPDATA%\Programs\Nous`, `%USERPROFILE%\open-webui` ou `NousData`.
  Teste de tela só pelo `tests-tela`, que sobe um Open WebUI próprio na porta 8082.
- **Ids:** `ouro`, `pitaya`, `maracuja`, `melancia`, `ametista`, `ceu`, `mata`. O
  padrão é `ouro`, e id desconhecido também vira `ouro`.
- **Valores de Ouro:** os que os painéis já usam hoje (`_base.js`/`painel.js`):
  - claro: acc `#a87a1c`, acc-txt `#7f5b10`;
  - escuro: acc `#c8962e`, acc-txt `#e7c069`;
  - cinzas com croma 0.
- **Texto:** a interface fica em português, sem jargão. O código segue o estilo de
  cada arquivo.
- **Lint:** `tools/lint.ps1` tem de terminar em "Tudo certo". Rode `git add` antes e
  ponha o `nous-teste\owui-012\Scripts` na frente do PATH.

## Pontos de atenção (os testes ficam nas tarefas donas)

1. **Paleta salva que não existe mais** (`aparencia.json` com id antigo ou arquivo
   corrompido): cai em Ouro, sem erro. Tarefa 3.
2. **Monitor fora do ar quando a página abre:** fica a última paleta do
   `localStorage`, e a tela abre normalmente. Tarefa 4.
3. **Dourado esquecido em algum módulo:** um teste estático procura os valores do
   ouro fora de `paletas.json` e `nous-paletas*.css`. Tarefa 6.
4. **Contraste nos painéis** numa paleta clara (Céu) e numa escura tingida
   (Maracujá), nos dois temas: `temas.spec.js`, Tarefa 6.
5. **Trocar a paleta com o Nous Code aberto:** a janela segue a troca quando ganha
   foco. Tarefa 7.

---

### Tarefa 1: Paletas e gerador

**Arquivos:**
- criar: `branding/paletas.json`, `branding/gerar_paletas.py`,
  `branding/nous-paletas.css`, `branding/nous-paletas-auto.css`,
  `branding/testes/test_paletas.py`;
- mudar: `tools/lint.ps1`, para rodar `branding/testes`.

**Produz:**
- **`paletas.json`:**
  `{"padrao":"ouro","paletas":[{"id","nome","tag","inspira","amostras":[[nome,hex...]],"cinza":{"matiz":float,"croma":float},"claro":{...},"escuro":{...}}]}`.
  Cada modo tem as chaves `bg lado alto linha txt mut acc on_acc acc_txt sec det ok perigo`.
- **`gerar_paletas.py`:**
  - `carregar() -> dict`;
  - `tokens(paleta, modo) -> dict[str,str]`, que também calcula `acc-rgb`, `on-sec` e
    `on-det`;
  - `contraste(a, b) -> float`;
  - `css(dados, escuro="classe"|"auto") -> str`;
  - `main()`, que grava os dois `.css`.
- **Variáveis:** `--nous-bg --nous-lado --nous-alto --nous-linha --nous-txt
  --nous-mut --nous-acc --nous-acc-rgb --nous-on-acc --nous-acc-txt --nous-sec
  --nous-on-sec --nous-det --nous-on-det --nous-ok --nous-perigo` e
  `--color-gray-{50..950}`.
- **Cinzas:**
  - luminosidade igual à do Open WebUI: 50:98, 100:94, 200:92, 300:85, 400:77,
    500:69, 600:51, 700:42, 800:32, 850:27, 900:20, 950:16 %;
  - croma da paleta vezes 0,5 (50–300), 0,8 (400–600) e 1 (700–950);
  - matiz da paleta.

- [ ] Testes (falham antes):
  - `test_sete_paletas_e_padrao_ouro`;
  - `test_contraste_minimo`: para as seis novas, nos dois modos, txt/bg, mut/bg,
    acc_txt/bg, on_acc/acc, txt/alto e perigo/bg ≥ 4,5;
  - `test_css_tem_bloco_por_paleta`: `[data-nous-paleta="pitaya"]` e
    `.dark [data-nous-paleta="pitaya"]` presentes, e `:root` com os valores de Ouro
    claro;
  - `test_auto_usa_media_query`;
  - `test_ouro_cinza_neutro`: `--color-gray-900: oklch(20% 0 0)`;
  - `test_css_versionado_igual_ao_gerado`: o `.css` no git é igual ao que `css()`
    produz.
- [ ] Implementar e gerar os `.css`; testes passam; commit.

### Tarefa 2: Ícone em selo

**Arquivos:**
- criar: `branding/gerar_icone.py`, `branding/assets/nous-selo.png`,
  `branding/testes/test_icone.py`;
- regravar: `branding/assets/nous.ico`;
- mudar: `branding/apply_branding.py` (favicons) e `launchers/bandeja.ps1:118`.

**Produz:**
- `gerar_icone.py` com `selo(tam:int) -> Image`. Os parâmetros vêm da variante `selo`
  do estudo (`nous-teste\paletas\gerar_icones.py`):
  - traço +0,08 px até 32 px;
  - sem coroa abaixo de 32 px;
  - coruja com 84% da altura até 20 px, 80% acima disso;
  - fundo `#141210`, raio de 24%;
  - borda dourada a partir de 32 px.
- `main()`, que grava `nous.ico` (16, 20, 24, 32, 40, 48, 64, 128, 256;
  `bitmap_format="bmp"`) e `nous-selo.png` (512).

- [ ] Testes:
  - `test_ico_tem_os_tamanhos`;
  - `test_quadros_pequenos_em_bmp`: quadros menores que 256 não começam com a
    assinatura PNG;
  - `test_selo_opaco_no_fundo`: um pixel do fundo do selo é `#141210`.
- [ ] Implementar, gerar e conferir no PowerShell:
  `New-Object Drawing.Icon(ico, 16, 16)` desenha a coruja, não ruído.
- [ ] `apply_branding.py`: selo em `favicon.ico`, `favicon.svg`, `favicon-96x96.png`,
  `apple-touch-icon.png` e `web-app-manifest-*.png`.
- [ ] `bandeja.ps1`: bolinha com `0.34` do tamanho. Commit.

### Tarefa 3: Onde a escolha fica

**Arquivos:**
- criar: `monitor/aparencia.py`, `monitor/testes/test_aparencia.py`;
- mudar: `monitor/nous_monitor.py` (registrar as rotas) e `tools/lint.ps1`.

**Produz:**
- `ler(data_dir: Path) -> str`: id válido ou `"ouro"`.
- `gravar(data_dir: Path, paleta: str) -> str`: `ValueError` se a paleta for
  desconhecida; grava `aparencia.json` por arquivo temporário + `os.replace`.
- `ids() -> list[str]`, lidos de `paletas.json`.
- `add_routes(app, data_dir_fn)`:
  - `GET /aparencia` → `{"paleta": id, "paletas": [{"id","nome","tag"}]}`;
  - `POST /aparencia` com `{"paleta": id}` → mesmo formato; 400 se desconhecida;
  - `GET /aparencia.js` → `window.NOUS_PALETA="id";`. Serve a tela de carregamento,
    que é `file://` e não passa no CORS; a tag `<script>` não manda Origin.

- [ ] Testes: `test_padrao_sem_arquivo`, `test_grava_e_le`,
  `test_id_desconhecido_vira_ouro`, `test_arquivo_corrompido_vira_ouro`,
  `test_post_recusa_desconhecida` (400), `test_get_lista_sete`, `test_js`.
- [ ] Implementar, registrar no monitor, commit.

### Tarefa 4: Base da tela principal

**Arquivos:**
- `branding/apply_branding.py`: custom.css = `nous-paletas.css` + `nous-gold.css`;
- `branding/nous-gold.css`: ouro → variáveis;
- `branding/nous-loader.js`: módulo `NousPaleta`, logo no início do arquivo;
- `branding/modules/_base.js` e `branding/modules/painel.js`: `--nd-*`/`--pn-*`
  passam a apontar para `--nous-*`;
- `tests-tela/monitor-falso.js`: responde `/aparencia`;
- criar: `tests-tela/paletas.spec.js`.

**Produz:**
`window.NousPaleta = { atual() -> string, aplicar(id) -> void, escolher(id) -> Promise<void>, lista() -> Promise<[{id,nome,tag}]>, aoMudar(fn) }`.
- `aplicar` põe `data-nous-paleta` no `<html>` (e tira, para `ouro`) e grava
  `localStorage['nous-paleta']`.
- Ao carregar, aplica o que está no `localStorage` e depois confere `GET /aparencia`.
- `escolher` faz o `POST` e aplica.
- Toda troca dispara o evento `nous-paleta` no `window`.

- [ ] Testes de tela:
  - `aplica a paleta do monitor`: o monitor falso diz `pitaya` →
    `html[data-nous-paleta=pitaya]`, e o `--nous-acc` calculado é `#c2185b` no claro;
  - `sem piscar`: com `localStorage` = `ceu` e o monitor atrasado 2 s, o atributo já
    está em `ceu` no primeiro quadro;
  - `monitor fora do ar`: fica a paleta do `localStorage` e a tela abre;
  - `ouro sem atributo`.
- [ ] Implementar; rodar `npx playwright test paletas.spec.js` em `tests-tela`; commit.

### Tarefa 5: Onde o usuário escolhe

**Arquivos:**
- `branding/nous-loader.js`: `NousPaleta.seletor(host) -> {destruir}`, usado pelos
  dois lugares abaixo;
- `branding/modules/painel.js`: seção `#nous-pn-aparencia`, depois de
  "Ferramentas":
  - grade de cartões, cada um com o próprio `data-nous-paleta`, mostrando fundo,
    botão e amostras;
  - nome da paleta e marca de escolhida;
  - botões Claro / Escuro / Igual ao Windows, com
    `UI.setTheme('light'|'dark'|'system')`;
- `branding/modules/primeiros.js`: lição final "Escolha as cores", com o mesmo
  seletor, e o item `cores` no menu "?", que abre o painel nessa seção.

- [ ] Testes de tela:
  - `escolher no painel troca na hora`: clique em Maracujá → o atributo muda e
    `POST /aparencia {"paleta":"maracuja"}` chega ao monitor falso, sem recarregar;
  - `teclado`: os cartões são botões com `aria-pressed`, e Enter escolhe;
  - `licao das cores`: a lição aparece nas lições.
- [ ] Implementar; testes; commit.

### Tarefa 6: Fim do dourado fixo

**Arquivos:**
- `branding/nous-loader.js` e
  `branding/modules/{agenda,editor,inicio,tour,primeiros,email,comparar,escrita,documentos,acoes,skills,respostas,mensageiros,diagnostico,celular,research}.js`;
- criar: `branding/testes/test_sem_ouro_fixo.py`;
- mudar: `tests-tela/temas.spec.js`.

**Regra de troca:**

| Cor fixa de hoje | Vira |
|---|---|
| `rgba(200,150,46,X)` | `rgba(var(--nous-acc-rgb),X)` |
| `#c8962e`, `#a87a1c` | `var(--nous-acc)` |
| `#e7c069`, `#7f5b10`, `#8a6414` | `var(--nous-acc-txt)` |
| fundos de painel `#141210`, `#fff` | `var(--nous-bg)` |
| `#1c1916`, `#faf6ee` | `var(--nous-alto)` |
| `#ddd5c6`, `#2a251e` | `var(--nous-txt)` |
| `#958a76`, `#7a6f5d` | `var(--nous-mut)` |
| `rgba(231,192,105,X)`, `rgba(138,100,20,X)` usados em linhas | `var(--nous-linha)` |

Cor usada por JavaScript em canvas ou SVG lê
`getComputedStyle(document.documentElement).getPropertyValue('--nous-…')`.

- [ ] Teste estático (falha antes): `test_sem_ouro_fixo` varre `branding/**/*.js` e
  `branding/*.css` atrás de `c8962e|e7c069|a87a1c|7f5b10|8a6414|rgba\(200, ?150, ?46`,
  fora de `paletas.json` e `nous-paletas*.css`. Resultado esperado: zero ocorrências.
- [ ] `temas.spec.js`: além de Ouro, roda os painéis e diálogos em `ceu` e
  `maracuja`, nos dois temas, com o mesmo mínimo de 4,5.
- [ ] Converter (dá para dividir por arquivo); testes; commit.

### Tarefa 7: Nous Code

**Arquivos:**
- `code/servidor.ts` ou `code/ide.ts`:
  - servir `GET /aparencia`, lendo `DATA_DIR\aparencia.json`, com a mesma regra de id
    desconhecido = `ouro`;
  - servir `/marca/nous-paletas.css`;
- `code/ide/index.html`: `<html class="dark">` e o link da folha antes de `app.css`;
- `code/ide/app.css`: `--noite`, `--alto`, `--ouro`… → `--nous-*` da versão escura;
- `code/ide/app.js`:
  - tema do Monaco e do xterm recalculados das variáveis;
  - aplica primeiro o `localStorage`;
  - confere `/aparencia` ao abrir e quando a janela ganha foco;
- criar: `code/testes/aparencia.test.ts`.

- [ ] Testes: `GET /aparencia sem arquivo = ouro`; `le a escolha do arquivo`;
  `id desconhecido = ouro`; `/marca/nous-paletas.css` responde `text/css`.
- [ ] Implementar; `npm test` em `code/`; commit.

### Tarefa 8: Celular, carregamento e relatórios

**Arquivos:**
- `celular/nous_celular.py`, página de pareamento:
  - `--fundo`, `--ouro`… → `--nous-*`;
  - embute `nous-paletas-auto.css` e o `data-nous-paleta`, lido de `aparencia.json`
    a cada pedido;
  - teste em `celular/testes`.
- `launchers/loading.html`: link para `../branding/nous-paletas-auto.css` e
  `<script src="http://127.0.0.1:8990/aparencia.js">`, que aplica `NOUS_PALETA`.
- `search/nous_search/report.py`: `--gold`… → `var(--nous-…, valor antigo)`.
- `monitor/nous_monitor.py:h_research_view`: injeta `data-nous-paleta` e a folha
  automática; teste em `monitor/testes`.

- [ ] Testes: `pagina de parear usa a paleta salva`; `relatorio recebe a paleta`.
- [ ] Implementar; testes; commit.

### Tarefa 9: Fechamento

- [ ] `CHANGELOG.md`, em [Não lançado]: paletas, ícone e correção do `.ico`.
- [ ] `tools/lint.ps1` em "Tudo certo"; `tests-tela` inteiro; `npm test` em `code/`.
- [ ] Capturas das telas para o dono ver, em `tests-tela/saida/`: painel com o
  seletor, Pitaya escura, Céu clara e Nous Code em Maracujá.
- [ ] Revisão final do branch por um agente novo; corrigir o que for confirmado.
