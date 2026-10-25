<#
  Nous - Inicia o ComfyUI (Flux) em segundo plano, com UTF-8.

  O PYTHONUTF8=1 e' ESSENCIAL no Windows: sem ele, a barra de progresso do
  sampler quebra com 'charmap codec can't encode...' (UnicodeEncodeError).

  Caminho nativo ROCm (RDNA4 / RX 9000) - sem ZLUDA.
  ComfyUI sobe em http://localhost:8188 (usado pelo Pipe "Nous" no chat).
#>
$ErrorActionPreference = "SilentlyContinue"

# Procura o ComfyUI nos locais padrao (instalacao nova ou o fork ComfyUI-Zluda).
$candidates = @(
    (Join-Path $env:USERPROFILE "ComfyUI"),
    (Join-Path $env:USERPROFILE "ComfyUI-Zluda")
)
$cu = $candidates | Where-Object { Test-Path (Join-Path $_ "venv\Scripts\python.exe") } | Select-Object -First 1
if (-not $cu) {
    Write-Host "ComfyUI nao encontrado. Instale com: images\install-comfyui.ps1" -ForegroundColor Red
    return
}
$py = Join-Path $cu "venv\Scripts\python.exe"

# Ja esta no ar?
if (Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue) {
    Write-Host "ComfyUI ja esta rodando: http://localhost:8188"
    return
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

Start-Process -FilePath $py `
    -ArgumentList "`"$cu\main.py`"", "--port", "8188" `
    -WorkingDirectory $cu -WindowStyle Hidden

Write-Host "ComfyUI iniciando (segundo plano) em http://localhost:8188 ..."
# Espera ficar pronto (a 1a subida leva ~20 s). Quem so' quer disparar pode ignorar.
$pronto = $false
for ($i = 0; $i -lt 40 -and -not $pronto; $i++) {
    Start-Sleep -Seconds 3
    try { Invoke-RestMethod "http://127.0.0.1:8188/system_stats" -TimeoutSec 2 | Out-Null; $pronto = $true } catch {}
}
if ($pronto) { Write-Host "ComfyUI pronto. Os modelos carregam na 1a imagem (~30 s)." }
else { Write-Host "ComfyUI ainda nao respondeu; confira em instantes." -ForegroundColor Yellow }
