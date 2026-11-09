"""Llamada real de prueba con Twilio: se simulan la API REST y los webhooks firmados (no se llama a Twilio real)."""
import base64
import hashlib
import hmac

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.ia import proveedor as prov_mod
from app.ia.local import ProveedorLocal
from app.models import Deuda, Llamada, NumeroAutorizado, PromesaPago
from app.telefonia import twilio

URL = "https://prueba-cobros.ngrok.app"


@pytest.fixture
def tw(monkeypatch):
    s = get_settings()
    for k, v in {"twilio_account_sid": "ACprueba", "twilio_auth_token": "token-prueba", "twilio_numero": "+15005550006",
                 "url_publica": URL, "twilio_motor_voz": "twilio"}.items():
        monkeypatch.setattr(s, k, v)
    llamadas = []

    def falso_iniciar(destino, id_llamada):
        llamadas.append((destino, id_llamada))
        return f"CA{id_llamada:032d}"

    monkeypatch.setattr(twilio, "iniciar_llamada", falso_iniciar)
    prov_mod.establecer_proveedor(ProveedorLocal())
    yield llamadas
    prov_mod.establecer_proveedor(None)


def _firma(ruta, datos):
    base = URL + ruta + "".join(f"{k}{datos[k]}" for k in sorted(datos))
    return base64.b64encode(hmac.new(b"token-prueba", base.encode(), hashlib.sha1).digest()).decode()


def _webhook(cliente, ruta, datos, firma=None):
    return cliente.post(ruta, data=datos, headers={"X-Twilio-Signature": firma or _firma(ruta, datos)})


def test_llamada_completa_con_promesa(admin, db, tw):
    db.add(NumeroAutorizado(telefono="+50255501234", descripcion="Celular del equipo (prueba)"))
    db.commit()
    d = db.execute(select(Deuda).where(Deuda.tramo == "MORA_TEMPRANA", Deuda.estado == "ACTIVA")).scalars().first()
    ag = next(a for a in admin.get("/api/agentes").json() if a["tramo"] == "MORA_TEMPRANA")
    assert admin.post("/api/twilio/llamar", json={"id_agente": ag["id_agente"], "id_deuda": d.id_deuda,
                                                  "telefono": "5550-9999"}).status_code == 403  # no autorizado
    r = admin.post("/api/twilio/llamar", json={"id_agente": ag["id_agente"], "id_deuda": d.id_deuda, "telefono": "5550-1234"})
    assert r.status_code == 201, r.text
    id_ll = r.json()["id_llamada"]
    sid = f"CA{id_ll:032d}"
    assert tw == [("+50255501234", id_ll)]
    ruta = f"/api/twilio/voz/{id_ll}"
    # Firma inválida → rechazado
    assert _webhook(admin, ruta, {"CallSid": sid}, firma="falsa").status_code == 403
    x = _webhook(admin, ruta, {"CallSid": sid}).text
    assert "<Gather" in x and "le saluda" in x and "Polly.Mia-Neural" in x
    x = _webhook(admin, ruta, {"CallSid": sid, "SpeechResult": f"Sí soy yo, mis dígitos son {d.cliente.documento[-4:]}"}).text
    assert "saldo pendiente" in x
    x = _webhook(admin, ruta, {"CallSid": sid, "SpeechResult": f"Puedo pagar {int(d.saldo / 2)} quetzales mañana"}).text
    assert "Lo confirma" in x
    x = _webhook(admin, ruta, {"CallSid": sid, "SpeechResult": "Sí, confirmo", "Confidence": "0.91"}).text
    assert "<Hangup/>" in x and "quedó registrada" in x
    assert _webhook(admin, f"/api/twilio/estado/{id_ll}", {"CallSid": sid, "CallStatus": "completed", "CallDuration": "48"}).status_code == 204
    db.expire_all()
    ll = db.get(Llamada, id_ll)
    assert ll.canal == "TELEFONIA" and ll.estado_tecnico == "FINALIZADA" and ll.resultado_contacto == "CONTESTADA"
    assert db.execute(select(PromesaPago).where(PromesaPago.id_llamada == id_ll)).scalar_one()


