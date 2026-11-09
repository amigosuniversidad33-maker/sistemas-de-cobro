"""Control de consumo de APIs. Los costos son ESTIMACIONES con precios de referencia, no facturación real."""
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import parametros
from ..config import get_settings
from ..models import ConsumoAPI, Llamada
from ..utils import hoy_local, inicio_dia_local_en_utc


def gasto_hoy(db: Session) -> Decimal:
    desde = inicio_dia_local_en_utc(hoy_local())
    total = db.execute(select(func.coalesce(func.sum(ConsumoAPI.costo_estimado_usd), 0))
                       .where(ConsumoAPI.fecha >= desde)).scalar_one()
    return Decimal(str(total))


def presupuesto_disponible(db: Session, llamada: Llamada | None = None) -> tuple[bool, str | None]:
    if gasto_hoy(db) >= parametros.obtener_decimal(db, "presupuesto_diario_usd"):
        return False, "Presupuesto diario de APIs agotado"
    if llamada is not None and Decimal(llamada.costo_estimado_usd or 0) >= parametros.obtener_decimal(db, "presupuesto_interaccion_usd"):
        return False, "Presupuesto por interacción agotado"
    return True, None


def costo_llm(tokens_in: int, tokens_out: int) -> Decimal:
    s = get_settings()
    return (Decimal(tokens_in) * s.llm_precio_entrada_mtok + Decimal(tokens_out) * s.llm_precio_salida_mtok) / Decimal(1_000_000)


def registrar(db: Session, *, proveedor: str, servicio: str, modelo: str, exito: bool, id_llamada: int | None = None,
              tokens_entrada: int = 0, tokens_salida: int = 0, segundos_audio: Decimal | float = 0,
              caracteres: int = 0, costo: Decimal = Decimal("0"), codigo_error: str | None = None,
              latencia_ms: int | None = None, version_prompt: str | None = None) -> ConsumoAPI:
    c = ConsumoAPI(proveedor=proveedor, servicio=servicio, modelo=modelo, exito=exito, id_llamada=id_llamada,
                   tokens_entrada=tokens_entrada, tokens_salida=tokens_salida,
                   segundos_audio=Decimal(str(segundos_audio)).quantize(Decimal("0.01")), caracteres=caracteres,
                   costo_estimado_usd=costo.quantize(Decimal("0.000001")), codigo_error=codigo_error,
                   latencia_ms=latencia_ms, version_prompt=version_prompt)
    db.add(c)
    if id_llamada is not None:
        ll = db.get(Llamada, id_llamada)
        if ll is not None:
            ll.costo_estimado_usd = Decimal(ll.costo_estimado_usd or 0) + c.costo_estimado_usd
    return c
