<#
.SYNOPSIS
  Nous WebUI - Atualiza o Open WebUI de uma instalacao que ja existe.
.DESCRIPTION
  Chamado pelo install-nous.ps1 (passo 4) quando o ambiente ja tem o Open WebUI
  numa versao diferente da testada com o Nous. Cada passo e' desfeito se algo
  der errado, e suas conversas, memorias e documentos nao ficam em risco:

    1) para tudo o que o Nous deixou rodando neste ambiente
    2) faz um backup completo de NousData (zip em bkp\, fora o cache de modelos)
    3) instala a versao nova por cima
    4) sobe o servidor uma vez, de teste, para o Open WebUI migrar o banco, e
       confere que contas, conversas, memorias e arquivos continuam todos la'
    5) se qualquer passo falhar: volta a versao anterior do Open WebUI e o
       banco/indice do backup. O Nous segue funcionando como antes.

  Idempotente: na versao certa nao faz nada. Versao MAIS NOVA que a testada
  tambem nao e' mexida.

  Codigo de saida: 0 = ja esta na versao (ou atualizou), 1 = nao atualizou mas o
  Nous continua funcionando como antes, 2 = falhou e a volta tambem falhou (o
  backup em bkp\ tem tudo), 3 = o Open WebUI nem esta instalado neste ambiente.
.PARAMETER Venv
  Ambiente Python (padrao do Nous: %USERPROFILE%\open-webui).
.PARAMETER DataDir
  Pasta de dados (padrao: %USERPROFILE%\NousData).
.PARAMETER Pin
  Versao do Open WebUI que o Nous foi testado.
.PARAMETER Repo
  Pasta do app Nous (de onde vem apply_branding.py e onde fica o bkp\).
#>
param(
    [Parameter(Mandatory = $true)][string]$Venv,
    [Parameter(Mandatory = $true)][string]$DataDir,
    [Parameter(Mandatory = $true)][string]$Pin,
    [string]$Repo = (Split-Path $PSScriptRoot -Parent),
    [double]$EsperaMinutos = 12
)
$ErrorActionPreference = "Continue"

$vpy    = Join-Path $Venv "Scripts\python.exe"
$vexe   = Join-Path $Venv "Scripts\open-webui.exe"
$bkpDir = Join-Path $Repo "bkp"
$stamp  = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$logOW  = Join-Path $bkpDir "atualizacao-openwebui.log"

function Info($t) { Write-Host "    $t" -ForegroundColor DarkGray }
function Ok($t)   { Write-Host "    [ok] $t" -ForegroundColor Green }
function Aviso($t) { Write-Host "    [aviso] $t" -ForegroundColor Yellow }

function Get-Versao {
    if (-not (Test-Path $vpy)) { return $null }
    $o = & $vpy -c "from importlib.metadata import version; print(version('open-webui'))" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $o) { return $null }
    return (@($o)[-1]).ToString().Trim()
}

function ConvertTo-Ver($s) {
    try { return [version]($s -replace '[^0-9.].*$', '') } catch { return $null }
}

# Encerra o que roda neste ambiente (servidor, servicos do Nous): o Windows nao
# deixa o pip trocar arquivos de um Python em uso. Pelo caminho do ambiente (o
# python do venv e' so' um redirecionador; /T leva o processo de verdade junto).
function Stop-Venv {
    for ($i = 0; $i -lt 3; $i++) {
        $ps = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like "$Venv\*" })
        if (-not $ps.Count) { break }
        foreach ($p in $ps) { & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null }
        Start-Sleep -Seconds 2
    }
    return -not @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path -like "$Venv\*" }).Count
}

function Get-Contagem($db) {
    if (-not (Test-Path $db)) { return $null }
    $o = & $vpy (Join-Path $Repo "tools\contar-dados.py") $db 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $o) { return $null }
    try { return (@($o)[-1] | ConvertFrom-Json) } catch { return $null }
}

