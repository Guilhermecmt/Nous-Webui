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

REM O instalador faz tudo - inclusive a analise da maquina - e sai com
REM codigo 1 se algo essencial falhar. Argumentos (uso avancado) passam direto.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\install-nous.ps1" %*
if errorlevel 1 goto erro

echo.
echo ============================================
echo  Pronto! Abrindo o Nous para voce...
echo  (na primeira vez, ele te ajuda a escolher
echo   e baixar o modelo de IA ideal)
echo ============================================
echo.
start "" wscript.exe "%LOCALAPPDATA%\Programs\Nous\launchers\nous-hidden.vbs"
pause
exit /b 0

:erro
echo.
echo ============================================
echo  A instalacao NAO terminou.
echo  Leia a mensagem em vermelho acima, corrija
echo  (quase sempre: a conexao com a internet)
echo  e rode o instalar.bat de novo.
echo ============================================
echo.
pause
exit /b 1
