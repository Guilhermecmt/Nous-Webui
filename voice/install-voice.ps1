<#
.SYNOPSIS
  Baixa o Piper TTS (binario Windows) e a voz pt_BR para NousData\voice\.
  Tambem configura o STT/TTS no banco do Open WebUI.
  Chamado por "Ativar conversa por voz" no painel Recursos, ou por ativar-voz.bat.

.NOTES
  Idempotente: pula o que ja existe. Use -Force para rebaizar tudo.
#>
param(
    [string]$DataDir  = (Join-Path $env:USERPROFILE "NousData"),
    [string]$VoiceName = "pt_BR-faber-medium",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$voiceDir = Join-Path $DataDir "voice"
New-Item -ItemType Directory -Force -Path $voiceDir | Out-Null

$venv = Join-Path $env:USERPROFILE "open-webui"
$py   = Join-Path $venv "Scripts\python.exe"

# --------------------------------------------------------------------------
# URLs de download (mirrors abertos, sem login)
# --------------------------------------------------------------------------

# Piper Windows release (rhasspy/piper no GitHub)
$PIPER_RELEASE   = "2023.11.14-2"
$PIPER_ZIP_URL   = "https://github.com/rhasspy/piper/releases/download/$PIPER_RELEASE/piper_windows_amd64.zip"
$PIPER_ZIP       = Join-Path $voiceDir "piper_windows.zip"
$PIPER_EXE       = Join-Path $voiceDir "piper.exe"
$ESPEAK_DLL      = Join-Path $voiceDir "espeak-ng.dll"

# Voz pt_BR (rhasspy/piper-voices no Hugging Face, branch gh-pages)
$VOICE_BASE_URL  = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR"
$VOICE_FOLDER    = $VoiceName -replace "pt_BR-", "" # ex.: faber-medium -> faber/medium
$VOICE_PARTS     = $VOICE_FOLDER -split "-"         # ("faber","medium")
if ($VOICE_PARTS.Count -ge 2) {
    $HF_VOICE_PATH = "$($VOICE_PARTS[0])/$($VOICE_PARTS[1])"
} else {
    $HF_VOICE_PATH = $VOICE_PARTS[0]
}
$ONNX_URL        = "$VOICE_BASE_URL/$HF_VOICE_PATH/$VoiceName.onnx"
$JSON_URL        = "$VOICE_BASE_URL/$HF_VOICE_PATH/$VoiceName.onnx.json"
$ONNX_FILE       = Join-Path $voiceDir "$VoiceName.onnx"
$JSON_FILE       = Join-Path $voiceDir "$VoiceName.onnx.json"

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

function Download-File($url, $dest, $label) {
    if ((Test-Path $dest) -and -not $Force) {
        Write-Host "  [ok] $label ja existe."
        return
    }
    Write-Host "  Baixando $label..."
    try {
        $wc = New-Object System.Net.WebClient
        $wc.Headers.Add("User-Agent", "Nous/2.3 (+local)")
        $wc.DownloadFile($url, $dest)
        Write-Host "  [ok] $label baixado."
    } catch {
        throw "Erro ao baixar ${label}: $_"
    }
}

# --------------------------------------------------------------------------
# 1. Baixar Piper
# --------------------------------------------------------------------------

if (-not (Test-Path $PIPER_EXE) -or $Force) {
    Download-File $PIPER_ZIP_URL $PIPER_ZIP "Piper TTS (binario Windows)"
    Write-Host "  Extraindo Piper..."
    Expand-Archive -Path $PIPER_ZIP -DestinationPath $voiceDir -Force
    # O zip desempacota em piper\ — mover os arquivos para voiceDir
    $piperSubdir = Join-Path $voiceDir "piper"
    if (Test-Path $piperSubdir) {
        Get-ChildItem $piperSubdir | Move-Item -Destination $voiceDir -Force
        Remove-Item $piperSubdir -Recurse -Force
    }
    Remove-Item $PIPER_ZIP -Force -ErrorAction SilentlyContinue
    Write-Host "  [ok] Piper extraido."
} else {
    Write-Host "  [ok] piper.exe ja existe."
}

# --------------------------------------------------------------------------
# 2. Baixar voz pt_BR
# --------------------------------------------------------------------------

Download-File $ONNX_URL  $ONNX_FILE "$VoiceName.onnx"
Download-File $JSON_URL  $JSON_FILE "$VoiceName.onnx.json"

# --------------------------------------------------------------------------
# 3. Registrar STT/TTS no banco
# --------------------------------------------------------------------------

Write-Host "  Registrando configuracao de voz no banco..."
$reg = Join-Path $PSScriptRoot "register_voice.py"
if ((Test-Path $py) -and (Test-Path $reg)) {
    & $py $reg --data-dir $DataDir --voice $VoiceName
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "register_voice.py saiu com erro $LASTEXITCODE (nao e fatal — tente reiniciar o Nous)."
    } else {
        Write-Host "  [ok] Configuracao de voz registrada."
    }
} else {
    Write-Warning "Python ou register_voice.py nao encontrado. Reinicie o Nous para aplicar."
}

Write-Host ""
Write-Host "Voz ativada! Recarregue a pagina do Nous e toque no icone de"
Write-Host "telefone no chat para conversar por voz em portugues."
