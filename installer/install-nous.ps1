<#
.SYNOPSIS
  Nous WebUI - Instalador idempotente (1 comando faz tudo).
.DESCRIPTION
  0) Analisa a capacidade da maquina (aborta se INCAPAZ)
  1) Copia o app para %LOCALAPPDATA%\Programs\Nous (sai da pasta Downloads)
  2) Instala o Ollama (silencioso)         - pula se ja existir
  3) Modelo: menu numerado (Enter pula) ou -WithModel
  4) Instala o Python 3.11                 - pula se ja existir
  5) Cria o ambiente + Open WebUI          - pula se ja existir
  6) Aplica a identidade Nous
  7) Cria pasta de dados + atalhos (via .vbs, sem janela)
  8) Verificacao final de saude

  Idempotente: rodar de novo nao quebra nada. Use -Force para reinstalar.
  Sai com codigo 1 se algo essencial falhar (o instalar.bat mostra o erro em
  vez de dizer "Pronto!").
.PARAMETER Force
  Reinstala/atualiza componentes mesmo que ja existam.
.PARAMETER Model
  Modelo do Ollama (padrao gemma4:12b).
#>
param(
    [switch]$Force,
    [switch]$WithModel,                # baixar o modelo durante a instalacao (por padrao NAO)
    [switch]$WithImages,               # instalar tambem o motor de imagem (ComfyUI + Flux)
    [string]$Model = "gemma4:12b",
    [string]$AdminEmail,               # se a conta ja existir, registra o Pipe de imagem
    [string]$AdminPassword,
    [switch]$NoUninstallEntry          # o Nous-Setup.exe (Inno) ja registra a propria entrada
)
$ErrorActionPreference = "Stop"

$SRC       = Split-Path $PSScriptRoot -Parent             # de onde o instalador foi aberto
$APP       = Join-Path $env:LOCALAPPDATA "Programs\Nous"  # onde o Nous passa a morar
$REPO      = $SRC                                         # vira $APP apos o passo 1
$venv      = Join-Path $env:USERPROFILE "open-webui"
$dataDir   = Join-Path $env:USERPROFILE "NousData"
$ollamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$ollamaApp = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"

# Versao do Open WebUI TESTADA com o Nous. Upgrades sao conscientes: valide a
# versao nova primeiro e depois suba este pin (a identidade Nous se reaplica
# sozinha no boot via marcador). Sem o pin, um "pip install" futuro pode trazer
# uma versao que quebra o patch do nome/tema em maquinas de usuarios leigos.
# Quem ja' tem o Nous numa versao mais antiga e' atualizado no passo 4, com
# backup e volta atras (installer\atualizar-openwebui.ps1).
$OPENWEBUI_PIN = "0.12.3"

# O Ollama novo (0.32+) abre uma tela de boas-vindas que convida a entrar numa
# conta e tem uma nuvem propria (modelos que rodam em ollama.com). O Nous e'
# privado por padrao: quando ELE instala o Ollama, ja' deixa a boas-vindas como
# concluida e a nuvem desligada (o usuario liga de novo nas configuracoes do
# Ollama, se quiser). Nunca mexe num Ollama que ja' existia. Tudo opcional: se
# a versao do Ollama nao conhece os arquivos, eles so' nao fazem nada.
function Set-OllamaPrivado {
    try {
        $dirs = @((Join-Path $env:USERPROFILE ".ollama"), (Join-Path $env:LOCALAPPDATA "Ollama"))
        foreach ($d in $dirs) {
            New-Item -ItemType Directory -Force -Path $d | Out-Null
            $marca = Join-Path $d "onboarding-v1.completed"
            if (-not (Test-Path $marca)) { New-Item -ItemType File -Path $marca | Out-Null }
        }
        $cfgPath = Join-Path $dirs[0] "server.json"
        $cfg = [ordered]@{}
        if (Test-Path $cfgPath) {
            try { (Get-Content $cfgPath -Raw | ConvertFrom-Json).PSObject.Properties | ForEach-Object { $cfg[$_.Name] = $_.Value } } catch {}
        }
        if (-not $cfg.Contains("disable_ollama_cloud")) {
            $cfg["disable_ollama_cloud"] = $true
            [IO.File]::WriteAllText($cfgPath, ($cfg | ConvertTo-Json))
        }
    } catch {}
}

