"""Importación, campañas, exclusiones, reglas de marcación, cola durable, eventos y canales."""
import io

import pytest
from datetime import datetime, timedelta

from sqlalchemy import select

from app import parametros
from app.db import SessionLocal, reconfigurar
from app.config import get_settings
from app.models import (
    CanalConcurrente,
    ClienteCampana,
    ExtensionSIP,
    Llamada,
    PlantaFreeswitch,
    Trabajo,
    TroncalSIP,
    ahora_utc,
)
from app.servicios import campanas as srv
from app.telefonia import marcador
from app.utils import celda_segura, dentro_de_ventana, normalizar_telefono

CSV = ("documento,nombre,telefono,referencia,saldo,dias_mora\n"
       "1111222233334,Cliente Prueba Uno,5555-0001,REF-1,1000.00,10\n"
       "1111222233335,Cliente Prueba Dos,+502 4444 0002,REF-2,2500.50,45\n"
       "1111222233336,Cliente Prueba Tres,22220003,REF-3,800,20\n"
       "123,Documento Malo,5555-0004,REF-4,100,10\n"
       "1111222233337,Telefono Malo,12345,REF-5,100,10\n")


def _importar(admin, contenido: str, nombre="clientes.csv"):
    return admin.post("/api/clientes/importar", files={"archivo": (nombre, io.BytesIO(contenido.encode()), "text/csv")})


def _utc_desde_local(h: int, m: int) -> datetime:
    return datetime(2026, 10, 15, h, m) + timedelta(hours=6)  # America/Guatemala = UTC-6


def test_normalizacion_y_celdas_seguras():
    assert normalizar_telefono("5555-1234") == "+50255551234"
    assert normalizar_telefono("+502 2222 3333") == "+50222223333"
    assert normalizar_telefono("1234") is None
    assert normalizar_telefono("95551234") is None
    assert celda_segura("=HYPERLINK(1)") == "'=HYPERLINK(1)"


def test_ventana_horaria_en_limites():
    assert not dentro_de_ventana("08:00", "20:00", _utc_desde_local(7, 59))
    assert dentro_de_ventana("08:00", "20:00", _utc_desde_local(8, 0))
    assert dentro_de_ventana("08:00", "20:00", _utc_desde_local(19, 59))
    assert not dentro_de_ventana("08:00", "20:00", _utc_desde_local(20, 0))


def test_importacion_validaciones_y_repetida(admin):
    r = _importar(admin, CSV)
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["registros_validos"] == 3 and d["registros_rechazados"] == 2
    motivos = {e["fila"]: e["motivos"] for e in d["errores"]}
    assert "documento inválido" in motivos[5] and "teléfono inválido" in motivos[6]
    r2 = _importar(admin, CSV)
    assert r2.status_code == 409  # mismo archivo: no duplica
    r3 = _importar(admin, CSV.replace("1000.00", "1200.00"), "clientes_v2.csv")
    assert r3.json()["registros_actualizados"] == 3 and r3.json()["registros_validos"] == 0


def test_archivos_invalidos(admin):
    r = admin.post("/api/clientes/importar", files={"archivo": ("virus.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")})
    assert r.status_code == 422
    assert _importar(admin, "a,b,c\n1,2,3\n", "x.csv").status_code == 422
    r = admin.post("/api/clientes/importar", files={"archivo": ("falso.xlsx", io.BytesIO(b"no es excel"), "application/vnd.ms-excel")})
    assert r.status_code == 422
    grande = "documento,nombre,telefono,referencia,saldo,dias_mora\n" + ("x" * (6 * 1024 * 1024))
    assert _importar(admin, grande, "grande.csv").status_code == 413


def _campana_activa(admin, nombre: str, codigo_tramo="MORA_TEMPRANA") -> dict:
    tramo = next(t for t in admin.get("/api/tramos").json() if t["codigo"] == codigo_tramo)
    hoy = datetime.now().date().isoformat()
    c = admin.post("/api/campanas", json={"nombre": nombre, "id_tramo": tramo["id_tramo"], "fecha_inicio": hoy,
                                          "fecha_fin": hoy, "mensaje_base": "Recordatorio", "hora_inicio": "00:00",
                                          "hora_fin": "23:59"}).json()
    r = admin.post(f"/api/campanas/{c['id_campana']}/estado", json={"estado": "ACTIVA"})
    assert r.status_code == 409  # incompleta: sin agente ni clientes
    agente = next(a for a in admin.get("/api/agentes").json() if a["tramo"] == codigo_tramo)
    admin.post(f"/api/campanas/{c['id_campana']}/agentes", json={"id_agente": agente["id_agente"]})
    assert admin.post(f"/api/campanas/{c['id_campana']}/clasificar").json()["asignados"] >= 1
    r = admin.post(f"/api/campanas/{c['id_campana']}/estado", json={"estado": "ACTIVA"})
    assert r.status_code == 200, r.text
    return c


