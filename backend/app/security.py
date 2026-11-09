"""Autenticación, sesiones, CSRF y autorización (denegación por defecto)."""
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import AsignacionSupervision, Permiso, RolPermiso, Sesion, Usuario, ahora_utc

COOKIE_SESION = "sc_sesion"
COOKIE_CSRF = "sc_csrf"
HEADER_CSRF = "X-CSRF-Token"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


# ------------------------------------------------------------------ contraseñas
# Se usa scrypt (hashlib, OpenSSL) en lugar de bcrypt. Justificación en DECISIONES.md:
# algoritmo resistente a memoria recomendado por OWASP, sin truncar a 72 bytes como bcrypt
# y sin dependencias compiladas adicionales en Windows.
def hash_password(password: str) -> str:
    s = get_settings()
    sal = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=sal, n=s.scrypt_n, r=s.scrypt_r, p=s.scrypt_p,
                        maxmem=256 * 1024 * 1024, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        s.scrypt_n, s.scrypt_r, s.scrypt_p,
        base64.b64encode(sal).decode(), base64.b64encode(dk).decode(),
    )


def verificar_password(password: str, almacenado: str) -> bool:
    try:
        alg, n, r, p, sal_b64, dk_b64 = almacenado.split("$")
        if alg != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(sal_b64), n=int(n), r=int(r),
                            p=int(p), maxmem=256 * 1024 * 1024, dklen=32)
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


_HASH_FICTICIO: str | None = None


def hash_ficticio() -> str:
    """Hash para comparar cuando el usuario no existe (mismo costo => evita enumeración por tiempo)."""
    global _HASH_FICTICIO
    if _HASH_FICTICIO is None:
        _HASH_FICTICIO = hash_password(secrets.token_urlsafe(16))
    return _HASH_FICTICIO


def validar_fortaleza(password: str) -> None:
    if len(password) < 10 or len(password) > 128:
        raise HTTPException(422, "La contraseña debe tener entre 10 y 128 caracteres.")
    clases = sum([any(c.islower() for c in password), any(c.isupper() for c in password),
                  any(c.isdigit() for c in password), any(not c.isalnum() for c in password)])
    if clases < 3:
        raise HTTPException(422, "La contraseña debe combinar al menos 3 de: minúsculas, mayúsculas, números, símbolos.")


def sha256(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ sesiones
def crear_sesion(db: Session, usuario: Usuario, ip: str | None, ua: str | None) -> tuple[str, str]:
    s = get_settings()
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    ahora = ahora_utc()
    db.add(Sesion(id_usuario=usuario.id_usuario, token_hash=sha256(token), csrf_hash=sha256(csrf), creada=ahora,
                  ultimo_uso=ahora, expira=ahora + timedelta(hours=s.sesion_absoluta_horas), ip_origen=ip,
                  user_agent=(ua or "")[:255]))
    return token, csrf


def poner_cookies(response, token: str, csrf: str) -> None:
    s = get_settings()
    edad = s.sesion_absoluta_horas * 3600
    response.set_cookie(COOKIE_SESION, token, max_age=edad, httponly=True, samesite="strict",
                        secure=s.cookie_secure, path="/")
    # La cookie CSRF es legible por JS (patrón double-submit) y además está ligada a la sesión en BD.
    response.set_cookie(COOKIE_CSRF, csrf, max_age=edad, httponly=False, samesite="strict",
                        secure=s.cookie_secure, path="/")


def borrar_cookies(response) -> None:
    response.delete_cookie(COOKIE_SESION, path="/")
    response.delete_cookie(COOKIE_CSRF, path="/")


def ip_cliente(request: Request) -> str:
    # No se confía en X-Forwarded-For: el servicio escucha solo en localhost.
    return request.client.host if request.client else "desconocida"


@dataclass
class Contexto:
    usuario: Usuario
    sesion: Sesion
    permisos: set[str]
    ip: str

    def tiene(self, permiso: str) -> bool:
        return permiso in self.permisos


def permisos_de_rol(db: Session, id_rol: int) -> set[str]:
    filas = db.execute(
        select(Permiso.codigo).join(RolPermiso, RolPermiso.id_permiso == Permiso.id_permiso)
        .where(RolPermiso.id_rol == id_rol)
    ).scalars().all()
    return set(filas)


def obtener_contexto(request: Request, db: Session = Depends(get_db)) -> Contexto:
    s = get_settings()
    token = request.cookies.get(COOKIE_SESION)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión no iniciada.")
    ses = db.execute(select(Sesion).where(Sesion.token_hash == sha256(token))).scalar_one_or_none()
    ahora = ahora_utc()
    if (ses is None or ses.revocada_en is not None or ses.expira <= ahora
            or ses.ultimo_uso + timedelta(minutes=s.sesion_inactividad_min) <= ahora):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión expirada o revocada.")
    usuario = ses.usuario
    if usuario.estado != "ACTIVO":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión expirada o revocada.")
    if request.method not in METODOS_SEGUROS:
        enviado = request.headers.get(HEADER_CSRF, "")
        cookie = request.cookies.get(COOKIE_CSRF, "")
        if not enviado or not hmac.compare_digest(enviado, cookie) or not hmac.compare_digest(sha256(enviado), ses.csrf_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Token CSRF inválido.")
    ses.ultimo_uso = ahora
    db.commit()
    return Contexto(usuario=usuario, sesion=ses, permisos=permisos_de_rol(db, usuario.id_rol), ip=ip_cliente(request))


def requiere(*permisos: str):
    """Dependencia: exige TODOS los permisos indicados (denegación por defecto)."""

    def _dep(ctx: Contexto = Depends(obtener_contexto)) -> Contexto:
        faltan = [p for p in permisos if p not in ctx.permisos]
        if faltan:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene permiso para esta acción.")
        return ctx

    return _dep


def campanas_permitidas(db: Session, ctx: Contexto, para_gestion: bool = False) -> set[int] | None:
    """None = todas (permiso campanas.todas). Si no, solo campañas asignadas al usuario."""
    if ctx.tiene("campanas.todas"):
        return None
    q = select(AsignacionSupervision.id_campana).where(AsignacionSupervision.id_usuario == ctx.usuario.id_usuario)
    if para_gestion:
        q = q.where(AsignacionSupervision.alcance == "GESTION")
    return set(db.execute(q).scalars().all())


def verificar_campana(db: Session, ctx: Contexto, id_campana: int | None, para_gestion: bool = False) -> None:
    permitidas = campanas_permitidas(db, ctx, para_gestion)
    if permitidas is None:
        return
    if id_campana is None or id_campana not in permitidas:
        # 404 para no revelar la existencia de registros ajenos
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Registro no encontrado.")
