# Motor próprio (nous-motor) — desenho e plano

> **Para quem for executar:** SUB-SKILL OBRIGATÓRIA: superpowers:subagent-driven-development
> (recomendado) ou superpowers:executing-plans, tarefa por tarefa. Os passos usam `- [ ]`.

**Objetivo:** o Nous funcionar sem o Ollama instalado, com o `llama-server` (llama.cpp,
Vulkan) carregado pelo próprio Nous, sem mudar nomes de modelos nem dados do usuário.

**Arquitetura:** um serviço novo, `motor/nous_motor.py` (aiohttp, porta 8989), responde o
pedaço da API do Ollama que o Nous e o Open WebUI usam. No modo `llama` ele traduz cada
pedido para um `llama-server` por modelo, que ele mesmo sobe e derruba; no modo `ollama`
ele só repassa para o Ollama (11434). Todos os chamadores já leem `OLLAMA_BASE_URL`:
basta apontá-lo para o motor. Os modelos continuam onde estão (pasta do Ollama, arquivos
GGUF), com os mesmos nomes (`qwen3:4b`).

**Tecnologia:** Python 3.11 do venv do Open WebUI (aiohttp, requests, stdlib),
llama.cpp `llama-server` para Windows (build Vulkan), PowerShell 5.1 nos launchers.

**Desenho (spec):** este próprio documento, seção "Desenho". Decidido com o dono em
15/11/2026: independência do Ollama; até ~2 GB de download no total (hoje em 5G).

---

## Desenho

### Por que um intermediário e não reescrever os chamadores
~40 arquivos chamam `/api/generate`, `/api/chat`, `/api/embeddings`, `/api/embed`,
`/api/tags`, `/api/show`, `/api/ps`, `/api/pull`, `/api/version` (44 chamadas só de
geração). Quase todos já leem `OLLAMA_BASE_URL`. O Open WebUI fala Ollama nativo e guarda
os nomes dos modelos em conversas, ajustes e filtros. Responder a mesma API num lugar só
muda uma variável de ambiente e duas chaves no banco, e deixa o Ollama como alternativa.

### O que o motor responde

| Rota | Modo `llama` |
|---|---|
| `GET /api/version` | `{"version": "0.0.0-nous-motor"}` |
| `GET /api/tags` | modelos da pasta de modelos (manifestos do Ollama) |
| `POST /api/show` | `details`, `model_info`, `capabilities`, `parameters`, `template` |
| `GET /api/ps` | processos `llama-server` vivos, com `expires_at` |
| `POST /api/chat` | `/v1/chat/completions` (stream SSE → NDJSON do Ollama) |
| `POST /api/generate` | idem, com `system` + `prompt` viram mensagens; `prompt` vazio = carregar; `keep_alive: 0` = descarregar |
| `POST /api/embeddings` | `/v1/embeddings` → `{"embedding": [...]}` (sem normalizar) |
| `POST /api/embed` | `/v1/embeddings` → `{"embeddings": [[...]]}` (normalizado L2, como o Ollama) |
| `POST /api/pull` | baixa do registry.ollama.ai para a mesma pasta, progresso NDJSON igual ao Ollama |
| `DELETE /api/delete` | apaga o manifesto e os blobs que ninguém mais usa |
| `POST /api/copy`, `/api/create`, `/api/push` | `501 {"error": "..."}` |
| `GET /health` | `{"ok": true, "motor": "llama" \| "ollama"}` |

No modo `ollama` todas as rotas `/api/*` são repassadas como estão (inclusive stream).

### Regras do modo `llama`
- **Um `llama-server` por modelo carregado**, numa porta livre de 127.0.0.1.
  Argumentos: `-m <blob> --host 127.0.0.1 --port <p> -c <ctx> --jinja
  --reasoning-format deepseek -np 1 --no-webui` (sem `-ngl`: o `--fit` do llama-server põe na placa o que cabe); embedding ganha `--embeddings -b <ctx> -ub <ctx>`; se faltar memória ao carregar, os modelos ociosos saem e tenta de novo;
  com projetor (visão), `--mmproj <blob>` (não testado neste plano, ver "Fora").
- **Contexto:** `options.num_ctx` do pedido, senão `OLLAMA_CONTEXT_LENGTH` (16384), nunca
  acima do `context_length` do GGUF. Pedido com contexto maior que o carregado recarrega.
