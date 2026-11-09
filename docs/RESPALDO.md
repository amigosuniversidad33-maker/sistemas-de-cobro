# Respaldo, restauración y retención

## Preparación (una vez)
1. Genere la clave de respaldos y guárdela en `backend\.env` como `RESPALDO_CLAVE`, **y también fuera del equipo**
   (gestor de contraseñas o papel en lugar seguro). Sin ella los respaldos no se pueden restaurar.
   ```powershell
   backend\.venv\Scripts\python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Configure `MYSQL_BIN_DIR` (carpeta de `mysqldump.exe`) y `DATABASE_URL_MIGRACIONES` (usuario `cobros_migra`).

## Crear respaldo
```powershell
powershell -ExecutionPolicy Bypass -File scripts\respaldo.ps1
```
Resultado: `backend\datos\respaldos\cobros_AAAAMMDD_HHMMSS.sql.enc` (volcado `mysqldump --single-transaction` cifrado con Fernet).
Las credenciales MySQL se pasan en un archivo temporal que se elimina al terminar. Las grabaciones cifradas de
`backend\datos\grabaciones` se respaldan copiando la carpeta (ya están cifradas con `GRABACIONES_CLAVE`).

## Verificar sin restaurar
```powershell
backend\.venv\Scripts\python -m app.respaldo verificar backend\datos\respaldos\ARCHIVO.sql.enc
```
(ejecutar desde la carpeta `backend`). Debe indicar «Descifrado correcto … Contenido válido».

## Restaurar (sobrescribe la base actual)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\detener.ps1
powershell -ExecutionPolicy Bypass -File scripts\restaurar.ps1 backend\datos\respaldos\ARCHIVO.sql.enc
powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1
```
Pide escribir `RESTAURAR`. Si la clave no corresponde, se detiene sin modificar la base.

## Prueba de restauración (obligatoria antes de la demo, M-14)
1. Crear respaldo. 2. Crear un usuario de prueba. 3. Restaurar el respaldo. 4. Comprobar que ese usuario ya no existe y que el resto de datos está intacto.

## Retención
`python -m app.cli purgar` aplica los plazos de `.env` (transcripciones 180 d, grabaciones 90 d, bitácora 365 d, sesiones 30 d).
Elimina datos de forma irreversible: haga un respaldo antes y ejecútelo solo con autorización.
