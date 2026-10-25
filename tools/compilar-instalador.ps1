<#
.SYNOPSIS
  Nous - compila o Nous-Setup.exe (Inno Setup) em dist\. NAO assina e NAO publica.
.DESCRIPTION
  Procura o ISCC.exe (PATH, Program Files, %LOCALAPPDATA%\Programs\Inno Setup 6),
  confere que a versao do .iss e' a do arquivo VERSION, compila
  installer\nous-setup.iss e escreve dist\Nous-Setup.exe + dist\Nous-Setup.exe.sha256.
  O .exe sai SEM assinatura (o Windows SmartScreen vai avisar); para assinar quando
  houver certificado: tools\assinar-instalador.ps1 (veja docs\DISTRIBUICAO.md).
  Instalar o Inno Setup so' para o seu usuario:
    winget install --id JRSoftware.InnoSetup -e --scope user
#>
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$iss  = Join-Path $root "installer\nous-setup.iss"

function Falha($t) { Write-Host "[erro] $t" -ForegroundColor Red; exit 1 }

$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    foreach ($c in (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
                   (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
                   (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")) {
        if ($c -and (Test-Path $c)) { $iscc = $c; break }
    }
}
if (-not $iscc) { Falha "Inno Setup nao encontrado. Instale com: winget install --id JRSoftware.InnoSetup -e --scope user" }

$versao = (Get-Content (Join-Path $root "VERSION") -Raw).Trim()
$noIss = ([regex]::Match((Get-Content $iss -Raw), '#define MyAppVersion "([^"]+)"')).Groups[1].Value
if ($versao -ne $noIss) { Falha "VERSION diz $versao e o nous-setup.iss diz $noIss. Acerte o #define MyAppVersion antes de compilar." }

& $iscc $iss
if ($LASTEXITCODE -ne 0) { Falha "o ISCC falhou (codigo $LASTEXITCODE)." }

$exe = Join-Path $root "dist\Nous-Setup.exe"
if (-not (Test-Path $exe)) { Falha "o ISCC terminou mas $exe nao existe." }
$h = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLower()
[IO.File]::WriteAllText("$exe.sha256", ("{0}  Nous-Setup.exe`n" -f $h), [Text.Encoding]::ASCII)
Write-Host ("`nPronto: {0}  ({1:N1} MB)" -f $exe, ((Get-Item $exe).Length / 1MB)) -ForegroundColor Green
Write-Host "SHA256: $h"
Write-Host "Sem assinatura: o SmartScreen vai avisar. Para assinar: tools\assinar-instalador.ps1" -ForegroundColor Yellow
exit 0
