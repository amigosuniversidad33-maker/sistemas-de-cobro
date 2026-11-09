# Deja el sistema listo para abrir http://127.0.0.1:8000 sin encender WAMP ni usar INICIAR.bat.
#  1. El servicio MySQL de WAMP (wampmysqld64) pasa a inicio Automático (arranca con Windows).
#  2. Crea la tarea programada «SistemaCobros»: al iniciar sesión (45 s después, para que MySQL esté listo)
#     arranca la API y el worker en segundo plano, sin ventanas.
# Ejecutar UNA vez en PowerShell «como administrador» (clic derecho en PowerShell > Ejecutar como administrador).
# Deshacer:  Unregister-ScheduledTask -TaskName SistemaCobros -Confirm:$false ; Set-Service wampmysqld64 -StartupType Manual
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Write-Host "Abra PowerShell como administrador y vuelva a ejecutar este archivo." -ForegroundColor Yellow
    exit 1
}
$raiz = Split-Path -Parent $PSScriptRoot

# 1. MySQL de WAMP automático
$servicio = Get-Service -Name "wampmysqld64" -ErrorAction SilentlyContinue
if ($servicio) {
    Set-Service -Name "wampmysqld64" -StartupType Automatic
    if ($servicio.Status -ne "Running") { Start-Service -Name "wampmysqld64" }
    Write-Host "MySQL de WAMP: inicio automático." -ForegroundColor Green
} else {
    Write-Host "No se encontró el servicio wampmysqld64; revise que MySQL arranque con Windows." -ForegroundColor Yellow
}

# 2. Tarea al iniciar sesión (para el usuario que usa la computadora, sin privilegios elevados)
$usuario = (Get-CimInstance Win32_ComputerSystem).UserName
if (-not $usuario) { $usuario = "$env:USERDOMAIN\$env:USERNAME" }
$accion = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$raiz\scripts\inicio_oculto.vbs`"" -WorkingDirectory $raiz
$disparador = New-ScheduledTaskTrigger -AtLogOn -User $usuario
$disparador.Delay = "PT45S"
$ajustes = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "SistemaCobros" -Description "Inicia el Sistema Outbound de Cobros (API y worker) al iniciar sesión" `
    -Action $accion -Trigger $disparador -Settings $ajustes -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName "SistemaCobros"

# 3. Acceso directo en el escritorio
$escritorio = [Environment]::GetFolderPath("Desktop")
Set-Content -Path (Join-Path $escritorio "Sistema de Cobros.url") -Value "[InternetShortcut]`r`nURL=http://127.0.0.1:8000/" -Encoding ascii
Write-Host "Listo. Desde ahora el sistema arranca solo al entrar a Windows. Abra http://127.0.0.1:8000" -ForegroundColor Green
