<#
  Nous - Atualizacao do app e dos modelos.

  Acoes:
    Verificar  Pergunta ao GitHub qual e' a ultima release do Nous (no maximo 1 vez por dia).
    Modelos    Compara o digest de cada modelo instalado com o do registro do Ollama.
    Tudo       Verificar + Modelos (e' o que a bandeja chama).
    Aplicar    Baixa a release, confere o SHA256, faz backup, troca os arquivos e
               reinicia; se algo falhar, volta ao que era.

  Privacidade: checar e' uma ida a' internet (api.github.com e registry.ollama.ai,
  sem enviar dado nenhum seu alem do pedido). O usuario desliga em
  NousData\atualizacao-config.json ("verificar": false) pelo menu da bandeja.
  Nada e' baixado sem o clique em "Atualizar".

  Formato da release (ver docs/DISTRIBUICAO.md): tag vX.Y.Z com os arquivos
  Nous-X.Y.Z.zip e Nous-X.Y.Z.zip.sha256 (uma linha: "<hash>  Nous-X.Y.Z.zip").

  Estado para o painel/bandeja: NousData\atualizacao-estado.json
  Registro do que aconteceu:    NousData\atualizacao\atualizacao.log
#>
param(
    [ValidateSet("Verificar", "Modelos", "Tudo", "Aplicar")][string]$Acao = "Tudo",
    [switch]$Forcar,                 # ignora o limite de 1 vez por dia e o "desligado" (clique do usuario)
    [string]$AppDir,                 # padrao: a pasta acima deste script
    [string]$DataDir,                # padrao: %USERPROFILE%\NousData
    [string]$Venv,                   # padrao: %USERPROFILE%\open-webui
    [string]$ApiUrl = "https://api.github.com/repos/Guilhermecmt/Nous-Webui/releases/latest",
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [string]$RegistroUrl = "https://registry.ollama.ai",
    [string]$PortaNous = "8080",
    [switch]$ModoTeste               # aceita URLs locais; nao para/inicia o Nous nem mexe no registro do Windows
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

if (-not $AppDir)  { $AppDir  = Split-Path $PSScriptRoot -Parent }
if (-not $DataDir) { $DataDir = Join-Path $env:USERPROFILE "NousData" }
if (-not $Venv)    { $Venv    = Join-Path $env:USERPROFILE "open-webui" }
$AppDir = $AppDir.TrimEnd('\')

$cfgPath    = Join-Path $DataDir "atualizacao-config.json"
$estadoPath = Join-Path $DataDir "atualizacao-estado.json"
$trabalho   = Join-Path $DataDir "atualizacao"
$logPath    = Join-Path $trabalho "atualizacao.log"
$HOSTS_OK   = '^https://(github\.com|api\.github\.com|objects\.githubusercontent\.com|release-assets\.githubusercontent\.com)/'
$EXCLUI_DIRS  = @("bkp", "node_modules", "__pycache__", ".git")
$EXCLUI_ARQ   = @("*.sqlite", "*.log", ".webui_secret_key", "*.local", "*.pyc")

New-Item -ItemType Directory -Force -Path $trabalho | Out-Null

function Log([string]$t) {
    $linha = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $t
    try { Add-Content -LiteralPath $logPath -Value $linha -Encoding ASCII } catch {}
    Write-Host $linha
}
function Read-Json([string]$p) {
    if (Test-Path -LiteralPath $p) { try { return (Get-Content -LiteralPath $p -Raw | ConvertFrom-Json) } catch {} }
    return $null
}
# UTF-8 sem BOM (Set-Content -Encoding UTF8 poe BOM no PS 5.1)
function Write-Json([string]$p, $obj) {
    [IO.File]::WriteAllText($p, (ConvertTo-Json -InputObject $obj -Depth 6))
}
function Get-Config {
    $c = Read-Json $cfgPath
    $r = [ordered]@{ verificar = $true; bandeja = $true }
    if ($c) {
        if ($null -ne $c.verificar) { $r.verificar = [bool]$c.verificar }
        if ($null -ne $c.bandeja)   { $r.bandeja   = [bool]$c.bandeja }
    }
    return $r
}
function Get-Estado {
    $e = [ordered]@{}
    $o = Read-Json $estadoPath
    if ($o) { foreach ($p in $o.PSObject.Properties) { $e[$p.Name] = $p.Value } }
    return $e
}
# Mescla chaves no estado (le, altera, grava) - quem le (painel/bandeja) nunca ve arquivo pela metade.
function Set-Estado([hashtable]$kv) {
    $e = Get-Estado
    foreach ($k in $kv.Keys) { $e[$k] = $kv[$k] }
    $tmp = "$estadoPath.tmp"
    Write-Json $tmp $e
    Move-Item -LiteralPath $tmp -Destination $estadoPath -Force
}
function Get-VersaoInstalada {
    $v = Join-Path $AppDir "VERSION"
    if (Test-Path -LiteralPath $v) { return (Get-Content -LiteralPath $v -Raw).Trim() }
    return "0.0.0"
}
function ConvertTo-Versao([string]$s) {
    $t = ("$s").Trim().TrimStart('v', 'V')
    $t = ($t -split '[-+]')[0]
    try { return [version]$t } catch { return $null }
}
function Test-Recente([string]$iso, [int]$horas) {
    if (-not $iso) { return $false }
    try { return ((Get-Date) - [datetime]::Parse($iso, [Globalization.CultureInfo]::InvariantCulture)).TotalHours -lt $horas } catch { return $false }
}
function Invoke-Api([string]$url, [int]$seg = 20) {
    $h = @{ "User-Agent" = "Nous-Atualizador/$(Get-VersaoInstalada)"; "Accept" = "application/vnd.github+json" }
    return Invoke-RestMethod -Uri $url -Headers $h -TimeoutSec $seg -UseBasicParsing
}
function Test-UrlPermitida([string]$url) {
    if ($ModoTeste) { return ($url -match '^http://127\.0\.0\.1:94\d\d/') -or ($url -match $HOSTS_OK) }
    return ($url -match $HOSTS_OK)
}

# ---------------------------------------------------------------- release ----

# Devolve @{ versao; zip; sha; notas; tamanho } ou $null se ainda nao ha release.
function Get-UltimaRelease {
    try { $rel = Invoke-Api $ApiUrl }
    catch {
        $st = $null
        try { $st = [int]$_.Exception.Response.StatusCode } catch {}
        if ($st -eq 404) { return $null }
        throw
    }
    $ver = ("$($rel.tag_name)").TrimStart('v', 'V')
    if (-not (ConvertTo-Versao $ver)) { throw "a release '$($rel.tag_name)' nao tem um numero de versao valido" }
    $zip = @($rel.assets | Where-Object { $_.name -match '^Nous-[0-9][0-9.]*\.zip$' }) | Select-Object -First 1
    $sha = @($rel.assets | Where-Object { $_.name -match '^Nous-[0-9][0-9.]*\.zip\.sha256$' }) | Select-Object -First 1
    if (-not $zip -or -not $sha) { throw "a release $ver nao traz o pacote .zip com o .sha256" }
    $notas = "$($rel.body)"
    if ($notas.Length -gt 800) { $notas = $notas.Substring(0, 800) + "..." }
    return @{ versao = $ver; zip = $zip.browser_download_url; sha = $sha.browser_download_url
              notas = $notas; tamanho = [int64]$zip.size }
}

function Invoke-Verificar {
    $cfg = Get-Config
    $est = Get-Estado
    if (-not $Forcar) {
        if (-not $cfg.verificar) { Log "verificacao automatica desligada - nada a fazer"; return }
        if (Test-Recente $est.ultima_verificacao 24) { Log "ja verifiquei nas ultimas 24 h"; return }
    }
    $agora = (Get-Date).ToString("s")
    $atual = Get-VersaoInstalada
    try {
        $r = Get-UltimaRelease
    } catch {
        Log "nao consegui consultar o GitHub: $($_.Exception.Message)"
        # grava a tentativa mesmo assim (sem internet nao fica insistindo toda hora)
        Set-Estado @{ ultima_verificacao = $agora; versao_atual = $atual; erro = "Sem conexao para procurar atualizacao." }
        return
    }
    if (-not $r) {
        Log "ainda nao ha release publicada"
        Set-Estado @{ ultima_verificacao = $agora; versao_atual = $atual; disponivel = $false; erro = $null }
        return
    }
    $nova = (ConvertTo-Versao $r.versao) -gt (ConvertTo-Versao $atual)
    Log ("instalada {0}, ultima release {1}: {2}" -f $atual, $r.versao, $(if ($nova) { "ha atualizacao" } else { "em dia" }))
    Set-Estado @{
        ultima_verificacao = $agora; versao_atual = $atual; disponivel = [bool]$nova; erro = $null
        versao_nova = $(if ($nova) { $r.versao } else { $null })
        notas = $(if ($nova) { $r.notas } else { $null })
        tamanho_mb = $(if ($nova) { [math]::Round($r.tamanho / 1MB, 1) } else { $null })
    }
}

# ---------------------------------------------------------------- modelos ----

function Get-RegistroManifestoUrl([string]$nome) {
    $base, $tag = $nome -split ':', 2
    if (-not $tag) { $tag = "latest" }
    $caminho = if ($base.Contains("/")) { $base } else { "library/$base" }
    return "$($RegistroUrl.TrimEnd('/'))/v2/$caminho/manifests/$tag"
}

function Invoke-Modelos {
    $cfg = Get-Config
    $est = Get-Estado
    if (-not $Forcar) {
        if (-not $cfg.verificar) { Log "modelos: verificacao automatica desligada"; return }
        if (Test-Recente $est.modelos_verificados_em 24) { Log "modelos: ja verifiquei nas ultimas 24 h"; return }
    }
    try { $tags = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -TimeoutSec 5 }
    catch { Log "modelos: o Ollama nao esta no ar - fica para a proxima"; return }
    $novos = @()
    $falhas = 0
    foreach ($m in @($tags.models)) {
        $nome = "$($m.name)"
        # so' o registro do Ollama: modelos do Hugging Face (hf.co/...), de nuvem e criados a mao ficam de fora
        if (-not $nome -or $nome -like "hf.co/*" -or $nome -like "*-cloud*" -or $m.remote_host) { continue }
        if ($falhas -ge 3) { break }
        try {
            $resp = Invoke-WebRequest -Uri (Get-RegistroManifestoUrl $nome) -Method Head -UseBasicParsing -TimeoutSec 15 `
                -Headers @{ Accept = "application/vnd.docker.distribution.manifest.v2+json"; "User-Agent" = "Nous-Atualizador" }
            $remoto = "$($resp.Headers['Docker-Content-Digest'])" -replace '^sha256:', ''
            $local = "$($m.digest)" -replace '^sha256:', ''
            if ($remoto -and $local -and ($remoto.ToLower() -ne $local.ToLower())) {
                $novos += @{ nome = $nome; digest_local = $local.Substring(0, 12); digest_novo = $remoto.Substring(0, 12) }
            }
            $falhas = 0
        } catch {
            $st = $null
            try { $st = [int]$_.Exception.Response.StatusCode } catch {}
            if ($st -ne 404 -and $st -ne 401) { $falhas++ }   # 404 = modelo que nao e' do registro (criado a mao)
        }
    }
    if ($falhas -ge 3) { Log "modelos: sem conexao com o registro do Ollama"; return }
    Log ("modelos: {0} instalado(s), {1} com versao nova" -f @($tags.models).Count, $novos.Count)
    Set-Estado @{ modelos_verificados_em = (Get-Date).ToString("s"); modelos_novos = @($novos) }
}

# ---------------------------------------------------------------- aplicar ----

function Test-NousRodando {
    try {
        $c = New-Object Net.Sockets.TcpClient
        $iar = $c.BeginConnect("127.0.0.1", [int]$PortaNous, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(500) -and $c.Connected
        $c.Close()
        return [bool]$ok
    } catch { return $false }
}
function Test-NousSaudavel {
    try { return (Invoke-WebRequest "http://127.0.0.1:$PortaNous/health" -TimeoutSec 3 -UseBasicParsing).StatusCode -eq 200 }
    catch { return $false }
}
function Stop-Nous {
    if ($ModoTeste) { Log "(teste) pularia: parar o Nous"; return }
    $s = Join-Path $AppDir "launchers\stop-nous.ps1"
    if (Test-Path -LiteralPath $s) { & powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $s | Out-Null }
    Start-Sleep -Seconds 2
}
function Start-Nous {
    if ($ModoTeste) { Log "(teste) pularia: iniciar o Nous"; return }
    # NOUS_SEM_NAVEGADOR: o start-nous.ps1 nao abre outra aba (a pagina aberta se recarrega sozinha)
    $env:NOUS_SEM_NAVEGADOR = "1"
    Start-Process wscript.exe -ArgumentList ('"{0}"' -f (Join-Path $AppDir "launchers\nous-hidden.vbs")) -WindowStyle Hidden
}
function Get-BandejaPids {
    if ($ModoTeste) { return @() }
    return @(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*bandeja.ps1*" } | ForEach-Object { $_.ProcessId })
}

function Copy-App([string]$de, [string]$para) {
    $ra = @($de, $para, "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:2", "/W:2", "/XD") + $EXCLUI_DIRS + @("/XF") + $EXCLUI_ARQ
    & robocopy @ra | Out-Null
    return ($LASTEXITCODE -lt 8)
}

function Save-File([string]$url, [string]$destino, [int64]$esperado) {
    $req = [Net.HttpWebRequest]::Create($url)
    $req.UserAgent = "Nous-Atualizador/$(Get-VersaoInstalada)"
    $req.Timeout = 30000
    $req.ReadWriteTimeout = 30000
    $resp = $req.GetResponse()
    try {
        $total = if ($resp.ContentLength -gt 0) { $resp.ContentLength } else { $esperado }
        $in = $resp.GetResponseStream()
        $out = [IO.File]::Create($destino)
        try {
            $buf = New-Object 'byte[]' 262144
            $lido = [int64]0
            $marca = Get-Date
            while (($n = $in.Read($buf, 0, $buf.Length)) -gt 0) {
                $out.Write($buf, 0, $n)
                $lido += $n
                if (((Get-Date) - $marca).TotalMilliseconds -gt 800) {
                    $marca = Get-Date
                    $pct = if ($total -gt 0) { [int](100 * $lido / $total) } else { 0 }
                    Set-Estado @{ fase = "baixando"; pct = $pct; mensagem = "Baixando a atualizacao ($pct%)..." }
                }
            }
        } finally { $out.Close(); $in.Close() }
    } finally { $resp.Close() }
}

function Invoke-Aplicar {
    $inicio = Get-Date
    $atual = Get-VersaoInstalada
    Set-Estado @{ fase = "preparando"; pct = 0; mensagem = "Preparando a atualizacao..."; erro = $null; resultado = $null }
    $falha = {
        param($msg)
        Log "FALHOU: $msg"
        Set-Estado @{ fase = "falhou"; pct = 0; mensagem = $msg; resultado = "falhou" }
    }

    # 1) qual release? (consulta de novo: nao confia no arquivo de estado)
    try { $r = Get-UltimaRelease } catch { & $falha "Nao consegui falar com o GitHub. Veja a internet e tente de novo."; return 1 }
    if (-not $r) { & $falha "Ainda nao ha versao nova publicada."; return 1 }
    if (-not ((ConvertTo-Versao $r.versao) -gt (ConvertTo-Versao $atual))) {
        Log "ja esta na versao mais nova ($atual)"
        Set-Estado @{ fase = "concluida"; disponivel = $false; mensagem = "O Nous ja esta na versao mais nova."; resultado = "em-dia" }
        return 0
    }
    foreach ($u in $r.zip, $r.sha) {
        if (-not (Test-UrlPermitida $u)) { & $falha "Endereco de download nao confiavel: $u"; return 1 }
    }
    Log "atualizando $atual -> $($r.versao)"

    # 2) espaco em disco (zip + extraido + backup, com folga)
    try {
        $unidade = (Get-Item -LiteralPath $DataDir).PSDrive
        $livre = $unidade.Free
        $precisa = [int64](($r.tamanho * 6) + 200MB)
        if ($livre -and $livre -lt $precisa) {
            & $falha ("Falta espaco no disco: preciso de uns {0} MB livres." -f [math]::Ceiling($precisa / 1MB)); return 1
        }
    } catch {}

    # 3) baixar + conferir o SHA256
    $dl = Join-Path $trabalho "baixado"
    Remove-Item -LiteralPath $dl -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $dl | Out-Null
    $zipLocal = Join-Path $dl "Nous-$($r.versao).zip"
    try {
        Save-File $r.zip $zipLocal $r.tamanho
        $shaTxt = (Invoke-WebRequest -Uri $r.sha -UseBasicParsing -TimeoutSec 20 -Headers @{ "User-Agent" = "Nous-Atualizador" }).Content
        if ($shaTxt -is [byte[]]) { $shaTxt = [Text.Encoding]::ASCII.GetString($shaTxt) }
    } catch {
        & $falha "O download nao terminou. Veja a internet e tente de novo. Nada foi alterado."
        Log $_.Exception.Message; return 1
    }
    Set-Estado @{ fase = "conferindo"; pct = 100; mensagem = "Conferindo se o arquivo esta integro..." }
    $esperado = ([regex]::Match("$shaTxt", '(?i)\b[0-9a-f]{64}\b')).Value.ToLower()
    $obtido = (Get-FileHash -LiteralPath $zipLocal -Algorithm SHA256).Hash.ToLower()
    if (-not $esperado -or $obtido -ne $esperado) {
        Remove-Item -LiteralPath $dl -Recurse -Force -ErrorAction SilentlyContinue
        & $falha "O arquivo baixado nao confere com a assinatura SHA256 publicada. Nada foi alterado."
        Log "esperado=$esperado obtido=$obtido"; return 1
    }
    Log "SHA256 confere ($obtido)"

    # 4) extrair e validar o pacote antes de tocar no app
    $stage = Join-Path $dl "novo"
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($zipLocal, $stage)
    } catch { & $falha "O pacote da atualizacao esta corrompido. Nada foi alterado."; Log $_.Exception.Message; return 1 }
    $obrig = "VERSION", "launchers\start-nous.ps1", "launchers\stop-nous.ps1", "installer\install-nous.ps1",
             "monitor\nous_monitor.py", "atualizacao\nous-atualizar.ps1"
    foreach ($o in $obrig) {
        if (-not (Test-Path -LiteralPath (Join-Path $stage $o))) { & $falha "O pacote da atualizacao esta incompleto (falta $o). Nada foi alterado."; return 1 }
    }
    $verPacote = (Get-Content -LiteralPath (Join-Path $stage "VERSION") -Raw).Trim()
    if ($verPacote -ne $r.versao) { & $falha "O pacote diz ser a versao $verPacote, mas a release e' $($r.versao). Nada foi alterado."; return 1 }

    # 5) backup do app atual (so' o ultimo fica guardado)
    Set-Estado @{ fase = "instalando"; pct = 100; mensagem = "Guardando uma copia da versao atual..." }
    $bkpRoot = Join-Path $trabalho "backup"
    $bkp = Join-Path $bkpRoot "nous-$atual"
    Remove-Item -LiteralPath $bkpRoot -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $bkp | Out-Null
    if (-not (Copy-App $AppDir $bkp)) { & $falha "Nao consegui guardar a copia de seguranca. Nada foi alterado."; return 1 }
    Log "backup em $bkp"

    # 6) trocar os arquivos (com o Nous parado)
    $estavaRodando = (-not $ModoTeste) -and (Test-NousRodando)
    $bandeja = Get-BandejaPids
    Set-Estado @{ fase = "instalando"; mensagem = "Instalando a versao $($r.versao)..." }
    Stop-Nous
    foreach ($b in $bandeja) { Stop-Process -Id $b -Force -ErrorAction SilentlyContinue }
    $lockAntigo = Get-FileHash -LiteralPath (Join-Path $AppDir "code\package-lock.json") -ErrorAction SilentlyContinue
    $pinAntigo = ([regex]::Match((Get-Content -LiteralPath (Join-Path $AppDir "installer\install-nous.ps1") -Raw -ErrorAction SilentlyContinue), '\$OPENWEBUI_PIN\s*=\s*"([\d.]+)"')).Groups[1].Value

    $reverter = {
        param($motivo)
        Log "voltando para a versao $atual ($motivo)"
        Stop-Nous
        if (-not (Copy-App $bkp $AppDir)) { Log "ERRO ao restaurar o backup; copia completa em $bkp" }
        if ($estavaRodando) { Start-Nous }
        if ($bandeja.Count -gt 0 -and -not $ModoTeste) { Start-Process wscript.exe -ArgumentList ('"{0}"' -f (Join-Path $AppDir "launchers\bandeja.vbs")) -WindowStyle Hidden }
        Set-Estado @{ fase = "revertida"; resultado = "revertida"; disponivel = $true
                      mensagem = "A atualizacao nao deu certo e o Nous voltou para a versao $atual. $motivo" }
    }
    if (-not (Copy-App $stage $AppDir)) { & $reverter "Nao consegui copiar os arquivos novos."; return 1 }

    # 7) pecas que dependem do pacote: Open WebUI (pin) e dependencias do Nous Code
    if (-not $ModoTeste) {
        $pinNovo = ([regex]::Match((Get-Content -LiteralPath (Join-Path $AppDir "installer\install-nous.ps1") -Raw), '\$OPENWEBUI_PIN\s*=\s*"([\d.]+)"')).Groups[1].Value
        $vpy = Join-Path $Venv "Scripts\python.exe"
        if ($pinNovo -and $pinNovo -ne $pinAntigo -and (Test-Path -LiteralPath $vpy)) {
            Set-Estado @{ mensagem = "Atualizando o Open WebUI para a versao $pinNovo (pode levar varios minutos)..." }
            & $vpy -m pip install "open-webui==$pinNovo" --quiet 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                & $vpy -m pip install "open-webui==$pinAntigo" --quiet 2>&1 | Out-Null
                & $reverter "Nao consegui atualizar o Open WebUI."; return 1
            }
        }
        $lockNovo = Get-FileHash -LiteralPath (Join-Path $AppDir "code\package-lock.json") -ErrorAction SilentlyContinue
        $node = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if ($lockNovo -and $node -and (-not $lockAntigo -or $lockAntigo.Hash -ne $lockNovo.Hash) -and (Test-Path -LiteralPath (Join-Path $AppDir "code\node_modules"))) {
            Set-Estado @{ mensagem = "Atualizando as pecas do Nous Code..." }
            Start-Process -FilePath $node.Source -ArgumentList "ci --omit=dev --no-audit --no-fund" -WorkingDirectory (Join-Path $AppDir "code") -WindowStyle Hidden -Wait
        }
    }

    # 8) reiniciar e conferir que subiu
    if ($estavaRodando) {
        Set-Estado @{ fase = "reiniciando"; mensagem = "Reiniciando o Nous..." }
        Start-Nous
        $subiu = $false
        for ($i = 0; $i -lt 90; $i++) { Start-Sleep -Seconds 2; if (Test-NousSaudavel) { $subiu = $true; break } }
        if (-not $subiu) { & $reverter "O Nous nao abriu com a versao nova."; return 1 }
    }

    # 9) registro do Windows (Aplicativos instalados) e bandeja
    if (-not $ModoTeste) {
        foreach ($k in "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Nous",
                       "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8E5F2B41-9C3A-4D7E-AB12-A1B2C3D4E5F6}_is1") {
            if (Test-Path -LiteralPath $k) { try { Set-ItemProperty -LiteralPath $k -Name DisplayVersion -Value $r.versao } catch {} }
        }
        if ($bandeja.Count -gt 0) {
            Start-Process wscript.exe -ArgumentList ('"{0}"' -f (Join-Path $AppDir "launchers\bandeja.vbs")) -WindowStyle Hidden
        }
    }
    Remove-Item -LiteralPath $dl -Recurse -Force -ErrorAction SilentlyContinue
    Log ("atualizado para {0} em {1:N0} s" -f $r.versao, ((Get-Date) - $inicio).TotalSeconds)
    Set-Estado @{ fase = "concluida"; pct = 100; resultado = "ok"; disponivel = $false; versao_atual = $r.versao
                  versao_nova = $null; notas = $null; versao_anterior = $atual
                  mensagem = "Pronto! O Nous foi atualizado para a versao $($r.versao)." }
    return 0
}

# ------------------------------------------------------------------ main ----

if ($Acao -eq "Aplicar") {
    # O script troca os proprios arquivos: roda de uma copia em %TEMP% para nao
    # mexer no arquivo que esta sendo executado.
    if (-not $env:NOUS_ATUALIZAR_COPIA) {
        $copia = Join-Path ([IO.Path]::GetTempPath()) ("nous-atualizar-{0}.ps1" -f [guid]::NewGuid().ToString("N").Substring(0, 8))
        Copy-Item -LiteralPath $PSCommandPath -Destination $copia -Force
        $env:NOUS_ATUALIZAR_COPIA = "1"
        $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", "`"$copia`"", "-Acao", "Aplicar",
               "-AppDir", "`"$AppDir`"", "-DataDir", "`"$DataDir`"", "-Venv", "`"$Venv`"", "-ApiUrl", "`"$ApiUrl`"",
               "-OllamaUrl", "`"$OllamaUrl`"", "-RegistroUrl", "`"$RegistroUrl`"", "-PortaNous", $PortaNous)
        if ($ModoTeste) { $a += "-ModoTeste" }
        $p = Start-Process powershell.exe -ArgumentList $a -WindowStyle Hidden -PassThru -Wait
        Remove-Item -LiteralPath $copia -Force -ErrorAction SilentlyContinue
        exit $p.ExitCode
    }
    try { $code = Invoke-Aplicar }
    catch {
        Log "erro inesperado: $($_.Exception.Message)"
        Set-Estado @{ fase = "falhou"; resultado = "falhou"; mensagem = "A atualizacao parou por um erro inesperado. Veja $logPath" }
        $code = 1
    }
    exit $code
}

try {
    if ($Acao -in "Verificar", "Tudo") { Invoke-Verificar }
    if ($Acao -in "Modelos", "Tudo")   { Invoke-Modelos }
} catch {
    Log "erro: $($_.Exception.Message)"
    exit 1
}
exit 0
