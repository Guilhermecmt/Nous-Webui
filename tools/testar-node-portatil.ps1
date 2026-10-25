<#
.SYNOPSIS
  Testa o Node portatil (launchers\node-nous.ps1) isolado numa pasta de teste.
.DESCRIPTION
  Nao roda o instalador nem mexe no Nous instalado: tudo acontece dentro de
  -Pasta. Precisa de internet (baixa ~30 MB do nodejs.org uma vez).
  Confere: SHA256 errado e' recusado e nao deixa lixo; o download certo
  instala e roda; rodar de novo nao baixa nada; Find-NousNode acha o
  portatil quando o computador nao tem Node; o PATH do sistema nao muda.
  Sai com 1 se algo falhar.
.PARAMETER Pasta
  Onde instalar o teste (apagada e recriada).
#>
param([Parameter(Mandatory = $true)][string]$Pasta)
$ErrorActionPreference = "Stop"
$here = Split-Path $PSScriptRoot -Parent
. (Join-Path $here "launchers\node-nous.ps1")
$falhas = 0
function Confere($ok, $msg) {
    if ($ok) { Write-Host "  [ok] $msg" -ForegroundColor Green }
    else { Write-Host "  [FALHA] $msg" -ForegroundColor Red; $script:falhas++ }
}

if (Test-Path -LiteralPath $Pasta) { Remove-Item -LiteralPath $Pasta -Recurse -Force }
New-Item -ItemType Directory -Path $Pasta -Force | Out-Null
$app = Join-Path $Pasta "app"
$dest = Get-PortableNodeDir $app
$pathAntes = [Environment]::GetEnvironmentVariable("Path", "User")

Write-Host "== SHA256 errado" -ForegroundColor Cyan
$r = Install-PortableNode -Dest $dest -Sha256 ("0" * 64)
Confere (-not $r) "recusa o arquivo que nao confere"
Confere ($script:NodeErro -like "*SHA256*") "explica o motivo: $script:NodeErro"
Confere (-not (Test-Path $dest) -and -not (Test-Path "$dest.tmp")) "nao deixa pasta nem lixo"

Write-Host "== Endereco que nao existe" -ForegroundColor Cyan
$r = Install-PortableNode -Dest $dest -Versao "0.0.1"
Confere (-not $r) "falha sem lancar erro ($script:NodeErro)"
Confere (-not (Test-Path "$dest.tmp")) "limpa a pasta temporaria"

Write-Host "== Download certo" -ForegroundColor Cyan
$t = Get-Date
$r = Install-PortableNode -Dest $dest
Confere $r "instalou ($([int]((Get-Date) - $t).TotalSeconds) s)"
$exe = Join-Path $dest "node.exe"
Confere (Test-NodeExe $exe) "node.exe roda e e' 22.18+ ($(& $exe --version))"
Confere (Test-Path (Join-Path $dest "npm.cmd")) "npm.cmd veio junto"

Write-Host "== Idempotente" -ForegroundColor Cyan
$t = Get-Date
$r = Install-PortableNode -Dest $dest -Sha256 ("0" * 64)
Confere ($r -and ((Get-Date) - $t).TotalSeconds -lt 5) "ja instalado: nao baixa de novo"

Write-Host "== Find-NousNode sem Node no computador" -ForegroundColor Cyan
$pathProc = $env:Path; $pf = $env:ProgramFiles
try {
    $env:Path = "$env:SystemRoot\System32"; $env:ProgramFiles = Join-Path $Pasta "vazio"
    Confere ((Find-NousNode $app) -eq $exe) "acha o portatil"
    Confere ($null -eq (Find-NousNode (Join-Path $Pasta "outro"))) "sem portatil e sem Node: devolve nada"
} finally { $env:Path = $pathProc; $env:ProgramFiles = $pf }

Confere ([Environment]::GetEnvironmentVariable("Path", "User") -eq $pathAntes) "o PATH do usuario nao mudou"
if ($falhas) { Write-Host "`n$falhas falha(s)" -ForegroundColor Red; exit 1 }
Write-Host "`nTudo certo." -ForegroundColor Green
