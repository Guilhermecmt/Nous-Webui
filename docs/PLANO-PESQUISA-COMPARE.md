# Plano de Execução — "Pesquisa Profunda" + "Comparar Modelos" — v2.4.0

> Documento de planejamento para execução pelo Sonnet. Estudo feito em 2026-06-13.
> Objetivo: trazer duas features de alto valor e baixo risco para o
> público leigo (ver memória `competitive-landscape`):
>   A) **Pesquisa Profunda** — pesquisa multi-etapas na web com relatório e citações.
>   B) **Comparar Modelos** — teste cego (blind) entre dois modelos para a mesma pergunta.
> Princípios do projeto valem: nunca mostrar terminal; idempotente; privado por
> padrão; registro direto no `webui.db`/serviços locais.

---

## PARTE A — Pesquisa Profunda (Deep Research)

### A0. O que já existe (não reconstruir)
- `search/nous_search/search.py` → `search_web(query, k)` via SearXNG, com cache.
- `search/nous_search/rag.py` → `answer(query, k, deep=False)`: monta contexto com
  fontes numeradas `[n]`, cita estilo Perplexity, e com `deep=True` baixa o texto
  das páginas (`fetch_page`, BeautifulSoup best-effort) antes de sintetizar.
- `search/nous_search/agent.py` → **esqueleto LangGraph** do laço
  `plan → search → (precisa de mais?) → synthesize`, hoje com TODOs.
- `search/docker-compose.yml` sobe o SearXNG (porta 8888, usada por `search.py`).

A Pesquisa Profunda é **terminar o agente** e expô-lo como um Pipe no dropdown.

### A1. Decisões de design (já tomadas)
1. **Forma de entrega = Pipe do Open WebUI** chamado **"Pesquisa Profunda (Nous)"**,
   registrado no banco igual ao `images/register_pipe_auto.py` (tabela `function`,
   `type='pipe'`). O usuário seleciona no dropdown de modelos e faz a pergunta
   normalmente — o Pipe roda o laço de pesquisa e devolve um relatório com fontes.
2. **Síntese 100% local** (Ollama). A web é consultada via SearXNG local; o texto
   das páginas é baixado pela própria máquina. Nada de API paga. On-brand.
3. **Status transitório na UI** a cada etapa ("Planejando...", "Buscando: X",
   "Lendo N páginas", "Escrevendo o relatório") via os eventos do Open WebUI
   (`__event_emitter__`), mesmo mecanismo de status já usado nos filtros de
   memória/arquivos.
4. **Relatório final em markdown** com seção de **Fontes** numeradas (URLs
   clicáveis) ao final — complementa as citações `[n]` inline do `rag.py`.
5. **Ativo só se o SearXNG estiver no ar** (auto-cura, igual ao Pipe de imagem que
   só ativa com ComfyUI instalado). Sem SearXNG → Pipe fica inativo, não aparece
   quebrado.
6. **Sem LangGraph como dependência dura.** O `agent.py` importa o langgraph sob
   demanda. Decisão: implementar o laço com **Python puro** dentro do Pipe (loop
   `while iterations < max`), reaproveitando `search_web`/`fetch_page`/Ollama —
   evita adicionar dependência pesada ao venv do leigo. O `agent.py` LangGraph fica
   como referência/experimento, não no caminho de produção.

### A2. Etapas de execução

**A2.1 Finalizar a lógica de pesquisa** (em `search/nous_search/`, Python puro):
- **plan**: pedir ao Ollama para decompor a pergunta em 2–4 sub-perguntas (prompt
  PT-BR, saída JSON simples; se o parse falhar, cair para `[pergunta original]`).
- **search**: `search_web` para cada sub-pergunta; dedup por URL (já há lógica no
  `agent.py`); manter os top-N por score.
- **need_more** (opcional, 1 iteração extra no máximo): perguntar ao LLM se o
  conjunto de fontes cobre a pergunta; se não e ainda há orçamento de iterações,
  gerar 1–2 sub-perguntas novas e buscar de novo. Manter `max_iterations=2` para
  não estourar tempo em CPU.
