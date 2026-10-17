# Changelog

## [2.8.0] - 2026-10-17
O melhor do Odysseus que faltava, em seis ondas, e cada função testada de
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
Funções inspiradas no Odysseus (PewDiePie), reescritas no estilo do Nous
(o Odysseus é AGPL; nenhum código dele foi copiado e o Nous continua MIT).
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
  identificado na análise competitiva: nem o Odysseus (só STT, inglês) nem os
  concorrentes entregam voz conversacional em PT-BR para leigos.
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
