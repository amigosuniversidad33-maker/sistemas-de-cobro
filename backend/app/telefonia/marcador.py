"""Marcador piloto (DS-04, DF-05, DF-06). Un canal concurrente por defecto.

Flujo: re-verificación de reglas -> reserva de canal -> originate (ESL) -> conversación por turnos
(TTS WAV -> uuid_broadcast ; uuid_record -> STT -> agente -> guardrails) -> liberación del canal.
"""
import array
import logging
import math
import re
import threading
import time
import uuid as uuidlib
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import parametros
from ..config import get_settings
from ..db import SessionLocal
from ..ia import agente as motor
from ..ia.proveedor import ErrorProveedor
from ..models import (
    Alerta,
    CanalConcurrente,
    ClienteCampana,
    EventoLlamada,
    ExtensionSIP,
    Llamada,
    NoContactable,
    NumeroAutorizado,
    PlantaFreeswitch,
    Trabajo,
    TroncalSIP,
    ahora_utc,
)
from ..servicios import campanas as srv_campanas
from ..servicios import reglas
from ..utils import enmascarar_telefono
from ..voz import deepgram
from .esl import ClienteESL, ErrorESL, cmd_originate, cmd_originate_extension, cmd_uuid

log = logging.getLogger("marcador")

CAUSAS_SIN_CONTESTAR = {"NO_ANSWER", "NO_USER_RESPONSE", "ORIGINATOR_CANCEL", "USER_BUSY", "CALL_REJECTED",
                        "ALLOTTED_TIMEOUT", "RECOVERY_ON_TIMER_EXPIRE"}
CAUSAS_NUMERO_INVALIDO = {"UNALLOCATED_NUMBER", "INVALID_NUMBER_FORMAT", "NO_ROUTE_DESTINATION"}


class Reprogramar(Exception):
    """El trabajo debe volver a la cola más tarde (sin consumir intento)."""


def registrar_evento(db: Session, ll: Llamada, tipo: str, clave: str, datos: dict | None = None) -> bool:
    """Idempotente: si la clave ya existe, el evento repetido se ignora (no hay doble conteo)."""
    try:
        with db.begin_nested():
            db.add(EventoLlamada(id_llamada=ll.id_llamada, tipo=tipo, clave_evento=clave[:120], datos=datos))
        return True
    except IntegrityError:
        return False


def clasificar_causa(causa: str) -> tuple[str, str | None]:
    """Devuelve (estado_tecnico, resultado_contacto). Fallos técnicos NO se cuentan como 'sin contestar'."""
    if causa in CAUSAS_SIN_CONTESTAR:
        return "FINALIZADA", "SIN_CONTESTAR"
    return "FALLIDA", None


def reservar_canal(db: Session) -> CanalConcurrente | None:
    q = (select(CanalConcurrente).join(ExtensionSIP).join(TroncalSIP, ExtensionSIP.id_troncal == TroncalSIP.id_troncal)
         .join(PlantaFreeswitch, ExtensionSIP.id_planta == PlantaFreeswitch.id_planta)
         .where(CanalConcurrente.estado == "LIBRE", ExtensionSIP.activa.is_(True), TroncalSIP.activa.is_(True),
                PlantaFreeswitch.activa.is_(True))
         .order_by(CanalConcurrente.id_canal).limit(1).with_for_update(skip_locked=True))
    return db.execute(q).scalars().first()


def liberar_canal(db: Session, id_canal: int | None) -> None:
    if id_canal:
        db.execute(update(CanalConcurrente).where(CanalConcurrente.id_canal == id_canal)
                   .values(estado="LIBRE", id_llamada=None, ocupado_desde=None))


