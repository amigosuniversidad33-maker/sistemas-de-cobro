"""Arranque automático del sistema en localhost (Windows + WAMP, o Mac + MAMP/Homebrew).

Lo ejecutan INICIAR.bat (Windows) o INICIAR.command (Mac) con doble clic, y la página http://localhost/cobros/. Hace, solo lo que falte:
  1. Crea el entorno virtual e instala dependencias (primera vez; requiere Internet).
  2. Detecta el MySQL de WAMP, crea la base `cobros_ia` y dos usuarios con contraseñas aleatorias, y escribe backend/.env.
  3. Aplica migraciones, carga catálogos y datos ficticios, y crea el administrador con una contraseña aleatoria.
  4. Inicia la API (http://127.0.0.1:8000) y el worker en segundo plano, y abre el navegador.
  5. Instala el acceso http://localhost/cobros/ en la carpeta www de WAMP.

El progreso se escribe en backend/datos/arranque.json (lo lee la página de WAMP).
"""
import json
import os
import secrets
import shutil
import string
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import quote

BACK = Path(__file__).resolve().parent
RAIZ = BACK.parent
DATOS = BACK / "datos"
LOGS = DATOS / "logs"
ESTADO = DATOS / "arranque.json"
BLOQUEO = DATOS / "arranque.lock"
PRIMER_ACCESO = DATOS / "primer_acceso.txt"
PIDS = DATOS / "pids.txt"
ENV = BACK / ".env"
WIN = os.name == "nt"
MAC = sys.platform == "darwin"
VENV_PY = BACK / ".venv" / ("Scripts/python.exe" if WIN else "bin/python")
URL = "http://127.0.0.1:8000"
FONDO = "--fondo" in sys.argv  # lanzado desde la página de WAMP (sin ventana)
if WIN and not FONDO:
    os.system("")  # habilita colores en la consola de Windows


def estado(etapa: str, mensaje: str, nivel: str = "progreso") -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    datos = {"etapa": etapa, "mensaje": mensaje, "nivel": nivel, "hora": time.strftime("%H:%M:%S"), "pid": os.getpid()}
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ESTADO)
    if not FONDO:
        color = {"error": "\033[91m", "listo": "\033[92m"}.get(nivel, "\033[96m")
        print(f"{color}[{datos['hora']}] {mensaje}\033[0m", flush=True)


def fallar(mensaje: str) -> None:
    estado("error", mensaje, "error")
    BLOQUEO.unlink(missing_ok=True)
    sys.exit(1)


def api_activa() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/salud", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def puerto_ocupado() -> bool:
    import socket

    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", 8000)) == 0


def ejecutar(args: list[str], log: str, mensaje_error: str, entrada: str | None = None) -> str:
    LOGS.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(args, cwd=BACK, capture_output=True, text=True, input=entrada,
                       creationflags=0x08000000 if WIN else 0)  # CREATE_NO_WINDOW
    with open(LOGS / log, "a", encoding="utf-8") as f:
        f.write(f"\n$ {' '.join(args)}\n{r.stdout}\n{r.stderr}\n")
    if r.returncode != 0:
        ultimo = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["sin detalle"]
        fallar(f"{mensaje_error}: {ultimo[0][:300]} (detalle en backend/datos/logs/{log})")
    return r.stdout


# ------------------------------------------------------------------ 1. entorno virtual
def preparar_entorno() -> None:
    if sys.version_info < (3, 11):
        fallar(f"Se requiere Python 3.11 o superior (encontrado {sys.version.split()[0]}). Instale Python 3.13 desde python.org.")
    if not VENV_PY.exists():
        estado("entorno", "Creando entorno de Python (solo la primera vez)...")
        ejecutar([sys.executable, "-m", "venv", str(BACK / ".venv")], "instalacion.log", "No se pudo crear el entorno virtual")
    marca = BACK / ".venv" / "requisitos.ok"
    req = BACK / "requirements.txt"
    if not marca.exists() or marca.read_text() != str(req.stat().st_mtime):
        estado("dependencias", "Instalando dependencias (2 a 5 minutos la primera vez, requiere Internet)...")
        ejecutar([str(VENV_PY), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(req)],
                 "instalacion.log", "Falló la instalación de dependencias")
        marca.write_text(str(req.stat().st_mtime))


