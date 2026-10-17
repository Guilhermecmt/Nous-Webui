<div align="center">

<img src="branding/assets/nous_logo.png" width="120" alt="Logo do Nous">

# Nous

**Sua IA particular — bonita, local e sua.**

Chat · Documentos · Agenda · E-mail · Visão · Imagens · Pesquisa — 100% no seu PC.  
Sem nuvem. Sem mensalidade. Suas conversas nunca saem da sua máquina.

[![version](https://img.shields.io/badge/version-2.9.0-c8962e)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)
[![platform](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6)](#requisitos)
[![local](https://img.shields.io/badge/100%25-local%20%26%20privado-2ea44f)](#por-que-o-nous)

[English](README.md) · **Português**

<img src="docs/screenshots/hero-github.png" width="860" alt="Interface do Nous">

</div>

---

## Por que o Nous

**Nous** (do grego *νοῦς*, "mente") transforma as melhores ferramentas de IA local em um produto acabado: instala com dois cliques, escolhe o modelo certo para o seu computador e cuida de tudo em segundo plano. Nenhuma etapa exige conhecimento técnico.

O que você ganha em relação a um chat de IA comum:

- **Privacidade de verdade.** O modelo roda no seu computador. Conversas, arquivos e memórias ficam com você — não há servidor para onde mandar nada.
- **Ele lembra de você.** O Nous aprende fatos duráveis (nome, trabalho, preferências) ao longo das conversas e os usa nas seguintes. Tudo armazenado localmente.
- **Ele lê suas anotações.** Aponte para o seu vault do Obsidian ou qualquer pasta de notas e o Nous traz os trechos relevantes para dentro da conversa.
- **Loja de Modelos integrada.** O Nous analisa seu hardware, recomenda o modelo ideal e baixa tudo com um clique — dentro do próprio site, com barra de progresso.
- **Visão e imagem.** Solte um print e pergunte sobre ele; peça *"crie uma imagem de…"* e ela aparece na conversa (ComfyUI + Flux, opcional).
- **Busca na web** opcional via DuckDuckGo, sem chave de API.
- **Documentos com a IA ao lado.** Escreva uma carta, um currículo ou um trabalho e peça *corrigir*, *mais formal*, *mais curto* ou *tópicos em texto*: cada mudança aparece riscada e você aceita ou recusa. Baixa em Word ou PDF.
- **Pesquisa Profunda.** Selecione "Pesquisa Profunda (Nous)" no dropdown — o Nous planeja, busca a web em múltiplas etapas, lê as páginas e entrega um relatório markdown com citações numeradas e lista de fontes clicáveis. 100% local.
- **Comparação cega de modelos.** A mesma pergunta para 2 a 4 modelos, voto antes de ver os nomes e um placar de qual combina mais com você.
- **Assistente de email (opcional).** Conecte sua caixa de entrada e o Nous faz triagem, resume e rascunha respostas — tudo na sua máquina. Seus emails só chegam ao modelo Ollama local, nunca à nuvem. Envio sempre exige confirmação.
- **Agenda, lembretes e tarefas.** *"Me lembre de pagar a luz sexta às 9h"* vira um aviso do Windows na hora certa; tarefas como o "bom dia com a agenda e os e-mails" rodam sozinhas no horário.
- **Ele aprende o seu jeito.** Diga *"aprenda isso"* e o Nous guarda o passo a passo para a próxima vez — inclusive o seu estilo de escrever.
- **Lê fotos, boletos e PDFs.** Texto de prints e documentos lido na sua máquina, boleto com valor e vencimento conferidos e formulários PDF preenchidos e assinados.
- **Editor de fotos e Galeria.** Remova o fundo, corte e ajuste — ou só escreva *"tira o fundo e corta quadrado"*.
- **Painel de recursos.** VRAM em tempo real, modelos carregados, um botão para liberar a placa de vídeo e um **Diagnóstico** que diz o que está funcionando.
- **Sem janelas de terminal.** Abre por um atalho, roda em segundo plano, fecha pelo "Parar Nous".

### Novidades da versão 2.9

- **📝 Documentos:** escreva ao lado do chat e peça à IA para corrigir, deixar formal, encurtar, organizar ou continuar. Ela **só sugere** — cada mudança aparece riscada/sublinhada para você aceitar ou recusar. Selecione um trecho para mexer só nele. Salva sozinho, guarda versões e baixa em **Word, PDF ou Markdown**.
- **Respostas:** botões **✂ Mais curto**, **🙂 Mais simples** e **📝 Documento** (abre a resposta para editar e baixar).
- **Memória:** **⬆ Importar** fatos de um currículo, de um "sobre mim" ou das memórias do ChatGPT (você escolhe o que guardar) e **⬇ Exportar** tudo em um arquivo.
- **Loja de Modelos:** baixe **qualquer modelo** do Ollama ou do Hugging Face pelo nome ou link — o Nous confere o tamanho e se cabe na sua máquina antes — e **"E se eu tivesse outra máquina?"** mostra o que rodaria com outra placa.
- **Pesquisa Profunda:** relatórios baixam em **PDF ou Word**.

Versões anteriores no [CHANGELOG](CHANGELOG.md).

---

<div align="center">
<img src="docs/screenshots/philosophy-banner.png" width="860" alt="Nous — The Intelligence Engine">
</div>

---

## Requisitos

| Recurso | Mínimo | Recomendado |
|---------|--------|-------------|
| Sistema | Windows 10 / 11 | Windows 11 |
| RAM     | 8 GB | 16 GB+ |
| GPU     | nenhuma — roda na CPU | 8 GB+ de VRAM |
| Disco   | 20 GB livres | 30 GB+ |

> **Sem placa de vídeo dedicada?** O Nous funciona na CPU — as respostas só demoram mais (1–2 min). A Loja de Modelos detecta isso e recomenda modelos leves automaticamente.

---

## Instalação

> Duas ações. Nenhuma configuração.

1. Clique no botão verde **Code → Download ZIP** no topo desta página e descompacte onde quiser.
2. Abra a pasta e dê **clique duplo em `instalar.bat`**. Se o Windows mostrar um aviso de segurança, escolha **"Mais informações → Executar assim mesmo"**.

O instalador verifica seu hardware, instala o Ollama, o Python e a interface, aplica a identidade Nous e cria os atalhos — na **área de trabalho** e no **Menu Iniciar**. Ao final, o Nous abre sozinho no navegador.

O Nous fica instalado em `%LOCALAPPDATA%\Programs\Nous`: depois da instalação, a pasta que você baixou pode ser apagada. Se algo falhar no caminho, o instalador mostra o motivo em vermelho em vez de dizer "Pronto!".

---

## Primeiro uso

**1. Crie sua conta.** Qualquer nome, e-mail e senha — a conta existe só na sua máquina, e a primeira criada é a administradora.

**2. Deixe o assistente trabalhar.** Na primeira abertura, o Nous percebe que ainda não há um modelo de IA instalado e mostra uma tela de boas-vindas com o **modelo recomendado para o seu computador**. Um clique em **"Baixar e começar"** e ele cuida do download, mostrando o progresso.

**3. Converse.** Quando o download termina, é só começar a digitar.

---

## Modelos de IA

A **Loja de Modelos** fica no card *Recursos* (canto inferior esquerdo) → botão **"Baixar modelos"**. Ela lista um catálogo curado com:

- selo **"Recomendado para sua máquina"** nos modelos que aproveitam bem o seu hardware (a análise de GPU/RAM é automática);
- selo **"Entende imagens"** nos modelos com visão;
- descrição em português, tamanho do download e instalação em **1 clique** com barra de progresso.

Você pode ter vários modelos instalados e alternar entre eles no seletor do topo do chat. Para referência, alguns destaques do catálogo:

| Sua máquina | Modelo sugerido | Download | Perfil |
|-------------|-----------------|----------|--------|
| Sem GPU dedicada | Qwen 3.5 4B | ~3,4 GB | Leve, rápido na CPU, entende imagens |
| GPU 8–12 GB | Gemma 4 12B | ~7,6 GB | Conversa, escrita e visão — o equilíbrio ideal |
| GPU 12–16 GB | Qwen 3 14B | ~9,3 GB | Raciocínio melhor, contexto mais longo |
| GPU 20 GB+ | Qwen 3 32B | ~20 GB | Qualidade comparável aos grandes modelos de nuvem |

Para **qualquer outro modelo**, escreva o nome (`qwen3:8b`) ou cole o link do [ollama.com](https://ollama.com/library) ou de um repositório GGUF do Hugging Face no campo **"Outro modelo"** da Loja e clique **Conferir**: o Nous lê o tamanho no catálogo (sem baixar nada), diz se cabe na sua placa e no disco e só então oferece o **Baixar**.

Pensando em trocar de computador? **"E se eu tivesse outra máquina?"** simula outra placa de vídeo e quantidade de RAM e mostra o que rodaria e a que velocidade.

---

## Recursos

### Memória — o Nous lembra de você

Conversando normalmente, o Nous identifica fatos duráveis — nome, cidade, trabalho, gostos — e os recupera nas conversas seguintes. O painel **"O que o Nous sabe"** (botão de cérebro, canto inferior direito) permite ver, editar e apagar cada memória, além de criar **personas** com memórias separadas (trabalho, estudos, pessoal). Tudo fica em `NousData`, no seu disco.

Fatos de identidade e de saúde (nome, alergias, remédios) ficam **fixados** e entram em toda conversa; dá para fixar outros com o 📌. Quando as memórias passam de 30, o Nous leva só as fixadas, as mais recentes e as que têm a ver com a pergunta. **🧹 Organizar memórias** encontra repetidas e propõe juntá-las — nada muda sem o seu OK.

**⬆ Importar** traz o que você já escreveu sobre si: um currículo, um texto "sobre mim" (.txt, .md, .docx, .pdf) ou a lista de memórias do ChatGPT colada no campo. O Nous propõe os fatos, marca os que já sabia e você escolhe o que guardar. **⬇ Exportar** baixa todas as memórias num arquivo (backup ou outro computador) — que o Importar traz de volta igualzinho, com as fixadas.

### Arquivos — o Nous lê suas anotações

No primeiro uso, o Nous cria a pasta `Documentos\Nous`. Qualquer `.md` ou `.txt` colocado ali entra automaticamente na busca que acontece antes de cada resposta. A busca usa o **granite-embedding** (multilíngue, entende português), baixado sozinho; os índices se refazem se o modelo mudar. Para usar seu vault do Obsidian, altere o valve `FOLDER` do filtro **Nous Files** no painel de administração.

### Geração de imagem local (opcional)

```powershell
powershell -ExecutionPolicy Bypass -File images\install-comfyui.ps1
```

Instala o ComfyUI, o PyTorch certo para a sua GPU e os modelos Flux.1 Schnell (~12 GB). Depois, selecione **Gerador de Imagem Local** no seletor de modelos e peça: *"crie uma logo dourada de uma coruja"*. A imagem aparece na conversa.

### Assistente de Email — IA local para sua caixa de entrada (opcional)

Conecte seu email (Gmail, Outlook, Yahoo) via `conectar-email.bat` ou pelo botão **✉ Assistente de Email** no card Recursos. Dá para ligar **várias contas** e escolher a padrão. O Nous vai:

- **Triar** cada email: Importante / Pode esperar / Promoção / Spam + resumo de 1 linha.
- **Resumir** a mensagem completa quando você abre — inclusive o conteúdo dos **anexos** (PDF, planilha, imagem).
- **Rascunhar uma resposta** em PT-BR educado, pronta para editar, ou **agendar** o envio.
- **Escrever pelo chat:** *"manda um e-mail para a Ana dizendo que atraso 10 minutos"* — o destinatário vem dos **contatos aprendidos** dos seus e-mails (importa/exporta vCard) e o texto vira um rascunho.
- **Convites** de reunião vão para a Agenda com um clique; a aba **Newsletters** ajuda a sair de listas.
- **Enviar** somente após você revisar e confirmar — nunca envia automaticamente.

> **Privacidade:** seus emails são processados apenas pelo **modelo Ollama local**. Nenhum conteúdo sai da máquina, mesmo com Nuvem NVIDIA ativa. As credenciais ficam em `NousData/.email_accounts.json` (fora do git). Use uma **senha de aplicativo**, não a senha principal — revogável a qualquer momento.

---

### Pesquisa Profunda — pesquisa multi-etapas com fontes

Selecione **"Pesquisa Profunda (Nous)"** no dropdown de modelos e faça qualquer pergunta de pesquisa. O Nous:

1. Planeja 2–4 sub-perguntas para cobrir o tema completamente.
2. Busca a web (SearXNG local) para cada sub-pergunta.
3. Baixa e lê as páginas mais relevantes.
4. Escreve um relatório em markdown com citações `[n]` e uma seção **Fontes** com URLs clicáveis.
5. Salva um **relatório visual** (sumário, citações clicáveis, cartões das fontes) na biblioteca **Recursos › Relatórios**, com o link no fim da resposta. Ali cada relatório também baixa em **PDF** ou **Word**.

Com modelos pequenos (até ~10B) ela faz menos buscas e responde direto quando a pergunta é simples; pergunta vaga ganha sugestões em botões, e dá para continuar a conversa sobre o último relatório (*"e no Brasil?"*).

Tudo roda na sua máquina. Sem chave de API, sem nuvem. Requer o container SearXNG (sobe automaticamente quando o Docker está disponível).

### Comparar Modelos — teste cego e placar

**Recursos › ⚖ Comparar modelos**: a mesma pergunta para **2 a 4 modelos**, um de cada vez (a placa fica inteira para cada um), com o tempo e os tokens/s de cada resposta. Por padrão é às cegas: você vota na melhor e só então vê os nomes. Os votos formam um **placar** com o aproveitamento e a velocidade média de cada modelo nesta máquina.

No chat, **"Comparar Modelos (Nous)"** no dropdown continua fazendo o duelo A/B da Arena. Os dois precisam de pelo menos dois modelos de chat instalados.

---

### Conversa por voz em português (opcional)

O Nous pode ouvir e falar — tudo na sua máquina, sem internet, sem API de nuvem.

```
Clique duplo em  ativar-voz.bat
```

Ou abra o painel **Recursos** → clique em **"🎙 Ativar voz em PT-BR"**. O painel baixa o motor de voz Piper (~30 MB) e o modelo de voz brasileiro (~60 MB). O modelo Whisper de reconhecimento de fala (~150 MB) é baixado automaticamente no primeiro uso.

Depois de ativar: clique no **ícone de telefone** no cabeçalho do chat para entrar no modo voz *hands-free* — fale, o Nous transcreve, responde e lê a resposta em voz alta em PT-BR.

> **100% local.** Áudio e transcrições nunca saem da sua máquina. A voz funciona mesmo usando um modelo de nuvem no chat — só o texto vai para a nuvem, nunca sua voz.

---

### Nous Nuvem — modelos de fronteira opcionais

O Nous é local por padrão. Se quiser experimentar modelos de ponta (DeepSeek R1, Llama 3.3 70B, Kimi K2…) sem GPU potente, conecte-o à API gratuita da NVIDIA:

1. Crie uma chave gratuita em [build.nvidia.com/models](https://build.nvidia.com/models) (sem cartão de crédito).
2. Clique duplo em **`ativar-nuvem.bat`**, cole a chave, confirme.
3. Reinicie o Nous — os modelos de nuvem aparecem no seletor.

> **Privacidade preservada:** conversas com modelos de nuvem vão para os servidores da NVIDIA, mas a sua **memória pessoal nunca é enviada** — o Nous a retém automaticamente nessas requisições. Para desligar tudo: `desativar-nuvem.bat`.

Também é possível plugar provedores pagos (GPT, Claude via OpenRouter) em Admin Panel → Settings → Connections. Sem chave, nada sai da máquina.

### Agenda — notas, lembretes e calendário

Peça no chat: *"me lembre de pagar a luz sexta às 9h"*, *"marca dentista dia 20 às 14h"*, *"anota: ideia para o projeto…"*, *"o que eu tenho amanhã?"*. O modelo local entende o pedido e grava na agenda; na hora certa o Nous avisa com uma **notificação do Windows** (mesmo com o navegador fechado) e um cartão na tela.

O painel **Recursos › 📅 Agenda** tem quatro abas: **Hoje** (atrasados e próximos 7 dias), **Notas** (busca, fixar, concluir, repetir todo dia/dias úteis/semana/mês/ano), **Calendário** (mês, compromissos com aviso antes, importar/exportar `.ics`) e **Tarefas**. Dá para trazer o Google Agenda, o Outlook ou o iCloud colando o endereço **iCal** da agenda (só leitura, atualiza de hora em hora).

Notas aceitam **listas de verificação** (`- [ ] item`) e o botão **💬 usar no chat**. Em **⚙ Avisos**, os lembretes também chegam no **celular** (app gratuito ntfy, sem cadastro) e/ou no seu **e-mail**. Se o Nous gravou algo errado pelo chat, o botão **↩ Desfazer** na resposta apaga. Datas e horas (*"sexta às 9h"*, *"daqui a 2 horas"*, *"dia 20"*) são lidas por regra, não adivinhadas pelo modelo. O Calendário e as Automações nativos do Open WebUI ficam escondidos para não haver dois de cada.

### Tarefas agendadas — o Nous trabalha sozinho

Em **Agenda › Tarefas**: *"todo dia às 8h, bom dia com a agenda e os e-mails"*, *"toda segunda, pesquise novidades de IA"*, *"às 18h, resuma meus e-mails"*. Rodam no horário mesmo com o navegador fechado; o resultado vira uma nota, um aviso e, se quiser, um e-mail para você. Uma tarefa pode **encadear** outra (o resultado da primeira vira contexto da segunda) e espera alguns minutos se você estiver usando a placa de vídeo.

### Habilidades — o Nous aprende o seu jeito

Depois de acertar algo numa conversa (o formato do relatório, o tom do e-mail de cobrança…), diga **"aprenda isso"**. O Nous resume o passo a passo numa habilidade (um arquivo `.md` legível em `NousData\skills`) e, nos próximos pedidos parecidos, segue sozinho. Em **Recursos › 🧠 Habilidades** você revisa, edita, cria e importa habilidades no formato `SKILL.md` de um link do GitHub. **✍ Ensinar meu jeito de escrever** lê textos seus e guarda o seu estilo, usado sempre que você pede para o Nous escrever algo.

### Documentos — escrever com a IA ao lado

**Recursos › 📝 Documentos** (ou *"abre meus documentos"* no chat). Escreva uma carta, um currículo, um trabalho ou um post — ou abra um arquivo `.docx`, `.pdf`, `.txt` ou `.md`. Embaixo ficam os pedidos prontos: **Corrigir português**, **Mais formal**, **Mais simples**, **Mais curto**, **Tópicos em texto**, **Organizar com títulos** e **Continuar escrevendo**, além do campo para pedir do seu jeito (*"troque você por senhor"*).

Documento vazio? Escolha um **modelo pronto** (carta formal, currículo, e-mail profissional, reclamação, ata) ou **✨ Escrever com a IA**: descreva o que precisa e revise o rascunho.

A IA nunca escreve direto no documento: cada mudança aparece **riscada (antes) e sublinhada (depois)** com ✓ e ✕. A revisão mostra *"sugestão 2 de 7"*; **Enter** aceita, **Delete** recusa e o Nous passa para a próxima sozinho — ou use **Aceitar todas** / **Recusar todas**. Depois de aplicar, o aviso traz **Desfazer**. Se você **selecionar um trecho** antes de pedir, só ele muda. Antes de cada mudança aceita, o Nous guarda uma **versão** (também a cada 10 min de escrita), e dá para voltar a qualquer uma.

O documento salva sozinho em `NousData\documentos`. **⬇ Baixar** gera **Word (.docx)**, **PDF** ou **Markdown**; **💬 Usar no chat** leva o texto para a conversa. Nas respostas do chat, o botão **📝 Documento** faz o caminho inverso. Tudo roda no modelo local.

### Utilidades no chat

- **YouTube:** cole um link e peça "resuma" ou pergunte sobre o vídeo — o Nous lê a legenda (português, se houver) e responde citando os minutos.
- **Clima:** *"vai chover amanhã em Curitiba?"* — previsão do Open-Meteo (gratuito, sem chave). Defina uma cidade padrão em Painel Admin › Funções › Nous Clima.
- **Ler imagens e boletos:** mande a foto de um documento, print ou boleto — o Nous lê o texto na sua máquina (OCR) mesmo com um modelo sem visão. Boletos saem com banco, valor e vencimento, conferidos pelo dígito verificador.
- **Formulários PDF** (**Recursos › 📄 Formulários**): mostra os campos de um PDF preenchível, sugere o que já sabe de você e assina com a sua assinatura salva.
- **Conversas longas:** quando a conversa passa do que o modelo aguenta, o Nous resume o começo sozinho e segue lembrando dos detalhes.
- **Respostas sob medida:** embaixo de cada resposta, **✂ Mais curto** e **🙂 Mais simples** pedem a reescrita, e **📝 Documento** abre a resposta nos Documentos.
- **Controle pelo chat:** *"abre minha agenda"*, *"tema escuro"*, *"libera a placa de vídeo"*, *"abre a galeria"*. Quando há escolhas, a resposta traz **botões**; e o Nous confere se o que o modelo diz ter feito (*"anotei"*, *"rascunho pronto"*) foi mesmo feito.

### Editor de fotos e Galeria

**Recursos › 🖼 Editor de fotos**, ou o botão **"✎ Editar"** que aparece sobre as imagens do chat. Cortar (livre, 1:1, 4:3, 16:9, 9:16), girar, espelhar, brilho/contraste/saturação/temperatura, filtros, redimensionar, desfazer/refazer, baixar PNG/JPG ou copiar. **Remover fundo** usa um modelo U²-Net de 4,5 MB, baixado no primeiro uso e rodando na sua máquina. Em **Diga o que fazer**, escreva do seu jeito: *"tira o fundo, deixa mais claro e corta quadrado"* (funciona sem modelo de IA).

A **Galeria** reúne as imagens geradas: favoritas ★, álbuns 📁, zoom, lixeira e o ✎ que abre a imagem no Editor.

### Painel de recursos e diagnóstico

O card **Recursos** (canto inferior esquerdo) mostra VRAM em tempo real, os modelos carregados na memória e os botões **"Parar modelos"** (libera a GPU na hora) e **"Baixar modelos"** (abre a Loja, que mostra a **velocidade estimada** de cada modelo na sua placa), além dos atalhos para Agenda, Email, Habilidades, Relatórios, Documentos, Galeria, Editor, Formulários e Comparar modelos.

**🩺 Diagnóstico** responde *"o que está funcionando?"*: cada parte do Nous com ✓/✗ e o que fazer. Ali também ficam a **privacidade na tela** (CPF, cartão, senhas e chaves aparecem borrados nas conversas até você clicar) e **"Ver as dicas de novo"** — cada painel mostra uma dica curta na primeira vez.

---

## Problemas comuns

**"O Windows protegeu seu computador" / "Editor desconhecido"**  
Comportamento padrão para software sem assinatura digital. Clique em **"Mais informações" → "Executar assim mesmo"**.

**O atalho não apareceu na área de trabalho**  
Alguns antivírus bloqueiam a criação de atalhos. Aperte a **tecla Windows** e digite **Nous** — o atalho do Menu Iniciar sempre é criado. Alternativa: clique duplo em `iniciar.bat` em `%LOCALAPPDATA%\Programs\Nous`.

**A tela inicial não mostra a logo do Nous / aparece "Open WebUI"**  
Abra o Nous pelo atalho e pressione **Ctrl+Shift+R** no navegador. A identidade é verificada e reaplicada automaticamente a cada inicialização.

**Abre mas não há modelo para conversar**  
Card *Recursos* → **"Baixar modelos"** → escolha o recomendado. O assistente de boas-vindas também reaparece enquanto não houver modelo instalado.

**"Ollama não está rodando" ou o chat não responde**  
Abra o Nous pelo atalho (não pelo endereço direto no navegador) — o atalho inicia todos os serviços. Persistindo, use **"Parar modelos"** no painel e abra de novo.

**A instalação falhou / quero recomeçar**  
Clique duplo em `desinstalar.bat` → opção **[1] Remoção segura** → rode `instalar.bat` de novo. Suas conversas e notas são preservadas.

**Esqueci minha senha**  
Em `%LOCALAPPDATA%\Programs\Nous`:
```powershell
python tools\reset-password.py --email seuemail@exemplo.com
```

---

## Desinstalar

Em **Configurações → Aplicativos → Aplicativos instalados**, procure **Nous** e clique em **Desinstalar** (ou dê clique duplo em `desinstalar.bat`, em `%LOCALAPPDATA%\Programs\Nous`):

- **[1] Remoção segura** *(recomendada)* — remove o app e o ambiente Python. Preserva conversas, notas, Ollama e Python.
- **[2] Remover tudo** — apaga também as conversas e desinstala Ollama/Python, **somente** se foi o Nous que os instalou. Programas que já existiam não são tocados.

---

## Estrutura do projeto

```
Nous WebUI/
├─ branding/    identidade: logo, tema Branco & Ouro, loader.js (painéis), aplicador
├─ voice/       Voz em PT-BR: servidor Piper TTS + registro STT/TTS
├─ cloud/       Nous Nuvem: registro opt-in da API NVIDIA NIM
├─ files/       RAG de arquivos locais: indexador + busca híbrida
├─ history/     RAG do histórico de conversas
├─ images/      geração de imagem: instalador ComfyUI, modelos Flux, Pipe do chat
├─ memory/      memória pessoal: filtro, API do painel, personas
├─ monitor/     painel de recursos + Loja de Modelos (serviço local, porta 8990)
├─ launchers/   iniciar/parar em segundo plano + build do .exe
├─ installer/   instalador de 1 clique + script do Inno Setup
├─ search/      busca na web + Pipe de Pesquisa Profunda (SearXNG + Ollama)
├─ evaluation/  Comparar Modelos: registro do Arena (comparação cega A/B)
├─ email/       Assistente de Email: cliente IMAP/SMTP + API REST (porta 8995)
├─ agenda/      notas, lembretes, calendário e tarefas agendadas (porta 8996)
├─ skills/      habilidades: filtro do chat + API do painel (porta 8997)
├─ utilidades/  filtros do chat: YouTube, clima, OCR/boletos, compactar, comandos, guarda
├─ documentos/  Documentos (IA com sugestões, versões, Word/PDF) e formulários PDF
├─ ajustes/     padrões do Open WebUI para o Nous (português, embeddings, nativos escondidos)
├─ tools/       análise de capacidade, backup, reset de senha, health check
└─ docs/        roadmap, screenshots
```

## Uso avançado

<details>
<summary>Opções para desenvolvedores</summary>

### Verificação de hardware

```powershell
powershell -ExecutionPolicy Bypass -File tools\check-system.ps1
```

Imprime **CAPAZ (GPU)**, **CAPAZ (CPU)** ou **INCAPAZ**, com detalhes e recomendações.

### Instalação por linha de comando

```powershell
powershell -ExecutionPolicy Bypass -File installer\install-nous.ps1 -WithModel -Model qwen3:14b
```

Idempotente. `-WithImages` instala também o motor de imagem; `-Force` reinstala. A versão do Open WebUI é **pinada** no script (`$OPENWEBUI_PIN`) — atualize o pin conscientemente após testar.

### Instalação manual

```powershell
# 1) Ollama  →  https://ollama.com
# 2) Python 3.11 + Open WebUI
py -3.11 -m venv $env:USERPROFILE\open-webui
& $env:USERPROFILE\open-webui\Scripts\python.exe -m pip install open-webui
# 3) Identidade Nous
& $env:USERPROFILE\open-webui\Scripts\python.exe branding\apply_branding.py
# 4) Iniciar
powershell -ExecutionPolicy Bypass -File launchers\start-nous.ps1
```

### Ferramentas

```powershell
tools\backup-data.ps1                                    # backup dos dados, mantém 10
tools\health-check.ps1                                   # verificação de integridade
python tools\reset-password.py --email voce@exemplo.com  # redefinir senha
```

### Serviço da Loja de Modelos (porta 8990)

```
GET  /stats        VRAM + modelos carregados
GET  /hardware     GPU, VRAM, RAM e tier da máquina
GET  /catalog      catálogo curado, ordenado para esta máquina
POST /pull         {"model":"tag"} — inicia download em background
GET  /pull/status  ?model=tag — progresso em tempo real
POST /unload       descarrega modelos da VRAM
GET  /research     biblioteca de relatórios da Pesquisa Profunda (/research/view?id=)
POST /image/remove-bg  imagem -> PNG sem fundo (editor de fotos)
GET  /installed    modelos instalados no Ollama (o painel não fala com o Ollama direto)
GET  /gallery      imagens geradas (/gallery/image/{id}, /gallery/delete, /gallery/meta)
GET  /diag         Diagnóstico: cada parte do Nous com ✓/✗
POST /pdf/fields   formulários PDF (/pdf/fill, /pdf/autofill, /pdf/signature)
POST /compare/run  Comparar modelos (/compare/vote, /compare/score, /compare/reset)
```

Agenda (8996) e Habilidades (8997) documentam as rotas no topo de
`agenda/nous_agenda_api.py` e `skills/nous_skills_api.py`.

### Instalador .exe (Inno Setup)

`installer\nous-setup.iss` gera `dist\Nous-Setup.exe` com `ISCC.exe installer\nous-setup.iss`.

</details>

---

<div align="center">
<img src="docs/screenshots/wallpaper.png" width="860" alt="Nous — Your Personal AI Sovereign">
</div>

---

## Construído sobre

[Open WebUI](https://github.com/open-webui/open-webui) ·
[Ollama](https://ollama.com) ·
[ComfyUI](https://github.com/comfyanonymous/ComfyUI) ·
[Flux.1 Schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) (Apache-2.0) ·
[U²-Net](https://github.com/xuebinqin/U-2-Net) (Apache-2.0, modelo `u2netp` publicado pelo [rembg](https://github.com/danielgatis/rembg)) ·
[RapidOCR](https://github.com/RapidAI/RapidOCR) (Apache-2.0) ·
[pypdf](https://github.com/py-pdf/pypdf) (BSD-3) ·
[Granite Embedding](https://huggingface.co/ibm-granite/granite-embedding-278m-multilingual) (Apache-2.0) ·
[ntfy](https://ntfy.sh) ·
[Open-Meteo](https://open-meteo.com).  
A estimativa de velocidade da Loja foi inspirada na ideia do [llmfit](https://github.com/AlexsJones/llmfit) (MIT).  
Marcas pertencem aos seus respectivos projetos.

## Licença

[MIT](LICENSE) © Nous. Contribuições são bem-vindas — abra uma issue ou um PR.
