# Crea un respaldo CIFRADO de la base (requiere RESPALDO_CLAVE y mysqldump; ver docs\RESPALDO.md).
. "$PSScriptRoot\comun.ps1"
Requiere-Venv; Requiere-Env
Ejecutar-Python @("-m", "app.respaldo", "crear")
