<div align="center">

<img src="branding/assets/nous_logo.png" width="112" alt="Logo do Nous">

# Nous

**Sua IA particular, rodando no seu computador.**

Chat, documentos, agenda, e-mail, pesquisa e programação com IA local no Windows.<br>
Sem nuvem, sem mensalidade e sem conta para criar.

[![Versão](https://img.shields.io/badge/vers%C3%A3o-2.11.0-c8962e)](CHANGELOG.md)
[![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-1f1b16)](LICENSE)
[![Windows 10 e 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6)](#requisitos)
[![100% local](https://img.shields.io/badge/IA-100%25%20local-2ea44f)](#privacidade-e-segurança)
[![Lint](https://github.com/Guilhermecmt/Nous-Webui/actions/workflows/lint.yml/badge.svg)](https://github.com/Guilhermecmt/Nous-Webui/actions)

[English](README.md) · **Português**

[Instalação](#instalação) · [Recursos](#recursos) · [Nous Code](#nous-code) · [Privacidade](#privacidade-e-segurança) · [Desenvolvimento](#para-desenvolvedores)

<img src="docs/screenshots/inicio-escuro.png" width="900" alt="Tela inicial do Nous com o painel Seu Nous">

</div>

## Visão geral

**Nous** (do grego *νοῦς*, "mente") transforma o [Open WebUI](https://github.com/open-webui/open-webui) e o [Ollama](https://ollama.com) num produto pronto para quem não é técnico. Ele instala com dois cliques, escolhe o modelo certo para o seu hardware e roda tudo em segundo plano, sem janelas de terminal.

- **Privado por padrão.** O modelo roda na sua máquina, o servidor só aceita conexões do próprio PC e conversas, memórias e arquivos ficam no seu disco.
- **Pronto para usar.** Não pede conta, chave de API nem configuração. Na primeira vez, um assistente recomenda e baixa o modelo ideal para a sua placa de vídeo.
- **Mais que um chat.** Ele lembra de você, lê as suas notas, escreve documentos com você, cuida da agenda e do e-mail, pesquisa na web com fontes e programa com um agente de verdade.
- **Feito para modelos locais.** Cada recurso foi testado com modelos pequenos (4B a 14B) rodando numa GPU doméstica, não só com modelos de nuvem.

## Galeria

<table>
<tr>
<td width="50%"><img src="docs/screenshots/conversa.png" alt="Conversa com respostas que podem ser encurtadas, simplificadas ou levadas para Documentos"><br><sub><b>Chat.</b> Cada resposta tem "Mais curto", "Mais simples" e "Documento". O painel à direita mostra a placa de vídeo, a agenda e o que o Nous sabe de você.</sub></td>
<td width="50%"><img src="docs/screenshots/documentos.png" alt="Documentos com sugestões da IA riscadas e sublinhadas"><br><sub><b>Documentos.</b> A IA só sugere: cada mudança aparece riscada e sublinhada, e você aceita ou recusa uma a uma.</sub></td>
</tr>
<tr>
<td width="50%"><img src="docs/screenshots/loja.png" alt="Loja de modelos com recomendação para a placa de vídeo"><br><sub><b>Loja de modelos.</b> Recomenda o que roda bem na sua placa, mostra a velocidade estimada e baixa com um clique.</sub></td>
<td width="50%"><img src="docs/screenshots/inicio-claro.png" alt="Tela inicial no tema claro"><br><sub><b>Tema claro.</b> Branco e dourado, com a mesma tela inicial e o mesmo painel.</sub></td>
</tr>
</table>

## Nous Code

Um IDE com agente de programação que usa só IA local, aberto numa janela própria. Ele junta o editor do VS Code (Monaco), arquivos, busca, Git e um terminal de verdade, com um agente ao lado que lê o seu projeto, propõe um plano, edita e roda os testes. Toda mudança passa pela sua aprovação. A parte do agente adapta o [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), de código aberto (MIT): as mesmas ferramentas, prompts e políticas, ajustados para um modelo local de 14B.

<img src="docs/screenshots/nous-code.png" width="900" alt="Nous Code com o editor, o terminal e um plano proposto pelo agente">

| No editor | No agente |
|---|---|
| Monaco em português, abas, minimapa, Ctrl+S | Lê, procura (`glob`, `grep`), navega pelo código com language server (`lsp`), edita e roda comandos |
| Árvore de arquivos com criar, renomear e apagar (vai para a Lixeira) | **Modo plano** (`/plano`): investiga sem mexer em nada e propõe um plano para você aprovar |
| **Ctrl+P** para abrir arquivo e **Ctrl+Shift+F** para buscar no projeto | **Permissões** em quatro níveis, de "Somente leitura" a "Acesso total" |
| Git: arquivos mudados, diff lado a lado, commit e descartar | Diff na tela antes de cada mudança e **Desfazer** por arquivo ou tudo |
| Terminal PowerShell real (ConPTY), com **Ctrl+`** | Lista de tarefas, perguntas com opções e **objetivo** (`/objetivo`) em que ele segue trabalhando, rodada após rodada, até cumprir |
| Recarrega o arquivo quando o agente o muda no disco | Comandos longos viram jobs em segundo plano, e o agente é avisado quando terminam |
| **Ctrl+L** pergunta ao agente sobre o trecho selecionado | **Lembretes** ("me lembre amanhã às 9h de rodar os testes") que rodam a conversa sozinhos |
| | **Servidores MCP** (`.mcp.json`, o formato do Claude Code), internet com permissão e arquivos entregues |
| | Compactação do contexto, subagente de pesquisa, skills (`SKILL.md`) e `@arquivo` |
| | Ollama e também **LM Studio**, llama.cpp ou vLLM pela API compatível com a OpenAI |

<img src="docs/screenshots/nous-code-diff.png" width="900" alt="O agente pede para aplicar uma correção, mostrando o diff">

**Feito para modelos pequenos.** O motor compensa os vícios mais comuns dos modelos locais:
- Lê chamadas de ferramenta escritas como JSON no texto. O `qwen2.5-coder:14b`, por exemplo, nunca usa o canal nativo do Ollama.
- Só deixa editar um arquivo depois de lê-lo, e recusa a edição se o arquivo mudou desde a leitura.
- Aceita o trecho copiado com os números de linha ou com o recuo diferente.
- Avisa quando o modelo repete a mesma chamada (na 3ª, 5ª e 8ª vez) e para depois de dez resultados iguais.
- Resume a conversa antes de estourar o contexto.

**Como abrir:**
- pelo atalho **Nous Code**;
- por **Código** no painel "Seu Nous";
- escrevendo *"abre o código"* no chat.

Precisa do [Node.js](https://nodejs.org) 22.18 ou mais novo (`winget install OpenJS.NodeJS.LTS`). Com ele presente, o instalador baixa o editor e cria o atalho. Detalhes técnicos em [`code/README.md`](code/README.md).

## Novidades da versão 2.11

- **Primeiros passos.** Para quem nunca usou IA: lições curtas enquanto o modelo baixa, cartões com tarefas do dia a dia para a primeira conversa e o botão **?** para rever tudo.
- **No celular.** Em casa, pelo mesmo Wi-Fi: ligue em **Seu Nous › Celular** e leia o QR. Vem desligado, e só aparelhos que você parear entram. Veja [docs/CELULAR.md](docs/CELULAR.md).
- **Agenda nos dois sentidos.** Conecte iCloud, Nextcloud ou Fastmail (CalDAV) e o que você muda aqui aparece lá, e vice-versa. Veja [docs/AGENDA-CALDAV.md](docs/AGENDA-CALDAV.md).
- **Ícone na bandeja.** Perto do relógio: abrir, iniciar, parar e ver o estado do Nous sem janela nenhuma.
- **Atualiza sozinho.** O Nous avisa quando há versão nova dele ou de um modelo e atualiza com um clique, voltando ao que era se algo der errado.
- **Por dentro.** Open WebUI 0.12.3, Loja com modelos novos, e-mail e motor de imagem testados de ponta a ponta, e o Nous Code corrigindo os próprios erros.

## Novidades da versão 2.10

- **Sem login.** O Nous abre direto no chat, como qualquer programa. A sua conta e as suas conversas antigas continuam lá. Com duas ou mais contas no mesmo PC, o login volta sozinho.
- **Painel "Seu Nous".** A coruja num anel mostra o uso da placa de vídeo, e o painel reúne a conversa privada, os próximos lembretes, o que o Nous sabe de você e todas as ferramentas.
- **Nous Code.** IDE com agente de IA local em janela própria, descrito acima.
- **Conversa privada.** Não fica no histórico nem vira memória.

O histórico completo está no [CHANGELOG](CHANGELOG.md).

## Requisitos

| | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10 ou 11 | Windows 11 |
| Memória RAM | 8 GB | 16 GB ou mais |
| Placa de vídeo | Nenhuma: roda na CPU | 8 GB de VRAM ou mais |
| Disco livre | 20 GB | 30 GB ou mais |

Sem placa de vídeo dedicada, o Nous funciona na CPU e as respostas só demoram mais. A Loja de modelos percebe isso e recomenda modelos leves.

## Instalação

1. Em **Code → Download ZIP**, no topo desta página, baixe o projeto e descompacte onde quiser.
2. Dê **clique duplo em `instalar.bat`**. Se o Windows avisar, escolha **Mais informações → Executar assim mesmo**.

O instalador:
- confere o hardware;
- instala o Ollama, o Python 3.11, a interface e o Node.js portátil do Nous Code (sem mexer no que já existe na máquina);
- aplica a identidade do Nous;
- cria os atalhos na área de trabalho e no Menu Iniciar.

No fim, o Nous abre sozinho no navegador. Ele fica em `%LOCALAPPDATA%\Programs\Nous`, então a pasta baixada pode ser apagada. Se algum passo falhar, o instalador mostra o motivo em vermelho em vez de dizer "Pronto!".

## Primeiro uso

1. **Abra.** Não há conta nem senha: o Nous abre direto no chat.
2. **Escolha o modelo.** Sem nenhum modelo instalado, uma tela de boas-vindas mostra o recomendado para o seu computador. **Baixar e começar** cuida do resto, com barra de progresso.
3. **Aprenda enquanto baixa.** Cinco lições curtas explicam o que é um modelo, que a IA pode errar e como pedir bem. Pule quando quiser.
4. **Converse.** Quando o download terminar, escolha um dos cartões da tela inicial ou escreva o que quiser. O botão **?** reabre as lições e o passeio pela tela.

Se várias pessoas dividem o computador, crie uma conta para cada uma em **Painel do Admin › Usuários**. Com duas ou mais contas o login volta, e cada pessoa vê só as próprias conversas.

## Recursos

### Painel "Seu Nous"

Fica fixo à direita e reúne o que importa:
- a placa de vídeo, num anel em volta da coruja que fica dourado quando há um modelo carregado, com **Liberar a placa de vídeo**;
- a **conversa privada**;
- os próximos lembretes;
- o que o Nous sabe de você;
- as **Ferramentas**: Documentos, Código, Agenda, E-mail, Pesquisas, Galeria, Editar fotos, Formulários, Habilidades, Comparar, Modelos, Voz e Diagnóstico.

Em telas menores ele vira uma gaveta. Fechado, sobra só a coruja no canto.

### Modelos de IA

Abra a Loja em **Ferramentas › Modelos**. Ela mostra:
- um catálogo com o selo **Recomendado para sua máquina**;
- a velocidade estimada na sua placa;
- quanto da memória de vídeo cada modelo ocupa;
- o selo **Entende imagens** nos modelos com visão.

| Sua máquina | Modelo sugerido | Download | Perfil |
|---|---|---|---|
| Sem GPU dedicada | Qwen 3.5 4B | ~3,4 GB | Leve, rápido na CPU, entende imagens |
| GPU de 8 a 12 GB | Gemma 4 12B | ~7,6 GB | Conversa, escrita e visão |
| GPU de 12 a 16 GB | Qwen 3 14B | ~9,3 GB | Raciocínio melhor e contexto mais longo |
| GPU de 20 GB ou mais | Qwen 3 32B | ~20 GB | Qualidade próxima dos grandes modelos de nuvem |

**Outro modelo** aceita qualquer nome do Ollama ou link do Hugging Face (GGUF). O Nous lê o tamanho no catálogo, sem baixar nada, e diz se o modelo cabe na placa e no disco antes de oferecer o download. **E se eu tivesse outra máquina?** simula outra placa e mostra o que rodaria.

### Memória

Conversando normalmente, o Nous guarda fatos duráveis (nome, cidade, trabalho, preferências) e os usa nas conversas seguintes. Em **O que eu sei de você › Ver e editar** você:
- vê, corrige, fixa e apaga cada memória;
- cria **personas** com memórias separadas;
- junta repetidas com **Organizar memórias**;
- usa **Importar**, que lê um currículo, um texto "sobre mim" ou as memórias do ChatGPT e deixa você escolher o que guardar;
- usa **Exportar**, que gera um backup.

### Documentos

Escreva cartas, currículos e trabalhos ao lado do chat, ou abra um `.docx`, `.pdf`, `.txt` ou `.md`.

**Pedidos prontos:**
- Corrigir português
- Mais formal
- Mais simples
- Mais curto
- Tópicos em texto
- Organizar com títulos
- Continuar escrevendo

**Como a revisão funciona:** a IA nunca escreve direto no texto. Cada mudança aparece riscada e sublinhada, com o texto chegando ao vivo, e você aceita ou recusa. **Por quê?** explica cada sugestão, e selecionar um trecho limita a mudança a ele.

O documento salva sozinho, guarda versões (dá para comparar antes de voltar) e baixa em **Word, PDF ou Markdown**.

### Agenda, lembretes e tarefas

*"Me lembre de pagar a luz sexta às 9h"* vira um aviso do Windows na hora certa, mesmo com o navegador fechado. A agenda tem:
- notas com listas de verificação;
- calendário com importação de `.ics` e assinatura do Google Agenda, Outlook ou iCloud;
- avisos no celular (ntfy) ou por e-mail;
- **tarefas agendadas**, como *"todo dia às 8h, bom dia com a agenda e os e-mails"*, que rodam sozinhas e podem encadear umas nas outras.

Datas e horas são lidas por regra, sem depender do palpite do modelo.

### E-mail (opcional)

Conecte Gmail, Outlook ou Yahoo, uma ou várias contas, com uma senha de aplicativo. O Nous:
- separa importante, pode esperar, promoção e spam;
- resume mensagens e anexos;
- rascunha respostas;
- aprende os contatos;
- escreve pelo chat (*"manda um e-mail para a Ana dizendo que atraso 10 minutos"*).

Ele nunca envia sem a sua confirmação, e os e-mails só passam pelo modelo local.

### Pesquisa Profunda

Escolha **Pesquisa Profunda (Nous)** no seletor de modelos. O Nous:
1. planeja sub-perguntas;
2. busca na web (SearXNG local);
3. lê as páginas;
4. entrega um relatório com citações numeradas e a lista de fontes.

Os relatórios ficam em **Ferramentas › Pesquisas**, baixam em PDF ou Word e podem continuar no chat.

### Mais recursos

- **Arquivos:** tudo o que você põe em `Documentos\Nous`, ou no seu vault do Obsidian, entra na busca antes de cada resposta, com embeddings multilíngues.
- **Habilidades:** diga *"aprenda isso"* e o Nous guarda o passo a passo para os próximos pedidos parecidos, inclusive o seu jeito de escrever.
- **Comparar modelos:** a mesma pergunta para 2 a 4 modelos, voto às cegas e um placar.
- **Leitura de imagens e boletos:** OCR local mesmo com modelos sem visão. Boletos saem com banco, valor e vencimento conferidos.
- **Formulários PDF:** preenche e assina.
- **Editor de fotos e Galeria:** cortar, ajustar, remover o fundo com IA local ou escrever *"tira o fundo e corta quadrado"*.
- **Geração de imagem (opcional):** ComfyUI com Flux.1 Schnell, por *"crie uma imagem de…"*.
- **Voz em português (opcional):** Piper e Whisper locais, com modo de conversa sem as mãos.
- **Utilidades no chat:** resumo de vídeos do YouTube, previsão do tempo e comandos como *"tema escuro"* ou *"libera a placa de vídeo"*.
- **Nous Nuvem (opcional):** modelos de fronteira pela API gratuita da NVIDIA, sem levar a sua memória pessoal junto.
- **Diagnóstico:** cada parte do Nous com ✓ ou ✗ e o que fazer. Lá também ficam a privacidade na tela (CPF, cartões e chaves borrados) e as dicas de primeiro uso.

## Privacidade e segurança

- **Tudo local.** Os modelos rodam no Ollama da sua máquina. Conversas, memórias, documentos e índices ficam em `%USERPROFILE%\NousData`.
- **Só o próprio PC.** O servidor do Nous e todos os serviços escutam apenas em `127.0.0.1`, então outros aparelhos da rede não chegam neles. O servidor e os serviços recusam páginas de outros sites.
- **Celular só se você ligar.** O portão do celular só existe enquanto está ligado, só atende a rede de casa (rede Privada no Windows) e só aparelhos pareados por QR. Quem entra usa o Nous inteiro, porque não há login. O Nous Code nunca passa por ele.
- **Atualização com aviso.** Procurar versão nova é uma ida à internet, no máximo uma vez por dia, e dá para desligar no ícone da bandeja. Nada é baixado sem o seu clique.
- **Sem login, com escolha.** Como ninguém de fora acessa o Nous, quem protege os dados é a senha do Windows. Para exigir login mesmo assim, crie um arquivo vazio `NousData\.exigir_login`.
- **Nada sai sem você pedir.** A busca na web, a Nuvem NVIDIA e o e-mail são opcionais. A memória pessoal nunca vai para modelos de nuvem.
- **Agente sob controle.** O Nous Code só mexe na pasta do projeto escolhido. Mudanças e comandos pedem aprovação, a internet pede permissão por conversa, e tudo o que ele muda pode ser desfeito.

## Problemas comuns

<details>
<summary><b>"O Windows protegeu seu computador"</b></summary>

Aviso padrão para programas sem assinatura digital. Clique em **Mais informações → Executar assim mesmo**.
</details>

<details>
<summary><b>O atalho não apareceu na área de trabalho</b></summary>

Alguns antivírus bloqueiam atalhos. Aperte a tecla Windows e digite **Nous**: o atalho do Menu Iniciar sempre é criado. Outra opção é dar clique duplo em `iniciar.bat`, em `%LOCALAPPDATA%\Programs\Nous`.
</details>

<details>
<summary><b>Aparece "Open WebUI" no lugar do Nous</b></summary>

Abra pelo atalho e aperte **Ctrl+Shift+R** no navegador. A identidade é conferida e reaplicada a cada início.
</details>

<details>
<summary><b>O chat não responde</b></summary>

Abra o Nous pelo atalho, que liga todos os serviços. Se continuar, use **Liberar a placa de vídeo** no painel e tente de novo. **Ferramentas › Diagnóstico** mostra o que está parado.
</details>

<details>
<summary><b>O Nous Code não abre</b></summary>

Rode o `instalar.bat` de novo: ele baixa o Node.js portátil (se o computador não tiver o Node 22.18 ou mais novo), baixa o editor e cria o atalho **Nous Code**.
</details>

<details>
<summary><b>Quero a tela de login de volta</b></summary>

Crie um arquivo vazio chamado `.exigir_login` em `%USERPROFILE%\NousData` e abra o Nous de novo. A sua conta volta ao e-mail e à senha de antes. Para tirar o login outra vez, apague o arquivo.
</details>

<details>
<summary><b>Não acho o ícone do Nous perto do relógio</b></summary>

No Windows 11 os ícones novos começam escondidos na setinha **^** da barra de tarefas. Abra a setinha e arraste a coruja para a barra.
</details>

<details>
<summary><b>O celular não abre o Nous</b></summary>

Confira se o celular está no mesmo Wi-Fi do computador e se a rede do Windows está como **Privada** (o painel do celular avisa e mostra o caminho). Na primeira vez que você liga, o Windows pede permissão para o firewall: aceite.
</details>

## Desinstalar

Em **Configurações → Aplicativos → Aplicativos instalados**, procure **Nous** e clique em **Desinstalar**:
- **Remoção segura** (recomendada): remove o app e o ambiente Python e preserva as conversas, as notas, o Ollama e o Python.
- **Remover tudo**: apaga também os dados e desinstala o Ollama e o Python, só se foi o Nous que os instalou.

## Para desenvolvedores

### Arquitetura

O Nous é uma camada de produto sobre o Open WebUI 0.12.3 (versão fixada no instalador). Ele junta a identidade visual, injetada por um `loader.js` com os painéis, filtros e pipes registrados no banco e serviços locais pequenos, todos em `127.0.0.1`:

| Porta | Serviço | Pasta |
|---|---|---|
| 8080 | Open WebUI com a identidade do Nous | `branding/`, `ajustes/` |
| 8990 | Monitor: Loja, Diagnóstico, Documentos, Galeria, Editor, Formulários, Comparar, relatórios | `monitor/`, `documentos/` |
| 8991, 8992 | Indexadores de arquivos e do histórico | `files/`, `history/` |
| 8993 | Memória e personas | `memory/` |
| 8994 | Voz (Piper) | `voice/` |
| 8995 | E-mail | `email/` |
| 8996 | Agenda, lembretes e tarefas | `agenda/` |
| 8997 | Habilidades | `skills/` |
| 8998 | Nous Code (IDE e agente, Node) | `code/` |
| 8999 | Portão do celular (só quando ligado; rede de casa) | `celular/` |
| 8188 | ComfyUI (opcional) | `images/` |
| 11434 | Ollama | |

O lançador (`launchers/start-nous.ps1`) sobe tudo escondido e registra filtros e ajustes a cada início. As operações são idempotentes: rodar de novo não quebra nada.

### Estrutura

```
branding/    identidade, loader.js e módulos dos painéis (branding/modules)
code/        Nous Code: agente (agente.ts), ferramentas, servidor e o IDE (code/ide)
monitor/     Loja de modelos, diagnóstico e APIs dos painéis
memory/      memória pessoal: filtro, API e personas
documentos/  Documentos (sugestões, versões, Word/PDF) e formulários PDF
agenda/      notas, lembretes, calendário e tarefas agendadas
email/       cliente IMAP/SMTP e API
search/      busca na web e Pesquisa Profunda
skills/      habilidades
utilidades/  filtros do chat: YouTube, clima, OCR, compactação, comandos
files/       busca nos seus arquivos
history/     busca no histórico de conversas
images/      ComfyUI, Flux e pipe de imagem
voice/       voz em português
cloud/       Nous Nuvem (NVIDIA NIM)
ajustes/     padrões do Open WebUI e acesso sem login
evaluation/  comparação de modelos
installer/   instalador, desinstalador e Inno Setup
launchers/   iniciar e parar em segundo plano
tools/       lint, health check, backup, análise de hardware
```

### Testes e lint

```powershell
tools\lint.ps1            # PowerShell 5.1, Python, JSON, JavaScript, Nous Code e os testes da Agenda (CalDAV), do e-mail e do celular
cd code; npm install; npm test
```

O lint roda no CI a cada push. Os testes não dependem de rede nem de modelo: o Nous Code usa um Ollama de mentira, o e-mail um servidor IMAP/SMTP falso, a Agenda um servidor CalDAV de mentira (e o Radicale, se estiver instalado) e o celular um portão com Open WebUI de mentira.

### Instalação por linha de comando

```powershell
powershell -ExecutionPolicy Bypass -File installer\install-nous.ps1 -WithModel -Model qwen3:14b
```

`-WithImages` instala também o motor de imagem e `-Force` reinstala. O instalador `.exe` sai de `installer\nous-setup.iss`, com `ISCC.exe`.

As rotas de cada serviço estão documentadas no topo do arquivo correspondente, por exemplo `monitor/nous_monitor.py`, `agenda/nous_agenda_api.py` e `code/servidor.ts`.

## Roadmap e contribuição

Os próximos passos estão no [ROADMAP](docs/ROADMAP.md). Issues e pull requests são bem-vindos: veja o [CONTRIBUTING](CONTRIBUTING.md).

## Construído sobre

**Base:**
- [Open WebUI](https://github.com/open-webui/open-webui)
- [Ollama](https://ollama.com)
- [Monaco Editor](https://github.com/microsoft/monaco-editor) (MIT)
- [xterm.js](https://github.com/xtermjs/xterm.js) (MIT)
- [node-pty](https://github.com/microsoft/node-pty) (MIT)
- [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (MIT): o agente do Nous Code adapta o contrato das ferramentas, os prompts e as políticas dele ([detalhes](code/THIRD_PARTY_NOTICES.md))
- [typescript-language-server](https://github.com/typescript-language-server/typescript-language-server) (Apache-2.0) e [Pyright](https://github.com/microsoft/pyright) (MIT), para a navegação de código

**Modelos e bibliotecas:**
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [Flux.1 Schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) (Apache-2.0)
- [U²-Net](https://github.com/xuebinqin/U-2-Net) (Apache-2.0, modelo publicado pelo [rembg](https://github.com/danielgatis/rembg))
- [RapidOCR](https://github.com/RapidAI/RapidOCR) (Apache-2.0)
- [pypdf](https://github.com/py-pdf/pypdf) (BSD-3)
- [Granite Embedding](https://huggingface.co/ibm-granite/granite-embedding-278m-multilingual) (Apache-2.0)

**Serviços:**
- [ntfy](https://ntfy.sh)
- [Open-Meteo](https://open-meteo.com)

A estimativa de velocidade da Loja foi inspirada no [llmfit](https://github.com/AlexsJones/llmfit) (MIT). As marcas pertencem aos seus projetos.

## Licença

[MIT](LICENSE)
