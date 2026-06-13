<#
  Nous — Conectar Email
  Solicita email e senha de app, detecta servidores IMAP/SMTP automaticamente,
  valida o login e salva as credenciais via API local (porta 8995).
  Tudo gráfico, sem janela de terminal.

  SEGURANÇA: usa SEMPRE senha de aplicativo (não a senha principal).
  O conteúdo dos emails é processado SOMENTE pelo modelo local — nunca vai à nuvem.
#>
$ErrorActionPreference = "SilentlyContinue"

Add-Type -AssemblyName Microsoft.VisualBasic
Add-Type -AssemblyName System.Windows.Forms

# Verificar se o serviço de email está no ar
$apiBase = "http://127.0.0.1:8995"
$apiUp = $false
try {
    $ping = Invoke-RestMethod "$apiBase/health" -TimeoutSec 3 -ErrorAction Stop
    $apiUp = $ping.ok -eq $true
} catch {}

# Se o serviço não estiver no ar, subir (requer que o Nous esteja rodando)
if (-not $apiUp) {
    $py  = Join-Path $env:USERPROFILE "open-webui\Scripts\python.exe"
    $api = Join-Path $PSScriptRoot "nous_email_api.py"
    if ((Test-Path $py) -and (Test-Path $api)) {
        Start-Process -FilePath $py -ArgumentList "`"$api`"" -WindowStyle Hidden
        Start-Sleep -Seconds 2
        try { $ping = Invoke-RestMethod "$apiBase/health" -TimeoutSec 3; $apiUp = $ping.ok -eq $true } catch {}
    }
    if (-not $apiUp) {
        [System.Windows.Forms.MessageBox]::Show(
            "O Nous precisa estar rodando para conectar o email.`nAbra o Nous pelo atalho e tente novamente.",
            "Nous — Email",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
        exit 1
    }
}

# Verificar se já há conta conectada
$status = $null
try { $status = Invoke-RestMethod "$apiBase/status" -TimeoutSec 5 } catch {}
if ($status -and $status.connected) {
    $res = [System.Windows.Forms.MessageBox]::Show(
        "Conta conectada: $($status.user)`n`nDeseja desconectar e configurar outra conta?",
        "Nous — Email já conectado",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    if ($res -ne [System.Windows.Forms.DialogResult]::Yes) { exit 0 }
}

# Instrução sobre senha de app
[System.Windows.Forms.MessageBox]::Show(
    "Para conectar seu email ao Nous, você precisará de uma SENHA DE APLICATIVO.`n`n" +
    "NÃO use sua senha principal.`n`n" +
    "Como gerar a senha de aplicativo:`n" +
    "  Gmail:   myaccount.google.com → Segurança → Senhas de app`n" +
    "  Outlook: account.microsoft.com → Segurança → Senha de aplicativo`n`n" +
    "A senha de aplicativo tem 16 caracteres (Gmail) ou similar.`n" +
    "Você pode revogar a qualquer momento sem afetar sua senha principal.",
    "Nous — Como obter a senha de app",
    [System.Windows.Forms.MessageBoxButtons]::OK,
    [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null

# Solicitar email
$emailAddr = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Digite seu endereço de email:`n`n(Suporte automático: Gmail, Outlook/Hotmail, Yahoo)",
    "Nous — Conectar Email",
    ""
)
if ($null -eq $emailAddr -or $emailAddr.Trim() -eq "") { exit 0 }
$emailAddr = $emailAddr.Trim()

# Solicitar senha de app
$appPwd = [Microsoft.VisualBasic.Interaction]::InputBox(
    "Digite a SENHA DE APLICATIVO para $emailAddr`n`n" +
    "Não é sua senha principal — é a senha de 16 dígitos gerada nas configurações de segurança da conta.`n`n" +
    "Ela ficará salva somente no seu computador (NousData).",
    "Nous — Senha de Aplicativo",
    ""
)
if ($null -eq $appPwd -or $appPwd.Trim() -eq "") {
    [System.Windows.Forms.MessageBox]::Show(
        "Nenhuma senha informada. Operação cancelada.",
        "Nous — Email",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Warning
    ) | Out-Null
    exit 0
}
$appPwd = $appPwd.Trim()

# Enviar para a API
$body = @{ user = $emailAddr; app_password = $appPwd } | ConvertTo-Json
try {
    $result = Invoke-RestMethod `
        -Uri "$apiBase/connect" `
        -Method Post `
        -Body $body `
        -ContentType "application/json" `
        -TimeoutSec 20 `
        -ErrorAction Stop

    [System.Windows.Forms.MessageBox]::Show(
        "Email conectado com sucesso!`n`nConta: $($result.user)`n`n" +
        "Abra o painel Email no Nous (ícone de envelope) para ver sua caixa de entrada.`n`n" +
        "LEMBRETE: O conteúdo dos seus emails é processado apenas pelo modelo de IA local — " +
        "nada sai da sua máquina.",
        "Nous — Email Conectado",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
} catch {
    $errMsg = ""
    try {
        $errBody = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($errBody)
        $errJson = $reader.ReadToEnd() | ConvertFrom-Json
        $errMsg = $errJson.error
    } catch {
        $errMsg = $_.Exception.Message
    }

    $friendly = switch -Wildcard ($errMsg) {
        "*rejeitada*"      { "Credenciais rejeitadas pelo servidor de email.`nVerifique se a senha de app está correta e se o IMAP está habilitado na sua conta." }
        "*inacessível*"    { "Não foi possível alcançar o servidor.`nVerifique sua conexão com a internet." }
        "*Não reconheço*"  { "Provedor de email não reconhecido automaticamente.`nUse conectar-email.ps1 com servidores manuais (contate suporte)." }
        default            { "Erro: $errMsg" }
    }

    [System.Windows.Forms.MessageBox]::Show(
        $friendly,
        "Nous — Falha na conexão",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}
