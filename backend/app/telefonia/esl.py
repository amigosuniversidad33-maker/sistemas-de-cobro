"""Cliente mínimo del Event Socket de FreeSWITCH (modo inbound, comandos `api`).

El Event Socket sirve para CONTROL de llamada. El audio NO viaja por aquí: en este proyecto el
"puente de medios" es por archivos (TTS WAV -> uuid_broadcast; uuid_record -> WAV -> STT), lo que exige
que FreeSWITCH y el backend compartan la carpeta FREESWITCH_DIR_AUDIO. Ver docs/FREESWITCH.md.
"""
import ipaddress
import re
import socket
from collections.abc import Callable

_SEGURO = re.compile(r"^[\w\-\.:/\\{}=,+&() ]+$")


class ErrorESL(Exception):
    pass


def host_permitido(host: str) -> bool:
    """Solo localhost o redes privadas (evita SSRF / exposición del administrativo)."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host == "localhost"
    return ip.is_loopback or ip.is_private


class ClienteESL:
    def __init__(self, host: str, puerto: int, password: str, timeout: float = 10.0,
                 abrir: Callable[[], object] | None = None):
        """abrir: conexión alternativa al socket TCP directo (p. ej. un canal dentro de un túnel SSH)."""
        if not host_permitido(host):
            raise ErrorESL("El host de FreeSWITCH debe ser localhost o de red privada.")
        if not password:
            raise ErrorESL("FREESWITCH_ESL_PASSWORD no está configurada.")
        self.host, self.puerto, self.password, self.timeout = host, puerto, password, timeout
        self.abrir = abrir
        self.sock: socket.socket | None = None
        self._buf = b""

    def __enter__(self):
        self.conectar()
        return self

    def __exit__(self, *exc):
        self.cerrar()

    def conectar(self) -> None:
        try:
            self.sock = self.abrir() if self.abrir else socket.create_connection((self.host, self.puerto), timeout=self.timeout)
            self.sock.settimeout(self.timeout)
        except (OSError, ErrorESL) as e:
            raise ErrorESL(f"No se pudo conectar a FreeSWITCH {self.host}:{self.puerto}: {e}") from e
        cab, _ = self._leer_mensaje()
        if cab.get("Content-Type") != "auth/request":
            raise ErrorESL("Respuesta inesperada del Event Socket")
        self._enviar(f"auth {self.password}")
        cab, _ = self._leer_mensaje()
        if not cab.get("Reply-Text", "").startswith("+OK"):
            raise ErrorESL("Autenticación ESL rechazada")

    def cerrar(self) -> None:
        if self.sock:
            try:
                self._enviar("exit")
            except OSError:
                pass
            self.sock.close()
            self.sock = None

    def _enviar(self, linea: str) -> None:
        if "\n" in linea or "\r" in linea:
            raise ErrorESL("Comando inválido")
        assert self.sock is not None
        self.sock.sendall((linea + "\n\n").encode("utf-8"))

    def _leer_linea(self) -> bytes:
        assert self.sock is not None
        while b"\n" not in self._buf:
            datos = self.sock.recv(4096)
            if not datos:
                raise ErrorESL("Conexión ESL cerrada")
            self._buf += datos
        linea, self._buf = self._buf.split(b"\n", 1)
        return linea

    def _leer_bytes(self, n: int) -> bytes:
        assert self.sock is not None
        while len(self._buf) < n:
            datos = self.sock.recv(4096)
            if not datos:
                raise ErrorESL("Conexión ESL cerrada")
            self._buf += datos
        cuerpo, self._buf = self._buf[:n], self._buf[n:]
        return cuerpo

    def _leer_mensaje(self) -> tuple[dict, str]:
        cab: dict[str, str] = {}
        while True:
            linea = self._leer_linea().decode("utf-8", "replace").rstrip("\r")
            if linea == "":
                if cab:
                    break
                continue
            if ":" in linea:
                k, v = linea.split(":", 1)
                cab[k.strip()] = v.strip()
        cuerpo = ""
        if "Content-Length" in cab:
            cuerpo = self._leer_bytes(int(cab["Content-Length"])).decode("utf-8", "replace")
        return cab, cuerpo

    def api(self, comando: str, timeout: float | None = None) -> str:
        if not _SEGURO.match(comando):
            raise ErrorESL("El comando contiene caracteres no permitidos")
        assert self.sock is not None
        try:
            self.sock.settimeout(timeout or self.timeout)
            self._enviar(f"api {comando}")
            while True:
                cab, cuerpo = self._leer_mensaje()
                if cab.get("Content-Type") == "api/response":
                    return cuerpo.strip()
        except OSError as e:  # tiempo agotado o conexión cortada: la llamada se cierra como fallo técnico
            raise ErrorESL(f"Se perdió la conexión con FreeSWITCH: {type(e).__name__}") from e


_RE_GATEWAY = re.compile(r"^[A-Za-z0-9_\-]{1,60}$")
_RE_UUID = re.compile(r"^[0-9a-fA-F\-]{36}$")
_RE_E164 = re.compile(r"^\+\d{8,15}$")
_RE_EXTENSION = re.compile(r"^\d{2,10}$")
_RE_RUTA = re.compile(r"^[\w\-\.:/\\]+$")


def cmd_originate(uuid: str, gateway: str, destino_e164: str, id_llamada: int, timeout_seg: int) -> str:
    """Construye el comando originate SOLO con valores validados (no se concatenan entradas libres)."""
    if not _RE_UUID.match(uuid) or not _RE_GATEWAY.match(gateway) or not _RE_E164.match(destino_e164):
        raise ErrorESL("Parámetros de originate inválidos")
    if not (5 <= int(timeout_seg) <= 120):
        raise ErrorESL("Timeout inválido")
    vars_ = f"origination_uuid={uuid},originate_timeout={int(timeout_seg)},ignore_early_media=true,sc_llamada={int(id_llamada)}"
    return f"originate {{{vars_}}}sofia/gateway/{gateway}/{destino_e164} &park()"


def cmd_originate_extension(uuid: str, extension: str, id_llamada: int, timeout_seg: int) -> str:
    """Llama a una extensión SIP interna registrada en FreeSWITCH (p. ej. Zoiper en el celular). No sale a la red pública."""
    if not _RE_UUID.match(uuid) or not _RE_EXTENSION.match(extension):
        raise ErrorESL("Parámetros de originate inválidos")
    if not (5 <= int(timeout_seg) <= 120):
        raise ErrorESL("Timeout inválido")
    vars_ = (f"origination_uuid={uuid},originate_timeout={int(timeout_seg)},ignore_early_media=true,sc_llamada={int(id_llamada)},"
             "origination_caller_id_name=CobrosIA,origination_caller_id_number=9000")
    return f"originate {{{vars_}}}user/{extension} &park()"


def cmd_uuid(accion: str, uuid: str, *args: str) -> str:
    if accion not in {"uuid_broadcast", "uuid_record", "uuid_kill", "uuid_exists", "uuid_break"}:
        raise ErrorESL("Acción no permitida")
    if not _RE_UUID.match(uuid):
        raise ErrorESL("UUID inválido")
    for a in args:
        if not _RE_RUTA.match(a):
            raise ErrorESL("Argumento inválido")
    return " ".join([accion, uuid, *args])
