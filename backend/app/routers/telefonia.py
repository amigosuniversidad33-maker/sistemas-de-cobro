"""Módulos Plantas FreeSWITCH (CU-24, CU-25) y Extensiones SIP (CU-26, CU-27)."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import parametros
from ..auditoria import auditar
from ..config import get_settings
from ..db import get_db
from ..ia import agente as motor
from ..models import (AgenteIA, CanalConcurrente, Deuda, ExtensionSIP, Llamada, NumeroAutorizado, PlantaFreeswitch,
                      PruebaLlamada, Trabajo, TroncalSIP)
from ..security import Contexto, requiere
from ..telefonia import marcador
from ..telefonia.esl import host_permitido
from ..utils import enmascarar_telefono, normalizar_telefono
from .comun import a_dict, obtener_o_404

router = APIRouter(prefix="/api/telefonia", tags=["Telefonía"])


class PlantaIn(BaseModel):
    nombre: str = Field(min_length=3, max_length=80)
    ip: str = Field(max_length=45)
    puerto_esl: int = Field(default=8021, ge=1, le=65535)
    capacidad_canales: int = Field(ge=1, le=500)
    activa: bool = True

    @field_validator("ip")
    @classmethod
    def _ip(cls, v):
        if not host_permitido(v.strip()):
            raise ValueError("Use localhost o una IP de red privada (no se permite exponer FreeSWITCH a Internet).")
        return v.strip()


class TroncalIn(BaseModel):
    id_planta: int
    nombre: str = Field(min_length=3, max_length=80)
    gateway: str = Field(pattern=r"^[A-Za-z0-9_\-]{1,60}$")
    proveedor: str | None = Field(default=None, max_length=80)
    max_canales: int = Field(ge=1, le=500)
    activa: bool = True


class ExtensionIn(BaseModel):
    id_planta: int
    id_troncal: int | None = None
    numero: str = Field(pattern=r"^[0-9]{2,20}$")
    canales_max: int = Field(ge=1, le=50)
    activa: bool = True


class LlamarExtensionIn(BaseModel):
    id_agente: int
    id_deuda: int
    id_extension: int


class NumeroIn(BaseModel):
    telefono: str = Field(max_length=30)
    descripcion: str = Field(min_length=3, max_length=160)


@router.get("/estado")
def estado(ctx: Contexto = Depends(requiere("telefonia.ver")), db: Session = Depends(get_db)):
    s = get_settings()
    canales = dict(db.execute(select(CanalConcurrente.estado, func.count()).group_by(CanalConcurrente.estado)).all())
    activas = db.execute(select(func.count(Llamada.id_llamada)).where(Llamada.canal == "TELEFONIA",
                                                                      Llamada.estado_tecnico == "EN_CURSO")).scalar_one()
    troncales = db.execute(select(func.count(TroncalSIP.id_troncal)).where(TroncalSIP.activa.is_(True))).scalar_one()
    bloqueos = []
    if not s.telefonia_habilitada:
        bloqueos.append("TELEFONIA_HABILITADA=false en .env")
    if not s.freeswitch_esl_password:
        bloqueos.append("Falta FREESWITCH_ESL_PASSWORD")
    if not s.freeswitch_dir_audio:
        bloqueos.append("Falta FREESWITCH_DIR_AUDIO (carpeta compartida de audio)")
    if troncales == 0:
        bloqueos.append("No hay troncal SIP registrada")
    if not canales:
        bloqueos.append("No hay extensiones/canales configurados")
    if not s.deepgram_api_key:
        bloqueos.append("Falta DEEPGRAM_API_KEY (necesaria para la voz en la llamada)")
    from ..telefonia import twilio as tw

    return {"twilio_faltan": tw.configurado(), "habilitada": s.telefonia_habilitada, "estado": "BLOQUEADA" if bloqueos else "LISTA_PARA_PILOTO",
            "bloqueos": bloqueos, "canales": canales, "llamadas_activas": activas,
            "max_canales_piloto": int(parametros.obtener(db, "max_canales_piloto")),
            "solo_numeros_autorizados": s.telefonia_solo_numeros_autorizados}


@router.get("/dimensionamiento")
def dimensionamiento(llamadas_dia: int = 65000, horas: float = 12, pct_contestadas: float = 50, pct_rechazadas: float = 20,
                     t_contestada_seg: float = 90, t_rechazada_seg: float = 20, t_sin_contestar_seg: float = 30,
                     margen_pct: float = 20, ctx: Contexto = Depends(requiere("telefonia.ver"))):
    """Ley de Little (C = R × T) como ESTIMACIÓN de diseño (sección 6 del documento). No reemplaza límites reales."""
    if not (0 < horas <= 24) or llamadas_dia < 0 or not (0 <= pct_contestadas + pct_rechazadas <= 100):
        raise HTTPException(422, "Parámetros inválidos.")
    r_min = llamadas_dia / (horas * 60)
    pc, pr = pct_contestadas / 100, pct_rechazadas / 100
    pn = 1 - pc - pr
    t_min = (pc * t_contestada_seg + pr * t_rechazada_seg + pn * t_sin_contestar_seg) / 60
    c = r_min * t_min
    return {"R_llamadas_por_minuto": round(r_min, 2), "R_llamadas_por_segundo": round(r_min / 60, 3),
            "T_minutos": round(t_min, 3), "T_segundos": round(t_min * 60, 1), "C_canales_teoricos": round(c, 2),
            "C_canales_recomendados": round(c * (1 + margen_pct / 100), 1),
            "distribucion": {"contestadas": round(llamadas_dia * pc), "rechazadas": round(llamadas_dia * pr),
                             "sin_contestar": round(llamadas_dia * pn)},
            "nota": "Estimación de dimensionamiento futura. El piloto opera con canales limitados y no ha sido probado a esta escala."}


# ---------------------------------------------------------------- plantas
@router.get("/plantas")
def plantas(ctx: Contexto = Depends(requiere("telefonia.ver")), db: Session = Depends(get_db)):
    salida = []
    for p in db.execute(select(PlantaFreeswitch).order_by(PlantaFreeswitch.id_planta)).scalars():
        d = a_dict(p, ["id_planta", "nombre", "ip", "puerto_esl", "capacidad_canales", "estado", "activa", "ultima_verificacion"])
        d["canales_ocupados"] = db.execute(select(func.count(CanalConcurrente.id_canal)).join(ExtensionSIP).where(
            ExtensionSIP.id_planta == p.id_planta, CanalConcurrente.estado == "OCUPADO")).scalar_one()
        d["canales_total"] = db.execute(select(func.count(CanalConcurrente.id_canal)).join(ExtensionSIP).where(
            ExtensionSIP.id_planta == p.id_planta)).scalar_one()
        salida.append(d)
    return salida


@router.post("/plantas", status_code=201)
def crear_planta(datos: PlantaIn, ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    p = PlantaFreeswitch(**datos.model_dump())
    db.add(p)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una planta con ese nombre.")
    auditar(db, "PLANTA_CREADA", "planta", p.id_planta, datos.model_dump(), ctx=ctx)
    db.commit()
    return {"id_planta": p.id_planta}


@router.put("/plantas/{id_planta}")
def modificar_planta(id_planta: int, datos: PlantaIn, ctx: Contexto = Depends(requiere("telefonia.gestionar")),
                     db: Session = Depends(get_db)):
    p = obtener_o_404(db, PlantaFreeswitch, id_planta)
    for k, v in datos.model_dump().items():
        setattr(p, k, v)
    auditar(db, "PLANTA_MODIFICADA", "planta", id_planta, datos.model_dump(), ctx=ctx)
    db.commit()
    return {"ok": True}


@router.post("/plantas/{id_planta}/verificar")
def verificar(id_planta: int, ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    p = obtener_o_404(db, PlantaFreeswitch, id_planta)
    r = marcador.verificar_planta(db, p)
    auditar(db, "PLANTA_VERIFICADA", "planta", id_planta, {"ok": r["ok"]}, ctx=ctx)
    db.commit()
    return r


# ---------------------------------------------------------------- troncales
@router.get("/troncales")
def troncales(ctx: Contexto = Depends(requiere("telefonia.ver")), db: Session = Depends(get_db)):
    return [a_dict(t, ["id_troncal", "id_planta", "nombre", "gateway", "proveedor", "max_canales", "activa"])
            for t in db.execute(select(TroncalSIP)).scalars()]


@router.post("/troncales", status_code=201)
def crear_troncal(datos: TroncalIn, ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    obtener_o_404(db, PlantaFreeswitch, datos.id_planta)
    t = TroncalSIP(**datos.model_dump())
    db.add(t)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe una troncal con ese nombre.")
    auditar(db, "TRONCAL_CREADA", "troncal", t.id_troncal, datos.model_dump(), ctx=ctx)
    db.commit()
    return {"id_troncal": t.id_troncal}


@router.post("/troncales/{id_troncal}/alternar")
def alternar_troncal(id_troncal: int, ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    t = obtener_o_404(db, TroncalSIP, id_troncal)
    t.activa = not t.activa
    auditar(db, "TRONCAL_ALTERNADA", "troncal", id_troncal, {"activa": t.activa}, ctx=ctx)
    db.commit()
    return {"activa": t.activa}


# ---------------------------------------------------------------- extensiones y canales
@router.get("/extensiones")
def extensiones(ctx: Contexto = Depends(requiere("telefonia.ver")), db: Session = Depends(get_db)):
    salida = []
    for e in db.execute(select(ExtensionSIP)).scalars():
        d = a_dict(e, ["id_extension", "id_planta", "id_troncal", "numero", "canales_max", "activa"])
        d["planta"] = e.planta.nombre
        d["troncal"] = e.troncal.nombre if e.troncal else None
        salida.append(d)
    return salida


@router.post("/extensiones", status_code=201)
def crear_extension(datos: ExtensionIn, ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    planta = obtener_o_404(db, PlantaFreeswitch, datos.id_planta)
    if datos.id_troncal:
        t = obtener_o_404(db, TroncalSIP, datos.id_troncal)
        if t.id_planta != planta.id_planta:
            raise HTTPException(422, "La troncal pertenece a otra planta.")
    actuales = db.execute(select(func.count(CanalConcurrente.id_canal)).join(ExtensionSIP)
                          .where(ExtensionSIP.id_planta == planta.id_planta)).scalar_one()
    if actuales + datos.canales_max > planta.capacidad_canales:
        raise HTTPException(422, f"Excede la capacidad de la planta ({planta.capacidad_canales} canales).")
    e = ExtensionSIP(**datos.model_dump())
    db.add(e)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La extensión ya existe en esa planta.")
    for _ in range(datos.canales_max):
        db.add(CanalConcurrente(id_extension=e.id_extension, estado="LIBRE"))
    auditar(db, "EXTENSION_CREADA", "extension", e.id_extension, datos.model_dump(), ctx=ctx)
    db.commit()
    return {"id_extension": e.id_extension}


@router.get("/canales")
def canales(ctx: Contexto = Depends(requiere("telefonia.ver")), db: Session = Depends(get_db)):
    return [{**a_dict(c, ["id_canal", "id_extension", "estado", "id_llamada", "ocupado_desde"]), "extension": c.extension.numero}
            for c in db.execute(select(CanalConcurrente).order_by(CanalConcurrente.id_canal)).scalars()]


@router.post("/canales/{id_canal}/liberar")
def liberar(id_canal: int, ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    c = obtener_o_404(db, CanalConcurrente, id_canal)
    if c.id_llamada:
        ll = db.get(Llamada, c.id_llamada)
        if ll and ll.estado_tecnico == "EN_CURSO":
            raise HTTPException(409, "El canal tiene una llamada en curso.")
    marcador.liberar_canal(db, id_canal)
    auditar(db, "CANAL_LIBERADO_MANUAL", "canal", id_canal, ctx=ctx)
    db.commit()
    return {"ok": True}


@router.post("/canales/recuperar")
def recuperar(ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    r = marcador.recuperar_tras_reinicio(db)
    auditar(db, "RECUPERACION_CANALES", "canal", None, r, ctx=ctx)
    db.commit()
    return r


# ---------------------------------------------------------------- números autorizados (piloto)
@router.get("/numeros-autorizados")
def numeros(ctx: Contexto = Depends(requiere("telefonia.ver")), db: Session = Depends(get_db)):
    return [{"id": n.id, "telefono": enmascarar_telefono(n.telefono), "descripcion": n.descripcion}
            for n in db.execute(select(NumeroAutorizado)).scalars()]


@router.post("/numeros-autorizados", status_code=201)
def crear_numero(datos: NumeroIn, ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    tel = normalizar_telefono(datos.telefono)
    if tel is None:
        raise HTTPException(422, "Teléfono inválido.")
    n = NumeroAutorizado(telefono=tel, descripcion=re.sub(r"[<>]", "", datos.descripcion), id_usuario=ctx.usuario.id_usuario)
    db.add(n)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "El número ya está autorizado.")
    auditar(db, "NUMERO_AUTORIZADO", "numero", n.id, {"telefono": enmascarar_telefono(tel)}, ctx=ctx)
    db.commit()
    return {"id": n.id}


@router.delete("/numeros-autorizados/{id_numero}")
def borrar_numero(id_numero: int, ctx: Contexto = Depends(requiere("telefonia.gestionar")), db: Session = Depends(get_db)):
    n = obtener_o_404(db, NumeroAutorizado, id_numero)
    db.delete(n)
    auditar(db, "NUMERO_DESAUTORIZADO", "numero", id_numero, ctx=ctx)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- llamada a extensión interna (Zoiper)
@router.get("/extensiones-internas")
def extensiones_internas(ctx: Contexto = Depends(requiere("prueba.ejecutar")), db: Session = Depends(get_db)):
    """Extensiones sin troncal: teléfonos SIP (Zoiper) registrados en FreeSWITCH. Solo estas pueden recibir la prueba."""
    s = get_settings()
    lista = [{"id_extension": e.id_extension, "numero": e.numero, "planta": e.planta.nombre, "ip": e.planta.ip,
              "estado_planta": e.planta.estado}
             for e in db.execute(select(ExtensionSIP).where(ExtensionSIP.id_troncal.is_(None), ExtensionSIP.activa.is_(True))
                                 .order_by(ExtensionSIP.numero)).scalars() if e.planta.activa]
    faltan = []
    if not s.telefonia_habilitada:
        faltan.append("TELEFONIA_HABILITADA=true")
    if not s.freeswitch_esl_password:
        faltan.append("FREESWITCH_ESL_PASSWORD (clave del Event Socket de la VM)")
    if not s.freeswitch_dir_audio:
        faltan.append("FREESWITCH_DIR_AUDIO (carpeta compartida con la VM)")
    if not s.deepgram_api_key:
        faltan.append("DEEPGRAM_API_KEY (voz del agente y reconocimiento)")
    return {"faltan": faltan, "extensiones": lista}


@router.post("/llamar-extension", status_code=201)
def llamar_extension(datos: LlamarExtensionIn, ctx: Contexto = Depends(requiere("prueba.ejecutar")),
                     db: Session = Depends(get_db)):
    if parametros.pausa_activa(db):
        raise HTTPException(423, "Pausa de emergencia activa: no se originan llamadas.")
    faltan = extensiones_internas(ctx, db)["faltan"]
    if faltan:
        raise HTTPException(409, "Falta configurar en backend\\.env: " + ", ".join(faltan))
    ext = obtener_o_404(db, ExtensionSIP, datos.id_extension)
    if ext.id_troncal is not None or not ext.activa or not ext.planta.activa:
        raise HTTPException(403, "Solo se puede llamar a extensiones internas activas (sin troncal).")
    activas = db.execute(select(func.count(Llamada.id_llamada)).where(Llamada.canal == "TELEFONIA",
                                                                      Llamada.estado_tecnico == "EN_CURSO")).scalar_one()
    if activas >= int(parametros.obtener(db, "max_canales_piloto")):
        raise HTTPException(409, "Ya hay una llamada telefónica en curso (límite del piloto).")
    ag = obtener_o_404(db, AgenteIA, datos.id_agente)
    deuda = obtener_o_404(db, Deuda, datos.id_deuda)
    try:
        ll = motor.iniciar(db, agente=ag, cliente=deuda.cliente, deuda=deuda, canal="TELEFONIA", modo="PRUEBA",
                           id_usuario=ctx.usuario.id_usuario)
    except motor.ErrorConversacion as e:
        raise HTTPException(409, str(e))
    ll.destino_enmascarado = f"Ext. {ext.numero}"
    db.flush()
    db.add(Trabajo(tipo="LLAMAR_EXTENSION", payload={"id_llamada": ll.id_llamada, "id_extension": ext.id_extension},
                   clave_idempotencia=f"LLAMAR_EXTENSION:{ll.id_llamada}", max_intentos=1))
    db.add(PruebaLlamada(id_agente=ag.id_agente, id_llamada=ll.id_llamada, tipo="TELEFONIA", resultado="SOLICITADA",
                         detalle=f"FreeSWITCH ext. {ext.numero}"))
    auditar(db, "LLAMADA_EXTENSION_PRUEBA", "llamada", ll.id_llamada, {"extension": ext.numero, "planta": ext.planta.nombre},
            ctx=ctx)
    db.commit()
    return {"id_llamada": ll.id_llamada, "estado": "Llamando a la extensión…"}
