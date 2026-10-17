# Plano de Execução — "Nous Voz" (conversa por voz 100% local em PT-BR) — v2.3.0

> Documento de planejamento para execução pelo Sonnet. Estudo feito em 2026-06-13.
> Objetivo: dar ao Nous **conversa por voz natural, 100% local e em português** —
> falar com o Nous e ouvir a resposta, sem internet, rodando até em CPU.
> É o maior diferencial inédito identificado na análise competitiva
> (ver memória `competitive-landscape`): os
> concorrentes (Cherry/Open WebUI: voz básica, inglês, instalação técnica)
> entregam voz conversacional em PT-BR empacotada para leigos.

---

## 1. Princípio que define a arquitetura (não re-discutir)

**Não construir UI de voz do zero.** O Open WebUI **já tem** o modo "Call"
(conversa hands-free: microfone → resposta falada, com detecção de fim de fala)
e suporta STT local (Whisper) + TTS plugável. A configuração de áudio vive como
*PersistentConfig* no `webui.db` (tabela `config`) — variáveis de ambiente só
valem no PRIMEIRO boot. Logo, a integração certa segue o padrão Nous já usado:
**escrever a config de áudio direto no banco, idempotente, a cada boot**
(espelhar `cloud/register_nvidia.py` e `images/register_pipe_auto.py`).

O trabalho do Nous é: (a) subir motores locais de qualidade em PT-BR, (b)
registrar no banco para o Open WebUI usá-los, (c) baixar os assets de forma leiga
(com progresso, reusando a UX da Loja de Modelos).

## 2. Decisões de design (já tomadas)

1. **STT = faster-whisper** (já suportado pelo Open WebUI como "Local Whisper").
   Modelo escolhido por hardware: GPU → `medium` (PT muito bom); CPU → `small`
   ou `base` (equilíbrio latência/qualidade). Idioma forçado em `pt`.
2. **TTS = Piper** (rhasspy/piper) com voz **pt_BR** — leve, ONNX, rápido em CPU,
   offline, com vozes brasileiras reais (ex.: `pt_BR-faber-medium`). É o melhor
   ajuste para leigo + CPU + português. (Kokoro/MeloTTS são focados em inglês.)
3. **Ponte TTS = servidor OpenAI-compatível local.** Os motores de TTS que o
   Open WebUI aceita são: WebAPI(browser), OpenAI, ElevenLabs, Azure, Transformers.
   Piper não é nenhum deles diretamente → subir um micro-servidor local que expõe
   `POST /v1/audio/speech` (contrato OpenAI) e por trás chama o Piper. O Open WebUI
   é configurado com TTS engine = `openai`, base_url = `http://127.0.0.1:8994/v1`.
   Mesmo padrão de serviço local do `monitor` (8990) e da `memory API` (8993).
   **Porta sugerida: 8994.**
4. **Opt-in com download leve (princípio "setup leve" v1.2).** Os assets (binário
   do Piper ~ alguns MB, voz pt_BR ~60 MB, modelo Whisper ~150–500 MB) **não** vão
   no instalador. Botão "Ativar conversa por voz" baixa tudo com barra de progresso
   (reusar a UX `/pull` da Loja de Modelos). Enquanto não ativado, nada muda.
5. **Privacidade reforçada.** Áudio e transcrição **nunca saem da máquina**.
   Em modelo de nuvem (id com `/`), a voz continua funcionando (STT/TTS são locais),
   mas vale um aviso na UI de que o TEXTO da conversa vai para a nuvem como hoje.
6. **PT-BR por padrão.** STT em `pt`, voz TTS pt_BR, rótulos da UI em português.

## 3. Etapas de execução (em ordem)

### Fase 0 — Verificar a versão instalada (ANTES de codar)
- Confirmar no Open WebUI pinado (`open-webui==0.9.6`) os nomes/chaves reais da
  config de áudio na tabela `config` (procurar em
  `%USERPROFILE%\open-webui\Lib\site-packages\open_webui\config.py`:
  `AUDIO_STT_ENGINE`, `AUDIO_STT_MODEL`, `AUDIO_TTS_ENGINE`,
  `AUDIO_TTS_OPENAI_API_BASE_URL`, `AUDIO_TTS_VOICE`, etc.). O formato (aninhado
  `audio.stt.*` vs plano) muda entre versões — inspecionar o JSON salvo num
  `webui.db` real, como foi feito no plano da Nuvem.
- Confirmar que o **modo "Call"** existe e está habilitado nessa versão (botão de
  telefone no chat). Se a UI mudou, ajustar; o fallback é o botão de microfone
  simples (STT) + autoplay da resposta (TTS).

### Fase 1 — Motores locais

**1.1 `voice/nous_tts_server.py`** (servidor OpenAI-compatível p/ Piper):
- stdlib + (aiohttp já no venv) ou FastAPI se já presente; espelhar o estilo do
  `monitor/nous_monitor.py` (CORS local, porta fixa 8994, singleton por porta).
- Rota `POST /v1/audio/speech` body `{model, input, voice, response_format}` →
  chama o binário do Piper com a voz pt_BR → devolve áudio (wav/mp3). Cachear a
  voz carregada em memória entre requisições (latência).
