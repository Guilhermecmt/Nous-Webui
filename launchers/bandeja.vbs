' Nous - icone da bandeja do sistema, SEM janela de console (start-nous.ps1 e o atalho "Nous Bandeja").
Dim sh, fso, dir
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & dir & "\bandeja.ps1""", 0, False
