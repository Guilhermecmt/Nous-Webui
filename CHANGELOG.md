# Changelog

## [Não lançado]
### Mudado
- **Conversa mais limpa.** As respostas não mostram mais o nome do modelo nem o
  avatar em cima do texto, como no ChatGPT e no Claude; o modelo em uso segue no
  seletor da caixa de texto (`branding/nous-gold.css`).
- Os avisos "Nous lembrou de N detalhe(s) sobre você" e "Nous encontrou contexto
  em N conversa(s)" aparecem só na primeira mensagem da conversa e somem cerca de
  2 segundos depois, sem ficar em cima da resposta (`memory/nous_memory.py`,
  `history/nous_history.py`).

## [2.11.0] - 2026-10-25
O Nous passa para o Open WebUI 0.12.3, abre no celular, sincroniza a agenda nos
dois sentidos, se atualiza sozinho, ensina quem nunca usou IA e ganha um ícone na
bandeja.
### Novo
- **Primeiros passos para quem nunca usou IA** (`branding/modules/_progresso.js`,
  `primeiros.js`, `tour.js` e o assistente do `nous-loader.js`). As boas-vindas
  explicam em linguagem simples o que é o Nous e o que é um "modelo". Enquanto o
  primeiro modelo baixa, cinco lições curtas, no ritmo da pessoa, ensinam o que é
  um modelo, que a IA pode errar e como conferir, como pedir bem, o que fica no
  computador e como mandar foto e documento; o download não depende delas, e elas
  não somem se ele terminar no meio nem se a página recarregar. Na tela inicial,
  cartões de tarefas do dia a dia (escrever uma mensagem, entender uma conta,
  planejar a semana, tirar uma dúvida) preenchem o pedido sem enviar, e dois avisos
  explicam o pedido e depois como ler e conferir a resposta. O botão **?** reabre
  qualquer parte: lições, exemplos, como anexar, passeio pela tela e dicas dos
  painéis. O passeio da v2.8 ganhou o +, o seletor de modelo e a barra lateral, e
  agora funciona no celular. O progresso fica nas configurações da conta
  (`nousTour`), vale em qualquer aparelho, e "Pular dicas" é respeitado. Quem
  atualiza da v2.10 com conversas ou dicas já vistas não é recebido como novato.
