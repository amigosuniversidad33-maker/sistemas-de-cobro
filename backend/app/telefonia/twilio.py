"""Llamada telefónica real de prueba mediante Twilio Programmable Voice (alternativa a FreeSWITCH/SIP para el piloto).

Flujo: el sistema pide a Twilio que llame al número autorizado → Twilio solicita instrucciones (TwiML) a
URL_PUBLICA/api/twilio/voz/{id} → el agente habla con <Say> (voz neuronal) y escucha con <Gather input="speech">
→ cada respuesta del cliente pasa por el mismo motor del agente (herramientas validadas + guardrails).

Voz: por defecto el agente habla con su voz Deepgram Aura-2 (audio servido por <Play> desde un enlace de un solo uso),
a la velocidad configurada en el agente; si Deepgram no responde, ese turno se dice con <Say> y SSML <prosody>.

Requisitos: cuenta Twilio (la de prueba sirve, solo llama a números verificados en Twilio), un número Twilio y una
URL pública HTTPS hacia este equipo (por ejemplo ngrok). Ver docs/TWILIO.md.
"""
import base64
import hashlib
import hmac
import secrets
import threading
import time
from xml.sax.saxutils import escape, quoteattr

import httpx

from ..config import get_settings
from ..voz.deepgram import texto_para_voz

API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"


class ErrorTwilio(Exception):
    pass


_ngrok_cache: tuple[float, str] = (0.0, "")


def _url_ngrok() -> str:
    """URL https del túnel abierto con «ngrok http 8000» (API local de ngrok, solo este equipo). Se guarda 60 s."""
    global _ngrok_cache
    if time.monotonic() - _ngrok_cache[0] < 60:
        return _ngrok_cache[1]
    url = ""
    try:
        r = httpx.get(get_settings().ngrok_api_url, timeout=1.5)
        for t in r.json().get("tunnels", []):
            destino = str(t.get("config", {}).get("addr", ""))
            if t.get("public_url", "").startswith("https://") and destino.endswith(str(get_settings().app_port)):
                url = t["public_url"]
                break
    except (httpx.HTTPError, ValueError):
        url = ""
    _ngrok_cache = (time.monotonic(), url)
    return url


def base_publica() -> str:
    return (get_settings().url_publica or _url_ngrok()).rstrip("/")


def configurado() -> list[str]:
    """Devuelve lo que falta configurar (lista vacía = listo)."""
    s = get_settings()
    faltan = []
    if not s.twilio_account_sid:
        faltan.append("TWILIO_ACCOUNT_SID")
    if not s.twilio_auth_token:
        faltan.append("TWILIO_AUTH_TOKEN")
    if not s.twilio_numero:
        faltan.append("TWILIO_NUMERO (número comprado o de prueba en Twilio)")
    if not base_publica().startswith("https://"):
        faltan.append("URL pública: abra una terminal y ejecute «ngrok http 8000» (o escriba URL_PUBLICA)")
    return faltan


