"""Parámetros operativos editables por el administrador (persisten en tb_configuracion)."""
from decimal import Decimal

from sqlalchemy.orm import Session

from .config import get_settings
from .models import Configuracion

# clave -> (valor por defecto como texto, descripción)
def _defaults() -> dict[str, tuple[str, str]]:
    s = get_settings()
    return {
        "pausa_emergencia": ("0", "1 = bloquea toda nueva marcación y nuevas conversaciones reales"),
        "ventana_inicio": ("08:00", "Inicio de ventana horaria por defecto (hora local, política inicial del proyecto)"),
        "ventana_fin": ("20:00", "Fin de ventana horaria por defecto (exclusivo)"),
        "presupuesto_diario_usd": (str(s.presupuesto_diario_usd), "Presupuesto diario estimado de APIs (USD)"),
        "presupuesto_interaccion_usd": (str(s.presupuesto_interaccion_usd), "Presupuesto estimado por interacción (USD)"),
        "max_canales_piloto": ("1", "Canales telefónicos simultáneos permitidos en el piloto"),
        "meta_diaria_diseno": ("65000", "Meta FUTURA de arquitectura (no soportada en piloto)"),
    }


def obtener(db: Session, clave: str) -> str:
    fila = db.get(Configuracion, clave)
    if fila is not None:
        return fila.valor
    return _defaults()[clave][0]


def obtener_decimal(db: Session, clave: str) -> Decimal:
    return Decimal(obtener(db, clave))


def pausa_activa(db: Session) -> bool:
    return obtener(db, "pausa_emergencia") == "1"


def establecer(db: Session, clave: str, valor: str, id_usuario: int | None) -> None:
    if clave not in _defaults():
        raise KeyError(clave)
    fila = db.get(Configuracion, clave)
    if fila is None:
        db.add(Configuracion(clave=clave, valor=valor, descripcion=_defaults()[clave][1], id_usuario=id_usuario))
    else:
        fila.valor = valor
        fila.id_usuario = id_usuario


def listar(db: Session) -> list[dict]:
    return [{"clave": k, "valor": obtener(db, k), "descripcion": d} for k, (_, d) in _defaults().items()]
