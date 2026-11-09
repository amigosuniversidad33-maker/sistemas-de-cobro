"""Protocolo ESL contra un servidor Event Socket SIMULADO (no es FreeSWITCH real).

Valida autenticación, construcción segura de comandos, clasificación de resultados y liberación de canales.
La llamada real a un número autorizado debe verificarse con FreeSWITCH y troncal SIP (docs/FREESWITCH.md).
"""
import socket
import threading

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    CanalConcurrente,
    ClienteCampana,
    ExtensionSIP,
    Llamada,
    NumeroAutorizado,
    PlantaFreeswitch,
    Trabajo,
    TroncalSIP,
)
from app.telefonia import marcador
from app.telefonia.esl import ClienteESL, ErrorESL, cmd_originate, cmd_uuid


class ESLSimulado(threading.Thread):
    def __init__(self, respuesta_originate: str):
        super().__init__(daemon=True)
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(5)
        self.puerto = self.srv.getsockname()[1]
        self.respuesta = respuesta_originate
        self.comandos: list[str] = []

    def run(self):
        while True:
            try:
                con, _ = self.srv.accept()
            except OSError:
                return
            try:
                self._atender(con)
            except OSError:
                pass
            finally:
                con.close()

    def _atender(self, con):
        con.sendall(b"Content-Type: auth/request\n\n")
        buf = b""
        while True:
            datos = con.recv(4096)
            if not datos:
                return
            buf += datos
            while b"\n\n" in buf:
                cmd, buf = buf.split(b"\n\n", 1)
                linea = cmd.decode()
                self.comandos.append(linea)
                if linea.startswith("auth "):
                    ok = linea == "auth ClaveESL-prueba"
                    con.sendall(f"Content-Type: command/reply\nReply-Text: {'+OK accepted' if ok else '-ERR invalid'}\n\n".encode())
                    if not ok:
                        return
                elif linea.startswith("api "):
                    cuerpo = (self.respuesta if "originate" in linea else "+OK").encode()
                    con.sendall(b"Content-Type: api/response\nContent-Length: " + str(len(cuerpo)).encode() + b"\n\n" + cuerpo)
                elif linea == "exit":
                    return


@pytest.fixture
def esl_config(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "telefonia_habilitada", True)
    monkeypatch.setattr(s, "freeswitch_esl_password", "ClaveESL-prueba")
    monkeypatch.setattr(s, "freeswitch_dir_audio", "/tmp")
    return s


def test_comandos_validados():
    c = cmd_originate("123e4567-e89b-12d3-a456-426614174000", "gw_prueba", "+50255550000", 7, 45)
    assert c.startswith("originate {origination_uuid=123e4567") and c.endswith("sofia/gateway/gw_prueba/+50255550000 &park()")
    with pytest.raises(ErrorESL):
        cmd_originate("123e4567-e89b-12d3-a456-426614174000", "gw; rm -rf", "+50255550000", 7, 45)
    with pytest.raises(ErrorESL):
        cmd_originate("123e4567-e89b-12d3-a456-426614174000", "gw", "5555 &bridge(x)", 7, 45)
    with pytest.raises(ErrorESL):
        cmd_uuid("system", "123e4567-e89b-12d3-a456-426614174000")


def test_host_publico_rechazado():
    with pytest.raises(ErrorESL):
        ClienteESL("8.8.8.8", 8021, "x")


def test_autenticacion_esl():
    srv = ESLSimulado("+OK")
    srv.start()
    with ClienteESL("127.0.0.1", srv.puerto, "ClaveESL-prueba") as c:
        assert c.api("status") == "+OK"
    with pytest.raises(ErrorESL):
        ClienteESL("127.0.0.1", srv.puerto, "clave-mala").conectar()


