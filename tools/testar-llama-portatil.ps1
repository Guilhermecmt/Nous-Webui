<#
.SYNOPSIS
  Testa o download do llama-server (launchers\llama-nous.ps1) isolado numa pasta de teste.
.DESCRIPTION
  Nao roda o instalador nem mexe no Nous instalado: tudo acontece dentro de
  -Pasta. Com -Zip usa um zip local (file:///) em vez de baixar do GitHub.
  Confere: SHA256 errado e' recusado e nao deixa lixo; o certo instala e roda;
  rodar de novo nao baixa nada; tag nova no LLAMA_VERSAO.json pede outro download.
  Sai com 1 se algo falhar.
#>
param([Parameter(Mandatory = $true)][string]$Pasta, [string]$Zip = "")
$ErrorActionPreference = "Stop"
$here = Split-Path $PSScriptRoot -Parent
. (Join-Path $here "launchers\llama-nous.ps1")
$falhas = 0
function Confere($ok, $msg) {
    if ($ok) { Write-Host "  [ok] $msg" -ForegroundColor Green }
    else { Write-Host "  [FALHA] $msg" -ForegroundColor Red; $script:falhas++ }
}

if (Test-Path -LiteralPath $Pasta) { Remove-Item -LiteralPath $Pasta -Recurse -Force }
$app = Join-Path $Pasta "app"
New-Item -ItemType Directory -Path (Join-Path $app "motor") -Force | Out-Null
Copy-Item (Join-Path $here "motor\LLAMA_VERSAO.json") (Join-Path $app "motor\LLAMA_VERSAO.json")
$url = if ($Zip) { ([Uri](Resolve-Path $Zip).Path).AbsoluteUri } else { "" }
$dest = Get-LlamaDir $app

Write-Host "== SHA256 errado" -ForegroundColor Cyan
$r = Install-LlamaServer -AppDir $app -Url $url -Sha256 ("0" * 64)
Confere (-not $r) "recusa o arquivo que nao confere"
Confere ($script:LlamaErro -like "*SHA256*") "explica o motivo: $script:LlamaErro"
Confere (-not (Test-Path $dest) -and -not (Test-Path "$dest.tmp")) "nao deixa pasta nem lixo"

Write-Host "== Download certo" -ForegroundColor Cyan
$t0 = Get-Date
$r = Install-LlamaServer -AppDir $app -Url $url
Confere $r "instala ($script:LlamaErro)"
Confere (Test-LlamaExe (Join-Path $dest "llama-server.exe")) "llama-server.exe roda"
Confere (Test-Path (Join-Path $dest "ggml-vulkan.dll")) "veio com o Vulkan"
Confere (-not (Test-Path "$dest.tmp")) "limpa a pasta temporaria"

Write-Host "== De novo" -ForegroundColor Cyan
$antes = (Get-Item (Join-Path $dest "llama-server.exe")).LastWriteTime
$r = Install-LlamaServer -AppDir $app -Url "http://127.0.0.1:9/nao-baixa.zip"
Confere ($r -and (Get-Item (Join-Path $dest "llama-server.exe")).LastWriteTime -eq $antes) "nao baixa de novo"

Write-Host "== Versao nova pedida" -ForegroundColor Cyan
$j = Get-Content (Join-Path $app "motor\LLAMA_VERSAO.json") -Raw | ConvertFrom-Json
$j.tag = "b0"
[IO.File]::WriteAllText((Join-Path $app "motor\LLAMA_VERSAO.json"), ($j | ConvertTo-Json))
Confere (-not (Test-LlamaAtual $app)) "tag diferente = desatualizado"

if ($falhas) { Write-Host "`n$falhas falha(s)." -ForegroundColor Red; exit 1 }
Write-Host "`nTudo certo." -ForegroundColor Green