# Zip de NousData (sem a pasta cache, que so' guarda modelos baixados e volta
# sozinha). Confere o conteudo; devolve o caminho ou $null.
function New-Backup($destino) {
    try {
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        New-Item -ItemType Directory -Force -Path (Split-Path $destino) | Out-Null
        $raiz = (Resolve-Path $DataDir).Path.TrimEnd('\')
        $arqs = @(Get-ChildItem -LiteralPath $raiz -Recurse -File -Force -ErrorAction Stop |
            Where-Object { $_.FullName -notlike "$raiz\cache\*" })
        $zip = [IO.Compression.ZipFile]::Open($destino, 'Create')
        try {
            foreach ($f in $arqs) {
                $rel = $f.FullName.Substring($raiz.Length + 1).Replace('\', '/')
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $f.FullName, $rel, 'Optimal') | Out-Null
            }
        } finally { $zip.Dispose() }
        $z = [IO.Compression.ZipFile]::OpenRead($destino)
        $n = $z.Entries.Count
        $z.Dispose()
        if ($n -ne $arqs.Count) { throw "o zip tem $n arquivos, eram $($arqs.Count)" }
        return $destino
    } catch {
        Aviso "backup nao concluido: $($_.Exception.Message)"
        Remove-Item -LiteralPath $destino -Force -ErrorAction SilentlyContinue
        return $null
    }
}

# Volta o banco e o indice de busca ao que o backup guardou (so' o que o servidor
# novo pode ter mexido). webui.db-wal/-shm velhos com o banco antigo estragariam
# o banco: saem antes.
function Restore-Backup($zipPath) {
    try {
        Add-Type -AssemblyName System.IO.Compression
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        foreach ($n in "webui.db", "webui.db-wal", "webui.db-shm") {
            Remove-Item -LiteralPath (Join-Path $DataDir $n) -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath (Join-Path $DataDir "vector_db") -Recurse -Force -ErrorAction SilentlyContinue
        $z = [IO.Compression.ZipFile]::OpenRead($zipPath)
        try {
            foreach ($e in $z.Entries) {
                if ($e.FullName -notmatch '^(webui\.db|vector_db/)') { continue }
                $dest = Join-Path $DataDir ($e.FullName.Replace('/', '\'))
                New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $dest, $true)
            }
        } finally { $z.Dispose() }
        return $true
    } catch {
        Aviso "nao consegui devolver os dados: $($_.Exception.Message)"
        return $false
    }
}

function Find-PortaLivre {
    foreach ($p in 8087..8099) {
        if (-not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)) { return $p }
    }
    return 8087
}

# Sobe o servidor so' para o Open WebUI migrar o banco. Devolve $true se ficou de pe'
# na versao certa. Sempre encerra o que subiu.
function Test-Boot($esperada) {
    $porta = Find-PortaLivre
    $keyFile = Join-Path $DataDir ".webui_secret_key"
    $env:DATA_DIR = $DataDir
    $env:WEBUI_NAME = "Nous"
    $env:OLLAMA_BASE_URL = "http://127.0.0.1:11434"
    $env:WEBUI_AUTH = "True"
    $env:ENABLE_VERSION_UPDATE_CHECK = "False"
    $env:WEBUI_SECRET_KEY = $(if (Test-Path $keyFile) { (Get-Content $keyFile -Raw).Trim() } else { [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N") })
    $out = Join-Path $env:TEMP "nous-teste-boot.out.log"
    $err = Join-Path $env:TEMP "nous-teste-boot.err.log"
    Remove-Item $out, $err -Force -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $vexe -ArgumentList "serve --host 127.0.0.1 --port $porta" -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $ok = $false
    $limite = (Get-Date).AddMinutes($EsperaMinutos)
    while ((Get-Date) -lt $limite) {
        Start-Sleep -Seconds 3
        if ($p.HasExited) { break }
        try {
            if ((Invoke-WebRequest "http://127.0.0.1:$porta/health" -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200) {
                $v = Invoke-RestMethod "http://127.0.0.1:$porta/api/version" -TimeoutSec 5
                $ok = ($v.version -eq $esperada)
                break
            }
        } catch {}
    }
    if (-not $ok) {
        New-Item -ItemType Directory -Force -Path $bkpDir | Out-Null
        "== ${stamp}: o servidor de teste nao subiu na versao $esperada ==" | Out-File $logOW -Encoding utf8
        if (Test-Path $err) { Get-Content $err -Tail 60 | Out-File $logOW -Append -Encoding utf8 }
    }
    & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
    Stop-Venv | Out-Null
    return $ok
}

# --------------------------------------------------------------------------

$atual = Get-Versao
if (-not $atual -or -not (Test-Path $vexe)) { Info "Open WebUI nao esta instalado neste ambiente."; exit 3 }
$vAtual = ConvertTo-Ver $atual
$vPin = ConvertTo-Ver $Pin
if ($atual -eq $Pin) { Ok "Open WebUI $atual (a versao testada com o Nous)"; exit 0 }
if ($vAtual -and $vPin -and $vAtual -gt $vPin) {
    Aviso "o Open WebUI deste computador ($atual) e' mais novo que o testado com o Nous ($Pin): nao mexo."
    exit 0
}

Write-Host ""
Info "Atualizando o Open WebUI de $atual para $Pin (com backup; se falhar, volta ao que era)."

if (-not (Stop-Venv)) { Aviso "ha' programas do Nous que nao consegui encerrar. Feche o Nous e tente de novo."; exit 1 }

$temDados = Test-Path (Join-Path $DataDir "webui.db")
$antes = $null
$zip = $null
if ($temDados) {
    $antes = Get-Contagem (Join-Path $DataDir "webui.db")
    # espaco: o backup (comprimido, mas conte o tamanho todo) + a versao nova (~4 GB)
    $bytes = (Get-ChildItem -LiteralPath $DataDir -Recurse -File -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notlike "$DataDir\cache\*" } | Measure-Object -Property Length -Sum).Sum
    $livre = (Get-PSDrive -Name ((Resolve-Path $DataDir).Path.Substring(0, 1)) -ErrorAction SilentlyContinue).Free
    $precisa = [int64]($bytes * 1.2) + 6GB
    if ($livre -and $livre -lt $precisa) {
        Aviso ("pouco espaco em disco para atualizar com seguranca (precisa de ~{0} GB livres). O Nous segue na versao atual." -f [math]::Ceiling($precisa / 1GB))
        exit 1
    }
    $zipPath = Join-Path $bkpDir "nous-antes-do-openwebui-$Pin`_$stamp.zip"
    Info "backup dos seus dados..."
    $zip = New-Backup $zipPath
    if (-not $zip) { Aviso "sem backup nao atualizo. O Nous segue na versao atual."; exit 1 }
    Ok ("backup: $zip ({0} MB)" -f [math]::Round((Get-Item $zip).Length / 1MB, 1))
} else {
    Info "sem dados ainda (primeira vez): nada a migrar."
}

function Voltar($motivo) {
    Aviso "$motivo - voltando ao Open WebUI $atual."
    Stop-Venv | Out-Null
    & $vpy -m pip install "open-webui==$atual" --quiet | Out-Host
    $pipOk = ($LASTEXITCODE -eq 0) -and ((Get-Versao) -eq $atual)
    $dadosOk = $true
    if ($zip) { $dadosOk = Restore-Backup $zip }
    & $vpy (Join-Path $Repo "branding\apply_branding.py") --data-dir $DataDir 2>&1 | Out-Null
    if ($pipOk -and $dadosOk) { Ok "tudo como estava (Open WebUI $atual e seus dados do backup)."; return 1 }
    Aviso "a volta nao fechou por completo. Seus dados estao em: $zip"
    return 2
}

Info "instalando o Open WebUI $Pin (varios minutos)..."
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install "open-webui==$Pin" pillow
if ($LASTEXITCODE -ne 0 -or (Get-Versao) -ne $Pin) { exit (Voltar "a instalacao nao terminou") }

& $vpy (Join-Path $Repo "branding\apply_branding.py") --data-dir $DataDir 2>&1 | Out-Null

if ($temDados) {
    Info "conferindo se o servidor novo abre com os seus dados (migra o banco, ate alguns minutos)..."
    if (-not (Test-Boot $Pin)) { exit (Voltar "o servidor novo nao abriu") }
    $depois = Get-Contagem (Join-Path $DataDir "webui.db")
    if ($antes -and $depois) {
        foreach ($t in "user", "chat", "memory", "file", "knowledge", "function") {
            if ([int]$depois.$t -lt [int]$antes.$t) { exit (Voltar "depois da migracao faltam dados (${t}: $($antes.$t) -> $($depois.$t))") }
        }
    } elseif ($antes) { exit (Voltar "nao consegui conferir os dados depois da migracao") }
    Ok ("dados conferidos: {0} conta(s), {1} conversa(s), {2} memoria(s), {3} arquivo(s)" -f $depois.user, $depois.chat, $depois.memory, $depois.file)
}

# Guarda so' os 3 backups mais recentes desta troca de versao.
Get-ChildItem $bkpDir -Filter "nous-antes-do-openwebui-*.zip" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 3 | Remove-Item -Force -ErrorAction SilentlyContinue

[IO.File]::WriteAllText((Join-Path $DataDir ".atualizacao_openwebui.json"),
    (@{ de = $atual; para = $Pin; quando = (Get-Date).ToString("s"); backup = $zip } | ConvertTo-Json))
Ok "Open WebUI atualizado: $atual -> $Pin"
exit 0
