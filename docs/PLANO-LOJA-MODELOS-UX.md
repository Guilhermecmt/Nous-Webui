# PLANO — Loja de Modelos no app + UX para leigos (v2.2.0)

> Plano escrito pelo Fable para execução pelo Sonnet. Leia tudo antes de começar.
> Princípios do projeto valem aqui: nunca mostrar terminal ao usuário final,
> idempotente, privado por padrão, registro direto no banco/serviços locais.

## Objetivo

Hoje o usuário leigo trava em dois pontos: (1) o instalador pergunta o nome do
modelo num prompt de terminal (`set /p` no `instalar.bat`) — exige conhecimento
técnico; (2) depois de instalado, baixar/trocar modelo exige navegar em
Admin Panel > Settings > Models do Open WebUI, em inglês.

Meta da v2.2.0: **a pessoa baixa o ZIP, dá 2 cliques, e todo o resto acontece
dentro do site** — uma "Loja de Modelos" com os modelos recomendados para a
máquina dela em primeiro, download com barra de progresso em 1 clique, e um
assistente de boas-vindas no primeiro uso. De quebra, corrigir em definitivo
dois bugs de campo: atalho que não aparece na área de trabalho e logo que não
é aplicada.

---

## Parte A — Loja de Modelos dentro do site

### A1. Catálogo curado — `monitor/catalog.json` (NOVO)

Arquivo JSON estático no repo, servido pelo monitor. Schema:

```json
{
  "version": 1,
  "models": [
    {
      "tag": "gemma4:12b",
      "name": "Gemma 4 12B",
      "desc": "Otimo para conversa, escrita e perguntas do dia a dia.",
      "download_gb": 8.0,
      "category": "conversa",
      "min_vram_gb": 8,
      "min_ram_cpu_gb": 16,
      "vision": false
    }
  ]
}
```

Popular com ~12–16 modelos do catálogo Ollama, descrições em PT-BR simples
(sem jargão: nada de "quantização Q4"). Incluir no mínimo:

- **Leves/CPU**: `gemma4:e4b` (~3 GB), `qwen3:4b`, `llama3.2:3b`
- **Equilibrados/GPU 8–12 GB**: `gemma4:12b`, `qwen3:8b`, `mistral`, `phi4`
- **Avançados/GPU 12–20 GB**: `qwen3:14b`, `deepseek-r1:14b`
- **Topo/GPU 20+ GB**: `qwen3:32b`, `deepseek-r1:32b`
- **Visão**: pelo menos 1 modelo com `"vision": true` (ex.: o gemma4 já tem visão — marcar corretamente conforme o catálogo Ollama)

Antes de gravar, **verifique tamanhos reais** em ollama.com/library (campo
`download_gb` é o tamanho do download, não da VRAM em uso). Os requisitos
(`min_vram_gb` / `min_ram_cpu_gb`) seguem a régua já usada em
`tools/check-system.ps1` e nos READMEs.

### A2. Backend — estender `monitor/nous_monitor.py`

O monitor (porta 8990) já tem CORS liberado, já fala com o Ollama via aiohttp
e já lê VRAM/RAM. Adicionar 4 rotas:

1. **`GET /hardware`** → `{ "gpu_name", "vram_gb", "ram_gb", "tier" }`
   - Reusar `_read_gpu()` (qwMemorySize do registro) + `Win32_ComputerSystem`.
   - `tier`: `"gpu-20"` (VRAM ≥ 20), `"gpu-12"` (≥ 12), `"gpu-8"` (≥ 8),
     `"cpu"` (sem GPU adequada). Mesma régua do check-system.

2. **`GET /catalog`** → catálogo + estado, pronto para a UI:
   - Lê `catalog.json` (mesma pasta do script).
   - Faz merge com `GET {OLLAMA}/api/tags`: marca `"installed": true/false`.
   - Calcula `"fit"` por modelo usando o tier: `"recomendado"` (encaixa no
     tier com folga), `"ok"` (roda mas apertado/CPU lenta), `"pesado"`
     (não recomendado). GPU: comparar `min_vram_gb` com a VRAM total.
     CPU: comparar `min_ram_cpu_gb` com a RAM total.
   - Retorna ordenado: recomendados primeiro, depois ok, depois pesados;
     dentro de cada grupo, menor download primeiro.