- **Quantos ficam carregados:** até `NOUS_MOTOR_MAX_MODELOS` (padrão 2) de geração mais
  os de embedding. Para abrir espaço sai o ocioso usado há mais tempo; modelo com
  pedido em andamento nunca é derrubado (o novo espera).
- **Tempo na memória:** `keep_alive` do pedido (`"5m"`, segundos, `0` = agora, `-1` =
  sempre), senão `OLLAMA_KEEP_ALIVE` (5m).
- **Parâmetros padrão do modelo:** a camada `params` do manifesto (ex.: qwen3:
  temperature 0.6, top_k 20, top_p 0.95, stop) vale por baixo de `options` do pedido.
- **`format`:** `"json"` → `response_format {"type":"json_object"}`; objeto →
  `{"type":"json_schema","json_schema":{"name":"saida","schema":<objeto>}}`.
- **`think`:** `true/false` → `chat_template_kwargs {"enable_thinking": <bool>}`; texto
  (`"low"`…) → `chat_template_kwargs {"reasoning_effort": <texto>}`; ausente → nada.
  `reasoning_content` volta como `message.thinking` (ou `thinking` no generate).
- **Ferramentas:** `tools` passa igual; `tool_calls` do Ollama (argumentos objeto) ↔
  OpenAI (argumentos texto JSON, com `id`); mensagens `tool` ganham `tool_call_id` pela
  ordem das chamadas anteriores.
- **Erros** sempre no formato do Ollama: `{"error": "<frase em português>"}` com 4xx/5xx.

### Onde ficam as coisas
- Pasta de modelos: `OLLAMA_MODELS` se definida; senão `%USERPROFILE%\.ollama\models`
  se existir; senão `%DATA_DIR%\modelos`. Mesmo layout (`manifests/…`, `blobs/sha256-…`).
- Binário: `NOUS_LLAMA_SERVER` se definida; senão `<app>\motor\bin\llama-server.exe`.
- Escolha do motor: `NOUS_MOTOR` (`llama`|`ollama`) se definida; senão
  `%DATA_DIR%\motor\ajustes.json` `{"motor": ...}`; senão `llama` se o binário existe,
  `ollama` se não.

### Fora deste plano
Modelos de visão no modo `llama` (precisa baixar um modelo de GBs para testar); escolha do
motor pela tela; baixar modelos do Hugging Face; remover o Ollama da máquina do dono.

---

## Restrições globais
- Sem dependência nova de pip ou npm; só stdlib, `aiohttp` e `requests` do venv.
- Motor só em `127.0.0.1:8989`; `llama-server` só em `127.0.0.1`.
- Nomes de modelos idênticos aos do Ollama (`qwen3:4b`, `granite-embedding:278m`).
- Nunca apagar nada da pasta de modelos fora do `DELETE /api/delete`.
- Scripts `.ps1` em ASCII puro (o lint confere); comentários de código em português sem acento.
- Testes em `unittest`, em `motor/testes/`, rodando sem rede e sem GPU (servidores de mentira).
- Download total ≤ 2 GB: o binário do llama.cpp (dezenas de MB) e, com OK do dono, um
  modelo pequeno para testar o pull de verdade. Nenhum modelo grande.
- Nunca rodar launcher/instalador de branch contra o app instalado; testes reais usam
  `C:\dev\pessoal\nous-teste` (venv `owui-012`, dados `dados-012`) com o app parado.

## Foco da revisão
1. **Embeddings diferentes dos já indexados** (Documentos, Histórico, Memória,
   Habilidades): a busca piora sem erro nenhum. Esperado: cosseno ≥ 0,99 entre o vetor do
   Ollama e o do motor para o mesmo texto e modelo. Teste: Tarefa 8, passo 3.
2. **Usuário aperta Parar no meio da resposta:** o motor fecha a conexão com o
   `llama-server` e a placa para de gerar. Teste: Tarefa 5, `test_cliente_desiste_fecha_upstream`.
3. **`llama-server` morre ou não carrega** (falta de VRAM, GGUF que ele não lê): erro
   `{"error"}` em segundos, não pedido pendurado; o próximo pedido tenta subir de novo.
   Teste: Tarefa 4, `test_processo_morre_no_carregamento` e `test_processo_morre_depois`.
