"""Reglas previas a la marcación (DS-09, DF-04). Se ejecutan al ENCOLAR y otra vez antes de ORIGINAR."""
from datetime import date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import parametros
from ..models import ClienteCampana, Llamada, NoContactable, PromesaPago, Trabajo, ahora_utc
from ..utils import dentro_de_ventana, hoy_local, inicio_dia_local_en_utc
from . import consumo

ESTADOS_FINALES_CC = {"EXCLUIDO", "AGOTADO", "CERRADO", "PROMESA", "PAGO_REPORTADO"}


def esta_excluido(db: Session, id_cliente: int, telefono: str | None) -> bool:
    cond = [NoContactable.id_cliente == id_cliente]
    if telefono:
        cond.append(NoContactable.telefono == telefono)
    return db.execute(select(NoContactable.id).where(NoContactable.activo.is_(True), or_(*cond)).limit(1)).first() is not None


def verificar(db: Session, cc: ClienteCampana, etapa: str = "ENCOLAR", ahora: datetime | None = None,
              id_trabajo_actual: int | None = None) -> list[str]:
    """Devuelve la lista de motivos de bloqueo. Lista vacía => se permite continuar."""
    ahora = ahora or ahora_utc()
    motivos: list[str] = []
    camp, cli, deuda = cc.campana, cc.cliente, cc.deuda

    if parametros.pausa_activa(db):
        motivos.append("PAUSA_EMERGENCIA")
    if camp.estado != "ACTIVA":
        motivos.append("CAMPANA_NO_ACTIVA")
    hoy: date = hoy_local(ahora)
    if (camp.fecha_inicio and hoy < camp.fecha_inicio) or (camp.fecha_fin and hoy > camp.fecha_fin):
        motivos.append("FUERA_DE_VIGENCIA")
    if cc.estado_gestion in ESTADOS_FINALES_CC:
        motivos.append(f"GESTION_{cc.estado_gestion}")
    if deuda.estado != "ACTIVA" or deuda.saldo <= 0:
        motivos.append("DEUDA_NO_ACTIVA")
    if not cli.contactable or not cli.telefono or not cli.telefono_valido:
        motivos.append("TELEFONO_INVALIDO")
    if esta_excluido(db, cli.id_cliente, cli.telefono):
        motivos.append("EXCLUIDO")
    if not dentro_de_ventana(camp.hora_inicio, camp.hora_fin, ahora):
        motivos.append("FUERA_DE_HORARIO")
    if cc.intentos >= camp.max_intentos_total:
        motivos.append("INTENTOS_AGOTADOS")
    intentos_hoy = db.execute(
        select(func.count(Llamada.id_llamada)).where(
            Llamada.id_cliente_campana == cc.id, Llamada.canal == "TELEFONIA",
            Llamada.inicio >= inicio_dia_local_en_utc(hoy))
    ).scalar_one()
    if intentos_hoy >= camp.max_intentos_dia:
        motivos.append("INTENTOS_DIARIOS_AGOTADOS")
    if cc.ultimo_intento and cc.ultimo_intento + timedelta(minutes=camp.minutos_entre_intentos) > ahora:
        motivos.append("TIEMPO_MINIMO_ENTRE_INTENTOS")
    en_curso = db.execute(select(Llamada.id_llamada).where(
        Llamada.id_cliente == cli.id_cliente, Llamada.estado_tecnico == "EN_CURSO", Llamada.canal == "TELEFONIA").limit(1)).first()
    if en_curso:
        motivos.append("LLAMADA_SIMULTANEA")
    promesa = db.execute(select(PromesaPago.id_promesa).where(
        PromesaPago.id_deuda == deuda.id_deuda, PromesaPago.estado == "PENDIENTE",
        PromesaPago.fecha_compromiso >= hoy).limit(1)).first()
    if promesa:
        motivos.append("PROMESA_VIGENTE")
    ok, motivo = consumo.presupuesto_disponible(db)
    if not ok:
        motivos.append("PRESUPUESTO_AGOTADO")
    if etapa == "ENCOLAR":
        q = select(Trabajo.id).where(Trabajo.tipo == "MARCAR", Trabajo.estado.in_(["PENDIENTE", "EN_PROCESO"]),
                                     Trabajo.clave_idempotencia.like(f"marcar:{cc.id}:%"))
        if db.execute(q.limit(1)).first():
            motivos.append("YA_EN_COLA")
    return motivos
