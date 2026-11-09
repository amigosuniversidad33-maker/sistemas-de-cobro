# Crea las tablas (migraciones), carga catalogos, crea el PRIMER administrador y, opcionalmente, datos ficticios.
. "$PSScriptRoot\comun.ps1"
Requiere-Venv; Requiere-Env
Write-Host "== Verificando configuracion ==" -ForegroundColor Cyan
Ejecutar-Python @("-m", "app.cli", "verificar")
Write-Host "== Aplicando migraciones (alembic upgrade head) ==" -ForegroundColor Cyan
Ejecutar-Python @("-m", "alembic", "upgrade", "head")
Write-Host "== Cargando catalogos ==" -ForegroundColor Cyan
Ejecutar-Python @("-m", "app.cli", "semilla")
Write-Host "== Primer administrador (la contrasena no se muestra al escribir) ==" -ForegroundColor Cyan
Push-Location $Back
& $Py -m app.cli crear-admin
Pop-Location
$r = Read-Host "Cargar clientes y campanas FICTICIOS de demostracion? (s/n)"
if ($r -eq "s") { Ejecutar-Python @("-m", "app.cli", "demo") }
Write-Host "Base de datos lista. Inicie el sistema con scripts\iniciar.ps1" -ForegroundColor Green
