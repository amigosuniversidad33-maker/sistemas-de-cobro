"""Control y Supervisión (dashboard ejecutivo, CU-30 a CU-33), Seguridad IA (alertas, riesgos), auditoría y sistema."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .. import parametros
from ..auditoria import auditar
from ..config import get_settings
from ..db import get_db
from ..ia import supervisores
from ..ia.proveedor import ErrorProveedor, descripcion_proveedor
from ..models import (
    Alerta,
    Bitacora,
    Campana,
    ConsumoAPI,
    Llamada,
    NoContactable,
    PromesaPago,
    Riesgo,
    TramoMora,
    Trabajo,
)
from ..security import Contexto, campanas_permitidas, requiere
from ..servicios import consumo
from ..utils import dentro_de_ventana, hoy_local, utc_a_local
from ..voz import grabaciones
from .comun import Paginacion, a_dict, obtener_o_404, paginar, rango_fechas

router = APIRouter(prefix="/api", tags=["Control y Supervisión"])


def _tasa(num: int, den: int):
    return round(num * 100 / den, 2) if den else None


@router.get("/dashboard")
def dashboard(desde: date | None = None, hasta: date | None = None, modo: str = "TODOS", canal: str = "TODOS",
              ctx: Contexto = Depends(requiere("dashboard.ver")), db: Session = Depends(get_db)):
    hoy = hoy_local()
    desde = desde or hoy
    hasta = hasta or hoy
    if hasta < desde or (hasta - desde).days > 366:
        raise HTTPException(422, "Rango de fechas inválido (máximo 366 días).")
    d_utc, h_utc = rango_fechas(desde, hasta)
    q = select(Llamada).where(Llamada.inicio >= d_utc, Llamada.inicio < h_utc)
    permitidas = campanas_permitidas(db, ctx)
    if permitidas is not None:
        q = q.where(Llamada.id_campana.in_(permitidas or [-1]))
    if modo in ("REAL", "PRUEBA"):
        q = q.where(Llamada.modo == modo)
    if canal in ("TEXTO", "VOZ_NAVEGADOR", "TELEFONIA"):
        q = q.where(Llamada.canal == canal)
    llamadas = db.execute(q).scalars().all()  # filas únicas: los eventos repetidos no afectan los conteos

    total = len(llamadas)
    contacto = Counter(ll.resultado_contacto for ll in llamadas if ll.resultado_contacto)
    tecnico = Counter(ll.estado_tecnico for ll in llamadas)
    fallos_tecnicos = sum(1 for ll in llamadas if ll.estado_tecnico == "FALLIDA" and ll.resultado_contacto is None)
    lc, lr, lnc = contacto.get("CONTESTADA", 0), contacto.get("RECHAZADA", 0), contacto.get("SIN_CONTESTAR", 0)
    con_resultado = lc + lr + lnc
    cobranza = Counter(ll.resultado_cobranza for ll in llamadas if ll.resultado_cobranza)
    en_curso_ahora = db.execute(select(func.count(Llamada.id_llamada)).where(Llamada.estado_tecnico == "EN_CURSO")).scalar_one()

    tramos = {t.id_tramo: t for t in db.execute(select(TramoMora)).scalars()}
    camp_tramo = {c.id_campana: tramos[c.id_tramo].nombre for c in db.execute(select(Campana)).scalars()}
    por_modulo: dict[str, Counter] = defaultdict(Counter)
    for ll in llamadas:
        modulo = camp_tramo.get(ll.id_campana, "Pruebas sin campaña")
        por_modulo[modulo]["intentos"] += 1
        if ll.resultado_contacto:
            por_modulo[modulo][ll.resultado_contacto] += 1
        if ll.resultado_cobranza == "PROMESA":
            por_modulo[modulo]["PROMESA"] += 1

    serie: dict[str, Counter] = defaultdict(Counter)
    fuera_ventana = 0
    camp_ventana = {c.id_campana: (c.hora_inicio, c.hora_fin) for c in db.execute(select(Campana)).scalars()}
    for ll in llamadas:
        serie[utc_a_local(ll.inicio).date().isoformat()][ll.resultado_contacto or ll.estado_tecnico] += 1
        if ll.canal == "TELEFONIA":
            hi, hf = camp_ventana.get(ll.id_campana, (parametros.obtener(db, "ventana_inicio"), parametros.obtener(db, "ventana_fin")))
            if not dentro_de_ventana(hi, hf, ll.inicio):
                fuera_ventana += 1

    pq = select(PromesaPago).where(PromesaPago.confirmada_en >= d_utc, PromesaPago.confirmada_en < h_utc)
    if permitidas is not None:
        pq = pq.where(PromesaPago.id_campana.in_(permitidas or [-1]))
    promesas = db.execute(pq).scalars().all()
    estados_p = Counter(p.estado for p in promesas)
    montos: dict[str, Decimal] = defaultdict(Decimal)
    for p in promesas:
        montos[p.moneda] += p.monto
    vencidas_eval = estados_p.get("CUMPLIDA", 0) + estados_p.get("INCUMPLIDA", 0)

    consumo_q = db.execute(select(ConsumoAPI.servicio, func.count(ConsumoAPI.id), func.coalesce(func.sum(ConsumoAPI.costo_estimado_usd), 0))
                           .where(ConsumoAPI.fecha >= d_utc, ConsumoAPI.fecha < h_utc).group_by(ConsumoAPI.servicio)).all()
    fallidas_api = dict(db.execute(select(ConsumoAPI.servicio, func.count(ConsumoAPI.id)).where(
        ConsumoAPI.fecha >= d_utc, ConsumoAPI.fecha < h_utc, ConsumoAPI.exito.is_(False)).group_by(ConsumoAPI.servicio)).all())
    alertas = dict(db.execute(select(Alerta.severidad, func.count(Alerta.id)).where(Alerta.estado == "ABIERTA")
                              .group_by(Alerta.severidad)).all())
    meta = int(parametros.obtener(db, "meta_diaria_diseno"))
    dias = (hasta - desde).days + 1
    return {
        "rango": {"desde": desde.isoformat(), "hasta": hasta.isoformat(), "dias": dias, "modo": modo, "canal": canal,
                  "zona_horaria": get_settings().zona_horaria},
        "llamadas": {
            "intentos_LS": total, "en_curso_ahora": en_curso_ahora,
            "contestadas_LC": lc, "rechazadas_LR": lr, "sin_contestar_LNC": lnc,
            "fallos_tecnicos": fallos_tecnicos, "canceladas": tecnico.get("CANCELADA", 0),
            "en_curso_en_rango": tecnico.get("EN_CURSO", 0) + tecnico.get("PENDIENTE", 0),
            "con_resultado_de_contacto": con_resultado,
            "tasa_contestacion": _tasa(lc, con_resultado), "tasa_rechazo": _tasa(lr, con_resultado),
            "tasa_no_contestacion": _tasa(lnc, con_resultado), "tasa_fallo_tecnico": _tasa(fallos_tecnicos, total),
            "denominadores": {"tasas_de_contacto": "Intentos con resultado de contacto (LC + LR + LNC). Excluye fallos técnicos, canceladas y en curso.",
                              "tasa_fallo_tecnico": "Total de intentos del rango (LS)."},
            "por_canal": dict(Counter(ll.canal for ll in llamadas)), "por_modo": dict(Counter(ll.modo for ll in llamadas)),
        },
        "cobranza": {"resultados": dict(cobranza), "promesas_generadas": len(promesas), "promesas_por_estado": dict(estados_p),
                     "monto_prometido": {k: str(v) for k, v in montos.items()},
                     "tasa_cumplimiento": _tasa(estados_p.get("CUMPLIDA", 0), vencidas_eval),
                     "denominador_cumplimiento": "Promesas ya evaluadas (CUMPLIDA + INCUMPLIDA)."},
        "por_modulo": {k: dict(v) for k, v in por_modulo.items()},
        "serie_diaria": {k: dict(v) for k, v in sorted(serie.items())},
        "exclusiones": {"activas": db.execute(select(func.count(NoContactable.id)).where(NoContactable.activo.is_(True))).scalar_one(),
                        "nuevas_en_rango": db.execute(select(func.count(NoContactable.id)).where(
                            NoContactable.fecha_registro >= d_utc, NoContactable.fecha_registro < h_utc)).scalar_one()},
        "consumo_api": {"por_servicio": [{"servicio": s_, "llamadas": n, "costo_estimado_usd": str(Decimal(str(c)).quantize(Decimal('0.0001'))),
                                          "fallidas": fallidas_api.get(s_, 0)} for s_, n, c in consumo_q],
                        "gasto_estimado_hoy_usd": str(consumo.gasto_hoy(db).quantize(Decimal("0.0001"))),
                        "presupuesto_diario_usd": parametros.obtener(db, "presupuesto_diario_usd"),
                        "nota": "Estimación con precios de referencia; no es facturación real del proveedor."},
        "alertas_abiertas": alertas,
        "ventana_horaria": {"llamadas_telefonicas_fuera_de_ventana": fuera_ventana,
                            "ventana_por_defecto": f"{parametros.obtener(db, 'ventana_inicio')}–{parametros.obtener(db, 'ventana_fin')}"},
        "meta_diseno": {"meta_diaria": meta, "intentos_promedio_diario": round(total / dias, 2),
                        "avance_pct": _tasa(round(total / dias), meta),
                        "nota": "Meta FUTURA de arquitectura (65,000/día). El piloto no ha sido probado a esa escala."},
        "pausa_emergencia": parametros.pausa_activa(db),
    }


# ---------------------------------------------------------------- alertas y seguridad
class EstadoAlertaIn(BaseModel):
    estado: str = Field(pattern="^(RECONOCIDA|CERRADA)$")


@router.get("/alertas")
def alertas(estado: str | None = "ABIERTA", severidad: str | None = None, pag: Paginacion = Depends(),
            ctx: Contexto = Depends(requiere("seguridad.ver")), db: Session = Depends(get_db)):
    q = select(Alerta).order_by(Alerta.id.desc())
    if estado:
        q = q.where(Alerta.estado == estado)
    if severidad:
        q = q.where(Alerta.severidad == severidad)
    return paginar(db, q, pag, lambda a: a_dict(a, ["id", "tipo", "severidad", "origen", "mensaje", "recomendacion", "detalle",
                                                    "estado", "fecha"]))


@router.post("/alertas/{id_alerta}/estado")
def estado_alerta(id_alerta: int, datos: EstadoAlertaIn, ctx: Contexto = Depends(requiere("seguridad.ver", "dashboard.ver")),
                  db: Session = Depends(get_db)):
    a = obtener_o_404(db, Alerta, id_alerta)
    a.estado, a.id_usuario_cierre = datos.estado, ctx.usuario.id_usuario
    auditar(db, "ALERTA_" + datos.estado, "alerta", id_alerta, ctx=ctx)
    db.commit()
    return {"ok": True}


@router.post("/seguridad/reglas/ejecutar")
def ejecutar_reglas(ctx: Contexto = Depends(requiere("seguridad.gestionar")), db: Session = Depends(get_db)):
    r = supervisores.reglas_deterministas(db)
    auditar(db, "REGLAS_SEGURIDAD_EJECUTADAS", "alerta", None, {"generadas": r}, ctx=ctx)
    db.commit()
    return {"alertas_generadas": r}


@router.post("/seguridad/supervisor-ia")
def supervisor_ia(ctx: Contexto = Depends(requiere("seguridad.gestionar")), db: Session = Depends(get_db)):
    try:
        creadas = supervisores.analizar_seguridad_ia(db)
    except ErrorProveedor as e:
        db.commit()
        raise HTTPException(502, f"Supervisor IA no disponible ({e.codigo}).")
    auditar(db, "SUPERVISOR_SEGURIDAD_IA", "alerta", None, {"alertas": len(creadas)}, ctx=ctx)
    db.commit()
    return {"alertas": [a_dict(a, ["tipo", "severidad", "mensaje", "recomendacion"]) for a in creadas]}


@router.get("/seguridad/metricas")
def metricas(ctx: Contexto = Depends(requiere("seguridad.ver")), db: Session = Depends(get_db)):
    return supervisores.metricas_sanitizadas(db)


@router.get("/seguridad/riesgos")
def riesgos(ctx: Contexto = Depends(requiere("seguridad.ver")), db: Session = Depends(get_db)):
    salida = []
    for r in db.execute(select(Riesgo).order_by(Riesgo.codigo)).scalars():
        d = a_dict(r, ["codigo", "nombre", "categoria", "probabilidad", "impacto", "disparador", "componente", "estrategia",
                       "control_implementado"])
        nr = r.probabilidad * r.impacto
        d["nivel_riesgo"] = nr
        d["nivel"] = "CRÍTICO" if nr >= 15 else "MEDIO" if nr >= 6 else "BAJO"
        salida.append(d)
    return salida


# ---------------------------------------------------------------- auditoría
@router.get("/auditoria")
def auditoria(accion: str | None = None, entidad: str | None = None, id_usuario: int | None = None, desde: date | None = None,
              hasta: date | None = None, pag: Paginacion = Depends(), ctx: Contexto = Depends(requiere("auditoria.ver")),
              db: Session = Depends(get_db)):
    q = select(Bitacora).order_by(Bitacora.id_log.desc())
    if accion:
        q = q.where(Bitacora.accion == accion)
    if entidad:
        q = q.where(Bitacora.entidad == entidad)
    if id_usuario:
        q = q.where(Bitacora.id_usuario == id_usuario)
    d, h = rango_fechas(desde, hasta)
    if d:
        q = q.where(Bitacora.fecha >= d)
    if h:
        q = q.where(Bitacora.fecha < h)
    return paginar(db, q, pag, lambda b: {**a_dict(b, ["id_log", "accion", "entidad", "id_entidad", "detalle", "ip", "fecha"]),
                                          "usuario": b.usuario.usuario if b.usuario else "sistema"})


# ---------------------------------------------------------------- sistema
class ParametroIn(BaseModel):
    valor: str = Field(min_length=1, max_length=50)


class EmergenciaIn(BaseModel):
    activar: bool
    motivo: str = Field(min_length=3, max_length=255)


@router.get("/sistema/estado")
def estado_sistema(ctx: Contexto = Depends(requiere("dashboard.ver")), db: Session = Depends(get_db)):
    s = get_settings()
    try:
        db.execute(text("SELECT 1"))
        bd = "OK"
    except Exception:
        bd = "ERROR"
    return {"base_de_datos": bd, "motor_bd": db.get_bind().dialect.name,
            "llm": {"proveedor": s.llm_proveedor, "modelo_agente": s.anthropic_modelo, "modelo_supervisor": s.anthropic_modelo_supervisor,
                    "credencial_configurada": bool(s.anthropic_api_key), "en_uso": descripcion_proveedor()["etiqueta"]},
            "deepgram": {"stt": s.deepgram_stt_modelo, "tts": s.deepgram_tts_modelo, "credencial_configurada": bool(s.deepgram_api_key)},
            "telefonia_habilitada": s.telefonia_habilitada, "grabaciones_cifradas": grabaciones.habilitadas(),
            "pausa_emergencia": parametros.pausa_activa(db),
            "trabajos_pendientes": db.execute(select(func.count(Trabajo.id)).where(Trabajo.estado == "PENDIENTE")).scalar_one(),
            "entorno": s.entorno}


@router.get("/sistema/parametros")
def ver_parametros(ctx: Contexto = Depends(requiere("dashboard.ver")), db: Session = Depends(get_db)):
    return parametros.listar(db)


@router.put("/sistema/parametros/{clave}")
def cambiar_parametro(clave: str, datos: ParametroIn, ctx: Contexto = Depends(requiere("sistema.configurar")),
                      db: Session = Depends(get_db)):
    import re

    validadores = {
        "ventana_inicio": r"^([01]\d|2[0-3]):[0-5]\d$", "ventana_fin": r"^([01]\d|2[0-3]):[0-5]\d$",
        "presupuesto_diario_usd": r"^\d{1,6}(\.\d{1,4})?$", "presupuesto_interaccion_usd": r"^\d{1,4}(\.\d{1,4})?$",
        "max_canales_piloto": r"^([1-9]|10)$", "meta_diaria_diseno": r"^\d{1,7}$",
    }
    if clave == "pausa_emergencia":
        raise HTTPException(400, "Use el endpoint de pausa de emergencia.")
    if clave not in validadores:
        raise HTTPException(404, "Parámetro desconocido.")
    if not re.match(validadores[clave], datos.valor):
        raise HTTPException(422, "Valor inválido para el parámetro.")
    anterior = parametros.obtener(db, clave)
    parametros.establecer(db, clave, datos.valor, ctx.usuario.id_usuario)
    auditar(db, "PARAMETRO_MODIFICADO", "configuracion", clave, {"anterior": anterior, "nuevo": datos.valor}, ctx=ctx)
    db.commit()
    return {"clave": clave, "valor": datos.valor}


@router.post("/sistema/emergencia")
def emergencia(datos: EmergenciaIn, ctx: Contexto = Depends(requiere("sistema.emergencia")), db: Session = Depends(get_db)):
    """Pausa de emergencia: bloquea NUEVAS marcaciones y conversaciones. Las llamadas activas terminan su turno actual
    y el marcador no origina más (ver MANUAL_TECNICO.md)."""
    parametros.establecer(db, "pausa_emergencia", "1" if datos.activar else "0", ctx.usuario.id_usuario)
    canceladas = 0
    if datos.activar:
        from sqlalchemy import update

        from ..models import ClienteCampana

        r = db.execute(update(Trabajo).where(Trabajo.tipo == "MARCAR", Trabajo.estado == "PENDIENTE")
                       .values(estado="CANCELADO", resultado="Pausa de emergencia"))
        canceladas = r.rowcount or 0
        db.execute(update(ClienteCampana).where(ClienteCampana.estado_gestion == "EN_COLA").values(estado_gestion="PENDIENTE"))
        db.add(Alerta(tipo="PAUSA_EMERGENCIA", severidad="CRITICA", origen="REGLA",
                      mensaje=f"Pausa de emergencia activada por {ctx.usuario.usuario}: {datos.motivo}"[:500]))
    auditar(db, "PAUSA_EMERGENCIA_" + ("ACTIVADA" if datos.activar else "DESACTIVADA"), "configuracion", "pausa_emergencia",
            {"motivo": datos.motivo, "trabajos_cancelados": canceladas}, ctx=ctx)
    db.commit()
    return {"pausa_emergencia": datos.activar, "trabajos_cancelados": canceladas}


@router.get("/sistema/consumo")
def consumo_detalle(dias: int = 7, ctx: Contexto = Depends(requiere("dashboard.ver")), db: Session = Depends(get_db)):
    dias = max(1, min(dias, 90))
    desde, _ = rango_fechas(hoy_local() - timedelta(days=dias - 1), None)
    filas = db.execute(select(ConsumoAPI).where(ConsumoAPI.fecha >= desde).order_by(ConsumoAPI.id.desc()).limit(500)).scalars()
    return [a_dict(c, ["id", "proveedor", "servicio", "modelo", "version_prompt", "id_llamada", "tokens_entrada", "tokens_salida",
                       "segundos_audio", "caracteres", "costo_estimado_usd", "exito", "codigo_error", "latencia_ms", "fecha"])
            for c in filas]


@router.get("/sistema/trabajos")
def trabajos(estado: str | None = None, pag: Paginacion = Depends(), ctx: Contexto = Depends(requiere("dashboard.ver")),
             db: Session = Depends(get_db)):
    q = select(Trabajo).order_by(Trabajo.id.desc())
    if estado:
        q = q.where(Trabajo.estado == estado)
    return paginar(db, q, pag, lambda t: a_dict(t, ["id", "tipo", "estado", "intentos", "resultado", "disponible_en", "creado",
                                                    "actualizado"]))