def _cc_nuevo(db, sufijo: int) -> ClienteCampana:
    """Cliente, deuda y campaña ACTIVA nuevos (ficticios) para no depender del estado de otras pruebas."""
    from datetime import timedelta
    from decimal import Decimal

    from app.models import AgenteIA, Campana, CampanaAgente, Cliente, Deuda, TramoMora
    from app.utils import hoy_local

    tramo = db.execute(select(TramoMora).where(TramoMora.codigo == "MORA_TEMPRANA")).scalar_one()
    ag = next(a for a in db.execute(select(AgenteIA)).scalars() if a.guion and a.guion.tramo == "MORA_TEMPRANA")
    cli = Cliente(nombre=f"Cliente Telefonía {sufijo}", documento=f"77{sufijo:011d}", telefono=f"+5025{sufijo % 10000000:07d}",
                  telefono_valido=True)
    db.add(cli)
    db.flush()
    d = Deuda(id_cliente=cli.id_cliente, referencia=f"TEL-{sufijo}", saldo=Decimal("900.00"), dias_mora=12, tramo="MORA_TEMPRANA")
    camp = Campana(nombre=f"Campaña telefonía {sufijo}", id_tramo=tramo.id_tramo, estado="ACTIVA", hora_inicio="00:00",
                   hora_fin="23:59", fecha_inicio=hoy_local() - timedelta(days=1), fecha_fin=hoy_local() + timedelta(days=1),
                   mensaje_base="Prueba")
    db.add_all([d, camp])
    db.flush()
    db.add(CampanaAgente(id_campana=camp.id_campana, id_agente=ag.id_agente))
    cc = ClienteCampana(id_cliente=cli.id_cliente, id_campana=camp.id_campana, id_deuda=d.id_deuda)
    db.add(cc)
    db.flush()
    db.refresh(camp)
    return cc


def _preparar(db, puerto: int) -> Trabajo:
    p = PlantaFreeswitch(nombre=f"Planta ESL {puerto}", ip="127.0.0.1", puerto_esl=puerto, capacidad_canales=1)
    db.add(p)
    db.flush()
    t = TroncalSIP(id_planta=p.id_planta, nombre=f"Troncal ESL {puerto}", gateway="gw_prueba")
    db.add(t)
    db.flush()
    e = ExtensionSIP(id_planta=p.id_planta, id_troncal=t.id_troncal, numero=str(puerto)[-4:])
    db.add(e)
    db.flush()
    db.add(CanalConcurrente(id_extension=e.id_extension))
    # Otros canales de pruebas previas se bloquean para forzar el uso de esta planta
    for c in db.execute(select(CanalConcurrente).join(ExtensionSIP).where(ExtensionSIP.id_planta != p.id_planta)).scalars():
        c.estado = "BLOQUEADO"
    cc = _cc_nuevo(db, puerto)
    if db.execute(select(NumeroAutorizado).where(NumeroAutorizado.telefono == cc.cliente.telefono)).first() is None:
        db.add(NumeroAutorizado(telefono=cc.cliente.telefono, descripcion="Número de prueba"))
    tr = Trabajo(tipo="MARCAR", payload={"id_cliente_campana": cc.id}, clave_idempotencia=f"marcar:{cc.id}:esl{puerto}")
    db.add(tr)
    db.commit()
    return tr


def test_originate_sin_respuesta_libera_canal(admin, esl_config):
    srv = ESLSimulado("-ERR NO_ANSWER")
    srv.start()
    with SessionLocal() as db:
        tr = _preparar(db, srv.puerto)
        res = marcador.procesar_marcar(db, tr)
        assert res == "FINALIZADO:NO_ANSWER"
        ll = db.execute(select(Llamada).where(Llamada.canal == "TELEFONIA").order_by(Llamada.id_llamada.desc())).scalars().first()
        assert ll.estado_tecnico == "FINALIZADA" and ll.resultado_contacto == "SIN_CONTESTAR"
        assert db.get(CanalConcurrente, ll.id_canal).estado == "LIBRE"
        assert any(c.startswith("api originate {origination_uuid=") for c in srv.comandos)


def test_fallo_tecnico_no_cuenta_como_sin_contestar(admin, esl_config):
    srv = ESLSimulado("-ERR GATEWAY_DOWN")
    srv.start()
    with SessionLocal() as db:
        tr = _preparar(db, srv.puerto)
        assert marcador.procesar_marcar(db, tr) == "FINALIZADO:GATEWAY_DOWN"
        ll = db.execute(select(Llamada).where(Llamada.canal == "TELEFONIA").order_by(Llamada.id_llamada.desc())).scalars().first()
        assert ll.estado_tecnico == "FALLIDA" and ll.resultado_contacto is None
        assert db.get(CanalConcurrente, ll.id_canal).estado == "LIBRE"


def test_numero_no_autorizado_no_se_marca(admin, esl_config):
    with SessionLocal() as db:
        cc = _cc_nuevo(db, 4242)
        tr = Trabajo(tipo="MARCAR", payload={"id_cliente_campana": cc.id}, clave_idempotencia=f"marcar:{cc.id}:noaut")
        db.add(tr)
        db.commit()
        assert marcador.procesar_marcar(db, tr) == "CANCELADO:NUMERO_NO_AUTORIZADO_PARA_PILOTO"


