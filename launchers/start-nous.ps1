<#
  Nous WebUI - Iniciar (em segundo plano, sem janela de terminal).
  Sobe o Ollama (se preciso) + o servidor Nous OCULTO e abre o navegador.
  Compile para .exe com build-exe.ps1 (-noConsole) para nao mostrar janela.
  Para encerrar: use stop-nous.ps1 (ou o atalho "Parar Nous").
#>
$ErrorActionPreference = "SilentlyContinue"

$venv = Join-Path $env:USERPROFILE "open-webui"
$exe  = Join-Path $venv "Scripts\open-webui.exe"
$py   = Join-Path $venv "Scripts\python.exe"
$url  = "http://localhost:8080"

# --- Configuracao ---
$env:WEBUI_NAME          = "Nous"
$env:DATA_DIR            = Join-Path $env:USERPROFILE "NousData"
$env:OLLAMA_BASE_URL     = "http://127.0.0.1:11434"
# Modelo sai da VRAM 30s apos a ultima mensagem (era 5 min). O Pipe ja envia
# keep_alive por requisicao; isto cobre tambem clientes diretos do Ollama.
$env:OLLAMA_KEEP_ALIVE   = "30s"
$env:ENABLE_WEB_SEARCH   = "True"
$env:WEB_SEARCH_ENGINE   = "duckduckgo"
$env:WEB_SEARCH_RESULT_COUNT = "5"
$env:ENABLE_RAG_WEB_SEARCH   = "True"
$env:RAG_WEB_SEARCH_ENGINE   = "duckduckgo"
# Injeta os resultados da busca direto no contexto (sem exigir modelo de
# embedding) - sem isto, o Gemma responde "nao tenho acesso em tempo real".
$env:BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = "True"
$env:PORT                = "8080"
# Arena é gerenciado pelo register_arena.py (register via DB no boot).
# DEFAULT_MODELS só é definido se o instalador gravou um modelo escolhido.
$manifestPath = Join-Path $env:DATA_DIR "install-manifest.json"
if (Test-Path $manifestPath) {
    try {
        $man = Get-Content $manifestPath -Raw | ConvertFrom-Json
        if ($man.model) { $env:DEFAULT_MODELS = $man.model }
    } catch {}
}

# Modelos de NUVEM opcionais (GPT-4, Claude via OpenRouter, Gemini...). Deixamos a
# conexao OpenAI-compativel LIGADA para que o usuario POSSA adicionar uma chave em
# Admin > Settings > Connections se quiser. Sem chave, nada acontece e nada sai da
# maquina — o Nous continua 100% local por padrao. A memoria, os arquivos e o
# historico SEMPRE usam o Ollama local, mesmo que o chat use um modelo de nuvem.
$env:ENABLE_OPENAI_API = "True"

# Forca o idioma do Whisper para portugues (env-only na 0.9.6).
$env:WHISPER_LANGUAGE = "pt"

# Chave secreta ESTAVEL: sem ela, o open-webui gera uma nova a cada inicio e
# desloga voce. Guardamos uma chave local (em NousData, fora do git) e a reusamos.
$keyFile = Join-Path $env:DATA_DIR ".webui_secret_key"
if (-not (Test-Path $keyFile)) {
    New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null
    $bytes = New-Object 'byte[]' 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $key = ($bytes | ForEach-Object { $_.ToString('x2') }) -join ''
    [IO.File]::WriteAllText($keyFile, $key)
}
$env:WEBUI_SECRET_KEY = (Get-Content $keyFile -Raw).Trim()

# Sugestoes da tela inicial (substitui as genericas em ingles)
$env:DEFAULT_PROMPT_SUGGESTIONS = '[{"title":["Resumir um texto","cole o conteudo e peca um resumo claro"],"content":"Resuma o texto a seguir de forma clara e objetiva:\n\n"},{"title":["Escrever um e-mail","profissional e direto"],"content":"Escreva um e-mail profissional sobre: "},{"title":["Explicar um conceito","de forma simples"],"content":"Explique de forma simples o conceito de: "},{"title":["Ideias criativas","para um projeto"],"content":"Me de 5 ideias criativas para: "}]'

