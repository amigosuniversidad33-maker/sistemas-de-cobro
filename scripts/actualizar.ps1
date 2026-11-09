# Actualizacion: trae cambios del repositorio, reinstala dependencias y aplica migraciones.
. "$PSScriptRoot\comun.ps1"
Requiere-Venv
Write-Host "Recomendado: crear un respaldo antes (scripts\respaldo.ps1)." -ForegroundColor Yellow
if (Test-Path (Join-Path $Raiz ".git")) { Push-Location $Raiz; git pull; Pop-Location }
& $Py -m pip install -r (Join-Path $Back "requirements.txt")
Ejecutar-Python @("-m", "alembic", "upgrade", "head")
Ejecutar-Python @("-m", "app.cli", "semilla")
Write-Host "Actualizacion aplicada. Reinicie con detener.ps1 e iniciar.ps1." -ForegroundColor Green
