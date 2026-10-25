<#
.SYNOPSIS
  Nous - Instalador do motor de imagem (ComfyUI + Flux.1 Schnell).
.DESCRIPTION
  Instala o ComfyUI num ambiente isolado e o PyTorch CERTO para a sua GPU:
    - NVIDIA            -> PyTorch CUDA (cu124)
    - AMD RDNA4 (RX 90x0) -> PyTorch ROCm NATIVO (gfx120X) - SEM ZLUDA
    - Outras / sem GPU  -> PyTorch CPU (funciona, porem lento)
  Depois instala o custom node ComfyUI-GGUF e baixa os modelos do Flux (~12 GB).

  Idempotente: pula o que ja existir. Use -Force p/ refazer o PyTorch.
.PARAMETER ComfyDir
  Pasta de instalacao do ComfyUI (padrao: %USERPROFILE%\ComfyUI).
.PARAMETER Torch
  Forca o backend: auto (padrao) | cuda | rocm | cpu.
.PARAMETER SkipModels
  Nao baixa os ~12 GB de modelos do Flux (faca depois com download-models.ps1).
#>
param(
    [string]$ComfyDir = (Join-Path $env:USERPROFILE "ComfyUI"),
    [ValidateSet("auto", "cuda", "rocm", "cpu")][string]$Torch = "auto",
    [switch]$SkipModels,
    [switch]$Force
)
$ErrorActionPreference = "Stop"

function Step($t) { Write-Host "`n>> $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "   [ok] $t" -ForegroundColor Green }
function Info($t) { Write-Host "   $t" -ForegroundColor DarkGray }
function Warn($t) { Write-Host "   [aviso] $t" -ForegroundColor Yellow }

Write-Host "========== Nous - motor de imagem (ComfyUI + Flux) ==========" -ForegroundColor Yellow

# 0) Pre-requisitos ---------------------------------------------------------
Step "Verificando git e Python 3.11"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git nao encontrado. Instale com: winget install --id Git.Git -e"
}
$py311 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
if (-not (Test-Path $py311)) {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) { $py311 = "py -3.11" } else { throw "Python 3.11 nao encontrado." }
}
Ok "pre-requisitos presentes"

# Roda um comando nativo e para com mensagem clara se ele falhar.
function Run($what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $what (codigo $LASTEXITCODE). Veja as mensagens acima." }
}

# Espaco em disco: ComfyUI + PyTorch (~8 GB) + modelos (~12 GB) = ~22 GB.
$drvName = (Split-Path -Qualifier $ComfyDir).TrimEnd(":")
$drv = Get-PSDrive -Name $drvName -ErrorAction SilentlyContinue
if ($drv) {
    $need = 24GB
    if ($SkipModels) { $need = 10GB }
    $have = $drv.Free + 0
    if (Test-Path (Join-Path $ComfyDir "main.py")) { $need = [math]::Max(2GB, $need - 8GB) }
    if ($have -lt $need) {
        throw ("Pouco espaco em {0}: livres {1:N1} GB, preciso de ~{2:N0} GB. Libere espaco e rode de novo." -f $drvName, ($have / 1GB), ($need / 1GB))
    }
    Ok ("espaco livre em ${drvName}: {0:N0} GB" -f ($have / 1GB))
}

# 1) Detecta a GPU ----------------------------------------------------------
Step "Detectando a GPU"
$gpuName = ((Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue).Name) -join " | "
Info "GPU(s): $gpuName"
$backend = $Torch
if ($backend -eq "auto") {
    if ($gpuName -match "NVIDIA|GeForce|RTX|GTX|Quadro") {
        $backend = "cuda"
    }
    elseif ($gpuName -match "Radeon.*(90[0-9]0|RX\s?9\d{3})|gfx120") {
        $backend = "rocm"   # RDNA4 (RX 9070/9060) - caminho TESTADO
    }
    elseif ($gpuName -match "AMD|Radeon") {
        Warn "GPU AMD nao-RDNA4: ROCm no Windows e' instavel aqui. Usando CPU."
        Warn "Geracao de imagem sera LENTA. Para tentar ROCm: -Torch rocm"
        $backend = "cpu"
    }
    else {
        $backend = "cpu"
    }
}
Ok "backend do PyTorch: $backend"

