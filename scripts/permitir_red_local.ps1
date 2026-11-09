# Permite que otras computadoras (Mac o Windows) de la MISMA red Wi-Fi abran el sistema en http://IP-de-este-equipo:8000
# Ejecutar UNA vez en PowerShell «como administrador». Requiere ACCESO_RED_LOCAL=true en backend\.env.
#  1. Marca la red Wi-Fi actual como «Privada» (en una red pública Windows bloquea las conexiones entrantes).
#  2. Quita las reglas que BLOQUEAN a python.exe (creadas al cancelar el aviso del firewall; un bloqueo gana a un permiso).
#  3. Permite el puerto 8000 solo desde la subred local y solo en redes privadas.
# Deshacer:  Remove-NetFirewallRule -DisplayName "Sistema de Cobros (red local)"
$esAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Write-Host "Abra PowerShell como administrador y vuelva a ejecutar este archivo." -ForegroundColor Yellow
    exit 1
}
Get-NetConnectionProfile | Where-Object { $_.InterfaceAlias -like "Wi-Fi*" } | Set-NetConnectionProfile -NetworkCategory Private
Get-NetFirewallApplicationFilter | Where-Object { $_.Program -like "*python*" } | Get-NetFirewallRule |
    Where-Object { $_.Direction -eq "Inbound" -and $_.Action -eq "Block" } | Remove-NetFirewallRule
Remove-NetFirewallRule -DisplayName "Sistema de Cobros (red local)" -ErrorAction SilentlyContinue
New-NetFirewallRule -DisplayName "Sistema de Cobros (red local)" -Direction Inbound -Protocol TCP -LocalPort 8000 `
    -RemoteAddress LocalSubnet -Profile Private -Action Allow | Out-Null
$ip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi*" | Select-Object -First 1).IPAddress
Write-Host "Listo. Desde otra computadora del mismo Wi-Fi abra:  http://$ip`:8000" -ForegroundColor Green
