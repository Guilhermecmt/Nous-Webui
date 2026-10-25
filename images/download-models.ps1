# ============================================================================
#  Nous - Download dos modelos do Flux.1 Schnell para o ComfyUI
#  Baixa: UNET (GGUF Q4) + T5 + CLIP-L + VAE  (cabem nos 16 GB da RX 9070 XT)
#
#  USO:
#    .\download-models.ps1 -ComfyUI "C:\caminho\para\ComfyUI"
#
#  Sao ~12 GB no total. Usa o curl.exe do Windows (retoma de onde parou se a
#  internet cair: basta rodar de novo) e confere o tamanho de cada arquivo.
#  Se uma URL do HuggingFace mudar, baixe manualmente do repo indicado.
#  Flux Schnell e' Apache-2.0 (uso comercial liberado).
# ============================================================================
param(
    [Parameter(Mandatory = $true)]
    [string]$ComfyUI
)

if (-not (Test-Path $ComfyUI)) {
    Write-Host "Pasta do ComfyUI nao encontrada: $ComfyUI" -ForegroundColor Red
    exit 1
}
$curl = Join-Path $env:SystemRoot "System32\curl.exe"
if (-not (Test-Path $curl)) {
    Write-Host "curl.exe nao encontrado (Windows 10 1803 ou mais novo)." -ForegroundColor Red
    exit 1
}

# destino_relativo  =>  url  (+ tamanho esperado em bytes, para conferir)
$models = @(
    @{ dir = "models\unet"; file = "flux1-schnell-Q4_K_S.gguf"; size = 6783943712;
       url = "https://huggingface.co/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q4_K_S.gguf" },
    @{ dir = "models\clip"; file = "t5xxl_fp8_e4m3fn.safetensors"; size = 4893934904;
       url = "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors" },
    @{ dir = "models\clip"; file = "clip_l.safetensors"; size = 246144152;
       url = "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors" },
    @{ dir = "models\vae"; file = "ae.safetensors"; size = 335304388;
       # O repo oficial (black-forest-labs) exige login (HTTP 401). Usamos um
       # espelho ABERTO do mesmo autoencoder (~320 MB, identico ao do Flux).
       url = "https://huggingface.co/ffxvs/vae-flux/resolve/main/ae.safetensors" }
)

# Espaco em disco: falha cedo se nao couber o que falta baixar.
$falta = 0
foreach ($m in $models) {
    $dest = Join-Path (Join-Path $ComfyUI $m.dir) $m.file
    if (-not (Test-Path $dest)) {
        $part = 0
        if (Test-Path "$dest.part") { $part = (Get-Item "$dest.part").Length }
        $falta += ($m.size - $part)
    }
}
if ($falta -gt 0) {
    $drive = (Get-Item $ComfyUI).PSDrive
    $livre = $drive.Free
    $precisa = $falta + 1GB
    if ($livre -lt $precisa) {
        Write-Host ("Sem espaco: faltam {0:N1} GB para os modelos, mas so ha {1:N1} GB livres em {2}:." -f ($precisa / 1GB), ($livre / 1GB), $drive.Name) -ForegroundColor Red
        exit 1
    }
}

$falhou = $false
foreach ($m in $models) {
    $destDir = Join-Path $ComfyUI $m.dir
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
    $dest = Join-Path $destDir $m.file

    if (Test-Path $dest) {
        Write-Host "[ja existe] $($m.file)" -ForegroundColor DarkGray
        continue
    }
    Write-Host "[baixando ] $($m.file) ..." -ForegroundColor Cyan
    # -C - retoma o .part; --retry cobre quedas curtas de rede.
    & $curl -L -f -s -S --retry 5 --retry-delay 5 -C - -o "$dest.part" $m.url
    $ok = ($LASTEXITCODE -eq 0) -and (Test-Path "$dest.part") -and ((Get-Item "$dest.part").Length -eq $m.size)
    if ($ok) {
        Move-Item -LiteralPath "$dest.part" -Destination $dest
        Write-Host "[ok       ] $($m.file)" -ForegroundColor Green
    } else {
        $falhou = $true
        Write-Host "[FALHOU   ] $($m.file)  -> rode de novo (retoma) ou baixe manualmente de:" -ForegroundColor Yellow
        Write-Host "             $($m.url)" -ForegroundColor Yellow
    }
}

Write-Host ""
if ($falhou) { exit 1 }
Write-Host "Modelos prontos. O custom node 'ComfyUI-GGUF' e' instalado pelo install-comfyui.ps1." -ForegroundColor White
