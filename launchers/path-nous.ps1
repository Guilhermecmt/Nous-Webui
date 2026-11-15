<#
  Nous - poe e tira uma pasta do PATH do usuario (sem admin).
  Dot-source: . launchers\path-nous.ps1
  Le' e grava o valor CRU do registro (REG_EXPAND_SZ): [Environment]::Get/Set...
  devolvem o valor ja' expandido e gravam REG_SZ, o que congelava para sempre as
  entradas com %VARIAVEL% que o usuario ja' tinha no PATH.
  -Sub so' para teste (outra chave em HKCU).
#>

function Get-NousPathBruto([string]$Sub) {
    $k = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($Sub)
    if (-not $k) { return "" }
    try { return [string]$k.GetValue("Path", "", [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames) }
    finally { $k.Close() }
}

function Set-NousPathBruto([string]$Sub, [string]$Valor) {
    $k = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($Sub)
    try { $k.SetValue("Path", $Valor, [Microsoft.Win32.RegistryValueKind]::ExpandString) }
    finally { $k.Close() }
    if ($Sub -eq "Environment") {
        # avisa o Windows (WM_SETTINGCHANGE) para terminais novos ja' verem o PATH novo
        [Environment]::SetEnvironmentVariable("NOUS_PATH_AVISO", "1", "User")
        [Environment]::SetEnvironmentVariable("NOUS_PATH_AVISO", $null, "User")
    }
}

function Test-NousMesmaPasta([string]$a, [string]$b) {
    return ($a.Trim().TrimEnd('\') -ieq $b.Trim().TrimEnd('\'))
}

function Add-NousPath([string]$Dir, [string]$Sub = "Environment") {
    $atual = Get-NousPathBruto $Sub
    $itens = @($atual -split ';' | Where-Object { $_ -ne "" })
    foreach ($i in $itens) { if (Test-NousMesmaPasta $i $Dir) { return } }
    Set-NousPathBruto $Sub ((@($itens) + $Dir.TrimEnd('\')) -join ';')
}

function Remove-NousPath([string]$Dir, [string]$Sub = "Environment") {
    $atual = Get-NousPathBruto $Sub
    $itens = @($atual -split ';' | Where-Object { $_ -ne "" })
    $resto = @($itens | Where-Object { -not (Test-NousMesmaPasta $_ $Dir) })
    if ($resto.Count -ne $itens.Count) { Set-NousPathBruto $Sub ($resto -join ';') }
}