3. **`POST /pull` body `{"model": "tag"}`** → inicia download:
   - Proxy do `POST {OLLAMA}/api/pull` com `{"name": tag, "stream": true}`.
   - O stream NDJSON do Ollama traz linhas `{status, digest, total, completed}`.
     Agregar progresso por digest: `pct = soma(completed) / soma(total)`.
   - Guardar estado em dict global `_pulls[tag] = {status, pct, completed_gb,
     total_gb, error}`. Task asyncio em background; a rota responde na hora
     `{"started": true}`. Se já existe pull em andamento para a tag, responder
     `{"started": false, "reason": "em andamento"}` (singleton por modelo).
   - Em erro (sem internet, tag inexistente), `status: "erro"` com mensagem
     amigável em PT-BR.

4. **`GET /pull/status?model=tag`** → o estado acima
   (`{"status": "baixando", "pct": 0.42, ...}`; `"pronto"` quando concluído).

Sem dependências novas (aiohttp já vem no venv). Manter o middleware CORS
existente cobrindo as rotas novas.

### A3. Frontend — painel "Modelos" em `branding/nous-loader.js`

Seguir exatamente o padrão visual/estrutural dos painéis existentes
(monitor e "O que o Nous sabe"): vanilla JS, CSS injetado, cores douradas
(`#c8962e`/`#e7c069`), fundo `rgba(18,18,22,.92)`.

1. **Botão de entrada**: dentro do card Recursos, abaixo do botão "Parar
   modelos", um botão **"Baixar modelos"** (mesmo estilo). Abre o painel.

2. **Painel "Modelos"** (centro da tela, modal ~420px, scroll):
   - Busca `GET 8990/catalog` ao abrir.
   - Card por modelo: nome amigável em destaque, descrição, "~X GB de
     download", e badges:
     - `fit === "recomendado"` → selo dourado **"Recomendado para sua máquina"**
     - `fit === "ok"` → selo cinza "Roda na sua máquina"
     - `fit === "pesado"` → selo vermelho discreto "Pesado para sua máquina"
       (card ainda clicável — não bloquear, só avisar)
     - `installed` → selo verde "Instalado" (sem botão de download)
   - Botão **"Baixar"** → `POST /pull` → o card vira barra de progresso
     (mesmo estilo `.nous-mon-track/.nous-mon-fill`) com % e GB, atualizada
     via `GET /pull/status` a cada 2 s. O painel pode ser fechado e reaberto
     sem perder o progresso (estado vive no monitor).
   - Ao concluir: selo "Instalado" + texto "Clique no nome do modelo no topo
     da tela para usá-lo". O modelo aparece sozinho no seletor do Open WebUI
     (a lista vem do `/api/tags` ao vivo).
   - **Melhor esforço (não bloqueante)**: investigar como o Open WebUI guarda
     o modelo selecionado (provável `localStorage`) e, se for simples e
     estável, auto-selecionar o modelo recém-baixado. Se for frágil, NÃO
     fazer — a instrução textual basta.

3. **Assistente de primeiro uso (wizard)**:
   - Condição: usuário logado (token no localStorage) E `GET
     http://127.0.0.1:11434/api/tags` sem nenhum modelo de chat (ignorar
     `nomic-embed-text` e outros embeddings).
   - Mostrar overlay de boas-vindas: logo, "Bem-vindo ao Nous! Falta só um
     passo: escolher sua IA.", o modelo **recomendado** do catálogo já
     destacado com um botão grande **"Baixar e começar"**, e um link
     "ver outros modelos" que abre o painel completo.
   - Durante o download, mesma barra de progresso + frase "Pode deixar esta
     janela aberta — avisamos quando terminar."
   - Ao terminar: "Tudo pronto! Escolha o modelo no topo e comece a
     conversar." + botão "Começar" que fecha o overlay.
   - O overlay só aparece nessa condição (zero modelos), então some sozinho
     para sempre depois do primeiro download. Checar a condição no máximo a
     cada 10 s e só na rota home.

### A4. Simplificar `instalar.bat` (remover a pergunta de modelo)

- Remover o bloco `set /p NOUS_MODEL=...` e a chamada com `-WithModel`.
  O instalador instala só o núcleo (já é o desenho da v1.2 "setup leve");
  o wizard do primeiro uso cuida do modelo com UI bonita.