# ------------------------------------------------------------------ 2. MySQL de WAMP y .env
def buscar_mysql_bin() -> str:
    for base in (Path("C:/wamp64/bin/mysql"), Path("C:/wamp/bin/mysql")):
        if base.exists():
            carpetas = sorted(base.glob("mysql*"), reverse=True)
            for c in carpetas:
                if (c / "bin" / "mysqldump.exe").exists():
                    return str(c / "bin")
    for base in (Path("C:/Program Files/MySQL"),):
        if base.exists():
            for c in sorted(base.glob("MySQL Server*"), reverse=True):
                if (c / "bin" / "mysqldump.exe").exists():
                    return str(c / "bin")
    if not WIN:  # Mac: MAMP, Homebrew o instalador oficial de MySQL
        candidatos = [Path("/Applications/MAMP/Library/bin"), Path("/opt/homebrew/bin"), Path("/usr/local/bin"),
                      Path("/usr/local/mysql/bin"), *sorted(Path("/Applications/MAMP/Library/bin").glob("mysql*/bin"), reverse=True)]
        for c in candidatos:
            if (c / "mysqldump").exists():
                return str(c)
        hallado = shutil.which("mysqldump")
        if hallado:
            return str(Path(hallado).parent)
    return ""


def detectar_mysql(clave_root: str):
    import pymysql

    candidatos = []
    # 3306/3307/3308: WAMP, MySQL oficial y Homebrew. 8889: MAMP en Mac (usuario root, contraseña "root").
    claves = [clave_root] if clave_root else ["", "root"]
    for puerto in (3306, 3308, 3307, 8889):
        con = None
        negado = False
        for clave in claves:
            try:
                con = pymysql.connect(host="127.0.0.1", port=puerto, user="root", password=clave, connect_timeout=3)
                break
            except pymysql.err.OperationalError as e:
                if e.args and e.args[0] == 1045:  # acceso denegado: el servidor existe pero la clave no coincide
                    negado = True
        if con is None:
            if negado:
                candidatos.append((puerto, None, "clave"))
            continue
        with con.cursor() as c:
            c.execute("SELECT VERSION()")
            version = c.fetchone()[0]
        candidatos.append((puerto, con, version))
    # Preferir MySQL sobre MariaDB
    validos = [x for x in candidatos if x[1] is not None]
    validos.sort(key=lambda x: "mariadb" in x[2].lower())
    if validos:
        for _, con, _ in validos[1:]:
            con.close()
        return validos[0]
    if any(x[2] == "clave" for x in candidatos):
        return None, None, "clave"
    return None, None, None


