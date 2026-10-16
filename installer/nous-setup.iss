; ============================================================
;  Nous - Instalador (Inno Setup)
;  Gera Nous-Setup.exe: instalador online pequeno que copia o app para
;  %LOCALAPPDATA%\Programs\Nous e roda o install-nous.ps1, que baixa e
;  configura o resto (Ollama, Python, Open WebUI) na maquina do usuario.
;  Compilar:  ISCC.exe nous-setup.iss
; ============================================================

#define MyAppName "Nous"
#define MyAppVersion "2.7.0"
#define MyAppPublisher "Nous"
#define MyAppURL "https://github.com/Guilhermecmt/Nous-Webui"

[Setup]
AppId={{8E5F2B41-9C3A-4D7E-AB12-A1B2C3D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
; Mesmo lugar usado pelo install-nous.ps1 (assim ele nao copia de novo).
DefaultDirName={localappdata}\Programs\Nous
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Nous-Setup
SetupIconFile=..\branding\assets\nous.ico
UninstallDisplayIcon={app}\branding\assets\nous.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Area de Trabalho"; GroupDescription: "Atalhos:"

[Files]
; O repositorio inteiro, menos o que e' de desenvolvimento ou gerado.
Source: "..\*"; DestDir: "{app}"; \
    Excludes: ".git\*,.github\*,dist\*,bkp\*.zip,mockups\*,docs\screenshots\*,__pycache__\*,*.pyc,*.log,*.exe,*.sqlite,.webui_secret_key,branding\assets\marble*.png"; \
    Flags: recursesubdirs ignoreversion

[Icons]
; wscript + .vbs: abre sem janela de console (sem ps2exe, que quebrava o
; $PSScriptRoot e impedia os servicos auxiliares de subir).
Name: "{userprograms}\Nous"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launchers\nous-hidden.vbs"""; WorkingDir: "{app}\launchers"; IconFilename: "{app}\branding\assets\nous.ico"
Name: "{userprograms}\Parar Nous"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launchers\parar-nous.vbs"""; WorkingDir: "{app}\launchers"; IconFilename: "{app}\branding\assets\nous.ico"
Name: "{userdesktop}\Nous"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\launchers\nous-hidden.vbs"""; WorkingDir: "{app}\launchers"; IconFilename: "{app}\branding\assets\nous.ico"; Tasks: desktopicon

[Run]
; Configura o backend (Ollama, Python, Open WebUI, identidade). Janela visivel
; de proposito para o usuario acompanhar o download (varios GB na 1a vez).
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\installer\install-nous.ps1"" -NoUninstallEntry"; \
    StatusMsg: "Configurando o Nous: instalando Ollama, Python e o Open WebUI (pode levar varios minutos)..."; \
    Flags: waituntilterminated
; Abre o Nous ao final (opcional)
Filename: "{sys}\wscript.exe"; Parameters: """{app}\launchers\nous-hidden.vbs"""; Description: "Abrir o Nous agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remocao segura: para os processos e apaga o ambiente Python. Preserva as
; conversas (NousData), o Ollama e o Python.
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File ""{app}\installer\uninstall-nous.ps1"" -KeepAppFolder"; \
    Flags: runhidden waituntilterminated; RunOnceId: "NousSafeUninstall"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\launchers"
Type: filesandordirs; Name: "{app}\installer"