function Step($n, $t) { Write-Host "`n[$n] $t" -ForegroundColor Cyan }
function Ok($t)       { Write-Host "    [ok] $t" -ForegroundColor Green }
function Info($t)     { Write-Host "    $t" -ForegroundColor DarkGray }
function Fail($t) {
    Write-Host "`n    [erro] $t" -ForegroundColor Red
    Write-Host "    Nada do que ja' estava no computador foi apagado. Corrija o item acima" -ForegroundColor Yellow
    Write-Host "    (geralmente: conexao com a internet) e rode o instalar.bat de novo." -ForegroundColor Yellow
    exit 1
}
# Comandos externos (winget, pip, venv) nao lancam excecao quando falham: so'
# deixam $LASTEXITCODE diferente de zero. Sem esta checagem o instalador dizia
# "[ok] instalado" e o instalar.bat terminava em "Pronto!".
function Assert-Exit([string]$what) {
    if ($LASTEXITCODE -ne 0) { Fail "$what falhou (codigo $LASTEXITCODE)." }
}
# Pela API, nunca por "ollama list": com o servico parado o CLI abre o app do
# Ollama, que herda o pipe de saida, e o instalador congelava ali para sempre.
function Test-ModelInstalled([string]$tag) {
    try {
        $tags = Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
        return [bool]($tags.models | Where-Object { $_.name -eq $tag -or $_.name -eq "${tag}:latest" })
    } catch { return $false }
}

