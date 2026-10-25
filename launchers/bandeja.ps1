<#
  Nous - Icone na bandeja do sistema (perto do relogio), SEM janela de terminal.
  Abre o Nous, inicia/para, mostra o estado (rodando ou parado, placa de video ou
  processador, memoria, modelo carregado), abre o Nous Code, avisa de versao nova
  do Nous e dos modelos e deixa atualizar com um clique.

  Chamado sem janela pelo bandeja.vbs. O start-nous.ps1 sobe a bandeja junto com
  o Nous; "Abrir junto com o Windows" (menu do icone) e' opcional, desligado por
  padrao. Uma so' copia roda por vez (mutex).

  Por que PowerShell + WinForms e nao Python/pystray: nao ha dependencia nova, e a
  bandeja continua funcionando (e mostra "parado") mesmo se o ambiente Python do
  Nous estiver quebrado - justo quando a pessoa mais precisa do botao Iniciar.
  O custo e' um powershell.exe escondido (~100 MB de memoria).

  Parametros so' para teste: portas, pastas e -Teste (mostra o menu em texto e sai).
#>
param(
    [string]$AppDir,
    [string]$DataDir,
    [string]$PortaNous = "8080",
    [string]$PortaMonitor = "8990",
    [string]$OllamaUrl = "http://127.0.0.1:11434",
    [string]$ChaveRun = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run",
    [string]$Instancia = "",          # separa o mutex (testes)
    [switch]$Teste,                   # monta o menu, escreve o texto dele e sai
    [string]$Captura,                 # com -Teste: salva um PNG do menu aberto
    [string]$Clicar                   # com -Teste: clica no item cujo texto comeca assim (antes de listar)
)
$ErrorActionPreference = "SilentlyContinue"
if (-not $AppDir)  { $AppDir  = Split-Path $PSScriptRoot -Parent }
if (-not $DataDir) { $DataDir = Join-Path $env:USERPROFILE "NousData" }
$launchers = Join-Path $AppDir "launchers"
$cfgPath   = Join-Path $DataDir "atualizacao-config.json"
$estPath   = Join-Path $DataDir "atualizacao-estado.json"
$atualizar = Join-Path $AppDir "atualizacao\nous-atualizar.ps1"
$icoPath   = Join-Path $AppDir "branding\assets\nous.ico"
$pt = [Globalization.CultureInfo]::GetCultureInfo("pt-BR")

# --- uma bandeja por vez ----------------------------------------------------
$mutex = New-Object Threading.Mutex($false, "Local\NousBandeja$Instancia")
if (-not $Teste) { if (-not $mutex.WaitOne(0)) { return } }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()

# --- configuracao (NousData\atualizacao-config.json) ------------------------
function Read-Json([string]$p) {
    if (Test-Path -LiteralPath $p) { try { return (Get-Content -LiteralPath $p -Raw | ConvertFrom-Json) } catch {} }
    return $null
}
function Get-Cfg {
    $r = [ordered]@{ verificar = $true; bandeja = $true; aviso_visto = $false }
    $c = Read-Json $cfgPath
    if ($c) { foreach ($p in $c.PSObject.Properties) { $r[$p.Name] = $p.Value } }
    return $r
}
function Set-Cfg([string]$chave, $valor) {
    $r = Get-Cfg
    $r[$chave] = $valor
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    [IO.File]::WriteAllText($cfgPath, (ConvertTo-Json -InputObject $r))
}
# @($null) tem 1 item em PowerShell: este filtro devolve lista vazia de verdade
function Get-Novos($est) { return @(@($est.modelos_novos) | Where-Object { $_ }) }
function Get-Versao {
    $v = Join-Path $AppDir "VERSION"
    if (Test-Path -LiteralPath $v) { return (Get-Content -LiteralPath $v -Raw).Trim() }
    return "?"
}

