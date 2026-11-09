@echo off
rem Doble clic para instalar (primera vez) e iniciar el sistema en http://127.0.0.1:8000
chcp 65001 >nul
title Sistema Outbound de Cobros con IA
cd /d "%~dp0"

if exist "backend\.venv\Scripts\python.exe" (
    "backend\.venv\Scripts\python.exe" backend\arranque.py
    goto fin
)
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 backend\arranque.py
    goto fin
)
where python >nul 2>nul
if %errorlevel%==0 (
    python backend\arranque.py
    goto fin
)
echo.
echo No se encontro Python. Instale Python 3.13 desde python.org
echo (marque la casilla "Add python.exe to PATH") y vuelva a ejecutar este archivo.
start https://www.python.org/downloads/

:fin
echo.
echo Puede cerrar esta ventana; el sistema sigue funcionando en segundo plano.
echo Para detenerlo ejecute DETENER.bat
pause