def firma_valida(url: str, parametros: dict, firma: str) -> bool:
    """Valida la cabecera X-Twilio-Signature (HMAC-SHA1 de URL + parámetros ordenados, en base64)."""
    token = get_settings().twilio_auth_token
    if not token or not firma:
        return False
    datos = url + "".join(f"{k}{parametros[k]}" for k in sorted(parametros))
    esperado = base64.b64encode(hmac.new(token.encode(), datos.encode("utf-8"), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(esperado, firma)


def url_publica(ruta: str) -> str:
    return base_publica() + ruta


def iniciar_llamada(destino_e164: str, id_llamada: int) -> str:
    """Pide a Twilio que origine la llamada. Devuelve el CallSid."""
    s = get_settings()
    faltan = configurado()
    if faltan:
        raise ErrorTwilio("Falta configurar: " + ", ".join(faltan))
    datos = {
        "To": destino_e164,
        "From": s.twilio_numero,
        "Url": url_publica(f"/api/twilio/voz/{id_llamada}"),
        "Method": "POST",
        "StatusCallback": url_publica(f"/api/twilio/estado/{id_llamada}"),
        "StatusCallbackMethod": "POST",
        "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
        "Timeout": "40",
        "TimeLimit": str(s.max_duracion_conversacion_seg),
    }
    try:
        r = httpx.post(API.format(sid=s.twilio_account_sid), data=datos,
                       auth=(s.twilio_account_sid, s.twilio_auth_token), timeout=20)
    except httpx.HTTPError as e:
        raise ErrorTwilio(f"No se pudo contactar a Twilio: {type(e).__name__}") from e
    if r.status_code not in (200, 201):
        try:
            detalle = r.json().get("message", "")
        except ValueError:
            detalle = r.text[:200]
        raise ErrorTwilio(f"Twilio rechazó la llamada ({r.status_code}): {detalle}")
    return r.json()["sid"]


# ------------------------------------------------------------------ audio Deepgram para <Play>
_audios: dict[str, tuple[float, bytes, str]] = {}
_candado = threading.Lock()
VIDA_AUDIO_SEG = 300


def guardar_audio(audio: bytes, mime: str) -> str:
    """Guarda en memoria el audio de un turno y devuelve un token aleatorio (expira en 5 minutos)."""
    token = secrets.token_urlsafe(24)
    ahora = time.monotonic()
    with _candado:
        for k in [k for k, v in _audios.items() if ahora - v[0] > VIDA_AUDIO_SEG]:
            del _audios[k]
        _audios[token] = (ahora, audio, mime)
    return token


def obtener_audio(token: str) -> tuple[bytes, str] | None:
    with _candado:
        v = _audios.get(token)
    if v is None or time.monotonic() - v[0] > VIDA_AUDIO_SEG:
        return None
    return v[1], v[2]


# ------------------------------------------------------------------ TwiML
def _say(texto: str, velocidad: float = 1.0) -> str:
    s = get_settings()
    cuerpo = escape(texto_para_voz(texto))
    if abs(float(velocidad) - 1.0) >= 0.01:  # SSML admitido por las voces Polly de Twilio
        cuerpo = f'<prosody rate="{round(float(velocidad) * 100)}%">{cuerpo}</prosody>'
    return f"<Say voice={quoteattr(s.twilio_voz)} language={quoteattr(s.twilio_idioma)}>{cuerpo}</Say>"


def habla(texto: str, velocidad: float = 1.0, token_audio: str | None = None) -> str:
    """Fragmento TwiML con lo que dice el agente: audio Deepgram (<Play>) o voz de Twilio (<Say>)."""
    if token_audio:
        return f"<Play>{escape(url_publica(f'/api/twilio/audio/{token_audio}'))}</Play>"
    return _say(texto, velocidad)


def twiml_hablar_y_escuchar(fragmento: str, id_llamada: int) -> str:
    s = get_settings()
    accion = url_publica(f"/api/twilio/voz/{id_llamada}")
    return ('<?xml version="1.0" encoding="UTF-8"?><Response>'
            f'<Gather input="speech" language={quoteattr(s.twilio_idioma)} speechTimeout="auto" timeout="7" '
            f'actionOnEmptyResult="true" action={quoteattr(accion)} method="POST">{fragmento}</Gather>'
            f'<Redirect method="POST">{escape(accion)}</Redirect></Response>')


def twiml_hablar_y_colgar(fragmento: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{fragmento}<Hangup/></Response>'


def clasificar_estado(estado: str) -> tuple[str, str | None]:
    """Estado final de Twilio → (estado_tecnico, resultado_contacto)."""
    if estado in ("no-answer", "busy", "canceled"):
        return "FINALIZADA", "SIN_CONTESTAR"
    if estado == "failed":
        return "FALLIDA", None
    return "FINALIZADA", None