4. **Filtro pede o qwen3:4b enquanto a conversa usa o 14b:** os dois cabem
   (MAX_MODELOS=2) e nenhum é derrubado com pedido em andamento. Teste: Tarefa 4,
   `test_nao_derruba_modelo_em_uso`.
5. **Pedido com `num_ctx` maior que o carregado ou acima do máximo do modelo:**
   recarrega com o maior; nunca passa do `context_length` do GGUF. Teste: Tarefa 4,
   `test_contexto_maior_recarrega` e `test_contexto_limitado_pelo_modelo`.

---

## Arquivos

| Arquivo | Responsabilidade |
|---|---|
| `motor/registro.py` | pasta de modelos: manifestos, leitura do cabeçalho GGUF, capacidades |
| `motor/traduz.py` | funções puras Ollama ↔ OpenAI (pedido, pedaços de stream, embeddings) |
| `motor/processos.py` | sobe/derruba `llama-server`, contexto, keep_alive, limite de modelos |
| `motor/baixar.py` | pull do registry.ollama.ai e delete, com progresso NDJSON |
| `motor/nous_motor.py` | servidor aiohttp: rotas, modo `ollama` (repasse) e `llama` |
| `motor/LLAMA_VERSAO.json` | versão fixa do llama.cpp: tag, URL do zip, sha256 |
| `motor/testes/falsos.py` | `llama-server`, Ollama e registry de mentira; GGUF sintético |
| `motor/testes/amostras/*.json` | respostas reais do `llama-server` gravadas na Tarefa 1 |
| `motor/testes/test_*.py` | um arquivo por módulo |
| `ajustes/register_motor.py` | grava `ollama.base_urls` e `rag.ollama.base_url` no webui.db |
| `launchers/*.ps1`, `installer/install-nous.ps1`, `tools/*.ps1` | ligar o motor |
| filtros com `11434` fixo | passam a ler `OLLAMA_BASE_URL` |

---

### Tarefa 1: llama-server na máquina e amostras reais

**Arquivos:**
- Criar: `motor/LLAMA_VERSAO.json`, `motor/testes/amostras/` (chat_stream.json,
  chat_json_schema.json, chat_tools.json, chat_sem_pensar.json, embeddings.json, health.json, erro_ctx.json)
- Criar: `motor/testes/gravar_amostras.py` (roda à mão, não entra no lint)

**Interfaces:**
- Produz: `LLAMA_VERSAO.json` = `{"tag": "bNNNN", "zip": "<url>", "sha256": "<hex>", "exe": "llama-server.exe"}`;
  amostras = lista de linhas `data:` do SSE já decodificadas em JSON (ou o JSON inteiro quando não é stream).

- [ ] **Passo 1:** escolher a release mais nova do llama.cpp com o zip `llama-<tag>-bin-win-vulkan-x64.zip`
  (GitHub ggml-org/llama.cpp), anotar tamanho antes de baixar; parar e avisar se passar de 150 MB.