# 2) Clona o ComfyUI --------------------------------------------------------
Step "ComfyUI em $ComfyDir"
if (Test-Path (Join-Path $ComfyDir "main.py")) { Ok "ja clonado" }
else {
    git clone https://github.com/comfyanonymous/ComfyUI $ComfyDir
    Ok "clonado"
}

# 3) Ambiente isolado -------------------------------------------------------
Step "Ambiente Python do ComfyUI"
$venv = Join-Path $ComfyDir "venv"
$vpy  = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $vpy)) {
    if ($py311 -eq "py -3.11") { & py -3.11 -m venv $venv } else { & $py311 -m venv $venv }
    Ok "venv criado"
} else { Ok "venv ja existe" }
& $vpy -m pip install --upgrade pip --quiet

# 4) PyTorch certo para a GPU ----------------------------------------------
Step "PyTorch ($backend)"
$hasTorch = $false
try { & $vpy -c "import torch" 2>$null; if ($LASTEXITCODE -eq 0) { $hasTorch = $true } } catch {}
if ($hasTorch -and -not $Force) { Ok "torch ja instalado (use -Force p/ refazer)" }
else {
    switch ($backend) {
        "cuda" {
            Info "baixando PyTorch CUDA (cu124)..."
            Run "PyTorch CUDA" { & $vpy -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 }
        }
        "rocm" {
            Info "baixando PyTorch ROCm NATIVO (gfx120X) - pode levar varios minutos..."
            Run "PyTorch ROCm" { & $vpy -m pip install --pre torch torchvision torchaudio --index-url https://rocm.nightlies.amd.com/v2/gfx120X-all/ }
        }
        default {
            Info "baixando PyTorch CPU..."
            Run "PyTorch CPU" { & $vpy -m pip install torch torchvision torchaudio }
        }
    }
    Ok "PyTorch instalado"
}

# 5) Dependencias do ComfyUI -----------------------------------------------
Step "Dependencias do ComfyUI"
Run "requirements do ComfyUI" { & $vpy -m pip install --quiet -r (Join-Path $ComfyDir "requirements.txt") }
Ok "requirements instalados"

# 6) Custom node: ComfyUI-GGUF (para o Flux quantizado) ---------------------
Step "Custom node ComfyUI-GGUF"
$ggufDir = Join-Path $ComfyDir "custom_nodes\ComfyUI-GGUF"
if (Test-Path $ggufDir) { Ok "ja instalado" }
else {
    git clone https://github.com/city96/ComfyUI-GGUF $ggufDir
    Run "requirements do ComfyUI-GGUF" { & $vpy -m pip install --quiet -r (Join-Path $ggufDir "requirements.txt") }
    Ok "instalado"
}

# 7) Modelos do Flux (~12 GB) ----------------------------------------------
if ($SkipModels) {
    Warn "modelos pulados (-SkipModels). Baixe depois com:"
    Warn "  images\download-models.ps1 -ComfyUI `"$ComfyDir`""
}
else {
    Step "Modelos do Flux.1 Schnell (~12 GB)"
    & (Join-Path $PSScriptRoot "download-models.ps1") -ComfyUI $ComfyDir
}

Write-Host "`n========== Motor de imagem pronto ==========" -ForegroundColor Green
Write-Host "Inicie com: images\start-comfyui.ps1  (sobe em http://localhost:8188)" -ForegroundColor White
Write-Host "No Nous, peca: 'crie uma imagem de ...' que a imagem aparece no chat." -ForegroundColor White
