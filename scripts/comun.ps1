# Funciones compartidas por los scripts (no ejecutar directamente).
$ErrorActionPreference = "Stop"
$Raiz = Split-Path -Parent $PSScriptRoot
$Back = Join-Path $Raiz "backend"
$Py = Join-Path $Back ".venv\Scripts\python.exe"
$Datos = Join-Path $Back "datos"
$Pids = Join-Path $Datos "pids.txt"

function Requiere-Venv {
    if (-not (Test-Path $Py)) {
        Write-Host "No existe el entorno virtual. Ejecute primero: scripts\instalar.ps1" -ForegroundColor Red
        exit 1
    }
}
function Requiere-Env {
    if (-not (Test-Path (Join-Path $Back ".env"))) {
        Write-Host "Falta backend\.env. Copie backend\.env.example como backend\.env y complete los valores." -ForegroundColor Red
        exit 1
    }
}
function Ejecutar-Python([string[]]$Argumentos) {
    Push-Location $Back
    try {
        & $Py @Argumentos
        if ($LASTEXITCODE -ne 0) { throw "El comando python $($Argumentos -join ' ') termino con codigo $LASTEXITCODE" }
    } finally { Pop-Location }
}
