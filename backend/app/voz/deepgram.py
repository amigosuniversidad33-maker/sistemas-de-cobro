"""Cliente Deepgram (REST) para STT y TTS en español.

STT: POST https://api.deepgram.com/v1/listen   (audio pregrabado de un turno)
TTS: POST https://api.deepgram.com/v1/speak    (Aura-2, voces en español: aura-2-*-es)
Verificar modelos y voces vigentes en https://developers.deepgram.com antes de la demostración.
"""
import re
import time
from dataclasses import dataclass
from decimal import Decimal

import httpx
from sqlalchemy.orm import Session

from ..config import get_settings
from ..ia.proveedor import ErrorProveedor
from ..servicios import consumo
from .cifras import cifras_para_voz

URL_STT = "https://api.deepgram.com/v1/listen"
URL_TTS = "https://api.deepgram.com/v1/speak"
MIME_PERMITIDOS = {"audio/webm", "audio/ogg", "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp4", "audio/wave"}


@dataclass
class ResultadoSTT:
    texto: str
    confianza: float | None
    duracion_seg: float
    latencia_ms: int


@dataclass
class ResultadoTTS:
    audio: bytes
    mime: str
    latencia_ms: int


_COMA = re.compile(r"(?<!\d)\s*[,;]\s*|\s*[,;]\s*(?!\d)")


def texto_para_voz(texto: str) -> str:
    """Quita comas y punto y coma entre palabras: las voces hacen una pausa larga en cada una y suena lento.
    Se conservan los puntos y signos de pregunta (pausa entre oraciones). Los montos se dicen en palabras
    («catorce mil quinientos setenta y siete quetzales con sesenta y tres centavos»), así no se leen mal los miles ni los
    centavos. Solo cambia lo que se pronuncia; la transcripción guarda el texto original."""
    return re.sub(r"\s{2,}", " ", _COMA.sub(" ", cifras_para_voz(texto or ""))).strip()


def _cliente() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(get_settings().deepgram_timeout_seg, connect=10.0))


def _cabeceras(extra: dict | None = None) -> dict:
    s = get_settings()
    if not s.deepgram_api_key:
        raise ErrorProveedor("SIN_CREDENCIAL", "DEEPGRAM_API_KEY no está configurada en .env")
    h = {"Authorization": f"Token {s.deepgram_api_key}"}
    h.update(extra or {})
    return h


def stt(db: Session, audio: bytes, mime: str, id_llamada: int | None = None) -> ResultadoSTT:
    s = get_settings()
    base_mime = (mime or "").split(";")[0].strip().lower()
    if base_mime not in MIME_PERMITIDOS:
        raise ErrorProveedor("FORMATO_AUDIO", f"Tipo de audio no permitido: {base_mime}")
    if len(audio) > s.voz_max_audio_mb * 1024 * 1024:
        raise ErrorProveedor("AUDIO_GRANDE", "El audio excede el tamaño permitido")
    params = {"model": s.deepgram_stt_modelo, "language": s.deepgram_idioma, "smart_format": "true", "punctuate": "true"}
    t0 = time.monotonic()
    try:
        with _cliente() as c:
            r = c.post(URL_STT, params=params, content=audio, headers=_cabeceras({"Content-Type": base_mime}))
    except httpx.TimeoutException as e:
        consumo.registrar(db, proveedor="deepgram", servicio="STT", modelo=s.deepgram_stt_modelo, exito=False,
                          id_llamada=id_llamada, codigo_error="TIMEOUT")
        raise ErrorProveedor("TIMEOUT", "Deepgram STT", True) from e
    except httpx.HTTPError as e:
        consumo.registrar(db, proveedor="deepgram", servicio="STT", modelo=s.deepgram_stt_modelo, exito=False,
                          id_llamada=id_llamada, codigo_error="RED")
        raise ErrorProveedor("RED", "Deepgram STT", True) from e
    lat = int((time.monotonic() - t0) * 1000)
    if r.status_code != 200:
        consumo.registrar(db, proveedor="deepgram", servicio="STT", modelo=s.deepgram_stt_modelo, exito=False,
                          id_llamada=id_llamada, codigo_error=f"HTTP_{r.status_code}", latencia_ms=lat)
        raise ErrorProveedor(f"HTTP_{r.status_code}", "Deepgram STT")
    d = r.json()
    try:
        alt = d["results"]["channels"][0]["alternatives"][0]
        texto, conf = alt.get("transcript", ""), alt.get("confidence")
    except (KeyError, IndexError):
        texto, conf = "", None
    dur = float(d.get("metadata", {}).get("duration", 0) or 0)
    costo = Decimal(str(dur)) / Decimal(60) * s.deepgram_precio_stt_min
    consumo.registrar(db, proveedor="deepgram", servicio="STT", modelo=s.deepgram_stt_modelo, exito=True,
                      id_llamada=id_llamada, segundos_audio=dur, costo=costo, latencia_ms=lat)
    return ResultadoSTT(texto=texto.strip(), confianza=conf, duracion_seg=dur, latencia_ms=lat)


