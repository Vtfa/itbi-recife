@echo off
title ITBI Recife - Painel Interativo de Imoveis
echo Iniciando Painel do ITBI Recife...

py --version >nul 2>&1
if %errorlevel%==0 (
    py "%~dp0iniciar_dashboard.py"
    goto :end
)

python --version >nul 2>&1
if %errorlevel%==0 (
    python "%~dp0iniciar_dashboard.py"
    goto :end
)

if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
    "%LOCALAPPDATA%\Python\bin\python.exe" "%~dp0iniciar_dashboard.py"
    goto :end
)

echo [ERRO] Python nao encontrado no PATH nem em %%LOCALAPPDATA%%\Python\bin\python.exe.

:end
pause
