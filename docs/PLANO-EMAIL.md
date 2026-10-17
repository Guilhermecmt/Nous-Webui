# Plano de Execução — "Nous Email" (assistente de email local) — v2.5.0

> Documento de planejamento para execução pelo Sonnet. Estudo feito em 2026-06-13.
> Objetivo: triagem, resumo e rascunho de respostas de email com IA **local**
> (Ollama), conectando à conta do usuário via IMAP/SMTP. É uma das features mais
> pedidas em assistentes de IA (ver memória `competitive-landscape`).
> ATENÇÃO: é o plano de MAIOR escopo e MAIOR superfície de segurança dos três
> (guarda credenciais de email). Executar por ÚLTIMO, depois de Voz e Pesquisa.
> Princípios do projeto valem: nunca mostrar terminal; idempotente; privado por
> padrão; nada sai da máquina (o conteúdo do email só vai ao Ollama LOCAL).

---

## 1. Decisões de design (já tomadas — não re-discutir)

1. **Opt-in explícito.** Email só existe depois que o usuário conecta a conta.
   Sem conexão → nenhuma funcionalidade de email, nenhum serviço no ar.
2. **Credenciais em `NousData\.email_account.json`** (fora do git, mesmo padrão de
   `.nvidia_api_key` e `.webui_secret_key`). Guardar: servidor IMAP/SMTP, porta,
   usuário, e **senha de app** (NÃO a senha principal — ver item 3). Permissões
   restritas ao usuário no Windows (best-effort).
3. **Senha de app, não OAuth.** OAuth do Gmail/Outlook exige registrar um app e
   fluxo de consentimento — atrito alto e fora do espírito leigo/local. Decisão:
   pedir uma **senha de aplicativo** (Gmail e Outlook permitem gerar uma) via
   diálogo gráfico, com link e instrução passo-a-passo em PT-BR. IMAP/SMTP padrão.
4. **Processamento 100% local.** O conteúdo dos emails só é enviado ao **Ollama
   local** para resumir/triar/rascunhar. NUNCA a nuvem (nem mesmo se o usuário
   tiver a Nuvem NVIDIA ativa — forçar modelo local aqui, como a memória pessoal
   já faz: ids com `/` são nuvem e devem ser evitados).
5. **Somente-leitura por padrão; envio exige confirmação.** O Nous LÊ, tria,
   resume e RASCUNHA. Enviar de fato (SMTP) só após o usuário revisar e clicar
   "Enviar". Nunca enviar automaticamente. Apagar/arquivar idem (confirmação).
6. **Entrega = serviço local + painel na UI** (não um Pipe de chat). Email é uma
   superfície própria: micro-serviço REST local (espelhar `memory/nous_memory_api.py`,
   porta 8993 → nova **porta 8995**, CORS só localhost) + painel no
   `branding/nous-loader.js` (botão flutuante, igual ao "O que o Nous sabe").

## 2. Etapas de execução (em ordem)

### Fase 1 — Núcleo (backend)

**1.1 `email/nous_email.py`** (cliente IMAP/SMTP, stdlib `imaplib`/`smtplib`/`email`):
- `connect()` lê `.email_account.json`; conexões TLS (IMAP 993 / SMTP 465/587).
- `list_recent(n=20)` → assunto, remetente, data, snippet (sem baixar anexos).
- `get_message(uid)` → corpo em texto limpo (preferir `text/plain`; se só HTML,
  strip de tags como o `fetch_page` do `rag.py` faz).
- `send_draft(to, subject, body, in_reply_to=None)` → envia via SMTP (só chamado
  após confirmação na UI).
- Best-effort e nunca derruba o serviço; erros viram mensagem amigável PT-BR.

**1.2 `email/nous_email_api.py`** (micro-serviço REST, espelhar
`memory/nous_memory_api.py`: CORS só localhost, escritas atômicas tmp+replace,
bodies malformados → 400). **Porta 8995.** Rotas:
- `GET /status` → conectado? qual conta? (sem expor a senha).
- `POST /connect` body `{imap, smtp, port, user, app_password}` → valida fazendo
  um login IMAP de teste; em sucesso, grava `.email_account.json`. Em falha
  (auth/host), erro claro.
- `POST /disconnect` → apaga `.email_account.json`.
- `GET /inbox` → `list_recent` + para cada email uma **triagem** do Ollama local
  (categoria: importante / pode esperar / promoção / etc. + resumo de 1 linha).
  Cachear por uid para não re-chamar o LLM a cada refresh.
- `GET /message?uid=` → corpo + **resumo** do Ollama local.
- `POST /draft?uid=` → gera um **rascunho de resposta** (Ollama local, tom PT-BR
  educado), retorna o texto para o usuário editar. NÃO envia.
- `POST /send` body `{to, subject, body, in_reply_to}` → envia (após confirmação).
- Toda chamada ao Ollama usa modelo **local** (recusar id com `/`).

