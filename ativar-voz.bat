@echo off
REM ============================================================
REM  Nous - Ativar Conversa por Voz em PT-BR (clique duplo).
REM  Baixa o Piper TTS e a voz portuguesa e ativa o microfone.
REM ============================================================
cd /d "%~dp0"
powershell.exe -ExecutionPolicy Bypass -File "%~dp0voice\install-voice.ps1"
pause
