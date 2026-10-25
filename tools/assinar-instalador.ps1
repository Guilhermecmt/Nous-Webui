<#
.SYNOPSIS
  Nous - assina o Nous-Setup.exe. FICA PARADO (com aviso) enquanto nao houver certificado.
.DESCRIPTION
  Hoje o Nous NAO tem certificado de assinatura: o instalador sai sem assinatura e o
  Windows SmartScreen avisa "editor desconhecido". Este script e' o que se roda no dia
  em que houver certificado. Passo a passo e custos: docs\DISTRIBUICAO.md.

  -Metodo pfx     certificado em arquivo .pfx (-Pfx) e senha na variavel de ambiente
                  indicada em -SenhaVar (padrao NOUS_PFX_SENHA; nunca na linha de comando).
  -Metodo azure   Azure Trusted Signing (-AzureDlib = Azure.CodeSigning.Dlib.dll,
                  -AzureMetadata = o .json com endpoint, conta e perfil).
  Sem -Metodo ou sem os dados do metodo: so' explica o que falta e sai com codigo 2.
.PARAMETER Arquivo
  O que assinar (padrao dist\Nous-Setup.exe).
.PARAMETER Timestamp
  Servidor de carimbo de data/hora (padrao: o da DigiCert para pfx; o da Microsoft para azure).
#>
param(
    [ValidateSet("", "pfx", "azure")][string]$Metodo = "",
    [string]$Arquivo,
    [string]$Pfx,
    [string]$SenhaVar = "NOUS_PFX_SENHA",
    [string]$AzureDlib,
    [string]$AzureMetadata,
    [string]$Timestamp
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
if (-not $Arquivo) { $Arquivo = Join-Path $root "dist\Nous-Setup.exe" }

function Parado($motivo) {
    Write-Host ""
    Write-Host "Assinatura NAO feita: $motivo" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "O Nous ainda nao tem certificado de assinatura de codigo (decisao: seguir sem por enquanto;"
    Write-Host "o SmartScreen vai avisar quem instalar). O Nous-Setup.exe de dist\ continua valido, so' sem assinatura."
    Write-Host "Quando houver certificado, leia docs\DISTRIBUICAO.md e rode, por exemplo:"
    Write-Host '  $env:NOUS_PFX_SENHA = "..." ; .\tools\assinar-instalador.ps1 -Metodo pfx -Pfx C:\caminho\nous.pfx'
    Write-Host '  .\tools\assinar-instalador.ps1 -Metodo azure -AzureDlib C:\...\Azure.CodeSigning.Dlib.dll -AzureMetadata C:\...\metadata.json'
    exit 2
}

if (-not $Metodo) { Parado "nenhum -Metodo informado (pfx ou azure)." }
if (-not (Test-Path -LiteralPath $Arquivo)) { Write-Host "[erro] nao achei $Arquivo (rode tools\compilar-instalador.ps1)." -ForegroundColor Red; exit 1 }

# signtool.exe: vem no Windows SDK (kit "Signing Tools for Desktop Apps")
$signtool = (Get-Command signtool.exe -ErrorAction SilentlyContinue).Source
if (-not $signtool) {
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kits) {
        $signtool = Get-ChildItem $kits -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\x64\' } | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
    }
}
if (-not $signtool) { Parado "signtool.exe nao encontrado (instale o Windows SDK: winget install Microsoft.WindowsSDK.10.0.26100)." }

if ($Metodo -eq "pfx") {
    if (-not $Pfx -or -not (Test-Path -LiteralPath $Pfx)) { Parado "informe o certificado com -Pfx (arquivo .pfx existente)." }
    $senha = [Environment]::GetEnvironmentVariable($SenhaVar)
    if (-not $senha) { Parado "a senha do .pfx deve estar na variavel de ambiente $SenhaVar." }
    $ts = if ($Timestamp) { $Timestamp } else { "http://timestamp.digicert.com" }
    & $signtool sign /fd SHA256 /f $Pfx /p $senha /tr $ts /td SHA256 /d "Nous" /du "https://github.com/Guilhermecmt/Nous-Webui" $Arquivo
}
else {
    if (-not $AzureDlib -or -not (Test-Path -LiteralPath $AzureDlib)) { Parado "informe -AzureDlib (Azure.CodeSigning.Dlib.dll)." }
    if (-not $AzureMetadata -or -not (Test-Path -LiteralPath $AzureMetadata)) { Parado "informe -AzureMetadata (o .json do Trusted Signing)." }
    $ts = if ($Timestamp) { $Timestamp } else { "http://timestamp.acs.microsoft.com" }
    & $signtool sign /v /fd SHA256 /tr $ts /td SHA256 /dlib $AzureDlib /dlibcs $AzureMetadata $Arquivo
}
if ($LASTEXITCODE -ne 0) { Write-Host "[erro] o signtool falhou (codigo $LASTEXITCODE)." -ForegroundColor Red; exit 1 }

& $signtool verify /pa $Arquivo
if ($LASTEXITCODE -ne 0) { Write-Host "[erro] a assinatura nao passou na verificacao." -ForegroundColor Red; exit 1 }
# o hash mudou com a assinatura
$h = (Get-FileHash -LiteralPath $Arquivo -Algorithm SHA256).Hash.ToLower()
[IO.File]::WriteAllText("$Arquivo.sha256", ("{0}  {1}`n" -f $h, (Split-Path $Arquivo -Leaf)), [Text.Encoding]::ASCII)
Write-Host "Assinado e verificado. Novo SHA256: $h" -ForegroundColor Green
exit 0