- Rota `GET /health` para o health-check.
- Resolver os assets em `NousData\voice\` (binário Piper + arquivo da voz).

**1.2 `voice/install-voice.ps1`** (espelhar `images/install-comfyui.ps1`):
- Baixar binário do Piper (Windows) + voz `pt_BR-faber-medium` (HF
  rhasspy/piper-voices) para `NousData\voice\`. Espelhos abertos (sem login),
  como o VAE do Flux.
- Baixar o modelo Whisper escolhido por hardware (o Open WebUI baixa sozinho na
  1ª transcrição, mas pré-baixar evita a espera no primeiro uso — decidir: deixar
  o Open WebUI baixar sob demanda é mais simples; pré-baixar é melhor UX).
- Idempotente: pular o que já existe; `-Force` rebaixa.

### Fase 2 — Registro no banco

**2.1 `voice/register_voice.py`** (espelhar `cloud/register_nvidia.py`):
- Resolver `webui.db` igual aos outros register_*.
- Ler a config (linha mais recente), garantir:
  - STT: engine = local whisper, modelo = (por hardware), idioma = `pt`.
  - TTS: engine = `openai`, base_url = `http://127.0.0.1:8994/v1`, api_key dummy
    (`nous-local`), voice = nome da voz pt_BR, autoplay de resposta = on.
- **Só registrar se os assets de voz existirem** em `NousData\voice\` (ou seja,
  se o usuário ativou). Se não existirem: não tocar na config (não quebrar quem
  não usa voz). Idempotente; não mexer em outras configs do usuário.

**2.2 `launchers/start-nous.ps1`**: adicionar `Start-VoiceServer` (sobe o 8994 se
os assets existem) e `Register-Voice`, chamadas nos DOIS pontos de boot, junto de
`Register-Memory`/`Register-Cloud`/`Ensure-Branding`.

### Fase 3 — UX de ativação (sem terminal)

**3.1 `branding/nous-loader.js`** — botão "Ativar conversa por voz" no card
Recursos (abaixo de "Baixar modelos"), mesmo estilo dourado:
- Ao clicar: dispara o download dos assets via uma nova rota no monitor
  (`POST /voice/install` + `GET /voice/status`) OU via um `.bat` fino — preferir
  rota no monitor para mostrar a MESMA barra de progresso da Loja de Modelos.
- Ao concluir: "Pronto! Recarregue a página e toque no ícone de telefone no chat
  para conversar por voz." Selo "Voz ativada".
- Detectar se já ativado (assets presentes via `GET /voice/status`) e esconder o
  botão / mostrar "Voz ativada".

**3.2 `ativar-voz.bat` na raiz** (opcional, fallback sem UI) — clique duplo que
roda `install-voice.ps1` + `register_voice.py`, no padrão de `ativar-nuvem.bat`.

### Fase 4 — Saúde, docs e release

**4.1 `tools/health-check.ps1`**: item INFORMATIVO "Voz: ativa / inativa" —
se ativa, `GET 127.0.0.1:8994/health` com timeout curto; nunca falhar por causa
da voz.

**4.2 Docs**:
- `README.md` + `README.pt-BR.md`: seção "Conversa por voz (opcional)" — o que é,
  como ativar, **100% local / nada sai da máquina**, roda em CPU (mais lento).
- `docs/ROADMAP.md`: marcar como entregue.
- `CHANGELOG.md`: entrada `[2.3.0]`; atualizar `VERSION`.

## 4. Critério de pronto (verificação)
1. Sem ativar: boot normal, nenhum serviço de voz no ar, config de áudio intocada.
2. "Ativar conversa por voz" baixa os assets com progresso real e termina.
3. Após recarregar: modo Call funciona — falo em português, o Nous transcreve
   (Whisper local), responde (modelo local) e **fala a resposta em pt_BR** (Piper).
4. Tudo offline: desligar a internet e a conversa por voz continua funcionando
   com modelo local.
5. Rodar `register_voice.py` duas vezes não duplica config (idempotência).
6. Latência aceitável em CPU (medir; se ruim, cair para Whisper `base` + comunicar
   "estou ouvindo..." na UI para gerenciar expectativa).

## 5. Riscos e armadilhas
- **Formato da config de áudio** muda entre versões do Open WebUI — inspecionar a
  0.9.6 antes de escrever (Fase 0). Maior risco do plano.
- **Latência em CPU**: Whisper `medium` é pesado sem GPU; usar `small`/`base` em
  CPU e gerenciar expectativa na UI ("ventilador acelerar é normal").
- **Microfone no navegador**: `http://localhost` é *secure context*, então o
  `getUserMedia` funciona — mas o usuário precisa permitir o mic uma vez.
- **Qualidade da voz Piper**: testar `faber` vs `edresson`; escolher a mais natural.
- **Modo Call ausente/alterado** na versão pinada → fallback botão de microfone.
- **Concorrência sqlite**: registrar com o servidor de pé funciona (os outros
  register_* já fazem); config só vale após reinício do servidor — a UX avisa.

## 6. Fora de escopo (não fazer agora)
- Clonagem de voz / voz personalizada do usuário.
- Interrupção em tempo real (barge-in) além do que o modo Call já faz.
- Wake word ("Ok Nous") — fica para uma fase futura junto com a Bandeja do Sistema.
- Voz em outros idiomas — PT-BR primeiro; estrutura deixa o caminho aberto.
