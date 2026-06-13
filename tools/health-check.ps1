<#
.SYNOPSIS
  Nous WebUI - Verificacao inteligente pos-instalacao.
.DESCRIPTION
  Confere se a instalacao esta integra: Ollama instalado e no ar, modelo
  presente, ambiente Open WebUI, identidade Nous aplicada e (se rodando)
  o servidor respondendo. Retorna 0 se tudo certo, 1 se houver falhas.
#>
param([string]$Model = "gemma4:12b")
$ErrorActionPreference = "SilentlyContinue"

$venv    = Join-Path $env:USERPROFILE "open-webui"
$owDir   = Join-Path $venv "Lib\site-packages\open_webui"
$dataDir = if ($env:DATA_DIR) { $env:DATA_DIR } else { Join-Path $env:USERPROFILE "NousData" }
$script:fail = 0

# Mesma logica de Find-Ollama do instalador: PATH > locais comuns.
function Find-Ollama {
    $c = Get-Command ollama -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles  "Ollama\ollama.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Ollama\ollama.exe"))) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    return $null
}
$ollamaExe = Find-Ollama

function Check($name, $ok, $detail) {
    if ($ok) { Write-Host ("  [OK]    {0}" -f $name) -ForegroundColor Green }
    else     { Write-Host ("  [FALHA] {0} -> {1}" -f $name, $detail) -ForegroundColor Red; $script:fail++ }
}
function Note($name, $msg) { Write-Host ("  [i]     {0} -> {1}" -f $name, $msg) -ForegroundColor DarkGray }

Write-Host "=== Nous - Verificacao de Saude ===`n" -ForegroundColor Cyan

Check "Ollama instalado" ($null -ne $ollamaExe) "ollama nao encontrado (PATH nem locais comuns)"

$apiUp = $false
try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null; $apiUp = $true } catch {}
Check "Servico Ollama no ar" $apiUp "API 11434 nao responde"

$hasModel = $false
if (Test-Path $ollamaExe) { $hasModel = [bool]((& $ollamaExe list 2>$null) -match [regex]::Escape($Model)) }
if ($hasModel) { Check "Modelo $Model presente" $true "" }
else { Note "Modelo" "nenhum baixado ainda - o Nous oferece o download no primeiro uso (Loja de Modelos)" }

Check "Open WebUI instalado" (Test-Path (Join-Path $venv "Scripts\open-webui.exe")) "ambiente/open-webui ausente"

# Identidade: tema + logo nas pastas static + marcador de auto-cura
$brandOk = (Test-Path (Join-Path $owDir "static\custom.css")) -and
           (Test-Path (Join-Path $owDir "static\favicon.png"))
Check "Identidade Nous aplicada" $brandOk "rode branding\apply_branding.py"
if (Test-Path (Join-Path $dataDir ".branding_marker.json")) {
    Check "Auto-cura da identidade (marcador)" $true ""
} else {
    Note "Identidade (marcador)" "sera gravado no proximo inicio do Nous"
}

# Atalho: area de trabalho OU Menu Iniciar (o launcher cria nos dois)
$lnkDesk  = Join-Path ([Environment]::GetFolderPath("Desktop"))  "Nous.lnk"
$lnkCommon= Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "Nous.lnk"
$lnkStart = Join-Path ([Environment]::GetFolderPath("Programs")) "Nous.lnk"
if ((Test-Path $lnkDesk) -or (Test-Path $lnkCommon) -or (Test-Path $lnkStart)) {
    Check "Atalho 'Nous' presente" $true ""
} else {
    Note "Atalho 'Nous'" "nao encontrado - use iniciar.bat ou rode instalar.bat de novo"
}

if (Test-Path (Join-Path $dataDir "webui.db")) {
    Check "Dados em local seguro (DATA_DIR)" $true ""
} else {
    Note "Dados (DATA_DIR)" "webui.db sera criado no primeiro uso ($dataDir)"
}

$srv = $false
try { $srv = (Invoke-WebRequest "http://localhost:8080/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200 } catch {}
if ($srv) { Write-Host "  [OK]    Servidor Nous respondendo (8080)" -ForegroundColor Green }
else      { Note "Servidor Nous" "parado (normal se voce ainda nao iniciou)" }

# Nuvem NVIDIA (informativo — nunca falha o health-check)
$nvKeyFile = Join-Path $dataDir ".nvidia_api_key"
if (Test-Path $nvKeyFile) {
    $nvKey = (Get-Content $nvKeyFile -Raw -ErrorAction SilentlyContinue).Trim()
    if ($nvKey) {
        $nvOk = $false
        try {
            $nvResp = Invoke-WebRequest `
                -Uri "https://integrate.api.nvidia.com/v1/models" `
                -Headers @{ Authorization = "Bearer $nvKey" } `
                -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop
            $nvOk = $nvResp.StatusCode -eq 200
        } catch {}
        if ($nvOk) { Note "Nuvem NVIDIA" "ativa e alcancavel" }
        else        { Note "Nuvem NVIDIA" "chave presente mas API nao respondeu (sem internet?)" }
    } else {
        Note "Nuvem NVIDIA" "inativa (arquivo de chave vazio)"
    }
} else {
    Note "Nuvem NVIDIA" "inativa (use ativar-nuvem.bat para ativar)"
}

# Voz local (informativo — nunca falha o health-check)
$voiceDir = Join-Path $dataDir "voice"
$piperExe = Join-Path $voiceDir "piper.exe"
$hasVoice = (Test-Path $piperExe) -and (Get-ChildItem $voiceDir -Filter "pt_BR-*.onnx" -ErrorAction SilentlyContinue | Select-Object -First 1)
if ($hasVoice) {
    $ttsSrv = $false
    try { $ttsSrv = (Invoke-RestMethod "http://127.0.0.1:8994/health" -TimeoutSec 3 -ErrorAction Stop).status -eq 'ok' } catch {}
    if ($ttsSrv) { Note "Voz" "ativa e servidor TTS respondendo (8994)" }
    else          { Note "Voz" "ativa mas servidor TTS nao esta no ar (sera iniciado no proximo boot)" }
} else {
    Note "Voz" "inativa (use 'Ativar voz em PT-BR' no painel Recursos ou ativar-voz.bat)"
}

# Email assistant (informativo — nunca falha o health-check)
$emailAcct = Join-Path $dataDir ".email_account.json"
if (Test-Path $emailAcct) {
    $emailUp = $false
    try {
        $emailResp = Invoke-RestMethod "http://127.0.0.1:8995/status" -TimeoutSec 3 -ErrorAction Stop
        $emailUp = $true
        Note "Email" "conectado ($($emailResp.user)) — serviço ativo (8995)"
    } catch {}
    if (-not $emailUp) { Note "Email" "conta configurada, mas serviço 8995 não responde (iniciará no próximo boot)" }
} else {
    Note "Email" "não configurado (use conectar-email.bat para ativar)"
}

Write-Host ""
if ($script:fail -eq 0) { Write-Host "TUDO CERTO - instalacao integra." -ForegroundColor Green; exit 0 }
else { Write-Host "$($script:fail) problema(s) encontrado(s)." -ForegroundColor Red; exit 1 }