def actualizar_env_existente() -> None:
    """Agrega variables nuevas de .env.example a un .env ya creado (sin tocar los valores existentes)."""
    if not ENV.exists():
        return
    actual = ENV.read_text(encoding="utf-8")
    actual = actual.replace("NOMBRE_EMPRESA=Financiera Demo (ficticia)", "NOMBRE_EMPRESA=Financiera Progreso")
    plantilla = [l for l in (BACK / ".env.example").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")]
    valores_plantilla = {l.split("=", 1)[0].strip(): l.split("=", 1)[1].strip() for l in plantilla}
    # Completa las variables que están VACÍAS en .env pero tienen valor en la plantilla (p. ej. claves de Deepgram/Twilio).
    lineas = []
    for l in actual.splitlines():
        clave, igual, valor = l.partition("=")
        clave = clave.strip()
        if igual and not l.startswith("#") and not valor.strip() and valores_plantilla.get(clave):
            l = f"{clave}={valores_plantilla[clave]}"
        lineas.append(l)
    actual = "\n".join(lineas) + "\n"
    claves = {l.split("=", 1)[0].strip() for l in actual.splitlines() if "=" in l and not l.startswith("#")}
    nuevas = [l for l in plantilla if l.split("=", 1)[0].strip() not in claves]
    if nuevas:
        actual = actual.rstrip("\n") + "\n\n# Variables agregadas por la actualización\n" + "\n".join(nuevas) + "\n"
    ENV.write_text(actual, encoding="utf-8")


def configurar_mysql() -> None:
    if ENV.exists():
        actualizar_env_existente()
        return
    estado("mysql", "Buscando MySQL (WAMP en Windows, MAMP o Homebrew en Mac)...")
    clave_root = os.environ.get("COBROS_MYSQL_ROOT", "")
    puerto, con, version = detectar_mysql(clave_root)
    if version == "clave":
        if FONDO:
            fallar("El usuario root de MySQL tiene contraseña. Ejecute INICIAR.bat (Windows) o INICIAR.command (Mac) una vez con doble clic para escribirla.")
        import getpass

        clave_root = getpass.getpass("El usuario root de MySQL tiene contraseña. Escríbala (no se guarda): ")
        puerto, con, version = detectar_mysql(clave_root)
    if con is None:
        fallar("No se encontró MySQL en 127.0.0.1 (puertos 3306/3307/3308/8889). Inicie WAMP (Windows) o MAMP (Mac) y espere a que MySQL esté encendido.")
    estado("mysql", f"MySQL encontrado en el puerto {puerto} ({version}). Creando base de datos y usuarios...")
    clave_app = secrets.token_urlsafe(18)
    clave_migra = secrets.token_urlsafe(18)
    with con.cursor() as c:
        c.execute("CREATE DATABASE IF NOT EXISTS cobros_ia CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        for usuario, clave in (("cobros_app", clave_app), ("cobros_migra", clave_migra)):
            c.execute(f"CREATE USER IF NOT EXISTS '{usuario}'@'localhost' IDENTIFIED BY %s", (clave,))
            c.execute(f"ALTER USER '{usuario}'@'localhost' IDENTIFIED BY %s", (clave,))
            c.execute(f"CREATE USER IF NOT EXISTS '{usuario}'@'127.0.0.1' IDENTIFIED BY %s", (clave,))
            c.execute(f"ALTER USER '{usuario}'@'127.0.0.1' IDENTIFIED BY %s", (clave,))
        for host in ("localhost", "127.0.0.1"):
            c.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON cobros_ia.* TO 'cobros_app'@'{host}'")
            c.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES, LOCK TABLES, "
                      f"SHOW VIEW, TRIGGER ON cobros_ia.* TO 'cobros_migra'@'{host}'")
        c.execute("FLUSH PRIVILEGES")
    con.close()
    from cryptography.fernet import Fernet

    plantilla = (BACK / ".env.example").read_text(encoding="utf-8")
    valores = {
        "DATABASE_URL": f"mysql+pymysql://cobros_app:{quote(clave_app)}@127.0.0.1:{puerto}/cobros_ia?charset=utf8mb4",
        "DATABASE_URL_MIGRACIONES": f"mysql+pymysql://cobros_migra:{quote(clave_migra)}@127.0.0.1:{puerto}/cobros_ia?charset=utf8mb4",
        "MYSQL_BIN_DIR": buscar_mysql_bin(),
        "GRABACIONES_CLAVE": Fernet.generate_key().decode(),
        "RESPALDO_CLAVE": Fernet.generate_key().decode(),
    }
    lineas = []
    for linea in plantilla.splitlines():
        clave = linea.split("=", 1)[0].strip()
        if not linea.startswith("#") and "=" in linea and clave in valores:
            linea = f"{clave}={valores[clave]}"
        lineas.append(linea)
    ENV.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    estado("mysql", "Configuración guardada en backend/.env (contraseñas aleatorias; no comparta ese archivo).")


# ------------------------------------------------------------------ 3. base de datos
def preparar_base() -> None:
    estado("migraciones", "Creando/actualizando las tablas (migraciones)...")
    ejecutar([str(VENV_PY), "-m", "alembic", "upgrade", "head"], "arranque.log", "Falló la migración de la base de datos")
    ejecutar([str(VENV_PY), "-m", "app.cli", "semilla"], "arranque.log", "No se pudieron cargar los catálogos")
    salida = ejecutar([str(VENV_PY), "-m", "app.cli", "crear-admin", "--generar", "--usuario", "admin", "--nombre",
                       "Administrador", "--apellido", "Sistema", "--correo", "admin@cobros.local"],
                      "arranque.log", "No se pudo crear el administrador")
    if "PASSWORD=" in salida:
        estado("demo", "Cargando clientes y campañas FICTICIOS de demostración...")
        ejecutar([str(VENV_PY), "-m", "app.cli", "demo"], "arranque.log", "No se pudieron cargar los datos de demostración")
        datos = dict(l.split("=", 1) for l in salida.strip().splitlines() if "=" in l)
        PRIMER_ACCESO.write_text(f"Usuario: {datos['USUARIO']}\nContraseña: {datos['PASSWORD']}\n", encoding="utf-8")
        if not FONDO:
            print("\n" + "=" * 60)
            print("  PRIMER ACCESO (anótelo; se muestra solo esta vez)")
            print(f"  Usuario:    {datos['USUARIO']}")
            print(f"  Contraseña: {datos['PASSWORD']}")
            print("=" * 60 + "\n", flush=True)
            PRIMER_ACCESO.unlink(missing_ok=True)


# ------------------------------------------------------------------ 4. iniciar procesos
def iniciar_procesos() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    flags = 0
    if WIN:
        flags = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    pids = []
    # ACCESO_RED_LOCAL=true en .env: escucha también en la red local (el sistema solo acepta IPs privadas, ver main.py)
    red_local = ENV.exists() and any(l.strip().lower() == "acceso_red_local=true"
                                     for l in ENV.read_text(encoding="utf-8").splitlines())
    host = "0.0.0.0" if red_local else "127.0.0.1"
    for nombre, args in (("api", [str(VENV_PY), "-m", "uvicorn", "app.main:app", "--host", host, "--port", "8000"]),
                         ("worker", [str(VENV_PY), "-m", "app.worker"])):
        salida = open(LOGS / f"{nombre}.log", "a", encoding="utf-8")
        try:
            # CREATE_BREAKAWAY_FROM_JOB: el Programador de tareas (y otras herramientas) agrupan los procesos en un
            # «job» que se cierra al terminar este arrancador; sin esto la API y el worker se apagaban a los segundos.
            p = subprocess.Popen(args, cwd=BACK, stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 creationflags=flags | (0x01000000 if WIN else 0), start_new_session=not WIN,
                                 close_fds=True)
        except OSError:  # el job no permite salir de él: se inicia igual que antes
            p = subprocess.Popen(args, cwd=BACK, stdout=salida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 creationflags=flags, start_new_session=not WIN, close_fds=True)
        pids.append(str(p.pid))
    PIDS.write_text("\n".join(pids))
    for _ in range(60):
        if api_activa():
            return
        time.sleep(0.5)
    fallar("La API no respondió. Revise backend/datos/logs/api.log")


# ------------------------------------------------------------------ 5. acceso por WAMP
CARPETAS_WWW = (
    Path("C:/wamp64/www"), Path("C:/wamp/www"),                     # Windows: WAMP
    Path("/Applications/MAMP/htdocs"),                              # Mac: MAMP
    Path("/opt/homebrew/var/www"), Path("/usr/local/var/www"),      # Mac: Apache de Homebrew
)


def instalar_acceso_wamp() -> None:
    origen = RAIZ / "wamp" / "cobros" / "index.php"
    for www in CARPETAS_WWW:
        if www.exists() and origen.exists():
            destino = www / "cobros"
            destino.mkdir(exist_ok=True)
            contenido = origen.read_text(encoding="utf-8").replace("__RAIZ_PROYECTO__", str(RAIZ).replace("\\", "/"))
            archivo = destino / "index.php"
            try:
                if not archivo.exists() or archivo.read_text(encoding="utf-8") != contenido:
                    archivo.write_text(contenido, encoding="utf-8")
                # Módulo sencillo de llamadas (http://localhost/cobros/llamadas/). No reemplaza un config.php ya editado.
                mod = RAIZ / "wamp" / "cobros" / "llamadas"
                if mod.is_dir():
                    (destino / "llamadas").mkdir(exist_ok=True)
                    for f in mod.iterdir():
                        dest = destino / "llamadas" / f.name
                        if f.is_file() and (f.name != "config.php" or not dest.exists()):
                            dest.write_bytes(f.read_bytes())
            except OSError:
                continue  # sin permiso de escritura en esa carpeta: probar la siguiente
            return


def main() -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    if api_activa():
        estado("listo", "El sistema ya está en ejecución.", "listo")
        if not FONDO:
            webbrowser.open(URL)
        return
    if BLOQUEO.exists() and time.time() - BLOQUEO.stat().st_mtime < 900:
        estado("esperando", "Ya hay un arranque en curso; espere un momento...")
        return
    BLOQUEO.write_text(str(os.getpid()))
    try:
        en_venv = sys.prefix != sys.base_prefix and Path(sys.prefix).resolve() == (BACK / ".venv").resolve()
        if not en_venv:
            preparar_entorno()
            # Continuar con el Python del entorno virtual (tiene las dependencias)
            BLOQUEO.unlink(missing_ok=True)
            r = subprocess.run([str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])
            sys.exit(r.returncode)
        preparar_entorno()
        if puerto_ocupado():
            fallar("El puerto 8000 está ocupado por otro programa. Ciérrelo o reinicie la computadora.")
        configurar_mysql()
        preparar_base()
        estado("iniciando", "Iniciando el servidor web y el procesador de trabajos...")
        iniciar_procesos()
        instalar_acceso_wamp()
        estado("listo", f"Sistema listo en {URL}", "listo")
        if not FONDO:
            print("Acceso directo para la próxima vez: http://localhost/cobros/  (o este mismo archivo INICIAR.bat / INICIAR.command)")
            webbrowser.open(URL)
    finally:
        BLOQUEO.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