- Manter o repasse de argumentos avançados (`if not "%~1"==""`).
- No final, em vez de só instruir, **abrir o Nous automaticamente**:
  `start "" wscript.exe "%~dp0launchers\nous-hidden.vbs"` após mensagem
  "Abrindo o Nous para você terminar a configuração...".
- Atualizar as mensagens finais do `installer/install-nous.ps1` (passo 3 das
  instruções vira: "O Nous vai te guiar para escolher sua IA na primeira vez").
- `tools/check-system.ps1` continua igual (o veredito de capacidade segue
  sendo o porteiro), mas as dicas de "digite o modelo" nele e nos READMEs
  passam a apontar para a Loja de Modelos.

---

## Parte B — Bug: atalho não aparece na área de trabalho (corrigir em definitivo)

**Estado atual**: o commit `8eea915` garantiu fallback `.vbs` (não depende de
ps2exe), mas restam 3 causas-raiz em `installer/install-nous.ps1`:

1. O script roda com `$ErrorActionPreference = "Stop"`; o atalho só é criado
   no passo 6 — qualquer erro fatal nos passos 1–5 aborta antes do atalho.
2. `$lnk.Save()` pode ser bloqueado por antivírus / "Acesso controlado a
   pastas" do Windows Defender (que protege a área de trabalho) → exceção →
   instalação morre ali, sem atalho e sem manifesto.
3. Instalação elevada (UAC com outra conta admin) grava o atalho na área de
   trabalho da conta errada.

**Correções**:

1. Extrair função `New-NousShortcut($targetFolder)` (cria o .lnk apontando
   para `Nous.exe` ou wscript+vbs, com ícone) e envolver TODAS as chamadas em
   try/catch não-fatal.
2. Criar o atalho **em dois lugares**: área de trabalho
   (`[Environment]::GetFolderPath("Desktop")`) **e Menu Iniciar**
   (`[Environment]::GetFolderPath("Programs")` + `\Nous.lnk`) — o Menu
   Iniciar não é protegido pelo Acesso Controlado a Pastas, então o usuário
   sempre encontra "Nous" ao apertar a tecla Windows.
3. Após cada `.Save()`, verificar com `Test-Path`. Se a área de trabalho
   falhou: tentar `[Environment]::GetFolderPath("CommonDesktopDirectory")`
   (funciona quando elevado) e, se ainda assim falhar, imprimir aviso em
   destaque amarelo: "Atalho bloqueado pelo antivírus — use iniciar.bat ou
   procure 'Nous' no Menu Iniciar".
4. Criar o atalho **cedo** (logo após o passo 0.5/winget, quando o repo já
   está no disco e o alvo .vbs existe) E reverificar/recriar no passo 6.
   Assim mesmo um aborto no meio deixa um atalho funcional.
5. `tools/health-check.ps1`: nova checagem não-fatal "Atalho Nous" — OK se
   existe na área de trabalho OU no Menu Iniciar; senão `Note` com instrução.

---

## Parte C — Bug: logo/identidade não aplicada (corrigir em definitivo)

**Estado atual**: `apply_branding.py` roda uma única vez, no instalador; o
exit code não é verificado (falha passa batida no PS 5.1); `pip install
open-webui` sem pin pode trazer versão nova que muda o padrão de `env.py`
(o `patch_name` imprime "PADRAO NAO ENCONTRADO" e segue); nenhum mecanismo
reaplica a identidade depois. O health-check só confere `custom.css`.

**Correções**:

1. **`branding/apply_branding.py`**:
   - `main()` retorna exit code ≠ 0 em falha real (logo-mestre ausente,
     nenhuma pasta static encontrada, exceção do PIL). Mensagens claras.
   - Ao final, gravar marcador `NousData\.branding_marker.json`:
     `{ "open_webui_version", "logo_sha256", "applied_at" }`
     (versão via `open_webui.__version__` ou metadata do pacote; hash da
     `nous_logo.png`). Aceitar `--data-dir` como os outros scripts.
   - Novo flag `--if-needed`: lê o marcador; se versão do pacote E hash da
     logo conferem, sai em silêncio com código 0 (rápido, sem PIL). Senão,
     aplica tudo e regrava o marcador. Toda a lógica fica no Python.
