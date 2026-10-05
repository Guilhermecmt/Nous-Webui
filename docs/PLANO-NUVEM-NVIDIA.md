# Plano de Execucao — "Nous Nuvem" (NVIDIA NIM API) — v1.6.0

> Documento de planejamento para execucao pelo Sonnet. Estudo feito em 2026-06-10.
> Objetivo: dar ao Nous acesso OPCIONAL a ~80 modelos de fronteira gratuitos
> (DeepSeek, Llama, Qwen, MiniMax, Kimi...) via API hospedada da NVIDIA,
> SEM quebrar o principio central do projeto: **privado por padrao**.

---

## 1. Fatos verificados (nao precisa re-pesquisar)

- **Endpoint**: `https://integrate.api.nvidia.com/v1` — 100% compativel com a
  API da OpenAI (`/chat/completions`, `/models`, streaming). Basta trocar
  `base_url` + `api_key` em qualquer cliente OpenAI.
- **Chave**: gratuita, prefixo `nvapi-...`, criada em https://build.nvidia.com/models
  (NVIDIA Developer Program; sem cartao de credito).
- **Free tier**: ~1.000 creditos de inferencia no cadastro (ate 5.000 com email
  corporativo, mediante pedido) e **40 requisicoes/minuto**. Sem aumento de
  limite no tier gratis. Pensado para prototipo/uso pessoal — perfeito p/ Nous.
- **Open WebUI**: suporta conexoes OpenAI-compativel nativamente. A config vive
  como *PersistentConfig* no banco (`webui.db`, tabela `config`) — variaveis de
  ambiente so valem no PRIMEIRO boot; depois o banco manda. Logo, a integracao
  certa segue o padrao Nous ja usado em `memory/register_memory.py` e
  `images/register_pipe_auto.py`: **escrever direto no banco, idempotente, a cada boot**.

## 2. Decisoes de design (ja tomadas — nao re-discutir)

1. **Opt-in explicito.** Nuvem so existe depois que o usuario ativa e cola a
   propria chave. Sem chave => nenhuma conexao externa configurada.
2. **Chave em `NousData\.nvidia_api_key`** (fora do git), mesmo padrao da
   `.webui_secret_key`.
3. **Registro automatico no banco** via novo script `cloud/register_nvidia.py`,
   chamado pelo launcher junto de `Register-Memory`/`Register-Pipe`.
   - Chave presente  => grava/atualiza a conexao OpenAI no config do banco.
   - Chave ausente   => REMOVE a conexao (desativacao limpa e reversivel).
4. **Curadoria de modelos.** O `/v1/models` da NVIDIA devolve ~80 modelos; jogar
   tudo no dropdown polui a UI. Registrar uma allowlist de 5-8 modelos bons
   (campo `model_ids` do `api_configs` da conexao — ver secao 4.1).
5. **Privacidade da memoria (CRITICO).** O Filter `nous_memory` injeta fatos
   pessoais no system message de TODA conversa. Em modelo de nuvem isso enviaria
   dados intimos a NVIDIA sem o usuario perceber. Decisao: **o inlet NAO injeta
   memorias em modelos de nuvem** (e o outlet continua extraindo só com Ollama
   local, como hoje). Deteccao: ids da NVIDIA tem formato `vendor/modelo`
   (contem `/`); ids locais do Ollama usam `:` (ex.: `gemma4:12b`). Adicionar
   valve `CLOUD_MODELS_GET_MEMORY: bool = False` para quem quiser ligar.
6. **Transparencia na UI.** Os modelos de nuvem devem aparecer com nome claro,
   ex.: `DeepSeek V3 (Nuvem)` — o usuario sempre sabe quando a conversa sai da
   maquina.

## 3. Etapas de execucao (em ordem)

### Fase 1 — Nucleo

**1.1 Criar `cloud/register_nvidia.py`** (espelhar o estilo de
`images/register_pipe_auto.py`: stdlib + sqlite3, idempotente, sem credenciais):
- Resolver `webui.db` igual ao `resolve_db()` existente.
- Ler a chave de `NousData\.nvidia_api_key`. Se nao existir/vazia: remover a
  URL da NVIDIA de `openai.api_base_urls`/`api_keys`/`api_configs` no config e sair.
- Se existir: ler o JSON da tabela `config` (linha mais recente), garantir:
  - `openai.enable = true`
  - `https://integrate.api.nvidia.com/v1` em `api_base_urls` com a chave no
    indice correspondente de `api_keys`
  - `api_configs` da conexao com `model_ids` = allowlist curada e
    `enable = true`
  - NAO tocar em outras conexoes que o usuario tenha criado manualmente.
- **ANTES de codar**: inspecionar o formato real do config na versao instalada,
  em `%USERPROFILE%\open-webui\Lib\site-packages\open_webui\config.py`
  (procurar `OPENAI_API_BASE_URLS`, `OPENAI_API_CONFIGS`) e, se houver um
  `webui.db` de dev, olhar o JSON salvo. O formato de `api_configs` mudou entre
  versoes (chave por indice "0","1"... vs por URL) — confirmar na versao local.

**1.2 Allowlist inicial** (validar com `GET /v1/models` usando a chave do
usuario quando disponivel; ajustar se algum id nao existir):
- `deepseek-ai/deepseek-v3.1` (geral, forte)
- `meta/llama-3.3-70b-instruct` (geral, estavel)
- `qwen/qwen3-coder-480b-a35b-instruct` (codigo)
- `minimaxai/minimax-m2` (agentico/rapido)
- `moonshotai/kimi-k2-instruct` (contexto longo)
Manter a lista numa constante no topo do script, facil de editar.

