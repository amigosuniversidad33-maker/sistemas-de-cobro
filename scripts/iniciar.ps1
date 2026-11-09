# Arranque habitual: aplica migraciones pendientes, inicia la API (http://127.0.0.1:8000) y el worker.
. "$PSScriptRoot\comun.ps1"
Requiere-Venv; Requiere-Env
if (Test-Path $Pids) {
    $vivos = Get-Content $Pids | Where-Object { $_ -and (Get-Process -Id $_ -ErrorAction SilentlyContinue) }
    if ($vivos) { Write-Host "El sistema ya parece estar en ejecucion (PID $($vivos -join ', ')). Use scripts\detener.ps1 primero." -ForegroundColor Yellow; exit 0 }
}
New-Item -ItemType Directory -Force -Path (Join-Path $Datos "logs") | Out-Null
Write-Host "== Migraciones ==" -ForegroundColor Cyan
Ejecutar-Python @("-m", "alembic", "upgrade", "head")
$logs = Join-Path $Datos "logs"
Write-Host "== Iniciando API y worker ==" -ForegroundColor Cyan
$api = Start-Process -FilePath $Py -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $Back -RedirectStandardOutput (Join-Path $logs "api.log") -RedirectStandardError (Join-Path $logs "api_errores.log") -PassThru -WindowStyle Hidden
$wrk = Start-Process -FilePath $Py -ArgumentList @("-m", "app.worker") `
    -WorkingDirectory $Back -RedirectStandardOutput (Join-Path $logs "worker.log") -RedirectStandardError (Join-Path $logs "worker_errores.log") -PassThru -WindowStyle Hidden
@($api.Id, $wrk.Id) | Set-Content $Pids
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 700
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8000/api/salud" -TimeoutSec 2; if ($r.StatusCode -eq 200) { $ok = $true; break } } catch { }
}
if ($ok) {
    Write-Host "Sistema en ejecucion: http://127.0.0.1:8000  (API PID $($api.Id), worker PID $($wrk.Id))" -ForegroundColor Green
    Start-Process "http://127.0.0.1:8000"
} else {
    Write-Host "La API no respondio. Revise backend\datos\logs\api_errores.log" -ForegroundColor Red
}