2. **`launchers/start-nous.ps1`**: nova função `Ensure-Branding` que roda
   `apply_branding.py --if-needed --data-dir $env:DATA_DIR` — chamada nos
   DOIS pontos de boot, junto com os outros registros (antes de
   Register-Memory). Auto-cura: máquina que ficou sem logo (upgrade do
   open-webui, instalação parcial) se corrige sozinha no próximo boot.
3. **`installer/install-nous.ps1`**:
   - Antes do passo 5: `& $vpy -m pip install pillow --quiet` (no-op se já
     existe; elimina a classe "PIL ausente").
   - Após o passo 5: checar `$LASTEXITCODE`; se ≠ 0, aviso em destaque
     (não-fatal — o Nous funciona sem logo, e o boot vai tentar de novo).
   - **Pinar a versão do open-webui** num range testado:
     `pip install "open-webui==<versão atual instalada nesta máquina>"`.
     Descubra a versão com `& $vpy -m pip show open-webui`. Gravar a versão
     pinada numa constante no topo do script com comentário explicando que
     upgrades são conscientes (testar → subir o pin). Isso protege leigos de
     quebras silenciosas em instalações futuras.
4. **`tools/health-check.ps1`**: além do `custom.css`, conferir que
   `favicon.png` existe nas duas pastas static e que o marcador
   `.branding_marker.json` existe; senão FALHA com "rode
   branding\apply_branding.py" (mantém o texto atual).

---

## Parte D — Documentação e versão

1. `VERSION` → `2.2.0`; `CHANGELOG.md` → entrada `[2.2.0] - <data de hoje>`
   listando: Loja de Modelos, wizard de primeiro uso, instalador sem pergunta
   de terminal, atalho garantido (desktop + Menu Iniciar), branding com
   auto-cura no boot, pin do open-webui.
2. `README.md` + `README.pt-BR.md`:
   - Badge de versão → 2.2.0.
   - Seção "Qual modelo devo usar?" — reescrever a abertura: o Nous agora
     recomenda e baixa o modelo sozinho, dentro do app ("Loja de Modelos");
     as tabelas viram referência.
   - "Começo rápido" — refletir que NÃO há mais pergunta de modelo no
     instalador e que o Nous abre sozinho no final.
   - Troubleshooting do atalho: acrescentar "procure 'Nous' no Menu Iniciar".
3. `docs/ROADMAP.md`: reorganizar — marcar "Assistente de primeira execução"
   (v1.2 do roadmap) como **feito** nesta versão; manter próximos: Bandeja
   do sistema e Distribuição. Aproveitar e ordenar as seções (hoje a v1.6
   está entre v1.3 e v1.4).

---

## Testes (obrigatórios antes do commit)

1. **Monitor**: subir `nous_monitor.py` e validar com Invoke-RestMethod:
   `/hardware` (tier coerente com a máquina), `/catalog` (ordenação:
   recomendados primeiro; `installed` correto), `POST /pull` com um modelo
   pequeno (ex.: `qwen3:0.6b` ou o menor disponível) e acompanhar
   `/pull/status` até `pronto`; repetir o POST durante o download e conferir
   o singleton. Apagar o modelo de teste depois (`ollama rm`).
2. **Loader**: `node --check branding\nous-loader.js` (se node disponível;
   senão, revisar sintaxe com cuidado). Teste manual: abrir o Nous, conferir
   painel Modelos, badges e barra de progresso.
3. **Instalador**: rodar `instalar.bat` nesta máquina (idempotente — tudo já
   existe, deve passar rápido) e conferir: sem pergunta de modelo, atalho na
   área de trabalho E no Menu Iniciar, Nous abre sozinho no final.
4. **Branding**: apagar `.branding_marker.json`, rodar `start-nous.ps1`,
   conferir que o marcador volta (auto-cura). Rodar `apply_branding.py
   --if-needed` duas vezes — a segunda deve ser instantânea.
5. **Health-check**: rodar e conferir as novas checagens (atalho, branding).
6. **Wizard**: testar a condição com Ollama sem modelos de chat é difícil na
   máquina de dev — simular: no console do navegador, verificar que a função
   do wizard respeita a condição (ou temporariamente forçar a condição via
   flag de teste no código e remover antes do commit).

## Commit

Mensagem sugerida:
`feat: Loja de Modelos no app + wizard de primeiro uso + atalho/logo garantidos (v2.2.0)`

Um único commit, após todos os testes. `git pull --rebase` antes do push
(projeto roda em duas máquinas).
