<#
  Nous WebUI - Iniciar (em segundo plano, sem janela de terminal).
  Sobe o Ollama (se preciso) + o servidor Nous OCULTO e abre o navegador.
  Chamado sem janela pelo nous-hidden.vbs (atalho "Nous" / iniciar.bat).
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
# Modelo fica na VRAM por 5 min apos a ultima mensagem. Era 30s, mas recarregar
# um modelo de ~8 GB custa ~100s; com 30s, qualquer pausa para ler/digitar fazia
# o modelo sair e a proxima resposta demorar muito. 5 min cobre conversas
# normais sem recarregar e ainda libera a VRAM sozinho quando voce para.
$env:OLLAMA_KEEP_ALIVE   = "5m"
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
$manifestModel = $null
if (Test-Path $manifestPath) {
    try { $manifestModel = (Get-Content $manifestPath -Raw | ConvertFrom-Json).model } catch {}
}
# O aviso "Uma nova versao do Open WebUI esta disponivel" leva ao GitHub e o
# usuario leigo nao tem como atualizar por la' - quem atualiza e' o Nous.
$env:ENABLE_VERSION_UPDATE_CHECK = "False"

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
$env:DEFAULT_PROMPT_SUGGESTIONS = '[{"title":["Resumir um texto","cole o conteúdo e peça um resumo claro"],"content":"Resuma o texto a seguir de forma clara e objetiva:\n\n"},{"title":["Escrever um e-mail","profissional e direto"],"content":"Escreva um e-mail profissional sobre: "},{"title":["Explicar um conceito","de forma simples"],"content":"Explique de forma simples o conceito de: "},{"title":["Ideias criativas","para um projeto"],"content":"Me dê 5 ideias criativas para: "}]'

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

# Oculta modelos de embedding (nomic-embed-text) do seletor de chat: eles
# servem so' para busca semantica e nao conversam — se aparecem no dropdown,
# o usuario seleciona e nao recebe resposta. Idempotente (escreve no webui.db).
function Hide-EmbedModels {
    $reg = Join-Path $PSScriptRoot "..\monitor\register_hidden_models.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
}

# Define num_ctx adequado (16384) nos modelos de chat. Sem isto, o Ollama usa
# 4096 e a busca web (que injeta paginas inteiras no prompt) estoura o contexto,
# fazendo o modelo devolver resposta VAZIA. Idempotente (escreve no webui.db).
function Set-ModelCtx {
    $reg = Join-Path $PSScriptRoot "..\monitor\register_model_ctx.py"
    if ((Test-Path $py) -and (Test-Path $reg)) {
        & $py "$reg" --data-dir "$env:DATA_DIR" | Out-Null
    }
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

# --- Geracao de imagem (ComfyUI + Flux): sobe o motor se estiver instalado ---

# Inicia o ComfyUI (porta 8188) em segundo plano SE estiver instalado. Ocioso
# ele quase nao usa recursos (os modelos so' carregam na 1a geracao). Com ele no
# ar, o register_pipe_auto ativa o 'Gerador de Imagem Local' no seletor do chat.
# Suporta os dois locais: ComfyUI e o fork ComfyUI-Zluda (GPUs AMD).
function Start-ComfyUI {
    $cu = @(
        (Join-Path $env:USERPROFILE "ComfyUI"),
        (Join-Path $env:USERPROFILE "ComfyUI-Zluda")
    ) | Where-Object { Test-Path (Join-Path $_ "venv\Scripts\python.exe") } | Select-Object -First 1
    if (-not $cu) { return }
    if (Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue) { return }
    $cpy  = Join-Path $cu "venv\Scripts\python.exe"
    $main = Join-Path $cu "main.py"
    $env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
    Start-Process -FilePath $cpy -ArgumentList "`"$main`"", "--port", "8188" -WorkingDirectory $cu -WindowStyle Hidden
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

# --- Email assistant (v2.5): serviço REST local na porta 8995 ---

# Sobe o serviço de email (8995) apenas se a conta estiver configurada.
function Start-EmailAPI {
    $acct = Join-Path $env:DATA_DIR ".email_account.json"
    $api  = Join-Path $PSScriptRoot "..\email\nous_email_api.py"
    if ((Test-Path $py) -and (Test-Path $api) -and (Test-Path $acct)) {
        try { Invoke-RestMethod "http://127.0.0.1:8995/health" -TimeoutSec 2 | Out-Null }
        catch { Start-Process -FilePath $py -ArgumentList "`"$api`"" -WindowStyle Hidden }
    }
}

# --- Utilidades (v2.7): YouTube e Clima, Filters globais registrados no banco ---

