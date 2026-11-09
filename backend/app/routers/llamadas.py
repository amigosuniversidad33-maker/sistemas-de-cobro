"""Módulos Llamadas (HU-08, CU-09 a CU-11), QA / Análisis (CU-22, CU-23) y Promesas de Pago (CU-16, CU-17)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auditoria import auditar
from ..db import get_db
from ..ia import supervisores
from ..ia.proveedor import ErrorProveedor
from ..models import (
    Campana,
    EvaluacionQA,
    EventoLlamada,
    Grabacion,
    Llamada,
    PromesaPago,
    SeguimientoPromesa,
    TramoMora,
)
from ..security import Contexto, campanas_permitidas, requiere, verificar_campana
from ..servicios import promesas as srv_promesas
from ..voz import grabaciones
from .comun import Paginacion, a_dict, csv_respuesta, obtener_o_404, paginar, rango_fechas
from .conversaciones import ser_turnos

router = APIRouter(prefix="/api", tags=["Llamadas, QA y Promesas"])
CAMPOS_LLAMADA = ["id_llamada", "canal", "modo", "id_campana", "id_cliente", "id_agente", "estado_tecnico",
                  "resultado_contacto", "resultado_cobranza", "identidad_verificada", "bloqueos_guardrail", "duracion_seg",
                  "destino_enmascarado", "motivo_fallo", "version_guion", "version_politica", "costo_estimado_usd", "inicio", "fin"]


class RevisionIn(BaseModel):
    puntaje_humano: float = Field(ge=0, le=100)
    observacion: str = Field(min_length=3, max_length=500)


class CumplimientoIn(BaseModel):
    observacion: str | None = Field(default=None, max_length=255)


class CancelarIn(BaseModel):
    observacion: str = Field(min_length=3, max_length=255)


def _filtro_alcance(db, ctx, q, columna):
    permitidas = campanas_permitidas(db, ctx)
    if permitidas is not None:
        q = q.where(or_(columna.in_(permitidas or [-1]), columna.is_(None) if ctx.tiene("prueba.ejecutar") else False))
    return q


def ser_llamada(ll: Llamada) -> dict:
    d = a_dict(ll, CAMPOS_LLAMADA)
    d["cliente"] = ll.cliente.nombre if ll.cliente else None
    d["agente"] = ll.agente.nombre if ll.agente else None
    d["campana"] = ll.campana.nombre if ll.campana else None
    return d


def _consulta_llamadas(db, ctx, id_campana, desde, hasta, estado, canal, resultado, tramo, modo):
    q = select(Llamada).order_by(Llamada.inicio.desc())
    q = _filtro_alcance(db, ctx, q, Llamada.id_campana)
    if id_campana:
        q = q.where(Llamada.id_campana == id_campana)
    d, h = rango_fechas(desde, hasta)
    if d:
        q = q.where(Llamada.inicio >= d)
    if h:
        q = q.where(Llamada.inicio < h)
    if estado:
        q = q.where(Llamada.estado_tecnico == estado)
    if canal:
        q = q.where(Llamada.canal == canal)
    if modo:
        q = q.where(Llamada.modo == modo)
    if resultado:
        q = q.where(Llamada.resultado_contacto == resultado)
    if tramo:
        q = q.join(Campana, Campana.id_campana == Llamada.id_campana).join(TramoMora).where(TramoMora.codigo == tramo)
    return q


@router.get("/llamadas")
def listar(id_campana: int | None = None, desde: date | None = None, hasta: date | None = None, estado: str | None = None,
           canal: str | None = None, resultado: str | None = None, tramo: str | None = None, modo: str | None = None,
           pag: Paginacion = Depends(), ctx: Contexto = Depends(requiere("llamadas.ver")), db: Session = Depends(get_db)):
    q = _consulta_llamadas(db, ctx, id_campana, desde, hasta, estado, canal, resultado, tramo, modo)
    return paginar(db, q, pag, ser_llamada)


@router.get("/llamadas/exportar.csv")
def exportar(id_campana: int | None = None, desde: date | None = None, hasta: date | None = None,
             ctx: Contexto = Depends(requiere("llamadas.ver", "clientes.exportar")), db: Session = Depends(get_db)):
    filas = db.execute(_consulta_llamadas(db, ctx, id_campana, desde, hasta, None, None, None, None, None).limit(50000)).scalars().all()
    auditar(db, "EXPORTACION_LLAMADAS", "llamada", None, {"filas": len(filas)}, ctx=ctx)
    db.commit()
    return csv_respuesta("llamadas.csv", CAMPOS_LLAMADA, [[a_dict(ll, CAMPOS_LLAMADA)[c] for c in CAMPOS_LLAMADA] for ll in filas])


@router.get("/llamadas/{id_llamada}")
def detalle(id_llamada: int, ctx: Contexto = Depends(requiere("llamadas.ver")), db: Session = Depends(get_db)):
    ll = obtener_o_404(db, Llamada, id_llamada)
    if ll.id_campana is not None:
        verificar_campana(db, ctx, ll.id_campana)
    elif not ctx.tiene("campanas.todas") and ll.id_usuario != ctx.usuario.id_usuario:
        raise HTTPException(404, "Registro no encontrado.")
    d = ser_llamada(ll)
    d["turnos"] = ser_turnos(db, id_llamada)
    d["eventos"] = [a_dict(e, ["tipo", "clave_evento", "datos", "fecha_evento"]) for e in db.execute(
        select(EventoLlamada).where(EventoLlamada.id_llamada == id_llamada).order_by(EventoLlamada.id)).scalars()]
    d["grabaciones"] = [a_dict(g, ["id_grabacion", "formato", "cifrada", "fecha"]) for g in db.execute(
        select(Grabacion).where(Grabacion.id_llamada == id_llamada)).scalars()] if ctx.tiene("grabaciones.ver") else []
    d["evaluaciones_qa"] = [ser_qa(e) for e in db.execute(select(EvaluacionQA).where(EvaluacionQA.id_llamada == id_llamada)).scalars()]
    d["promesa"] = next((ser_promesa(p) for p in db.execute(select(PromesaPago).where(PromesaPago.id_llamada == id_llamada)).scalars()), None)
    return d


@router.get("/grabaciones/{id_grabacion}/audio")
def audio(id_grabacion: int, ctx: Contexto = Depends(requiere("grabaciones.ver")), db: Session = Depends(get_db)):
    g = obtener_o_404(db, Grabacion, id_grabacion)
    ll = db.get(Llamada, g.id_llamada)
    if ll.id_campana is not None:
        verificar_campana(db, ctx, ll.id_campana)
    try:
        datos = grabaciones.leer(g)
    except (PermissionError, FileNotFoundError) as e:
        raise HTTPException(404, str(e))
    auditar(db, "GRABACION_ESCUCHADA", "grabacion", id_grabacion, {"id_llamada": g.id_llamada}, ctx=ctx)
    db.commit()
    return Response(datos, media_type=g.formato.split(";")[0], headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- QA
def ser_qa(e: EvaluacionQA) -> dict:
    return a_dict(e, ["id_qa", "id_llamada", "puntaje", "cumple_guion", "trato_adecuado", "confirmacion_correcta",
                      "compromisos_fuera_politica", "incertidumbre", "hallazgos", "resumen", "proveedor", "modelo",
                      "version_prompt", "estado_revision", "puntaje_humano", "observacion", "fecha"])


@router.get("/qa")
def qa_listar(estado_revision: str | None = None, pag: Paginacion = Depends(), ctx: Contexto = Depends(requiere("qa.ver")),
              db: Session = Depends(get_db)):
    q = select(EvaluacionQA).join(Llamada, Llamada.id_llamada == EvaluacionQA.id_llamada).order_by(EvaluacionQA.id_qa.desc())
    q = _filtro_alcance(db, ctx, q, Llamada.id_campana)
    if estado_revision:
        q = q.where(EvaluacionQA.estado_revision == estado_revision)
    return paginar(db, q, pag, ser_qa)


@router.post("/qa/evaluar/{id_llamada}")
def qa_evaluar(id_llamada: int, ctx: Contexto = Depends(requiere("qa.revisar")), db: Session = Depends(get_db)):
    ll = obtener_o_404(db, Llamada, id_llamada)
    if ll.id_campana is not None:
        verificar_campana(db, ctx, ll.id_campana)
    if ll.estado_tecnico == "EN_CURSO":
        raise HTTPException(409, "La llamada sigue en curso.")
    try:
        ev = supervisores.evaluar_llamada(db, id_llamada)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except ErrorProveedor as e:
        db.commit()
        raise HTTPException(502, f"Supervisor IA no disponible ({e.codigo}). No se generó una evaluación inventada.")
    auditar(db, "QA_EVALUADA", "qa", ev.id_qa, {"id_llamada": id_llamada}, ctx=ctx)
    db.commit()
    return ser_qa(ev)


@router.post("/qa/{id_qa}/revisar")
def qa_revisar(id_qa: int, datos: RevisionIn, ctx: Contexto = Depends(requiere("qa.revisar")), db: Session = Depends(get_db)):
    ev = obtener_o_404(db, EvaluacionQA, id_qa)
    ev.estado_revision, ev.revisado_por = "REVISADA", ctx.usuario.id_usuario
    ev.puntaje_humano, ev.observacion = datos.puntaje_humano, datos.observacion
    auditar(db, "QA_REVISION_HUMANA", "qa", id_qa, datos.model_dump(), ctx=ctx)
    db.commit()
    return ser_qa(ev)


# ---------------------------------------------------------------- promesas
def ser_promesa(p: PromesaPago) -> dict:
    d = a_dict(p, ["id_promesa", "id_cliente", "id_deuda", "id_campana", "id_llamada", "monto", "moneda", "fecha_compromiso",
                   "estado", "frase_confirmacion", "confirmada_en", "fecha_cumplimiento", "observacion"])
    d["cliente"] = p.cliente.nombre
    d["referencia"] = p.deuda.referencia
    d["campana"] = p.campana.nombre if p.campana else None
    return d


@router.get("/promesas")
def promesas(estado: str | None = None, desde: date | None = None, hasta: date | None = None, pag: Paginacion = Depends(),
             ctx: Contexto = Depends(requiere("promesas.ver")), db: Session = Depends(get_db)):
    q = _filtro_alcance(db, ctx, select(PromesaPago).order_by(PromesaPago.fecha_compromiso), PromesaPago.id_campana)
    if estado:
        q = q.where(PromesaPago.estado == estado)
    if desde:
        q = q.where(PromesaPago.fecha_compromiso >= desde)
    if hasta:
        q = q.where(PromesaPago.fecha_compromiso <= hasta)
    return paginar(db, q, pag, ser_promesa)


@router.get("/promesas/{id_promesa}/seguimiento")
def seguimiento(id_promesa: int, ctx: Contexto = Depends(requiere("promesas.ver")), db: Session = Depends(get_db)):
    p = obtener_o_404(db, PromesaPago, id_promesa)
    if p.id_campana:
        verificar_campana(db, ctx, p.id_campana)
    return [a_dict(s, ["id", "resultado", "reingreso_campana", "observacion", "fecha_revision"]) for s in db.execute(
        select(SeguimientoPromesa).where(SeguimientoPromesa.id_promesa == id_promesa).order_by(SeguimientoPromesa.id)).scalars()]


@router.post("/promesas/{id_promesa}/cumplida")
def cumplida(id_promesa: int, datos: CumplimientoIn, ctx: Contexto = Depends(requiere("promesas.gestionar")),
             db: Session = Depends(get_db)):
    p = obtener_o_404(db, PromesaPago, id_promesa)
    if p.id_campana:
        verificar_campana(db, ctx, p.id_campana, para_gestion=True)
    try:
        srv_promesas.marcar_cumplida(db, p, ctx.usuario.id_usuario, datos.observacion, ctx=ctx)
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return ser_promesa(p)


@router.post("/promesas/{id_promesa}/cancelar")
def cancelar(id_promesa: int, datos: CancelarIn, ctx: Contexto = Depends(requiere("promesas.gestionar")),
             db: Session = Depends(get_db)):
    p = obtener_o_404(db, PromesaPago, id_promesa)
    if p.id_campana:
        verificar_campana(db, ctx, p.id_campana, para_gestion=True)
    try:
        srv_promesas.cancelar(db, p, ctx.usuario.id_usuario, datos.observacion, ctx=ctx)
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.commit()
    return ser_promesa(p)


@router.post("/promesas/revisar-vencidas")
def revisar_vencidas(ctx: Contexto = Depends(requiere("promesas.gestionar", "campanas.todas")), db: Session = Depends(get_db)):
    r = srv_promesas.revisar_vencidas(db)
    auditar(db, "REVISION_PROMESAS_VENCIDAS", "promesa", None, r, ctx=ctx)
    db.commit()
    return r