# --- Deteccao robusta: NAO rebaixar o que ja existe, mesmo instalado por
#     outro metodo/local (PATH, locais comuns, serviço no ar). ---
function Find-Ollama {
    $c = Get-Command ollama -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"),
        (Join-Path $env:ProgramFiles  "Ollama\ollama.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Ollama\ollama.exe"))) {
        if ($p -and (Test-Path $p)) { return $p }
    }
    return $null
}
function Test-OllamaUp {
    try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null; return $true }
    catch { return $false }
}
# Cria/atualiza o atalho "Nous.lnk" em $folder, sempre via wscript + nous-hidden.vbs
# (abre sem janela e le o start-nous.ps1 ao vivo). NUNCA lanca excecao: antivirus /
# "Acesso controlado a pastas" do Defender podem bloquear a gravacao na area de
# trabalho — tratamos e seguimos. Retorna $true se o atalho existe ao final.
function New-NousShortcut([string]$folder, [string]$name = "Nous", [string]$vbsName = "nous-hidden.vbs") {
    try {
        if (-not $folder) { return $false }
        if (-not (Test-Path $folder)) { return $false }
        $lnkPath = Join-Path $folder "$name.lnk"
        $ws  = New-Object -ComObject WScript.Shell
        $lnk = $ws.CreateShortcut($lnkPath)
        # SEMPRE via .vbs: ele le o start-nous.ps1 ao vivo (sem janela), entao o
        # atalho nunca fica preso numa versao congelada como acontecia com o .exe.
        $vbs = Join-Path $REPO "launchers\$vbsName"
        $lnk.TargetPath = "wscript.exe"
        $lnk.Arguments  = "`"$vbs`""
        $lnk.WorkingDirectory = (Join-Path $REPO "launchers")
        $ico = Join-Path $REPO "branding\assets\nous.ico"
        if (Test-Path $ico) { $lnk.IconLocation = "$ico,0" }
        $lnk.Save()
        return [bool](Test-Path $lnkPath)
    } catch { return $false }
}

function Find-Py311 {
    # Open WebUI exige Python 3.11 (nao 3.12+). Procura qualquer 3.11 ja' presente.
    try {
        $v = & py -3.11 -c "import sys; sys.stdout.write(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
    } catch {}
    foreach ($p in @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        "C:\Python311\python.exe",
        (Join-Path $env:ProgramFiles "Python311\python.exe"))) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

# VRAM dedicada (GB) via registro, p/ marcar o modelo recomendado no menu.
# 0 = sem GPU detectada (vai recomendar modelos leves de CPU). Nunca lanca.
function Get-VramGB {
    try {
        $cls = 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
        $max = 0
        Get-ChildItem $cls -ErrorAction SilentlyContinue | ForEach-Object {
            $v = (Get-ItemProperty $_.PSPath -Name 'HardwareInformation.qwMemorySize' -ErrorAction SilentlyContinue).'HardwareInformation.qwMemorySize'
            if ($v -and [int64]$v -gt $max) { $max = [int64]$v }
        }
        return [math]::Round($max / 1GB, 1)
    } catch { return 0 }
}

# Menu numerado de modelos (le o catalog.json da Loja). O usuario digita um
# numero em vez do nome (tags como "qwen2.5-coder:14b" sao longas e dificeis).
# Enter sem nada = pula (mantem o padrao: escolher depois, na Loja do app).
# Retorna a TAG escolhida, ou $null se pulou / catalogo indisponivel.
function Select-ModelInteractive {
    $catPath = Join-Path $REPO "monitor\catalog.json"
    if (-not (Test-Path $catPath)) { return $null }
    try { $models = (Get-Content $catPath -Raw | ConvertFrom-Json).models } catch { return $null }
    if (-not $models -or $models.Count -eq 0) { return $null }

    $vram = Get-VramGB

    # Marca o "recomendado": melhor modelo que cabe na maquina. Com GPU, o de
    # maior min_vram_gb que ainda <= VRAM; sem GPU, o leve mais capaz (<=4 GB dl).
    $recIdx = -1
    if ($vram -ge 4) {
        $best = -1
        for ($i = 0; $i -lt $models.Count; $i++) {
            if ($models[$i].min_vram_gb -le $vram -and $models[$i].min_vram_gb -gt $best) {
                $best = $models[$i].min_vram_gb; $recIdx = $i
            }
        }
    } else {
        for ($i = 0; $i -lt $models.Count; $i++) {
            if ($models[$i].category -eq 'leve' -and $models[$i].download_gb -le 4.0) { $recIdx = $i; break }
        }
    }

    Write-Host ""
    if ($vram -ge 1) { Info ("GPU detectada: ~{0} GB de VRAM." -f $vram) }
    else { Info "Sem GPU dedicada detectada: modelos leves rodam melhor (na CPU)." }
    Write-Host "    Escolha um modelo digitando o NUMERO (ou Enter para escolher depois):" -ForegroundColor White
    Write-Host ""

    for ($i = 0; $i -lt $models.Count; $i++) {
        $m   = $models[$i]
        $num = ($i + 1).ToString().PadLeft(2)
        $vis = if ($m.vision) { " [imagens]" } else { "" }
        $tag = if ($i -eq $recIdx) { " <- recomendado p/ sua maquina" } else { "" }
        $color = if ($i -eq $recIdx) { "Green" } else { "Gray" }
        Write-Host ("     [{0}] {1} - {2} GB{3}{4}" -f $num, $m.name, $m.download_gb, $vis, $tag) -ForegroundColor $color
    }
    Write-Host ""

    $defaultNum = if ($recIdx -ge 0) { ($recIdx + 1) } else { $null }
    $promptTxt = if ($defaultNum) { "    Numero do modelo [$defaultNum = recomendado, Enter pula]: " }
                 else            { "    Numero do modelo [Enter pula]: " }
    Write-Host $promptTxt -ForegroundColor White -NoNewline
    $ans = Read-Host

    if ([string]::IsNullOrWhiteSpace($ans)) { return $null }
    $ans = $ans.Trim()
    $n = 0
    if (-not [int]::TryParse($ans, [ref]$n)) { Info "Entrada invalida - vou pular (escolha depois na Loja)."; return $null }
    if ($n -lt 1 -or $n -gt $models.Count) { Info "Numero fora da lista - vou pular (escolha depois na Loja)."; return $null }
    return $models[$n - 1].tag
}

Write-Host "================ Instalador do Nous ================" -ForegroundColor Yellow

# 0) Porteiro de capacidade -------------------------------------------------
Step 0 "Analisando a capacidade da maquina"
& (Join-Path $REPO "tools\check-system.ps1")
switch ($LASTEXITCODE) {
    1 { Write-Host "`nMaquina INCAPAZ de rodar o Nous. Instalacao abortada." -ForegroundColor Red; exit 1 }
    2 { Info "Sem GPU adequada: vai funcionar na CPU (mais lento)." }
}

# 0.5) Pre-requisito: winget (App Installer) --------------------------------
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host "`nO 'winget' (App Installer) nao foi encontrado nesta maquina." -ForegroundColor Red
    Write-Host "Ele ja vem no Windows 10/11 atualizado. Instale o 'App Installer'" -ForegroundColor Yellow
    Write-Host "pela Microsoft Store e rode o instalador de novo:" -ForegroundColor Yellow
    Write-Host "  https://apps.microsoft.com/detail/9NBLGGH4NNS1" -ForegroundColor Cyan
    exit 1
}