def test_llamada_a_extension_zoiper(admin, db, monkeypatch):
    """Extensión interna (sin troncal): se encola LLAMAR_EXTENSION; una extensión con troncal se rechaza."""
    from app.models import Deuda, Trabajo, TroncalSIP
    from app.telefonia.esl import ErrorESL, cmd_originate_extension

    s = get_settings()
    for k, v in {"telefonia_habilitada": True, "freeswitch_esl_password": "x", "freeswitch_dir_audio": "C:/cobros_audio",
                 "deepgram_api_key": "dg"}.items():
        monkeypatch.setattr(s, k, v)
    planta = PlantaFreeswitch(nombre="VM Zoiper prueba", ip="192.168.1.50", puerto_esl=8021, capacidad_canales=4)
    db.add(planta)
    db.flush()
    troncal = TroncalSIP(id_planta=planta.id_planta, nombre="Troncal zoiper prueba", gateway="gw_x", max_canales=1)
    db.add(troncal)
    db.flush()
    interna = ExtensionSIP(id_planta=planta.id_planta, numero="1000", canales_max=1)
    externa = ExtensionSIP(id_planta=planta.id_planta, id_troncal=troncal.id_troncal, numero="1500", canales_max=1)
    db.add_all([interna, externa])
    db.commit()
    lista = admin.get("/api/telefonia/extensiones-internas").json()
    assert lista["faltan"] == [] and "1000" in [e["numero"] for e in lista["extensiones"]]
    assert "1500" not in [e["numero"] for e in lista["extensiones"]]
    d = db.execute(select(Deuda).where(Deuda.estado == "ACTIVA")).scalars().first()
    ag = admin.get("/api/agentes").json()[0]
    cuerpo = {"id_agente": ag["id_agente"], "id_deuda": d.id_deuda}
    assert admin.post("/api/telefonia/llamar-extension", json={**cuerpo, "id_extension": externa.id_extension}).status_code == 403
    r = admin.post("/api/telefonia/llamar-extension", json={**cuerpo, "id_extension": interna.id_extension})
    assert r.status_code == 201, r.text
    id_ll = r.json()["id_llamada"]
    t = db.execute(select(Trabajo).where(Trabajo.clave_idempotencia == f"LLAMAR_EXTENSION:{id_ll}")).scalar_one()
    assert t.payload == {"id_llamada": id_ll, "id_extension": interna.id_extension}
    db.get(Llamada, id_ll).estado_tecnico = "FINALIZADA"  # no deja ocupado el límite del piloto para otras pruebas
    t.estado = "CANCELADO"
    db.commit()
    uuid = "0" * 8 + "-0000-0000-0000-" + "0" * 12
    assert cmd_originate_extension(uuid, "1000", 5, 30).endswith("}user/1000 &park()")
    with pytest.raises(ErrorESL):
        cmd_originate_extension(uuid, "1000@otro", 5, 30)


def test_ruta_de_audio_vista_por_la_vm(monkeypatch):
    from pathlib import Path

    from app.telefonia.marcador import ruta_freeswitch

    s = get_settings()
    monkeypatch.setattr(s, "freeswitch_dir_audio_remoto", "/mnt/cobros_audio/")
    assert ruta_freeswitch(Path("C:/cobros_audio/abc_a1.wav")) == "/mnt/cobros_audio/abc_a1.wav"
    monkeypatch.setattr(s, "freeswitch_dir_audio_remoto", "")
    assert ruta_freeswitch(Path("/cobros_audio/abc_a1.wav")) == str(Path("/cobros_audio/abc_a1.wav"))


