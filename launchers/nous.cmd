@echo off
rem Nous no terminal: abre o Nous Code (agente de programacao) na pasta onde voce esta.
rem   nous                 conversa interativa
rem   nous -p "pedido"     um pedido so', a resposta vai para a saida padrao
rem   nous --ajuda         todas as opcoes
rem Usa o Node do computador (22.18 ou mais novo) ou o portatil que o instalador
rem deixa em <app>\runtime\node (mesma ordem de launchers\node-nous.ps1).
setlocal EnableExtensions
set "NOUS_RAIZ=%~dp0.."
set "NOUS_CLI=%NOUS_RAIZ%\code\cli.ts"
set "NOUS_NODE="

for %%N in (node.exe) do if not defined NOUS_NODE if not "%%~$PATH:N"=="" call :testar "%%~$PATH:N"
if not defined NOUS_NODE if defined ProgramFiles call :testar "%ProgramFiles%\nodejs\node.exe"
if not defined NOUS_NODE call :testar "%NOUS_RAIZ%\runtime\node\node.exe"

if not defined NOUS_NODE (
    echo nous: o Nous Code precisa do Node.js 22.18 ou mais novo. 1>&2
    echo Rode o instalar.bat de novo, com internet ^(ele baixa o Node sozinho^), 1>&2
    echo ou instale com:  winget install OpenJS.NodeJS.LTS 1>&2
    endlocal & exit /b 1
)
if not exist "%NOUS_CLI%" (
    echo nous: nao achei %NOUS_CLI% 1>&2
    endlocal & exit /b 1
)

"%NOUS_NODE%" --disable-warning=ExperimentalWarning "%NOUS_CLI%" %*
endlocal & exit /b %ERRORLEVEL%

:testar
if not exist "%~1" goto :eof
"%~1" -e "var v=process.versions.node.split('.');process.exit(v[0]>22||(v[0]==22&&v[1]>=18)?0:1)" >nul 2>nul
if not errorlevel 1 set "NOUS_NODE=%~1"
goto :eof
