<#
  Nous WebUI - Parar o servidor (libera a porta e a memoria).
  Encerra TODOS os processos do Nous: servidor (8080), monitor (8990),
  indexadores (8991/8992), memoria (8993), voz (8994), email (8995), agenda (8996), habilidades (8997), Nous Code (8998), o portao do
  celular (8999, "Usar no celular"; a regra do firewall dele sai ao desligar no painel) e o
  motor de imagem que o proprio Nous sobe (ComfyUI, 8188). Antes so' a 8080
  era fechada e os outros processos Python ficavam para tras. O Ollama nao e'
  tocado (outros programas podem usa-lo); "Parar modelos" no painel libera a GPU.
#>
$ErrorActionPreference = "SilentlyContinue"
$venv = Join-Path $env:USERPROFILE "open-webui"

# O python.exe de um venv no Windows e' so' um redirecionador: o processo real
# roda o Python base e so' e' achado pela porta. Por isso: caminho + portas.
$procs = @(Get-Process | Where-Object { $_.Path -and $_.Path -like "$venv\*" })
foreach ($port in 8080, 8990, 8991, 8992, 8993, 8994, 8995, 8996, 8997, 8998, 8999, 8188) {
    $c = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($c) { $procs += @($c.OwningProcess | Select-Object -Unique | ForEach-Object { Get-Process -Id $_ }) }
}
$procs = @($procs | Where-Object { $_ } | Sort-Object Id -Unique)

if ($procs.Count) {
    $procs | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Nous encerrado ($($procs.Count) processo(s))." -ForegroundColor Green
} else {
    Write-Host "O Nous nao estava em execucao." -ForegroundColor Yellow
}