def tts(db: Session, texto: str, modelo: str | None = None, telefonia: bool = False,
        id_llamada: int | None = None, velocidad: float | None = None) -> ResultadoTTS:
    """telefonia=True devuelve WAV lineal 8 kHz mono (compatible con FreeSWITCH); si no, MP3 para navegador.

    velocidad (0.7 a 1.5, parámetro «speed» de Aura-2): si Deepgram no lo acepta, se repite sin él (voz a 1.0×).
    En el navegador la velocidad se aplica al reproducir, sin costo extra.
    """
    s = get_settings()
    modelo = modelo or s.deepgram_tts_modelo
    texto = texto_para_voz(texto)[:1500]
    if not texto:
        raise ErrorProveedor("TEXTO_VACIO", "")
    params = {"model": modelo}
    if telefonia:
        params.update(encoding="linear16", sample_rate="8000", container="wav")
    if velocidad is not None and abs(float(velocidad) - 1.0) >= 0.01:
        params["speed"] = f"{min(1.5, max(0.7, float(velocidad))):.2f}"
    t0 = time.monotonic()
    try:
        with _cliente() as c:
            r = c.post(URL_TTS, params=params, json={"text": texto}, headers=_cabeceras({"Content-Type": "application/json"}))
            if r.status_code == 400 and "speed" in params:  # la cuenta o el modelo no admiten «speed»
                params.pop("speed")
                r = c.post(URL_TTS, params=params, json={"text": texto}, headers=_cabeceras({"Content-Type": "application/json"}))
    except httpx.TimeoutException as e:
        consumo.registrar(db, proveedor="deepgram", servicio="TTS", modelo=modelo, exito=False, id_llamada=id_llamada,
                          codigo_error="TIMEOUT")
        raise ErrorProveedor("TIMEOUT", "Deepgram TTS", True) from e
    except httpx.HTTPError as e:
        consumo.registrar(db, proveedor="deepgram", servicio="TTS", modelo=modelo, exito=False, id_llamada=id_llamada,
                          codigo_error="RED")
        raise ErrorProveedor("RED", "Deepgram TTS", True) from e
    lat = int((time.monotonic() - t0) * 1000)
    if r.status_code != 200:
        consumo.registrar(db, proveedor="deepgram", servicio="TTS", modelo=modelo, exito=False, id_llamada=id_llamada,
                          codigo_error=f"HTTP_{r.status_code}", latencia_ms=lat)
        raise ErrorProveedor(f"HTTP_{r.status_code}", "Deepgram TTS")
    costo = Decimal(len(texto)) / Decimal(1000) * s.deepgram_precio_tts_1k_car
    consumo.registrar(db, proveedor="deepgram", servicio="TTS", modelo=modelo, exito=True, id_llamada=id_llamada,
                      caracteres=len(texto), costo=costo, latencia_ms=lat)
    return ResultadoTTS(audio=r.content, mime="audio/wav" if telefonia else r.headers.get("content-type", "audio/mpeg"),
                        latencia_ms=lat)


