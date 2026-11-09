"""Llamada real de prueba con Twilio: inicio desde la interfaz y webhooks de Twilio (firmados)."""
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import parametros
from ..auditoria import auditar
from ..db import get_db
from ..ia import agente as motor
from ..models import AgenteIA, Deuda, EventoLlamada, Llamada, NumeroAutorizado, PruebaLlamada, ahora_utc
from ..security import Contexto, requiere
from ..telefonia import twilio
from ..telefonia.marcador import registrar_evento
from ..config import get_settings
from ..ia.proveedor import ErrorProveedor
from ..utils import enmascarar_telefono, normalizar_telefono
from ..voz import deepgram
from .comun import obtener_o_404

router = APIRouter(prefix="/api/twilio", tags=["Twilio"])
XML = "application/xml"


class LlamarIn(BaseModel):
    id_agente: int
    id_deuda: int
    telefono: str = Field(max_length=30)


@router.get("/estado-configuracion")
def estado_configuracion(ctx: Contexto = Depends(requiere("prueba.ejecutar")), db: Session = Depends(get_db)):
    numeros = [{"id": n.id, "telefono": enmascarar_telefono(n.telefono), "descripcion": n.descripcion}
               for n in db.execute(select(NumeroAutorizado)).scalars()]
    return {"faltan": twilio.configurado(), "numeros_autorizados": numeros}


@router.post("/llamar", status_code=201)
def llamar(datos: LlamarIn, ctx: Contexto = Depends(requiere("prueba.ejecutar")), db: Session = Depends(get_db)):
    if parametros.pausa_activa(db):
        raise HTTPException(423, "Pausa de emergencia activa: no se originan llamadas.")
    faltan = twilio.configurado()
    if faltan:
        raise HTTPException(409, "Falta configurar en backend\\.env: " + ", ".join(faltan))
    tel = normalizar_telefono(datos.telefono)
    if tel is None:
        raise HTTPException(422, "Teléfono inválido (use un número de Guatemala de 8 dígitos).")
    if db.execute(select(NumeroAutorizado.id).where(NumeroAutorizado.telefono == tel)).first() is None:
        raise HTTPException(403, "Ese número no está autorizado. Agréguelo en Extensiones SIP › Números autorizados.")
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
    ll.destino_enmascarado = enmascarar_telefono(tel)
    db.commit()
    try:
        sid = twilio.iniciar_llamada(tel, ll.id_llamada)
    except twilio.ErrorTwilio as e:
        ll.estado_tecnico, ll.fin, ll.motivo_fallo = "FALLIDA", ahora_utc(), str(e)[:255]
        db.commit()
        raise HTTPException(502, str(e))
    ll.uuid_freeswitch = sid  # identificador de la llamada en el proveedor (CallSid)
    registrar_evento(db, ll, "LLAMADA_SOLICITADA", f"{sid}:SOLICITADA", {"proveedor": "twilio"})
    db.add(PruebaLlamada(id_agente=ag.id_agente, id_llamada=ll.id_llamada, tipo="TELEFONIA", resultado="SOLICITADA",
                         detalle="Twilio"))
    auditar(db, "LLAMADA_REAL_PRUEBA", "llamada", ll.id_llamada, {"destino": enmascarar_telefono(tel), "proveedor": "twilio"},
            ctx=ctx)
    db.commit()
    return {"id_llamada": ll.id_llamada, "estado": "Llamando…"}


def _decir(db: Session, ll: Llamada, texto: str) -> str:
    """Lo que dice el agente, con su voz Deepgram y su velocidad; si Deepgram falla, con la voz de Twilio."""
    vel = float(ll.agente.velocidad_voz or 1)
    s = get_settings()
    if s.twilio_motor_voz == "deepgram" and s.deepgram_api_key:
        try:
            a = deepgram.tts(db, texto, ll.agente.voz_deepgram, id_llamada=ll.id_llamada, velocidad=vel)
            return twilio.habla(texto, token_audio=twilio.guardar_audio(a.audio, a.mime))
        except ErrorProveedor as e:
            registrar_evento(db, ll, "TTS_RESPALDO", f"TTS:{time.time_ns()}", {"codigo": e.codigo})
    return twilio.habla(texto, vel)


