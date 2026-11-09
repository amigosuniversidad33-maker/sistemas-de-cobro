# Restaura un respaldo cifrado. SOBRESCRIBE la base actual. Uso:
#   powershell -ExecutionPolicy Bypass -File scripts\restaurar.ps1 backend\datos\respaldos\cobros_AAAAMMDD_HHMMSS.sql.enc
param([Parameter(Mandatory = $true)][string]$Archivo)
. "$PSScriptRoot\comun.ps1"
Requiere-Venv; Requiere-Env
$ruta = (Resolve-Path $Archivo).Path
Write-Host "Detenga el sistema antes de restaurar (scripts\detener.ps1)." -ForegroundColor Yellow
Ejecutar-Python @("-m", "app.respaldo", "verificar", $ruta)
Push-Location $Back
& $Py -m app.respaldo restaurar $ruta
Pop-Location
