<#
  Nous.exe (janela propria): compila numa pasta temporaria e confere para onde cada
  endereco vai (codigo de saida do --destino). Sem janela na tela.
  Uso: powershell -File janela\testes\testar-janela.ps1   (sai com 1 se algo falhar)
#>
$ErrorActionPreference = "Stop"
$app = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
. (Join-Path $app "launchers\janela-nous.ps1")

$falhas = 0
function Confere([string]$nome, [bool]$ok, [string]$detalhe = "") {
    if ($ok) { Write-Host "  ok    $nome" }
    else { Write-Host "  FALHA $nome $detalhe" -ForegroundColor Red; $script:falhas++ }
}

$saida = Join-Path ([IO.Path]::GetTempPath()) ("nous-janela-teste-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
try {
    $ok = Build-NousJanela -AppDir $app -Saida $saida
    Confere "compila" $ok $script:JanelaErro
    if (-not $ok) { exit 1 }
    $exe = Join-Path $saida "Nous.exe"
    foreach ($dll in "Microsoft.Web.WebView2.Core.dll", "Microsoft.Web.WebView2.WinForms.dll", "WebView2Loader.dll") {
        Confere "copia $dll" (Test-Path -LiteralPath (Join-Path $saida $dll))
    }
    Confere "marca a versao do codigo" ((Get-Content -LiteralPath (Join-Path $saida "versao.txt") -Raw).Trim() -eq (Get-JanelaHash $app))

    # 0 Nous | 1 Nous Code | 2 outra pagina local | 3 site de fora | 4 bloqueado
    $casos = [ordered]@{
        "http://localhost:8080"                    = 0
        "http://127.0.0.1:8080/c/abc?x=1"          = 0
        "http://127.0.0.1:8998/?pasta=C%3A%2Fp"    = 1
        "http://localhost:8998/"                   = 1
        "http://127.0.0.1:8990/research/view?id=r" = 2
        "http://[::1]:8996/"                       = 2
        "https://exemplo.com/artigo"               = 3
        "http://192.168.0.10:8999/"                = 3
        "mailto:ana@exemplo.com"                   = 3
        "http://localhost.exemplo.com:8080/"       = 3
        "javascript:alert(1)"                      = 4
        "file:///C:/Windows/win.ini"               = 4
        "nao e endereco"                           = 4
    }
    foreach ($u in $casos.Keys) {
        $p = Start-Process -FilePath $exe -ArgumentList @("--destino", "`"$u`"") -Wait -PassThru -WindowStyle Hidden
        Confere "destino $u = $($casos[$u])" ($p.ExitCode -eq $casos[$u]) "(deu $($p.ExitCode))"
    }
    # a tela de carregamento do proprio Nous pode abrir; outro arquivo nao. O Nous.exe
    # acha o app duas pastas acima dele (janela\bin): aqui, duas acima da pasta do teste.
    $appDoTeste = [IO.Path]::GetFullPath((Join-Path $saida "..\.."))
    $loading = "file:///" + ((Join-Path $appDoTeste "launchers\loading.html") -replace '\\', '/')
    $p = Start-Process -FilePath $exe -ArgumentList @("--destino", "`"$loading`"") -Wait -PassThru -WindowStyle Hidden
    Confere "destino loading.html = 2" ($p.ExitCode -eq 2) "(deu $($p.ExitCode))"
    # --code so' aceita o Nous Code
    $p = Start-Process -FilePath $exe -ArgumentList @("--code", "`"https://exemplo.com`"") -Wait -PassThru -WindowStyle Hidden
    Confere "--code recusa site de fora" ($p.ExitCode -eq 4) "(deu $($p.ExitCode))"
} finally {
    Remove-Item -LiteralPath $saida -Recurse -Force -ErrorAction SilentlyContinue
}
if ($falhas) { Write-Host "$falhas falha(s)" -ForegroundColor Red; exit 1 }
Write-Host "Janela: tudo certo."
exit 0
