"""Módulo Campañas (HU-05, HU-06, CU-04 a CU-06) y tramos de mora."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auditoria import auditar
from ..db import get_db
from ..models import AgenteIA, Campana, CampanaAgente, ClienteCampana, TramoMora
from ..security import Contexto, campanas_permitidas, requiere, verificar_campana
from ..servicios import campanas as srv
from ..utils import enmascarar_telefono, parse_hhmm
from .comun import Paginacion, a_dict, obtener_o_404, paginar

router = APIRouter(prefix="/api", tags=["Campañas"])


class CampanaIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=120)
    id_tramo: int
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    mensaje_base: str | None = Field(default=None, max_length=2000)
    prioridad: int = Field(default=1, ge=1, le=10)
    hora_inicio: str = "08:00"
    hora_fin: str = "20:00"
    max_intentos_dia: int = Field(default=2, ge=1, le=10)
    max_intentos_total: int = Field(default=6, ge=1, le=50)
    minutos_entre_intentos: int = Field(default=120, ge=5, le=10080)
    max_concurrencia: int = Field(default=1, ge=1, le=5)

    @field_validator("hora_inicio", "hora_fin")
    @classmethod
    def _hora(cls, v):
        parse_hhmm(v)
        return v


class EstadoIn(BaseModel):
    estado: str = Field(pattern="^(ACTIVA|PAUSADA|FINALIZADA)$")


class AgenteIn(BaseModel):
    id_agente: int


class TramoIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=80)
    prioridad: int = Field(ge=1, le=10)
    tono_permitido: str = Field(min_length=3, max_length=255)


def ser_campana(db: Session, c: Campana, detalle=False) -> dict:
    d = a_dict(c, ["id_campana", "nombre", "id_tramo", "estado", "fecha_inicio", "fecha_fin", "mensaje_base", "prioridad",
                   "hora_inicio", "hora_fin", "max_intentos_dia", "max_intentos_total", "minutos_entre_intentos",
                   "max_concurrencia", "fecha_creacion"])
    d["tramo"] = {"codigo": c.tramo.codigo, "nombre": c.tramo.nombre, "dias_min": c.tramo.dias_min, "dias_max": c.tramo.dias_max}
    d["agentes"] = [{"id_agente": ca.agente.id_agente, "nombre": ca.agente.nombre} for ca in c.agentes]
    conteo = dict(db.execute(select(ClienteCampana.estado_gestion, func.count()).where(ClienteCampana.id_campana == c.id_campana)
                             .group_by(ClienteCampana.estado_gestion)).all())
    d["clientes_por_estado"] = conteo
    d["total_clientes"] = sum(conteo.values())
    if detalle:
        d["faltantes_para_activar"] = srv.faltantes_para_activar(db, c) if c.estado in ("BORRADOR", "PAUSADA") else []
    return d


@router.get("/tramos")
def tramos(ctx: Contexto = Depends(requiere("campanas.ver")), db: Session = Depends(get_db)):
    return [a_dict(t, ["id_tramo", "codigo", "nombre", "dias_min", "dias_max", "prioridad", "tono_permitido", "severidad"])
            for t in db.execute(select(TramoMora).order_by(TramoMora.dias_min)).scalars()]


@router.put("/tramos/{id_tramo}")
def editar_tramo(id_tramo: int, datos: TramoIn, ctx: Contexto = Depends(requiere("campanas.gestionar", "campanas.todas")),
                 db: Session = Depends(get_db)):
    t = obtener_o_404(db, TramoMora, id_tramo)
    t.nombre, t.prioridad, t.tono_permitido = datos.nombre, datos.prioridad, datos.tono_permitido
    auditar(db, "TRAMO_MODIFICADO", "tramo", id_tramo, datos.model_dump(), ctx=ctx)
    db.commit()
    return {"ok": True}


@router.get("/campanas")
def listar(estado: str | None = None, pag: Paginacion = Depends(), ctx: Contexto = Depends(requiere("campanas.ver")),
           db: Session = Depends(get_db)):
    q = select(Campana).order_by(Campana.id_campana.desc())
    permitidas = campanas_permitidas(db, ctx)
    if permitidas is not None:
        q = q.where(Campana.id_campana.in_(permitidas or [-1]))
    if estado:
        q = q.where(Campana.estado == estado)
    return paginar(db, q, pag, lambda c: ser_campana(db, c))


@router.post("/campanas", status_code=201)
def crear(datos: CampanaIn, ctx: Contexto = Depends(requiere("campanas.gestionar")), db: Session = Depends(get_db)):
    obtener_o_404(db, TramoMora, datos.id_tramo)
    c = Campana(**datos.model_dump(), estado="BORRADOR", id_usuario=ctx.usuario.id_usuario)
    db.add(c)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una campaña con ese nombre.")
    auditar(db, "CAMPANA_CREADA", "campana", c.id_campana, {"nombre": c.nombre}, ctx=ctx)
    db.commit()
    db.refresh(c)
    return ser_campana(db, c, True)


@router.get("/campanas/{id_campana}")
def detalle(id_campana: int, ctx: Contexto = Depends(requiere("campanas.ver")), db: Session = Depends(get_db)):
    verificar_campana(db, ctx, id_campana)
    return ser_campana(db, obtener_o_404(db, Campana, id_campana), True)


@router.put("/campanas/{id_campana}")
def modificar(id_campana: int, datos: CampanaIn, ctx: Contexto = Depends(requiere("campanas.gestionar")),
              db: Session = Depends(get_db)):
    verificar_campana(db, ctx, id_campana, para_gestion=True)
    c = obtener_o_404(db, Campana, id_campana)
    if c.estado not in ("BORRADOR", "PAUSADA"):
        raise HTTPException(409, "Solo se pueden modificar campañas en BORRADOR o PAUSADA.")
    if datos.id_tramo != c.id_tramo and c.estado != "BORRADOR":
        raise HTTPException(409, "El tramo solo puede cambiarse en BORRADOR.")
    obtener_o_404(db, TramoMora, datos.id_tramo)
    for k, v in datos.model_dump().items():
        setattr(c, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una campaña con ese nombre.")
    auditar(db, "CAMPANA_MODIFICADA", "campana", id_campana, datos.model_dump(mode="json"), ctx=ctx)
    db.commit()
    return ser_campana(db, c, True)


@router.post("/campanas/{id_campana}/agentes")
def asignar_agente(id_campana: int, datos: AgenteIn, ctx: Contexto = Depends(requiere("campanas.gestionar")),
                   db: Session = Depends(get_db)):
    verificar_campana(db, ctx, id_campana, para_gestion=True)
    c = obtener_o_404(db, Campana, id_campana)
    obtener_o_404(db, AgenteIA, datos.id_agente)
    db.add(CampanaAgente(id_campana=id_campana, id_agente=datos.id_agente))
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El agente ya está asignado.")
    auditar(db, "AGENTE_ASIGNADO_CAMPANA", "campana", id_campana, {"id_agente": datos.id_agente}, ctx=ctx)
    db.commit()
    db.refresh(c)
    return ser_campana(db, c, True)


@router.delete("/campanas/{id_campana}/agentes/{id_agente}")
def quitar_agente(id_campana: int, id_agente: int, ctx: Contexto = Depends(requiere("campanas.gestionar")),
                  db: Session = Depends(get_db)):
    verificar_campana(db, ctx, id_campana, para_gestion=True)
    c = obtener_o_404(db, Campana, id_campana)
    if c.estado == "ACTIVA":
        raise HTTPException(409, "Pause la campaña antes de quitar agentes.")
    ca = db.execute(select(CampanaAgente).where(CampanaAgente.id_campana == id_campana,
                                                CampanaAgente.id_agente == id_agente)).scalar_one_or_none()
    if ca is None:
        raise HTTPException(404, "Registro no encontrado.")
    db.delete(ca)
    auditar(db, "AGENTE_QUITADO_CAMPANA", "campana", id_campana, {"id_agente": id_agente}, ctx=ctx)
    db.commit()
    db.refresh(c)
    return ser_campana(db, c, True)


@router.post("/campanas/{id_campana}/clasificar")
def clasificar(id_campana: int, ctx: Contexto = Depends(requiere("campanas.gestionar")), db: Session = Depends(get_db)):
    verificar_campana(db, ctx, id_campana, para_gestion=True)
    c = obtener_o_404(db, Campana, id_campana)
    try:
        r = srv.clasificar_y_asignar(db, c)
    except ValueError as e:
        raise HTTPException(409, str(e))
    auditar(db, "CAMPANA_CLASIFICADA", "campana", id_campana, r, ctx=ctx)
    db.commit()
    return r


@router.post("/campanas/{id_campana}/estado")
def cambiar_estado(id_campana: int, datos: EstadoIn, ctx: Contexto = Depends(requiere("campanas.operar")),
                   db: Session = Depends(get_db)):
    verificar_campana(db, ctx, id_campana, para_gestion=True)
    c = obtener_o_404(db, Campana, id_campana)
    try:
        r = srv.cambiar_estado(db, c, datos.estado)
    except ValueError as e:
        raise HTTPException(409, str(e))
    auditar(db, "CAMPANA_ESTADO", "campana", id_campana, r, ctx=ctx)
    db.commit()
    return {**r, "campana": ser_campana(db, c, True)}


@router.post("/campanas/{id_campana}/encolar")
def encolar(id_campana: int, ctx: Contexto = Depends(requiere("campanas.operar")), db: Session = Depends(get_db)):
    verificar_campana(db, ctx, id_campana, para_gestion=True)
    c = obtener_o_404(db, Campana, id_campana)
    try:
        r = srv.encolar(db, c)
    except ValueError as e:
        raise HTTPException(409, str(e))
    auditar(db, "CAMPANA_ENCOLADA", "campana", id_campana, r, ctx=ctx)
    db.commit()
    return r


@router.get("/campanas/{id_campana}/clientes")
def clientes_campana(id_campana: int, estado: str | None = None, pag: Paginacion = Depends(),
                     ctx: Contexto = Depends(requiere("campanas.ver")), db: Session = Depends(get_db)):
    verificar_campana(db, ctx, id_campana)
    q = select(ClienteCampana).where(ClienteCampana.id_campana == id_campana).order_by(ClienteCampana.id)
    if estado:
        q = q.where(ClienteCampana.estado_gestion == estado)
    return paginar(db, q, pag, lambda cc: {
        "id": cc.id, "id_cliente": cc.id_cliente, "cliente": cc.cliente.nombre,
        "telefono": enmascarar_telefono(cc.cliente.telefono), "id_deuda": cc.id_deuda, "saldo": str(cc.deuda.saldo),
        "moneda": cc.deuda.moneda, "dias_mora": cc.deuda.dias_mora, "intentos": cc.intentos,
        "estado_gestion": cc.estado_gestion})