def recuperar_tras_reinicio(db: Session) -> dict:
    """Libera canales y cierra llamadas huérfanas; evita re-marcar trabajos interrumpidos."""
    s = get_settings()
    ahora = ahora_utc()
    limite = ahora - timedelta(seconds=s.max_duracion_conversacion_seg + 120)
    huerfanas = db.execute(select(Llamada).where(Llamada.canal == "TELEFONIA", Llamada.estado_tecnico == "EN_CURSO",
                                                 Llamada.inicio < limite)).scalars().all()
    for ll in huerfanas:
        ll.estado_tecnico, ll.fin, ll.motivo_fallo = "FALLIDA", ahora, "Recuperada tras reinicio"
        registrar_evento(db, ll, "RECUPERADA", f"{ll.id_llamada}:RECUPERADA")
        if ll.id_cliente_campana:
            cc = db.get(ClienteCampana, ll.id_cliente_campana)
            if cc and cc.estado_gestion == "EN_LLAMADA":
                cc.estado_gestion = "PENDIENTE"
    canales = db.execute(select(CanalConcurrente).where(CanalConcurrente.estado == "OCUPADO")).scalars().all()
    liberados = 0
    for c in canales:
        ll = db.get(Llamada, c.id_llamada) if c.id_llamada else None
        if ll is None or ll.estado_tecnico != "EN_CURSO":
            liberar_canal(db, c.id_canal)
            liberados += 1
    trabajos = db.execute(select(Trabajo).where(Trabajo.estado == "EN_PROCESO",
                                                (Trabajo.bloqueado_hasta.is_(None)) | (Trabajo.bloqueado_hasta < ahora))).scalars().all()
    for t in trabajos:
        if t.tipo == "MARCAR":  # no se re-marca automáticamente: podría duplicar una llamada real
            t.estado, t.resultado = "FALLIDO", "Interrumpido por reinicio; no se reintenta para evitar doble marcación"
            id_cc = (t.payload or {}).get("id_cliente_campana")
            cc = db.get(ClienteCampana, id_cc) if id_cc else None
            if cc and cc.estado_gestion in ("EN_COLA", "EN_LLAMADA"):
                cc.estado_gestion = "PENDIENTE"
        else:
            t.estado, t.bloqueado_por, t.bloqueado_hasta = "PENDIENTE", None, None
    return {"llamadas_recuperadas": len(huerfanas), "canales_liberados": liberados, "trabajos_recuperados": len(trabajos)}


def _duracion_wav(audio: bytes) -> float:
    return max(len(audio) - 44, 0) / 16000.0  # PCM 16-bit mono 8 kHz


