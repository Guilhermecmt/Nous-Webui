<#
  Nous — Ativar Nuvem NVIDIA
  Solicita a chave NVIDIA NIM, valida, salva e registra a conexao
  no banco do Open WebUI. Tudo grafico, sem janela de terminal.
#>
$ErrorActionPreference = "SilentlyContinue"

Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

$dataDir = Join-Path $env:USERPROFILE "NousData"
$keyFile = Join-Path $dataDir ".nvidia_api_key"
$py      = Join-Path $env:USERPROFILE "open-webui\Scripts\python.exe"
$reg     = Join-Path $PSScriptRoot "register_nvidia.py"

# Verificar se ja tem chave
$current = ""
if (Test-Path $keyFile) { $current = (Get-Content $keyFile -Raw).Trim() }

$prompt = if ($current) {
    "Cole sua chave NVIDIA NIM abaixo.`n`nChave atual: $($current.Substring(0,12))...`n`n(Deixe em branco para manter a atual)"
} else {
    "Cole sua chave NVIDIA NIM abaixo.`n`nObtida gratuitamente em build.nvidia.com/models`n`nATENCAO: conversas com modelos de nuvem sao processadas`nnos servidores da NVIDIA. Sua memoria pessoal local NAO e enviada."
}

$input = [Microsoft.VisualBasic.Interaction]::InputBox(
    $prompt,
    "Nous — Ativar Nuvem NVIDIA",
    ""
)

# Cancelou o dialogo
if ($null -eq $input) { exit 0 }

# Deixou em branco: manter chave atual (se existir)
if ($input.Trim() -eq "") {
    if ($current) {
        [System.Windows.Forms.MessageBox]::Show(
            "Chave mantida. Nenhuma alteracao feita.",
            "Nous — Nuvem NVIDIA",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    } else {
        [System.Windows.Forms.MessageBox]::Show(
            "Nenhuma chave informada. Operacao cancelada.",
            "Nous — Nuvem NVIDIA",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
    }
    exit 0
}

$apiKey = $input.Trim()

# Validar formato basico
if (-not $apiKey.StartsWith("nvapi-")) {
    [System.Windows.Forms.MessageBox]::Show(
        "Chave invalida. A chave NVIDIA deve comecar com 'nvapi-'.`n`nVerifique em build.nvidia.com/models.",
        "Nous — Erro",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

# Validar chave online
try {
    $resp = Invoke-WebRequest `
        -Uri "https://integrate.api.nvidia.com/v1/models" `
        -Headers @{ Authorization = "Bearer $apiKey" } `
        -TimeoutSec 15 `
        -UseBasicParsing `
        -ErrorAction Stop

    if ($resp.StatusCode -ne 200) { throw "HTTP $($resp.StatusCode)" }
} catch {
    $msg = $_.Exception.Message
    if ($msg -like "*401*" -or $msg -like "*Unauthorized*") {
        [System.Windows.Forms.MessageBox]::Show(
            "Chave rejeitada pela NVIDIA (erro 401).`n`nVerifique se a chave e valida em build.nvidia.com/models.",
            "Nous — Chave Invalida",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    } else {
        [System.Windows.Forms.MessageBox]::Show(
            "Nao foi possivel validar a chave (sem conexao?).`n`nErro: $msg`n`nA chave sera' salva assim mesmo.",
            "Nous — Aviso",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
    }
    # nao abortar em caso de erro de rede — salvar mesmo assim
}

# Salvar chave
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
[System.IO.File]::WriteAllText($keyFile, $apiKey)

# Registrar no banco (se o Python/venv existir)
if ((Test-Path $py) -and (Test-Path $reg)) {
    & $py $reg --data-dir $dataDir | Out-Null
}

[System.Windows.Forms.MessageBox]::Show(
    "Nuvem NVIDIA ativada com sucesso!`n`nOs modelos de nuvem aparecerao no dropdown apos reiniciar o Nous.`n`nATENCAO: conversas com esses modelos saem da sua maquina e sao processadas pela NVIDIA.",
    "Nous — Nuvem Ativada",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null
