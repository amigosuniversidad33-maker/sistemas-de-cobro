"""Módulo Prueba de Llamada (DS-07, CU-20, CU-21): conversación real por texto y por voz en navegador.

Una conversación por voz en el navegador NO equivale a una llamada telefónica; se identifica como canal VOZ_NAVEGADOR.
"""
import base64

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import parametros
from ..auditoria import auditar
from ..config import get_settings
from ..db import get_db
from ..ia import agente as motor
from ..ia.proveedor import ErrorProveedor, descripcion_proveedor
from ..models import AgenteIA, Deuda, Llamada, PruebaLlamada, TurnoConversacion
from ..security import Contexto, requiere
from ..voz import deepgram, grabaciones
from .comun import Paginacion, a_dict, obtener_o_404, paginar

router = APIRouter(prefix="/api", tags=["Prueba de Llamada"])


class IniciarIn(BaseModel):
    id_agente: int
    id_deuda: int
    canal: str = Field(default="TEXTO", pattern="^(TEXTO|VOZ_NAVEGADOR)$")


class MensajeIn(BaseModel):
    texto: str = Field(min_length=1, max_length=1000)


class TTSIn(BaseModel):
    texto: str = Field(min_length=2, max_length=500)
    voz: str = Field(pattern=r"^aura-2-[a-z]+-es$")
    id_agente: int | None = None


def _llamada_propia(db: Session, ctx: Contexto, id_llamada: int) -> Llamada:
    ll = obtener_o_404(db, Llamada, id_llamada)
    if ll.canal == "TELEFONIA" or (ll.id_usuario != ctx.usuario.id_usuario and not ctx.tiene("sistema.configurar")):
        raise HTTPException(404, "Registro no encontrado.")
    return ll


def ser_turnos(db: Session, id_llamada: int) -> list[dict]:
    return [a_dict(t, ["orden", "rol", "texto", "bloqueado", "confianza_stt", "fecha"]) for t in db.execute(
        select(TurnoConversacion).where(TurnoConversacion.id_llamada == id_llamada).order_by(TurnoConversacion.orden)).scalars()]


@router.post("/conversaciones", status_code=201)
def iniciar(datos: IniciarIn, ctx: Contexto = Depends(requiere("prueba.ejecutar")), db: Session = Depends(get_db)):
    if parametros.pausa_activa(db):
        raise HTTPException(423, "Pausa de emergencia activa: no se inician nuevas conversaciones.")
    ag = obtener_o_404(db, AgenteIA, datos.id_agente)
    deuda = obtener_o_404(db, Deuda, datos.id_deuda)
    try:
        ll = motor.iniciar(db, agente=ag, cliente=deuda.cliente, deuda=deuda, canal=datos.canal, modo="PRUEBA",
                           id_usuario=ctx.usuario.id_usuario)
    except motor.ErrorConversacion as e:
        raise HTTPException(409, str(e))
    db.add(PruebaLlamada(id_agente=ag.id_agente, id_llamada=ll.id_llamada, tipo=datos.canal, resultado="INICIADA"))
    auditar(db, "PRUEBA_INICIADA", "llamada", ll.id_llamada, {"canal": datos.canal}, ctx=ctx)
    db.commit()
    return {"id_llamada": ll.id_llamada, "canal": ll.canal, "modo": ll.modo, "agente": ag.nombre,
            "voz": ag.voz_deepgram, "velocidad_voz": float(ag.velocidad_voz or 1), "turnos": ser_turnos(db, ll.id_llamada), **config_voz()}


def config_voz() -> dict:
    ia = descripcion_proveedor()
    return {"deepgram": bool(get_settings().deepgram_api_key), "proveedor_ia": ia["proveedor"], "etiqueta_ia": ia["etiqueta"]}


@router.get("/voz/config")
def voz_config(ctx: Contexto = Depends(requiere("prueba.ejecutar"))):
    return config_voz()


@router.get("/conversaciones/{id_llamada}")
def obtener(id_llamada: int, ctx: Contexto = Depends(requiere("prueba.ejecutar")), db: Session = Depends(get_db)):
    ll = _llamada_propia(db, ctx, id_llamada)
    return {**a_dict(ll, ["id_llamada", "canal", "modo", "estado_tecnico", "resultado_contacto", "resultado_cobranza",
                          "identidad_verificada", "bloqueos_guardrail", "promesa_propuesta", "costo_estimado_usd"]),
            "turnos": ser_turnos(db, id_llamada)}


@router.post("/conversaciones/{id_llamada}/mensajes")
def mensaje(id_llamada: int, datos: MensajeIn, ctx: Contexto = Depends(requiere("prueba.ejecutar")),
            db: Session = Depends(get_db)):
    ll = _llamada_propia(db, ctx, id_llamada)
    try:
        r = motor.procesar_mensaje(db, ll, datos.texto)
    except motor.ErrorConversacion as e:
        raise HTTPException(409, str(e))
    db.commit()
    return r


