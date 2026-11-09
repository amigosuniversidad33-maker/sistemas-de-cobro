"""Bitácora de auditoría para operaciones sensibles."""
from sqlalchemy.orm import Session

from .models import Bitacora
from .utils import enmascarar_pii


def _limpiar(detalle):
    if detalle is None:
        return None
    if isinstance(detalle, dict):
        return {k: _limpiar(v) for k, v in detalle.items() if "password" not in k.lower() and "clave" not in k.lower()}
    if isinstance(detalle, list):
        return [_limpiar(v) for v in detalle]
    if isinstance(detalle, str):
        return enmascarar_pii(detalle)[:500]
    return detalle


def auditar(db: Session, accion: str, entidad: str, id_entidad=None, detalle: dict | None = None,
            id_usuario: int | None = None, ip: str | None = None, ctx=None) -> None:
    if ctx is not None:
        id_usuario = id_usuario or ctx.usuario.id_usuario
        ip = ip or ctx.ip
    db.add(Bitacora(id_usuario=id_usuario, accion=accion, entidad=entidad,
                    id_entidad=str(id_entidad) if id_entidad is not None else None,
                    detalle=_limpiar(detalle), ip=ip))
