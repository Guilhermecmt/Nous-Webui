# Roadmap — Nous

Objetivo maior: transformar o Nous em um **programa que qualquer pessoa baixa e usa**,
sem conhecimento tecnico, com tudo acontecendo em segundo plano.

## Feito

### v1.0 — Fundacao
- Identidade visual (logo, favicons, tema Branco & Ouro), nome "Nous".
- Persistencia dos dados fora do `site-packages` (`DATA_DIR`).
- Execucao em segundo plano (sem janela de terminal).
- Ferramentas: analise de capacidade, backup, reset de senha.
- Repositorio versionado (Git + SemVer + CHANGELOG).

### v1.1 — Instalador de 1 clique
- Bootstrapper unico (`install-nous`) com porteiro de capacidade (aborta se
  INCAPAZ), instalacao silenciosa de Ollama + Python + Open WebUI, identidade
  aplicada e atalhos criados. Idempotente.

### v1.2 — Setup leve
- O modelo NAO e baixado na instalacao — fica para dentro do app, mantendo o
  setup pequeno e a escolha com o usuario.

### v1.3 — Health check
- Verificacao pos-instalacao: Ollama no ar, ambiente, identidade, servidor,
  atalho. Mensagens acionaveis.

### v1.4–v2.0 — Produto completo
- Visao, geracao de imagem local (ComfyUI + Flux), painel de recursos (VRAM),
  memoria pessoal persistente, RAG de arquivos locais (Obsidian/notas), RAG de
  historico, painel "O que o Nous sabe" + personas, link criar conta, badges
  de capacidade VRAM por modelo, citacoes de fonte.

### v2.7 — Agenda, habilidades e utilidades
- Agenda (notas, lembretes, calendario, assinatura iCal) com aviso do Windows,
  agenda pelo chat, tarefas agendadas, habilidades ("aprenda isso"), relatorio
  visual da pesquisa, editor de fotos com remover fundo local, YouTube e clima
  no chat, velocidade estimada na Loja.

### v2.8 — Seis ondas, testadas com modelo pequeno
- Memoria com fixadas e "organizar", notas com checklist, avisos no celular
  (ntfy) e no e-mail, tarefas encadeadas, conversas longas compactadas,
  pesquisa para modelos pequenos, e-mail com varias contas/anexos/contatos e
  pelo chat, OCR e boletos, formularios PDF, botoes e comandos no chat com
  guarda, diagnostico, dicas, privacidade na tela, galeria com albuns,
  "diga o que fazer" no editor e comparar 2-4 modelos com placar.
- Validado com qwen3:4b: agenda, "aprenda isso", e-mail pelo chat, OCR,
  pesquisa, compactacao (o que era pendente da v2.7).
- Pendente na epoca (feito na v2.11): usar no celular e CalDAV de duas
  vias. Ainda pendente: testar com IMAP real.

### v2.9 — Documentos, memoria portatil e qualquer modelo
- Documentos com a IA sugerindo mudancas para aceitar/recusar, versoes e
  Word/PDF; botoes Mais curto / Mais simples / Documento nas respostas;
  importar e exportar memorias; Loja com qualquer modelo do Ollama/Hugging
  Face (tamanho e encaixe conferidos antes) e simulacao de outra maquina;
  relatorios da pesquisa em PDF/Word.

### v2.10 — Sem login
- Abre direto no chat (a conta unica vira a conta fixa do Open WebUI, mesmo
  id, conversas preservadas; 2+ contas ou `NousData\.exigir_login` mantem o
  login e desfazem a conversao). Tela inicial com saudacao, dica e "Conversa
  privada" (chat temporario que o filtro de memoria ignora).
- Painel "Seu Nous" a' direita no lugar do card Recursos e dos botoes
  flutuantes: anel de uso da placa, agenda, memorias e ferramentas.
- Nous Code: IDE com agente de programacao local (code/), aprovacao com diff,
  desfazer, feito para modelos pequenos. O harness adapta o DeepSeek Harness
  (MIT): contrato das ferramentas, modo plano, objetivo com rodadas, jobs,
  compactacao, skills, LSP, MCP, lembretes e provedores compativeis com
  OpenAI (LM Studio, llama.cpp, vLLM). Proximos passos: diagnosticos do LSP
  depois de editar, worktrees do Git para tarefas isoladas, subagente que
  tambem edita, instalar o Node pelo instalador.

### v2.11 — Celular, agenda de duas vias e atualizacao sozinha
- Open WebUI 0.12.3, com atualizacao segura de quem ja tem o Nous (backup,
  migracao conferida, volta atras). Telas ancoradas em ids estaveis. Loja com
  catalogo novo e ranking explicito. Ollama novo sem nuvem nem boas-vindas
  quando o Nous o instala.