@router.post("/conversaciones/{id_llamada}/voz")
async def mensaje_voz(id_llamada: int, audio: UploadFile = File(...), ctx: Contexto = Depends(requiere("prueba.ejecutar")),
                      db: Session = Depends(get_db)):
    """Turno de voz: audio del navegador -> Deepgram STT -> agente + guardrails -> Deepgram TTS -> audio."""
    s = get_settings()
    ll = _llamada_propia(db, ctx, id_llamada)
    if ll.estado_tecnico != "EN_CURSO":
        raise HTTPException(409, "La conversación ya finalizó.")
    contenido = await audio.read(s.voz_max_audio_mb * 1024 * 1024 + 1)
    if len(contenido) > s.voz_max_audio_mb * 1024 * 1024:
        raise HTTPException(413, "Audio demasiado grande.")
    if len(contenido) < 200:
        raise HTTPException(422, "Audio vacío.")
    try:
        res_stt = deepgram.stt(db, contenido, audio.content_type or "audio/webm", ll.id_llamada)
    except ErrorProveedor as e:
        db.commit()
        raise HTTPException(502, f"No se pudo transcribir con Deepgram ({e.codigo}). No se usó ninguna simulación.")
    grabaciones.guardar(db, ll.id_llamada, contenido, audio.content_type or "audio/webm")
    if not res_stt.texto:
        db.commit()
        return {"transcripcion": "", "silencio": True, "respuesta": None, "audio": None, "finalizada": False,
                "latencia_stt_ms": res_stt.latencia_ms}
    try:
        r = motor.procesar_mensaje(db, ll, res_stt.texto, confianza_stt=res_stt.confianza)
    except motor.ErrorConversacion as e:
        raise HTTPException(409, str(e))
    db.commit()
    audio_b64, mime, lat_tts, error_tts = None, None, None, None
    try:
        tts = deepgram.tts(db, r["respuesta"], ll.agente.voz_deepgram, id_llamada=ll.id_llamada)
        audio_b64, mime, lat_tts = base64.b64encode(tts.audio).decode(), tts.mime, tts.latencia_ms
    except ErrorProveedor as e:
        error_tts = f"Deepgram TTS no disponible ({e.codigo}); se muestra solo el texto."
    db.add(PruebaLlamada(id_agente=ll.id_agente, id_llamada=ll.id_llamada, tipo="VOZ_NAVEGADOR",
                         resultado="TURNO_OK" if audio_b64 else "TTS_FALLIDO",
                         latencia_ms=res_stt.latencia_ms + (lat_tts or 0),
                         calidad_voz=round(res_stt.confianza * 100, 2) if res_stt.confianza is not None else None))
    db.commit()
    return {**r, "transcripcion": res_stt.texto, "confianza_stt": res_stt.confianza, "audio": audio_b64, "mime": mime,
            "latencia_stt_ms": res_stt.latencia_ms, "latencia_tts_ms": lat_tts, "error_tts": error_tts}


@router.post("/conversaciones/{id_llamada}/finalizar")
def finalizar(id_llamada: int, ctx: Contexto = Depends(requiere("prueba.ejecutar")), db: Session = Depends(get_db)):
    ll = _llamada_propia(db, ctx, id_llamada)
    if ll.estado_tecnico == "EN_CURSO":
        motor.cerrar_manual(db, ll)
    db.commit()
    return {"ok": True, "estado_tecnico": ll.estado_tecnico}


@router.post("/voz/tts-prueba")
def tts_prueba(datos: TTSIn, ctx: Contexto = Depends(requiere("prueba.ejecutar")), db: Session = Depends(get_db)):
    """CU-21: valida calidad y latencia de la voz Deepgram."""
    try:
        r = deepgram.tts(db, datos.texto, datos.voz)
    except ErrorProveedor as e:
        db.add(PruebaLlamada(id_agente=datos.id_agente, tipo="TTS", resultado=f"ERROR_{e.codigo}"[:30]))
        db.commit()
        raise HTTPException(502, f"Deepgram TTS no disponible ({e.codigo}).")
    db.add(PruebaLlamada(id_agente=datos.id_agente, tipo="TTS", resultado="OK", latencia_ms=r.latencia_ms,
                         detalle=f"voz={datos.voz}, {len(datos.texto)} caracteres"))
    db.commit()
    return {"audio": base64.b64encode(r.audio).decode(), "mime": r.mime, "latencia_ms": r.latencia_ms}


@router.get("/pruebas")
def pruebas(pag: Paginacion = Depends(), ctx: Contexto = Depends(requiere("prueba.ejecutar")), db: Session = Depends(get_db)):
    return paginar(db, select(PruebaLlamada).order_by(PruebaLlamada.id_prueba.desc()), pag,
                   lambda p: a_dict(p, ["id_prueba", "id_agente", "id_llamada", "tipo", "resultado", "calidad_voz",
                                        "latencia_ms", "detalle", "fecha"]))