- **synthesize**: `fetch_page` nas melhores fontes (modo `deep`) + `rag.answer`
  para o relatório final com `[n]` e lista de fontes. Limitar nº de páginas
  baixadas (ex.: 5–6) para controlar latência.
- Expor uma função única `deep_research(question, emit=None) -> {report, sources}`
  que o Pipe chama, passando um callback `emit` para os status.

**A2.2 Criar o Pipe** `search/nous_research_pipe.py` (espelhar o cabeçalho e a
estrutura de classe de `images/nous_image_pipe.py`: docstring com `title:`,
`version:`, `Valves` Pydantic, método `async def pipe(self, body, __event_emitter__...)`):
- `Valves`: `OLLAMA_MODEL` (default lê `NOUS_MODEL`/`gemma4:12b`),
  `SEARXNG_URL` (default `http://localhost:8888`), `MAX_ITERATIONS`,
  `MAX_PAGES`, `LANG` (`pt-BR`).
- No `pipe`: extrai a última mensagem do usuário como `question`, chama
  `deep_research` com um `emit` que repassa status via `__event_emitter__`, e
  retorna o relatório em markdown (com a seção **Fontes**).
- Robustez: SearXNG fora do ar → mensagem amigável ("A busca na web não está
  disponível agora."), nunca stacktrace. Timeouts generosos (pesquisa é lenta).

**A2.3 Registrar o Pipe** `search/register_research_pipe.py` (copiar
`images/register_pipe_auto.py` quase 1:1):
- `FUNC_ID = "nous_research"`, `FUNC_NAME = "Pesquisa Profunda (Nous)"`.
- `active = 1` apenas se o SearXNG responder (checagem rápida a
  `GET {SEARXNG_URL}/healthz` ou `/search?q=teste&format=json` com timeout curto);
  senão `active = 0` (auto-cura quando o SearXNG subir).
- Idempotente; re-sincroniza o conteúdo do `.py` a cada boot.

**A2.4 Launcher** `launchers/start-nous.ps1`: garantir que o **SearXNG sobe** (já
há `search/docker-compose.yml`; se o projeto evita Docker para o leigo, avaliar
rodar o SearXNG standalone ou documentar que Pesquisa Profunda exige o container).
Adicionar `Register-Research` nos dois pontos de boot, junto dos outros register_*.
**Ponto de atenção**: se Docker é barreira para o leigo, considerar um modo de
busca sem SearXNG (fallback DuckDuckGo HTML) — decidir na execução; não bloquear.

---

## PARTE B — Comparar Modelos (teste cego)

### B0. O que já existe
- O Open WebUI tem o recurso **Arena Models** (avaliação A/B com voto e identidade
  oculta). O Nous **desativou** isso na v1.6.0 via
  `ENABLE_EVALUATION_ARENA_MODELS=False` (CHANGELOG/monitor) "para evitar confusão".
  O Arena JÁ É o teste cego que queremos — a jogada é **re-ligar e
  reembrulhar** com nome amigável, em vez de reconstruir split-chat no Svelte
  (que foi avaliado e adiado na v2.0.0 por risco de regressão no frontend).

### B1. Decisões de design (já tomadas)
1. **Reusar o Arena**, não construir split-chat. Risco baixo, código zero no Svelte.
2. **Curadoria**: registrar **um** "Arena model" amigável chamado
   **"Comparar Modelos (Nous)"** que sorteia entre os modelos de chat instalados
   (ou um par curado), em vez de expor a config crua de avaliação. O usuário
   pergunta, vê duas respostas anônimas (A/B) e vota — o nome do modelo só aparece
   após o voto.
3. **PersistentConfig**: a flag vive no banco após o 1º boot → ligar via registro
   no `webui.db` (mesmo motivo dos outros register_*), não via env no launcher.

### B2. Etapas de execução

**B2.1 Verificar na versão pinada** (`open-webui==0.9.6`) — ANTES de codar:
- Onde mora a flag de Arena no config do banco (chave em `config`, ex.:
  `evaluation.arena.enable` ou `ENABLE_EVALUATION_ARENA_MODELS`) e como o Arena
  model é representado (tabela `model` com flag de "arena", ou config própria).
  O formato muda entre versões — inspecionar o `config.py` instalado e um
  `webui.db` real (mesma diligência do plano da Nuvem).

**B2.2 `evaluation/register_arena.py`** (novo, padrão dos outros register_*):
- Liga a flag de Arena no config do banco (idempotente).
- Cria/atualiza UM arena model "Comparar Modelos (Nous)" apontando para os
  modelos de chat locais instalados (ler de `/api/tags` do Ollama, ignorando
  embeddings). Se houver < 2 modelos de chat, **não** ativar (sem comparação
  possível) — auto-cura quando o 2º modelo for baixado.
- NÃO mexer em outras configs de avaliação que o usuário tenha.

**B2.3 Launcher**: `Register-Arena` nos dois pontos de boot.

**B2.4 (opcional, melhor esforço) UI** em `branding/nous-loader.js`: um aviso
curto/explicação quando o usuário seleciona "Comparar Modelos" pela primeira vez
("Você verá duas respostas anônimas — escolha a melhor. O nome só aparece depois.").
Não bloquear o release por isso.

---

## PARTE C — Documentação e versão

1. `VERSION` → `2.4.0`; `CHANGELOG.md` → entrada `[2.4.0] - <data>`: Pesquisa
   Profunda (Pipe com relatório + citações, 100% local) e Comparar Modelos
   (teste cego via Arena reembrulhado).
2. `README.md` + `README.pt-BR.md`: badge de versão; itens curtos em "Features"
   ("Pesquisa profunda na web com fontes" e "Compare dois modelos às cegas").
3. `docs/ROADMAP.md`: registrar as entregas; lembrar que o split-chat adiado na
   v2.0 foi resolvido por outro caminho (Arena).

---

## Critério de pronto (verificação)
**Pesquisa Profunda:**
1. SearXNG no ar → "Pesquisa Profunda (Nous)" aparece no dropdown.
2. Uma pergunta gera relatório em markdown com citações `[n]` e seção de Fontes
   com URLs reais; os status aparecem durante a execução.
3. SearXNG fora do ar → Pipe inativo (não aparece quebrado) ou mensagem amigável;
   nunca stacktrace.
4. Registrar duas vezes não duplica (idempotência).

**Comparar Modelos:**
5. Com ≥ 2 modelos de chat instalados → "Comparar Modelos (Nous)" disponível;
   pergunta mostra A/B anônimos; após votar, revela os nomes.
6. Com < 2 modelos → não aparece (auto-cura quando baixar o 2º).
7. `register_arena.py` idempotente.

## Riscos e armadilhas
- **SearXNG via Docker** pode ser barreira para o leigo — avaliar fallback sem
  Docker (busca DuckDuckGo HTML) ou documentar bem; é o maior risco da Parte A.
- **Latência da Pesquisa Profunda em CPU**: baixar páginas + síntese é lento;
  limitar páginas/iterações e mostrar status para gerenciar expectativa.
- **Formato do Arena/flag de avaliação** muda entre versões do Open WebUI —
  inspecionar a 0.9.6 antes (B2.1). Se o Arena tiver sido removido/alterado
  upstream, a Parte B vira um split-chat custom no `nous-loader.js` (escopo maior)
  — nesse caso, **adiar a Parte B** e entregar só a Pesquisa Profunda na v2.4.0.
- **Não adicionar LangGraph** ao venv do leigo (peso/dependências) — laço em
  Python puro.

## Fora de escopo (não fazer agora)
- Visualizações/gráficos no relatório (aqui é texto + citações).
- Comparar mais de 2 modelos simultâneos.
- Pesquisa profunda sobre arquivos locais (já há o RAG de arquivos separado).
