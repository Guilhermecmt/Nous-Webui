@echo off
REM ============================================================
REM  Nous - Instalador (clique duplo). Funciona de qualquer pasta.
REM  Sem perguntas tecnicas: o modelo de IA e' escolhido DENTRO
REM  do Nous, num assistente visual, no primeiro uso.
REM ============================================================
title Instalador do Nous
cd /d "%~dp0"

echo ============================================
echo             Instalador do Nous
echo ============================================
echo.
echo Isto instala tudo que o Nous precisa:
echo   - Ollama (motor dos modelos de IA)
echo   - Python + Open WebUI (a interface)
echo   - a identidade Nous (tema, logo, memoria)
echo.
echo Durante a instalacao voce pode escolher um modelo
echo de IA por uma lista numerada (so' digitar o numero),
echo ou apertar Enter e escolher DEPOIS dentro do Nous,
echo com recomendacao automatica e download em 1 clique.
echo.
echo Pode levar varios minutos e baixar alguns GB.
echo Se aparecer um aviso do Windows, escolha "Sim".
echo.
pause

REM Com argumentos (uso avancado) = repassa direto sem analise.
if not "%~1"=="" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install-nous.ps1" %*
    goto fim
)

REM ---- Analisa o hardware (porteiro de capacidade) ----
echo.
echo Analisando sua maquina...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\check-system.ps1"
set CHECK_EXIT=%errorlevel%

REM EXIT 1 = INCAPAZ (pouca RAM ou disco)
if %CHECK_EXIT%==1 (
    echo.
    echo ATENCAO: sua maquina nao atende os requisitos minimos.
    echo Veja os detalhes acima. Instalacao cancelada.
    echo.
    pause
    exit /b 1
)

echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install-nous.ps1"

:fim
echo.
echo ============================================
echo  Pronto! Abrindo o Nous para voce...
echo  (na primeira vez, ele te ajuda a escolher
echo   e baixar o modelo de IA ideal)
echo ============================================
echo.
start "" wscript.exe "%~dp0launchers\nous-hidden.vbs"
pause