# --- coleta do estado (roda num segundo plano a cada 5 s; nunca trava o menu) --
$coletaTxt = @'
param($S, $porta, $ollama, $dataDir)
function Gb($b) { [math]::Round($b / 1GB, 1) }
if (-not $S.gpu -and -not $S.cpu) {
    $nome = $null
    foreach ($v in @(Get-CimInstance Win32_VideoController)) {
        if ($v.Name -match 'NVIDIA|Radeon|Arc|GeForce|Intel\(R\) (UHD|Iris)') {
            if (-not $nome -or $v.Name -match 'NVIDIA|Radeon RX|Arc') { $nome = $v.Name }
        }
    }
    $S.gpu = $nome
    $S.cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name -replace '\s+', ' '
}
try {
    $c = New-Object Net.Sockets.TcpClient
    $iar = $c.BeginConnect("127.0.0.1", [int]$porta, $null, $null)
    $S.rodando = [bool]($iar.AsyncWaitHandle.WaitOne(400) -and $c.Connected)
    $c.Close()
} catch { $S.rodando = $false }
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $S.ram_total = Gb ($os.TotalVisibleMemorySize * 1KB)
    $S.ram_usada = Gb (($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) * 1KB)
} catch {}
try {
    $ps = Invoke-RestMethod -Uri "$ollama/api/ps" -TimeoutSec 2
    $S.ollama = $true
    $S.modelos = @($ps.models | ForEach-Object { @{ nome = "$($_.name)"; gb = (Gb $_.size); gpu = ([double]$_.size_vram -gt 0); tudo_gpu = ([double]$_.size_vram -ge [double]$_.size) } })
} catch { $S.ollama = $false; $S.modelos = @() }
$S.coletado = Get-Date
'@

$S = [hashtable]::Synchronized(@{ rodando = $false; ollama = $false; modelos = @(); ram_total = 0; ram_usada = 0; gpu = $null; cpu = $null })
$coleta = [scriptblock]::Create($coletaTxt)

# --- icones: o do Nous com uma bolinha de estado ---------------------------
function New-IconeEstado([string]$cor) {
    $tam = [Windows.Forms.SystemInformation]::SmallIconSize
    $base = New-Object Drawing.Icon($icoPath, $tam)
    $bmp = New-Object Drawing.Bitmap($tam.Width, $tam.Height)
    $g = [Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = "AntiAlias"
    $g.DrawIcon($base, (New-Object Drawing.Rectangle(0, 0, $tam.Width, $tam.Height)))
    if ($cor) {
        $d = [int]($tam.Width * 0.5)
        $pincel = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml($cor))
        $borda = New-Object Drawing.Pen([Drawing.Color]::FromArgb(230, 20, 20, 24), 1.4)
        $g.FillEllipse($pincel, $tam.Width - $d - 1, $tam.Height - $d - 1, $d, $d)
        $g.DrawEllipse($borda, $tam.Width - $d - 1, $tam.Height - $d - 1, $d, $d)
        $pincel.Dispose(); $borda.Dispose()
    }
    $g.Dispose()
    $ic = [Drawing.Icon]::FromHandle($bmp.GetHicon())
    return $ic
}

# --- menu --------------------------------------------------------------------
$menu = New-Object Windows.Forms.ContextMenuStrip
function Add-Item([string]$texto, $acao, [bool]$ativo = $true) {
    $i = New-Object Windows.Forms.ToolStripMenuItem($texto)
    $i.Enabled = $ativo
    if ($acao) { $i.add_Click($acao) }
    [void]$menu.Items.Add($i)
    return $i
}
function Add-Sep { [void]$menu.Items.Add((New-Object Windows.Forms.ToolStripSeparator)) }

function Start-Oculto([string]$vbs) {
    Start-Process -FilePath "wscript.exe" -ArgumentList ('"{0}"' -f (Join-Path $launchers $vbs)) -WindowStyle Hidden
}
function Start-Atualizador([string]$acao, [switch]$Forcar) {
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", ('"{0}"' -f $atualizar),
           "-Acao", $acao, "-AppDir", ('"{0}"' -f $AppDir), "-DataDir", ('"{0}"' -f $DataDir), "-PortaNous", $PortaNous, "-OllamaUrl", ('"{0}"' -f $OllamaUrl))
    if ($Forcar) { $a += "-Forcar" }
    return (Start-Process -FilePath "powershell.exe" -ArgumentList $a -WindowStyle Hidden -PassThru)
}

