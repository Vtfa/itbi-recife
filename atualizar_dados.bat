@echo off
title ITBI Recife - Atualizacao Automatica de Dados
echo Iniciando atualizacao dos dados do ITBI junto a Prefeitura do Recife...

py --version >nul 2>&1
if %errorlevel%==0 (
    py "%~dp0scripts\atualizar_dados.py" %*
    goto :end
)

python --version >nul 2>&1
if %errorlevel%==0 (
    python "%~dp0scripts\atualizar_dados.py" %*
    goto :end
)

if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
    "%LOCALAPPDATA%\Python\bin\python.exe" "%~dp0scripts\atualizar_dados.py" %*
    goto :end
)

echo [ERRO] Python nao encontrado no PATH nem em %%LOCALAPPDATA%%\Python\bin\python.exe.

:end
pause