function Register-Utilidades {
    $reg = Join-Path $PSScriptRoot "..\utilidades\register_utilidades.py"
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

# --- Partida -----------------------------------------------------------------

# Sobe o Nous Monitor (painel de VRAM / Loja de Modelos) em segundo plano. Roda
# em TODO inicio - inclusive com o servidor ja no ar - para que um monitor que
# caiu volte sem precisar reiniciar o computador.
function Start-Monitor {
    $monitor = Join-Path $PSScriptRoot "..\monitor\nous_monitor.py"
    if ((Test-Path $py) -and (Test-Path $monitor)) {
        try { Invoke-RestMethod "http://127.0.0.1:8990/health" -TimeoutSec 2 | Out-Null }
        catch { Start-Process -FilePath $py -ArgumentList "`"$monitor`"" -WindowStyle Hidden }
    }
}

# Mesma busca do instalador: o Ollama pode estar no PATH ou em Program Files,
# nao so' em LOCALAPPDATA.
function Find-OllamaApp {
    $dirs = @()
    $c = Get-Command ollama -ErrorAction SilentlyContinue
    if ($c) { $dirs += (Split-Path $c.Source) }
    $dirs += (Join-Path $env:LOCALAPPDATA "Programs\Ollama")
    $dirs += (Join-Path $env:ProgramFiles "Ollama")
    foreach ($d in $dirs) {
        $app = Join-Path $d "ollama app.exe"
        if (Test-Path $app) { return @{ exe = $app; args = $null } }
        $cli = Join-Path $d "ollama.exe"
        if (Test-Path $cli) { return @{ exe = $cli; args = "serve" } }
    }
    return $null
}

# Servidor do Nous ja em processo de partida (um segundo clique no atalho)?
function Test-ServerProcess {
    [bool](Get-Process open-webui -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path -like "$venv\*" })
}

function Register-All {
    Ensure-Branding; Register-Memory; Register-Pipe; Register-Research; Register-Arena
    Register-Cloud; Register-Voice; Start-VoiceServer; Start-ComfyUI; Setup-Files
    Setup-History; Hide-EmbedModels; Set-ModelCtx; Start-MemoryAPI; Start-EmailAPI
    Register-Utilidades
}

function Show-Error([string]$msg) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($msg, "Nous",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
}

if (-not (Test-Path $exe)) {
    Show-Error ("O Nous nao esta instalado por completo (falta a interface).`n`n" +
        "Rode o instalar.bat de novo. Suas conversas sao preservadas.")
    return
}

Start-Monitor

# Ja esta rodando? Garante funcoes nativas e abre o navegador.
if (Test-Up) { Register-All; Start-Process $url; return }

# O servidor NAO esta no ar: abre JA a tela de carregamento (o usuario ve o logo
# do Nous e uma barra de progresso na hora). Ela mesma checa o servidor e abre o
# Nous sozinha quando estiver pronto. Sem isto, o navegador so' abriria 1-2 min
# depois - tempo em que a pessoa acha que travou e clica varias vezes.
$loading = Join-Path $PSScriptRoot "loading.html"
if (Test-Path $loading) { Start-Process $loading }

# Um clique anterior ja esta subindo o servidor: fica so' a tela de carregamento.
# Sem esta trava, cada clique subia OUTRO servidor contra o mesmo webui.db.
if (Test-ServerProcess) { return }

# Garante o Ollama (em segundo plano)
try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null }
catch {
    $ol = Find-OllamaApp
    if ($ol) {
        if ($ol.args) { Start-Process $ol.exe -ArgumentList $ol.args -WindowStyle Hidden }
        else          { Start-Process $ol.exe -WindowStyle Hidden }
    }
}

# Modelo padrao so' se ele de fato estiver instalado (o Open WebUI escolhe o
# primeiro disponivel sozinho quando nao ha padrao).
if ($manifestModel) {
    for ($i = 0; $i -lt 10; $i++) {
        try {
            $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
            if ($tags.models | Where-Object { $_.name -eq $manifestModel -or $_.name -eq "${manifestModel}:latest" }) {
                $env:DEFAULT_MODELS = $manifestModel
            }
            break
        } catch { Start-Sleep -Seconds 1 }
    }
}

# Garante a identidade ANTES do servidor subir (1a requisicao ja sai com logo)
Ensure-Branding

# Sobe o servidor OCULTO (sem janela) e desanexa. So' em 127.0.0.1: o Nous e'
# privado e nao deve aparecer para outros aparelhos da rede (antes: 0.0.0.0).
Start-Process -FilePath $exe -ArgumentList "serve --host 127.0.0.1 --port 8080" -WindowStyle Hidden

# Espera ficar pronto (ate 5 min: 1a partida num PC modesto) e garante as
# funcoes nativas. NAO abre o navegador aqui: a tela de carregamento, aberta
# la' em cima, detecta o servidor no ar e redireciona sozinha para o Nous.
$up = $false
for ($i = 0; $i -lt 150; $i++) {
    Start-Sleep -Seconds 2
    if (Test-Up) { $up = $true; break }
}
if ($up) { Register-All }
else {
    Show-Error ("O Nous demorou demais para abrir.`n`n" +
        "Tente: menu Iniciar > Parar Nous, e depois abra o Nous de novo.`n" +
        "Se continuar, reinicie o computador.")
}
