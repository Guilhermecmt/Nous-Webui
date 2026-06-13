<div align="center">

<img src="branding/assets/nous_logo.png" width="120" alt="Nous">

# Nous

**Your own private AI — beautiful, local, and yours.**

Chat · Vision · Image generation · Web search — 100% on your PC.  
No cloud. No subscription. Your conversations never leave your machine.

[![version](https://img.shields.io/badge/version-2.3.0-c8962e)](CHANGELOG.md)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)
[![platform](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6)](#requirements)
[![local](https://img.shields.io/badge/100%25-local%20%26%20private-2ea44f)](#why-nous)

**English** · [Português](README.pt-BR.md)

<img src="docs/screenshots/hero-github.png" width="860" alt="Nous interface">

</div>

---

## Why Nous

**Nous** (Greek *νοῦς*, "mind") turns the best local-AI tooling into a finished product: it installs in two clicks, picks the right model for your computer, and runs everything in the background. No step requires technical knowledge.

What you get over an ordinary AI chat:

- **Real privacy.** The model runs on your computer. Conversations, files and memories stay with you — there is no server to send anything to.
- **It remembers you.** Nous learns durable facts (name, work, preferences) across conversations and uses them in the next ones. All stored locally.
- **It reads your notes.** Point it at your Obsidian vault or any notes folder and Nous brings the relevant passages into the conversation, with source citations.
- **Built-in Model Store.** Nous analyzes your hardware, recommends the ideal model and downloads it in one click — inside the app, with a progress bar.
- **Vision and images.** Drop a screenshot and ask about it; type *"create an image of…"* and it appears in the chat (ComfyUI + Flux, optional).
- **Optional web search** via DuckDuckGo, no API key.
- **Resource panel.** Live VRAM, loaded models, and a one-click button to free your GPU.
- **No terminal windows.** Opens from a shortcut, runs in the background, stops with "Parar Nous".

---

<div align="center">
<img src="docs/screenshots/philosophy-banner.png" width="860" alt="Nous — The Intelligence Engine">
</div>

---

## Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| OS       | Windows 10 / 11 | Windows 11 |
| RAM      | 8 GB | 16 GB+ |
| GPU      | none — runs on CPU | 8 GB+ VRAM |
| Disk     | 20 GB free | 30 GB+ |

> **No dedicated GPU?** Nous works on CPU — replies just take longer (1–2 min). The Model Store detects this and recommends lightweight models automatically.

---

## Install

> Two actions. Zero configuration.

1. Click the green **Code → Download ZIP** button at the top of this page and unzip it anywhere.
2. Open the folder and **double-click `instalar.bat`**. If Windows shows a security warning, choose **"More info → Run anyway"**.

The installer checks your hardware, installs Ollama, Python and the interface, applies the Nous identity and creates shortcuts — on the **Desktop** and in the **Start Menu**. When it finishes, Nous opens in your browser by itself.

---

## First run

**1. Create your account.** Any name, email and password — the account exists only on your machine, and the first one created is the administrator.

**2. Let the assistant work.** On first launch, Nous notices there is no AI model installed yet and shows a welcome screen with the **model recommended for your computer**. One click on **"Download and start"** and it handles the rest, showing progress.

**3. Chat.** When the download finishes, just start typing.

---

## AI models

The **Model Store** lives in the *Recursos* card (bottom-left) → **"Baixar modelos"** button. It shows a curated catalogue with:

- a **"Recommended for your machine"** badge on models that make good use of your hardware (GPU/RAM analysis is automatic);
- an **"Understands images"** badge on vision-capable models;
- plain-language descriptions, download size, and **1-click** install with a progress bar.

You can keep several models installed and switch between them in the selector at the top of the chat. For reference, a few catalogue highlights:

| Your machine | Suggested model | Download | Profile |
|--------------|-----------------|----------|---------|
| No dedicated GPU | Qwen 3.5 4B | ~3.4 GB | Light, fast on CPU, understands images |
| 8–12 GB GPU | Gemma 4 12B | ~7.6 GB | Chat, writing and vision — the sweet spot |
| 12–16 GB GPU | Qwen 3 14B | ~9.3 GB | Better reasoning, longer context |
| 20 GB+ GPU | Qwen 3 32B | ~20 GB | Quality on par with large cloud models |

Power users can install **any** model from [ollama.com/library](https://ollama.com/library) through the admin panel (Admin Panel → Settings → Models).

---

## Features

### Memory — Nous remembers you

As you chat, Nous identifies durable facts — name, city, work, preferences — and recalls them in later conversations. The **"O que o Nous sabe"** panel (brain button, bottom-right) lets you view, edit and delete every memory, and create **personas** with separate memory sets (work, studies, personal). Everything lives in `NousData`, on your disk.

### Files — Nous reads your notes

On first use, Nous creates the `Documents\Nous` folder. Any `.md` or `.txt` placed there automatically joins the search that runs before every reply — with source citations. To use your Obsidian vault, change the `FOLDER` valve of the **Nous Files** filter in the admin panel.

### Local image generation (optional)

```powershell
powershell -ExecutionPolicy Bypass -File images\install-comfyui.ps1
```

Installs ComfyUI, the right PyTorch for your GPU and the Flux.1 Schnell models (~12 GB). Then select **Gerador de Imagem Local** in the model selector and ask: *"create a golden owl logo"*. The image appears in the conversation.

### Voice conversation in Portuguese (optional)

Nous can listen and speak — entirely on your machine, no internet, no cloud API.

```
Double-click  ativar-voz.bat
```

Or open the **Recursos** panel → click **"🎙 Ativar voz em PT-BR"**. The panel downloads the Piper TTS engine (~30 MB) and the Brazilian Portuguese voice model (~60 MB). The Whisper speech-recognition model (~150 MB) downloads automatically on first use.

Once activated: click the **phone icon** in the chat header to enter hands-free voice mode — speak, Nous transcribes, replies, and reads the answer aloud in PT-BR.

> **100% local.** Audio and transcripts never leave your machine. Voice works even when using a cloud model in the chat — only the text goes to the cloud, not your voice.

---

### Nous Cloud — optional frontier models

Nous is local by default. To try state-of-the-art models (DeepSeek R1, Llama 3.3 70B, Kimi K2…) without a powerful GPU, connect it to NVIDIA's free hosted API:

1. Create a free key at [build.nvidia.com/models](https://build.nvidia.com/models) (no credit card).
2. Double-click **`ativar-nuvem.bat`**, paste the key, confirm.
3. Restart Nous — the cloud models appear in the selector.

> **Privacy preserved:** conversations with cloud models go to NVIDIA's servers, but your **personal memory is never sent** — Nous holds it back on those requests automatically. To switch everything off: `desativar-nuvem.bat`.

You can also plug in paid providers (GPT, Claude via OpenRouter) under Admin Panel → Settings → Connections. Without a key, nothing leaves your machine.

### Resource panel

The **Recursos** card (bottom-left) shows live VRAM, the models loaded in memory, and the **"Parar modelos"** (frees the GPU instantly) and **"Baixar modelos"** (opens the Store) buttons.

---

## Troubleshooting

**"Windows protected your PC" / "Unknown publisher"**  
Standard behaviour for unsigned software. Click **"More info" → "Run anyway"**.

**The shortcut didn't appear on the Desktop**  
Some antivirus tools block shortcut creation. Press the **Windows key** and type **Nous** — the Start Menu shortcut is always created. Alternative: double-click `iniciar.bat` in the Nous folder.

**The start screen doesn't show the Nous logo / says "Open WebUI"**  
Open Nous from the shortcut and press **Ctrl+Shift+R** in the browser. The identity is verified and re-applied automatically on every launch.

**It opens but there is no model to chat with**  
*Recursos* card → **"Baixar modelos"** → pick the recommended one. The welcome assistant also reappears as long as no model is installed.

**"Ollama is not running" or the chat doesn't reply**  
Open Nous from the shortcut (not by typing the address in the browser) — the shortcut starts all services. If it persists, click **"Parar modelos"** in the panel and open it again.

**The install failed / I want to start over**  
Double-click `desinstalar.bat` → option **[1] Safe removal** → run `instalar.bat` again. Conversations and notes are preserved.

**I forgot my password**  
From inside the Nous folder:
```powershell
python tools\reset-password.py --email you@example.com
```

---

## Uninstall

Double-click **`desinstalar.bat`**:

- **[1] Safe removal** *(recommended)* — removes the app and its Python environment. Keeps conversations, notes, Ollama and Python.
- **[2] Remove everything** — also deletes conversations and uninstalls Ollama/Python, **only** if Nous installed them. Pre-existing programs are never touched.

---

## Project layout

```
Nous WebUI/
├─ branding/    identity: logo, White & Gold theme, loader.js (panels), applier
├─ voice/       Voice in PT-BR: Piper TTS server + STT/TTS registration
├─ cloud/       Nous Cloud: opt-in NVIDIA NIM API registration
├─ files/       local file RAG: indexer + hybrid search
├─ history/     conversation-history RAG
├─ images/      image generation: ComfyUI installer, Flux models, chat Pipe
├─ memory/      personal memory: filter, panel API, personas
├─ monitor/     resource panel + Model Store (local service, port 8990)
├─ launchers/   background start/stop + .exe build
├─ installer/   one-click installer + Inno Setup script
├─ search/      web search (DuckDuckGo)
├─ tools/       capability check, backup, password reset, health check
└─ docs/        roadmap, screenshots
```

## Advanced usage

<details>
<summary>Developer options</summary>

### Hardware check

```powershell
powershell -ExecutionPolicy Bypass -File tools\check-system.ps1
```

Prints **CAPABLE (GPU)**, **CAPABLE (CPU)** or **NOT CAPABLE**, with details and recommendations.

### Command-line install

```powershell
powershell -ExecutionPolicy Bypass -File installer\install-nous.ps1 -WithModel -Model qwen3:14b
```

Idempotent. `-WithImages` also installs the image engine; `-Force` reinstalls. The Open WebUI version is **pinned** in the script (`$OPENWEBUI_PIN`) — bump the pin deliberately, after testing.

### Manual install

```powershell
# 1) Ollama  →  https://ollama.com
# 2) Python 3.11 + Open WebUI
py -3.11 -m venv $env:USERPROFILE\open-webui
& $env:USERPROFILE\open-webui\Scripts\python.exe -m pip install open-webui
# 3) Nous identity
& $env:USERPROFILE\open-webui\Scripts\python.exe branding\apply_branding.py
# 4) Launch
powershell -ExecutionPolicy Bypass -File launchers\start-nous.ps1
```

### Tools

```powershell
tools\backup-data.ps1                              # data backup, keeps 10 newest
tools\health-check.ps1                             # integrity check
python tools\reset-password.py --email you@example.com
```

### Model Store service (port 8990)

```
GET  /stats        VRAM + loaded models
GET  /hardware     GPU, VRAM, RAM and machine tier
GET  /catalog      curated catalogue, ranked for this machine
POST /pull         {"model":"tag"} — starts a background download
GET  /pull/status  ?model=tag — live progress
POST /unload       unloads models from VRAM
```

### Inno Setup installer (.exe)

`installer\nous-setup.iss` builds `dist\Nous-Setup.exe` with `ISCC.exe installer\nous-setup.iss`.

</details>

---

<div align="center">
<img src="docs/screenshots/wallpaper.png" width="860" alt="Nous — Your Personal AI Sovereign">
</div>

---

## Built on

[Open WebUI](https://github.com/open-webui/open-webui) ·
[Ollama](https://ollama.com) ·
[ComfyUI](https://github.com/comfyanonymous/ComfyUI) ·
[Flux.1 Schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) (Apache-2.0).  
All trademarks belong to their respective projects.

## License

[MIT](LICENSE) © Nous. Contributions welcome — open an issue or a PR.