- **Open WebUI 0.12.3** (antes 0.9.6). Quem já tem o Nous é atualizado pelo
  instalador ou pela atualização automática (`installer/atualizar-openwebui.ps1`):
  encerra o que está aberto, faz um zip da `NousData` em `bkp\`, instala a versão
  nova, sobe um servidor de teste para migrar o banco e confere contas, conversas,
  memórias e arquivos; se algo falhar, volta a versão anterior e os dados do zip.
  As telas do Nous passaram a se ancorar em ids e atributos estáveis em vez de
  textos traduzidos, e as configurações lidas e gravadas pelo Nous funcionam nos
  dois formatos de tabela do Open WebUI (`ajustes/config_db.py`). A busca na web e
  os documentos seguem no modo "legacy" de ferramentas, porque o modo nativo do
  0.10+ não funciona com modelos pequenos. O ambiente do servidor mora agora em
  `launchers/nous-env.ps1`, usado pelo lançador e pelo atualizador.
- **Loja** com catálogo novo (qwen3.5, qwen3.6, qwen3.8, gemma4 12b/26b/31b,
  gpt-oss, ministral-3) e um campo `ranking` explícito que ordena a lista e escolhe
  os recomendados, sem usar o tamanho do arquivo como medida de qualidade.
- **Usar no celular** (`celular/`, `branding/modules/celular.js`,
  `docs/CELULAR.md`). O Nous abre no celular, em casa, pelo mesmo Wi-Fi. Vem
  desligado: em Seu Nous > Celular você liga, lê um QR com um código de uso único
  (vence em 5 minutos) e o celular guarda um cookie de aparelho (`HttpOnly`,
  `SameSite=Strict`; só o hash fica no disco). Por trás há um portão próprio
  (porta 8999) que só existe enquanto está ligado: aceita só IPs da rede de casa,
  confere Host e Origin, freia tentativas de código e repassa o Open WebUI (HTTP,
  streaming, WebSocket) e os serviços do Nous pela mesma origem. O Open WebUI e os
  serviços continuam só em 127.0.0.1, e o Nous Code fica de fora. O Windows pede
  permissão uma vez para uma regra de firewall só para rede Privada, removida ao
  desligar e na desinstalação; em rede Pública o Nous não liga. É HTTP puro (um
  certificado próprio assustaria quem não é técnico), então microfone e "instalar
  como app" não funcionam no celular. Nos módulos, os endereços fixos
  `127.0.0.1:89xx` viraram `NousUrl(porta)`.
- **Agenda: sincronização de duas vias por CalDAV** (`agenda/caldav_sync.py`,
  `docs/AGENDA-CALDAV.md`). Em Agenda > Calendário, conecte uma conta CalDAV
  (iCloud, Nextcloud, Fastmail, Radicale... com senha de app), escolha os
  calendários e o Nous sincroniza de 5 em 5 minutos e logo depois de cada mudança
  feita aqui (sync-token, ctag e etag; envio com If-Match). O que o Nous não conhece
  (participantes, exceções de séries, alarmes) é preservado, e o alarme do servidor
  vira o lembrete do Nous. Se o mesmo compromisso mudar dos dois lados, vale o do
  servidor e a versão do Nous fica guardada como "(versão do Nous)", com aviso. A
  senha de app fica protegida pelo DPAPI do Windows. Dá para editar compromissos e
  escolher onde guardar os novos. O Google Agenda não aceita senha de app no CalDAV
  (só OAuth): o Nous explica e mantém o endereço iCal secreto, somente leitura.
- **Ícone na bandeja** (`launchers/bandeja.ps1`): Abrir o Nous, Iniciar/Parar,
  Nous Code, celular ligado ou não e o estado da máquina (rodando ou parado, placa
  de vídeo ou processador, memória, modelo carregado). Sobe junto com o Nous;
  abrir com o Windows é opcional e vem desligado.
- **Atualização automática** (`atualizacao/nous-atualizar.ps1`,
  `docs/DISTRIBUICAO.md`). O Nous procura versão nova no máximo 1 vez por dia (usa
  a internet; dá para desligar no menu do ícone) e avisa no painel e na bandeja.
  Nada é baixado sem o clique em "Atualizar": o pacote é conferido pelo SHA256
  publicado na release, a versão atual é guardada e, se algo falhar, o Nous volta
  sozinho. Modelos instalados com versão nova no registro do Ollama também são
  avisados e atualizados com um clique.
- **Instalador .exe** pronto para assinar: `tools/compilar-instalador.ps1` compila o
  `Nous-Setup.exe`, `tools/assinar-instalador.ps1` assina quando houver certificado
  (por enquanto o SmartScreen avisa) e `tools/empacotar-release.ps1` gera o pacote
  da release com o hash.
- **Nous Code**: depois de cada edição, o agente consulta o language server
  (TypeScript, JavaScript e Python) e recebe só os erros que a edição criou, no
  máximo 5, para corrigir no passo seguinte; o editor sublinha os mesmos erros. A
  **tarefa separada** (menu ⋯ da conversa) faz o agente trabalhar numa cópia do
  projeto (worktree do Git); no fim, "Revisar e aplicar" mostra o diff e leva as
  mudanças ao projeto sem commitar, ou recusa sem tocar em nada se o projeto mudou
  nos mesmos trechos. O `subagent` aceita `edit=true` com `files`: edita só esses
  arquivos, não roda comandos e passa pela mesma aprovação com diff. O instalador
  baixa o **Node.js 22 portátil** (zip oficial, SHA256 fixado) para `runtime\node`
  quando o computador não tem Node 22.18+, sem mexer no PATH.
- **Ollama**: quando o Nous instala o Ollama, a tela de boas-vindas dele já vem
  concluída e a nuvem do Ollama desligada; modelos de nuvem ficam escondidos do
  seletor.
### Corrigido
- **E-mail testado de ponta a ponta com um servidor IMAP/SMTP de mentira**
  (`email/testes/`, 106 testes sem rede e sem Ollama). O Nous agora confere o
  certificado do servidor (antes a senha podia ir para qualquer um no meio do
  caminho), tem limite de tempo em toda conexão e explica os erros em português.
  Nada é enviado sem confirmação explícita (`confirmado: true` em todo envio,
  agendamento e descadastro) e um rascunho não sai duas vezes. Assuntos com quebra
  de linha não injetam cabeçalhos. Modelos de nuvem do Ollama (`-cloud`,
  `remote_host`) deixaram de receber e-mail. Senhas com acento funcionam, a
  triagem lê o começo do corpo (antes só o assunto), corpos com charset
  desconhecido não ficam vazios e o resumo de uma conta não aparece em outra.
- **Motor de imagem testado de ponta a ponta** numa RX 9070 XT, com ROCm nativo no
  Windows (sem ZLUDA nem HIP SDK). O `install-comfyui.ps1` confere o espaço em
  disco e o `download-models.ps1` retoma downloads. O Pipe de imagem reconhece mais
  pedidos ("desenhe um farol"), libera a placa antes de gerar e solta a VRAM
  depois; o link quebrado do termo de responsabilidade virou um aviso curto. O
  monitor encerra o ComfyUI parado há 10 minutos (`NOUS_COMFY_IDLE_MIN`). Primeira
  imagem em ~34 s com a placa livre.
- Fusos (`TZID`) de compromissos importados no Windows sem o pacote tzdata.
- A imagem gerada aparecia como texto cru no Open WebUI 0.10+ (o `upload_image`
  passou a devolver um dicionário em vez do endereço).
- A Loja dizia "já baixado" e não baixava de novo um modelo apagado depois de
  baixado na mesma sessão do Nous.
- As notas de versão em inglês do Open WebUI não aparecem mais num banco novo, e o
  modelo escolhido na instalação segue como padrão.
### Segurança
- O servidor local só aceita pedidos do próprio Nous (CORS). Antes, sem login,
  qualquer site aberto no navegador poderia conversar com ele.
- Testes novos no `tools/lint.ps1`: CalDAV (servidor de mentira e Radicale),
  e-mail (servidor falso) e o portão do celular. A CI usa o Node 22.

## [2.10.0] - 2026-10-17
O Nous abre como um programa do computador: sem tela de login.
### Novo
- **Sem login** (`ajustes/acesso_local.py`, chamado pelo launcher antes de
  subir o servidor). O Nous só escuta em 127.0.0.1, então a senha só protegia
  contra quem já está no Windows. O Open WebUI 0.9.6 só desliga o login
  (`WEBUI_AUTH=False`) se a única conta for a fixa `admin@localhost`; por isso,
  com **uma** conta, ela é convertida nessa (mesmo id: conversas, memórias,
  documentos e configurações ficam) e o e-mail e a senha originais vão para
  `NousData/.conta_original.json`. Com **duas ou mais** contas (família no
  mesmo PC) ou com o arquivo `NousData/.exigir_login`, o login continua e a
  conta convertida volta ao que era. Na dúvida (erro), login ligado. Conta
  nova criada sem login ganha o nome do Windows no lugar de "User".
- **Tela inicial** (`branding/modules/inicio.js`): saudação pela hora e pelo
  nome, frase de privacidade, uma dica do Nous a cada visita e o botão
  **Conversa privada** (o chat temporário do Open WebUI). Sem login, o "Sair"
  do menu da conta e o aviso "Você agora está logado" somem.
- **Painel "Seu Nous"** (`branding/modules/painel.js`): um painel fixo à
  direita reúne o que antes flutuava pela tela. A coruja fica dentro de um anel
  que mostra o uso da placa de vídeo (dourado quando há modelo carregado, com
  "Liberar a placa de vídeo"), e o painel traz a conversa privada, os próximos
  lembretes da Agenda, as memórias mais recentes e as 12 ferramentas com nome.
  Em tela larga o chat abre espaço; em tela menor vira gaveta; fechado, sobra
  só a coruja no canto, e o Nous lembra a escolha. Saem o card "Recursos", o
  botão flutuante da memória, o do tema, o NOUS do topo e o ícone do chat
  temporário.
- **Nous Code** (`code/`): um IDE com agente de IA local, numa janela própria
  (atalho "Nous Code" no Menu Iniciar, ou Código no painel do Nous). Editor
  Monaco (o do VS Code) em português, árvore de arquivos com abas, Ctrl+P,
  busca no projeto (Ctrl+Shift+F), Git (diff lado a lado, commit, descartar),
  terminal PowerShell de verdade (ConPTY, Ctrl+`) e o agente ao lado (Ctrl+L
  pergunta sobre a seleção). O agente lista, lê, procura, edita e roda
  comandos, um passo por vez; editar e rodar esperam o seu OK com o diff na
  frente, "Desfazer" volta os arquivos, e o editor mostra as mudanças dele
  na hora (o serviço avisa por WebSocket quando um arquivo muda no disco).
  Serviço em Node 22.18+ (TypeScript rodando direto, sem build) na porta
  8998, aceitando só o Nous e a própria janela como origem; o instalador
  baixa o Monaco, o xterm e o node-pty quando há Node. Feito para modelos
  pequenos: lê chamadas escritas como JSON no texto (o qwen2.5-coder:14b
  nunca usa o canal nativo), aceita edição com números de linha ou recuo
  diferente, empurra quando o modelo anuncia e para, e encerra quando ele
  anda em círculo. Com o qwen2.5-coder:14b, achou e corrigiu dois bugs com os
  testes em cerca de 30 s.
- **Nous Code no nível do DeepSeek Harness** (comparado função por função com o
  `dsh`, ficando de fora só o que é plataforma ou não serve para modelo pequeno):
  modo plano com `exit_plan_mode` e revisão do plano; permissões em quatro
  níveis aplicadas no servidor (`POLICY_DENIED`); ler antes de editar e recusar
  arquivo que mudou desde a leitura; comandos que passam do tempo viram jobs em
  segundo plano (`job_output`, `job_list`, `job_kill`); `web_search` e `web_fetch`
  com permissão por conversa; `glob`; `todo_write`; `ask_user`; objetivo
  persistente; ajudante só leitura (`task`); skills `SKILL.md` e `/nome-da-skill`;
  instruções em cadeia (global, raiz e subpastas); compactação em duas etapas com
  medidor de tokens e `/compactar`; raciocínio configurável; aviso de repetição
  na 3ª e 5ª vez, parada na 8ª; comandos `/` e `@arquivo` com autocompletar;
  renomear, duplicar a partir de um pedido, exportar e buscar conversas; inspetor
  do contexto; títulos automáticos. Testado com o qwen2.5-coder:14b: o modo plano
  propôs, foi aprovado e implementou; a busca na web pediu permissão e citou a
  fonte. 25 testes do núcleo e das políticas, com um Ollama de mentira.