**1.3 Privacidade da triagem**: a triagem/resumo roda sob demanda (ao abrir o
painel), não num cron em background, para o usuário ter controle e não haver
processamento silencioso. (Cron opcional fica fora de escopo nesta versão.)

### Fase 2 — Conexão sem terminal (UX)

**2.1 `email/conectar-email.ps1`** (espelhar `cloud/ativar-nuvem.ps1`):
- Diálogo gráfico (InputBox do `Microsoft.VisualBasic.Interaction`) coletando
  email e senha de app; detectar IMAP/SMTP automaticamente para Gmail/Outlook
  pelos domínios comuns (tabela: gmail.com → imap.gmail.com/smtp.gmail.com, etc.),
  perguntando manualmente só se domínio desconhecido.
- MessageBox com **link e passo-a-passo** para gerar a senha de app (Gmail:
  myaccount.google.com → Segurança → Senhas de app).
- Validar login IMAP; em 401/erro, MessageBox claro.
- Salvar via `POST /connect` (ou direto no arquivo + rodar o serviço).
- `email/desconectar-email.ps1`: apaga a conta, confirma.
- Atalhos finos `conectar-email.bat` / `desconectar-email.bat` na raiz.

**2.2 Painel no `branding/nous-loader.js`** (mesmo padrão visual dos painéis
existentes: vanilla JS, dourado `#c8962e`, fundo `rgba(18,18,22,.92)`):
- Botão flutuante (ícone de envelope) abre o painel "Email".
- Se não conectado: tela "Conectar email" com campos + instrução da senha de app
  (chama `POST 8995/connect`).
- Se conectado: lista da caixa de entrada com selo de categoria (triagem) e
  resumo de 1 linha; clicar abre o email com resumo + botão **"Rascunhar
  resposta"** → mostra o rascunho editável → botão **"Enviar"** (confirmação).
- Botão "Desconectar".

### Fase 3 — Launcher, saúde, docs

**3.1 `launchers/start-nous.ps1`**: `Start-EmailAPI` (sobe a 8995 **só se**
`.email_account.json` existe) nos dois pontos de boot, junto de `Start-MemoryAPI`.

**3.2 `tools/health-check.ps1`**: item INFORMATIVO "Email: conectado (conta) /
não conectado" — se conectado, `GET 127.0.0.1:8995/status` com timeout curto;
nunca falhar o health-check por causa do email.

**3.3 Docs**:
- `README.md` + `README.pt-BR.md`: seção "Assistente de email (opcional)" — o que
  faz, como conectar (senha de app), **aviso: o conteúdo dos emails é processado
  pelo modelo LOCAL; nada vai para a nuvem**; envio sempre exige confirmação.
- `docs/ROADMAP.md`: registrar entrega.
- `CHANGELOG.md`: entrada `[2.5.0]`; atualizar `VERSION`.

## 3. Critério de pronto (verificação)
1. Sem conectar: boot normal, serviço 8995 não sobe, nada muda.
2. `conectar-email` com senha de app válida (Gmail de teste): valida e salva;
   senha errada → mensagem clara, nada salvo.
3. Painel lista a caixa de entrada com triagem (categoria + resumo de 1 linha),
   resumos gerados por modelo **local** (conferir que nenhum dado foi à nuvem).
4. "Rascunhar resposta" gera texto editável; "Enviar" só dispara após confirmação
   e o email chega de verdade.
5. `desconectar-email` apaga a conta; serviço para de subir no próximo boot.
6. Com a Nuvem NVIDIA ativa, a triagem/resumo continua usando modelo local
   (id com `/` é recusado).
7. CORS: chamada à 8995 de origem não-local é bloqueada (CSRF local), como na
   memory API (8993).

## 4. Riscos e armadilhas
- **SEGURANÇA é o maior risco.** Credenciais de email em disco: arquivo fora do
  git, permissões restritas, nunca logar a senha, CORS só localhost (o bug de
  CSRF da memory API na v1.9.0 é o precedente — não repetir). Considerar avisar o
  usuário para usar senha de app (revogável) e nunca a senha principal.
- **Envio acidental**: jamais enviar sem clique explícito; sem auto-resposta.
- **Vazamento para a nuvem**: forçar modelo local em TODA chamada de IA do email
  (recusar ids com `/`), mesmo com a Nuvem ativa.
- **IMAP de provedores variados**: começar com Gmail/Outlook (detecção
  automática); domínios desconhecidos pedem servidor/porta manual.
- **Volume**: caixas grandes — paginar (`list_recent(20)`) e triar sob demanda,
  não a caixa inteira.
- **Menos "mágico" para o leigo total** que voz/imagem, e mais arriscado — por
  isso é o último dos três. Se a senha de app provar ser barreira grande em
  testes, reavaliar o valor antes de investir mais.

## 5. Fora de escopo (não fazer agora)
- OAuth (Gmail/Outlook) — senha de app primeiro.
- Triagem automática em background / cron — sob demanda nesta versão.
- Anexos (download/análise) e calendário — ficam para versões futuras.
- Múltiplas contas simultâneas — uma conta por vez na v2.5.0.
