<#
  Nous — Desconectar Email
  Remove a conta de email configurada (apaga .email_account.json).
#>
$ErrorActionPreference = "SilentlyContinue"

Add-Type -AssemblyName System.Windows.Forms

$apiBase = "http://127.0.0.1:8995"

# Verificar conta ativa
$status = $null
try { $status = Invoke-RestMethod "$apiBase/status" -TimeoutSec 5 } catch {}

if (-not $status -or -not $status.connected) {
    [System.Windows.Forms.MessageBox]::Show(
        "Nenhuma conta de email está conectada.",
        "Nous — Email",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
    exit 0
}

$res = [System.Windows.Forms.MessageBox]::Show(
    "Desconectar a conta $($status.user)?`n`nAs credenciais serão apagadas. Seus emails NÃO são deletados.",
    "Nous — Desconectar Email",
    [System.Windows.Forms.MessageBoxButtons]::YesNo,
    [System.Windows.Forms.MessageBoxIcon]::Question
)
if ($res -ne [System.Windows.Forms.DialogResult]::Yes) { exit 0 }

try {
    Invoke-RestMethod "$apiBase/disconnect" -Method Post -TimeoutSec 5 | Out-Null
} catch {
    # Se a API não responder, apaga o arquivo diretamente
    $f = Join-Path $env:USERPROFILE "NousData\.email_account.json"
    if (Test-Path $f) { Remove-Item $f -Force }
}

[System.Windows.Forms.MessageBox]::Show(
    "Conta desconectada. As credenciais foram apagadas.",
    "Nous — Email Desconectado",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null