- Usar no celular: portao na rede de casa, desligado por padrao, pareamento
  por QR, firewall so' em rede Privada. HTTP (sem microfone/PWA no celular).
- Agenda: CalDAV de duas vias (iCloud, Nextcloud, Fastmail...). Google so'
  leitura (o CalDAV dele exige OAuth).
- Icone na bandeja; atualizacao automatica do Nous e dos modelos; Nous-Setup.exe
  e script de assinatura prontos (falta o certificado).
- Nous Code: diagnosticos do LSP depois de editar, tarefa separada (worktree),
  subagente que edita, Node portatil pelo instalador.
- E-mail e motor de imagem testados de ponta a ponta (servidor IMAP/SMTP falso;
  ComfyUI com ROCm nativo na RX 9070 XT).

### v2.6 — Correcoes para o primeiro acesso
- Instalador que nao trava nem mente ("Pronto!" so' quando deu certo), app em
  `%LOCALAPPDATA%\Programs\Nous`, entrada em Aplicativos instalados.
- Primeira tela sem o changelog em ingles do Open WebUI; servidor so' local;
  monitor protegido contra paginas de fora. Lint + CI no PowerShell 5.1.

### v2.1 — Nous Nuvem
- Acesso *opt-in* a modelos de fronteira via NVIDIA NIM API (gratuito, sem GPU).
- Ativacao/desativacao por clique duplo; memoria pessoal protegida (nao vai
  para a nuvem por padrao).

### v2.5 — Assistente de Email
- Triagem (importante / pode esperar / promoção / spam), resumo e rascunho de
  resposta via IMAP local. 100% local — conteúdo dos emails só vai ao Ollama
  local, nunca à nuvem. Envio sempre exige confirmação explícita do usuário.
  Ativação opt-in via `conectar-email.bat` ou painel Recursos.

### v2.4 — Pesquisa Profunda + Comparar Modelos
- **Pesquisa Profunda (Nous)**: Pipe no dropdown que pesquisa a web em múltiplas
  etapas via SearXNG local (sem Docker necessário para uso — já sobe no monitor)
  e entrega um relatório markdown com citações `[n]` e lista de fontes.
  100% local (SearXNG + Ollama).
- **Comparar Modelos (Nous)**: teste cego A/B via Arena nativo do Open WebUI,
  reembrulhado com nome amigável e modelos locais. Sem construir split-chat no
  Svelte — decisão validada na v2.0.0 e resolvida pelo Arena.

### v2.3 — Conversa por voz 100% local em PT-BR
- Falar com o Nous e ouvir a resposta em português, sem internet, rodando até
  em CPU. STT Whisper local (pt) + TTS Piper (voz pt_BR) num servidor
  OpenAI-compatível local (porta 8994). Ativação opt-in com 1 clique no painel
  Recursos. Maior diferencial inédito de mercado na categoria.

### v2.2 — Loja de Modelos + primeiro uso guiado
- Loja de Modelos dentro do site: catalogo curado com recomendacao automatica
  para o hardware da maquina, download em 1 clique com progresso real.
- Assistente de primeiro uso: boas-vindas + modelo recomendado + um botao.
- Instalador sem NENHUMA pergunta tecnica; abre o Nous sozinho ao final.
- Atalho garantido (area de trabalho + Menu Iniciar, com verificacao).
- Identidade com auto-cura no boot (marcador versao+hash).
- Versao do Open WebUI pinada (testada) em novas instalacoes.

## Proximo

### Distribuicao
- Certificado de assinatura (Azure Trusted Signing ou OV) para o SmartScreen
  parar de avisar; o script ja esta pronto (docs/DISTRIBUICAO.md).
- Publicar a primeira release no GitHub (o atualizador automatico depende dela).

### Celular
- HTTPS sem assustar leigo (para microfone e instalar como app no celular).
- Testar num celular de verdade e a regra de firewall real.

### Agenda
- Google Agenda de duas vias (exige OAuth e um app registrado no Google).

### Testes com contas e aparelhos reais
- E-mail com Gmail/Outlook de verdade; OCR de imagem anexada.
- Galeria e motor de imagem vistos dentro do Nous; conversa + imagem com a placa
  livre.

---
### Principios
- **Nunca** mostrar janela de terminal ao usuario final.
- **Sempre** checar capacidade antes de baixar (falhar cedo, com mensagem clara).
- **Idempotente**: rodar de novo nao quebra nada; detecta o que ja existe.
- **Privado por padrao**: dados locais; nada sai da maquina sem acao explicita.