**1.3 Editar `launchers/start-nous.ps1`**: adicionar `Register-Cloud` (mesmo
padrao das funcoes `Register-Memory`/`Register-Pipe`, linhas ~53-67) e chama-la
nos dois pontos onde as outras sao chamadas (servidor ja de pe e pos-boot).

**1.4 Ativacao sem terminal** — criar `cloud/ativar-nuvem.ps1`:
- Abrir dialogo grafico p/ colar a chave (InputBox do
  `Microsoft.VisualBasic.Interaction` — sem prompt cru, principio do projeto).
- Validar com `GET https://integrate.api.nvidia.com/v1/models`
  (`Authorization: Bearer <chave>`); em erro 401, mensagem clara via MessageBox.
- Salvar em `NousData\.nvidia_api_key`, rodar `register_nvidia.py` na hora e
  avisar: "Pronto. Reinicie o Nous (ou recarregue a pagina) para ver os modelos."
- Criar tambem `cloud/desativar-nuvem.ps1`: apaga a chave, roda o register
  (que limpa a conexao), confirma via MessageBox.
- Atalhos `.bat` finos na raiz (`ativar-nuvem.bat` / `desativar-nuvem.bat`)
  seguindo o padrao de `iniciar.bat`.

### Fase 2 — Privacidade e UX

**2.1 Editar `memory/nous_memory.py`** (bump p/ 0.2.0):
- Nova valve `CLOUD_MODELS_GET_MEMORY: bool = False`.
- No `inlet`: obter o id do modelo (`body.get("model", "")`); se contiver `/`
  e a valve estiver False, retornar `body` sem injetar (e sem emitir status).
- O `outlet` permanece como esta (extracao e' sempre local via Ollama).
- Lembrar: `register_memory.py` re-sincroniza o arquivo a cada boot, entao basta
  editar o `.py` — mas conferir se valves persistidas no banco sobrevivem
  (novas valves ganham default, ok).

**2.2 Nomes amigaveis**: avaliar se a versao local do Open WebUI suporta
campo de alias/nome no `api_configs` ou na tabela `model`. Se sim, registrar
nomes como "DeepSeek V3 (Nuvem)". Se for complexo, aceitavel deixar os ids
crus na v1.6.0 e melhorar depois — nao bloquear o release por isso.

**2.3 Erros de limite**: free tier = 40 req/min e creditos finitos. Testar o
que o usuario ve num 429/402. Se a mensagem do Open WebUI ja for compreensivel,
nao fazer nada; so criar tratamento (ex.: filter traduzindo o erro) se a
experiencia real for ruim. Nao engenheirar antecipadamente.

### Fase 3 — Saude, docs e release

**3.1 `tools/health-check.ps1`**: item INFORMATIVO "Nuvem NVIDIA: ativa
(N modelos) / inativa" — chave presente => `GET /v1/models` com timeout curto;
nunca falhar o health-check por causa da nuvem.

**3.2 Docs**:
- `README.md` + `README.pt-BR.md`: secao curta "Nous Nuvem (opcional)" —
  o que e', como ativar, **aviso explicito de que conversas nesses modelos vao
  para servidores da NVIDIA** e que a memoria pessoal NAO e' enviada.
- `docs/ROADMAP.md`: registrar a entrega.
- `CHANGELOG.md`: entrada `[1.6.0]` (Adicionado: Nous Nuvem; Mudado: memoria
  nao injetada em modelos de nuvem). Atualizar `VERSION` p/ `1.6.0`.

**3.3 Verificacao (criterio de pronto)**:
1. Sem chave: boot normal, zero conexao externa no config, dropdown so com locais.
2. `ativar-nuvem` com chave valida: modelos da allowlist aparecem no dropdown
   apos reinicio; chat com um deles responde (streaming ok).
3. Conversa em modelo de nuvem NAO mostra "Nous lembrou de N detalhe(s)" e o
   system message nao contem o bloco `[Memoria do Nous]`.
4. Conversa em modelo local continua com memoria normal.
5. `desativar-nuvem`: conexao some do config; dropdown volta ao estado local.
6. Rodar `ativar` duas vezes seguidas nao duplica a conexao (idempotencia).

## 4. Riscos e armadilhas conhecidas

- **PersistentConfig**: nao adianta setar `OPENAI_API_BASE_URL` como env no
  launcher — depois do primeiro boot o banco ignora env. Por isso o registro
  e' direto no banco (item 1.1).
- **Formato do `api_configs`** muda entre versoes do Open WebUI (indexado por
  posicao vs por URL). Inspecionar a versao instalada antes de escrever.
- **Concorrencia no sqlite**: escrever no `webui.db` com o servidor de pe
  funciona (os outros register_* ja fazem), mas o servidor cacheia config em
  memoria — mudancas valem apos reinicio do servidor. A UX do `ativar-nuvem`
  ja avisa isso.
- **Ids de modelo da allowlist** podem nao existir mais (catalogo da NVIDIA
  muda). O register nao deve quebrar por isso; e o `ativar-nuvem` pode filtrar
  a allowlist contra o `/v1/models` real no momento da ativacao.
- **Termos NVIDIA**: tier gratis e' para desenvolvimento/prototipo; dados sao
  processados nos servidores deles. Por isso o aviso explicito no README e o
  opt-in.

## 5. Fora de escopo (nao fazer agora)

- UI propria para colar a chave dentro do webapp (fica p/ First-Run Wizard, v1.2 do roadmap).
- Roteamento automatico local->nuvem ("fallback inteligente").
- Suporte a outros provedores de nuvem (OpenRouter etc.) — a estrutura
  `cloud/` ja deixa o caminho aberto.