def procesar_marcar(db: Session, trabajo: Trabajo) -> str:
    s = get_settings()
    cc = db.get(ClienteCampana, (trabajo.payload or {}).get("id_cliente_campana"))
    if cc is None:
        return "CANCELADO:cliente_campana inexistente"
    motivos = reglas.verificar(db, cc, "ORIGINAR")
    if motivos:
        if "EXCLUIDO" in motivos:
            cc.estado_gestion = "EXCLUIDO"
        elif cc.estado_gestion == "EN_COLA":
            cc.estado_gestion = "PENDIENTE"
        return "CANCELADO:" + ",".join(motivos)
    if not s.telefonia_habilitada:
        cc.estado_gestion = "PENDIENTE"
        clave = f"telefonia_bloqueada:{ahora_utc().strftime('%Y%m%d')}"
        if db.execute(select(Alerta.id).where(Alerta.clave == clave)).first() is None:
            db.add(Alerta(tipo="TELEFONIA_BLOQUEADA", severidad="MEDIA", origen="REGLA", clave=clave,
                          mensaje="Hay trabajos de marcación pero la telefonía está deshabilitada (falta FreeSWITCH/troncal SIP)."))
        return "BLOQUEADO:TELEFONIA_NO_CONFIGURADA"
    destino = cc.cliente.telefono
    if s.telefonia_solo_numeros_autorizados and db.execute(
            select(NumeroAutorizado.id).where(NumeroAutorizado.telefono == destino)).first() is None:
        cc.estado_gestion = "PENDIENTE"
        return "CANCELADO:NUMERO_NO_AUTORIZADO_PARA_PILOTO"
    activas = db.execute(select(func.count(Llamada.id_llamada)).where(Llamada.canal == "TELEFONIA",
                                                                      Llamada.estado_tecnico == "EN_CURSO")).scalar_one()
    if activas >= int(parametros.obtener(db, "max_canales_piloto")):
        raise Reprogramar("Capacidad del piloto ocupada")
    canal = reservar_canal(db)
    if canal is None:
        raise Reprogramar("Sin canal SIP libre")
    agentes = srv_campanas.agentes_validos(db, cc.campana)
    if not agentes:
        return "CANCELADO:SIN_AGENTE_VALIDO"
    ext = canal.extension
    planta, troncal = ext.planta, ext.troncal
    ll = motor.iniciar(db, agente=agentes[0], cliente=cc.cliente, deuda=cc.deuda, canal="TELEFONIA", modo="REAL", cc=cc)
    ll.uuid_freeswitch = str(uuidlib.uuid4())
    ll.destino_enmascarado = enmascarar_telefono(destino)
    ll.id_extension, ll.id_canal = ext.id_extension, canal.id_canal
    canal.estado, canal.id_llamada, canal.ocupado_desde = "OCUPADO", ll.id_llamada, ahora_utc()
    cc.estado_gestion, cc.intentos, cc.ultimo_intento = "EN_LLAMADA", cc.intentos + 1, ahora_utc()
    registrar_evento(db, ll, "ORIGINATE_SOLICITADO", f"{ll.uuid_freeswitch}:ORIGINATE")
    db.commit()  # el estado de la llamada sobrevive a una caída a partir de aquí
    try:
        with cliente_esl(planta) as esl:
            resp = esl.api(cmd_originate(ll.uuid_freeswitch, troncal.gateway, destino, ll.id_llamada,
                                         s.telefonia_originate_timeout_seg), timeout=s.telefonia_originate_timeout_seg + 15)
            if not resp.startswith("+OK"):
                causa = resp.replace("-ERR", "").strip().split()[0] if resp else "DESCONOCIDA"
                estado, contacto = clasificar_causa(causa)
                ll.estado_tecnico, ll.resultado_contacto, ll.fin = estado, contacto, ahora_utc()
                ll.motivo_fallo, ll.resultado_cobranza = causa, "SIN_RESULTADO"
                registrar_evento(db, ll, "ORIGINATE_FALLIDO", f"{ll.uuid_freeswitch}:FALLO", {"causa": causa})
                if causa in CAUSAS_NUMERO_INVALIDO:
                    db.add(NoContactable(id_cliente=cc.id_cliente, telefono=destino, motivo="NUMERO_INVALIDO",
                                         detalle=causa, origen="MANUAL"))
                    cc.estado_gestion = "EXCLUIDO"
                else:
                    cc.estado_gestion = "PENDIENTE"
                return f"FINALIZADO:{causa}"
            registrar_evento(db, ll, "CONTESTADA", f"{ll.uuid_freeswitch}:ANSWER")
            db.commit()
            _conversar(db, esl, ll)
            return f"FINALIZADO:{ll.resultado_contacto or ll.estado_tecnico}"
    except ErrorESL as e:
        if ll.estado_tecnico == "EN_CURSO":
            ll.estado_tecnico, ll.fin, ll.motivo_fallo = "FALLIDA", ahora_utc(), f"ESL: {e}"[:255]
        db.add(Alerta(tipo="FALLA_FREESWITCH", severidad="ALTA", origen="REGLA", mensaje=f"Error ESL: {e}"[:500]))
        if cc.estado_gestion == "EN_LLAMADA":
            cc.estado_gestion = "PENDIENTE"
        return f"FALLIDO:{e}"
    finally:
        liberar_canal(db, canal.id_canal)
        registrar_evento(db, ll, "CANAL_LIBERADO", f"{ll.uuid_freeswitch}:LIBERADO")
        db.commit()