- **Nous Code com o harness do DeepSeek Harness** (MIT, creditado em
  `code/THIRD_PARTY_NOTICES.md`): o agente agora fala o mesmo contrato de
  ferramentas (`read`, `write`, `edit`, `glob`, `grep`, `pwsh`, jobs, web,
  `ask_user_question`, objetivo, `skill`, `subagent`, `lsp`, `present`,
  `schedule_*`) com os mesmos textos, formatos e mensagens de erro; os nomes
  antigos continuam aceitos. Novidades que vieram junto: **navegação de código
  por LSP** (TypeScript/JavaScript e Python, servidores instalados junto);
  **servidores MCP** no formato do `.mcp.json` do Claude Code, com permissão
  para os de projeto; **lembretes** (`schedule_create`: depois de N segundos,
  data, intervalo, diário, semanal ou cron, com fuso) que rodam a conversa
  sozinhos; **objetivo com rodadas automáticas** e mensagem de fechamento;
  **LM Studio, llama.cpp e vLLM** pela API compatível com a OpenAI; contexto de
  execução e hora como mensagem (o prompt de sistema fica fixo e o cache do
  Ollama é reaproveitado); compactação com checkpoint de 8 seções; jobs que
  avisam ao terminar e `job_output` que lê só o novo; saída grande guardada em
  arquivo legível pelo agente; instruções em cadeia (`AGENTS.md`, `CLAUDE.md`,
  `*.local.md`); catálogo de skills e `/skill`; várias chamadas por passo.
  Tela: perguntas com várias opções, cartões de MCP e de arquivos entregues,
  lembretes no painel, objetivo com Pausar e Retomar, `/mcp` e `/lembretes`.
  42 testes do núcleo e das políticas e 16 verificações da tela.
- **Terminal do Nous Code em UTF-8:** a saída do Node e do npm (✔, ℹ, acentos)
  chegava embaralhada no PowerShell do terminal.
- **README:** reescrito nas duas línguas, com prints novos da 2.10 feitos numa
  instância de demonstração.
- **Casca:** marca maior na barra lateral, estrela ao lado do modelo no lugar
  de "Definir como padrão" e primeiro nome no lugar do nome inteiro cortado.
### Corrigido
- **Memória:** o filtro não aprende nada de conversa temporária (id
  `local:...`); antes ela sumia do histórico mas ainda podia virar memória.

## [2.9.0] - 2026-10-17
As funções de IA local que os usuários mais elogiam e que ainda faltavam,
em código próprio, testadas com um modelo pequeno (qwen3:4b) numa instância
isolada. O Nous continua MIT.
### Novo
- **📝 Documentos** (`documentos/escrita.py`, painel `escrita.js`): escrever
  ao lado do chat com pedidos prontos (corrigir, mais formal, mais simples,
  mais curto, tópicos em texto, organizar com títulos, continuar) ou do seu
  jeito. A IA reescreve e o Nous compara palavra por palavra (parágrafo
  inteiro quando ela reescreve muito): cada mudança é uma sugestão para
  aceitar ou recusar. Seleção = só o trecho muda. Salva sozinho, guarda até
  25 versões, abre `.docx`/`.pdf`/`.txt`/`.md` e exporta para Word, PDF e
  Markdown (`documentos/exportar.py`, sem dependência nova). *"Abre meus
  documentos"* funciona no chat.
- **Botões nas respostas** (`respostas.js`): ✂ Mais curto, 🙂 Mais simples e
  📝 Documento (abre a resposta, com o Markdown original, nos Documentos).
- **Memória: importar e exportar.** O modelo propõe fatos a partir de um
  arquivo ou texto colado (currículo, "sobre mim", memórias do ChatGPT, até em
  inglês) e você escolhe; o que já sabia vem marcado. O backup exportado volta
  sem passar pelo modelo, com as fixadas.
- **Loja: qualquer modelo.** Nome do Ollama, link do ollama.com ou repositório
  GGUF do Hugging Face: o tamanho vem do manifesto do registro (nada é
  baixado), com selo de "cabe na máquina", velocidade estimada, se entende
  imagens e espaço em disco. Fora do catálogo, o monitor só baixa o que foi
  conferido na última hora e cabe no disco.
- **Loja: "E se eu tivesse outra máquina?"** simula outra placa/RAM e mostra
  o que rodaria e a que velocidade (sem botão de baixar na simulação).
- **Pesquisa Profunda:** relatórios baixam em PDF e Word (`/research/export`);
  os novos guardam também o Markdown, os antigos saem do HTML. Na biblioteca,
  ✎ Editar abre o relatório nos Documentos e 📋 copia o texto com as fontes.
- **Usabilidade dos painéis** (revisão com fotos no Chrome, desktop e celular):
  - Documentos: revisão guiada ("sugestão 2 de 7", ‹ ›, Enter aceita, Delete
    recusa, avança e conclui sozinha), **Desfazer** depois de aplicar, aviso
    "A IA está escrevendo" com Cancelar, aviso de trecho selecionado, modelos
    prontos (carta, currículo, e-mail, reclamação, ata) e "✨ Escrever com a IA"
    no documento vazio, negrito/itálico/título/listas, palavras e tempo de
    leitura, estado do salvamento, Ctrl+S guarda versão, busca na lista e
    lista em gaveta no celular.
  - Loja: filtros (cabem aqui, leves, conversa, raciocínio, programação,
    entendem imagens), "ocupa ~X GB dos Y GB da placa", "Procurar outro modelo"
    recolhido, confirmação antes de baixar modelo pesado e aviso quando o
    download termina.
  - Memória: busca a partir de 8 memórias, apagar com **Desfazer**, importar
    com "marcar todas/nenhuma" e avisos de quantas foram guardadas/exportadas.
  - Avisos (toasts) e confirmações no visual do Nous (`modules/_base.js`) no
    lugar do `alert`/`confirm` do navegador — também nos painéis antigos
    (Agenda, E-mail, Habilidades, Comparar, Formulários, Galeria) — e os
    títulos de todos os painéis em Cinzel.
  - Documentos: a resposta da IA aparece **ao vivo** ("pensando" e depois o
    texto chegando; Cancelar agora para o modelo de verdade); **❓ Por quê?**
    explica cada sugestão (acento, maiúscula, pontuação e ortografia por
    regra, sem errar; o resto pelo modelo, marcado "pode errar"); **comparar
    versões** antes de voltar (riscado sai, sublinhado volta).
  - Relatórios: **💬 Conversar** leva o relatório para o chat.
  - Loja: download **travado** (sem bytes novos por 90 s) ou com a conexão
    caída tenta de novo sozinho, até 3 vezes, com o aviso no card.
### Corrigido
- Modelos que sempre pensam (qwen3 2507 "thinking": o molde abre o `<think>`)
  despejavam o raciocínio na resposta dos Documentos; agora o Nous detecta
  pelo molde e pede `think` ao Ollama, que separa o raciocínio.
