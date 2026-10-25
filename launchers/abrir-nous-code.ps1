<#
  Nous Code - abre o IDE numa janela propria (atalho "Nous Code").
  Liga o servico (code/servidor.ts, porta 8998) se ele nao estiver no ar e
  pede a ele para abrir a janela (modo app do Edge, sem abas nem barra).
  Usa o Node do computador ou o portatil do Nous (launchers\node-nous.ps1);
  sem Node 22.18+ ou sem as dependencias, mostra o que fazer.
#>
$ErrorActionPreference = "SilentlyContinue"
$code = Join-Path $PSScriptRoot "..\code"
$srv  = Join-Path $code "servidor.ts"
if (-not $env:DATA_DIR) { $env:DATA_DIR = Join-Path $env:USERPROFILE "NousData" }

function Show-Error([string]$msg) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($msg, "Nous Code",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
}
function Test-Up {
    try { Invoke-RestMethod "http://127.0.0.1:8998/health" -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

if (-not (Test-Up)) {
    # o Node do computador ou o portatil que o instalador deixou em <app>\runtime\node
    . (Join-Path $PSScriptRoot "node-nous.ps1")
    $exe = Find-NousNode (Join-Path $PSScriptRoot "..")
    if (-not $exe) {
        Show-Error ("O Nous Code precisa do Node.js 22.18 ou mais novo.`n`n" +
            "Rode o instalar.bat de novo, com internet: ele baixa o Node sozinho.`n" +
            "(Ou instale pelo terminal com:  winget install OpenJS.NodeJS.LTS)")
        return
    }
    if (-not (Test-Path (Join-Path $code "node_modules\monaco-editor"))) {
        Show-Error ("Faltam as pecas do editor do Nous Code.`n`n" +
            "Rode o instalar.bat de novo (com internet): ele baixa o que falta.")
        return
    }
    Start-Process -FilePath $exe -ArgumentList "`"$srv`"" -WorkingDirectory $code -WindowStyle Hidden
    for ($i = 0; $i -lt 30 -and -not (Test-Up); $i++) { Start-Sleep -Milliseconds 500 }
    if (-not (Test-Up)) { Show-Error "O Nous Code nao abriu. Tente de novo; se continuar, reinicie o computador."; return }
}

Invoke-RestMethod "http://127.0.0.1:8998/abrir-janela" -Method Post -ContentType "application/json" -Body "{}" | Out-Null
