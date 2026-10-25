# Nous · Geração de imagens (ComfyUI + Flux) — RX 9070 XT, 100% local

Geração de imagens **local**, integrada ao chat do Nous (Open WebUI), com
**detecção automática de intenção**: *"crie uma logo dourada de uma coruja"* gera
a imagem no **Flux** via **ComfyUI** e mostra **dentro da conversa**; qualquer
outra pergunta vai normalmente para o **Gemma**.

```
Chat (modelo "Nous") ─▶ Pipe ─▶ intenção de imagem? ─▶ ComfyUI ─▶ Flux ─▶ imagem inline
                              \▶ senão ───────────────▶ Ollama (gemma4:12b) ─▶ texto
```

## ✅ Status (testado em 25/10/2026, Windows 11, RX 9070 XT 16 GB)
- **Caminho AMD: ROCm NATIVO no Windows, sem ZLUDA e sem instalar o HIP SDK.** O
  PyTorch ROCm (`torch 2.13 +rocm7.13`, índice `rocm.nightlies.amd.com/v2/gfx120X-all`)
  traz as bibliotecas da AMD dentro das próprias rodas do pip. O GPU aparece como
  `cuda:0 AMD Radeon RX 9070 XT : native`. É o que o `install-comfyui.ps1` faz sozinho
  quando detecta uma RX 9000 (RDNA4). Outras Radeon caem em CPU (use `-Torch rocm` para tentar).
- **Instalação do zero pelo script:** ~13 min (a maior parte é o download), ~18 GB em
  `%USERPROFILE%\ComfyUI` (venv com PyTorch ~5 GB + modelos ~12 GB + ComfyUI). Rodar de novo
  leva segundos (pula o que já existe) e o download dos modelos retoma de onde parou.
- **Geração (Flux Schnell Q4, 1024x1024, 4 passos):** 1ª imagem com a placa livre ~34 s
  (carrega ~11 GB). Com **outro modelo de linguagem na VRAM** (ex.: um de 4-5 GB) o Flux
  não cabe e vaza para a RAM: 50-70 s (13-18 s por passo). Por isso o Pipe descarrega o
  Ollama antes de gerar quando faltam ~12 GB livres e manda o ComfyUI soltar a VRAM depois.
- ComfyUI em `http://localhost:8188`. Ocioso por 10 min, o Monitor o encerra sozinho
  (`NOUS_COMFY_IDLE_MIN`, 0 desliga); o próximo pedido de imagem o sobe de novo (~20 s).
- Pipe registrado e ativo no Open WebUI → aparece no seletor de modelos como
  **"Gerador de Imagem Local"**; as imagens geradas entram na **Galeria** do Nous.
- O **Editor de fotos** (remover fundo) NÃO usa o ComfyUI: roda o U2-Net no Monitor, na CPU.

> Observação honesta sobre qualidade: o **Flux Schnell** (4 passos, Apache-2.0) é
> rápido mas tem **aderência limitada** a prompts específicos e **erra texto**.
> Para resultados mais fiéis use prompts em inglês, ou troque para **Flux Dev**
> (mais passos/qualidade, porém licença **não-comercial** e mais pesado para 16 GB).

## Como usar (no dia a dia)
1. **Suba o ComfyUI** (precisa estar no ar para gerar imagem):
   ```powershell
   powershell -ExecutionPolicy Bypass -File images\start-comfyui.ps1
   ```
   (Sobe em segundo plano, com `PYTHONUTF8=1`.)
2. No Nous, selecione o modelo **"Nous"** no topo do chat.
3. Peça uma imagem: *"crie uma logo dourada de uma coruja"*, *"gere uma paisagem
   futurista"*. Para texto, é só perguntar normalmente.

> ⚠️ Se o ComfyUI **não** estiver no ar, o Pipe responde com um aviso de erro em
> vez da imagem. Rode o `start-comfyui.ps1` antes.

## Como foi instalado (reproduzível em outra máquina RX 9000)
Pré-requisitos: **git** e **Python 3.11** (o HIP SDK da AMD não é necessário).
O jeito mais simples é o script, que faz todos os passos abaixo:
`powershell -ExecutionPolicy Bypass -File images\install-comfyui.ps1`.

```powershell
# 1) ComfyUI (base)
git clone https://github.com/comfyanonymous/ComfyUI "$env:USERPROFILE\ComfyUI"
cd "$env:USERPROFILE\ComfyUI"

# 2) venv + PyTorch ROCm NATIVO para RDNA4 (gfx120X) - este e' o pulo do gato
py -3.11 -m venv venv
venv\Scripts\python -m pip install --upgrade pip
venv\Scripts\pip install --pre torch torchvision torchaudio `
  --index-url https://rocm.nightlies.amd.com/v2/gfx120X-all/
venv\Scripts\pip install -r requirements.txt   # nao sobrescreve o torch ROCm

# 3) no GGUF (Flux quantizado) e suas deps
git clone https://github.com/city96/ComfyUI-GGUF custom_nodes\ComfyUI-GGUF
venv\Scripts\pip install -r custom_nodes\ComfyUI-GGUF\requirements.txt

# 4) modelos do Flux Schnell (~12 GB)
powershell -ExecutionPolicy Bypass -File "<repo>\images\download-models.ps1" -ComfyUI "$env:USERPROFILE\ComfyUI"
```
> O `download-models.ps1` ja usa um espelho ABERTO para o VAE (o repo oficial da
> Black Forest Labs exige login). Modelos: `flux1-schnell-Q4_K_S.gguf` (unet),
> `t5xxl_fp8_e4m3fn.safetensors` + `clip_l.safetensors` (clip), `ae.safetensors` (vae).

Iniciar: `images\start-comfyui.ps1`  → http://localhost:8188
(o Nous também sobe o ComfyUI sozinho quando você pede uma imagem).
O fork `ComfyUI-Zluda`, se já estiver em `%USERPROFILE%`, continua sendo reconhecido.

## O Pipe (integração com o chat)
`nous_image_pipe.py` é um **Pipe** do Open WebUI (já registrado aqui como função
"Nous"). Ele detecta intenção de imagem (PT/EN), gera no ComfyUI e devolve a
imagem inline; o resto encaminha ao `gemma4:12b`.

Para (re)instalar manualmente: Open WebUI → **Admin → Settings → Functions → "+"**
→ cole `nous_image_pipe.py` → salve e habilite. Valves úteis: `COMFYUI_URL`
(padrão `http://localhost:8188`), `STEPS`, `WIDTH/HEIGHT`, `STORAGE_DIR`,
`USE_LLM_CLASSIFIER`, `NEEDED_VRAM_GB` (descarrega o Ollama antes de gerar se
faltar VRAM; 0 desliga) e `FREE_VRAM_AFTER` (o ComfyUI solta a VRAM depois da imagem).

## Modularidade (adicionar modelos sem mexer no chat)
Troque/adicione um workflow do ComfyUI (formato API) e aponte a valve
`WORKFLOW_PATH`, ou adicione ao dicionário do Pipe. **SDXL, Flux Dev, ControlNet,
img2img, inpainting** entram assim — o frontend (o chat) nunca muda.

## Arquivos
```
images/
├─ README.md                este guia
├─ nous_image_pipe.py       Pipe do Open WebUI (detecção + roteamento)
├─ start-comfyui.ps1        sobe o ComfyUI (PYTHONUTF8) em segundo plano
├─ download-models.ps1      baixa o Flux Schnell (com espelho aberto p/ o VAE)
└─ workflows/
   └─ flux_schnell.json     workflow ComfyUI (Flux Schnell, formato API)
```
