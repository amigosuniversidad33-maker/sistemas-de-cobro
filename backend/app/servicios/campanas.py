"""Campañas: estados, clasificación por tramo de mora y encolado (DS-03, CU-04 a CU-06, DF-03)."""
from collections import Counter
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import AgenteIA, Campana, ClienteCampana, Deuda, Trabajo, ahora_utc
from ..utils import parse_hhmm
from . import reglas

TRANSICIONES = {
    "BORRADOR": {"ACTIVA", "FINALIZADA"},
    "ACTIVA": {"PAUSADA", "FINALIZADA"},
    "PAUSADA": {"ACTIVA", "FINALIZADA"},
    "FINALIZADA": set(),
}


def agentes_validos(db: Session, camp: Campana) -> list[AgenteIA]:
    validos = []
    for ca in camp.agentes:
        ag = ca.agente
        if (ag.activo and ag.guion is not None and ag.guion.estado == "PUBLICADO" and ag.guion.tramo == camp.tramo.codigo
                and ag.politica is not None and ag.politica.activa):
            validos.append(ag)
    return validos


def faltantes_para_activar(db: Session, camp: Campana) -> list[str]:
    f = []
    if not camp.fecha_inicio or not camp.fecha_fin:
        f.append("Defina fecha de inicio y fin.")
    elif camp.fecha_fin < camp.fecha_inicio:
        f.append("La fecha de fin es anterior a la de inicio.")
    try:
        if parse_hhmm(camp.hora_inicio) >= parse_hhmm(camp.hora_fin):
            f.append("La hora de inicio debe ser menor que la hora de fin.")
    except ValueError:
        f.append("Horario inválido.")
    if not (camp.mensaje_base or "").strip():
        f.append("Defina el mensaje base.")
    if not agentes_validos(db, camp):
        f.append("Asigne al menos un agente IA activo con guion PUBLICADO del mismo tramo y política activa.")
    n = db.execute(select(ClienteCampana.id).where(ClienteCampana.id_campana == camp.id_campana).limit(1)).first()
    if not n:
        f.append("Clasifique y asigne clientes a la campaña.")
    return f


def cancelar_trabajos_pendientes(db: Session, ids_cc: list[int], motivo: str) -> int:
    if not ids_cc:
        return 0
    total = 0
    for id_cc in ids_cc:
        r = db.execute(update(Trabajo).where(
            Trabajo.tipo == "MARCAR", Trabajo.estado == "PENDIENTE",
            Trabajo.clave_idempotencia.like(f"marcar:{id_cc}:%")
        ).values(estado="CANCELADO", resultado=motivo, actualizado=ahora_utc()))
        total += r.rowcount or 0
    db.execute(update(ClienteCampana).where(ClienteCampana.id.in_(ids_cc), ClienteCampana.estado_gestion == "EN_COLA")
               .values(estado_gestion="PENDIENTE"))
    return total


def cambiar_estado(db: Session, camp: Campana, nuevo: str) -> dict:
    if nuevo not in TRANSICIONES.get(camp.estado, set()):
        raise ValueError(f"Transición no permitida: {camp.estado} → {nuevo}")
    if nuevo == "ACTIVA":
        faltan = faltantes_para_activar(db, camp)
        if faltan:
            raise ValueError("Campaña incompleta: " + " ".join(faltan))
    anterior = camp.estado
    camp.estado = nuevo
    cancelados = 0
    if nuevo in ("PAUSADA", "FINALIZADA"):
        ids = list(db.execute(select(ClienteCampana.id).where(ClienteCampana.id_campana == camp.id_campana)).scalars())
        cancelados = cancelar_trabajos_pendientes(db, ids, f"Campaña {nuevo.lower()}")
    return {"anterior": anterior, "nuevo": nuevo, "trabajos_cancelados": cancelados}


def clasificar_y_asignar(db: Session, camp: Campana) -> dict:
    """Asigna deudas activas cuyo tramo coincide con el de la campaña. Idempotente (uq_campana_deuda)."""
    if camp.estado == "FINALIZADA":
        raise ValueError("La campaña está finalizada.")
    t = camp.tramo
    existentes = set(db.execute(select(ClienteCampana.id_deuda).where(ClienteCampana.id_campana == camp.id_campana)).scalars())
    deudas = db.execute(select(Deuda).where(Deuda.estado == "ACTIVA", Deuda.dias_mora >= t.dias_min,
                                            Deuda.dias_mora <= t.dias_max)).scalars().all()
    nuevos = excluidos = 0
    for d in deudas:
        if d.id_deuda in existentes:
            continue
        excl = reglas.esta_excluido(db, d.id_cliente, d.cliente.telefono)
        db.add(ClienteCampana(id_cliente=d.id_cliente, id_campana=camp.id_campana, id_deuda=d.id_deuda,
                              prioridad=t.prioridad, estado_gestion="EXCLUIDO" if excl else "PENDIENTE"))
        nuevos += 1
        excluidos += int(excl)
    fuera = db.execute(select(Deuda.id_deuda).where(Deuda.estado == "ACTIVA", Deuda.tramo == "GESTION_ESPECIAL")).all()
    return {"asignados": nuevos, "excluidos": excluidos, "ya_asignados": len(existentes),
            "gestion_especial_sin_regla": len(fuera)}


def encolar(db: Session, camp: Campana) -> dict:
    if camp.estado != "ACTIVA":
        raise ValueError("Solo se pueden encolar campañas activas.")
    resumen: Counter = Counter()
    ccs = db.execute(select(ClienteCampana).where(ClienteCampana.id_campana == camp.id_campana,
                                                  ClienteCampana.estado_gestion == "PENDIENTE")
                     .order_by(ClienteCampana.prioridad.desc(), ClienteCampana.id)).scalars().all()
    for cc in ccs:
        motivos = reglas.verificar(db, cc, "ENCOLAR")
        if "EXCLUIDO" in motivos:
            cc.estado_gestion = "EXCLUIDO"
        if "INTENTOS_AGOTADOS" in motivos:
            cc.estado_gestion = "AGOTADO"
        if motivos:
            for m in motivos:
                resumen[m] += 1
            continue
        db.add(Trabajo(tipo="MARCAR", payload={"id_cliente_campana": cc.id, "id_campana": camp.id_campana},
                       clave_idempotencia=f"marcar:{cc.id}:{cc.intentos + 1}:{uuid4().hex[:10]}", max_intentos=1))
        cc.estado_gestion = "EN_COLA"
        resumen["ENCOLADOS"] += 1
    return dict(resumen)