$iCab    = Add-Item "Nous" $null $false
$iCab.Font = New-Object Drawing.Font($iCab.Font, [Drawing.FontStyle]::Bold)
$iOnde   = Add-Item "" $null $false
$iMem    = Add-Item "" $null $false
$iModelo = Add-Item "" $null $false
Add-Sep
$iAbrir = Add-Item "Abrir o Nous" {
    if ($S.rodando) { Start-Process "http://localhost:$PortaNous" } else { Start-Oculto "nous-hidden.vbs" }
}
$iAbrir.Font = New-Object Drawing.Font($iAbrir.Font, [Drawing.FontStyle]::Bold)
$iLiga = Add-Item "Iniciar o Nous" {
    if ($S.rodando) { Start-Oculto "parar-nous.vbs" } else { Start-Oculto "nous-hidden.vbs" }
}
$iCode = Add-Item "Abrir o Nous Code" { Start-Oculto "nous-code.vbs" }
# "Usar no celular": mostra se esta' ligado e deixa desligar (ligar e' no painel Seu Nous,
# onde aparece o QR). Desligar passa pelo monitor, que tambem tira a regra do firewall.
$iCel = Add-Item "" $null $false
$iCelOff = Add-Item "Desligar o celular" {
    $r = [Windows.Forms.MessageBox]::Show("Desligar o uso do Nous no celular?`n`nOs celulares ja ligados continuam registrados e voltam a abrir quando voce ligar de novo. O Windows pode pedir permissao para fechar a porta.",
        "Usar no celular", "OKCancel", "Question")
    if ($r -ne "OK") { return }
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$PortaMonitor/celular/desligar" -Method Post -ContentType "application/json" -Body "{}" -TimeoutSec 120 | Out-Null
        $script:ni.ShowBalloonTip(4000, "Nous", "O celular foi desligado.", "Info")
    } catch {
        [void][Windows.Forms.MessageBox]::Show("Nao consegui desligar agora. Abra o Nous e use o painel Seu Nous > Celular.", "Nous")
    }
}
$iCelOff.Available = $false
Add-Sep
$iAtuApp = Add-Item "" {
    $est = Read-Json $estPath
    if (-not $est -or -not $est.disponivel) { return }
    $r = [Windows.Forms.MessageBox]::Show(
        ("Atualizar o Nous da versao {0} para a {1}?`n`nO Nous fecha por alguns minutos e abre de novo sozinho. Suas conversas e arquivos nao sao tocados; se algo der errado, ele volta para a versao atual." -f (Get-Versao), $est.versao_nova),
        "Atualizar o Nous", "OKCancel", "Question")
    if ($r -eq "OK") {
        $script:ni.ShowBalloonTip(6000, "Nous", "Atualizando o Nous... pode levar alguns minutos.", "Info")
        [void](Start-Atualizador "Aplicar")
    }
}
$iAtuApp.Available = $false
$iAtuMod = Add-Item "" {
    $est = Read-Json $estPath
    $lista = Get-Novos $est
    if (-not $lista.Count) { return }
    $nomes = ($lista | ForEach-Object { $_.nome }) -join ", "
    $r = [Windows.Forms.MessageBox]::Show(
        ("Baixar a versao nova de: {0}?`n`nSo' as partes que mudaram sao baixadas. O progresso aparece na Loja de Modelos do Nous." -f $nomes),
        "Atualizar modelos", "OKCancel", "Question")
    if ($r -ne "OK") { return }
    foreach ($m in $lista) {
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$PortaMonitor/update/modelos/atualizar" -Method Post -ContentType "application/json" `
                -Body (ConvertTo-Json -InputObject @{ model = $m.nome }) -TimeoutSec 8 | Out-Null
            $script:modelosEmAtualizacao = $true
        } catch {
            [void][Windows.Forms.MessageBox]::Show("Para atualizar os modelos, abra o Nous primeiro (menu: Abrir o Nous) e tente de novo.", "Nous")
            return
        }
    }
    $script:ni.ShowBalloonTip(6000, "Nous", "Baixando a versao nova dos modelos. Acompanhe na Loja de Modelos.", "Info")
}
$iAtuMod.Available = $false
$iProcura = Add-Item "Procurar atualizacoes agora" {
    $script:procVerif = Start-Atualizador "Tudo" -Forcar
    $script:ni.ShowBalloonTip(3000, "Nous", "Procurando atualizacoes...", "Info")
}
$iAuto = Add-Item "Procurar atualizacoes sozinho (1 vez por dia, usa a internet)" {
    Set-Cfg "verificar" (-not [bool](Get-Cfg).verificar)
}
$iAuto.CheckOnClick = $false
Add-Sep
$iWin = Add-Item "Abrir este icone junto com o Windows" {
    $v = (Get-ItemProperty -Path $ChaveRun -Name "Nous" -ErrorAction SilentlyContinue).Nous
    if ($v) { Remove-ItemProperty -Path $ChaveRun -Name "Nous" -ErrorAction SilentlyContinue }
    else {
        if (-not (Test-Path $ChaveRun)) { New-Item -Path $ChaveRun -Force | Out-Null }
        Set-ItemProperty -Path $ChaveRun -Name "Nous" -Value ('wscript.exe "{0}"' -f (Join-Path $launchers "bandeja.vbs"))
    }
}
$iBand = Add-Item "Mostrar este icone sempre que o Nous abrir" {
    Set-Cfg "bandeja" (-not [bool](Get-Cfg).bandeja)
}
Add-Sep
$iSair = Add-Item "Sair (o Nous continua como esta)" {
    $script:fim = $true
    $script:ni.Visible = $false
    [Windows.Forms.Application]::Exit()
}

