# Ejecuta la suite automatizada (usa SQLite temporal y un doble de prueba del proveedor IA; no consume APIs).
. "$PSScriptRoot\comun.ps1"
Requiere-Venv
Ejecutar-Python @("-m", "pytest", "-q")