# 0.6) App no lugar definitivo ----------------------------------------------
# Antes o Nous rodava de onde o ZIP foi descompactado (quase sempre Downloads):
# limpar essa pasta quebrava o atalho, e rodar de dentro do ZIP nem funcionava.
Step "0.6" "Copiando o Nous para $APP"
if ($SRC.TrimEnd('\') -ne $APP.TrimEnd('\')) {
    New-Item -ItemType Directory -Force -Path $APP | Out-Null
    # /E sem /MIR: nunca apaga o que ja existe la' (backups em bkp\, etc.)
    robocopy $SRC $APP /E /XD .git dist /XF *.log Nous.exe "Parar Nous.exe" /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "nao consegui copiar os arquivos do Nous para $APP." }
    $global:LASTEXITCODE = 0
    Ok "app copiado - a pasta que voce baixou pode ser apagada depois"
} else {
    Ok "ja esta no lugar"
}
$REPO = $APP

# 0.7) Atalho ANTES de tudo --------------------------------------------------
# Se algo falhar no meio da instalacao, o usuario ja' tem como abrir o Nous.
# O Menu Iniciar nao e' bloqueado pelo "Acesso controlado a pastas" do Defender,
# entao "Nous" sempre aparece ao apertar a tecla Windows e digitar o nome.
$null = New-NousShortcut ([Environment]::GetFolderPath("Desktop"))
$null = New-NousShortcut ([Environment]::GetFolderPath("Programs"))