- No celular, os botões das respostas alargavam a página inteira (todo painel
  aparecia cortado à direita); agora viram só ícones em telas estreitas.
### Mudado
- Modelos `hf.co/...` (GGUF baixado pelo Ollama) recebem a memória pessoal
  como os outros locais; só ids de nuvem com `/` continuam sem.
- No monitor, "modelo local" = tudo o que o Ollama lista menos os `:cloud`
  (antes, qualquer nome com `/` era tratado como nuvem).
- API de memória aceita pedidos de até 21 MB (importar arquivo).

## [2.8.0] - 2026-10-17
Seis ondas de funções novas, e cada função testada de
verdade com um modelo pequeno (qwen3:4b) numa instância isolada. Código
próprio, o Nous continua MIT.
### Novo
- **Memória:** memórias fixadas (identidade e saúde fixam sozinhas), escolha
  pelas que têm a ver com a pergunta quando passam de 30 e **🧹 Organizar
  memórias**, que junta repetidas par a par com a sua aprovação.
- **Agenda:** listas de verificação nas notas, "💬 usar no chat", avisos no
  celular (ntfy) e no e-mail, **↩ Desfazer** no chat, tarefas encadeadas e
  tarefas que esperam o computador ficar livre.
- **Conversas longas** (filtro Nous Compactar): o começo vira um resumo
  incremental e a conversa continua lembrando dos detalhes.
- **Pesquisa Profunda:** modo para modelos pequenos, resposta curta para
  perguntas simples, continuação sobre o último relatório, sugestões em
  botões para perguntas vagas e relatório parcial quando algo falha.
- **E-mail:** várias contas, anexos lidos, convites para a Agenda,
  newsletters com descadastro, rascunhos agendados, contatos aprendidos
  (vCard) e **e-mail pelo chat** (vira rascunho; nunca envia sozinho).
- **Ler imagens e boletos** (filtro Nous Leitura): OCR local (RapidOCR) para
  fotos e prints, também com modelos sem visão; boletos conferidos pelo
  dígito verificador (banco, valor, vencimento).
- **Formulários PDF** (`documentos/`): campos, sugestões pelas memórias e
  assinatura salva.
