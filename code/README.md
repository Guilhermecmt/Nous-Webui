# Nous Code

Um IDE com agente de IA local, aberto numa janela própria. O agente roda no Ollama da máquina, e o editor é o Monaco, o mesmo do VS Code.

| Parte | O que tem |
|---|---|
| Editor | Monaco em português, abas, Ctrl+S, minimapa, destaque de sintaxe. Recarrega sozinho quando o arquivo muda no disco; se você tiver mudanças não salvas, pergunta antes. |
| Arquivos | Árvore com novo, renomear, apagar (vai para a Lixeira) e "Perguntar ao agente sobre este arquivo". Ctrl+P abre arquivo pelo nome. |
| Busca | Ctrl+Shift+F no projeto inteiro, com maiúsculas e expressão regular. |
| Git | Ramo, arquivos mudados, diff lado a lado com o último commit, commit de tudo e descartar. |
| Terminal | PowerShell de verdade (ConPTY), aberto e fechado com Ctrl+`. |
| Agente | Ctrl+L pergunta sobre a seleção. Ele lista, lê, procura, edita e roda comandos, um passo por vez. Editar e rodar esperam o seu OK com o diff na frente ("Editar sem perguntar" libera só as edições), e "Desfazer" volta os arquivos ao que eram antes da conversa. |

**Para abrir:**
- pelo atalho **Nous Code**, que liga o serviço se preciso;
- por **Código** no painel "Seu Nous";
- escrevendo "abre o código" no chat do Nous.

## Como funciona

O serviço `servidor.ts` roda em `127.0.0.1:8998` e serve também a página do IDE (`ide/`). Ele só aceita o Nous (`localhost:8080`) e a própria janela como origem, porque muda arquivos e roda comandos.

| Arquivo | O que faz |
|---|---|
| `servidor.ts` | HTTP: conversas do agente, cada uma respondida em NDJSON, um evento por linha. |
| `agente.ts` | O laço modelo → ferramenta → modelo, o prompt, o contexto, a trava de repetição e o desfazer. |
| `ferramentas.ts` | `list_files`, `read_file`, `search`, `edit_file`, `write_file` e `run_command`, todas presas na pasta do projeto. |
| `modelo.ts` | O `/api/chat` do Ollama e a leitura das chamadas de ferramenta. |
| `ide.ts` | Arquivos, busca, Git, a janela (modo app do Edge) e o WebSocket do terminal e dos avisos de arquivo mudado. |
| `ide/` | A página: `app.js` sem build, com Monaco e xterm servidos de `node_modules`. |

**Modelos pequenos têm vícios, e o motor compensa:**
- O `qwen2.5-coder:14b` nunca usa o canal de ferramentas do Ollama: escreve a chamada como JSON no texto. Por isso o texto é a via principal e o canal nativo entra junto.
- O `edit_file` aceita o trecho copiado com os números de linha do `read_file` e também com o recuo diferente.
- Quando o modelo anuncia "vou verificar…" e para, o motor dá um empurrão, no máximo 2 por pedido.
- A mesma ação com o mesmo resultado pela terceira vez encerra o pedido com uma explicação.

As conversas ficam em `NousData/code/sessoes/`. O agente lê `NOUS.md`, `AGENTS.md` ou `CLAUDE.md` na raiz do projeto, se existirem.

**Dependências de execução** (o instalador baixa com `npm ci --omit=dev`):
- `monaco-editor` e `@xterm/xterm` + `@xterm/addon-fit`, para a tela;
- `@lydell/node-pty`, o ConPTY com binário pronto, sem compilar;
- `ws`, para o WebSocket.

## Desenvolvimento

```powershell
cd code
npm install          # inclui typescript e @types/node para checar tipos
npm test             # testes do núcleo, sem modelo
npx tsc -p .         # checagem de tipos
node servidor.ts     # sobe o serviço; abra http://127.0.0.1:8998
```
