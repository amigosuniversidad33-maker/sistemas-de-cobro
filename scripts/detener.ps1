# Detiene la API y el worker iniciados por iniciar.ps1.
# El worker recupera al siguiente arranque los trabajos y canales que hubieran quedado a medias.
. "$PSScriptRoot\comun.ps1"
if (-not (Test-Path $Pids)) { Write-Host "No hay procesos registrados."; exit 0 }
foreach ($id in Get-Content $Pids) {
    if ($id -and (Get-Process -Id $id -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $id -Force
        Write-Host "Proceso $id detenido."
    }
}
Remove-Item $Pids -Force
Write-Host "Sistema detenido. Los datos permanecen en MySQL." -ForegroundColor Green