- **Modo agente leve:** botões nas respostas (`⟦opcao⟧`, `⟦abrir⟧`,
  `⟦tema⟧`, `⟦acao⟧`), comandos pelo chat ("abre minha agenda", "tema
  escuro", "libera a placa de vídeo") e a **guarda**, que confere se o que o
  modelo diz ter feito foi mesmo feito.
- **Primeiros passos:** 🩺 Diagnóstico, dicas na primeira vez de cada painel,
  CPF/cartão/senhas borrados na tela e "✍ Ensinar meu jeito de escrever".
- **Galeria** (vinda do wip-galeria): grade, lightbox com zoom, lixeira,
  ComfyUI ligado sob demanda; agora com favoritas, álbuns e ✎ para o Editor.
- **Editor:** "Diga o que fazer" — frases em português viram as ações.
- **Comparar modelos** no painel: 2 a 4 modelos, tempo e tokens/s, voto às
  cegas e placar acumulado.
### Mudado
- **Embeddings:** granite-embedding:278m (multilíngue) no lugar do
  nomic-embed-text, também no RAG do Open WebUI (só onde ainda não há
  arquivos); índices refeitos sozinhos ao trocar o modelo.
- **Contexto de 16k** em todas as chamadas diretas ao Ollama e no
  `OLLAMA_CONTEXT_LENGTH`: o Ollama 0.30 abria 262k (44 GB) e cada resposta
  levava 140–210 s; agora 5–25 s.
- **Português por padrão:** idioma da interface, legendas do YouTube e um
  prompt de sistema em PT-BR para modelos sem prompt próprio.
- Calendário e Automações nativos do Open WebUI escondidos (filtro de
  ajustes em `ajustes/`); a Agenda e as Tarefas do Nous fazem isso.
- Agenda pelo chat lê datas e horas por regra (não pelo modelo) e recusa
  horário no passado.
- Citações de Arquivos e Histórico não vão mais no fim da resposta
  (decisão do wip-galeria).
- SearXNG escuta só em 127.0.0.1.
### Corrigido
- qwen3 "pensando em voz alta" quebrava respostas estruturadas (agora com
  JSON schema e `think` desligado).
- Habilidades aprendidas ficavam específicas demais ("do João").

## [2.7.0] - 2026-10-16
Agenda, tarefas, habilidades e utilidades novas, em código próprio (o Nous
continua MIT).
### Novo
- **Agenda** (`agenda/`, porta 8996): notas, lembretes com repetição,
  calendário com compromissos e aviso antes, importar/exportar `.ics` e
  assinatura do Google Agenda/Outlook/iCloud pelo endereço iCal (só leitura).
  Lembretes chegam como notificação do Windows mesmo com o navegador fechado.
- **Agenda pelo chat** (filtro Nous Agenda): "me lembre de...", "marca
  dentista dia 20", "o que tenho amanhã?". Regenerar a resposta não duplica.
- **Tarefas agendadas**: pergunta ao modelo, pesquisa na web, resumo dos
  e-mails e "bom dia" (agenda + e-mails), no horário, com o resultado em nota,
  aviso e e-mail opcional.
- **Habilidades** (`skills/`, porta 8997): "aprenda isso" no chat guarda o
  passo a passo em Markdown; pedidos parecidos depois usam a habilidade.
  Painel para revisar, editar e importar SKILL.md do GitHub.
- **Relatório visual da Pesquisa Profunda** com biblioteca em Recursos ›
  Relatórios (HTML escapado + CSP sem scripts).
- **Editor de fotos**: cortar, girar, luz/cor, filtros, redimensionar,
  desfazer, baixar/copiar e **remover fundo** (U²-Net local, 4,5 MB).
- **YouTube** (resume vídeos pela legenda) e **Clima** (Open-Meteo) no chat.
- **Loja de Modelos** mostra a velocidade estimada de cada modelo na sua placa.
### Corrigido
- **Pesquisa Profunda não achava o pacote `nous_search`** dentro do Open WebUI
  (o pipe roda de um arquivo temporário); o registro grava a pasta real.
### Mudado
- `apply_branding.py` concatena `branding/modules/*.js` no `loader.js`
  (painéis novos em arquivos próprios; `window.NousUI` expõe utilitários).

## [2.6.0] - 2026-10-05
Rodada de correções para quem instala e usa o Nous pela primeira vez.
### Corrigido
- **Instalador e verificação de saúde travavam** quando o Ollama estava
  parado: `ollama list` abria o app do Ollama, que herdava a saída do script,
  e o PowerShell esperava para sempre. Agora a checagem de modelos é pela API.
- **Falhas apareciam como sucesso**: o instalador não conferia o resultado do
  pip, do venv nem da instalação do Python, e o `instalar.bat` terminava em
  "Pronto!" mesmo assim. Agora para com a mensagem em vermelho e código 1.
- **PCs de 8 GB eram recusados** ("INCAPAZ"): o Windows reporta ~7,6 GB.
  Mesma folga de 0,6 GB da Loja de Modelos.
- **"O que há de novo" do Open WebUI, em inglês, era a 1ª tela após criar a
  conta**, e o aviso "nova versão disponível" levava ao GitHub. Os dois somem.
- **Link "Criar conta" morto** na tela de login (o Open WebUI ignora
  `?mode=signup`): virou a explicação do caminho real (Painel Admin › Usuários).
- **Assistente de primeiro uso** podia ficar em "Baixando… 0%" para sempre se o
  pedido falhasse; agora mostra o erro e "Tentar de novo". Ao terminar, abre o
  chat já com o modelo novo (antes podia cair no de embeddings).
- **Card Recursos e botão de memória** apareciam na tela de login; no celular,
  o wordmark encavalava no seletor de modelo e o card cobria as sugestões.
- **Badge de VRAM** marcava em vermelho justamente o modelo já carregado
  (comparava com a VRAM livre, não com a total).
- `gemma4:e4b` aparecia com 9,6 GB (são ~6,6), o que distorcia a recomendação.
- `stop-nous.ps1` só fechava a porta 8080; agora encerra todos os serviços.
- Segundo clique no atalho durante a partida subia **outro servidor** contra o
  mesmo banco; agora só reabre a tela de carregamento.
- Se o servidor não sobe em 5 min, aparece um aviso em vez de silêncio.
### Mudado
- **O app passa a morar em `%LOCALAPPDATA%\Programs\Nous`**: o instalador copia
  tudo para lá, e limpar a pasta Downloads não quebra mais o atalho.
- **Nous aparece em Configurações › Aplicativos** (desinstalar como qualquer
  programa) e ganha o atalho **"Parar Nous"** no Menu Iniciar.
- **Servidor só em `127.0.0.1`** (antes `0.0.0.0`, visível na rede local).
- **Monitor (8990)**: recusa DNS rebinding (header Host), aceita `/pull` só de
  modelos do catálogo e ganha `/installed` — o painel não chama mais o Ollama
  direto do navegador.
- Reinstalar preserva no manifesto o que o Nous instalou antes (o "Remover
  tudo" voltou a funcionar após reinstalação) e só grava o modelo se ele foi
  escolhido de fato.
- `nous-setup.iss` atualizado: copia o projeto inteiro, atalhos via `.vbs`,
  desinstalação segura pelo próprio Inno.
### Adicionado
- `tools/lint.ps1` + workflow `lint` (GitHub Actions, Windows): scripts do
  Windows em ASCII ou UTF-8 com BOM, sintaxe no PowerShell 5.1, Python, JSON e
  JavaScript válidos.

## [2.5.0] - 2026-06-13
### Adicionado
- **Assistente de Email (Nous Email)** — triagem, resumo e rascunho de resposta
  com IA local, 100% privado. O conteúdo dos emails nunca sai da máquina.
  - `email/nous_email.py`: cliente IMAP/SMTP (stdlib pura). Detecção automática
    de servidores para Gmail, Outlook e Yahoo. `list_recent`, `get_message`,
    `send_message`. Nunca envia sem chamada explícita.
  - `email/nous_email_api.py`: micro-serviço REST local (porta 8995). CORS
    restrito a localhost (mesmo padrão da Memory API — sem CSRF local). Rotas:
    `/status`, `/connect`, `/disconnect`, `/inbox` (triagem LLM local),
    `/message` (resumo LLM local), `/draft` (rascunho LLM local), `/send`
    (somente após confirmação). Cache de triagem em memória (1h TTL).
    Forçado a usar modelo local — recusa ids com `/` (nuvem).
  - `email/conectar-email.ps1`: diálogo gráfico sem terminal. Instrução passo-a-
    passo para senha de app (Gmail/Outlook). Detecção automática de IMAP/SMTP
    pelo domínio. Valida login antes de salvar.
  - `email/desconectar-email.ps1`: remove `.email_account.json` com confirmação.
  - `conectar-email.bat` / `desconectar-email.bat` na raiz: clique duplo.
  - Painel **✉ Assistente de Email** no card Recursos (`nous-loader.js`):
    tela de conexão (email + senha de app), caixa de entrada com categoria e
    resumo de 1 linha por email, visualização com resumo completo, rascunho
    editável e botão Enviar com `confirm()` obrigatório.
  - Credenciais em `NousData/.email_account.json` (fora do git, permissões
    restritas ao dono; nunca logadas; removíveis com `desconectar-email.bat`).
### Mudado
- `launchers/start-nous.ps1`: `Start-EmailAPI` sobe a 8995 nos dois pontos de
  boot, apenas se `.email_account.json` existir.
- `tools/health-check.ps1`: item informativo "Email: conectado / não configurado".
  Corrigido lint PSPossibleIncorrectComparisonWithNull na linha 39.

## [2.4.0] - 2026-06-13
### Adicionado
- **Pesquisa Profunda (Nous)** — selecione no dropdown de modelos e faça uma
  pergunta; o Nous pesquisa a web em múltiplas etapas e entrega um relatório em
  markdown com citações `[n]` e lista de fontes. 100% local (SearXNG + Ollama),
  sem API paga. Status em tempo real durante a pesquisa.
  - `search/nous_search/deep_research.py`: laço Python puro — planejar
    sub-perguntas com o LLM, buscar com `search_web()`, refinar se necessário,
    baixar páginas com `fetch_page()`, sintetizar com Ollama.
  - `search/nous_research_pipe.py`: Pipe do Open WebUI que expõe o `deep_research`
    no dropdown. Auto-desativado se o SearXNG estiver fora do ar.
  - `search/register_research_pipe.py`: registro idempotente no `webui.db` a cada
    boot; ativo = SearXNG respondendo (auto-cura quando o container subir).
- **Comparar Modelos (Nous)** — teste cego A/B entre dois modelos locais.
  Selecione "Comparar Modelos (Nous)" no dropdown, faça uma pergunta e veja as
  duas respostas anônimas lado a lado; vote no melhor antes de revelar os nomes.
  Reusa o Arena nativo do Open WebUI.
  - `evaluation/register_arena.py`: liga o Arena no `webui.db` apontando para os
    dois primeiros modelos de chat instalados. Só ativa com ≥ 2 modelos; auto-cura
    quando o 2º modelo for baixado.
### Mudado
- `launchers/start-nous.ps1`: funções `Register-Research` e `Register-Arena`
  adicionadas aos dois pontos de boot. `ENABLE_EVALUATION_ARENA_MODELS` removido
  do env (gerenciado agora pelo `register_arena.py` diretamente no banco).

## [2.3.0] - 2026-06-13
### Adicionado
- **Conversa por voz 100% local em PT-BR** — fale com o Nous e ouça a resposta
  em português, sem internet, rodando até em CPU. O maior diferencial inédito
  identificado na análise competitiva: os
  concorrentes não entregam voz conversacional em PT-BR para leigos.
  - `voice/nous_tts_server.py`: servidor TTS local (porta 8994) compatível com
    a API OpenAI `/v1/audio/speech`, chamando o **Piper TTS** por baixo com voz
    `pt_BR-faber-medium`. Permite ao Open WebUI usar TTS local sem nenhuma
    mudança de frontend — engine configurada como "openai" com base_url local.
  - `voice/register_voice.py`: configura STT (Whisper local, idioma `pt`,
    modelo `medium` em GPU ou `small` em CPU) e TTS (Piper via servidor 8994)
    no `webui.db` a cada boot, idempotente. Só age se os assets existirem.
    Remove a config ao desinstalar.
  - `voice/install-voice.ps1`: baixa o binário do Piper para Windows e a voz
    `pt_BR-faber-medium` (~60 MB) para `NousData\voice\`, sem login, com
    espelhos abertos. Idempotente; `-Force` rebaixa.
  - `ativar-voz.bat` na raiz: clique duplo ativa tudo (baixa + registra).
  - Botão **"🎙 Ativar voz em PT-BR"** no card Recursos (abaixo de "Baixar
    modelos"), com painel de instalação com barra de progresso. Após ativar,
    muda para "🎙 Voz ativada" em verde.
  - Novas rotas no monitor (8990): `GET /voice/status` e `POST /voice/install`.
### Mudado
- `launchers/start-nous.ps1`: `WHISPER_LANGUAGE=pt` definido a cada boot;
  funções `Start-VoiceServer` e `Register-Voice` chamadas nos dois pontos de
  boot (junto de `Register-Memory`, `Register-Cloud`, etc.).
- `tools/health-check.ps1`: novo item informativo "Voz: ativa / inativa" com
  checagem do servidor TTS na porta 8994; nunca falha o health-check.


Todas as mudancas notaveis do Nous. Formato baseado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
[Versionamento Semantico](https://semver.org/lang/pt-BR/).

## [2.2.0] - 2026-06-10
### Adicionado
- **Loja de Modelos dentro do app** — o usuario escolhe e baixa o modelo de IA
  sem sair do site, sem terminal e sem ingles:
  - `monitor/catalog.json`: catalogo curado (~17 modelos do Ollama) com nome
    amigavel, descricao em PT-BR, tamanho de download e requisitos reais.
  - `monitor/nous_monitor.py`: novas rotas `GET /hardware` (GPU/VRAM/RAM +
    tier da maquina), `GET /catalog` (catalogo ordenado: **recomendados para
    esta maquina primeiro**, com `installed`/`fit`/progresso), `POST /pull`
    (download via Ollama em background, singleton por modelo) e
    `GET /pull/status` (progresso real agregado por digest).
  - `branding/nous-loader.js`: painel **"Baixar modelos"** no card Recursos —
    cards com selos "Recomendado para sua maquina" / "Roda na sua maquina" /
    "Pesado para sua maquina" / "Entende imagens", download em 1 clique com
    barra de progresso (pode fechar e reabrir: o estado vive no monitor).
- **Assistente de primeiro uso** — se nao ha nenhum modelo de chat instalado,
  o Nous abre uma tela de boas-vindas com o modelo recomendado para a maquina
  e um unico botao "Baixar e comecar". Some sozinho apos o primeiro download.
- **Atalho garantido**: o instalador agora cria o atalho tambem no **Menu
  Iniciar** (imune ao "Acesso controlado a pastas" do Defender), cria o da
  area de trabalho logo no inicio da instalacao (sobrevive a falhas no meio),
  verifica o resultado e tem fallback para a area de trabalho publica em
  instalacoes elevadas. `health-check.ps1` passa a conferir o atalho.
- **Identidade com auto-cura**: `apply_branding.py` grava um marcador
  (versao do open-webui + hash dos arquivos Nous) em
  `NousData\.branding_marker.json`; o novo modo `--if-needed` reaplica a
  identidade so quando algo mudou. `start-nous.ps1` chama `Ensure-Branding`
  a cada boot — logo/tema perdidos em upgrade se corrigem sozinhos.
### Mudado
- `instalar.bat` **nao pergunta mais o modelo no terminal** — era o maior
  ponto de friccao para leigos. O nucleo instala sem modelo e o assistente
  de primeiro uso cuida do resto; no final, o instalador abre o Nous sozinho.
- `installer/install-nous.ps1`: versao do Open WebUI **pinada**
  (`open-webui==0.9.6`, testada com o Nous) para novas instalacoes nao
  quebrarem com mudancas upstream; garante o Pillow antes do branding e
  avisa (sem abortar) se a identidade falhar.
- `tools/health-check.ps1`: confere tambem `favicon.png`, o marcador de
  auto-cura e o atalho (area de trabalho ou Menu Iniciar).

## [2.1.0] - 2026-06-10
### Adicionado
- **Nous Nuvem (NVIDIA NIM)** — acesso *opt-in* a ~80 modelos de fronteira
  gratuitos (DeepSeek R1, Llama 3.3 70B, Qwen3 Coder, MiniMax M1, Kimi K2...)
  via API hospedada da NVIDIA (`integrate.api.nvidia.com/v1`), 100% compativel
  com OpenAI. Sem GPU, sem cartao de credito, sem assinatura.
  - `cloud/register_nvidia.py`: registra/remove a conexao NVIDIA direto no
    `webui.db` a cada boot. Idempotente, sem credenciais de admin.
    Curadoria de 5 modelos para nao poluir o dropdown.
  - `cloud/ativar-nuvem.ps1` + `cloud/desativar-nuvem.ps1`: ativacao/desativacao
    por dialog grafico (sem terminal). Valida a chave online antes de salvar.
  - `ativar-nuvem.bat` + `desativar-nuvem.bat` na raiz: clique duplo e pronto.
  - Chave armazenada em `NousData\.nvidia_api_key` (fora do git, mesmo padrao
    da `.webui_secret_key`).
### Mudado
- **Memoria protegida em nuvem** (`memory/nous_memory.py` v0.2.0): o inlet
  **nao injeta fatos pessoais** em modelos de nuvem (ids com `/`, ex.:
  `deepseek-ai/deepseek-r1`). Nova valve `CLOUD_MODELS_GET_MEMORY` (padrao
  `False`) para quem quiser ligar explicitamente.
- `tools/health-check.ps1`: novo item informativo "Nuvem NVIDIA: ativa /
  inativa" — nunca falha o health-check por causa da nuvem.
- `launchers/start-nous.ps1`: chama `Register-Cloud` a cada boot junto com
  `Register-Memory`, `Register-Pipe`, `Setup-Files`, `Setup-History` e
  `Start-MemoryAPI`.

## [2.0.0] - 2026-06-08
### Adicionado
- **Link "Criar conta" na tela de login** (`branding/nous-loader.js`): apos o
  primeiro usuario criar sua conta, o Open WebUI escondia o formulario de cadastro
  permanentemente. Agora o JS injeta um link discreto "Primeiro acesso? Criar conta"
  abaixo do form de login, que leva para `/auth?mode=signup`. Zero config.
- **Capability gate — badge de VRAM nos modelos** (`branding/nous-loader.js`): cada
  modelo no dropdown do chat recebe um ponto colorido indicando se cabe na VRAM:
  verde (< 85% da VRAM livre), amarelo (85-100%), vermelho (nao cabe). Dados em
  tempo real do monitor local (porta 8990) + tamanhos do Ollama (`/api/tags`).
  Atualiza a cada 10 s sem impacto de performance.
- **Citacoes de fonte inline nas respostas RAG** (`files/nous_files.py`,
  `history/nous_history.py`): quando o Nous usa arquivos ou historico de conversas
  para responder, agora inclui ao final da resposta uma linha em markdown
  `> Fontes consultadas: arquivo.md` / `> Contexto de conversas anteriores: data`.
  Complementa o status transitorio (que some) com uma referencia permanente na
  mensagem.
### Nota
- Split-chat (comparar dois modelos lado a lado) foi avaliado e adiado: requer
  engenharia no frontend Svelte do Open WebUI; risco de regressao alto para o
  ganho. Ficara' no roadmap para uma versao futura.

## [1.9.0] - 2026-06-08
### Adicionado
- **Modelos de nuvem opcionais** (GPT-4, Claude, Gemini): `start-nous.ps1` agora
  liga explicitamente `ENABLE_OPENAI_API=True`. O usuario pode adicionar uma chave
  em Admin > Settings > Connections (OpenRouter recomendado para Claude/Gemini).
  Sem chave, nada sai da maquina — o Nous segue 100% local por padrao. README (EN/PT)
  documenta o passo a passo e deixa claro: memoria, arquivos e historico SEMPRE usam
  o Ollama local, mesmo com chat via nuvem.
### Corrigido
- **[CRITICO] Historico indexava texto corrompido** (`history/index_history.py`): a
  coluna `content` do `webui.db` vem JSON-encoded (string entre aspas, com escapes
  `\uXXXX`). O parser so' decodificava quando comecava com `[`/`{`, entao indexava o
  literal com aspas e acentos quebrados, e as respostas do assistente entravam
  poluidas com blocos `<details type="reasoning">`. Agora decodifica strings JSON
  e remove blocos de raciocinio/HTML. Indices antigos sao reconstruidos no proximo
  boot (controle por `PARSER_VERSION` na tabela `meta`).
- **Cache do retrieval nao atualizava em modo WAL** (`history/nous_history.py`,
  `files/nous_files.py`): a invalidacao por `mtime` do arquivo principal nunca
  disparava (em WAL a escrita vai para o `-wal`), servindo um indice velho ate o
  proximo checkpoint. Agora a assinatura inclui mtime+tamanho do `-wal`.
- **API de memoria sem protecao de origem** (`memory/nous_memory_api.py`): CORS `*`
  permitia que qualquer site aberto no navegador chamasse a porta 8993 (CSRF local) e,
  p.ex., apontasse a pasta indexada para a home do usuario, exfiltrando arquivos via
  contexto. Agora so' aceita origem local (localhost/127.0.0.1) e reflete essa origem
  em vez de `*`. Escritas de JSON viraram atomicas (tmp + replace) e bodies malformados
  retornam 400 em vez de 500.
- **`exclude_chat` do historico nunca funcionava** (`history/nous_history.py`): o
  `chat_id` chega por `__metadata__`, nao na raiz de `body`. Sem ele, o filtro podia
  reinjetar a propria conversa atual (contexto circular). Assinatura do `inlet`
  corrigida.
- **Re-scan eterno do historico** (`history/index_history.py`): a marca d'agua so'
  avancava quando algo era indexado; conversas so' com mensagens curtas eram
  revarridas a cada ciclo. Agora avanca por toda mensagem vista.
- **Troca de modelo de embedding quebrava a busca** (`history/index_history.py`):
  dimensoes diferentes viravam vetores mortos para sempre (sem re-embed). Agora o
  indice e' reconstruido automaticamente quando `NOUS_EMBED_MODEL` muda.

## [1.8.0] - 2026-06-08
### Adicionado
- **Painel "O que o Nous sabe" — Fase 3** (`memory/nous_memory_api.py`): micro-servico
  REST local (porta 8993, CORS aberto para localhost) que expoe as memorias para o
  novo painel flutuante da UI. Endpoints: listar, adicionar, editar e deletar memorias;
  criar/trocar/deletar personas; sincronizar pasta de arquivos ao trocar persona.
- **Personas — Fase 5** (`memory/`): suporte a multiplos modos de uso com contexto
  de memoria independente. Cada persona tem seu proprio conjunto de memorias e,
  opcionalmente, uma pasta de arquivos diferente.
  - Migracao automatica da tabela `memories`: adiciona coluna `persona TEXT DEFAULT
    'default'` (compativel com dados existentes).
  - `nous_memory.py` atualizado: le a persona ativa de `nous_active_persona.json`
    (escrito pela API) no `inlet` e `outlet`; filtra memorias por persona; salva
    novas memorias com a tag da persona ativa.
  - `branding/nous-loader.js` atualizado: botao flutuante (icone cerebro, canto
    inferior direito) abre painel "O que o Nous sabe" com seletor de persona,
    lista de memorias editaveis/deletaveis, formulario para criar novas personas
    (com pasta de arquivos opcional) e campo para adicionar memorias manualmente.
- `launchers/start-nous.ps1`: adiciona `Start-MemoryAPI` nos dois pontos de boot.

## [1.7.0] - 2026-06-08
### Adicionado
- **Historico de conversas — Fase 4** (`history/`): o Nous agora recupera contexto
  de dialogos anteriores do usuario e o injeta automaticamente em cada resposta.
  - `history/index_history.py` — indexador incremental em modo watch (60 s): le
    `webui.db` do Open WebUI em modo somente-leitura, agrupa mensagens em pares
    dialogo (pergunta + resposta seguinte), gera embeddings via Ollama
    (`nomic-embed-text`, prefixo `search_document:`), tabela FTS5 de duas colunas
    (`user_msg`, `asst_msg`). Deduplicacao por `msg_id`. Singleton por porta (8992).
    Marca d'agua de tempo com 1 h de sobreposicao para capturar respostas tardias.
  - `history/nous_history.py` — Filter global do Open WebUI com busca **hibrida**
    (semantica + FTS5/BM25, RRF). Filtra pelo `user_id` (cada usuario ve so' o
    proprio historico). Exclui a conversa atual (evita auto-referencia circular).
    Limiar `MIN_SIM=0.60`. Status: *"Nous encontrou contexto em N conversa(s)
    anterior(es)."* Complementa Memoria Pessoal (fatos) e Arquivos (notas).
  - `history/register_history.py` — auto-registra o filter em `webui.db` (sem
    login, idempotente). Chamado pelo launcher a cada boot.
- `launchers/start-nous.ps1`: adicionadas funcoes `Start-HistoryIndexer`,
  `Register-History` e `Setup-History`; chamadas nos dois pontos de boot.

## [1.6.0] - 2026-06-07
### Adicionado
- **Acesso aos seus arquivos locais — Fase 2** (`files/`): o Nous agora consulta
  automaticamente sua pasta de notas (Obsidian, `.md`, `.txt`) e injeta os trechos
  mais relevantes no contexto de cada conversa.
  - `files/index_files.py` — indexador incremental: chunking por paragrafos/headings,
    embeddings via Ollama (`nomic-embed-text` com prefixo `search_document:`), tabela
    FTS5, mtime+hash para so' reindexa o que mudou. Modo watch (a cada 20 s).
    Singleton por porta (8991) para nao duplicar processo.
  - `files/nous_files.py` — Filter global do Open WebUI com busca **hibrida**:
    semantica (cosine similarity via matriz de embeddings) + palavra-chave (FTS5/BM25),
    fundidas por Reciprocal Rank Fusion. Limiar `MIN_SIM=0.65` bloqueia ruido
    (`search_query:` no embedding da consulta). Status: *"Nous consultou seus
    arquivos: arquivo.md"*. Stopwords PT/EN para eliminar tokens triviais do FTS.
  - `files/register_files.py` — auto-registra o filter direto no `webui.db` (sem
    login, idempotente). Chamado pelo launcher a cada boot.
- **Arena Model desativado** (`ENABLE_EVALUATION_ARENA_MODELS=False`): nao aparece
  mais no dropdown, evitando confusao.
- **Modelo pre-selecionado** (`DEFAULT_MODELS=gemma4:12b`): novo chat ja abre com
  o gemma4 selecionado; usuario nao precisa escolher nada.
### Mudado
- `instalar.bat` agora passa `-WithModel` por padrao: instala o gemma4:12b (~5 GB)
  durante o setup, sem precisar navegar ate Admin > Settings > Models.

## [1.5.1] - 2026-06-07
### Corrigido
- **Wordmark alinhado com a coruja na tela inicial**: o `body::after` fixo ficava
  longe da logo (topo vs centro). Agora o CSS o suprime quando a coruja esta'
  visivel e o `loader.js` injeta `.nous-home-wordmark` diretamente abaixo dela.
### Adicionado
- **Auto-registro do Pipe de imagem** (`images/register_pipe_auto.py`): o launcher
  registra o Gerador de Imagem Local **direto no banco** a cada boot, sem email
  nem senha. Instale o ComfyUI, reinicie o Nous e o Pipe ja' aparece no dropdown
  de modelos, sem nenhum comando extra.

## [1.5.0] - 2026-06-07
### Adicionado
- **Memoria pessoal persistente e 100% local** (`memory/nous_memory.py`): o Nous
  **lembra de voce entre conversas**. E' um Filter global do Open WebUI -
  `inlet` injeta no contexto o que ele ja sabe; `outlet` extrai novos fatos com o
  Ollama local e salva em `nous_memory.sqlite3` (dentro do `NousData`, gitignored).
  Captura fatos duraveis (nome, cidade, trabalho, gostos) e acontecimentos do dia
  a dia (com data). Mostra status na tela: *"Nous lembrou de N detalhe(s)..."*.
- **Auto-instalacao da memoria** (`memory/register_memory.py`): grava a funcao
  direto no banco como Filter **global e ativo** - sem login, sem painel, sem
  importar nada. O launcher roda isso a cada inicio (idempotente; re-sincroniza o
  codigo). E' o primeiro passo do diferencial do Nous: *uma IA na nuvem pode ser
  inteligente; so' uma IA local pode ser realmente sua.*
### Corrigido
- A memoria agora e' **mesclada no system message existente** em vez de criar um
  segundo (que o Ollama descartava) - sem isto, o recall nao chegava ao modelo.

## [1.4.0] - 2026-06-06
### Adicionado
- **Geracao de imagem local** (ComfyUI + Flux.1 Schnell): peca *"crie uma imagem
  de ..."* no chat e a imagem aparece **inline**. Pipe **assincrono** (nao trava o
  servidor) que salva a imagem como **arquivo nativo** do Open WebUI (persistente).
  - `images/install-comfyui.ps1`: instala o ComfyUI + o PyTorch certo p/ a GPU
    (NVIDIA CUDA, AMD RDNA4 ROCm nativo, ou CPU) + custom node GGUF + modelos Flux.
  - `images/register_pipe.py`: registra o Pipe "Gerador de Imagem Local" (idempotente).
- **Visao**: o Gemma agora **le imagens** que voce envia (prints, fotos). O Pipe
  passa as imagens em base64 ao Ollama; antes elas eram descartadas (ele "chutava").
- **Painel de Recursos** (canto inferior esquerdo): VRAM / memoria compartilhada da
  GPU em tempo real, modelos carregados (com contagem regressiva de descarga) e
  botao **"Parar modelos"**. Servico local `monitor/nous_monitor.py` (porta 8990).
- Botao flutuante de tema **claro/escuro** na tela inicial (`branding/nous-loader.js`).
### Mudado
- `OLLAMA_KEEP_ALIVE=30s` (era 5 min): o modelo **sai da VRAM rapido**. O Pipe
  tambem envia `keep_alive` por requisicao.
- `WEBUI_SECRET_KEY` agora e' **fixada** (chave local em `NousData`): fim dos
  logouts a cada reinicio do servidor.
- Busca na web: `BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL=True` corrige o
  "nao tenho acesso a informacoes em tempo real".
- `download-models.ps1`: VAE do Flux agora de um **espelho aberto** (sem login).
### Corrigido
- **Logo/favicons que sumiam (404)**: `apply_branding.py` agora **cria** os PNGs
  que faltavam em `/static` (favicon.png, splash.png, logo.png, ...).

## [1.3.0] - 2026-06-05
### Adicionado
- `installer/nous-setup.iss` -> **`dist/Nous-Setup.exe`** (~8 MB): instalador online
  (Inno Setup) que baixa e configura tudo (Ollama, Python, Open WebUI, identidade),
  cria atalhos e desinstalador. Assistente em portugues.
- Marca **"Nous"** (wordmark) na interface, em fonte serifada classica (Cinzel).
- `branding/make_marble.py`: gerador opcional de textura de marmore.
### Mudado
- Tema: removido o fundo de marmore (ficou poluido); mantidos os acentos dourados.
- Sugestoes da tela inicial: on-brand em portugues por padrao.

## [1.2.0] - 2026-06-05
### Mudado
- A instalacao **nao baixa mais o modelo** por padrao (setup leve, ~5-6 GB). O
  modelo e baixado **dentro do app** (Open WebUI: Admin > Settings > Models), com
  barra de progresso nativa. Use `install-nous.ps1 -WithModel` para baixar no setup.
### Adicionado
- `check-system.ps1` agora **recomenda o modelo** conforme o hardware
  (gemma4:12b com GPU; gemma4:e4b em CPU).
- `health-check.ps1`: ausencia de modelo passou a ser informativa (nao falha mais).

## [1.1.0] - 2026-06-05
### Adicionado
- `installer/install-nous.ps1` — instalador idempotente de **1 comando**: porteiro de
  capacidade (aborta se INCAPAZ) -> Ollama -> modelo -> Python 3.11 -> Open WebUI ->
  identidade Nous -> atalho + launcher oculto -> verificacao. Pula o que ja existe;
  `-Force` reinstala.
- `tools/health-check.ps1` — verificacao pos-instalacao (Ollama no ar, modelo presente,
  ambiente, identidade aplicada, servidor respondendo) com codigo de saida.

## [1.0.0] - 2026-06-04
### Adicionado
- Identidade visual **Nous**: logo da coruja imperial dourada, favicons (png/svg/ico)
  e tema claro **Branco & Ouro** (`branding/`).
- `apply_branding.py` — aplica logo + favicons + tema + nome "Nous" (remove o
  sufixo "(Open WebUI)"), de forma portatil (`import open_webui`).
- `prepare_logo.py` — gera a logo-mestre transparente a partir de uma imagem-fonte.
- `tools/check-system.ps1` — analise inteligente de capacidade da maquina
  (RAM, VRAM real via registro, disco) com veredito e codigo de saida.
- `tools/backup-data.ps1` — backup compactado dos dados com poda automatica.
- `tools/reset-password.py` — redefinicao de senha local (sem segredos no codigo).
- `launchers/` — iniciar/parar em **segundo plano** (sem janela de terminal) e
  `build-exe.ps1` para gerar `.exe` sem console.
- Persistencia dos dados em `DATA_DIR` fora do `site-packages` (sobrevive a updates).
- Documentacao: README, este changelog e o [roadmap](docs/ROADMAP.md).

[1.0.0]: https://github.com/Guilhermecmt/nous-webui/releases/tag/v1.0.0