# 1) Ollama -----------------------------------------------------------------
Step 1 "Ollama"
$instOllama = $false   # o Nous instalou? (para o desinstalador saber)
$ollamaExe = Find-Ollama
if (($ollamaExe -or (Test-OllamaUp)) -and -not $Force) {
    Ok "ja instalado - nao vou baixar de novo$(if ($ollamaExe) { " ($ollamaExe)" })"
} else {
    $ollamaSetup = Join-Path $env:TEMP "OllamaSetup.exe"
    $ollamaUrl   = "https://ollama.com/download/OllamaSetup.exe"

    Info "baixando o Ollama (~1.3 GB)..."
    Write-Host ""

    # Download com barra de progresso nativa do PowerShell.
    # WebClient.DownloadFile bloqueia sem progresso; usamos WebClient assíncrono
    # com evento DownloadProgressChanged para atualizar Write-Progress.
    $wc = New-Object System.Net.WebClient
    $done = $false
    $dlError = $null

    $wc.add_DownloadProgressChanged({
        param($s, $e)
        $mb     = [math]::Round($e.BytesReceived / 1MB, 1)
        $total  = if ($e.TotalBytesToReceive -gt 0) { [math]::Round($e.TotalBytesToReceive / 1MB, 1) } else { '?' }
        $pct    = $e.ProgressPercentage
        $status = if ($e.TotalBytesToReceive -gt 0) {
            "$mb MB de $total MB"
        } else {
            "$mb MB baixados"
        }
        Write-Progress -Activity "Baixando Ollama" -Status $status -PercentComplete $pct
    })

    $wc.add_DownloadFileCompleted({
        param($s, $e)
        $script:done = $true
        if ($e.Error) { $script:dlError = $e.Error.Message }
    })

    $wc.DownloadFileAsync([uri]$ollamaUrl, $ollamaSetup)

    # Aguarda o download terminar (máx 30 min para internet lenta)
    $deadline = (Get-Date).AddMinutes(30)
    while (-not $done -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    Write-Progress -Activity "Baixando Ollama" -Completed

    if ($dlError) {
        Write-Host "    [erro] Falha no download: $dlError" -ForegroundColor Red
        exit 1
    }
    if (-not (Test-Path $ollamaSetup)) {
        Write-Host "    [erro] Arquivo nao encontrado apos o download." -ForegroundColor Red
        exit 1
    }

    Set-OllamaPrivado   # antes do instalador: ele ja' pode abrir o app
    Info "instalando o Ollama (silencioso)..."
    Start-Process -FilePath $ollamaSetup -ArgumentList "/VERYSILENT /NORESTART" -Wait -NoNewWindow
    Remove-Item $ollamaSetup -Force -ErrorAction SilentlyContinue

    $ollamaExe = Find-Ollama
    if (-not $ollamaExe) { Fail "a instalacao do Ollama nao terminou." }
    $instOllama = $true
    Ok "instalado"
}
if (-not (Test-OllamaUp)) {
    if (Test-Path $ollamaApp)   { Start-Process $ollamaApp -WindowStyle Hidden }
    elseif ($ollamaExe)         { Start-Process $ollamaExe -ArgumentList "serve" -WindowStyle Hidden }
    for ($i = 0; $i -lt 15 -and -not (Test-OllamaUp); $i++) { Start-Sleep -Seconds 1 }
}
if (Test-OllamaUp) { Ok "servico no ar" } else { Info "servico nao respondeu ainda (confira o Ollama)" }

# 2) Modelo (baixado DENTRO do app, com progresso na tela) ------------------
Step 2 "Modelo"
$ollamaCmd = if ($ollamaExe) { $ollamaExe } else { "ollama" }
$instModel = $false

# Menu numerado: so' oferece se a instalacao e' interativa (nao passou -Model
# nem -WithModel por linha de comando) e o terminal aceita entrada do usuario.
$modelExplicit = $PSBoundParameters.ContainsKey('Model')
if (-not $WithModel -and -not $modelExplicit -and [Environment]::UserInteractive) {
    $chosen = Select-ModelInteractive
    if ($chosen) { $Model = $chosen; $WithModel = $true }
}

$hasModel = Test-ModelInstalled $Model
if ($WithModel) {
    if ($hasModel -and -not $Force) { Ok "$Model ja baixado" }
    else {
        Info "baixando $Model (pode levar varios minutos)..."
        # Nao deixa uma falha de download (internet/Ollama) abortar a instalacao
        # toda: o usuario ainda pode baixar pela Loja depois.
        try {
            & $ollamaCmd pull $Model
            if ($LASTEXITCODE -eq 0) { $instModel = $true; Ok "baixado" }
            else { Info "download nao concluido - voce pode baixar depois na Loja de Modelos." }
        } catch {
            Info "download nao concluido - voce pode baixar depois na Loja de Modelos."
        }
    }
}
elseif ($hasModel) { Ok "$Model ja presente" }
else {
    Info "pulado: no primeiro uso o Nous abre um assistente que recomenda o"
    Info "modelo ideal p/ esta maquina e baixa em 1 clique (Loja de Modelos)."
}

# 3) Python 3.11 ------------------------------------------------------------
Step 3 "Python 3.11"
$instPython = $false
$py311 = Find-Py311
if ($py311 -and -not $Force) { Ok "ja instalado - nao vou baixar de novo ($py311)" }
else {
    Info "instalando Python 3.11 (~27 MB, rapido)..."
    winget install --id Python.Python.3.11 -e --accept-package-agreements --accept-source-agreements --silent
    $py311 = Find-Py311
    if (-not $py311) { Fail "Python 3.11 nao encontrado apos a instalacao (codigo $LASTEXITCODE)." }
    $instPython = $true
    Ok "instalado"
}

# 4) Ambiente + Open WebUI --------------------------------------------------
Step 4 "Ambiente Python + Open WebUI"
$vpy = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $vpy)) {
    Info "criando ambiente isolado..."
    & $py311 -m venv $venv
    Assert-Exit "a criacao do ambiente Python"
}
# Ja' existe: confere a versao e, se for mais antiga que a testada, atualiza com
# backup dos dados e volta atras se algo falhar (script a parte, em outro
# processo: ele encerra o que o Nous deixou rodando e sobe um servidor de teste).
$temOpenWebUI = Test-Path (Join-Path $venv "Scripts\open-webui.exe")
$updExit = 0
if ($temOpenWebUI) {
    $upd = Join-Path $REPO "installer\atualizar-openwebui.ps1"
    if (Test-Path $upd) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $upd -Venv $venv -DataDir $dataDir -Pin $OPENWEBUI_PIN -Repo $REPO
        $updExit = $LASTEXITCODE
        $global:LASTEXITCODE = 0
    }
    if ($updExit -eq 1) { Write-Host "    [aviso] o Open WebUI nao foi atualizado agora; o Nous segue funcionando na versao que ja' estava." -ForegroundColor Yellow }
    if ($updExit -eq 2) { Fail "a atualizacao do Open WebUI falhou e nao consegui voltar sozinho. Seus dados estao no ultimo zip da pasta bkp\ do Nous." }
}
if ($temOpenWebUI -and -not $Force) { Ok "Open WebUI ja instalado" }
else {
    Info "instalando o Open WebUI $OPENWEBUI_PIN (varios minutos, baixa varios GB)..."
    & $vpy -m pip install --upgrade pip --quiet
    & $vpy -m pip install "open-webui==$OPENWEBUI_PIN"
    Assert-Exit "a instalacao do Open WebUI"
    Ok "instalado (versao testada com o Nous)"
}