def procesar_llamar_extension(db: Session, trabajo: Trabajo) -> str:
    """Llamada de prueba a una extensión interna (Zoiper registrado en FreeSWITCH): sin troncal ni red pública."""
    s = get_settings()
    p = trabajo.payload or {}
    ll = db.get(Llamada, p.get("id_llamada"))
    ext = db.get(ExtensionSIP, p.get("id_extension"))
    if ll is None or ext is None or ll.estado_tecnico != "EN_CURSO":
        return "CANCELADO:llamada o extensión no vigente"
    if not s.telefonia_habilitada:
        ll.estado_tecnico, ll.fin, ll.motivo_fallo, ll.resultado_cobranza = "FALLIDA", ahora_utc(), "Telefonía deshabilitada", "SIN_RESULTADO"
        return "BLOQUEADO:TELEFONIA_NO_CONFIGURADA"
    canal = db.execute(select(CanalConcurrente).where(CanalConcurrente.id_extension == ext.id_extension,
                                                      CanalConcurrente.estado == "LIBRE")
                       .limit(1).with_for_update(skip_locked=True)).scalars().first()
    if canal is None:
        ll.estado_tecnico, ll.fin, ll.motivo_fallo, ll.resultado_cobranza = "FALLIDA", ahora_utc(), "Extensión ocupada", "SIN_RESULTADO"
        return "CANCELADO:EXTENSION_OCUPADA"
    planta = ext.planta
    ll.uuid_freeswitch = str(uuidlib.uuid4())
    ll.id_extension, ll.id_canal = ext.id_extension, canal.id_canal
    canal.estado, canal.id_llamada, canal.ocupado_desde = "OCUPADO", ll.id_llamada, ahora_utc()
    registrar_evento(db, ll, "ORIGINATE_SOLICITADO", f"{ll.uuid_freeswitch}:ORIGINATE", {"extension": ext.numero})
    db.commit()
    try:  # el saludo y la muletilla se preparan mientras suena, para que el agente hable apenas contestan
        audio_agente(db, ll, motor.saludo_inicial(ll.agente, ll.cliente))
        if s.telefonia_muletilla:
            audio_agente(db, ll, s.telefonia_muletilla)
    except ErrorProveedor:
        pass
    try:
        with cliente_esl(planta) as esl:
            resp = esl.api(cmd_originate_extension(ll.uuid_freeswitch, ext.numero, ll.id_llamada, s.telefonia_originate_timeout_seg),
                           timeout=s.telefonia_originate_timeout_seg + 15)
            if not resp.startswith("+OK"):
                causa = resp.replace("-ERR", "").strip().split()[0] if resp else "DESCONOCIDA"
                estado, contacto = clasificar_causa(causa)
                if causa == "USER_NOT_REGISTERED":
                    causa = "USER_NOT_REGISTERED (Zoiper no está conectado a FreeSWITCH)"
                ll.estado_tecnico, ll.resultado_contacto, ll.fin = estado, contacto, ahora_utc()
                ll.motivo_fallo, ll.resultado_cobranza = causa[:255], "SIN_RESULTADO"
                registrar_evento(db, ll, "ORIGINATE_FALLIDO", f"{ll.uuid_freeswitch}:FALLO", {"causa": causa})
                return f"FINALIZADO:{causa}"[:500]
            registrar_evento(db, ll, "CONTESTADA", f"{ll.uuid_freeswitch}:ANSWER")
            db.commit()
            _conversar(db, esl, ll)
            return f"FINALIZADO:{ll.resultado_contacto or ll.estado_tecnico}"
    except ErrorESL as e:
        if ll.estado_tecnico == "EN_CURSO":
            ll.estado_tecnico, ll.fin, ll.motivo_fallo, ll.resultado_cobranza = "FALLIDA", ahora_utc(), f"ESL: {e}"[:255], "SIN_RESULTADO"
        db.add(Alerta(tipo="FALLA_FREESWITCH", severidad="ALTA", origen="REGLA", mensaje=f"Error ESL: {e}"[:500]))
        return f"FALLIDO:{e}"[:500]
    finally:
        liberar_canal(db, canal.id_canal)
        registrar_evento(db, ll, "CANAL_LIBERADO", f"{ll.uuid_freeswitch}:LIBERADO")
        db.commit()


def ruta_freeswitch(archivo: Path) -> str:
    """Ruta del archivo tal como la ve FreeSWITCH (otra máquina) o la local si comparten disco."""
    remoto = get_settings().freeswitch_dir_audio_remoto
    return f"{remoto.rstrip('/')}/{archivo.name}" if remoto else str(archivo)


_RE_DESTINO_SSH = re.compile(r"^[\w.\-]+@[\w.\-]+$")


