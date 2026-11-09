"""Grabaciones privadas cifradas en reposo con Fernet (AES-128-CBC + HMAC-SHA256, librería `cryptography`).

Si GRABACIONES_CLAVE está vacía, NO se guarda audio (solo transcripción enmascarada).
Generar clave:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Grabacion


def _fernet() -> Fernet | None:
    clave = get_settings().grabaciones_clave
    return Fernet(clave.encode()) if clave else None


def habilitadas() -> bool:
    return _fernet() is not None


def guardar(db: Session, id_llamada: int, audio: bytes, formato: str) -> Grabacion | None:
    f = _fernet()
    if f is None:
        return None
    carpeta = Path(get_settings().grabaciones_dir) / str(id_llamada)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{secrets.token_hex(8)}.bin"  # nombre no adivinable; contenido cifrado
    (carpeta / nombre).write_bytes(f.encrypt(audio))
    g = Grabacion(id_llamada=id_llamada, ruta_audio=f"{id_llamada}/{nombre}", formato=formato[:40], cifrada=True)
    db.add(g)
    return g


def leer(g: Grabacion) -> bytes:
    f = _fernet()
    if f is None:
        raise PermissionError("No hay clave de grabaciones configurada")
    base = Path(get_settings().grabaciones_dir).resolve()
    ruta = (base / g.ruta_audio).resolve()
    if base not in ruta.parents:
        raise PermissionError("Ruta inválida")
    try:
        return f.decrypt(ruta.read_bytes())
    except InvalidToken as e:
        raise PermissionError("No se pudo descifrar la grabación (clave incorrecta)") from e
