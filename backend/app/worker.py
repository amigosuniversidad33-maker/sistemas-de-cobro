"""Proceso de trabajos en segundo plano (separado de la API).

Ejecutar:  python -m app.worker
- Cola durable en MySQL (tb_trabajo), reclamada con FOR UPDATE SKIP LOCKED.
- Al iniciar recupera trabajos/canales/llamadas interrumpidos.
- Tareas periódicas: reglas deterministas de seguridad y revisión de promesas vencidas.
"""
import logging
import os
import signal
import socket
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .db import SessionLocal
from .ia import supervisores
from .ia.proveedor import ErrorProveedor
from .models import Trabajo, ahora_utc
from .servicios import promesas
from .telefonia import marcador

log = logging.getLogger("worker")
ID_WORKER = f"{socket.gethostname()}:{os.getpid()}"
_detener = False


def _senal(*_):
    global _detener
    _detener = True
    log.info("Señal de detención recibida; se termina el trabajo actual y se sale.")


def reclamar(db) -> Trabajo | None:
    s = get_settings()
    ahora = ahora_utc()
    t = db.execute(select(Trabajo).where(Trabajo.estado == "PENDIENTE", Trabajo.disponible_en <= ahora)
                   .order_by(Trabajo.id).limit(1).with_for_update(skip_locked=True)).scalars().first()
    if t is None:
        db.rollback()
        return None
    t.estado, t.bloqueado_por = "EN_PROCESO", ID_WORKER
    t.bloqueado_hasta = ahora + timedelta(seconds=s.worker_bloqueo_seg)
    t.intentos += 1
    db.commit()
    return t


def ejecutar(db, t: Trabajo) -> None:
    try:
        if t.tipo == "MARCAR":
            res = marcador.procesar_marcar(db, t)
            t.estado = ("CANCELADO" if res.startswith("CANCELADO") else
                        "FALLIDO" if res.startswith(("FALLIDO", "BLOQUEADO")) else "COMPLETADO")
            t.resultado = res[:500]
        elif t.tipo == "LLAMAR_EXTENSION":
            res = marcador.procesar_llamar_extension(db, t)
            t.estado = ("CANCELADO" if res.startswith("CANCELADO") else
                        "FALLIDO" if res.startswith(("FALLIDO", "BLOQUEADO")) else "COMPLETADO")
            t.resultado = res[:500]
        elif t.tipo == "QA_LLAMADA":
            ev = supervisores.evaluar_llamada(db, int(t.payload["id_llamada"]))
            t.estado, t.resultado = "COMPLETADO", f"QA #{ev.id_qa} puntaje {ev.puntaje}"
        elif t.tipo == "REVISAR_PROMESAS":
            t.estado, t.resultado = "COMPLETADO", str(promesas.revisar_vencidas(db))
        elif t.tipo == "SUPERVISION_SEGURIDAD":
            creadas = supervisores.analizar_seguridad_ia(db)
            t.estado, t.resultado = "COMPLETADO", f"{len(creadas)} alertas"
        else:
            t.estado, t.resultado = "FALLIDO", "Tipo de trabajo desconocido"
    except marcador.Reprogramar as e:
        db.rollback()
        t = db.get(Trabajo, t.id)
        t.estado, t.intentos, t.resultado = "PENDIENTE", max(t.intentos - 1, 0), str(e)
        t.disponible_en = ahora_utc() + timedelta(seconds=60)
    except ErrorProveedor as e:
        db.rollback()
        t = db.get(Trabajo, t.id)
        if e.reintentable and t.intentos < t.max_intentos:
            t.estado, t.disponible_en = "PENDIENTE", ahora_utc() + timedelta(seconds=60 * t.intentos)
        else:
            t.estado = "FALLIDO"
        t.resultado = f"Proveedor: {e.codigo}"
    except ValueError as e:
        db.rollback()
        t = db.get(Trabajo, t.id)
        t.estado, t.resultado = "FALLIDO", str(e)[:500]
    t.bloqueado_por, t.bloqueado_hasta = None, None
    db.commit()


def programar_periodicos(db) -> None:
    ahora = ahora_utc()
    clave = f"promesas:{ahora.strftime('%Y%m%d%H')}"
    if db.execute(select(Trabajo.id).where(Trabajo.clave_idempotencia == clave)).first() is None:
        try:
            db.add(Trabajo(tipo="REVISAR_PROMESAS", payload={}, clave_idempotencia=clave))
            db.commit()
        except IntegrityError:
            db.rollback()
    supervisores.reglas_deterministas(db)
    db.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGINT, _senal)
    signal.signal(signal.SIGTERM, _senal)
    s = get_settings()
    with SessionLocal() as db:
        res = marcador.recuperar_tras_reinicio(db)
        db.commit()
        log.info("Worker %s iniciado. Recuperación: %s", ID_WORKER, res)
    ultimo_periodico = 0.0
    while not _detener:
        with SessionLocal() as db:
            try:
                if time.monotonic() - ultimo_periodico > 60:
                    programar_periodicos(db)
                    ultimo_periodico = time.monotonic()
                t = reclamar(db)
                if t is not None:
                    log.info("Procesando trabajo #%s (%s)", t.id, t.tipo)
                    ejecutar(db, t)
                    log.info("Trabajo #%s -> %s", t.id, t.estado)
                    continue
            except Exception:  # el worker no debe morir por un error puntual
                log.exception("Error en el ciclo del worker")
                db.rollback()
        time.sleep(s.worker_intervalo_seg)
    log.info("Worker detenido.")


if __name__ == "__main__":
    main()