def test_worker_extension_no_registrada_libera_canal(admin, esl_config):
    """Zoiper desconectado: FreeSWITCH responde USER_NOT_REGISTERED; la llamada falla con motivo claro y el canal se libera."""
    from app.ia import agente as motor
    from app.models import AgenteIA, Deuda

    srv = ESLSimulado("-ERR USER_NOT_REGISTERED")
    srv.start()
    with SessionLocal() as db:
        p = PlantaFreeswitch(nombre=f"VM ESL {srv.puerto}", ip="127.0.0.1", puerto_esl=srv.puerto, capacidad_canales=1)
        db.add(p)
        db.flush()
        e = ExtensionSIP(id_planta=p.id_planta, numero="1001")
        db.add(e)
        db.flush()
        db.add(CanalConcurrente(id_extension=e.id_extension))
        ag = db.execute(select(AgenteIA).where(AgenteIA.activo.is_(True), AgenteIA.id_guion.is_not(None))).scalars().first()
        d = db.execute(select(Deuda).where(Deuda.estado == "ACTIVA")).scalars().first()
        ll = motor.iniciar(db, agente=ag, cliente=d.cliente, deuda=d, canal="TELEFONIA", modo="PRUEBA")
        tr = Trabajo(tipo="LLAMAR_EXTENSION", payload={"id_llamada": ll.id_llamada, "id_extension": e.id_extension},
                     clave_idempotencia=f"LLAMAR_EXTENSION:prueba:{srv.puerto}")
        db.add(tr)
        db.commit()
        res = marcador.procesar_llamar_extension(db, tr)
        assert res.startswith("FINALIZADO:USER_NOT_REGISTERED")
        db.refresh(ll)
        assert ll.estado_tecnico == "FALLIDA" and "Zoiper" in ll.motivo_fallo
        assert db.get(CanalConcurrente, ll.id_canal).estado == "LIBRE"
        assert any("}user/1001 &park()" in c for c in srv.comandos)


@pytest.mark.parametrize("ruido", [200, 900])
def test_fin_de_turno_por_silencio(monkeypatch, tmp_path, ruido):
    """El turno del cliente termina al callar (no tras una ventana fija), también con ruido de fondo alto."""
    import array as arr
    import time as t

    s = get_settings()
    monkeypatch.setattr(s, "telefonia_silencio_fin_seg", 0.5)
    monkeypatch.setattr(s, "telefonia_espera_inicio_seg", 3.0)
    monkeypatch.setattr(s, "telefonia_max_segundos_turno", 10)
    grab = tmp_path / "x_c1.wav"
    voz = arr.array("h", [6000, -6000] * 2000).tobytes()  # 0.5 s de "voz" a 8 kHz
    silencio = arr.array("h", [ruido, -ruido] * 2000).tobytes()  # 0.5 s de ruido de fondo
    inicio = t.monotonic()

    class Fuente:
        def leer_desde(self, archivo, pos):
            transcurrido = t.monotonic() - inicio
            contenido = (b"\0" * 44 + silencio + (voz if transcurrido > 0.3 else b"")
                         + (silencio * 3 if transcurrido > 0.6 else b""))
            return contenido[pos:]

    marcador.esperar_fin_de_habla(Fuente(), grab)
    assert t.monotonic() - inicio < 2.5  # terminó por silencio, mucho antes del máximo


def test_wav_leido_mientras_se_grababa_queda_con_tamanos_correctos():
    cab = bytearray(b"RIFF" + bytes(4) + b"WAVEfmt " + (16).to_bytes(4, "little") + bytes(16) + b"data" + bytes(4))
    wav = marcador.wav_completo(bytes(cab) + b"\x01\x00" * 100)
    assert int.from_bytes(wav[40:44], "little") == 200 and int.from_bytes(wav[4:8], "little") == len(wav) - 8


def test_respuesta_del_agente_se_divide_en_frases():
    f = marcador.dividir_frases("Gracias por confirmar. Su saldo pendiente es de Q 14,577.63, con 30 días de atraso. "
                                "¿Cuánto y en qué fecha puede pagar?")
    assert f[0].startswith("Gracias por confirmar. Su saldo") and len(f) == 2  # la muy corta se une a la siguiente
    assert "14,577.63" in f[0] and f[-1].endswith("?")


def test_event_socket_por_tunel_ssh_solo_para_la_vm(monkeypatch):
    """Con FREESWITCH_SSH_DESTINO, la planta de esa VM usa el túnel SSH; otra planta conecta directo."""
    s = get_settings()
    monkeypatch.setattr(s, "freeswitch_ssh_destino", "cobros@10.0.0.5")
    monkeypatch.setattr(s, "freeswitch_esl_password", "x")
    assert marcador.cliente_esl(PlantaFreeswitch(ip="10.0.0.5", puerto_esl=8021)).abrir is not None
    assert marcador.cliente_esl(PlantaFreeswitch(ip="10.0.0.9", puerto_esl=8021)).abrir is None