def test_sin_respuesta_no_cuenta_como_contestada(admin, db, tw):
    d = db.execute(select(Deuda).where(Deuda.estado == "ACTIVA")).scalars().first()
    ag = admin.get("/api/agentes").json()[0]
    r = admin.post("/api/twilio/llamar", json={"id_agente": ag["id_agente"], "id_deuda": d.id_deuda, "telefono": "5550-1234"})
    id_ll = r.json()["id_llamada"]
    _webhook(admin, f"/api/twilio/estado/{id_ll}", {"CallSid": f"CA{id_ll:032d}", "CallStatus": "no-answer"})
    db.expire_all()
    ll = db.get(Llamada, id_ll)
    assert ll.estado_tecnico == "FINALIZADA" and ll.resultado_contacto == "SIN_CONTESTAR"


def test_tunel_publico_solo_expone_webhooks(admin):
    r = admin.get("/api/usuarios", headers={"X-Forwarded-For": "8.8.8.8"})
    assert r.status_code == 403
    r = admin.get("/", headers={"Host": "prueba-cobros.ngrok.app"})
    assert r.status_code == 403


def test_falta_configuracion(admin, monkeypatch):
    s = get_settings()
    for k, v in {"twilio_account_sid": "", "url_publica": "", "ngrok_api_url": "http://127.0.0.1:9/sin-ngrok"}.items():
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr(twilio, "_ngrok_cache", (0.0, ""))
    faltan = admin.get("/api/twilio/estado-configuracion").json()["faltan"]
    assert any("TWILIO_ACCOUNT_SID" in f for f in faltan)


def test_voz_deepgram_y_velocidad_del_agente(admin, db, tw, monkeypatch):
    from app.models import AgenteIA
    from app.routers import twilio as rt
    from app.voz.deepgram import ResultadoTTS

    s = get_settings()
    monkeypatch.setattr(s, "twilio_motor_voz", "deepgram")
    monkeypatch.setattr(s, "deepgram_api_key", "dg-prueba")
    pedidos = []

    def falso_tts(db_, texto, modelo=None, telefonia=False, id_llamada=None, velocidad=None):
        pedidos.append((modelo, float(velocidad)))
        return ResultadoTTS(audio=b"ID3audio", mime="audio/mpeg", latencia_ms=5)

    monkeypatch.setattr(rt.deepgram, "tts", falso_tts)
    if db.execute(select(NumeroAutorizado).where(NumeroAutorizado.telefono == "+50255501234")).first() is None:
        db.add(NumeroAutorizado(telefono="+50255501234", descripcion="Celular del equipo (prueba)"))
        db.commit()
    d = db.execute(select(Deuda).where(Deuda.estado == "ACTIVA")).scalars().first()
    ag = admin.get("/api/agentes").json()[0]
    assert admin.put(f"/api/agentes/{ag['id_agente']}/velocidad", json={"velocidad_voz": 2}).status_code == 422
    assert admin.put(f"/api/agentes/{ag['id_agente']}/velocidad", json={"velocidad_voz": 0.9}).json()["velocidad_voz"] == "0.90"
    id_ll = admin.post("/api/twilio/llamar", json={"id_agente": ag["id_agente"], "id_deuda": d.id_deuda,
                                                   "telefono": "5550-1234"}).json()["id_llamada"]
    ruta = f"/api/twilio/voz/{id_ll}"
    x = _webhook(admin, ruta, {"CallSid": f"CA{id_ll:032d}"}).text
    assert "<Play>" in x and "<Say" not in x
    assert pedidos == [(db.get(AgenteIA, ag["id_agente"]).voz_deepgram, 0.9)]
    token = x.split("/api/twilio/audio/")[1].split("<")[0]
    r = admin.get(f"/api/twilio/audio/{token}")
    assert r.status_code == 200 and r.content == b"ID3audio"
    assert admin.get("/api/twilio/audio/inventado").status_code == 404


def test_voz_twilio_con_velocidad_usa_prosody():
    assert '<prosody rate="85%">' in twilio.habla("Hola", 0.85)
    assert "<prosody" not in twilio.habla("Hola", 1.0)


def test_voz_sin_pausas_por_comas():
    from app.voz.deepgram import texto_para_voz

    assert texto_para_voz("Buen día, le saluda Sofía, de Financiera Progreso.") == "Buen día le saluda Sofía de Financiera Progreso."
    assert texto_para_voz("Su saldo es Q1,500.00, gracias.") == "Su saldo es Q1,500.00 gracias."
    assert "," not in twilio.habla("Hola, ¿me escucha?")