function Test-Up {
    try { return (Invoke-WebRequest "$url/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200 }
    catch { return $false }
}

# Garante a identidade Nous (logo, tema, loader.js) no pacote open_webui.
# Auto-cura: o marcador em NousData guarda versao do open-webui + hash dos
# arquivos Nous; se um upgrade/reinstalacao apagou o tema, reaplica sozinho.
# Com o marcador valido, sai em milissegundos (sem PIL, sem reescrever nada).
function Ensure-Branding {
    $brand = Join-Path $PSScriptRoot "..\branding\apply_branding.py"
    if ((Test-Path $py) -and (Test-Path $brand)) {
        & $py "$brand" --if-needed --data-dir "$env:DATA_DIR" | Out-Null
    }
}

# Garante a memoria nativa (Filter global e ativo) registrada no banco.
# Idempotente, sem login: re-sincroniza nous_memory.py a cada inicio.
function Register-Memory {
    $reg = Join-Path $PSScriptRoot "..\memory\register_memory.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

# Garante o Pipe de imagem registrado no banco (sem credenciais).
# So' faz algo se nous_image_pipe.py existir (ComfyUI instalado).
function Register-Pipe {
    $reg = Join-Path $PSScriptRoot "..\images\register_pipe_auto.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

# --- Acesso aos seus arquivos (Fase 2): RAG local sobre uma pasta sua ---

# Garante a pasta a indexar: usa a config existente OU cria a pasta padrao 'Nous'
# em Documentos (resolve o caminho real, mesmo com OneDrive) e grava a config.
# Para apontar p/ o Obsidian: edite nous_files.json ou use o valve do Nous Files.
function Ensure-FilesFolder {
    $cfg = Join-Path $env:DATA_DIR "nous_files.json"
    $folder = $null
    if (Test-Path $cfg) {
        try { $folder = (Get-Content $cfg -Raw | ConvertFrom-Json).folder } catch {}
    }
    if (-not $folder) {
        $docs = [Environment]::GetFolderPath('MyDocuments')
        if (-not $docs) { $docs = Join-Path $env:USERPROFILE "Documents" }
        $folder = Join-Path $docs "Nous"
        New-Item -ItemType Directory -Force -Path $folder    | Out-Null
        New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null
        # WriteAllText = UTF-8 SEM BOM (Set-Content -Encoding UTF8 poe BOM no PS 5.1)
        [IO.File]::WriteAllText($cfg, (@{ folder = $folder } | ConvertTo-Json))
    }
}

# Garante o modelo de embeddings (busca semantica nos arquivos). Baixa so' se faltar.
function Ensure-EmbedModel {
    try {
        $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
        $has = $false
        foreach ($m in $tags.models) { if ($m.name -match "nomic-embed-text") { $has = $true } }
        if (-not $has) {
            $ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
            if (-not (Test-Path $ollamaExe)) { $ollamaExe = "ollama" }
            Start-Process -FilePath $ollamaExe -ArgumentList "pull nomic-embed-text" -WindowStyle Hidden
        }
    } catch {}
}

# Sobe o indexador (modo watch) em segundo plano. Ele mesmo evita duplicar (lock),
# le a pasta da config a cada ciclo e reindexa o que mudou (~20s).
function Start-Indexer {
    $idx = Join-Path $PSScriptRoot "..\files\index_files.py"
    if ((Test-Path $py) -and (Test-Path $idx)) {
        Start-Process -FilePath $py -ArgumentList "`"$idx`" --data-dir `"$env:DATA_DIR`"" -WindowStyle Hidden
    }
}

# Garante o filtro Nous Files registrado no banco (Filter global e ativo, sem login).
function Register-Files {
    $reg = Join-Path $PSScriptRoot "..\files\register_files.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

function Setup-Files { Ensure-FilesFolder; Ensure-EmbedModel; Start-Indexer; Register-Files }

# --- Historico de conversas (Fase 4): RAG sobre dialogo passado do usuario ---

# Sobe o indexador de historico em segundo plano. Le o webui.db e indexa pares
# de dialogo (pergunta + resposta) em nous_history.sqlite3. Singleton por porta
# (8992). Ciclo de 60 s (conversas mudam com menos frequencia que arquivos).
function Start-HistoryIndexer {
    $idx = Join-Path $PSScriptRoot "..\history\index_history.py"
    if ((Test-Path $py) -and (Test-Path $idx)) {
        Start-Process -FilePath $py -ArgumentList "`"$idx`" --data-dir `"$env:DATA_DIR`"" -WindowStyle Hidden
    }
}

# Garante o filtro Nous History registrado no banco (Filter global e ativo, sem login).
function Register-History {
    $reg = Join-Path $PSScriptRoot "..\history\register_history.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

function Setup-History { Start-HistoryIndexer; Register-History }

# --- Painel de memoria e personas (Fase 3 + 5): micro-servico REST local ----

# Sobe a API de memoria/personas em segundo plano. Expoe http://127.0.0.1:8993.
# Usada pelo painel flutuante do nous-loader.js (lista, edita, deleta memorias
# e gerencia personas). Tolerante a falhas: o Nous funciona sem ela.
function Start-MemoryAPI {
    $api = Join-Path $PSScriptRoot "..\memory\nous_memory_api.py"
    if ((Test-Path $py) -and (Test-Path $api)) {
        try { Invoke-RestMethod "http://127.0.0.1:8993/health" -TimeoutSec 2 | Out-Null }
        catch { Start-Process -FilePath $py -ArgumentList "`"$api`"" -WindowStyle Hidden }
    }
}

# --- Voz local em PT-BR (v2.3): Piper TTS + Whisper STT ---

# Sobe o servidor TTS local (porta 8994) se os assets de voz existirem.
# Idempotente: o servidor recusa subir se a porta ja esta ocupada.
function Start-VoiceServer {
    $srv = Join-Path $PSScriptRoot "..\voice\nous_tts_server.py"
    $vdir = Join-Path $env:DATA_DIR "voice"
    if ((Test-Path $py) -and (Test-Path $srv) -and (Test-Path (Join-Path $vdir "piper.exe"))) {
        try { Invoke-RestMethod "http://127.0.0.1:8994/health" -TimeoutSec 2 | Out-Null }
        catch { Start-Process -FilePath $py -ArgumentList "`"$srv`" --data-dir `"$env:DATA_DIR`"" -WindowStyle Hidden }
    }
}

# Configura STT/TTS no banco (so' age se os assets existirem; remove se ausentes).
function Register-Voice {
    $reg = Join-Path $PSScriptRoot "..\voice\register_voice.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

# --- Pesquisa Profunda (v2.4): Pipe registrado no banco, ativo só com SearXNG ---

# Registra o Pipe 'Pesquisa Profunda (Nous)' no banco. Ativo se SearXNG responder.
function Register-Research {
    $reg = Join-Path $PSScriptRoot "..\search\register_research_pipe.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

# --- Comparar Modelos (v2.4): Arena do Open WebUI reembrulhado ---

# Liga o Arena com modelos locais se >= 2 modelos de chat estiverem instalados.
function Register-Arena {
    $reg = Join-Path $PSScriptRoot "..\evaluation\register_arena.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

# --- Nuvem NVIDIA NIM (v2.1): conexao opt-in registrada/removida a cada boot ---

# Garante a conexao NVIDIA NIM no banco (se a chave existir) ou a remove.
# Idempotente: ativa quando NousData\.nvidia_api_key presente, desativa se ausente.
function Register-Cloud {
    $reg = Join-Path $PSScriptRoot "..\cloud\register_nvidia.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

# Ja esta rodando? Garante funcoes nativas e abre o navegador.
if (Test-Up) { Ensure-Branding; Register-Memory; Register-Pipe; Register-Research; Register-Arena; Register-Cloud; Register-Voice; Start-VoiceServer; Setup-Files; Setup-History; Start-MemoryAPI; Start-Process $url; return }

# Garante o Ollama (em segundo plano)
try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null }
catch {
    $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
    if (Test-Path $ollama) { Start-Process $ollama -WindowStyle Hidden }
    Start-Sleep -Seconds 4
}

# Garante a identidade ANTES do servidor subir (1a requisicao ja sai com logo)
Ensure-Branding

# Sobe o servidor OCULTO (sem janela) e desanexa
Start-Process -FilePath $exe -ArgumentList "serve" -WindowStyle Hidden

# Sobe o Nous Monitor (painel de VRAM / modelos) em segundo plano
$monitor = Join-Path $PSScriptRoot "..\monitor\nous_monitor.py"
if ((Test-Path $py) -and (Test-Path $monitor)) {
    try { Invoke-RestMethod "http://127.0.0.1:8990/health" -TimeoutSec 2 | Out-Null }
    catch { Start-Process -FilePath $py -ArgumentList "`"$monitor`"" -WindowStyle Hidden }
}

# Espera ficar pronto, garante funcoes nativas e abre o navegador
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Up) { Ensure-Branding; Register-Memory; Register-Pipe; Register-Research; Register-Arena; Register-Cloud; Register-Voice; Start-VoiceServer; Setup-Files; Setup-History; Start-MemoryAPI; Start-Process $url; break }
}