def _ssh_conectado():
    """SSH a la VM con la llave indicada y la huella fijada en FREESWITCH_SSH_KNOWN_HOSTS (equipo desconocido = rechazo).
    Se usa paramiko y no ssh/scp porque el sistema puede correr como otra cuenta de Windows (p. ej. iniciado por WAMP)."""
    import paramiko

    s = get_settings()
    if not _RE_DESTINO_SSH.match(s.freeswitch_ssh_destino):
        raise ErrorESL("FREESWITCH_SSH_DESTINO inválido (use usuario@ip)")
    usuario, host = s.freeswitch_ssh_destino.split("@", 1)
    cliente = paramiko.SSHClient()
    cliente.load_host_keys(s.freeswitch_ssh_known_hosts)
    cliente.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        cliente.connect(host, username=usuario, key_filename=s.freeswitch_ssh_llave, timeout=5, banner_timeout=5,
                        auth_timeout=5, allow_agent=False, look_for_keys=False)
    except (paramiko.SSHException, OSError) as e:
        cliente.close()
        raise ErrorESL(f"No se pudo conectar por SSH a la VM de FreeSWITCH: {type(e).__name__}") from e
    return cliente


@contextmanager
def _sftp():
    import paramiko

    cliente = _ssh_conectado()
    try:
        with cliente.open_sftp() as sftp:
            yield sftp
    except (paramiko.SSHException, OSError) as e:
        raise ErrorESL(f"No se pudo copiar audio con la VM de FreeSWITCH: {type(e).__name__}") from e
    finally:
        cliente.close()


class _CanalTunel:
    """Canal SSH hacia 127.0.0.1:puerto de la VM con la interfaz de socket que usa ClienteESL."""

    def __init__(self, puerto: int):
        self.cliente = _ssh_conectado()
        try:
            self.canal = self.cliente.get_transport().open_channel("direct-tcpip", ("127.0.0.1", puerto), ("127.0.0.1", 0))
        except Exception as e:
            self.cliente.close()
            raise ErrorESL(f"La VM no abrió el Event Socket local: {type(e).__name__}") from e

    def settimeout(self, t):
        self.canal.settimeout(t)

    def sendall(self, datos: bytes):
        self.canal.sendall(datos)

    def recv(self, n: int) -> bytes:
        return self.canal.recv(n)

    def close(self):
        self.canal.close()
        self.cliente.close()


def cliente_esl(planta: PlantaFreeswitch, timeout: float = 10.0) -> ClienteESL:
    """Event Socket de la planta. Si es la VM con acceso SSH (FREESWITCH_SSH_DESTINO), va dentro del túnel SSH hacia
    127.0.0.1 de la VM: el Event Socket no queda expuesto en la red y no hay que reconfigurar FreeSWITCH al cambiar
    de red (casa, universidad)."""
    s = get_settings()
    destino = s.freeswitch_ssh_destino
    if destino and destino.split("@", 1)[-1] == planta.ip:
        return ClienteESL(planta.ip, planta.puerto_esl, s.freeswitch_esl_password, timeout,
                          abrir=lambda: _CanalTunel(planta.puerto_esl))
    return ClienteESL(planta.ip, planta.puerto_esl, s.freeswitch_esl_password, timeout)


class CanalAudio:
    """Archivos de audio entre el backend y FreeSWITCH durante una llamada: carpeta compartida o una sola conexión SFTP."""

    def __init__(self, sftp=None):
        self.sftp = sftp

    def _remoto(self, operacion):
        try:
            return operacion()
        except FileNotFoundError:
            raise
        except OSError as e:
            raise ErrorESL(f"Se perdió la conexión de audio con la VM: {type(e).__name__}") from e

    def publicar(self, archivo: Path) -> None:
        """Deja el WAV del agente donde FreeSWITCH lo lee."""
        if self.sftp:
            self._remoto(lambda: self.sftp.put(str(archivo), ruta_freeswitch(archivo)))

    def traer(self, archivo: Path) -> None:
        """Trae la grabación del cliente (si no existe, no hay archivo local y se trata como silencio)."""
        if self.sftp:
            try:
                self._remoto(lambda: self.sftp.get(ruta_freeswitch(archivo), str(archivo)))
            except FileNotFoundError:
                archivo.unlink(missing_ok=True)

    def leer_desde(self, archivo: Path, pos: int) -> bytes:
        """Lo grabado hasta ahora a partir de pos (la grabación sigue creciendo mientras el cliente habla)."""
        def leer():
            with (self.sftp.open(ruta_freeswitch(archivo), "rb") if self.sftp else open(archivo, "rb")) as f:
                f.seek(pos)
                return f.read()
        try:
            return self._remoto(leer)
        except FileNotFoundError:
            return b""

    def borrar(self, *archivos: Path) -> None:
        """El audio en claro no se conserva tampoco en la VM."""
        for a in archivos:
            a.unlink(missing_ok=True)
            if self.sftp:
                try:
                    self._remoto(lambda: self.sftp.remove(ruta_freeswitch(a)))
                except FileNotFoundError:
                    pass


