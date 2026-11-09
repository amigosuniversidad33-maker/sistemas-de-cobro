"""Utilidades compartidas por los routers."""
import csv
import io
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..utils import celda_segura, inicio_dia_local_en_utc, iso


class Paginacion:
    def __init__(self, pagina: int = Query(1, ge=1, le=100000), por_pagina: int = Query(20, ge=1, le=200)):
        self.pagina, self.por_pagina = pagina, por_pagina


def paginar(db: Session, q, pag: Paginacion, serializar) -> dict:
    total = db.execute(select(func.count()).select_from(q.order_by(None).subquery())).scalar_one()
    filas = db.execute(q.limit(pag.por_pagina).offset((pag.pagina - 1) * pag.por_pagina)).scalars().all()
    return {"items": [serializar(f) for f in filas], "total": total, "pagina": pag.pagina, "por_pagina": pag.por_pagina,
            "paginas": max(1, -(-total // pag.por_pagina))}


def valor_json(v):
    if isinstance(v, datetime):
        return iso(v)
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def a_dict(obj, campos: list[str]) -> dict:
    return {c: valor_json(getattr(obj, c)) for c in campos}


def obtener_o_404(db: Session, modelo, id_):
    obj = db.get(modelo, id_)
    if obj is None:
        raise HTTPException(404, "Registro no encontrado.")
    return obj


def rango_fechas(desde: date | None, hasta: date | None) -> tuple[datetime | None, datetime | None]:
    """Convierte días locales (America/Guatemala) a límites UTC [desde, hasta+1)."""
    from datetime import timedelta

    d = inicio_dia_local_en_utc(desde) if desde else None
    h = inicio_dia_local_en_utc(hasta + timedelta(days=1)) if hasta else None
    return d, h


def csv_respuesta(nombre: str, encabezados: list[str], filas) -> StreamingResponse:
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(encabezados)
    for f in filas:
        w.writerow([celda_segura(valor_json(v)) for v in f])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
