# Instalacion inicial (una sola vez). Ejecutar en PowerShell desde la carpeta del proyecto:
#   powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
. "$PSScriptRoot\comun.ps1"

Write-Host "== Verificando Python ==" -ForegroundColor Cyan
$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if (-not $pyLauncher) { Write-Host "No se encontro el lanzador 'py'. Instale Python 3.12 o 3.13 desde python.org (marque 'Add to PATH')." -ForegroundColor Red; exit 1 }
$version = ""
foreach ($v in @("3.13", "3.12")) {
    & py "-$v" --version 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $version = $v; break }
}
if (-not $version) { Write-Host "Se requiere Python 3.12 o 3.13." -ForegroundColor Red; exit 1 }
Write-Host "Python $version encontrado."

if (-not (Test-Path $Py)) {
    Write-Host "== Creando entorno virtual backend\.venv ==" -ForegroundColor Cyan
    & py "-$version" -m venv (Join-Path $Back ".venv")
}
Write-Host "== Instalando dependencias (versiones fijadas) ==" -ForegroundColor Cyan
& $Py -m pip install --upgrade pip
& $Py -m pip install -r (Join-Path $Back "requirements.txt")
if ($LASTEXITCODE -ne 0) { Write-Host "Fallo la instalacion de dependencias." -ForegroundColor Red; exit 1 }

$envFile = Join-Path $Back ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Back ".env.example") $envFile
    Write-Host "Se creo backend\.env a partir de .env.example. EDITELO antes de continuar." -ForegroundColor Yellow
}
New-Item -ItemType Directory -Force -Path (Join-Path $Datos "logs"), (Join-Path $Datos "respaldos"), (Join-Path $Datos "grabaciones") | Out-Null

Write-Host ""
Write-Host "Instalacion terminada. Siguientes pasos:" -ForegroundColor Green
Write-Host " 1. Cree la base y los usuarios MySQL con scripts\mysql_crear_bd.sql (ver README)."
Write-Host " 2. Edite backend\.env (DATABASE_URL, claves de API si las tiene)."
Write-Host " 3. Ejecute: powershell -ExecutionPolicy Bypass -File scripts\inicializar_bd.ps1"