- [ ] **Passo 2:** baixar para `C:\dev\pessoal\nous-teste\llama\`, conferir o sha256, extrair, gravar `LLAMA_VERSAO.json`.
- [ ] **Passo 3:** `llama-server.exe --version` e `--list-devices`. Esperado: a RX 9070 XT aparece como dispositivo Vulkan.
  Se não aparecer, parar e avisar o dono (o plano depende da GPU).
- [ ] **Passo 4:** `llama-server --help` e confirmar cada argumento do Desenho
  (`--jinja`, `--reasoning-format deepseek`, `-np`, `--embeddings`, `--mmproj`, `-ngl`, `-c`).
  Se algum mudou de nome, corrigir a seção "Regras do modo llama" deste documento antes de seguir.
- [ ] **Passo 5:** escrever `gravar_amostras.py`: sobe o `llama-server` com o blob do `qwen3:4b`
  (caminho lido do manifesto) e grava, com `stream_options.include_usage`: conversa simples
  com stream; `response_format` json_schema `{"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}`;
  uma ferramenta `hora_atual` sem parâmetros com a pergunta "que horas são? use a ferramenta";
  `enable_thinking: false`; depois sobe com `granite-embedding:278m` + `--embeddings` e grava
  `/v1/embeddings` de `["oi", "tudo bem"]`; e um pedido com mais tokens que o `-c` (erro).
- [ ] **Passo 6:** rodar e conferir à mão que cada amostra tem o que o nome diz
  (`reasoning_content` presente em chat_stream, `tool_calls` em chat_tools, JSON válido em chat_json_schema).
- [ ] **Passo 7:** medir tokens/s do qwen3:4b no `llama-server` (campo `timings` da resposta) e,
  com o Ollama ligado, no Ollama (`eval_count/eval_duration`). Anotar os dois no commit.
- [ ] **Passo 8:** commit `feat(motor): versao fixa do llama.cpp e amostras reais do llama-server`.

### Tarefa 2: registro de modelos (`motor/registro.py`)

**Arquivos:** Criar `motor/registro.py`, `motor/testes/falsos.py` (parte GGUF/pasta), `motor/testes/test_registro.py`

**Interfaces:**
- Produz:
  - `pasta_modelos() -> str` (regra da seção "Onde ficam as coisas")
  - `ler_gguf(caminho: str) -> dict` com chaves `arquitetura: str`, `contexto: int`,
    `template: str`, `parametros: int`, `embedding: bool`
    (embedding = arquitetura em `bert`, `nomic-bert`, `xlm-roberta`, `jina-bert-v2`, `gte` ou existe `<arq>.pooling_type`)
  - `@dataclass Modelo(nome: str, blob: str, tamanho: int, digest: str, familia: str,
    tamanho_param: str, quantizacao: str, params: dict, projetor: str | None, template_ollama: str, gguf: dict)`
  - `listar(pasta: str) -> list[Modelo]`; `achar(pasta: str, nome: str) -> Modelo | None`
  - `capacidades(m: Modelo) -> list[str]`; `normalizar_nome(nome: str) -> str`
- `falsos.py` produz `escrever_gguf(caminho, chaves: dict)` e `pasta_falsa(tmp, modelos: dict) -> str`.

- [ ] **Passo 1: testes que falham** em `test_registro.py`:
  - `test_lista_nome_e_tag`: pasta com `library/qwen3/4b` e `library/granite-embedding/278m` → nomes `["granite-embedding:278m", "qwen3:4b"]`.
  - `test_achar_aceita_variantes`: `achar(p, "qwen3:4b")`, `"registry.ollama.ai/library/qwen3:4b"`; `achar(p, "nomic")` sem tag acha `nomic:latest`; inexistente → `None`.
  - `test_details_do_config`: `familia == "qwen3"`, `tamanho_param == "4.0B"`, `quantizacao == "Q4_K_M"`.
  - `test_params_do_manifesto`: `params == {"temperature": 0.6, "top_k": 20, "top_p": 0.95, "stop": [...]}`.
  - `test_gguf`: GGUF sintético com `general.architecture=qwen3`, `qwen3.context_length=262144`, `tokenizer.chat_template="{{x}}"` → `contexto == 262144`, `embedding is False`; com `bert` → `embedding is True`.
  - `test_capacidades`: template com `tools` e `<think>` → `["completion", "tools", "thinking"]`; embedding → `["embedding"]`; com projetor → contém `"vision"`.
  - `test_pasta_modelos_regra`: com `OLLAMA_MODELS` → ela; sem ela e sem `~/.ollama/models` (HOME temporário) → `DATA_DIR/modelos`.
  - `test_manifesto_quebrado_e_ignorado`: JSON inválido ou blob ausente não derruba `listar`.
- [ ] **Passo 2:** `python -m unittest discover -s motor/testes -t motor/testes -p test_registro.py` → FALHA (módulo não existe).
- [ ] **Passo 3:** implementar. Leitor GGUF lê só o cabeçalho (v2/v3, tipos 0–12, arrays pulados sem carregar); para no último par chave-valor.
- [ ] **Passo 4:** mesmo comando → PASSA. Também rodar contra a pasta real: `listar(pasta_modelos())` mostra os 6 modelos da máquina.
- [ ] **Passo 5:** commit `feat(motor): registro de modelos lendo manifestos do Ollama e GGUF`.

### Tarefa 3: tradução Ollama ↔ OpenAI (`motor/traduz.py`)

**Arquivos:** Criar `motor/traduz.py`, `motor/testes/test_traduz.py`

**Interfaces:**
- Consome: `Modelo` (Tarefa 2).
- Produz:
  - `opcoes_openai(opcoes: dict, padrao: dict) -> dict` (temperature, top_p, top_k, min_p,
    repeat_penalty, seed, stop, presence_penalty, frequency_penalty; `num_predict`→`max_tokens`, `-1`/`-2` omitem)
  - `pedido_chat(corpo: dict, modelo: Modelo) -> dict` (corpo do `/v1/chat/completions`, sempre `stream: true` + `stream_options.include_usage`)
  - `pedido_generate(corpo: dict, modelo: Modelo) -> dict`
  - `class Juntador(nome: str, tipo: Literal["chat", "generate"])` com
    `pedaco(evento: dict) -> list[dict]` (linhas NDJSON do Ollama a mandar já) e
    `fim() -> dict` (linha final `done: true`, `done_reason`, `prompt_eval_count`, `eval_count`,
    `total_duration`, `eval_duration` em ns) e `inteiro() -> dict` (resposta sem stream)
  - `resposta_embeddings(dados: dict) -> dict`; `resposta_embed(dados: dict, nome: str) -> dict`
  - `keep_alive_segundos(valor, padrao: str) -> float | None` (`None` = para sempre)

- [ ] **Passo 1: testes que falham**, usando as amostras da Tarefa 1:
  - `test_opcoes_padrao_por_baixo`: `opcoes_openai({"temperature": 0.1, "num_predict": 50}, {"temperature": 0.6, "top_k": 20})` → `{"temperature": 0.1, "top_k": 20, "max_tokens": 50}`.
  - `test_format_json_e_schema`: `"json"` → `{"type": "json_object"}`; objeto → `json_schema` com `"name": "saida"`.
  - `test_think`: `True` → `chat_template_kwargs == {"enable_thinking": True}`; `"high"` → `{"reasoning_effort": "high"}`; ausente → sem a chave.
  - `test_generate_vira_mensagens`: `system` + `prompt` → `[{"role":"system"...},{"role":"user"...}]`.
  - `test_tool_calls_ida_e_volta`: histórico Ollama com `tool_calls` (argumentos objeto) e mensagem `tool` → OpenAI com `id` `call_0`, argumentos texto, `tool_call_id == "call_0"`.
  - `test_stream_chat_amostra`: alimentar `chat_stream.json` → linhas com `message.thinking` antes de `message.content`; texto juntado igual ao da amostra; última linha `done: true`, `done_reason: "stop"`, `eval_count` = `usage.completion_tokens`.
  - `test_stream_tools_amostra`: `chat_tools.json` → uma linha com `message.tool_calls[0].function.arguments` como objeto e `done_reason: "stop"`.
  - `test_generate_inteiro`: tipo `generate` → `{"response": ..., "thinking": ..., "done": true}`.
  - `test_embed_normaliza`: `resposta_embed` → norma de cada vetor = 1 (±1e-6); `resposta_embeddings` devolve o vetor sem mudar.
  - `test_keep_alive`: `"5m"` → 300; `"1h"` → 3600; `30` → 30; `0` → 0; `-1` → `None`; ausente → padrão.
  - `test_imagens_sem_projetor_erro`: mensagem com `images` e `modelo.projetor is None` → `ValueError("o modelo ... nao le imagens")`.
- [ ] **Passo 2:** rodar `-p test_traduz.py` → FALHA.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar → PASSA.
- [ ] **Passo 5:** commit `feat(motor): traducao entre a API do Ollama e a do llama-server`.

### Tarefa 4: processos `llama-server` (`motor/processos.py`)

**Arquivos:** Criar `motor/processos.py`; ampliar `motor/testes/falsos.py` (`llama-server` de mentira); criar `motor/testes/test_processos.py`

**Interfaces:**
- Consome: `Modelo`, `keep_alive_segundos`.
- Produz:
  - `class Gerente(binario: str, max_modelos: int = 2, ctx_padrao: int = 16384, keep_padrao: str = "5m", iniciar=None)`
    - `iniciar(argv: list[str]) -> asyncio.subprocess.Process`-like (injetável nos testes)
    - `async garantir(m: Modelo, ctx: int | None) -> str` (URL base do servidor pronto)
    - `usando(m: Modelo, ctx: int | None, keep_alive) -> AsyncContextManager[str]` (conta pedido em andamento; ao sair marca `expira_em`)
    - `async soltar(nome: str) -> bool`; `async soltar_todos() -> None`
    - `ativos() -> list[dict]` (formato de item do `/api/ps`: `name`, `model`, `size`, `digest`, `details`, `expires_at` ISO, `size_vram`, `context_length`)
    - `async faxina() -> None` (derruba expirados; o servidor chama a cada 5 s)
  - `class ErroMotor(Exception)` com mensagem em português.
- `falsos.py`: `LlamaFalso` (aiohttp em thread) que responde `/health` (503 por N chamadas, depois 200), `/v1/chat/completions` reproduzindo uma amostra, `/v1/embeddings`; opções `morrer_ao_carregar`, `morrer_depois`, `atraso_por_token`.

- [ ] **Passo 1: testes que falham:**
  - `test_argv`: `garantir(qwen, None)` chama `iniciar` com `-m <blob>`, `-c 16384`, `-ngl 999`, `--jinja`, `--reasoning-format deepseek`, `--host 127.0.0.1`; embedding ganha `--embeddings`.
  - `test_espera_health`: `/health` 503 três vezes → `garantir` só volta depois do 200.
  - `test_reaproveita`: dois `garantir` seguidos do mesmo modelo → `iniciar` chamado uma vez.
  - `test_contexto_maior_recarrega`: carregado com 16384, pedido de 32768 → processo velho encerrado, novo com `-c 32768`.
  - `test_contexto_limitado_pelo_modelo`: pedido 999999 em modelo de 40960 → `-c 40960`.
  - `test_limite_derruba_ocioso_mais_antigo`: max 2, carregar A, B, C (todos ociosos) → A encerrado.
  - `test_nao_derruba_modelo_em_uso`: max 1, A com `usando` aberto, `garantir(B)` espera; fechar A → B sobe.
  - `test_embedding_nao_conta_no_limite`: max 1 com um de geração e um de embedding → os dois vivos.
  - `test_keep_alive_zero_e_faxina`: `usando(..., keep_alive=0)` ao sair → `faxina()` encerra; `-1` nunca expira.
  - `test_processo_morre_no_carregamento`: `ErroMotor` em menos de 5 s, com o fim do stderr na mensagem.
  - `test_processo_morre_depois`: morto entre pedidos → próximo `garantir` sobe outro.
  - `test_ativos_formato`: um item com `name`, `expires_at` terminando em `Z`, `context_length`.
- [ ] **Passo 2:** rodar `-p test_processos.py` → FALHA.
- [ ] **Passo 3:** implementar. Porta livre: bind em `127.0.0.1:0` e soltar. Um `asyncio.Lock` por modelo para não subir dois iguais. Encerrar = `terminate`, 5 s, depois `kill`.
- [ ] **Passo 4:** rodar → PASSA.
- [ ] **Passo 5:** commit `feat(motor): gerente de processos do llama-server`.

### Tarefa 5: o servidor (`motor/nous_motor.py`)

**Arquivos:** Criar `motor/nous_motor.py`, `motor/testes/test_servidor.py`; ampliar `falsos.py` (`OllamaFalso`)

**Interfaces:**
- Consome: `registro`, `traduz`, `Gerente`, `baixar` (Tarefa 6 liga `/api/pull`; até lá a rota responde 501).
- Produz: `criar_app(motor: str, pasta: str, gerente: Gerente | None, ollama_url: str) -> aiohttp.web.Application`;
  `escolher_motor(data_dir: str, binario: str) -> str`; `main()` lê ambiente e sobe em `127.0.0.1:8989`
  (`NOUS_MOTOR_PORT` para testes), grava o PID em `%DATA_DIR%\motor\motor.pid` e, ao sair, `soltar_todos()`.

- [ ] **Passo 1: testes que falham** (app com `aiohttp.test_utils`, `LlamaFalso`, pasta falsa):
  - `test_tags_e_show`: `/api/version` responde `version`; `/api/tags` lista os nomes; `/api/show {"model":"qwen3:4b"}` traz `capabilities`, `details.family`, `model_info["qwen3.context_length"]`.
  - `test_chat_stream_ndjson`: `/api/chat` com `stream` omitido → `application/x-ndjson`, última linha `done: true`.
  - `test_chat_sem_stream`: `"stream": false` → um JSON só com `message.content`.
  - `test_generate_json_schema`: `format` objeto chega ao falso como `response_format.type == "json_schema"`.
  - `test_generate_vazio_carrega_e_keep_alive_zero_descarrega`: `prompt: ""` → `done_reason: "load"` e `/api/ps` com 1; `keep_alive: 0` → `/api/ps` vazio, `done_reason: "unload"`.
  - `test_embed_e_embeddings`: formatos de resposta da seção Desenho.
  - `test_modelo_inexistente`: `404 {"error": "modelo 'x' nao encontrado..."}`.
  - `test_cliente_desiste_fecha_upstream`: cliente fecha a conexão após a 1ª linha → o falso registra a conexão fechada antes do fim (`atraso_por_token`).
  - `test_rotas_nao_suportadas`: `/api/create` → 501 com `error`.
  - `test_modo_ollama_repassa`: `motor="ollama"` contra `OllamaFalso` → corpo e stream idênticos, inclusive `/api/pull`.
  - `test_escolher_motor`: `NOUS_MOTOR` vence; depois `ajustes.json`; sem nada, `llama` se o binário existe, senão `ollama`.
- [ ] **Passo 2:** rodar `-p test_servidor.py` → FALHA.
- [ ] **Passo 3:** implementar. Repasse no modo `ollama` copia status, `Content-Type` e corpo em pedaços.
- [ ] **Passo 4:** rodar → PASSA.
- [ ] **Passo 5:** commit `feat(motor): servidor nous-motor com modos llama e ollama`.

### Tarefa 6: baixar e apagar modelos (`motor/baixar.py`)

**Arquivos:** Criar `motor/baixar.py`, `motor/testes/test_baixar.py`; ampliar `falsos.py` (`RegistryFalso`); ligar as rotas em `nous_motor.py`

**Interfaces:**
- Produz: `async puxar(pasta: str, nome: str, registry: str = "https://registry.ollama.ai") -> AsyncIterator[dict]`
  (eventos iguais aos do Ollama: `{"status":"pulling manifest"}`, `{"status":"pulling <digest12>","digest","total","completed"}`,
  `{"status":"verifying sha256 digest"}`, `{"status":"writing manifest"}`, `{"status":"success"}`; erro → `{"error": ...}`);
  `apagar(pasta: str, nome: str) -> bool`.

- [ ] **Passo 1: testes que falham:**
  - `test_puxa_e_aparece_no_tags`: registry falso com manifesto + 2 blobs → arquivos no layout do Ollama; `registro.achar` encontra.
  - `test_eventos_iguais_ao_ollama`: sequência de `status` exatamente como acima; `completed` cresce até `total`.
  - `test_retoma_com_range`: blob parcial `*-partial` existente → pedido com `Range: bytes=<n>-`.
  - `test_sha_errado`: blob corrompido → `error` e nenhum manifesto gravado.
  - `test_blob_ja_existe_nao_baixa`: blob presente com sha certo → nenhum GET de blob.
  - `test_apagar_mantem_blob_compartilhado`: dois manifestos com o mesmo blob; apagar um → blob fica.
- [ ] **Passo 2:** rodar `-p test_baixar.py` → FALHA.
- [ ] **Passo 3:** implementar (Accept `application/vnd.docker.distribution.manifest.v2+json`; segue redirecionamento do blob; grava `sha256-<hex>-partial` e renomeia no fim).
- [ ] **Passo 4:** rodar → PASSA. Ligar `/api/pull` (stream e não-stream) e `/api/delete` no modo `llama`; teste em `test_servidor.py`: `test_pull_pelo_servidor`.
- [ ] **Passo 5:** commit `feat(motor): baixar e apagar modelos sem o Ollama`.

### Tarefa 7: ligar o motor no Nous

**Arquivos:**
- Criar: `ajustes/register_motor.py`, `motor/testes/test_register_motor.py`, `motor/testes/test_sem_11434.py`
- Modificar: `launchers/nous-env.ps1:12`, `launchers/start-nous.ps1` (Start-Motor; trecho do Ollama em ~424–448), `launchers/stop-nous.ps1`,
  `launchers/bandeja.ps1:23`, `atualizacao/nous-atualizar.ps1:29`, `tools/health-check.ps1:42-50`, `tools/lint.ps1` (etapa "Motor"),
  `agenda/nous_agenda.py:352`, `memory/nous_memory.py:104`, `images/nous_image_pipe.py:156`, `monitor/nous_monitor.py:58`, `search/nous_search/rag.py:10`

**Interfaces:**
- Produz: `MOTOR_URL = "http://127.0.0.1:8989"`; `register_motor.py --data-dir DIR` grava `ollama.base_urls = [MOTOR_URL]`,
  `rag.ollama.base_url = MOTOR_URL` (só se diferentes; usa `ajustes/config_db.py`), e entra no `Register-All` do launcher.

- [ ] **Passo 1: testes que falham:**
  - `test_register_motor`: webui.db temporário (config por chave e config em blob) com `11434` → depois `["http://127.0.0.1:8989"]`; rodar de novo não muda `updated_at`.
  - `test_sem_11434`: nenhum `.py/.ts/.js/.ps1` fora de `motor/`, `installer/`, testes e `bkp/` contém `11434`; os filtros com valve de URL têm padrão que lê `OLLAMA_BASE_URL`.
- [ ] **Passo 2:** rodar → FALHA.
- [ ] **Passo 3:** trocar os padrões fixos por `os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:8989")`
  (monitor: `NOUS_OLLAMA_URL` continua valendo para testes, depois `OLLAMA_BASE_URL`); `nous-env.ps1` aponta para 8989;
  `start-nous.ps1` ganha `Start-Motor` antes de tudo que usa IA e só liga o Ollama se `motor/ajustes.json` ou `NOUS_MOTOR` disser `ollama`
  (ou se o binário não existe); a espera por `/api/tags` passa a usar o motor; `stop-nous.ps1` encerra o motor (PID do `motor.pid`)
  e os `llama-server` filhos; `health-check.ps1` confere o motor; `lint.ps1` roda `motor/testes`.
- [ ] **Passo 4:** rodar os testes → PASSA; `tools/lint.ps1` completo → "Tudo certo".
- [ ] **Passo 5:** commit `feat(motor): Nous fala com o nous-motor em vez do Ollama`.

### Tarefa 8: teste de verdade na tela e instalador

**Arquivos:** Modificar `installer/install-nous.ps1`, `docs/DISTRIBUICAO.md`, `CHANGELOG.md`, `README.md` (seção de requisitos)

- [ ] **Passo 1:** instância de teste (app instalado parado; `sobe.ps1`/`servicos.ps1`/`registra.ps1` com `-Repo` do worktree,
  motor com `NOUS_LLAMA_SERVER=C:\dev\pessoal\nous-teste\llama\llama-server.exe`, Ollama DESLIGADO).
  Esperado: `/api/tags` do motor lista os 6 modelos; a tela abre com `qwen3:4b`.
- [ ] **Passo 2:** na tela: conversa normal com stream e "Pensou por…"; "me lembre de pagar a luz sexta às 9h" (filtro da agenda com JSON);
  "/pc lista os arquivos" (Comandos); painel "Seu Nous" mostra o modelo carregado e "Liberar a placa de vídeo" esvazia o `/api/ps`;
  Parar no meio de uma resposta longa → `llama-server` para de usar a GPU em segundos.
- [ ] **Passo 3:** embeddings: para 5 frases, cosseno entre `/api/embed` do motor e do Ollama (ligado só para isso) com
  `granite-embedding:278m` e `bge-m3`. Esperado ≥ 0,99. Se não, parar: reindexar seria preciso e o dono decide.
- [ ] **Passo 4:** Nous Code com o motor: uma tarefa que usa ferramenta (`read` de um arquivo) conclui.
- [ ] **Passo 5:** com OK do dono, `/api/pull all-minilm:22m` (~46 MB) pela Loja → aparece e responde embeddings; depois apagar pela tela.
- [ ] **Passo 6:** instalador: se `<app>\motor\bin\llama-server.exe` não existe, baixa o zip de `LLAMA_VERSAO.json`, confere o sha256 e extrai;
  o Ollama deixa de ser instalado por padrão (fica `-ComOllama`). Rodar só contra pastas de teste (`NOUS_VENV`/`NOUS_DATA_DIR`), nunca o app real.
- [ ] **Passo 7:** CHANGELOG ("Motor próprio"), DISTRIBUICAO.md e README; lint completo → "Tudo certo".
- [ ] **Passo 8:** commit `feat(motor): instalador leva o llama-server; Ollama vira opcional` e avisar o dono para PR e instalação.
