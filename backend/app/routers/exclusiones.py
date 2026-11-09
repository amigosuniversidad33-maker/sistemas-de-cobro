"""Módulo No Contactables (CU-18, CU-19)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auditoria import auditar
from ..db import get_db
from ..models import Cliente, ClienteCampana, NoContactable
from ..security import Contexto, requiere
from ..servicios import campanas as srv_campanas
from ..utils import enmascarar_telefono, normalizar_telefono
from .comun import Paginacion, a_dict, obtener_o_404, paginar

router = APIRouter(prefix="/api/exclusiones", tags=["No Contactables"])
MOTIVOS = "^(NUMERO_INVALIDO|SOLICITUD_NO_CONTACTO|PROCESO_LEGAL|OTRO)$"


class ExclusionIn(BaseModel):
    id_cliente: int | None = None
    telefono: str | None = Field(default=None, max_length=30)
    motivo: str = Field(pattern=MOTIVOS)
    detalle: str | None = Field(default=None, max_length=255)


def ser(n: NoContactable) -> dict:
    d = a_dict(n, ["id", "id_cliente", "motivo", "detalle", "origen", "activo", "fecha_registro"])
    d["telefono"] = enmascarar_telefono(n.telefono)
    d["cliente"] = n.cliente.nombre if n.cliente else None
    return d


@router.get("")
def listar(activo: bool | None = True, motivo: str | None = None, pag: Paginacion = Depends(),
           ctx: Contexto = Depends(requiere("exclusiones.ver")), db: Session = Depends(get_db)):
    q = select(NoContactable).order_by(NoContactable.id.desc())
    if activo is not None:
        q = q.where(NoContactable.activo.is_(activo))
    if motivo:
        q = q.where(NoContactable.motivo == motivo)
    return paginar(db, q, pag, ser)


@router.post("", status_code=201)
def crear(datos: ExclusionIn, ctx: Contexto = Depends(requiere("exclusiones.gestionar")), db: Session = Depends(get_db)):
    tel = normalizar_telefono(datos.telefono) if datos.telefono else None
    if datos.telefono and tel is None:
        raise HTTPException(422, "Teléfono inválido.")
    if datos.id_cliente is None and tel is None:
        raise HTTPException(422, "Indique un cliente o un teléfono.")
    cli = obtener_o_404(db, Cliente, datos.id_cliente) if datos.id_cliente else None
    n = NoContactable(id_cliente=cli.id_cliente if cli else None, telefono=tel or (cli.telefono if cli else None),
                      motivo=datos.motivo, detalle=datos.detalle, origen="MANUAL", id_usuario=ctx.usuario.id_usuario)
    db.add(n)
    db.flush()
    # La exclusión aplica de inmediato a trabajos ya encolados (CU-19).
    q = select(ClienteCampana.id)
    if cli:
        q = q.where(ClienteCampana.id_cliente == cli.id_cliente)
    else:
        q = q.join(Cliente, Cliente.id_cliente == ClienteCampana.id_cliente).where(Cliente.telefono == tel)
    ids = list(db.execute(q).scalars())
    cancelados = srv_campanas.cancelar_trabajos_pendientes(db, ids, "Cliente excluido")
    for cc in db.execute(select(ClienteCampana).where(ClienteCampana.id.in_(ids or [-1]))).scalars():
        if cc.estado_gestion in ("PENDIENTE", "EN_COLA"):
            cc.estado_gestion = "EXCLUIDO"
    auditar(db, "EXCLUSION_CREADA", "no_contactable", n.id, {"motivo": datos.motivo, "trabajos_cancelados": cancelados}, ctx=ctx)
    db.commit()
    return {**ser(n), "trabajos_cancelados": cancelados}


@router.post("/{id_exclusion}/desactivar")
def desactivar(id_exclusion: int, ctx: Contexto = Depends(requiere("exclusiones.gestionar")), db: Session = Depends(get_db)):
    n = obtener_o_404(db, NoContactable, id_exclusion)
    if n.motivo == "SOLICITUD_NO_CONTACTO" and n.origen == "AGENTE_IA" and not ctx.tiene("sistema.configurar"):
        raise HTTPException(403, "Solo un administrador puede retirar una solicitud expresa de no contacto.")
    n.activo = False
    auditar(db, "EXCLUSION_DESACTIVADA", "no_contactable", n.id, ctx=ctx)
    db.commit()
    return ser(n)