def test_flujo_campana_exclusion_despues_de_encolar(admin):
    c = _campana_activa(admin, "Campaña exclusión")
    r = admin.post(f"/api/campanas/{c['id_campana']}/encolar").json()
    assert r.get("ENCOLADOS", 0) >= 1
    assert admin.post(f"/api/campanas/{c['id_campana']}/encolar").json().get("ENCOLADOS", 0) == 0  # sin duplicar
    with SessionLocal() as db:
        cc = db.execute(select(ClienteCampana).where(ClienteCampana.id_campana == c["id_campana"],
                                                     ClienteCampana.estado_gestion == "EN_COLA")).scalars().first()
        id_cliente, id_cc = cc.id_cliente, cc.id
    r = admin.post("/api/exclusiones", json={"id_cliente": id_cliente, "motivo": "SOLICITUD_NO_CONTACTO"})
    assert r.status_code == 201 and r.json()["trabajos_cancelados"] >= 1
    with SessionLocal() as db:
        assert db.get(ClienteCampana, id_cc).estado_gestion == "EXCLUIDO"
        pend = db.execute(select(Trabajo).where(Trabajo.estado == "PENDIENTE",
                                                Trabajo.clave_idempotencia.like(f"marcar:{id_cc}:%"))).first()
        assert pend is None


def test_exclusion_detectada_justo_antes_de_originar(admin):
    """Si la exclusión llega por otra vía (sin cancelar el trabajo), la re-verificación previa a originar la bloquea."""
    c = _campana_activa(admin, "Campaña re-verificación", "MORA_TARDIA")
    admin.post(f"/api/campanas/{c['id_campana']}/encolar")
    with SessionLocal() as db:
        t = db.execute(select(Trabajo).where(Trabajo.estado == "PENDIENTE", Trabajo.tipo == "MARCAR")
                       .order_by(Trabajo.id.desc())).scalars().first()
        cc = db.get(ClienteCampana, t.payload["id_cliente_campana"])
        from app.models import NoContactable

        db.add(NoContactable(id_cliente=cc.id_cliente, telefono=cc.cliente.telefono, motivo="PROCESO_LEGAL"))
        db.commit()
        res = marcador.procesar_marcar(db, t)
        assert res.startswith("CANCELADO") and "EXCLUIDO" in res


def test_campana_pausada_antes_de_marcar(admin):
    c = _campana_activa(admin, "Campaña pausa")
    admin.post(f"/api/campanas/{c['id_campana']}/encolar")
    with SessionLocal() as db:
        t = db.execute(select(Trabajo).where(Trabajo.estado == "PENDIENTE", Trabajo.tipo == "MARCAR")
                       .order_by(Trabajo.id.desc())).scalars().first()
        id_t = t.id
    r = admin.post(f"/api/campanas/{c['id_campana']}/estado", json={"estado": "PAUSADA"})
    assert r.json()["trabajos_cancelados"] >= 1
    with SessionLocal() as db:
        t = db.get(Trabajo, id_t)
        assert t.estado == "CANCELADO"
        res = marcador.procesar_marcar(db, t)  # aunque el worker lo hubiera tomado, re-verifica
        assert "CAMPANA_NO_ACTIVA" in res


def test_telefonia_deshabilitada_queda_bloqueada(admin):
    c = _campana_activa(admin, "Campaña telefonía", "MORA_TEMPRANA")
    with SessionLocal() as db:
        cc = db.execute(select(ClienteCampana).where(ClienteCampana.id_campana == c["id_campana"],
                                                     ClienteCampana.estado_gestion == "PENDIENTE")).scalars().first()
        t = Trabajo(tipo="MARCAR", payload={"id_cliente_campana": cc.id}, clave_idempotencia=f"marcar:{cc.id}:prueba")
        db.add(t)
        db.commit()
        assert marcador.procesar_marcar(db, t) == "BLOQUEADO:TELEFONIA_NO_CONFIGURADA"


def test_pausa_de_emergencia(admin):
    r = admin.post("/api/sistema/emergencia", json={"activar": True, "motivo": "Prueba automatizada"})
    assert r.status_code == 200
    agente = admin.get("/api/agentes").json()[0]
    assert admin.post("/api/conversaciones", json={"id_agente": agente["id_agente"], "id_deuda": 1}).status_code == 423
    admin.post("/api/sistema/emergencia", json={"activar": False, "motivo": "Fin de prueba"})


def test_eventos_duplicados_y_fuera_de_orden(db):
    ll = Llamada(canal="TELEFONIA", modo="REAL", estado_tecnico="FINALIZADA")
    db.add(ll)
    db.commit()
    assert marcador.registrar_evento(db, ll, "COLGADA", "uuid-x:HANGUP")
    assert marcador.registrar_evento(db, ll, "CONTESTADA", "uuid-x:ANSWER")  # llega después (fuera de orden)
    assert not marcador.registrar_evento(db, ll, "COLGADA", "uuid-x:HANGUP")  # repetido: ignorado
    db.commit()


