"""Módulo Agentes Internos (HU-01 a HU-04, CU-01 a CU-03): usuarios, roles, permisos y supervisión."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auditoria import auditar
from ..db import get_db
from ..models import AsignacionSupervision, Campana, Permiso, Rol, RolPermiso, Sesion, Usuario, ahora_utc
from ..security import Contexto, hash_password, requiere, validar_fortaleza
from .comun import Paginacion, a_dict, obtener_o_404, paginar

router = APIRouter(prefix="/api", tags=["Agentes Internos"])
_RE_USUARIO = re.compile(r"^[a-zA-Z0-9._-]{3,50}$")
_RE_CORREO = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")
_RE_NOMBRE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ' .-]{2,80}$")


class UsuarioBase(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    apellido: str = Field(min_length=2, max_length=80)
    correo: str = Field(max_length=160)
    id_rol: int

    @field_validator("correo")
    @classmethod
    def _correo(cls, v: str) -> str:
        v = v.strip().lower()
        if not _RE_CORREO.match(v):
            raise ValueError("Correo electrónico inválido")
        return v

    @field_validator("nombre", "apellido")
    @classmethod
    def _nombre(cls, v: str) -> str:
        v = v.strip()
        if not _RE_NOMBRE.match(v):
            raise ValueError("Solo letras, espacios, apóstrofos, puntos y guiones")
        return v


class UsuarioCrear(UsuarioBase):
    usuario: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("usuario")
    @classmethod
    def _usuario(cls, v: str) -> str:
        if not _RE_USUARIO.match(v):
            raise ValueError("Use 3 a 50 caracteres: letras, números, punto, guion o guion bajo")
        return v.lower()


class EstadoIn(BaseModel):
    estado: str = Field(pattern="^(ACTIVO|INACTIVO)$")


class RolIn(BaseModel):
    id_rol: int


class PasswordIn(BaseModel):
    password: str = Field(min_length=10, max_length=128)


class PermisosIn(BaseModel):
    codigos: list[str]


class SupervisionIn(BaseModel):
    id_usuario: int
    id_campana: int
    alcance: str = Field(default="GESTION", pattern="^(LECTURA|GESTION)$")


def ser_usuario(u: Usuario) -> dict:
    d = a_dict(u, ["id_usuario", "nombre", "apellido", "correo", "usuario", "estado", "fecha_creacion", "ultimo_acceso", "id_rol"])
    d["rol"] = u.rol.nombre if u.rol else None
    d["bloqueado_temporalmente"] = bool(u.bloqueado_hasta and u.bloqueado_hasta > ahora_utc())
    return d


def _revocar_sesiones(db: Session, id_usuario: int) -> None:
    db.execute(update(Sesion).where(Sesion.id_usuario == id_usuario, Sesion.revocada_en.is_(None)).values(revocada_en=ahora_utc()))


@router.get("/usuarios")
def listar(q: str | None = None, id_rol: int | None = None, estado: str | None = None, pag: Paginacion = Depends(),
           ctx: Contexto = Depends(requiere("usuarios.ver")), db: Session = Depends(get_db)):
    consulta = select(Usuario).order_by(Usuario.id_usuario.desc())
    if q:
        patron = f"%{q.strip()[:60]}%"
        consulta = consulta.where(or_(Usuario.nombre.ilike(patron), Usuario.apellido.ilike(patron),
                                      Usuario.usuario.ilike(patron), Usuario.correo.ilike(patron)))
    if id_rol:
        consulta = consulta.where(Usuario.id_rol == id_rol)
    if estado:
        consulta = consulta.where(Usuario.estado == estado)
    return paginar(db, consulta, pag, ser_usuario)


@router.post("/usuarios", status_code=201)
def crear(datos: UsuarioCrear, ctx: Contexto = Depends(requiere("usuarios.gestionar")), db: Session = Depends(get_db)):
    obtener_o_404(db, Rol, datos.id_rol)
    validar_fortaleza(datos.password)
    u = Usuario(nombre=datos.nombre, apellido=datos.apellido, correo=str(datos.correo).lower(), usuario=datos.usuario,
                id_rol=datos.id_rol, hash_password=hash_password(datos.password), estado="ACTIVO")
    db.add(u)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El nombre de usuario o el correo ya están registrados.")
    auditar(db, "USUARIO_CREADO", "usuario", u.id_usuario, {"usuario": u.usuario, "id_rol": u.id_rol}, ctx=ctx)
    db.commit()
    return ser_usuario(u)


@router.get("/usuarios/{id_usuario}")
def detalle(id_usuario: int, ctx: Contexto = Depends(requiere("usuarios.ver")), db: Session = Depends(get_db)):
    return ser_usuario(obtener_o_404(db, Usuario, id_usuario))


@router.put("/usuarios/{id_usuario}")
def modificar(id_usuario: int, datos: UsuarioBase, ctx: Contexto = Depends(requiere("usuarios.gestionar")),
              db: Session = Depends(get_db)):
    u = obtener_o_404(db, Usuario, id_usuario)
    obtener_o_404(db, Rol, datos.id_rol)
    if u.id_usuario == ctx.usuario.id_usuario and datos.id_rol != u.id_rol:
        raise HTTPException(400, "No puede cambiar su propio rol.")
    antes = {"nombre": u.nombre, "apellido": u.apellido, "correo": u.correo, "id_rol": u.id_rol}
    u.nombre, u.apellido, u.correo = datos.nombre, datos.apellido, str(datos.correo).lower()
    rol_cambio = u.id_rol != datos.id_rol
    u.id_rol = datos.id_rol
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El correo ya está registrado.")
    if rol_cambio:
        _revocar_sesiones(db, u.id_usuario)
    auditar(db, "USUARIO_MODIFICADO", "usuario", u.id_usuario, {"antes": antes, "rol_cambiado": rol_cambio}, ctx=ctx)
    db.commit()
    return ser_usuario(u)


@router.post("/usuarios/{id_usuario}/rol")
def asignar_rol(id_usuario: int, datos: RolIn, ctx: Contexto = Depends(requiere("usuarios.gestionar")),
                db: Session = Depends(get_db)):
    u = obtener_o_404(db, Usuario, id_usuario)
    rol = obtener_o_404(db, Rol, datos.id_rol)
    if u.id_usuario == ctx.usuario.id_usuario:
        raise HTTPException(400, "No puede cambiar su propio rol.")
    anterior = u.id_rol
    u.id_rol = rol.id_rol
    _revocar_sesiones(db, u.id_usuario)  # los permisos nuevos aplican en el próximo inicio de sesión
    auditar(db, "ROL_ASIGNADO", "usuario", u.id_usuario, {"anterior": anterior, "nuevo": rol.id_rol}, ctx=ctx)
    db.commit()
    return ser_usuario(u)


@router.post("/usuarios/{id_usuario}/estado")
def cambiar_estado(id_usuario: int, datos: EstadoIn, ctx: Contexto = Depends(requiere("usuarios.gestionar")),
                   db: Session = Depends(get_db)):
    u = obtener_o_404(db, Usuario, id_usuario)
    if u.id_usuario == ctx.usuario.id_usuario:
        raise HTTPException(400, "No puede desactivarse a sí mismo.")
    u.estado = datos.estado
    if datos.estado != "ACTIVO":
        _revocar_sesiones(db, u.id_usuario)
    else:
        u.bloqueado_hasta, u.intentos_fallidos = None, 0
    auditar(db, "USUARIO_ESTADO", "usuario", u.id_usuario, {"estado": datos.estado}, ctx=ctx)
    db.commit()
    return ser_usuario(u)


@router.post("/usuarios/{id_usuario}/password")
def restablecer_password(id_usuario: int, datos: PasswordIn, ctx: Contexto = Depends(requiere("usuarios.gestionar")),
                         db: Session = Depends(get_db)):
    u = obtener_o_404(db, Usuario, id_usuario)
    validar_fortaleza(datos.password)
    u.hash_password = hash_password(datos.password)
    u.bloqueado_hasta, u.intentos_fallidos = None, 0
    _revocar_sesiones(db, u.id_usuario)
    auditar(db, "PASSWORD_RESTABLECIDA", "usuario", u.id_usuario, ctx=ctx)
    db.commit()
    return {"ok": True}


@router.post("/usuarios/{id_usuario}/revocar-sesiones")
def revocar(id_usuario: int, ctx: Contexto = Depends(requiere("usuarios.gestionar")), db: Session = Depends(get_db)):
    obtener_o_404(db, Usuario, id_usuario)
    _revocar_sesiones(db, id_usuario)
    auditar(db, "SESIONES_REVOCADAS", "usuario", id_usuario, ctx=ctx)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- roles y permisos
@router.get("/roles")
def roles(ctx: Contexto = Depends(requiere("usuarios.ver")), db: Session = Depends(get_db)):
    salida = []
    for r in db.execute(select(Rol).order_by(Rol.id_rol)).scalars():
        salida.append({"id_rol": r.id_rol, "nombre": r.nombre, "descripcion": r.descripcion,
                       "permisos": sorted(rp.permiso.codigo for rp in r.permisos)})
    return salida


@router.get("/permisos")
def permisos(ctx: Contexto = Depends(requiere("usuarios.ver")), db: Session = Depends(get_db)):
    return [a_dict(p, ["id_permiso", "codigo", "modulo", "accion"]) for p in db.execute(select(Permiso).order_by(Permiso.modulo))
            .scalars()]


@router.put("/roles/{id_rol}/permisos")
def actualizar_permisos(id_rol: int, datos: PermisosIn, ctx: Contexto = Depends(requiere("roles.gestionar")),
                        db: Session = Depends(get_db)):
    rol = obtener_o_404(db, Rol, id_rol)
    if rol.nombre == "ADMINISTRADOR":
        raise HTTPException(400, "Los permisos del rol ADMINISTRADOR no se modifican desde la interfaz.")
    validos = {p.codigo: p.id_permiso for p in db.execute(select(Permiso)).scalars()}
    desconocidos = [c for c in datos.codigos if c not in validos]
    if desconocidos:
        raise HTTPException(422, "Permisos desconocidos: " + ", ".join(desconocidos))
    rol.permisos.clear()
    db.flush()
    for c in set(datos.codigos):
        db.add(RolPermiso(id_rol=id_rol, id_permiso=validos[c]))
    ids = list(db.execute(select(Usuario.id_usuario).where(Usuario.id_rol == id_rol)).scalars())
    for i in ids:
        _revocar_sesiones(db, i)
    auditar(db, "PERMISOS_ROL", "rol", id_rol, {"codigos": sorted(set(datos.codigos))}, ctx=ctx)
    db.commit()
    return {"ok": True, "sesiones_revocadas_de_usuarios": len(ids)}


# ---------------------------------------------------------------- asignaciones de supervisión
@router.get("/supervision")
def asignaciones(ctx: Contexto = Depends(requiere("usuarios.ver")), db: Session = Depends(get_db)):
    filas = db.execute(select(AsignacionSupervision, Usuario, Campana)
                       .join(Usuario, Usuario.id_usuario == AsignacionSupervision.id_usuario)
                       .join(Campana, Campana.id_campana == AsignacionSupervision.id_campana)).all()
    return [{"id": a.id, "id_usuario": u.id_usuario, "usuario": u.usuario, "id_campana": c.id_campana,
             "campana": c.nombre, "alcance": a.alcance} for a, u, c in filas]


@router.post("/supervision", status_code=201)
def asignar(datos: SupervisionIn, ctx: Contexto = Depends(requiere("usuarios.gestionar")), db: Session = Depends(get_db)):
    obtener_o_404(db, Usuario, datos.id_usuario)
    obtener_o_404(db, Campana, datos.id_campana)
    a = AsignacionSupervision(id_usuario=datos.id_usuario, id_campana=datos.id_campana, alcance=datos.alcance)
    db.add(a)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La asignación ya existe.")
    auditar(db, "SUPERVISION_ASIGNADA", "asignacion", a.id, datos.model_dump(), ctx=ctx)
    db.commit()
    return {"id": a.id}


@router.delete("/supervision/{id_asig}")
def quitar(id_asig: int, ctx: Contexto = Depends(requiere("usuarios.gestionar")), db: Session = Depends(get_db)):
    a = obtener_o_404(db, AsignacionSupervision, id_asig)
    db.delete(a)
    auditar(db, "SUPERVISION_QUITADA", "asignacion", id_asig, ctx=ctx)
    db.commit()
    return {"ok": True}
