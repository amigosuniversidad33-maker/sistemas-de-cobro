# Sistema Outbound para Gestión de Cobros por Campaña con IA

Proyecto académico de la Universidad Regional de Guatemala (Prácticas de Administración de Sistemas de Información).
Es una aplicación web que corre en **su computadora con Windows o Mac**, en **http://127.0.0.1:8000**, con:

- **Frontend** HTML, CSS y JavaScript modular (tema azul), servido por el mismo backend.
- **Backend** Python 3.12/3.13 + FastAPI, con un **worker** separado para los trabajos en segundo plano.
- **MySQL 8** local, gestionado con SQLAlchemy y migraciones Alembic.
- **IA**: API de Anthropic (agente conversacional, supervisor QA y supervisor de seguridad) detrás de una interfaz intercambiable.
- **Voz**: Deepgram STT (`nova-3`, español) y TTS (Aura-2 en español).
- **Telefonía**: FreeSWITCH por Event Socket + troncal SIP (piloto de un canal, **deshabilitada hasta tener troncal y número autorizado**).

> Las APIs de Anthropic y Deepgram **necesitan Internet y credenciales propias con saldo**, aunque el sistema corra en localhost.
> La suscripción de Claude Pro (chat) **no** incluye saldo de API. Sin claves, el sistema funciona en todo lo administrativo
> y las conversaciones muestran un mensaje de contingencia (no se inventan respuestas).
>
> Una conversación de voz en el navegador **no** es una llamada telefónica. La llamada real requiere FreeSWITCH + SIP.

---

## Arranque de un clic (WAMP + MySQL ya instalados)

1. Instale **Python 3.13** desde python.org (marque **Add python.exe to PATH**). Es lo único extra que necesita.
2. Descomprima el ZIP en **`C:\sistema-cobros`**.
3. Encienda WAMP (ícono en **verde**).
4. Haga **doble clic en `INICIAR.bat`**. La primera vez (2 a 5 minutos, con Internet) instala todo, crea la base `cobros_ia`
   en el MySQL de WAMP con usuarios y contraseñas aleatorias, carga datos ficticios, **muestra el usuario y la contraseña del
   administrador una sola vez** y abre el navegador.
5. Desde entonces, abra el enlace **http://localhost/cobros/**: si el sistema está apagado lo inicia solo y lo lleva a
   **http://127.0.0.1:8000**. Para apagarlo: doble clic en `DETENER.bat`.

Si el usuario `root` de MySQL tiene contraseña, `INICIAR.bat` la pedirá una vez (no se guarda).

### En una Mac

Es igual, pero con **MAMP** en lugar de WAMP y **`INICIAR.command` / `DETENER.command`** en lugar de los `.bat`.
La carpeta debe quedar en `/Users/SU_USUARIO/sistema-cobros` (no en Descargas, Escritorio ni Documentos) y MAMP con los
puertos **80 y 3306** para usar **http://localhost/cobros/**. Pasos completos: **`docs/MAC.md`**.

**Sin claves de pago también funciona:** sin `ANTHROPIC_API_KEY` el sistema usa un *agente local de reglas* (sigue el guion y las mismas validaciones; no es IA real) y sin `DEEPGRAM_API_KEY` usa la *voz del navegador* (Chrome o Edge). Ambos se indican en pantalla. Con las claves en `backend\.env` se usan Anthropic y Deepgram reales.

**Llamada real a su celular:** con una cuenta de prueba de Twilio y ngrok el agente llama a un número autorizado y conversa por teléfono. Guía: `docs/TWILIO.md`.
Los pasos manuales de abajo quedan como alternativa y referencia.

## 1. Requisitos de su computadora

| Herramienta | Versión | Para qué |
|---|---|---|
| Windows 10/11 64 bits | 8 GB RAM recomendados, 3 GB libres | |
| Python | 3.12 o 3.13 (python.org, marque **Add python.exe to PATH**) | Backend |
| MySQL Community Server | 8.0 u 8.4 (incluye `mysql.exe` y `mysqldump.exe`) | Base de datos |
| Navegador | Chrome o Edge actualizados | Interfaz y micrófono |
| Git (opcional) | Cualquiera reciente | Control de versiones |
| Visual Studio Code (opcional) | | Editar archivos |

No se necesitan Docker ni WSL2 para el sistema. Solo FreeSWITCH podría requerirlos (ver `docs/FREESWITCH.md`).

## 2. Instalación inicial (una vez)

Todos los comandos se escriben en **PowerShell**, dentro de la carpeta del proyecto (la que contiene este README).