# 5) Identidade Nous --------------------------------------------------------
Step 5 "Aplicando a identidade Nous"
& $vpy -m pip install pillow --quiet | Out-Null   # garante o PIL (no-op se ja existe)
& $vpy (Join-Path $REPO "branding\apply_branding.py") --data-dir $dataDir
if ($LASTEXITCODE -ne 0) {
    Write-Host "    [aviso] identidade nao aplicada agora - o Nous reaplica sozinho a cada inicio." -ForegroundColor Yellow
}

# 6) Dados + atalho + launcher oculto --------------------------------------
Step 6 "Dados, atalho e launcher"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
Ok "pasta de dados: $dataDir"
# NAO geramos mais o Nous.exe via ps2exe: o ps2exe EMBUTE o start-nous.ps1
# dentro do .exe na compilacao, entao o atalho rodava uma copia CONGELADA do
# codigo — qualquer atualizacao dos .ps1 nao chegava ao usuario ("versao
# desatualizada"). O atalho usa o nous-hidden.vbs, que le o start-nous.ps1
# AO VIVO (abre sem janela igual ao .exe). Remove .exe antigo se existir.
foreach ($oldExe in "Nous.exe", "Parar Nous.exe") {
    $ep = Join-Path $REPO "launchers\$oldExe"
    if (Test-Path $ep) { Remove-Item $ep -Force -ErrorAction SilentlyContinue }
}
Ok "launcher via .vbs (sempre a versao atual, sem codigo congelado)"

# Recria os atalhos (apontando p/ o .vbs, que le sempre o start-nous.ps1 atual) e VERIFICA.
$desktopOk = New-NousShortcut ([Environment]::GetFolderPath("Desktop"))
if (-not $desktopOk) {
    # instalacao elevada (outra conta) ou Desktop bloqueado: area de trabalho publica
    $desktopOk = New-NousShortcut ([Environment]::GetFolderPath("CommonDesktopDirectory"))
}
$startOk = New-NousShortcut ([Environment]::GetFolderPath("Programs"))
$null = New-NousShortcut ([Environment]::GetFolderPath("Programs")) "Parar Nous" "parar-nous.vbs"
$null = New-NousShortcut ([Environment]::GetFolderPath("Programs")) "Nous Bandeja" "bandeja.vbs"   # icone perto do relogio

