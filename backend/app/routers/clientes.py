"""Clientes y deudas (sección administrativa): importación CSV/Excel, consulta y exportación."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..auditoria import auditar
from ..config import get_settings
from ..db import get_db
from ..models import Cliente, Deuda, Llamada, LoteImportacion, PromesaPago
from ..security import Contexto, requiere
from ..servicios import importacion
from ..utils import enmascarar_documento, enmascarar_telefono
from .comun import Paginacion, a_dict, csv_respuesta, obtener_o_404, paginar

router = APIRouter(prefix="/api", tags=["Clientes"])


def ser_cliente(c: Cliente) -> dict:
    return {"id_cliente": c.id_cliente, "nombre": c.nombre, "documento": enmascarar_documento(c.documento),
            "telefono": enmascarar_telefono(c.telefono), "telefono_valido": c.telefono_valido,
            "contactable": c.contactable,
            "deudas": [{"id_deuda": d.id_deuda, "referencia": d.referencia, "saldo": str(d.saldo), "moneda": d.moneda,
                        "dias_mora": d.dias_mora, "tramo": d.tramo, "estado": d.estado} for d in c.deudas]}


@router.get("/clientes")
def listar(q: str | None = None, tramo: str | None = None, pag: Paginacion = Depends(),
           ctx: Contexto = Depends(requiere("clientes.ver")), db: Session = Depends(get_db)):
    consulta = select(Cliente).order_by(Cliente.id_cliente.desc())
    if q:
        p = f"%{q.strip()[:60]}%"
        consulta = consulta.where(or_(Cliente.nombre.ilike(p), Cliente.documento.ilike(p)))
    if tramo:
        consulta = consulta.where(Cliente.id_cliente.in_(select(Deuda.id_cliente).where(Deuda.tramo == tramo)))
    return paginar(db, consulta, pag, ser_cliente)


@router.get("/clientes/plantilla.csv")
def plantilla(ctx: Contexto = Depends(requiere("clientes.importar"))):
    return csv_respuesta("plantilla_clientes.csv", importacion.COLUMNAS_REQUERIDAS + importacion.COLUMNAS_OPCIONALES,
                         [["1234567890101", "Cliente Ficticio Uno", "5555-0101", "PRE-0001", "1500.00", "15", "", "GTQ"]])


@router.get("/clientes/exportar.csv")
def exportar(ctx: Contexto = Depends(requiere("clientes.exportar")), db: Session = Depends(get_db)):
    filas = db.execute(select(Cliente, Deuda).join(Deuda, Deuda.id_cliente == Cliente.id_cliente)).all()
    auditar(db, "EXPORTACION_CLIENTES", "cliente", None, {"filas": len(filas)}, ctx=ctx)
    db.commit()
    return csv_respuesta("clientes.csv", ["id_cliente", "nombre", "documento", "telefono", "referencia", "saldo", "moneda",
                                          "dias_mora", "tramo"],
                         [[c.id_cliente, c.nombre, enmascarar_documento(c.documento), enmascarar_telefono(c.telefono),
                           d.referencia, d.saldo, d.moneda, d.dias_mora, d.tramo] for c, d in filas])


@router.get("/clientes/{id_cliente}")
def detalle(id_cliente: int, ctx: Contexto = Depends(requiere("clientes.ver")), db: Session = Depends(get_db)):
    c = obtener_o_404(db, Cliente, id_cliente)
    d = ser_cliente(c)
    llamadas = db.execute(select(Llamada).where(Llamada.id_cliente == id_cliente).order_by(Llamada.inicio.desc()).limit(50)).scalars()
    d["historial_llamadas"] = [a_dict(ll, ["id_llamada", "canal", "modo", "estado_tecnico", "resultado_contacto",
                                           "resultado_cobranza", "inicio", "duracion_seg"]) for ll in llamadas]
    promesas = db.execute(select(PromesaPago).where(PromesaPago.id_cliente == id_cliente)).scalars()
    d["promesas"] = [a_dict(p, ["id_promesa", "monto", "moneda", "fecha_compromiso", "estado"]) for p in promesas]
    return d


@router.post("/clientes/importar", status_code=201)
async def importar(archivo: UploadFile = File(...), ctx: Contexto = Depends(requiere("clientes.importar")),
                   db: Session = Depends(get_db)):
    limite = get_settings().tamano_max_importacion_mb * 1024 * 1024
    contenido = await archivo.read(limite + 1)
    if len(contenido) > limite:
        raise HTTPException(413, f"El archivo supera {get_settings().tamano_max_importacion_mb} MB.")
    try:
        lote = importacion.importar(db, archivo.filename or "archivo", contenido, ctx.usuario.id_usuario)
    except importacion.ErrorImportacion as e:
        db.rollback()
        raise HTTPException(e.codigo, str(e))
    auditar(db, "IMPORTACION_CLIENTES", "lote", lote.id_lote,
            {"validos": lote.registros_validos, "actualizados": lote.registros_actualizados,
             "rechazados": lote.registros_rechazados}, ctx=ctx)
    db.commit()
    return a_dict(lote, ["id_lote", "archivo", "registros_validos", "registros_actualizados", "registros_rechazados",
                         "errores", "fecha_carga"])


@router.get("/lotes")
def lotes(pag: Paginacion = Depends(), ctx: Contexto = Depends(requiere("clientes.ver")), db: Session = Depends(get_db)):
    return paginar(db, select(LoteImportacion).order_by(LoteImportacion.id_lote.desc()), pag,
                   lambda l: a_dict(l, ["id_lote", "archivo", "registros_validos", "registros_actualizados",
                                        "registros_rechazados", "fecha_carga"]))


@router.get("/lotes/{id_lote}/errores.csv")
def errores_lote(id_lote: int, ctx: Contexto = Depends(requiere("clientes.importar")), db: Session = Depends(get_db)):
    lote = obtener_o_404(db, LoteImportacion, id_lote)
    return csv_respuesta(f"errores_lote_{id_lote}.csv", ["fila", "documento", "motivos"],
                         [[e["fila"], e["documento"], "; ".join(e["motivos"])] for e in (lote.errores or [])])