# "Usar no celular": ligado = o portao (nous_celular.py) esta' vivo (NousData/celular/estado.json)
function Get-Celular {
    $r = @{ ligado = $false; aparelhos = 0 }
    $pasta = Join-Path $DataDir "celular"
    $e = Read-Json (Join-Path $pasta "estado.json")
    if ($e -and $e.pid) {
        $p = Get-Process -Id ([int]$e.pid) -ErrorAction SilentlyContinue
        if ($p) { $r.ligado = $true }
    }
    $r.aparelhos = @(Get-ChildItem -LiteralPath (Join-Path $pasta "aparelhos") -Filter "*.json" -ErrorAction SilentlyContinue).Count
    return $r
}

# --- atualiza os textos do menu com o que a coleta achou -----------------------
function Update-Menu {
    $est = Read-Json $estPath
    $cfg = Get-Cfg
    $ver = Get-Versao
    $iCab.Text = "Nous $ver - " + $(if ($S.rodando) { "rodando" } else { "parado" })

    $carregado = @($S.modelos)
    if ($carregado.Count -gt 0) {
        $m = $carregado[0]
        $onde = if ($m.tudo_gpu) { "placa de video" } elseif ($m.gpu) { "placa de video e processador" } else { "processador" }
        $iOnde.Text = "Rodando em: $onde" + $(if ($S.gpu -and $m.gpu) { " ($($S.gpu))" } elseif ($S.cpu -and -not $m.gpu) { " ($($S.cpu))" } else { "" })
        $iModelo.Text = ("Modelo carregado: {0} ({1} GB)" -f $m.nome, $m.gb.ToString("0.0", $pt))
    } else {
        $iOnde.Text = if ($S.gpu) { "Placa de video: $($S.gpu)" } elseif ($S.cpu) { "Processador: $($S.cpu)" } else { "Hardware: lendo..." }
        $iModelo.Text = if ($S.ollama) { "Nenhum modelo carregado agora" } else { "Ollama parado (sobe sozinho quando voce abrir o Nous)" }
    }
    $iMem.Text = if ($S.ram_total -gt 0) {
        "Memoria: {0} de {1} GB em uso ({2}%)" -f ([double]$S.ram_usada).ToString("0.0", $pt), ([double]$S.ram_total).ToString("0.0", $pt), [int](100 * $S.ram_usada / $S.ram_total)
    } else { "Memoria: lendo..." }

    $iAbrir.Text = if ($S.rodando) { "Abrir o Nous" } else { "Abrir o Nous (inicia e abre)" }
    $iLiga.Text = if ($S.rodando) { "Parar o Nous" } else { "Iniciar o Nous" }

    $atualizando = $est -and $est.fase -in "preparando", "baixando", "conferindo", "instalando", "reiniciando"
    $iAtuApp.Available = [bool]($est -and $est.disponivel -and -not $atualizando)
    if ($iAtuApp.Available) { $iAtuApp.Text = "Ha uma versao nova do Nous ($($est.versao_nova)) - Atualizar" }
    $novos = Get-Novos $est
    $iAtuMod.Available = [bool]($novos.Count -gt 0 -and $S.ollama)
    if ($iAtuMod.Available) { $iAtuMod.Text = if ($novos.Count -eq 1) { "O modelo $($novos[0].nome) tem versao nova - Atualizar" } else { "$($novos.Count) modelos tem versao nova - Atualizar" } }
    $iProcura.Enabled = -not $atualizando
    $iProcura.Text = if ($atualizando) { "Atualizando: " + $est.mensagem } else { "Procurar atualizacoes agora" }
    $iAuto.Checked = [bool]$cfg.verificar
    $iBand.Checked = [bool]$cfg.bandeja
    $iWin.Checked = [bool](Get-ItemProperty -Path $ChaveRun -Name "Nous" -ErrorAction SilentlyContinue).Nous
    $iCode.Enabled = $true
    $cel = Get-Celular
    $iCel.Text = if ($cel.ligado) { "Celular: ligado ({0})" -f $(if ($cel.aparelhos -eq 1) { "1 aparelho" } else { "$($cel.aparelhos) aparelhos" }) } else { "Celular: desligado" }
    $iCelOff.Available = [bool]$cel.ligado
    $script:ultimoEst = $est
}

