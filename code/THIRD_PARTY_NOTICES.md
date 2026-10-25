# Avisos de terceiros: Nous Code

O Nous Code é MIT, como o resto do Nous. Partes dele foram copiadas ou adaptadas de outros projetos de código aberto, listados abaixo com as licenças deles.

## DeepSeek Harness

O agente do Nous Code adapta partes do [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (`dsh`), da DeepSeek. Usamos o checkout de 17/10/2026, versão 0.2.1-rc.2.

**O que veio de lá:**

O contrato das ferramentas com o modelo. Isso inclui os nomes, os parâmetros, as descrições, o formato dos resultados e as mensagens de erro e de correção de:
- `read`, `write`, `edit`, `glob`, `grep`;
- `pwsh`, `job_output`, `job_list`, `job_kill`;
- `web_search`, `web_fetch`, `todo_write`, `ask_user_question`, `exit_plan_mode`;
- `create_goal`, `get_goal`, `update_goal`;
- `skill`, `subagent`, `lsp`, `present`;
- `schedule_create`, `schedule_list`, `schedule_update`, `schedule_delete`.

As políticas do agente e os textos que o modelo recebe:

| Parte | Pacotes de origem |
|---|---|
| Contexto de execução enviado como mensagem | `dsh-system-prompt` |
| Modo plano | `dsh-plan-mode` |
| Objetivo com rodadas automáticas e mensagem de fechamento | `dsh-goal`, `dsh-tool-goal`, `dsh-goal-round-driver` |
| Aviso de chamada repetida na 3ª, 5ª e 8ª vez | `dsh-repeat-tool-reminder` |
| Compactação em duas etapas: poda dos resultados, depois checkpoint com 8 seções | `dsh-compaction-basic`, `dsh-compaction-tool-result-pruner` |
| Título da conversa | `dsh-session-title-first-prompt-llm` |
| Hora no contexto | `dsh-time-context` |
| Aviso de job terminado | `dsh-tool-jobs` |
| Saída grande guardada em arquivo | `dsh-spill-policy` |
| Instruções do projeto em cadeia | `dsh-agent-instructions` |
| Catálogo de skills e `<skill_content>` | `dsh-tool-skill`, `dsh-skill-filesystem` |
| Contexto do subagente | `dsh-subagent` |

Os módulos adaptados:

| Módulo | Pacotes de origem |
|---|---|
| Cliente LSP: `code/lsp.ts` | `dsh-lsp`, `dsh-lsp-stdio`, `dsh-tool-lsp` |
| Cliente MCP: `code/mcp.ts` | `dsh-mcp-client` |
| Lembretes: `code/lembretes.ts` | `dsh-schedule`, `dsh-tool-schedule` |

Para caber no contexto de um modelo local de 14B, mudamos três coisas:
- os limites ficaram menores;
- a edição ficou mais tolerante;
- os nomes antigos das ferramentas continuam aceitos como apelidos.

Cada arquivo adaptado diz no cabeçalho de quais pacotes veio.

```
MIT License

Copyright (c) 2026 DeepSeek

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Dependências instaladas pelo npm

Elas não são copiadas para o repositório: o instalador baixa cada uma com a própria licença.

| Pacote | Licença | Para quê |
|---|---|---|
| [monaco-editor](https://github.com/microsoft/monaco-editor) | MIT | o editor |
| [@xterm/xterm](https://github.com/xtermjs/xterm.js) e @xterm/addon-fit | MIT | o terminal |
| [@lydell/node-pty](https://github.com/lydell/node-pty) | MIT | o PowerShell do terminal (ConPTY) |
| [ws](https://github.com/websockets/ws) | MIT | o WebSocket do terminal e dos avisos |
| [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server) | Apache-2.0 | `lsp` em TypeScript e JavaScript (opcional) |
| [typescript](https://github.com/microsoft/TypeScript) | Apache-2.0 | o motor do language server acima (opcional) |
| [pyright](https://github.com/microsoft/pyright) | MIT | `lsp` em Python (opcional) |
