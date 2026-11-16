<#
  Nous WebUI - Parar o servidor (libera a porta e a memoria).
  Encerra TODOS os processos do Nous: servidor (8080), monitor (8990),
  indexadores (8991/8992), memoria (8993), voz (8994), email (8995), agenda (8996), habilidades (8997), Nous Code (8998), o portao do
  celular (8999, "Usar no celular"; a regra do firewall dele sai ao desligar no painel), o
  Telegram/WhatsApp (8988, e a ponte do WhatsApp em 8987, que e' um node.exe) e o
  motor de imagem que o proprio Nous sobe (ComfyUI, 8188), e o motor de IA
  (nous-motor, 8989) com os llama-server dele. Antes so' a 8080
  era fechada e os outros processos Python ficavam para tras. O Ollama nao e'
  tocado (outros programas podem usa-lo); "Parar modelos" no painel libera a GPU.
  As janelas do Nous (Nous.exe) fecham junto, menos com -ManterJanela (o atualizador
  reinicia o servidor e a janela aberta se recarrega sozinha).
#>
param([switch]$ManterJanela)
$ErrorActionPreference = "SilentlyContinue"
$venv = Join-Path $env:USERPROFILE "open-webui"

# Janelas do Nous: fecha pedindo (guarda tamanho e posicao); a que nao fechar, cai junto.
if (-not $ManterJanela) {
    $exeJanela = Join-Path (Split-Path $PSScriptRoot -Parent) "janela\bin\Nous.exe"
    $janelas = @(Get-Process -Name Nous -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $exeJanela })
    foreach ($j in $janelas) { $null = $j.CloseMainWindow() }
    if ($janelas.Count) { Start-Sleep -Milliseconds 1500 }
    foreach ($j in $janelas) { if (-not $j.HasExited) { Stop-Process -Id $j.Id -Force -ErrorAction SilentlyContinue } }
}

# O python.exe de um venv no Windows e' so' um redirecionador: o processo real
# roda o Python base e so' e' achado pela porta. Por isso: caminho + portas.
$procs = @(Get-Process | Where-Object { $_.Path -and $_.Path -like "$venv\*" })
foreach ($port in 8080, 8987, 8988, 8989, 8990, 8991, 8992, 8993, 8994, 8995, 8996, 8997, 8998, 8999, 8188) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($c) { $procs += @($c.OwningProcess | Select-Object -Unique | ForEach-Object { Get-Process -Id $_ }) }
}
# llama-server do motor: morrem junto com ele (Job do Windows), mas se o motor ja'
# tinha caido sobra a lista de PIDs. So' derruba se o executavel for o do Nous.
$dataDir = if ($env:NOUS_DATA_DIR) { $env:NOUS_DATA_DIR } else { Join-Path $env:USERPROFILE "NousData" }
$pidsLlama = Join-Path $dataDir "motor\llama-pids.json"
$appDir = Split-Path $PSScriptRoot -Parent
if (Test-Path $pidsLlama) {
    try {
        foreach ($id in (Get-Content $pidsLlama -Raw | ConvertFrom-Json)) {
            $p = Get-Process -Id $id -ErrorAction SilentlyContinue
            if ($p -and $p.Path -and $p.Path -like "$appDir\*") { $procs += $p }
        }
    } catch {}
}
$procs = @($procs | Where-Object { $_ } | Sort-Object Id -Unique)

if ($procs.Count) {
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Nous encerrado ($($procs.Count) processo(s))." -ForegroundColor Green
} else {
    Write-Host "O Nous nao estava em execucao." -ForegroundColor Yellow
}
