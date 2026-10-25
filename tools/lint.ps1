<#
.SYNOPSIS
  Nous - checagens rapidas antes de publicar (local ou no GitHub Actions).
.DESCRIPTION
  1) Todo .ps1/.bat/.vbs e' ASCII puro. O PowerShell 5.1 le arquivo sem BOM
     como Windows-1252: um travessao (em dash) dentro de string vira aspas curvas, quebra a
     sintaxe e o script (que roda escondido) falha calado. Foi o que deixou o
     ativar-nuvem.bat sem funcionar.
  2) Todo .ps1 e' analisado pelo parser do PowerShell em que este lint roda
     (rode com powershell.exe = 5.1, o mesmo dos usuarios).
  3) Todo .py compila; todo .json carrega; o nous-loader.js e' JS valido
     (estes dois ultimos so' se python/node existirem).
  Sai com 1 se algo falhar.
#>
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$fail = 0
function Bad($msg) { Write-Host "  [FALHA] $msg" -ForegroundColor Red; $script:fail++ }

$files = git ls-files
if (-not $files) { $files = Get-ChildItem -Recurse -File | ForEach-Object { Resolve-Path -Relative $_.FullName } }

Write-Host "== ASCII nos scripts do Windows" -ForegroundColor Cyan
foreach ($f in $files | Where-Object { $_ -match '\.(ps1|bat|vbs)$' }) {
    $bytes = [IO.File]::ReadAllBytes((Join-Path $root $f))
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    if (-not $hasBom -and ($bytes | Where-Object { $_ -gt 127 } | Select-Object -First 1)) {
        $line = 0
        foreach ($l in [IO.File]::ReadAllLines((Join-Path $root $f), [Text.Encoding]::UTF8)) {
            $line++
            if ($l -match '[^\x00-\x7F]') { Bad "$f`:$line tem caractere nao-ASCII (troque por ASCII; acentos so' em .js/.html/.py)"; break }
        }
    }
}

Write-Host "== Sintaxe PowerShell ($($PSVersionTable.PSVersion))" -ForegroundColor Cyan
foreach ($f in $files | Where-Object { $_ -match '\.ps1$' }) {
    $tokens = $null; $errs = $null
    [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root $f), [ref]$tokens, [ref]$errs) | Out-Null
    foreach ($e in $errs) { Bad "$f`:$($e.Extent.StartLineNumber) $($e.Message)" }
}

$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
    Write-Host "== Python e JSON" -ForegroundColor Cyan
    $pyFiles = @($files | Where-Object { $_ -match '\.py$' })
    $jsonFiles = @($files | Where-Object { $_ -match '\.json$' })
    $code = "import ast,io,json,sys`nbad=0`nfor p in sys.argv[1:]:`n    try:`n        s=io.open(p,encoding='utf-8').read()`n        json.loads(s) if p.endswith('.json') else ast.parse(s,p)`n    except Exception as e:`n        print('  [FALHA] %s: %s' % (p,e)); bad+=1`nsys.exit(1 if bad else 0)"
    & $py.Source -c $code @pyFiles @jsonFiles
    if ($LASTEXITCODE -ne 0) { $fail++ }

    # Agenda: testes da sincronizacao CalDAV (servidor de mentira local; pulam sozinhos
    # se faltar requests/dateutil, e usam o Radicale se ele estiver instalado)
    $agTests = Join-Path $root "agenda/tests"
    if (Test-Path $agTests) {
        Write-Host "== Agenda (CalDAV)" -ForegroundColor Cyan
        $ErrorActionPreference = "Continue"   # o unittest escreve no stderr
        $out = & $py.Source -m unittest discover -s $agTests 2>&1 | Out-String
        $ErrorActionPreference = "Stop"
        if ($LASTEXITCODE -ne 0) { Write-Host $out; Bad "agenda/tests: testes falharam" }
    }
}

$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    Write-Host "== JavaScript" -ForegroundColor Cyan
    foreach ($f in $files | Where-Object { $_ -match '\.js$' }) {
        & $node.Source --check (Join-Path $root $f)
        if ($LASTEXITCODE -ne 0) { Bad "$f nao e' JavaScript valido" }
    }

    # Nous Code: checa os tipos (se o npm install do code/ foi feito) e roda os testes
    $code = Join-Path $root "code"
    if (Test-Path (Join-Path $code "servidor.ts")) {
        Write-Host "== Nous Code (TypeScript)" -ForegroundColor Cyan
        $tsc = Join-Path $code "node_modules\typescript\bin\tsc"
        if (Test-Path $tsc) {
            & $node.Source $tsc -p $code
            if ($LASTEXITCODE -ne 0) { Bad "code/: erro de tipos" }
        } else { Write-Host "  (tipos nao checados: rode npm install em code/)" -ForegroundColor DarkGray }
        Push-Location $code
        $out = & $node.Source --test "testes/*.test.ts" 2>&1 | Out-String
        $ok = $LASTEXITCODE -eq 0
        Pop-Location
        if (-not $ok) { Write-Host $out; Bad "code/: testes falharam" }
    }
}

Write-Host ""
if ($fail) { Write-Host "$fail problema(s)." -ForegroundColor Red; exit 1 }
Write-Host "Tudo certo." -ForegroundColor Green
exit 0
