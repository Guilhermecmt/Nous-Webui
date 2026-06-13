<#
  Nous — Desativar Nuvem NVIDIA
  Remove a chave e limpa a conexao da NVIDIA do banco do Open WebUI.
  Tudo grafico, sem janela de terminal.
#>
$ErrorActionPreference = "SilentlyContinue"

Add-Type -AssemblyName System.Windows.Forms

$dataDir = Join-Path $env:USERPROFILE "NousData"
$keyFile = Join-Path $dataDir ".nvidia_api_key"
$py      = Join-Path $env:USERPROFILE "open-webui\Scripts\python.exe"
$reg     = Join-Path $PSScriptRoot "register_nvidia.py"

# Verificar se existe chave
if (-not (Test-Path $keyFile)) {
    [System.Windows.Forms.MessageBox]::Show(
        "A Nuvem NVIDIA nao esta ativa. Nada a desativar.",
        "Nous — Nuvem NVIDIA",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
    exit 0
}

# Confirmar
$confirm = [System.Windows.Forms.MessageBox]::Show(
    "Desativar a Nuvem NVIDIA?`n`nOs modelos de nuvem serao removidos do dropdown apos reiniciar o Nous.",
    "Nous — Confirmar Desativacao",
    [System.Windows.Forms.MessageBoxButtons]::YesNo,
    [System.Windows.Forms.MessageBoxIcon]::Question
)

if ($confirm -ne [System.Windows.Forms.DialogResult]::Yes) { exit 0 }

# Remover arquivo de chave
Remove-Item -Path $keyFile -Force -ErrorAction SilentlyContinue

# Limpar conexao do banco (register sem chave = remove)
if ((Test-Path $py) -and (Test-Path $reg)) {
    & $py $reg --data-dir $dataDir | Out-Null
}

[System.Windows.Forms.MessageBox]::Show(
    "Nuvem NVIDIA desativada.`n`nReinicie o Nous para aplicar a alteracao.",
    "Nous — Nuvem Desativada",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null
