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

### v2.1 — Nous Nuvem
- Acesso *opt-in* a modelos de fronteira via NVIDIA NIM API (gratuito, sem GPU).
- Ativacao/desativacao por clique duplo; memoria pessoal protegida (nao vai
  para a nuvem por padrao).

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

### Pesquisa Profunda + Comparar Modelos (v2.4)
- Deep Research: Pipe no dropdown que pesquisa a web em múltiplas etapas e
  entrega um relatório com citações de fonte.
- Comparar Modelos: teste cego (blind) entre dois modelos para a mesma pergunta,
  reusando o Arena do Open WebUI.

### Email assistant (v2.5)
- Triagem, resumo e rascunho de email via IMAP/SMTP com Ollama local.
  Processamento 100% local; envio sempre exige confirmação.

### Bandeja do sistema (System Tray)
- Icone na bandeja: Iniciar/Parar, abrir, status (rodando/parado, GPU/CPU),
  uso de memoria — substitui qualquer necessidade de terminal.

### Distribuicao
- Instalador assinado (.exe/MSI) para reduzir alerta do SmartScreen.
- Auto-update do Nous e do modelo.

---
### Principios
- **Nunca** mostrar janela de terminal ao usuario final.
- **Sempre** checar capacidade antes de baixar (falhar cedo, com mensagem clara).
- **Idempotente**: rodar de novo nao quebra nada; detecta o que ja existe.
- **Privado por padrao**: dados locais; nada sai da maquina sem acao explicita.