async def _formulario_firmado(request: Request, ruta: str) -> dict:
    form = dict((await request.form()).items())
    if not twilio.firma_valida(twilio.url_publica(ruta), form, request.headers.get("X-Twilio-Signature", "")):
        raise HTTPException(403, "Firma de Twilio inválida.")
    return form


@router.post("/voz/{id_llamada}")
async def voz(id_llamada: int, request: Request, db: Session = Depends(get_db)):
    form = await _formulario_firmado(request, f"/api/twilio/voz/{id_llamada}")
    ll = db.get(Llamada, id_llamada)
    if ll is None or ll.estado_tecnico != "EN_CURSO" or ll.canal != "TELEFONIA":
        return Response(twilio.twiml_hablar_y_colgar(twilio.habla("Gracias. Hasta luego.")), media_type=XML)
    sid = form.get("CallSid", "")
    if registrar_evento(db, ll, "CONTESTADA", f"{sid}:SALUDO"):
        xml = twilio.twiml_hablar_y_escuchar(_decir(db, ll, motor.saludo_inicial(ll.agente, ll.cliente)), id_llamada)
        db.commit()
        return Response(xml, media_type=XML)
    texto = (form.get("SpeechResult") or "").strip()
    if not texto:
        silencios = db.execute(select(func.count(EventoLlamada.id)).where(
            EventoLlamada.id_llamada == id_llamada, EventoLlamada.tipo == "SILENCIO")).scalar_one()
        registrar_evento(db, ll, "SILENCIO", f"{sid}:SILENCIO:{silencios + 1}")
        if silencios + 1 >= 2:
            motor._agregar_turno(db, ll, "AGENTE", "No logro escucharle. Le llamaremos en otro momento.")
            motor._cerrar(db, ll, "SIN_RESULTADO")
            xml = twilio.twiml_hablar_y_colgar(
                _decir(db, ll, "No logro escucharle. Le llamaremos en otro momento. Que tenga buen día."))
        else:
            xml = twilio.twiml_hablar_y_escuchar(
                _decir(db, ll, "¿Me escucha? Por favor, responda después del mensaje."), id_llamada)
        db.commit()
        return Response(xml, media_type=XML)
    try:
        confianza = float(form.get("Confidence")) if form.get("Confidence") else None
    except ValueError:
        confianza = None
    try:
        r = motor.procesar_mensaje(db, ll, texto, confianza_stt=confianza)
    except motor.ErrorConversacion:
        return Response(twilio.twiml_hablar_y_colgar(twilio.habla("Gracias por su tiempo.")), media_type=XML)
    if r["finalizada"]:
        xml = twilio.twiml_hablar_y_colgar(_decir(db, ll, r["respuesta"]))
    else:
        xml = twilio.twiml_hablar_y_escuchar(_decir(db, ll, r["respuesta"]), id_llamada)
    db.commit()
    return Response(xml, media_type=XML)


@router.get("/audio/{token}")
def audio(token: str):
    """Audio Deepgram de un turno para <Play>. El token es aleatorio, de un solo turno, y expira en 5 minutos."""
    a = twilio.obtener_audio(token)
    if a is None:
        raise HTTPException(404, "Audio no disponible.")
    return Response(a[0], media_type=a[1], headers={"Cache-Control": "no-store"})


@router.post("/estado/{id_llamada}")
async def estado(id_llamada: int, request: Request, db: Session = Depends(get_db)):
    form = await _formulario_firmado(request, f"/api/twilio/estado/{id_llamada}")
    ll = db.get(Llamada, id_llamada)
    if ll is None:
        return Response(status_code=204)
    estado_tw = form.get("CallStatus", "")
    sid = form.get("CallSid", "")
    registrar_evento(db, ll, f"TWILIO_{estado_tw.upper()}"[:40], f"{sid}:{estado_tw}",
                     {"duracion": form.get("CallDuration")})
    if estado_tw in ("completed", "no-answer", "busy", "failed", "canceled") and ll.estado_tecnico == "EN_CURSO":
        tecnico, contacto = twilio.clasificar_estado(estado_tw)
        if estado_tw == "completed":
            motor._cerrar(db, ll, "SIN_RESULTADO")
        else:
            ll.estado_tecnico, ll.resultado_contacto, ll.fin = tecnico, contacto, ahora_utc()
            ll.resultado_cobranza, ll.motivo_fallo = "SIN_RESULTADO", estado_tw
    db.commit()
    return Response(status_code=204)
