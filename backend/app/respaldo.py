"""Respaldo y restauración de la base de datos, cifrados con Fernet (clave RESPALDO_CLAVE en .env).

  python -m app.respaldo crear                 -> datos/respaldos/cobros_AAAAMMDD_HHMMSS.sql.enc
  python -m app.respaldo restaurar <archivo>   -> pide escribir RESTAURAR (sobrescribe la base actual)
  python -m app.respaldo verificar <archivo>   -> comprueba que el respaldo se descifra y contiene SQL

MySQL: usa mysqldump / mysql (MYSQL_BIN_DIR si no están en el PATH). Las credenciales se pasan en un archivo
temporal --defaults-extra-file que se borra al terminar (no aparecen en la línea de comandos).
SQLite (solo pruebas): copia el archivo de base de datos.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

DIR_RESPALDOS = Path("datos/respaldos")


def _fernet() -> Fernet:
    clave = os.environ.get("RESPALDO_CLAVE") or get_settings().respaldo_clave
    if not clave:
        sys.exit("Falta RESPALDO_CLAVE en .env. Genere una con:\n"
                 '  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"\n'
                 "Guárdela fuera del equipo: sin ella no se puede restaurar.")
    return Fernet(clave.encode())


def _url_bd() -> str:
    return os.environ.get("DATABASE_URL_MIGRACIONES") or get_settings().database_url_migraciones or get_settings().database_url


def _bin(nombre: str) -> str:
    base = os.environ.get("MYSQL_BIN_DIR") or get_settings().mysql_bin_dir
    if base:
        candidato = Path(base) / (nombre + (".exe" if os.name == "nt" else ""))
        if candidato.exists():
            return str(candidato)
    ruta = shutil.which(nombre)
    if not ruta:
        sys.exit(f"No se encontró '{nombre}'. Configure MYSQL_BIN_DIR en .env (p. ej. C:\\Program Files\\MySQL\\MySQL Server 8.4\\bin).")
    return ruta


def _opciones_mysql(url) -> tuple[str, str]:
    contenido = (f"[client]\nuser={unquote(url.username or '')}\npassword={unquote(url.password or '')}\n"
                 f"host={url.hostname or '127.0.0.1'}\nport={url.port or 3306}\n")
    fd, ruta = tempfile.mkstemp(suffix=".cnf")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(contenido)
    os.chmod(ruta, 0o600)
    return ruta, url.path.lstrip("/").split("?")[0]


def volcar() -> bytes:
    url_txt = _url_bd()
    if url_txt.startswith("sqlite"):
        return Path(url_txt.split("///", 1)[1]).read_bytes()
    url = urlparse(url_txt.replace("mysql+pymysql://", "mysql://"))
    opciones, bd = _opciones_mysql(url)
    try:
        r = subprocess.run([_bin("mysqldump"), f"--defaults-extra-file={opciones}", "--single-transaction", "--routines",
                            "--triggers", "--no-tablespaces", "--default-character-set=utf8mb4", "--set-gtid-purged=OFF", bd],
                           capture_output=True, check=False)
    finally:
        os.remove(opciones)
    if r.returncode != 0:
        sys.exit("mysqldump falló: " + r.stderr.decode("utf-8", "replace")[:500])
    return r.stdout


def cargar(datos: bytes) -> None:
    url_txt = _url_bd()
    if url_txt.startswith("sqlite"):
        Path(url_txt.split("///", 1)[1]).write_bytes(datos)
        return
    url = urlparse(url_txt.replace("mysql+pymysql://", "mysql://"))
    opciones, bd = _opciones_mysql(url)
    try:
        r = subprocess.run([_bin("mysql"), f"--defaults-extra-file={opciones}", "--default-character-set=utf8mb4", bd],
                           input=datos, capture_output=True, check=False)
    finally:
        os.remove(opciones)
    if r.returncode != 0:
        sys.exit("mysql falló al restaurar: " + r.stderr.decode("utf-8", "replace")[:500])


def crear(destino: Path = DIR_RESPALDOS) -> Path:
    f = _fernet()
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"cobros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql.enc"
    archivo.write_bytes(f.encrypt(volcar()))
    return archivo


def descifrar(archivo: Path) -> bytes:
    try:
        return _fernet().decrypt(Path(archivo).read_bytes())
    except InvalidToken:
        sys.exit("No se pudo descifrar: la clave RESPALDO_CLAVE no corresponde o el archivo está dañado.")


def main():
    p = argparse.ArgumentParser(prog="python -m app.respaldo")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("crear")
    r = sub.add_parser("restaurar")
    r.add_argument("archivo")
    r.add_argument("--si", action="store_true")
    v = sub.add_parser("verificar")
    v.add_argument("archivo")
    a = p.parse_args()
    if a.cmd == "crear":
        ruta = crear()
        print(f"Respaldo cifrado creado: {ruta} ({ruta.stat().st_size} bytes)")
    elif a.cmd == "verificar":
        datos = descifrar(Path(a.archivo))
        ok = datos.startswith(b"SQLite format 3") or b"CREATE TABLE" in datos[:200000]
        print(f"Descifrado correcto: {len(datos)} bytes. Contenido {'válido' if ok else 'NO reconocido'}.")
        sys.exit(0 if ok else 1)
    else:
        datos = descifrar(Path(a.archivo))
        if not a.si and input("Esto SOBRESCRIBE la base de datos actual. Escriba RESTAURAR para continuar: ").strip() != "RESTAURAR":
            sys.exit("Cancelado.")
        cargar(datos)
        print("Restauración completada. Reinicie el sistema (detener.ps1 / iniciar.ps1).")


if __name__ == "__main__":
    main()
