# Nous Code

Um IDE com agente de IA local, aberto numa janela própria. O agente roda no Ollama da máquina, ou no LM Studio, llama.cpp ou vLLM, e o editor é o Monaco, o mesmo do VS Code. A parte do agente adapta o [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (MIT): veja [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

| Parte | O que tem |
|---|---|
| Editor | Monaco em português, abas, Ctrl+S, minimapa e destaque de sintaxe. Recarrega sozinho quando o arquivo muda no disco; se houver mudanças não salvas, pergunta antes. |
| Arquivos | Árvore com novo, renomear, apagar (vai para a Lixeira) e "Perguntar ao agente sobre este arquivo". Ctrl+P abre arquivo pelo nome. |
| Busca | Ctrl+Shift+F no projeto inteiro, com maiúsculas e expressão regular. |
| Git | Ramo, arquivos mudados, diff lado a lado com o último commit, commit de tudo e descartar. |
| Terminal | PowerShell de verdade (ConPTY), aberto e fechado com Ctrl+`. |
| Agente | Ctrl+L pergunta sobre a seleção. Ele lê, procura, navega pelo código (LSP), edita e roda comandos. Editar e rodar esperam o seu OK com o diff na frente, e "Desfazer" volta os arquivos ao que eram antes da conversa. |
| Planejar | **Modo plano** (`/plano` ou o botão Planejar): o agente só investiga e chama `exit_plan_mode`. Você aprova ou pede para continuar planejando, com comentário. |
| Permissões | Somente leitura, Pedir antes de mudar, Editar sem perguntar e Acesso total. A política vale no servidor: o que é negado volta ao modelo como `POLICY_DENIED`. |
| Objetivo | `/objetivo` ou `create_goal`: depois de cada resposta o agente ganha uma nova rodada (`<goal_round>`) até marcar o objetivo como concluído ou bloqueado. São até 20 rodadas, com Pausar e Retomar no painel. |
| Lembretes | "Me lembre amanhã às 9h de rodar os testes": o agente cria o lembrete (`schedule_create`). Na hora marcada, a conversa roda sozinha; o que precisa de aprovação é recusado, porque não há ninguém na tela. |
| MCP | Servidores MCP no formato do `.mcp.json` do Claude Code. As ferramentas entram como `mcp__servidor__ferramenta`. |
| Conversa | Lista de tarefas (`todo_write`), perguntas com opções (`ask_user_question`), arquivos entregues (`present`), comandos `/` com autocompletar, `@arquivo`, renomear, duplicar a partir de um pedido, exportar em Markdown, buscar nas conversas e ver o que o modelo está vendo. |
| Problemas do código | Depois de cada edição o agente consulta o language server (TypeScript, JavaScript e Python) e recebe só os erros que a edição criou, no máximo 5, para corrigir no passo seguinte. O editor sublinha os mesmos erros e a conversa mostra uma linha com atalho para a linha. `NOUS_CODE_DIAGNOSTICOS=0` desliga. |
| Tarefa separada | **Nova tarefa separada** (menu ⋯ da conversa): o agente trabalha numa cópia do projeto (uma worktree do Git, em `NousData/code/tarefas/copias`), que parte do projeto como está agora, inclusive o que ainda não foi commitado. No fim, **Revisar e aplicar** mostra os arquivos mudados com o diff; **Aplicar** leva as mudanças ao projeto sem commitar, ou recusa sem tocar em nada se o projeto mudou nos mesmos trechos. **Descartar** apaga a cópia. Não vão para a cópia os arquivos novos ainda fora do Git e as pastas ignoradas (como `node_modules`). |
| Contexto | Medidor de tokens e compactação em duas etapas: primeiro encurta os resultados antigos; depois o modelo escreve um checkpoint com 8 seções. `/compactar` faz isso na hora. Se o contexto estourar, compacta e repete o passo. |

**Para abrir:**
- pelo atalho **Nous Code**, que liga o serviço se preciso;
- por **Código** no painel "Seu Nous";
- escrevendo "abre o código" no chat do Nous.

## Ferramentas do agente

Os nomes, parâmetros e textos seguem o DeepSeek Harness. Os nomes antigos do Nous Code e os do Claude Code continuam aceitos: `read_file`, `edit_file`, `run_command`, `Bash`, `Read` e outros.

| Ferramenta | O que faz |
|---|---|
| `read`, `write`, `edit` | Lê (numerado, `N: texto`, com `offset` e `limit`), cria ou troca texto. Só muda o que leu, e recusa se o arquivo mudou desde a leitura. |
| `glob`, `grep`, `list_files` | Acha arquivos por padrão (os mais recentes primeiro) e procura texto respeitando o `.gitignore`. Mostra no máximo 100 resultados; a lista inteira vai para um arquivo que o agente pode ler. |
| `lsp` | Ir para a definição, achar referências e implementações, e ver o tipo e a documentação (hover). Funciona em TypeScript e JavaScript (typescript-language-server) e em Python (pyright). |
| `pwsh` | PowerShell no projeto. Depois do tempo limite o comando não morre: vira um job em segundo plano. Quando ele termina, o agente recebe um aviso; `job_output` lê só o que saiu de novo. |
| `web_search`, `web_fetch` | Busca até 4 consultas de uma vez e lê páginas, sempre marcando o conteúdo como externo e não confiável. Pede permissão uma vez por conversa. |
| `todo_write`, `ask_user_question`, `exit_plan_mode` | Lista de tarefas, perguntas com opções (uma ou várias) e o plano para aprovar. |
| `create_goal`, `get_goal`, `update_goal` | Objetivo com rodadas automáticas. "Bloqueado" só é aceito depois de 3 rodadas. |
| `subagent` | Um subagente investiga com contexto próprio e devolve um relatório. Só lê, a menos que receba `edit=true` e `files` (os arquivos ou pastas que pode mudar): aí também edita, não roda comandos, e passa pelas mesmas permissões e pela mesma aprovação com diff; o que está fora de `files` volta como `POLICY_DENIED`. |
| `skill` | Carrega uma `SKILL.md` de `.nous`, `.agents`, `.claude` ou `.dsh` (projeto), ou de `~/.nous` e `~/.agents`. `/nome-da-skill` no pedido injeta as instruções. |
| `present` | Entrega arquivos (relatório, planilha), com os botões "Abrir no editor" e "Abrir no Windows". |
| `schedule_*` | Lembretes: daqui a N segundos, numa data, a cada N segundos, diário, semanal ou cron, sempre com fuso horário. |
| `mcp__*` | Ferramentas dos servidores MCP. As de leitura (`readOnlyHint`) valem até no modo plano. |

Os resultados grandes voltam ao modelo como início, `[...]` e fim, e a saída inteira fica num arquivo que ele pode abrir com `read` ou `grep`.

## O que o modelo recebe além do pedido

- **Instruções do projeto.** `~/.nous/AGENTS.md`, `~/.agents/AGENTS.md` e, da raiz do Git até o projeto, todos os `NOUS.md`, `AGENTS.md`, `CLAUDE.md` e `*.local.md`. Arquivos repetidos entram uma vez. As instruções de uma subpasta entram quando o agente mexe nela.
- **Contexto de execução.** Pasta, permissões, internet, a política do modo plano e as instruções dos servidores MCP. É reenviado só quando muda, sem alterar o prompt de sistema; assim o Ollama reaproveita o cache.
- **Hora.** No máximo a cada 10 minutos.
- **Catálogo de skills.** Só nome e descrição; o corpo carrega quando é usado.

## Modelos

O padrão é o `qwen2.5-coder:14b` do Ollama.
- **LM Studio:** quando está aberto, os modelos dele aparecem sozinhos na lista, como `lmstudio › modelo`.
- **Outros servidores compatíveis com a API da OpenAI**, como llama.cpp, vLLM e Jan: entram por `~/.nous/provedores.json`:

```json
{ "llamacpp": { "url": "http://127.0.0.1:8081/v1" }, "vllm": { "url": "http://servidor:8000/v1", "chave": "..." } }
```

**Modelos pequenos têm vícios, e o motor compensa:**
- **Chamada no texto.** O `qwen2.5-coder:14b` nunca usa o canal de ferramentas: escreve a chamada como JSON no texto. Por isso o texto é a via principal, e o canal nativo entra junto.
- **Edição tolerante.** O `edit` aceita o trecho copiado com os números de linha do `read` e também com o recuo diferente.
- **Anúncio sem ação.** Quando o modelo anuncia "vou verificar…" e para, o motor dá um empurrão, no máximo 2 por pedido.
- **Repetição.** A mesma chamada seguida recebe os avisos do DeepSeek Harness na 3ª, 5ª e 8ª vez; a mesma ação com o mesmo resultado 10 vezes encerra o pedido.

## Servidores MCP

Formato do `.mcp.json` do Claude Code:

```json
{ "mcpServers": {
  "github": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"], "env": { "GITHUB_TOKEN": "..." } },
  "docs":   { "type": "http", "url": "https://exemplo.com/mcp" }
} }
```

- **Para todos os projetos:** `~/.nous/mcp.json`. Vale sem perguntar, porque foi você quem escreveu.
- **De um projeto:** `.mcp.json` ou `.nous/mcp.json` na pasta dele. Esses rodam programas de quem fez o projeto. Só ligam depois que você permite, no cartão que aparece na conversa ou com `/mcp`; se o arquivo mudar, a permissão cai.
- **Permissões das ferramentas:** chamar uma ferramenta que não é só de leitura segue as permissões da conversa, como um comando.

## Como funciona

O serviço `servidor.ts` roda em `127.0.0.1:8998` e serve também a página do IDE (`ide/`). Como ele muda arquivos e roda comandos, só aceita como origem o Nous (`localhost:8080`) e a própria janela.

| Arquivo | O que faz |
|---|---|
| `servidor.ts` | HTTP: conversas do agente, cada uma respondida em NDJSON, um evento por linha; lembretes vencidos; permissões do MCP. |
| `agente.ts` | O laço modelo → ferramenta → modelo, o prompt, o contexto de execução, o objetivo, a compactação, a trava de repetição e o desfazer. |
| `ferramentas.ts` | Esquemas e implementação das ferramentas de arquivo, todas presas na pasta do projeto; apelidos; saída grande em arquivo. |
| `jobs.ts` | Comandos como jobs, com a saída inteira num arquivo e aviso quando terminam. |
| `web.ts` | `web_search` (DuckDuckGo, sem chave) e `web_fetch` (HTML para texto). |
| `contexto.ts` | Instruções em cadeia e catálogo de skills. |
| `lsp.ts` | Cliente LSP: um language server por projeto, iniciado sob demanda. |
| `mcp.ts` | Cliente MCP (stdio e HTTP) e a permissão dos servidores de projeto. |
| `tarefas.ts` | Tarefas separadas: a cópia do projeto em worktree do Git, a revisão, o aplicar e o descartar. |
| `lembretes.ts` | Lembretes com fuso horário e cron, sem biblioteca. |
| `modelo.ts` | O `/api/chat` do Ollama, o `chat/completions` dos compatíveis com OpenAI e a leitura das chamadas de ferramenta. |
| `ide.ts` | Arquivos, busca, Git, a janela (modo app do Edge) e o WebSocket do terminal e dos avisos. |
| `ide/` | A página: `app.js` sem build, com Monaco e xterm servidos de `node_modules`. |

As conversas, os lembretes e as saídas completas ficam em `NousData/code/`.

**Dependências** (o instalador baixa com `npm ci --omit=dev`):
- `monaco-editor`, `@xterm/xterm` e `@xterm/addon-fit`, para a tela;
- `@lydell/node-pty`, o ConPTY com binário pronto, sem compilar;
- `ws`, para o WebSocket;
- o **Node** em si: se o computador não tem o 22.18+, o instalador baixa o Node portátil (zip oficial, SHA256 fixado) para `runtime
ode` na pasta do Nous, sem mexer no PATH (`launchers/node-nous.ps1`; teste isolado em `tools/testar-node-portatil.ps1`);
- opcionais: `typescript-language-server`, `typescript` e `pyright`, para o `lsp`.

## Desenvolvimento

```powershell
cd code
npm install          # inclui typescript e @types/node para checar tipos
npm test             # núcleo, ferramentas, lembretes, MCP e políticas do agente (com um Ollama de mentira)
npx tsc -p .         # checagem de tipos
node servidor.ts     # sobe o serviço; abra http://127.0.0.1:8998
```