# Nous Code (IDE com agente de IA local): precisa do Node 22.18+. Sem Node bom no
# computador, baixa o Node portatil (zip oficial, SHA256 conferido) para
# <app>\runtime\node, sem mexer no PATH do sistema; os launchers usam esse
# Node (launchers\node-nous.ps1). Baixa as pecas do editor (Monaco, terminal)
# uma vez e cria o atalho "Nous Code". Opcional: se nada der certo, o resto do
# Nous funciona igual.
$nodeExe = $null
$nodeLib = Join-Path $REPO "launchers\node-nous.ps1"
if ((Test-Path $nodeLib) -and (Test-Path (Join-Path $REPO "code\package.json"))) {
    . $nodeLib
    $nodeExe = Find-NousNode $REPO
    if (-not $nodeExe) {
        Info "Nous Code: baixando o Node.js portatil (~30 MB; fica na pasta do Nous e nao mexe no seu PATH)..."
        if (Install-PortableNode (Get-PortableNodeDir $REPO)) { Ok "Node.js portatil instalado ($($script:NodePin.Versao))" }
        else { Info "Nous Code: nao consegui baixar o Node.js ($script:NodeErro)." }
        $nodeExe = Find-NousNode $REPO
    }
}
$nodeOk = [bool]$nodeExe
$codeDir = Join-Path $REPO "code"
if ($nodeOk -and (Test-Path (Join-Path $codeDir "package.json"))) {
    # tambem quando falta o language server (instalacao de antes do lsp)
    if (-not (Test-Path (Join-Path $codeDir "node_modules\monaco-editor")) -or -not (Test-Path (Join-Path $codeDir "node_modules\typescript-language-server"))) {
        Info "Nous Code: baixando as pecas do editor e da navegacao de codigo (~100 MB)..."
        Push-Location $codeDir
        # o npm vem junto do Node; o PATH muda so' neste processo
        $env:Path = (Split-Path $nodeExe -Parent) + ";" + $env:Path
        & npm ci --omit=dev --no-audit --no-fund 2>&1 | Out-Null
        $npmOk = $LASTEXITCODE -eq 0
        Pop-Location
        if (-not $npmOk) { Info "Nous Code: download nao concluido (rode o instalador de novo com internet)." }
    }
    $null = New-NousShortcut ([Environment]::GetFolderPath("Programs")) "Nous Code" "nous-code.vbs"
    $null = New-NousShortcut ([Environment]::GetFolderPath("Desktop")) "Nous Code" "nous-code.vbs"
    Ok "atalho 'Nous Code' (editor de codigo com IA local)"
} else {
    Info "Nous Code (opcional): faltou o Node.js 22.18+ (precisa de internet para baixar). Rode o instalador de novo com internet."
}
if ($desktopOk) { Ok "atalho 'Nous' na area de trabalho" }
if ($startOk)   { Ok "atalhos 'Nous' e 'Parar Nous' no Menu Iniciar (tecla Windows > digite Nous)" }
if (-not $desktopOk) {
    Write-Host "    [aviso] nao consegui criar o atalho na area de trabalho" -ForegroundColor Yellow
    Write-Host "            (o antivirus ou o 'Acesso controlado a pastas' pode ter bloqueado)." -ForegroundColor Yellow
    if ($startOk) { Write-Host "            Use o Menu Iniciar (tecla Windows > Nous)." -ForegroundColor Yellow }
    else          { Write-Host "            Abra o Nous com clique duplo em iniciar.bat, em $APP." -ForegroundColor Yellow }
}

# Entrada em Configuracoes > Aplicativos instalados: o leigo desinstala o Nous
# como qualquer programa, sem precisar achar o desinstalar.bat.
if (-not $NoUninstallEntry) { try {
    $unKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Nous"
    New-Item -Path $unKey -Force | Out-Null
    $ver = (Get-Content (Join-Path $REPO "VERSION") -Raw -ErrorAction SilentlyContinue)
    $props = [ordered]@{
        DisplayName     = "Nous"
        DisplayVersion  = $(if ($ver) { $ver.Trim() } else { "" })
        Publisher       = "Nous"
        InstallLocation = $APP
        DisplayIcon     = (Join-Path $APP "branding\assets\nous.ico")
        UninstallString = "cmd.exe /c `"`"$(Join-Path $APP 'desinstalar.bat')`"`""
    }
    foreach ($k in $props.Keys) { Set-ItemProperty -Path $unKey -Name $k -Value $props[$k] }
    Set-ItemProperty -Path $unKey -Name NoModify -Value 1 -Type DWord
    Set-ItemProperty -Path $unKey -Name NoRepair -Value 1 -Type DWord
    Ok "Nous aparece em Configuracoes > Aplicativos (para desinstalar)"
} catch { Info "nao consegui registrar em Aplicativos instalados (segue sem)" } }

