<div align="center">

<img src="branding/assets/nous_logo.png" width="120" alt="Logo do Nous">

# Nous

**Sua IA particular — bonita, local e sua.**

Chat · Visão · Geração de imagem · Busca na web — 100% no seu PC.  
Sem nuvem. Sem mensalidade. Suas conversas nunca saem da sua máquina.

[![version](https://img.shields.io/badge/version-2.6.0-c8962e)](CHANGELOG.md)
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
- **Ele lê suas anotações.** Aponte para o seu vault do Obsidian ou qualquer pasta de notas e o Nous traz os trechos relevantes para dentro da conversa, com citação da fonte.
- **Loja de Modelos integrada.** O Nous analisa seu hardware, recomenda o modelo ideal e baixa tudo com um clique — dentro do próprio site, com barra de progresso.
- **Visão e imagem.** Solte um print e pergunte sobre ele; peça *"crie uma imagem de…"* e ela aparece na conversa (ComfyUI + Flux, opcional).
- **Busca na web** opcional via DuckDuckGo, sem chave de API.
- **Pesquisa Profunda.** Selecione "Pesquisa Profunda (Nous)" no dropdown — o Nous planeja, busca a web em múltiplas etapas, lê as páginas e entrega um relatório markdown com citações numeradas e lista de fontes clicáveis. 100% local.
- **Comparação cega de modelos.** Selecione "Comparar Modelos (Nous)" e faça uma pergunta — duas respostas anônimas aparecem lado a lado. Você vota antes de ver os nomes.
- **Assistente de email (opcional).** Conecte sua caixa de entrada e o Nous faz triagem, resume e rascunha respostas — tudo na sua máquina. Seus emails só chegam ao modelo Ollama local, nunca à nuvem. Envio sempre exige confirmação.
- **Painel de recursos.** VRAM em tempo real, modelos carregados e um botão para liberar a placa de vídeo na hora.
- **Sem janelas de terminal.** Abre por um atalho, roda em segundo plano, fecha pelo "Parar Nous".

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

Usuários avançados podem instalar **qualquer** modelo do catálogo [ollama.com/library](https://ollama.com/library) pelo painel de administração (Admin Panel → Settings → Models).

---

## Recursos

### Memória — o Nous lembra de você

Conversando normalmente, o Nous identifica fatos duráveis — nome, cidade, trabalho, gostos — e os recupera nas conversas seguintes. O painel **"O que o Nous sabe"** (botão de cérebro, canto inferior direito) permite ver, editar e apagar cada memória, além de criar **personas** com memórias separadas (trabalho, estudos, pessoal). Tudo fica em `NousData`, no seu disco.

### Arquivos — o Nous lê suas anotações

No primeiro uso, o Nous cria a pasta `Documentos\Nous`. Qualquer `.md` ou `.txt` colocado ali entra automaticamente na busca que acontece antes de cada resposta — com citação da fonte. Para usar seu vault do Obsidian, altere o valve `FOLDER` do filtro **Nous Files** no painel de administração.

### Geração de imagem local (opcional)

```powershell
powershell -ExecutionPolicy Bypass -File images\install-comfyui.ps1
```

Instala o ComfyUI, o PyTorch certo para a sua GPU e os modelos Flux.1 Schnell (~12 GB). Depois, selecione **Gerador de Imagem Local** no seletor de modelos e peça: *"crie uma logo dourada de uma coruja"*. A imagem aparece na conversa.

### Assistente de Email — IA local para sua caixa de entrada (opcional)

Conecte seu email (Gmail, Outlook, Yahoo) via `conectar-email.bat` ou pelo botão **✉ Assistente de Email** no card Recursos. O Nous vai:

- **Triar** cada email: Importante / Pode esperar / Promoção / Spam + resumo de 1 linha.
- **Resumir** a mensagem completa quando você abre.
- **Rascunhar uma resposta** em PT-BR educado, pronta para editar.
- **Enviar** somente após você revisar e confirmar — nunca envia automaticamente.

> **Privacidade:** seus emails são processados apenas pelo **modelo Ollama local**. Nenhum conteúdo sai da máquina, mesmo com Nuvem NVIDIA ativa. As credenciais ficam em `NousData/.email_account.json` (fora do git). Use uma **senha de aplicativo**, não a senha principal — revogável a qualquer momento.

---

### Pesquisa Profunda — pesquisa multi-etapas com fontes

Selecione **"Pesquisa Profunda (Nous)"** no dropdown de modelos e faça qualquer pergunta de pesquisa. O Nous:

1. Planeja 2–4 sub-perguntas para cobrir o tema completamente.
2. Busca a web (SearXNG local) para cada sub-pergunta.
3. Baixa e lê as páginas mais relevantes.
4. Escreve um relatório em markdown com citações `[n]` e uma seção **Fontes** com URLs clicáveis.

Tudo roda na sua máquina. Sem chave de API, sem nuvem. Requer o container SearXNG (sobe automaticamente quando o Docker está disponível).

### Comparar Modelos — teste cego A/B

Selecione **"Comparar Modelos (Nous)"** no dropdown e envie sua pergunta. Duas respostas anônimas (A e B) aparecem lado a lado — você vota na melhor antes de revelar os nomes dos modelos. Requer pelo menos dois modelos de chat instalados.

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

### Painel de recursos

O card **Recursos** (canto inferior esquerdo) mostra VRAM em tempo real, os modelos carregados na memória e os botões **"Parar modelos"** (libera a GPU na hora) e **"Baixar modelos"** (abre a Loja).

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
```

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
[Flux.1 Schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) (Apache-2.0).  
Marcas pertencem aos seus respectivos projetos.

## Licença

[MIT](LICENSE) © Nous. Contribuições são bem-vindas — abra uma issue ou um PR.