# --- modo teste: escreve o menu e sai -------------------------------------------
if ($Teste) {
    & $coleta $S $PortaNous $OllamaUrl $DataDir
    Update-Menu
    if ($Clicar) {
        foreach ($i in $menu.Items) { if ($i.Text -like "$Clicar*") { $i.PerformClick(); break } }
        Update-Menu
    }
    foreach ($i in $menu.Items) {
        if ($i -is [Windows.Forms.ToolStripSeparator]) { "---" }
        elseif ($i.Available) { "{0}[{1}] {2}" -f $(if ($i.Checked) { "(x) " } else { "    " }), $(if ($i.Enabled) { "ativo" } else { "info " }), $i.Text }
    }
    if ($Captura) {
        $menu.Show(60, 60)
        [Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 600
        [Windows.Forms.Application]::DoEvents()
        $b = $menu.Bounds
        $bmp = New-Object Drawing.Bitmap($b.Width, $b.Height)
        $gr = [Drawing.Graphics]::FromImage($bmp)
        $gr.CopyFromScreen($b.Location, [Drawing.Point]::Empty, $b.Size)
        $bmp.Save($Captura, [Drawing.Imaging.ImageFormat]::Png)
        $gr.Dispose(); $bmp.Dispose()
        $menu.Close()
    }
    return
}

# --- o icone ---------------------------------------------------------------------
$icones = @{ verde = (New-IconeEstado "#3ad07a"); cinza = (New-IconeEstado "#8a8a8a"); ambar = (New-IconeEstado "#e7a52e") }
$script:ni = New-Object Windows.Forms.NotifyIcon
$ni = $script:ni
$ni.Icon = $icones.cinza
$ni.Text = "Nous"
$ni.ContextMenuStrip = $menu
$ni.Visible = $true
$ni.add_MouseDoubleClick({ param($s, $e) if ($e.Button -eq "Left") { $iAbrir.PerformClick() } })
$ni.add_BalloonTipClicked({
    # clicar no aviso de versao nova abre o menu na hora de decidir
    if ($script:balaoAcao -eq "app") { $iAtuApp.PerformClick() }
    elseif ($script:balaoAcao -eq "modelos") { $iAtuMod.PerformClick() }
    $script:balaoAcao = $null
})
$menu.add_Opening({ Update-Menu })

# --- coleta em segundo plano -----------------------------------------------------
$rs = [runspacefactory]::CreateRunspace()
$rs.ApartmentState = "MTA"
$rs.Open()
$ps = [powershell]::Create()
$ps.Runspace = $rs
[void]$ps.AddScript({
    param($S, $coletaTxt, $porta, $ollama, $dataDir)
    $blk = [scriptblock]::Create($coletaTxt)
    while ($true) {
        try { & $blk $S $porta $ollama $dataDir } catch {}
        Start-Sleep -Seconds 5
    }
}).AddArgument($S).AddArgument($coletaTxt).AddArgument($PortaNous).AddArgument($OllamaUrl).AddArgument($DataDir)
[void]$ps.BeginInvoke()

# --- relogio da interface: icone, dica, avisos ------------------------------------
$script:fim = $false
$script:procVerif = $null
$script:balaoAcao = $null
$script:avisouApp = $null
$script:avisouMod = ""
$script:fasePassada = $null
$script:proxVerif = (Get-Date).AddSeconds(25)
$script:ultimoEst = $null

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 3000
$timer.add_Tick({
    Update-Menu
    $est = $script:ultimoEst
    $atualizando = $est -and $est.fase -in "preparando", "baixando", "conferindo", "instalando", "reiniciando"
    $cor = if ($atualizando) { "ambar" } elseif ($est -and ($est.disponivel -or (Get-Novos $est).Count -gt 0)) { "ambar" } elseif ($S.rodando) { "verde" } else { "cinza" }
    if ($ni.Icon -ne $icones[$cor]) { $ni.Icon = $icones[$cor] }
    $txt = if ($atualizando) { "Nous - atualizando " + $est.pct + "%" }
           elseif ($S.rodando) { "Nous - rodando" + $(if (@($S.modelos).Count) { ": " + @($S.modelos)[0].nome } else { "" }) }
           else { "Nous - parado" }
    if ($txt.Length -gt 63) { $txt = $txt.Substring(0, 63) }
    $ni.Text = $txt

    # 1o uso: deixa claro que procurar atualizacao e' uma ida a' internet (e como desligar)
    $cfg = Get-Cfg
    if (-not $cfg.aviso_visto) {
        Set-Cfg "aviso_visto" $true
        $ni.ShowBalloonTip(15000, "Nous", "O Nous procura atualizacoes 1 vez por dia (usa a internet). Para desligar, clique com o botao direito neste icone.", "Info")
        return
    }
    # versao nova / modelos novos: avisa uma vez por versao
    if ($est -and $est.disponivel -and $est.versao_nova -and $script:avisouApp -ne $est.versao_nova -and -not $atualizando) {
        $script:avisouApp = $est.versao_nova
        $script:balaoAcao = "app"
        $ni.ShowBalloonTip(15000, "Nous", "Ha uma versao nova do Nous ($($est.versao_nova)). Clique aqui para atualizar.", "Info")
    }
    $novos = (Get-Novos $est | ForEach-Object { $_.nome }) -join ","
    if ($novos -and $novos -ne $script:avisouMod -and $S.ollama -and $script:balaoAcao -ne "app") {
        $script:avisouMod = $novos
        $script:balaoAcao = "modelos"
        $ni.ShowBalloonTip(15000, "Nous", "Ha modelos com versao nova. Clique aqui para atualizar.", "Info")
    }
    # resultado de uma atualizacao feita agora ha pouco
    if ($est -and $est.fase -in "concluida", "falhou", "revertida" -and $est.mensagem -and $script:fasePassada -ne ($est.fase + $est.mensagem)) {
        $script:fasePassada = $est.fase + $est.mensagem
        $recente = (Test-Path $estPath) -and ((Get-Date) - (Get-Item $estPath).LastWriteTime).TotalMinutes -lt 3
        if ($recente) { $ni.ShowBalloonTip(10000, "Nous", $est.mensagem, $(if ($est.fase -eq "concluida") { "Info" } else { "Warning" })) }
    }
    # fim do "Procurar agora"
    if ($script:procVerif -and $script:procVerif.HasExited) {
        $script:procVerif = $null
        $msg = if ($est.erro) { $est.erro } elseif ($est.disponivel) { "Ha uma versao nova do Nous ($($est.versao_nova))." } else { "Seu Nous esta na versao mais nova ($(Get-Versao))." }
        if ((Get-Novos $est).Count -gt 0) { $msg += " " + (Get-Novos $est).Count + " modelo(s) com versao nova." }
        $ni.ShowBalloonTip(8000, "Nous", $msg, "Info")
    }
    # verificacao diaria (o atualizador se limita sozinho a 1 vez por dia e respeita o "desligar")
    if ((Get-Date) -ge $script:proxVerif) {
        $script:proxVerif = (Get-Date).AddHours(6)
        if ($cfg.verificar -and -not $atualizando -and -not $script:procVerif) { [void](Start-Atualizador "Tudo") }
    }
})
$timer.Start()
Update-Menu

[Windows.Forms.Application]::Run()

# --- saida ------------------------------------------------------------------------
$timer.Stop()
$ni.Visible = $false
$ni.Dispose()
try { $ps.Stop(); $rs.Close() } catch {}
try { $mutex.ReleaseMutex() } catch {}
