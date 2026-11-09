"""Seguimiento de promesas (CU-17). Una promesa no es un pago: el cumplimiento lo registra un usuario autorizado."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auditoria import auditar
from ..models import ClienteCampana, PromesaPago, SeguimientoPromesa, ahora_utc
from ..utils import hoy_local


def marcar_cumplida(db: Session, p: PromesaPago, id_usuario: int, observacion: str | None, ctx=None) -> None:
    if p.estado != "PENDIENTE" and p.estado != "INCUMPLIDA":
        raise ValueError(f"No se puede marcar como cumplida una promesa en estado {p.estado}.")
    anterior = p.estado
    p.estado, p.id_usuario_cumplimiento, p.fecha_cumplimiento = "CUMPLIDA", id_usuario, ahora_utc()
    p.observacion = (observacion or "")[:255] or None
    db.add(SeguimientoPromesa(id_promesa=p.id_promesa, resultado="CUMPLIDA_MANUAL", reingreso_campana=False,
                              observacion=p.observacion, id_usuario=id_usuario))
    if p.id_cliente_campana:
        cc = db.get(ClienteCampana, p.id_cliente_campana)
        if cc:
            cc.estado_gestion = "CERRADO"
    auditar(db, "PROMESA_CUMPLIDA_MANUAL", "promesa", p.id_promesa, {"anterior": anterior, "observacion": observacion}, ctx=ctx,
            id_usuario=id_usuario)


def cancelar(db: Session, p: PromesaPago, id_usuario: int, observacion: str, ctx=None) -> None:
    if p.estado != "PENDIENTE":
        raise ValueError("Solo se pueden cancelar promesas pendientes.")
    p.estado, p.observacion = "CANCELADA", observacion[:255]
    db.add(SeguimientoPromesa(id_promesa=p.id_promesa, resultado="CANCELADA", observacion=observacion[:255],
                              id_usuario=id_usuario))
    auditar(db, "PROMESA_CANCELADA", "promesa", p.id_promesa, {"observacion": observacion}, ctx=ctx, id_usuario=id_usuario)


def revisar_vencidas(db: Session) -> dict:
    """Marca INCUMPLIDA las promesas vencidas y reingresa a campaña (el reingreso respeta todas las reglas al encolar)."""
    hoy = hoy_local()
    vencidas = db.execute(select(PromesaPago).where(PromesaPago.estado == "PENDIENTE",
                                                    PromesaPago.fecha_compromiso < hoy)).scalars().all()
    reingresos = 0
    for p in vencidas:
        p.estado = "INCUMPLIDA"
        reingreso = False
        if p.id_cliente_campana:
            cc = db.get(ClienteCampana, p.id_cliente_campana)
            if cc and cc.campana.estado in ("ACTIVA", "PAUSADA") and cc.estado_gestion == "PROMESA":
                cc.estado_gestion = "PENDIENTE"
                reingreso = True
                reingresos += 1
        db.add(SeguimientoPromesa(id_promesa=p.id_promesa, resultado="INCUMPLIDA_AUTOMATICA", reingreso_campana=reingreso))
    return {"vencidas": len(vencidas), "reingresos": reingresos}
