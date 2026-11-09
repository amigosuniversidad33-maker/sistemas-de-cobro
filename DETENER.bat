@echo off
rem Detiene la API y el worker iniciados por INICIAR.bat o por http://localhost/cobros/
chcp 65001 >nul
cd /d "%~dp0"
if not exist "backend\datos\pids.txt" (
    echo No hay procesos registrados.
    pause
    exit /b 0
)
for /f %%p in (backend\datos\pids.txt) do taskkill /PID %%p /T /F >nul 2>nul
del "backend\datos\pids.txt" >nul 2>nul
echo Sistema detenido. Los datos permanecen en MySQL.
pause
