<#
  Nous - llama-server (llama.cpp, build Vulkan) do motor de IA proprio.
  Dot-source: . launchers\llama-nous.ps1
  A versao e o SHA256 ficam em motor\LLAMA_VERSAO.json (fixados e testados com o
  Nous). O zip oficial do GitHub do llama.cpp (~40 MB) vai para <app>\motor\bin;
  nada fora da pasta do Nous muda. Usado pelo instalador e pelo atualizador.
#>

function Get-LlamaPin([string]$AppDir) {
    $f = Join-Path $AppDir "motor\LLAMA_VERSAO.json"
    if (-not (Test-Path -LiteralPath $f)) { return $null }
    try { return (Get-Content -LiteralPath $f -Raw | ConvertFrom-Json) } catch { return $null }
}

function Get-LlamaDir([string]$AppDir) { return (Join-Path $AppDir "motor\bin") }

function Test-LlamaExe([string]$Exe) {
    if (-not $Exe -or -not (Test-Path -LiteralPath $Exe)) { return $false }
    try {
        $p = Start-Process -FilePath $Exe -ArgumentList "--version" -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput "$env:TEMP\nous-llama-v.out" -RedirectStandardError "$env:TEMP\nous-llama-v.err"
        return ($p.ExitCode -eq 0)
    } catch { return $false }
}

# Ja' tem o llama-server certo (mesma tag do LLAMA_VERSAO.json) e ele roda?
function Test-LlamaAtual([string]$AppDir) {
    $pin = Get-LlamaPin $AppDir
    $dir = Get-LlamaDir $AppDir
    if (-not $pin) { return $false }
    $marca = Join-Path $dir "versao.txt"
    if (-not (Test-Path -LiteralPath $marca)) { return $false }
    if ((Get-Content -LiteralPath $marca -Raw).Trim() -ne $pin.tag) { return $false }
    return (Test-LlamaExe (Join-Path $dir $pin.exe))
}

# Baixa, confere o SHA256 e instala. Devolve $true/$false; o motivo da falha fica
# em $script:LlamaErro. -Url/-Sha256 so' para teste.
function Install-LlamaServer {
    param(
        [Parameter(Mandatory = $true)][string]$AppDir,
        [string]$Url = "",
        [string]$Sha256 = ""
    )
    $script:LlamaErro = ""
    if (Test-LlamaAtual $AppDir) { return $true }
    $pin = Get-LlamaPin $AppDir
    if (-not $pin) { $script:LlamaErro = "falta motor\LLAMA_VERSAO.json"; return $false }
    if (-not $Url) { $Url = $pin.zip }
    if (-not $Sha256) { $Sha256 = $pin.sha256 }
    $dest = Get-LlamaDir $AppDir
    $tmp = "$dest.tmp"
    $zip = Join-Path $tmp "llama.zip"
    try {
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
        New-Item -ItemType Directory -Path $tmp -Force | Out-Null
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
        $old = $ProgressPreference; $ProgressPreference = "SilentlyContinue"
        try { Invoke-WebRequest -Uri $Url -OutFile $zip -UseBasicParsing -TimeoutSec 600 } finally { $ProgressPreference = $old }
        $h = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
        if ($h -ne $Sha256.ToUpper()) {
            $script:LlamaErro = "o arquivo baixado nao confere com o SHA256 esperado (recebido $h); descartado"
            Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
            return $false
        }
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, "$tmp\x")
        $exe = Get-ChildItem -LiteralPath "$tmp\x" -Recurse -Filter $pin.exe | Select-Object -First 1
        if (-not $exe -or -not (Test-LlamaExe $exe.FullName)) { throw "o llama-server baixado nao roda aqui" }
        [IO.File]::WriteAllText((Join-Path $exe.DirectoryName "versao.txt"), $pin.tag)
        if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force }
        Move-Item -LiteralPath $exe.DirectoryName -Destination $dest
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        return (Test-LlamaAtual $AppDir)
    } catch {
        $script:LlamaErro = $_.Exception.Message
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
        return $false
    }
}
