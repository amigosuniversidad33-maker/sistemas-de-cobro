# Instalar y abrir el sistema en una Mac

El sistema es el mismo que en Windows. En la Mac se cambia **WAMP por MAMP** e **INICIAR.bat por INICIAR.command**.
Al terminar se abre igual: **http://localhost/cobros/**, que lleva a **http://127.0.0.1:8000**.

## Qué necesita (una sola vez)

| Programa | Dónde | Nota |
|---|---|---|
| **Python 3.13** | https://www.python.org/downloads/macos/ (instalador *macOS 64-bit universal2*) | El `python3` que trae macOS es 3.9 y **no sirve**. |
| **MAMP** (gratis) | https://www.mamp.info/en/downloads/ | Trae Apache + PHP + MySQL, igual que WAMP. |
| Internet | Solo la primera vez | Para instalar las dependencias de Python (2 a 5 minutos). |

Funciona en Mac con chip Apple (M1 a M4) y con chip Intel.

## Pasos

1. **Copie la carpeta del proyecto a su carpeta personal**, para que quede así: `/Users/SU_USUARIO/sistema-cobros`.
   - En Finder: menú *Ir › Inicio* y arrastre ahí la carpeta `sistema-cobros`.
   - **No la deje en Descargas, Escritorio ni Documentos.** macOS no deja que el servidor web (Apache de MAMP) entre a esas carpetas, y el enlace `localhost/cobros` no podría iniciar el sistema.
   - Si la carpeta viene de una computadora con Windows, **no copie** `backend/.venv`, `backend/.env` ni `backend/datos`. La Mac crea los suyos. El ZIP para Mac ya viene sin ellos.

2. **Configure MAMP para usar `localhost` sin número de puerto.**
   - Abra MAMP › *Preferences* (o *Settings*) › *Ports*.
   - Presione **"Set Web & MySQL ports to 80 & 3306"** y acepte (pide su contraseña de la Mac).
   - Presione **Start**. Las luces de Apache y MySQL deben quedar en verde.
   - Si prefiere dejar los puertos de fábrica (8888 y 8889), también funciona, pero la dirección será **http://localhost:8888/cobros/**.

3. **Permita abrir los archivos de doble clic** (solo la primera vez). Abra la app *Terminal* y pegue:
   ```bash
   chmod +x ~/sistema-cobros/INICIAR.command ~/sistema-cobros/DETENER.command
   ```
   Esto es necesario porque al pasar los archivos por ZIP desde Windows pierden el permiso de ejecución.

4. **Haga doble clic en `INICIAR.command`.**
   - Si la Mac dice que "no se puede abrir porque proviene de un desarrollador no identificado", haga **clic derecho › Abrir › Abrir**. Solo se pide una vez.
   - La primera vez instala todo y crea la base `cobros_ia` en el MySQL de MAMP. MAMP trae el usuario `root` con contraseña `root`, y el sistema la detecta solo.
   - Al final **muestra el usuario y la contraseña del administrador**: anótelos, porque se muestran solo esa vez.
   - También copia la página de acceso a `/Applications/MAMP/htdocs/cobros/`.

5. **Desde ahí, para entrar** abra **http://localhost/cobros/** con MAMP encendido. Si el sistema está apagado, la página lo enciende sola y muestra el progreso.

Para apagarlo: doble clic en **`DETENER.command`**.

## Si algo falla

| Mensaje | Qué hacer |
|---|---|
| «No se encontró Python 3.11 o superior» | Instale Python 3.13 desde python.org (paso de "Qué necesita"). |
| «No se encontró MySQL en 127.0.0.1…» | Abra MAMP y presione **Start**. Espere las luces verdes. |
| «El usuario root de MySQL tiene contraseña» | Abra `INICIAR.command`: le pedirá la contraseña una vez (no se guarda). |
| «No se encontró el proyecto en /Users/…/sistema-cobros» | La carpeta no está en su carpeta personal o tiene otro nombre. Muévala (paso 1) o use `INICIAR.command`. |
| `localhost/cobros` dice "Not Found" | Abra `INICIAR.command` una vez: es el que copia la página a MAMP. Revise también el puerto (80 u 8888). |
| La página se queda en "Iniciando…" | Use `INICIAR.command` y lea el mensaje en la ventana. El detalle queda en `backend/datos/logs/`. |
| «El puerto 8000 está ocupado» | Ejecute `DETENER.command` o reinicie la Mac. |

## Alternativa sin MAMP (Homebrew)

Si ya usa Homebrew, puede instalar MySQL con `brew install mysql` y luego `brew services start mysql`. El sistema detecta MySQL en el puerto 3306. En ese caso `INICIAR.command` funciona igual. El enlace `localhost/cobros` solo existe si además tiene Apache con PHP (`brew install httpd php`); sin eso, entre directo a **http://127.0.0.1:8000**.