@contextmanager
def canal_audio():
    if get_settings().freeswitch_ssh_destino:
        with _sftp() as sftp:
            yield CanalAudio(sftp)
    else:
        yield CanalAudio()


_MUESTRAS_TRAMO = 400  # 50 ms a 8 kHz


def esperar_fin_de_habla(audio: CanalAudio, grab: Path, al_leer: Callable[[bytes], None] | None = None,
                         silencio_fin: float | None = None, silencio_max: float | None = None) -> tuple[str, bytes]:
    """Escucha la grabación en curso y vuelve en cuanto el cliente deja de hablar (en vez de esperar un tiempo fijo).

    Por cada tramo de 50 ms se mide la energía (RMS). El ruido de fondo es el percentil 10 de los últimos 3 s, así se
    adapta al ruido real de la llamada (salón, calle); voz = tramo > 3 veces ese ruido. Termina tras
    TELEFONIA_SILENCIO_FIN_SEG sin voz después de haber hablado, si no habla en TELEFONIA_ESPERA_INICIO_SEG, o al llegar
    a TELEFONIA_MAX_SEGUNDOS_TURNO. Devuelve el motivo (queda en el registro del worker para afinar los umbrales) y lo
    grabado hasta ese momento, cabecera WAV incluida, para no volver a descargarlo. al_leer recibe el audio nuevo
    (reconocimiento en vivo).
    """
    s = get_settings()
    inicio, capturado, resto = time.monotonic(), b"", b""
    recientes: deque[float] = deque(maxlen=60)  # 3 s de tramos
    piso, pico, hablo, ultima_voz = 0.0, 0.0, False, 0.0
    motivo = ""
    while not motivo:
        time.sleep(0.2)
        ahora = time.monotonic() - inicio
        datos = audio.leer_desde(grab, len(capturado))
        if len(capturado) < 44:  # la cabecera WAV (44 bytes) no es audio
            corte = max(0, 44 - len(capturado))
            capturado += datos
            datos = datos[corte:]
        else:
            capturado += datos
        if al_leer:
            al_leer(datos)
        datos = resto + datos
        tam = _MUESTRAS_TRAMO * 2
        completos = len(datos) - len(datos) % tam
        for k in range(0, completos, tam):
            muestras = array.array("h", datos[k:k + tam])
            rms = math.sqrt(sum(x * x for x in muestras) / len(muestras))
            pico = max(pico, rms)
            recientes.append(rms)
            piso = sorted(recientes)[len(recientes) // 10]
            if rms > max(250.0, piso * 3.0):
                hablo, ultima_voz = True, ahora
        resto = datos[completos:]
        if hablo and ahora - ultima_voz >= (silencio_fin or s.telefonia_silencio_fin_seg):
            motivo = "silencio tras hablar"
        elif not hablo and ahora >= (silencio_max or s.telefonia_espera_inicio_seg):
            motivo = "no habló"
        elif ahora >= s.telefonia_max_segundos_turno:
            motivo = "tiempo máximo"
    log.info("Turno del cliente: %.1f s, %s (ruido %.0f, pico %.0f)", time.monotonic() - inicio, motivo, piso, pico)
    return motivo, capturado


def wav_completo(cabecera_y_audio: bytes) -> bytes:
    """Corrige los tamaños de la cabecera de un WAV leído mientras se grababa (FreeSWITCH los escribe al cerrar)."""
    datos = bytearray(cabecera_y_audio)
    if len(datos) < 44 or datos[:4] != b"RIFF" or datos[36:40] != b"data":
        return bytes(datos)
    datos[4:8] = (len(datos) - 8).to_bytes(4, "little")
    datos[40:44] = (len(datos) - 44).to_bytes(4, "little")
    return bytes(datos)


_cache_tts: dict[tuple, bytes] = {}
_candado_tts = threading.Lock()


def _tts_frase(texto: str, voz: str, velocidad: float, id_llamada: int) -> bytes:
    """WAV 8 kHz de una frase. Las frases repetidas (saludo, preguntas fijas) se reutilizan sin volver a pedirlas.
    Usa su propia sesión de BD para poder correr en paralelo con otras frases."""
    clave = (texto, voz, velocidad)
    with _candado_tts:
        if clave in _cache_tts:
            return _cache_tts[clave]
    with SessionLocal() as db:
        wav = deepgram.tts(db, texto, voz, telefonia=True, id_llamada=id_llamada, velocidad=velocidad).audio
        db.commit()
    with _candado_tts:
        if len(_cache_tts) >= 100:
            _cache_tts.pop(next(iter(_cache_tts)))
        _cache_tts[clave] = wav
    return wav


def audio_agente(db: Session, ll: Llamada, texto: str) -> bytes:
    return _tts_frase(texto, ll.agente.voz_deepgram, float(ll.agente.velocidad_voz or 1), ll.id_llamada)


def dividir_frases(texto: str) -> list[str]:
    """Oraciones del agente, para generar su voz en paralelo y empezar a hablar con la primera.
    Las muy cortas se unen a la siguiente (cada pedido a Deepgram tiene un costo fijo de tiempo)."""
    frases: list[str] = []
    for f in re.split(r"(?<=[.!?])\s+", texto.strip()):  # punto seguido de espacio: no corta montos como 14,577.63
        f = f.strip()
        if not f:
            continue
        if frases and len(frases[-1]) < 25:
            frases[-1] = f"{frases[-1]} {f}"
        else:
            frases.append(f)
    return frases or [texto]


def _conversar(db: Session, esl: ClienteESL, ll: Llamada) -> None:
    s = get_settings()
    carpeta = Path(s.freeswitch_dir_audio)
    carpeta.mkdir(parents=True, exist_ok=True)
    u = ll.uuid_freeswitch
    texto_agente = motor.saludo_inicial(ll.agente, ll.cliente)
    silencios, n = 0, 0
    inicio = time.monotonic()
    muletilla = carpeta / f"{u}_m.wav"

    voz, vel = ll.agente.voz_deepgram, float(ll.agente.velocidad_voz or 1)
    hilos = ThreadPoolExecutor(max_workers=3)
    estado = {"stt": None}

    def abrir_stt() -> None:
        try:
            estado["stt"] = deepgram.SttEnVivo(ll.id_llamada)
        except ErrorProveedor:
            estado["stt"] = None  # el turno usa el reconocimiento normal

    def decir(audio_vm: CanalAudio, arch: Path, texto: str, preparar_escucha: bool = False) -> None:
        """Habla frase por frase: la primera suena apenas está lista y las demás se generan mientras tanto.
        Con preparar_escucha, durante la locución se abre el reconocimiento en vivo del siguiente turno."""
        pendientes = [hilos.submit(_tts_frase, f, voz, vel, ll.id_llamada) for f in dividir_frases(texto)]
        for k, futuro in enumerate(pendientes):
            wav = futuro.result()
            parte = arch.with_name(f"{arch.stem}_{k}.wav")
            parte.write_bytes(wav)
            audio_vm.publicar(parte)
            esl.api(cmd_uuid("uuid_broadcast", u, ruta_freeswitch(parte), "aleg"))
            fin = time.monotonic() + _duracion_wav(wav) + 0.1
            if preparar_escucha and k == len(pendientes) - 1:
                abrir_stt()
            while (resta := fin - time.monotonic()) > 0:
                time.sleep(min(resta, 2.5))
                if estado["stt"]:
                    estado["stt"].mantener()
            audio_vm.borrar(parte)

    try:
        with canal_audio() as audio_vm:
            if s.telefonia_muletilla:  # «Ajá.» apenas el cliente calla: cubre el tiempo de reconocer y responder
                muletilla.write_bytes(audio_agente(db, ll, s.telefonia_muletilla))
                audio_vm.publicar(muletilla)
            while ll.estado_tecnico == "EN_CURSO" and time.monotonic() - inicio < s.max_duracion_conversacion_seg:
                n += 1
                arch, grab = carpeta / f"{u}_a{n}.wav", carpeta / f"{u}_c{n}.wav"
                if "true" not in esl.api(cmd_uuid("uuid_exists", u)):
                    break
                if n == 1 and float(ll.agente.espera_inicio_seg or 0) > 0:  # tiempo de espera del agente al contestar
                    time.sleep(float(ll.agente.espera_inicio_seg))
                decir(audio_vm, arch, texto_agente, preparar_escucha=True)
                esl.api(cmd_uuid("uuid_record", u, "start", ruta_freeswitch(grab), str(s.telefonia_max_segundos_turno + 2)))
                stt = estado["stt"]
                motivo, contenido = esperar_fin_de_habla(audio_vm, grab, al_leer=stt.enviar if stt else None,
                                                         silencio_fin=float(ll.agente.silencio_fin_seg or 0) or None,
                                                         silencio_max=float(ll.agente.silencio_max_seg or 0) or None)
                esl.api(cmd_uuid("uuid_record", u, "stop", ruta_freeswitch(grab)))
                if motivo == "silencio tras hablar" and s.telefonia_muletilla:
                    esl.api(cmd_uuid("uuid_broadcast", u, ruta_freeswitch(muletilla), "aleg"))
                if "true" not in esl.api(cmd_uuid("uuid_exists", u)):
                    break
                contenido = contenido + audio_vm.leer_desde(grab, len(contenido))
                if contenido[36:40] == b"data":
                    contenido = wav_completo(contenido)
                else:  # cabecera con otro formato: se descarga el archivo ya cerrado
                    audio_vm.traer(grab)
                    contenido = grab.read_bytes() if grab.exists() else b""
                texto = None
                if stt:
                    try:
                        texto = stt.terminar(db).texto if len(contenido) > 1000 else ""
                    except ErrorProveedor:
                        texto = None
                    estado["stt"] = None
                if texto is None or (not texto and motivo == "silencio tras hablar"):  # respaldo: grabación completa
                    texto = deepgram.stt(db, contenido, "audio/wav", ll.id_llamada).texto if len(contenido) > 1000 else ""
                audio_vm.borrar(arch, grab)
                if not texto:
                    silencios += 1
                    if silencios >= 2:
                        texto_agente = "No logro escucharle. Le llamaremos en otro momento. Que tenga buen día."
                        motor._agregar_turno(db, ll, "AGENTE", texto_agente)
                        decir(audio_vm, arch, texto_agente)
                        audio_vm.borrar(arch)
                        break
                    texto_agente = "¿Me escucha? Por favor responda después del mensaje."
                    motor._agregar_turno(db, ll, "AGENTE", texto_agente)
                    continue
                silencios = 0
                r = motor.procesar_mensaje(db, ll, texto)
                db.commit()
                texto_agente = r["respuesta"]
                if r["finalizada"]:
                    decir(audio_vm, arch, texto_agente)
                    audio_vm.borrar(arch)
                    break
            audio_vm.borrar(muletilla)
    except ErrorProveedor as e:
        motor._cerrar(db, ll, "SIN_RESULTADO", "FALLIDA", f"Proveedor: {e.codigo}")
    finally:
        hilos.shutdown(wait=False, cancel_futures=True)
        if estado["stt"]:
            estado["stt"].cerrar()
        try:
            if "true" in esl.api(cmd_uuid("uuid_exists", u)):
                esl.api(cmd_uuid("uuid_kill", u))
        except ErrorESL:
            pass
        registrar_evento(db, ll, "COLGADA", f"{u}:HANGUP")
        if ll.estado_tecnico == "EN_CURSO":
            motor._cerrar(db, ll, "SIN_RESULTADO")
        db.commit()


def verificar_planta(db: Session, planta: PlantaFreeswitch) -> dict:
    s = get_settings()
    planta.ultima_verificacion = ahora_utc()
    try:
        with cliente_esl(planta, timeout=5) as esl:
            estado = esl.api("status")
            gateways = esl.api("sofia status gateway")
        planta.estado = "DISPONIBLE"
        return {"ok": True, "status": estado[:800], "gateways": gateways[:1500]}
    except ErrorESL as e:
        planta.estado = "NO_DISPONIBLE"
        return {"ok": False, "error": str(e)}