# 6.5) Manifesto de instalacao ---------------------------------------------
# Registra o que o Nous REALMENTE instalou, para o desinstalador remover so'
# isso e nunca mexer num Ollama/Python que ja' existia antes. Numa reinstalacao
# o Ollama/Python ja' "existem" - por isso as marcas antigas sao preservadas
# (OR), senao o "Remover tudo" deixava de remove-los. O modelo so' e' gravado
# se foi de fato escolhido/baixado (o launcher o usa como modelo padrao).
$manPath = Join-Path $dataDir "install-manifest.json"
$old = $null
if (Test-Path $manPath) { try { $old = Get-Content $manPath -Raw | ConvertFrom-Json } catch {} }
$manifest = [ordered]@{
    installed_at   = (Get-Date).ToString("s")
    app            = $APP
    venv           = $venv
    ollama_by_nous = [bool]($instOllama -or ($old -and $old.ollama_by_nous))
    python_by_nous = [bool]($instPython -or ($old -and $old.python_by_nous))
    model          = $(if ($WithModel -and ($instModel -or $hasModel)) { $Model } elseif ($old) { $old.model } else { $null })
    model_by_nous  = [bool]($instModel -or ($old -and $old.model_by_nous))
}
[IO.File]::WriteAllText($manPath, ($manifest | ConvertTo-Json))
Ok "manifesto de instalacao salvo (ajuda o desinstalador)"

# 7) Verificacao ------------------------------------------------------------
Step 7 "Verificacao final de saude"
& (Join-Path $REPO "tools\health-check.ps1") -Model $manifest.model

# 8) Motor de imagem (opcional) --------------------------------------------
# Nao-fatal: se a parte pesada/GPU-especifica falhar, o nucleo continua OK.
if ($WithImages) {
    Step 8 "Motor de imagem (ComfyUI + Flux) - opcional"
    try {
        & (Join-Path $REPO "images\install-comfyui.ps1")
        if ($AdminEmail -and $AdminPassword) {
            Info "registrando o Pipe 'Gerador de Imagem Local'..."
            & $vpy (Join-Path $REPO "images\register_pipe.py") --email $AdminEmail --password $AdminPassword
        } else {
            Info "Apos criar sua conta no Nous, ative a geracao de imagem no chat com:"
            Info "  `"$vpy`" images\register_pipe.py --email SEU@EMAIL --password SUASENHA"
        }
    } catch {
        Info "[aviso] motor de imagem falhou (segue sem ele): $($_.Exception.Message)"
    }
}

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " Nous pronto!" -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
Write-Host ""
Write-Host " 1. Abra pelo atalho 'Nous' na area de trabalho" -ForegroundColor White
Write-Host "    (ou tecla Windows > digite Nous; ou clique duplo em iniciar.bat)." -ForegroundColor DarkGray
Write-Host ""
Write-Host " 2. Sem conta e sem senha: o Nous abre direto no chat." -ForegroundColor White
Write-Host "    (Varias pessoas no mesmo PC? Crie uma conta para cada uma no Painel do Admin.)" -ForegroundColor DarkGray
Write-Host ""
if ($WithModel) {
    Write-Host " 3. O modelo $Model ja foi baixado. Ele aparece no seletor" -ForegroundColor White
    Write-Host "    de modelos no topo da tela. Clique nele e comece a conversar." -ForegroundColor DarkGray
} else {
    Write-Host " 3. O Nous abre um assistente no primeiro uso: ele recomenda o" -ForegroundColor White
    Write-Host "    modelo ideal para a sua maquina e baixa tudo em 1 clique." -ForegroundColor DarkGray
}
Write-Host ""
Write-Host " Dica: chat, visao (envie prints), busca na web e memoria pessoal" -ForegroundColor DarkGray
Write-Host "       ja vem ativos - sem configurar nada." -ForegroundColor DarkGray
if (-not $WithImages) {
    Write-Host ""
    Write-Host " Para gerar imagens localmente depois: install-nous.ps1 -WithImages" -ForegroundColor DarkGray
}
exit 0