def test_recuperacion_de_trabajos_y_liberacion_de_canales(db):
    p = PlantaFreeswitch(nombre="Planta prueba recuperación", ip="127.0.0.1", capacidad_canales=2)
    db.add(p)
    db.flush()
    t = TroncalSIP(id_planta=p.id_planta, nombre="Troncal prueba", gateway="gw_prueba")
    db.add(t)
    db.flush()
    e = ExtensionSIP(id_planta=p.id_planta, id_troncal=t.id_troncal, numero="1001")
    db.add(e)
    db.flush()
    ll = Llamada(canal="TELEFONIA", modo="REAL", estado_tecnico="EN_CURSO", inicio=ahora_utc() - timedelta(hours=1))
    db.add(ll)
    db.flush()
    canal = CanalConcurrente(id_extension=e.id_extension, estado="OCUPADO", id_llamada=ll.id_llamada, ocupado_desde=ll.inicio)
    db.add(canal)
    tm = Trabajo(tipo="MARCAR", estado="EN_PROCESO", payload={}, clave_idempotencia="marcar:rec:1",
                 bloqueado_hasta=ahora_utc() - timedelta(minutes=1))
    tq = Trabajo(tipo="QA_LLAMADA", estado="EN_PROCESO", payload={"id_llamada": ll.id_llamada}, clave_idempotencia="qa:rec:1",
                 bloqueado_hasta=ahora_utc() - timedelta(minutes=1))
    db.add_all([tm, tq])
    db.commit()
    r = marcador.recuperar_tras_reinicio(db)
    db.commit()
    db.refresh(canal), db.refresh(ll), db.refresh(tm), db.refresh(tq)
    assert ll.estado_tecnico == "FALLIDA" and canal.estado == "LIBRE"
    assert tm.estado == "FALLIDO"  # no se re-marca automáticamente
    assert tq.estado == "PENDIENTE"  # tarea no telefónica: se reintenta
    assert r["canales_liberados"] >= 1


def test_persistencia_despues_de_reiniciar(admin):
    antes = admin.get("/api/clientes").json()["total"]
    reconfigurar(get_settings().database_url)  # simula reinicio: nuevo motor/pool de conexiones
    with SessionLocal() as db:
        assert parametros.obtener(db, "ventana_inicio") == "08:00"
    assert admin.get("/api/clientes").json()["total"] == antes > 0


def test_transiciones_de_estado_invalidas(admin):
    tramo = admin.get("/api/tramos").json()[0]
    c = admin.post("/api/campanas", json={"nombre": "Campaña transiciones", "id_tramo": tramo["id_tramo"]}).json()
    assert admin.post(f"/api/campanas/{c['id_campana']}/estado", json={"estado": "PAUSADA"}).status_code == 409
    assert admin.post(f"/api/campanas/{c['id_campana']}/estado", json={"estado": "FINALIZADA"}).status_code == 200
    assert admin.post(f"/api/campanas/{c['id_campana']}/estado", json={"estado": "ACTIVA"}).status_code == 409


def test_clasificacion_respeta_tramos(db):
    from app.models import Campana

    for c in db.execute(select(Campana)).scalars():
        for cc in db.execute(select(ClienteCampana).where(ClienteCampana.id_campana == c.id_campana)).scalars():
            assert c.tramo.dias_min <= cc.deuda.dias_mora <= c.tramo.dias_max


def test_respaldo_y_restauracion_cifrados(tmp_path, monkeypatch, admin):
    """Prueba con SQLite (copia de archivo). En MySQL se usa mysqldump/mysql: verificar manualmente (docs/RESPALDO.md)."""
    from cryptography.fernet import Fernet

    from app import respaldo

    monkeypatch.setenv("RESPALDO_CLAVE", Fernet.generate_key().decode())
    archivo = respaldo.crear(tmp_path)
    assert archivo.read_bytes()[:15] != b"SQLite format 3"  # el archivo está cifrado
    antes = admin.get("/api/clientes").json()["total"]
    admin.post("/api/clientes/importar", files={"archivo": ("extra.csv", io.BytesIO(
        b"documento,nombre,telefono,referencia,saldo,dias_mora\n5555666677778,Cliente Posterior,5555-7777,REF-X,100,5\n"), "text/csv")})
    assert admin.get("/api/clientes").json()["total"] == antes + 1
    from app.db import engine

    engine.dispose()
    respaldo.cargar(respaldo.descifrar(archivo))
    engine.dispose()
    assert admin.get("/api/clientes").json()["total"] == antes
    monkeypatch.setenv("RESPALDO_CLAVE", Fernet.generate_key().decode())
    with pytest.raises(SystemExit):
        respaldo.descifrar(archivo)  # clave incorrecta