1. **Instalar dependencias de Python**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1
   ```
   Debe terminar con «Instalación terminada». Crea `backend\.venv` y `backend\.env`.

2. **Crear la base de datos y los usuarios MySQL** (privilegios mínimos)
   - Abra `scripts\mysql_crear_bd.sql`, cambie las dos contraseñas de ejemplo y ejecútelo como root
     (MySQL Workbench → File → Open SQL Script → Execute, o en PowerShell):
   ```powershell
   & "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -u root -p -e "source scripts/mysql_crear_bd.sql"
   ```
   Resultado esperado: sin errores. Se crean `cobros_ia`, `cobros_app` (solo datos) y `cobros_migra` (migraciones/respaldos).

3. **Configurar `backend\.env`** (bloc de notas o VS Code). Como mínimo:
   - `DATABASE_URL` y `DATABASE_URL_MIGRACIONES` con las contraseñas que eligió.
     Si la contraseña tiene símbolos (`@ : / ? # %`), escríbalos codificados (p. ej. `@` → `%40`).
   - `MYSQL_BIN_DIR` con la carpeta `bin` de MySQL.
   - Opcional ahora: `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`, `GRABACIONES_CLAVE`, `RESPALDO_CLAVE`
     (las dos últimas se generan con:
     `backend\.venv\Scripts\python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
   - **Nunca** comparta este archivo ni lo suba a Git (ya está en `.gitignore`).

4. **Crear tablas, catálogos y el primer administrador**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\inicializar_bd.ps1
   ```
   Pedirá usuario, nombre, correo y contraseña del administrador (la contraseña no se ve al escribir; mínimo 10
   caracteres y 3 tipos). Responda `s` para cargar clientes **ficticios** de demostración.

## 3. Arranque habitual

```powershell
powershell -ExecutionPolicy Bypass -File scripts\iniciar.ps1
```
Abre el navegador en **http://127.0.0.1:8000**. Inicie sesión con el administrador creado.
Se ejecutan dos procesos: la API (uvicorn) y el worker (cola de trabajos). Los registros quedan en `backend\datos\logs`.

## 4. Detención

```powershell
powershell -ExecutionPolicy Bypass -File scripts\detener.ps1
```
Los datos permanecen en MySQL. Al volver a iniciar, el worker recupera trabajos y canales que hubieran quedado a medias.

## 5. Actualización

```powershell
powershell -ExecutionPolicy Bypass -File scripts\respaldo.ps1     # recomendado antes
powershell -ExecutionPolicy Bypass -File scripts\actualizar.ps1
```

## 6. Respaldo y restauración

```powershell
powershell -ExecutionPolicy Bypass -File scripts\respaldo.ps1
powershell -ExecutionPolicy Bypass -File scripts\detener.ps1
powershell -ExecutionPolicy Bypass -File scripts\restaurar.ps1 backend\datos\respaldos\cobros_AAAAMMDD_HHMMSS.sql.enc
```
Los respaldos se cifran con `RESPALDO_CLAVE` (Fernet). Detalle y prueba de restauración: `docs/RESPALDO.md`.

## 7. Pruebas automatizadas

```powershell
powershell -ExecutionPolicy Bypass -File scripts\pruebas.ps1
```
Usan SQLite temporal y un doble de prueba del proveedor IA (no consumen APIs). Las integraciones reales se verifican con `docs/PRUEBAS.md`.

## 8. Solución de errores frecuentes

| Síntoma | Causa probable | Solución |
|---|---|---|
| «No se puede cargar el archivo … porque la ejecución de scripts está deshabilitada» | Política de PowerShell | Use `powershell -ExecutionPolicy Bypass -File …` como en este README |
| `py` no se reconoce | Python sin lanzador/PATH | Reinstale Python marcando *Add to PATH* y *py launcher* |
| `Access denied for user 'cobros_app'` | Contraseña o usuario distinto en `.env` | Revise `DATABASE_URL`; codifique símbolos especiales |
| `Can't connect to MySQL server on '127.0.0.1'` | Servicio MySQL detenido | Servicios de Windows → MySQL84 → Iniciar |
| `CREATE command denied` al migrar | Migración con el usuario de la app | Configure `DATABASE_URL_MIGRACIONES` con `cobros_migra` |
| Puerto 8000 ocupado | Otra instancia | `scripts\detener.ps1` o `netstat -ano | findstr :8000` |
| La conversación responde «inconveniente técnico» | Falta `ANTHROPIC_API_KEY`, sin saldo o sin Internet | Módulo **Sistema** muestra el estado; revise el consumo con error |
| El micrófono no funciona | Permiso denegado o URL no segura | Use `http://127.0.0.1:8000` o `http://localhost:8000` y permita el micrófono en el candado |
| `mysqldump` no encontrado | `MYSQL_BIN_DIR` vacío | Configure la carpeta `bin` de MySQL en `.env` |
| La telefonía aparece «BLOQUEADA» | Falta FreeSWITCH, troncal o número autorizado | Es el estado correcto hasta completar `docs/FREESWITCH.md` |

## 9. Documentación

| Archivo | Contenido |
|---|---|
| `docs/MANUAL_USUARIO.md` | Uso de los 13 módulos y la sección de clientes |
| `docs/MANUAL_TECNICO.md` | Arquitectura, modelo de datos, seguridad, amenazas, retención |
| `docs/MATRIZ_REQUISITOS.md` | Requisito, fuente y página, módulo, prioridad, fase, aceptación, prueba y estado |
| `docs/PRUEBAS.md` | Pruebas ejecutadas y pruebas manuales pendientes |
| `docs/FREESWITCH.md` | Instalación y configuración de la telefonía piloto |
| `docs/RESPALDO.md` | Respaldo, restauración y retención |
| `docs/GUION_DEMO.md` | Guion de demostración de 10 minutos |
| `docs/esquema_mysql.sql` | DDL generado desde la migración 0001 |
| `ESTADO_PROYECTO.md`, `DECISIONES.md`, `CLAUDE.md` | Continuidad del proyecto |

## 10. Control de versiones

- **Commit**: registrar cambios localmente (`git add . ; git commit -m "mensaje"`).
- **Push**: enviarlos a GitHub (`git push`).
- **Ejecución local**: iniciar el sistema en su equipo (`scripts\iniciar.ps1`).
- **Despliegue**: instalarlo en un servidor de servicio. **No es necesario** para la entrega en localhost.
