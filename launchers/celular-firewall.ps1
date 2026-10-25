<#
  Nous - Usar no celular: regra do Firewall do Windows. SEM janela de terminal.

  Uma unica regra de ENTRADA, so' para a porta do portao do celular (TCP), so' no
  perfil de rede PRIVADO e so' para aparelhos da mesma sub-rede (rede de casa).
  Criada quando o usuario liga "Usar no celular"; removida quando desliga e na
  desinstalacao. Criar/remover pede permissao de administrador (o Windows mostra o
  pedido: este script se reabre elevado). Ler o estado nao pede nada.

  -Acao Estado   {"regra":bool,"perfil":"Private|Public|...","admin":bool}
  -Acao Criar    cria a regra (se ja' existe, so' confere)
  -Acao Remover  apaga a regra
  -Simular       NAO muda nada no Windows: escreve em <Dados>\simulado.log o comando
                 que seria executado (usado nos testes). A "regra" simulada vive no
                 arquivo <Dados>\simulado-regra.json.

  A ultima linha da saida e' sempre um JSON de uma linha.
#>
param(
    [ValidateSet("Estado", "Criar", "Remover")][string]$Acao = "Estado",
    [int]$Porta = 8999,
    [string]$Ip = "",              # IP do PC na rede de casa (para descobrir o perfil da rede)
    [string]$Programa = "",        # python.exe que escuta (opcional)
    [string]$Dados = "",           # pasta NousData\celular (log e estado da simulacao)
    [switch]$Simular,
    [string]$PerfilSimulado = ""
)
$ErrorActionPreference = "Stop"
$Nome = "Nous - Usar no celular"

function Test-Admin {
    ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
function Out-Json($o) { Write-Output (ConvertTo-Json -InputObject $o -Compress) }
function Aspas([string]$s) { '"' + $s + '"' }

# --- o que seria executado -----------------------------------------------------
$prog = if ($Programa -and (Test-Path -LiteralPath $Programa)) { $Programa } else { "" }
$cmdCriar = "New-NetFirewallRule -DisplayName '$Nome' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Porta -Profile Private -RemoteAddress LocalSubnet" +
    $(if ($prog) { " -Program '$prog'" } else { "" })
$cmdRemover = "Remove-NetFirewallRule -DisplayName '$Nome'"

# --- simulacao: nada muda no Windows -------------------------------------------
if ($Simular) {
    if (-not $Dados) { $Dados = Join-Path $env:TEMP "nous-celular-sim" }
    New-Item -ItemType Directory -Force -Path $Dados | Out-Null
    $marca = Join-Path $Dados "simulado-regra.json"
    $log = Join-Path $Dados "simulado.log"
    $tem = Test-Path -LiteralPath $marca
    if ($Acao -eq "Criar" -and -not $tem) {
        Add-Content -LiteralPath $log -Value ("{0} [SIMULADO] {1}" -f (Get-Date -Format s), $cmdCriar)
        [IO.File]::WriteAllText($marca, "{}"); $tem = $true
    } elseif ($Acao -eq "Remover" -and $tem) {
        Add-Content -LiteralPath $log -Value ("{0} [SIMULADO] {1}" -f (Get-Date -Format s), $cmdRemover)
        Remove-Item -LiteralPath $marca -Force; $tem = $false
    }
    $perfil = "Private"
    if ($PerfilSimulado) { $perfil = $PerfilSimulado }
    else {
        try {
            if ($Ip) {
                $ifx = (Get-NetIPAddress -IPAddress $Ip -ErrorAction Stop | Select-Object -First 1).InterfaceIndex
                $perfil = [string](Get-NetConnectionProfile -InterfaceIndex $ifx -ErrorAction Stop | Select-Object -First 1).NetworkCategory
            }
        } catch { $perfil = "?" }
    }
    Out-Json @{ regra = $tem; perfil = $perfil; admin = $false; simulado = $true }
    return
}

# --- perfil da rede e regra atual (leitura: sem administrador) ------------------
function Get-Perfil {
    try {
        if ($Ip) {
            $ifx = (Get-NetIPAddress -IPAddress $Ip -ErrorAction Stop | Select-Object -First 1).InterfaceIndex
            return [string](Get-NetConnectionProfile -InterfaceIndex $ifx -ErrorAction Stop | Select-Object -First 1).NetworkCategory
        }
    } catch {}
    return "?"
}
function Test-Regra { [bool](Get-NetFirewallRule -DisplayName $Nome -ErrorAction SilentlyContinue) }

if ($Acao -eq "Estado") {
    Out-Json @{ regra = (Test-Regra); perfil = (Get-Perfil); admin = (Test-Admin) }
    return
}

# --- criar / remover: precisa de administrador -----------------------------------
if (-not (Test-Admin)) {
    # reabre este mesmo script elevado: o Windows mostra o pedido de permissao
    $a = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", (Aspas $PSCommandPath),
           "-Acao", $Acao, "-Porta", $Porta)
    if ($prog) { $a += @("-Programa", (Aspas $prog)) }
    try { Start-Process -FilePath "powershell.exe" -ArgumentList $a -Verb RunAs -Wait -WindowStyle Hidden }
    catch {
        # o usuario recusou o pedido do Windows
        Out-Json @{ regra = (Test-Regra); perfil = (Get-Perfil); admin = $false; negado = $true }
        return
    }
    Out-Json @{ regra = (Test-Regra); perfil = (Get-Perfil); admin = $false }
    return
}

try {
    if ($Acao -eq "Criar") {
        if (-not (Test-Regra)) {
            $p = @{ DisplayName = $Nome; Description = "Deixa o celular abrir o Nous pela rede de casa. Criada e removida pelo proprio Nous."
                    Direction = "Inbound"; Action = "Allow"; Protocol = "TCP"; LocalPort = $Porta
                    Profile = "Private"; RemoteAddress = "LocalSubnet" }
            if ($prog) { $p.Program = $prog }
            New-NetFirewallRule @p | Out-Null
        }
    } else {
        Get-NetFirewallRule -DisplayName $Nome -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    }
} catch {}
Out-Json @{ regra = (Test-Regra); perfil = (Get-Perfil); admin = $true }
