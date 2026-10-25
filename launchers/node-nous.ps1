<#
  Nous - Node.js para o Nous Code (inclui o Node portatil).
  Nao roda nada sozinho: quem precisa (o instalador e os launchers) carrega
  com ". node-nous.ps1" e chama as funcoes.

  O Nous Code precisa do Node 22.18+. Quando o computador nao tem, o
  instalador baixa o zip oficial para <app>\runtime\node, confere o SHA256
  (fixado aqui, nao o do site) e pronto: nada de instalador do Node, nada de
  PATH do sistema. Quem usa o Node chama pelo caminho completo.
#>

$script:NodeMinimo = [version]"22.18.0"
# Versao LTS (Jod) fixada. Para subir: troque a versao e os dois SHA256 (de
# https://nodejs.org/dist/vX.Y.Z/SHASUMS256.txt) e teste o bloco isolado.
$script:NodePin = @{
    Versao = "22.23.4"
    x64    = "cbc74b5e0982c9dbb41525fd8fb5dcd32fbee237863f7829072f4639a1ce5f20"
    arm64  = "a8b8cd79cbbb3062435f449591d98dd63730bbbf30ce2d7cc3a6376c236cb111"
}
$script:NodeErro = ""   # o motivo da ultima falha de Install-PortableNode

# $true se o node.exe existe e e' o 22.18 ou mais novo.
function Test-NodeExe([string]$exe) {
    if (-not $exe -or -not (Test-Path -LiteralPath $exe)) { return $false }
    try { $v = (& $exe --version 2>$null) } catch { return $false }
    if (-not $v -or ("$v" -notmatch '^v(\d+)\.(\d+)\.(\d+)')) { return $false }
    return ([version]("{0}.{1}.{2}" -f $Matches[1], $Matches[2], $Matches[3])) -ge $script:NodeMinimo
}

# A pasta do Node portatil dentro do app.
function Get-PortableNodeDir([string]$appRoot) { return Join-Path $appRoot "runtime\node" }

# O node.exe a usar: o do computador (PATH, Arquivos de Programas) se for
# bom; senao o portatil do Nous. $null quando nenhum serve.
function Find-NousNode([string]$appRoot) {
    $cands = @()
    $c = Get-Command node -ErrorAction SilentlyContinue
    if ($c -and $c.Source) { $cands += $c.Source }
    if ($env:ProgramFiles) { $cands += (Join-Path $env:ProgramFiles "nodejs\node.exe") }
    if ($appRoot) { $cands += (Join-Path (Get-PortableNodeDir $appRoot) "node.exe") }
    foreach ($e in $cands) { if (Test-NodeExe $e) { return $e } }
    return $null
}

# Baixa o zip oficial do Node, confere o SHA256 e deixa o Node em $Dest
# (node.exe direto dentro dela). Idempotente: se $Dest ja tem um Node bom,
# nao baixa nada. Nunca lanca erro: devolve $false e deixa o motivo em
# $script:NodeErro. Nada e' escrito fora de $Dest (e do irmao $Dest.tmp).
function Install-PortableNode {
    param(
        [Parameter(Mandatory = $true)][string]$Dest,
        [string]$Versao = $script:NodePin.Versao,
        [string]$Sha256 = "",
        [string]$Arq = "",
        [string]$BaseUrl = "https://nodejs.org/dist"
    )
    $script:NodeErro = ""
    if (Test-NodeExe (Join-Path $Dest "node.exe")) { return $true }
    if (-not $Arq) { $Arq = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "x64" } }
    if (-not $Sha256) { $Sha256 = $script:NodePin[$Arq] }
    if (-not $Sha256) { $script:NodeErro = "arquitetura sem Node fixado: $Arq"; return $false }
    $nome = "node-v$Versao-win-$Arq"
    $url  = "$BaseUrl/v$Versao/$nome.zip"
    $tmp  = "$Dest.tmp"
    $zip  = "$tmp\$nome.zip"
    try {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
        $old = $ProgressPreference; $ProgressPreference = "SilentlyContinue"
        try { Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 600 } finally { $ProgressPreference = $old }
        $h = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
        if ($h -ne $Sha256.ToUpper()) {
            $script:NodeErro = "o arquivo baixado nao confere com o SHA256 esperado (recebido $h); descartado"
            Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
            return $false
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, "$tmp\x")
        $dentro = Join-Path "$tmp\x" $nome
        if (-not (Test-NodeExe (Join-Path $dentro "node.exe"))) { throw "o Node baixado nao roda aqui" }
        if (Test-Path -LiteralPath $Dest) { Remove-Item -LiteralPath $Dest -Recurse -Force }
        New-Item -ItemType Directory -Path (Split-Path $Dest -Parent) -Force | Out-Null
        Move-Item -LiteralPath $dentro -Destination $Dest
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        return (Test-NodeExe (Join-Path $Dest "node.exe"))
    } catch {
        $script:NodeErro = $_.Exception.Message
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        return $false
    }
}
