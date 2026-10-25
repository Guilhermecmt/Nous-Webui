<#
.SYNOPSIS
  Nous - gera o pacote de uma release (zip + SHA256). NAO publica nada.
.DESCRIPTION
  Cria dist\Nous-X.Y.Z.zip com os arquivos versionados do commit escolhido
  (sem .github, mockups e screenshots) e dist\Nous-X.Y.Z.zip.sha256 com a linha
  "<hash>  Nous-X.Y.Z.zip". E' o par que o atualizador do Nous (atualizacao\
  nous-atualizar.ps1) baixa e confere. Tambem usado pelo workflow release.yml.
  Se dist\Nous-Setup.exe existir (tools\compilar-instalador.ps1), gera o .sha256 dele.

  Publicar (a mao, depois de conferir os arquivos):
    gh release create vX.Y.Z dist\Nous-X.Y.Z.zip dist\Nous-X.Y.Z.zip.sha256 [dist\Nous-Setup.exe ...] --draft
.PARAMETER Origem
  Commit/branch/tag a empacotar (padrao: HEAD).
.PARAMETER Saida
  Pasta de saida (padrao: dist\ na raiz do repositorio).
#>
param(
    [string]$Origem = "HEAD",
    [string]$Saida
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
if (-not $Saida) { $Saida = Join-Path $root "dist" }
Set-Location $root

function Falha($t) { Write-Host "[erro] $t" -ForegroundColor Red; exit 1 }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Falha "git nao encontrado." }
$commit = (& git rev-parse --verify "$Origem^{commit}" 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $commit) { Falha "nao achei o commit '$Origem'." }
$versao = (& git show "${commit}:VERSION").Trim()
if ($versao -notmatch '^\d+\.\d+\.\d+$') { Falha "VERSION do commit tem '$versao' (esperado X.Y.Z)." }
if ($Origem -eq "HEAD" -and (& git status --porcelain --untracked-files=no)) {
    Write-Host "[aviso] ha mudancas nao commitadas: o pacote leva so' o que esta no commit." -ForegroundColor Yellow
}

New-Item -ItemType Directory -Force -Path $Saida | Out-Null
$zip = Join-Path $Saida "Nous-$versao.zip"
Remove-Item -LiteralPath $zip, "$zip.sha256" -Force -ErrorAction SilentlyContinue

# Mesmo corte do nous-setup.iss: fora o que e' so' de desenvolvimento.
& git archive --format=zip -o $zip $commit -- . ":(exclude).github" ":(exclude)mockups" ":(exclude)docs/screenshots"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $zip)) { Falha "git archive falhou." }

# Confere o conteudo: o atualizador recusa pacote sem estes arquivos.
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z = [IO.Compression.ZipFile]::OpenRead($zip)
try {
    $nomes = @($z.Entries | ForEach-Object { $_.FullName })
    foreach ($n in "VERSION", "launchers/start-nous.ps1", "launchers/stop-nous.ps1", "installer/install-nous.ps1",
                   "monitor/nous_monitor.py", "atualizacao/nous-atualizar.ps1") {
        if ($nomes -notcontains $n) { Falha "o pacote nao tem $n." }
    }
    if ($nomes | Where-Object { $_ -like ".github/*" -or $_ -like "mockups/*" }) { Falha "o pacote levou arquivo de desenvolvimento." }
} finally { $z.Dispose() }

function Grava-Hash([string]$arquivo) {
    $h = (Get-FileHash -LiteralPath $arquivo -Algorithm SHA256).Hash.ToLower()
    # ASCII + LF: igual ao que "sha256sum" escreve, qualquer ferramenta le.
    [IO.File]::WriteAllText("$arquivo.sha256", ("{0}  {1}`n" -f $h, (Split-Path $arquivo -Leaf)), [Text.Encoding]::ASCII)
    return $h
}
$hash = Grava-Hash $zip
Write-Host ("Pacote:  {0}  ({1:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB)) -ForegroundColor Green
Write-Host ("SHA256:  {0}" -f $hash)
$setup = Join-Path $Saida "Nous-Setup.exe"
if (Test-Path $setup) {
    $hs = Grava-Hash $setup
    Write-Host ("Setup:   {0}  SHA256 {1}" -f $setup, $hs)
}
Write-Host ""
Write-Host "Nada foi publicado. Para publicar (rascunho, a voce confere antes de liberar):" -ForegroundColor DarkGray
Write-Host "  gh release create v$versao `"$zip`" `"$zip.sha256`" --draft --title `"Nous $versao`"" -ForegroundColor DarkGray
exit 0
