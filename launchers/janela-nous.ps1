<#
  Nous - janela propria (Nous.exe): compilar, conferir e abrir.
  Usado pelo instalador, pelo atualizador, pelo start-nous.ps1 e pela bandeja.

  O Nous.exe (janela\Nous.cs) e' compilado NA MAQUINA com o csc.exe do .NET
  Framework 4.8, que ja' vem no Windows, contra o SDK do WebView2 em janela\lib.
  Ele so' mostra a janela: quem liga o Nous continua sendo o start-nous.ps1 (o
  Nous.exe antigo, do ps2exe, embutia o codigo e as atualizacoes nao chegavam).
  Sem WebView2 ou sem compilar, tudo continua abrindo no navegador.

    Test-WebView2                     o runtime do WebView2 esta instalado?
    Get-JanelaHash  <app>             assinatura do codigo da janela (fonte, DLLs, icone)
    Test-JanelaAtual <app>            o Nous.exe compilado e' deste codigo?
    Build-NousJanela -AppDir <app> [-Saida <pasta>]   compila; $script:JanelaErro diz o porque
    Get-NousJanela <app>              caminho do Nous.exe, se da' para usar; senao $null
    Open-NousJanela <app> [args]      abre a janela; $false se nao deu (use o navegador)
#>

$script:JanelaErro = ""
$script:JanelaLibs = @("Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll", "WebView2Loader.dll")

function Get-JanelaExe([string]$AppDir) { Join-Path $AppDir "janela\bin\Nous.exe" }

function Test-WebView2 {
    $guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    foreach ($k in "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$guid",
                   "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid",
                   "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$guid") {
        $pv = (Get-ItemProperty -Path $k -Name pv -ErrorAction SilentlyContinue).pv
        if ($pv -and $pv -ne "0.0.0.0") { return $true }
    }
    return $false
}

function Get-JanelaHash([string]$AppDir) {
    $arqs = @((Join-Path $AppDir "janela\Nous.cs"), (Join-Path $AppDir "branding\assets\nous.ico")) +
            @($script:JanelaLibs | ForEach-Object { Join-Path $AppDir "janela\lib\$_" })
    $junto = ($arqs | ForEach-Object {
        if (Test-Path -LiteralPath $_) { (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash } else { "falta" }
    }) -join "|"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return (($sha.ComputeHash([Text.Encoding]::ASCII.GetBytes($junto)) | ForEach-Object { $_.ToString("x2") }) -join "") }
    finally { $sha.Dispose() }
}

function Test-JanelaAtual([string]$AppDir) {
    $exe = Get-JanelaExe $AppDir
    $marca = Join-Path (Split-Path $exe) "versao.txt"
    if (-not (Test-Path -LiteralPath $exe) -or -not (Test-Path -LiteralPath $marca)) { return $false }
    return ((Get-Content -LiteralPath $marca -Raw).Trim() -eq (Get-JanelaHash $AppDir))
}

# Poe um arquivo no lugar mesmo com o antigo em uso (janela aberta): o Windows deixa
# renomear um .exe/.dll em execucao; o antigo sai na proxima compilacao.
function Set-ArquivoNoLugar([string]$de, [string]$para) {
    if (Test-Path -LiteralPath $para) {
        # igual ao que ja' esta la' (as DLLs quase sempre): nao mexe
        if ((Get-FileHash -LiteralPath $de).Hash -eq (Get-FileHash -LiteralPath $para).Hash) {
            Remove-Item -LiteralPath $de -Force -ErrorAction SilentlyContinue
            return
        }
        try { Remove-Item -LiteralPath $para -Force -ErrorAction Stop }
        catch { Rename-Item -LiteralPath $para -NewName ((Split-Path $para -Leaf) + ".velho-" + [DateTime]::Now.Ticks) -ErrorAction Stop }
    }
    Move-Item -LiteralPath $de -Destination $para -Force -ErrorAction Stop
}

function Build-NousJanela {
    param([Parameter(Mandatory = $true)][string]$AppDir, [string]$Saida = "")
    $script:JanelaErro = ""
    $csc = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
    if (-not (Test-Path -LiteralPath $csc)) { $script:JanelaErro = "falta o csc.exe do .NET Framework 4.8"; return $false }
    $fonte = Join-Path $AppDir "janela\Nous.cs"
    $lib = Join-Path $AppDir "janela\lib"
    $ico = Join-Path $AppDir "branding\assets\nous.ico"
    foreach ($f in @($fonte, $ico) + @($script:JanelaLibs | ForEach-Object { Join-Path $lib $_ })) {
        if (-not (Test-Path -LiteralPath $f)) { $script:JanelaErro = "falta $f"; return $false }
    }
    if (-not $Saida) { $Saida = Split-Path (Get-JanelaExe $AppDir) }
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("nous-janela-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        $ref = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319"
        $a = @("/nologo", "/target:winexe", "/platform:x64", "/optimize+", "/utf8output",
               "/win32icon:$ico", "/out:$(Join-Path $tmp 'Nous.exe')",
               "/reference:$(Join-Path $ref 'System.Windows.Forms.dll')", "/reference:$(Join-Path $ref 'System.Drawing.dll')",
               "/reference:$(Join-Path $lib 'Microsoft.Web.WebView2.Core.dll')",
               "/reference:$(Join-Path $lib 'Microsoft.Web.WebView2.WinForms.dll')", $fonte)
        $saidaCsc = & $csc @a 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $tmp "Nous.exe"))) {
            $script:JanelaErro = "a compilacao falhou: " + $saidaCsc.Trim()
            return $false
        }
        foreach ($d in $script:JanelaLibs) { Copy-Item -LiteralPath (Join-Path $lib $d) -Destination $tmp }
        [IO.File]::WriteAllText((Join-Path $tmp "versao.txt"), (Get-JanelaHash $AppDir))
        New-Item -ItemType Directory -Force -Path $Saida | Out-Null
        Get-ChildItem -LiteralPath $Saida -Filter "*.velho-*" -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
        foreach ($f in @($script:JanelaLibs) + @("Nous.exe", "versao.txt")) {
            Set-ArquivoNoLugar (Join-Path $tmp $f) (Join-Path $Saida $f)
        }
        return $true
    } catch {
        $script:JanelaErro = $_.Exception.Message
        return $false
    } finally {
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-NousJanela([string]$AppDir) {
    if ($env:NOUS_JANELA -eq "0") { return $null }   # para voltar ao navegador sem desinstalar
    $exe = Get-JanelaExe $AppDir
    if ((Test-Path -LiteralPath $exe) -and (Test-WebView2)) { return $exe }
    return $null
}

function Open-NousJanela([string]$AppDir, [string[]]$Argumentos = @()) {
    $exe = Get-NousJanela $AppDir
    if (-not $exe) { return $false }
    try {
        if ($Argumentos.Count) { Start-Process -FilePath $exe -ArgumentList $Argumentos -ErrorAction Stop }
        else { Start-Process -FilePath $exe -ErrorAction Stop }
        return $true
    } catch { return $false }
}