class SttEnVivo:
    """Reconocimiento en streaming (WebSocket) para llamadas: el audio se envía mientras el cliente habla y, al callar,
    el texto queda listo en unas décimas de segundo (en vez de subir la grabación completa al final del turno).

    WSS https://api.deepgram.com/v1/listen con PCM lineal de 16 bits. «Finalize» pide el resultado de lo recibido y
    «KeepAlive» evita que Deepgram cierre la conexión mientras habla el agente.
    """

    def __init__(self, id_llamada: int | None = None, sample_rate: int = 8000):
        from urllib.parse import urlencode

        from websockets.sync.client import connect

        s = get_settings()
        self.id_llamada, self.sample_rate, self.bytes_audio = id_llamada, sample_rate, 0
        self.partes: list[str] = []
        self.confianzas: list[float] = []
        params = urlencode({"model": s.deepgram_stt_modelo, "language": s.deepgram_idioma, "encoding": "linear16",
                            "sample_rate": sample_rate, "channels": 1, "punctuate": "true", "smart_format": "true"})
        try:
            self.ws = connect(f"wss://api.deepgram.com/v1/listen?{params}", additional_headers=_cabeceras(),
                              open_timeout=6, close_timeout=2)
        except Exception as e:  # red, credencial o protocolo: el turno usa el reconocimiento normal
            raise ErrorProveedor("STREAM", f"Deepgram en vivo: {type(e).__name__}", True) from e

    def enviar(self, pcm: bytes) -> None:
        if pcm:
            try:
                self.ws.send(pcm)
                self.bytes_audio += len(pcm)
            except Exception as e:
                raise ErrorProveedor("STREAM", f"Deepgram en vivo: {type(e).__name__}", True) from e

    def mantener(self) -> None:
        try:
            self.ws.send('{"type": "KeepAlive"}')
        except Exception:
            pass

    def terminar(self, db: Session, espera_seg: float = 3.0) -> ResultadoSTT:
        import json

        t0 = time.monotonic()
        try:
            self.ws.send('{"type": "Finalize"}')
            while time.monotonic() - t0 < espera_seg:
                d = json.loads(self.ws.recv(timeout=max(0.05, espera_seg - (time.monotonic() - t0))))
                if d.get("type") != "Results":
                    continue
                alt = d["channel"]["alternatives"][0]
                if d.get("is_final") and alt.get("transcript"):
                    self.partes.append(alt["transcript"])
                    if alt.get("confidence") is not None:
                        self.confianzas.append(alt["confidence"])
                if d.get("from_finalize"):
                    break
        except TimeoutError:
            pass
        except Exception as e:
            raise ErrorProveedor("STREAM", f"Deepgram en vivo: {type(e).__name__}", True) from e
        finally:
            self.cerrar()
        s = get_settings()
        dur = self.bytes_audio / (2 * self.sample_rate)
        lat = int((time.monotonic() - t0) * 1000)
        consumo.registrar(db, proveedor="deepgram", servicio="STT", modelo=s.deepgram_stt_modelo, exito=True,
                          id_llamada=self.id_llamada, segundos_audio=dur, latencia_ms=lat,
                          costo=Decimal(str(dur)) / Decimal(60) * s.deepgram_precio_stt_min)
        conf = sum(self.confianzas) / len(self.confianzas) if self.confianzas else None
        return ResultadoSTT(texto=" ".join(self.partes).strip(), confianza=conf, duracion_seg=dur, latencia_ms=lat)

    def cerrar(self) -> None:
        try:
            self.ws.send('{"type": "CloseStream"}')
            self.ws.close()
        except Exception:
            pass
