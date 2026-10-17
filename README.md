<div align="center">

<img src="branding/assets/nous_logo.png" width="120" alt="Nous">

# Nous

**Your own private AI — beautiful, local, and yours.**

Chat · Documents · Agenda · Email · Vision · Images · Research — 100% on your PC.  
No cloud. No subscription. Your conversations never leave your machine.

[![version](https://img.shields.io/badge/version-2.10.0-c8962e)](CHANGELOG.md)
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
- **It reads your notes.** Point it at your Obsidian vault or any notes folder and Nous brings the relevant passages into the conversation.
- **Built-in Model Store.** Nous analyzes your hardware, recommends the ideal model and downloads it in one click — inside the app, with a progress bar.
- **Vision and images.** Drop a screenshot and ask about it; type *"create an image of…"* and it appears in the chat (ComfyUI + Flux, optional).
- **Optional web search** via DuckDuckGo, no API key.
- **Documents with AI at your side.** Write a letter, a résumé or a school paper and ask to *fix*, *make it formal*, *shorter* or *turn bullets into prose*: every change shows up struck through for you to accept or reject. Downloads as Word or PDF.
- **Deep Research.** Select "Pesquisa Profunda (Nous)" in the model dropdown — Nous plans, searches the web in multiple steps, downloads the relevant pages and writes a full report with numbered citations and a source list. 100% local.
- **Blind model comparison.** The same question to 2–4 models, vote before the names are revealed, and a leaderboard of which one suits you best.
- **Email assistant (optional).** Connect your inbox and Nous triage, summarizes and drafts replies — all on your machine. Your emails only reach the local Ollama model, never the cloud. Sending always requires explicit confirmation.
- **Agenda, reminders and tasks.** *"Remind me to pay the power bill Friday at 9am"* becomes a Windows notification at the right time; tasks like a "good morning with my agenda and emails" run on their own on schedule.
- **It learns your way.** Say *"learn this"* and Nous saves the steps for next time — your writing style too.
- **Reads photos, bills and PDFs.** Text from screenshots and documents read on your machine, Brazilian boletos with amount and due date checked, PDF forms filled and signed.
- **Photo editor and Gallery.** Remove backgrounds, crop and adjust — or just type *"remove the background and crop it square"* (Portuguese phrases).
- **Resource panel.** Live VRAM, loaded models, a one-click button to free your GPU, and a **Diagnostics** view that tells you what is working.
- **No terminal windows.** Opens from a shortcut, runs in the background, stops with "Parar Nous".

### What's new in 2.10

- **No login:** Nous opens straight into the chat, like any other program on your PC — no account or password to remember. It only accepts connections from the computer itself, so your Windows password is what protects it. Your existing conversations are kept.
- **"Seu Nous" panel:** on the right, the owl inside a ring shows how much of your GPU is in use, followed by the private chat switch, upcoming reminders, what Nous knows about you and every tool by name. Closed, only the owl stays in the corner.
- **⌨ Nous Code:** an IDE with a local-AI agent, in its own window: the VS Code editor (Monaco), files and tabs, search, Git and a terminal, with the agent alongside. Ask, for example, "the tests are failing, fix them": it reads the code, edits files and runs commands step by step; every change waits for your OK with the diff on screen, and can be undone. Open it from the **Nous Code** shortcut or **Código** in the panel. Needs Node.js 22.18 or newer.
- **New home screen:** *"Boa tarde, Name"*, a Nous tip on every visit and a **Conversa privada** (private chat) button — the chat is not kept in history and never becomes memory.

### What's new in 2.9

- **📝 Documents:** write next to the chat and ask the AI to fix, formalize, shorten, organize or continue. It **only suggests** — each change appears struck through/underlined for you to accept or reject. Select a passage to change just that part. Autosaves, keeps versions and downloads as **Word, PDF or Markdown**.
- **Replies:** **✂ Mais curto** (shorter), **🙂 Mais simples** (simpler) and **📝 Documento** (open the reply to edit and download) buttons.
- **Memory:** **⬆ Import** facts from a résumé, an "about me" text or your ChatGPT memories (you pick what to keep) and **⬇ Export** everything to a file.
- **Model Store:** download **any model** from Ollama or Hugging Face by name or link — Nous checks the size and whether it fits your machine first — and **"What if I had another machine?"** shows what would run on a different GPU.
- **Deep Research:** reports download as **PDF or Word**.

Earlier versions in the [CHANGELOG](CHANGELOG.md).

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

Nous is installed to `%LOCALAPPDATA%\Programs\Nous`, so the downloaded folder can be deleted afterwards. If a step fails, the installer shows the reason in red instead of saying "Pronto!".

---

## First run

**1. Just open it.** There is no account or password: Nous opens straight into the chat. If several people share the computer, create one account each in **Admin Panel › Users** — with two or more accounts the login screen comes back and each person sees only their own chats.

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

For **any other model**, type its name (`qwen3:8b`) or paste a link from [ollama.com](https://ollama.com/library) or a Hugging Face GGUF repository into the Store's **"Outro modelo"** field and click **Conferir**: Nous reads the size from the registry (nothing is downloaded), tells you whether it fits your GPU and disk, and only then offers **Baixar**.

Thinking about a new computer? **"E se eu tivesse outra máquina?"** simulates another GPU and amount of RAM and shows what would run, and how fast.

---

## Features

### Memory — Nous remembers you

As you chat, Nous identifies durable facts — name, city, work, preferences — and recalls them in later conversations. The **"O que o Nous sabe"** panel (brain button, bottom-right) lets you view, edit and delete every memory, and create **personas** with separate memory sets (work, studies, personal). Everything lives in `NousData`, on your disk.

Identity and health facts (name, allergies, medication) are **pinned** and join every conversation; pin others with 📌. Past 30 memories, Nous brings only the pinned ones, the most recent and those related to the question. **🧹 Organizar memórias** finds duplicates and proposes merging them — nothing changes without your OK.

**⬆ Importar** brings in what you have already written about yourself: a résumé, an "about me" text (.txt, .md, .docx, .pdf) or the list of ChatGPT memories pasted into the box. Nous proposes the facts, flags the ones it already knew, and you choose what to keep. **⬇ Exportar** downloads every memory to a file (backup or another computer), which Import brings back exactly, pinned ones included.

### Files — Nous reads your notes

On first use, Nous creates the `Documents\Nous` folder. Any `.md` or `.txt` placed there automatically joins the search that runs before every reply. Search uses **granite-embedding** (multilingual, understands Portuguese), downloaded automatically; indexes rebuild themselves if the model changes. To use your Obsidian vault, change the `FOLDER` valve of the **Nous Files** filter in the admin panel.

### Local image generation (optional)

```powershell
powershell -ExecutionPolicy Bypass -File images\install-comfyui.ps1
```

Installs ComfyUI, the right PyTorch for your GPU and the Flux.1 Schnell models (~12 GB). Then select **Gerador de Imagem Local** in the model selector and ask: *"create a golden owl logo"*. The image appears in the conversation.

### Email assistant — local AI for your inbox (optional)

Connect your email (Gmail, Outlook, Yahoo) via `conectar-email.bat` or the **✉ Assistente de Email** button in the Recursos panel. **Several accounts** can be connected, with one as default. Nous will:

- **Triage** each email: Importante / Pode esperar / Promoção / Spam + 1-line summary.
- **Summarize** the full message when you open it — **attachments** included (PDF, spreadsheet, image).
- **Draft a reply** in polished PT-BR, ready for you to edit, or **schedule** it.
- **Write from the chat:** *"manda um e-mail para a Ana dizendo que atraso 10 minutos"* — the recipient comes from **contacts learned** from your mail (vCard import/export) and the text becomes a draft.
- Meeting **invites** go to the Agenda in one click; the **Newsletters** tab helps you unsubscribe.
- **Send** only after you review and confirm — no auto-sending ever.

> **Privacy:** your emails are processed only by the **local Ollama model**. No email content ever leaves your machine, even if you have NVIDIA Cloud active. Credentials are stored in `NousData/.email_accounts.json` (never committed to git). Use an **app password**, not your main password — revocable at any time.

---

### Deep Research — multi-step web research with sources

Select **"Pesquisa Profunda (Nous)"** in the model dropdown and ask any research question. Nous:

1. Plans 2–4 sub-questions to cover the topic fully.
2. Searches the web (SearXNG, running locally) for each sub-question.
3. Downloads the most relevant pages and reads them.
4. Writes a structured markdown report with inline citations `[n]` and a **Fontes** (Sources) section with clickable URLs.
5. Saves a **visual report** (table of contents, clickable citations, source cards) to the **Recursos › Relatórios** library, linked at the end of the answer. Each report there also downloads as **PDF** or **Word**.

With small models (up to ~10B) it searches less and answers directly when the question is simple; vague questions get suggestion buttons, and you can follow up on the last report (*"e no Brasil?"*).

All computation happens on your machine. No API key, no cloud. Requires the SearXNG container (runs automatically when Docker is available).

### Blind model comparison and scoreboard

**Recursos › ⚖ Comparar modelos**: the same question to **2 to 4 models**, one at a time (each gets the whole GPU), with time and tokens/s for every answer. Blind by default: you vote for the best one and only then see the names. Votes build a **scoreboard** with each model's win rate and average speed on this machine.

In the chat, **"Comparar Modelos (Nous)"** in the dropdown still runs the Arena A/B duel. Both need at least two chat models installed.

---

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

### Agenda — notes, reminders and calendar

Ask in the chat: *"me lembre de pagar a luz sexta às 9h"* (remind me to pay the power bill Friday at 9), *"marca dentista dia 20 às 14h"*, *"o que eu tenho amanhã?"*. The local model extracts the request and saves it; at the right time Nous shows a **Windows notification** (even with the browser closed) and an in-app card.

**Recursos › 📅 Agenda** has four tabs: **Hoje** (overdue + next 7 days), **Notas** (search, pin, complete, repeat), **Calendário** (month view, events with advance alerts, `.ics` import/export) and **Tarefas**. Google Calendar, Outlook or iCloud can be added by pasting the calendar's **iCal** address (read-only, refreshed hourly).

Notes support **checklists** (`- [ ] item`) and a **💬 usar no chat** button. Under **⚙ Avisos**, reminders can also reach your **phone** (free ntfy app, no sign-up) and/or your **email**. If Nous saved something wrong from the chat, the **↩ Desfazer** button in the reply removes it. Dates and times (*"sexta às 9h"*, *"daqui a 2 horas"*, *"dia 20"*) are parsed by rules, not guessed by the model. Open WebUI's native Calendar and Automations are hidden so there aren't two of each.

### Scheduled tasks — Nous works on its own

In **Agenda › Tarefas**: a morning briefing with today's agenda and emails, a weekly web research, an evening inbox summary. Tasks run on schedule even with the browser closed; the result becomes a note, a notification and, optionally, an email to yourself. A task can **chain** another (the first result becomes the second one's context) and waits a few minutes while you are using the GPU.

### Skills — Nous learns how you like things done

After getting something right in a conversation, say **"aprenda isso"** ("learn this"). Nous distills the procedure into a skill (a readable `.md` file in `NousData\skills`) and applies it to similar requests later. **Recursos › 🧠 Habilidades** lets you review, edit, create and import `SKILL.md` files from a GitHub link. **✍ Ensinar meu jeito de escrever** reads samples of your writing and stores your style, applied whenever you ask Nous to write something.

### Documents — write with AI at your side

**Recursos › 📝 Documentos** (or *"abre meus documentos"* in the chat). Write a letter, a résumé, a school paper or a post — or open a `.docx`, `.pdf`, `.txt` or `.md` file. Below the text are one-click requests: **Corrigir português** (fix), **Mais formal**, **Mais simples**, **Mais curto**, **Tópicos em texto** (bullets to prose), **Organizar com títulos** and **Continuar escrevendo**, plus a box to ask in your own words.

Empty document? Pick a **ready template** (formal letter, résumé, work email, complaint, meeting minutes) or **✨ Escrever com a IA**: describe what you need and review the draft.

The AI never writes straight into the document: each change appears **struck through (before) and underlined (after)** with ✓ and ✕. Review shows *"suggestion 2 of 7"*; **Enter** accepts, **Delete** rejects and Nous moves to the next one — or use **Accept all** / **Reject all**. After applying, the notice offers **Undo**. While the AI works you watch the text arrive **live**; during review, **❓ Por quê?** (or the **?** key) explains the suggestion. In **🕘 Versões**, clicking a version shows what would change before you go back. If you **select a passage** first, only that part changes. Before each accepted change Nous keeps a **version** (also every 10 minutes of writing), and you can go back to any of them.

Documents autosave to `NousData\documentos`. **⬇ Baixar** produces **Word (.docx)**, **PDF** or **Markdown**; **💬 Usar no chat** takes the text into the conversation. In chat replies, the **📝 Documento** button goes the other way. Everything runs on the local model.

### Chat utilities

- **YouTube:** paste a link and ask for a summary — Nous reads the captions and answers with timestamps.
- **Weather:** *"vai chover amanhã em Curitiba?"* — Open-Meteo forecast (free, no key).
- **Read images and bills:** send a photo of a document, a screenshot or a Brazilian *boleto* — Nous reads the text locally (OCR), even with a model without vision. Boletos come out with bank, amount and due date, checked against the check digit.
- **PDF forms** (**Recursos › 📄 Formulários**): lists the fields of a fillable PDF, suggests what it already knows about you and signs with your saved signature.
- **Long conversations:** when a chat outgrows the model's context, Nous summarizes the beginning on its own and keeps the details.
- **Tailored replies:** under each reply, **✂ Mais curto** and **🙂 Mais simples** ask for a shorter or simpler rewrite, and **📝 Documento** opens the reply in Documents.
- **Chat control:** *"abre minha agenda"*, *"tema escuro"*, *"libera a placa de vídeo"*, *"abre a galeria"*. When there are choices, the reply shows **buttons**; and Nous checks that what the model claims to have done (*"anotei"*, *"rascunho pronto"*) really happened.

### Photo editor and Gallery

**Recursos › 🖼 Editor de fotos**, or the **"✎ Editar"** chip over chat images. Crop (free, 1:1, 4:3, 16:9, 9:16), rotate, flip, light/color, filters, resize, undo/redo, download PNG/JPG or copy. **Remove background** runs a 4.5 MB U²-Net model locally, downloaded on first use. In **Diga o que fazer**, just write it: *"tira o fundo, deixa mais claro e corta quadrado"* (works without an AI model).

The **Gallery** collects generated images: favorites ★, albums 📁, zoom, recycle bin and ✎ to open an image in the Editor.

### Resource panel and diagnostics

The **Recursos** card (bottom-left) shows live VRAM, the models loaded in memory, and the **"Parar modelos"** (frees the GPU instantly) and **"Baixar modelos"** (opens the Store, now with an **estimated speed** per model on your GPU) buttons, plus shortcuts to Agenda, Email, Skills, Reports, Documents, Gallery, Editor, PDF forms and Compare models.

**🩺 Diagnóstico** answers *"what is working?"*: every part of Nous with ✓/✗ and what to do. It also holds **on-screen privacy** (CPF, card numbers, passwords and keys are blurred in chats until clicked) and **"Ver as dicas de novo"** — each panel shows a short tip the first time it opens.

---

## Troubleshooting

**"Windows protected your PC" / "Unknown publisher"**  
Standard behaviour for unsigned software. Click **"More info" → "Run anyway"**.

**The shortcut didn't appear on the Desktop**  
Some antivirus tools block shortcut creation. Press the **Windows key** and type **Nous** — the Start Menu shortcut is always created. Alternative: double-click `iniciar.bat` in `%LOCALAPPDATA%\Programs\Nous`.

**The start screen doesn't show the Nous logo / says "Open WebUI"**  
Open Nous from the shortcut and press **Ctrl+Shift+R** in the browser. The identity is verified and re-applied automatically on every launch.

**It opens but there is no model to chat with**  
*Recursos* card → **"Baixar modelos"** → pick the recommended one. The welcome assistant also reappears as long as no model is installed.

**"Ollama is not running" or the chat doesn't reply**  
Open Nous from the shortcut (not by typing the address in the browser) — the shortcut starts all services. If it persists, click **"Parar modelos"** in the panel and open it again.

**The install failed / I want to start over**  
Double-click `desinstalar.bat` → option **[1] Safe removal** → run `instalar.bat` again. Conversations and notes are preserved.

**I want the login screen back**  
Create an empty file named `.exigir_login` inside `%USERPROFILE%\NousData` and open Nous again. Your account goes back to the email and password it had before. Delete the file to remove the login again.

**I forgot my password** (only with the login on)  
From `%LOCALAPPDATA%\Programs\Nous`:
```powershell
python tools\reset-password.py --email you@example.com
```

---

## Uninstall

Go to **Settings → Apps → Installed apps**, find **Nous** and click **Uninstall** (or double-click `desinstalar.bat` in `%LOCALAPPDATA%\Programs\Nous`):

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
├─ search/      web search + Deep Research Pipe (SearXNG + Ollama)
├─ evaluation/  Comparar Modelos: Arena register (blind A/B model comparison)
├─ email/       Email assistant: IMAP/SMTP client + REST API (port 8995)
├─ agenda/      notes, reminders, calendar and scheduled tasks (port 8996)
├─ skills/      skills: chat filter + panel API (port 8997)
├─ utilidades/  chat filters: YouTube, weather, OCR/boletos, compaction, commands, guard
├─ documentos/  Documents (AI suggestions, versions, Word/PDF) and PDF forms
├─ ajustes/     Open WebUI defaults for Nous (Portuguese, embeddings, hidden natives)
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
GET  /research     Deep Research report library (/research/view?id=)
POST /image/remove-bg  image -> PNG without background (photo editor)
GET  /installed    models installed in Ollama (the panel never talks to Ollama directly)
GET  /gallery      generated images (/gallery/image/{id}, /gallery/delete, /gallery/meta)
GET  /diag         Diagnostics: every part of Nous with ✓/✗
POST /pdf/fields   PDF forms (/pdf/fill, /pdf/autofill, /pdf/signature)
POST /compare/run  Compare models (/compare/vote, /compare/score, /compare/reset)
```

Agenda (8996) and Skills (8997) document their routes at the top of
`agenda/nous_agenda_api.py` and `skills/nous_skills_api.py`.

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
[Flux.1 Schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell) (Apache-2.0) ·
[U²-Net](https://github.com/xuebinqin/U-2-Net) (Apache-2.0, `u2netp` model as published by [rembg](https://github.com/danielgatis/rembg)) ·
[RapidOCR](https://github.com/RapidAI/RapidOCR) (Apache-2.0) ·
[pypdf](https://github.com/py-pdf/pypdf) (BSD-3) ·
[Granite Embedding](https://huggingface.co/ibm-granite/granite-embedding-278m-multilingual) (Apache-2.0) ·
[ntfy](https://ntfy.sh) ·
[Open-Meteo](https://open-meteo.com).  
The Store's speed estimate was inspired by the idea behind [llmfit](https://github.com/AlexsJones/llmfit) (MIT).  
All trademarks belong to their respective projects.

## License

[MIT](LICENSE) © Nous. Contributions welcome — open an issue or a PR.
