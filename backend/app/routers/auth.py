"""Autenticación (DS-01, DF-01): sin registro público, bloqueo por intentos, sesiones revocables."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..auditoria import auditar
from ..config import get_settings
from ..db import get_db
from ..models import IntentoLogin, Sesion, Usuario, ahora_utc
from ..security import (
    Contexto,
    borrar_cookies,
    crear_sesion,
    hash_ficticio,
    hash_password,
    ip_cliente,
    obtener_contexto,
    poner_cookies,
    sha256,
    validar_fortaleza,
    verificar_password,
)
from .comun import a_dict

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])
MENSAJE_GENERICO = "Usuario o contraseña incorrectos, o cuenta no disponible."


class LoginIn(BaseModel):
    usuario: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class CambioIn(BaseModel):
    actual: str = Field(min_length=1, max_length=128)
    nueva: str = Field(min_length=10, max_length=128)


def datos_usuario(u: Usuario, permisos: set[str]) -> dict:
    d = a_dict(u, ["id_usuario", "nombre", "apellido", "correo", "usuario", "estado"])
    d["rol"] = u.rol.nombre
    d["permisos"] = sorted(permisos)
    return d


@router.post("/login")
def login(datos: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    ip = ip_cliente(request)
    ahora = ahora_utc()
    fallos_ip = db.execute(select(func.count(IntentoLogin.id)).where(
        IntentoLogin.ip == ip, IntentoLogin.exito.is_(False), IntentoLogin.fecha >= ahora - timedelta(minutes=15))).scalar_one()
    if fallos_ip >= s.login_max_fallos_ip_15min:
        raise HTTPException(429, "Demasiados intentos. Espere unos minutos.")
    nombre = datos.usuario.strip().lower()
    u = db.execute(select(Usuario).where(func.lower(Usuario.usuario) == nombre)).scalar_one_or_none()
    valido = verificar_password(datos.password, u.hash_password if u else hash_ficticio())
    bloqueado = u is not None and u.bloqueado_hasta is not None and u.bloqueado_hasta > ahora
    exito = bool(u and valido and not bloqueado and u.estado == "ACTIVO")
    db.add(IntentoLogin(ip=ip, usuario_hash=sha256(nombre), exito=exito))
    if not exito:
        if u is not None and not bloqueado:
            u.intentos_fallidos += 1
            if u.intentos_fallidos >= s.login_max_intentos_usuario:
                u.bloqueado_hasta = ahora + timedelta(minutes=s.login_bloqueo_min)
                u.intentos_fallidos = 0
                auditar(db, "CUENTA_BLOQUEADA_TEMPORALMENTE", "usuario", u.id_usuario, ip=ip)
        auditar(db, "LOGIN_FALLIDO", "sesion", None, {"usuario_hash": sha256(nombre)[:12]}, ip=ip)
        db.commit()
        raise HTTPException(401, MENSAJE_GENERICO)
    u.intentos_fallidos, u.bloqueado_hasta, u.ultimo_acceso = 0, None, ahora
    token, csrf = crear_sesion(db, u, ip, request.headers.get("user-agent"))
    auditar(db, "LOGIN", "sesion", None, id_usuario=u.id_usuario, ip=ip)
    db.commit()
    poner_cookies(response, token, csrf)
    from ..security import permisos_de_rol

    return {"usuario": datos_usuario(u, permisos_de_rol(db, u.id_rol))}


@router.post("/logout")
def logout(response: Response, ctx: Contexto = Depends(obtener_contexto), db: Session = Depends(get_db)):
    ses = db.get(Sesion, ctx.sesion.id_sesion)
    ses.revocada_en = ahora_utc()
    auditar(db, "LOGOUT", "sesion", ses.id_sesion, ctx=ctx)
    db.commit()
    borrar_cookies(response)
    return {"ok": True}


@router.get("/yo")
def yo(ctx: Contexto = Depends(obtener_contexto)):
    return {"usuario": datos_usuario(ctx.usuario, ctx.permisos)}


@router.post("/cambiar-password")
def cambiar_password(datos: CambioIn, response: Response, ctx: Contexto = Depends(obtener_contexto),
                     db: Session = Depends(get_db)):
    u = db.get(Usuario, ctx.usuario.id_usuario)
    if not verificar_password(datos.actual, u.hash_password):
        raise HTTPException(400, "La contraseña actual no es correcta.")
    validar_fortaleza(datos.nueva)
    u.hash_password = hash_password(datos.nueva)
    db.execute(update(Sesion).where(Sesion.id_usuario == u.id_usuario, Sesion.revocada_en.is_(None))
               .values(revocada_en=ahora_utc()))
    auditar(db, "CAMBIO_PASSWORD", "usuario", u.id_usuario, ctx=ctx)
    db.commit()
    borrar_cookies(response)
    return {"ok": True, "mensaje": "Contraseña actualizada. Inicie sesión de nuevo."}
