"""Utilidades: zona horaria, teléfonos, enmascaramiento PII y exportación segura."""
import re
from datetime import date, datetime, time, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from .config import get_settings


def zona() -> ZoneInfo:
    return ZoneInfo(get_settings().zona_horaria)


def utc_a_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(zona())


def local_ahora(ahora_utc: datetime | None = None) -> datetime:
    base = ahora_utc or datetime.now(timezone.utc).replace(tzinfo=None)
    return utc_a_local(base)


def hoy_local(ahora_utc: datetime | None = None) -> date:
    return local_ahora(ahora_utc).date()


def inicio_dia_local_en_utc(dia: date) -> datetime:
    """Medianoche local del día indicado, expresada en UTC sin tzinfo."""
    return datetime.combine(dia, time(0, 0), tzinfo=zona()).astimezone(timezone.utc).replace(tzinfo=None)


def iso(dt: datetime | None) -> str | None:
    """Serializa un datetime UTC almacenado como ISO con zona local."""
    loc = utc_a_local(dt)
    return loc.isoformat() if loc else None


def parse_hhmm(valor: str) -> time:
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", valor or ""):
        raise ValueError("Hora inválida, use HH:MM")
    h, m = valor.split(":")
    return time(int(h), int(m))


def dentro_de_ventana(hora_inicio: str, hora_fin: str, ahora_utc: datetime | None = None) -> bool:
    """Ventana [inicio, fin): a las 20:00 exactas ya NO se permite marcar."""
    t = local_ahora(ahora_utc).time()
    return parse_hhmm(hora_inicio) <= t < parse_hhmm(hora_fin)


# ---------------------------------------------------------------- teléfonos
def normalizar_telefono(valor: str | None, codigo_pais: str = "502") -> str | None:
    """Devuelve E.164 (+502XXXXXXXX) o None si no es válido.

    Guatemala: 8 dígitos, el primero 2-7 (fijos 2-6, móviles 3-5-4...). Se aceptan
    formatos con espacios, guiones, paréntesis y prefijos 502 / +502 / 00502.
    """
    if valor is None:
        return None
    s = re.sub(r"[\s\-\.\(\)]", "", str(valor).strip())
    if s.endswith(".0"):  # números leídos desde Excel como float
        s = s[:-2]
    if s.startswith("00"):
        s = "+" + s[2:]
    if s.startswith("+"):
        digitos = s[1:]
        if not digitos.isdigit():
            return None
        if digitos.startswith(codigo_pais) and len(digitos) == len(codigo_pais) + 8:
            local = digitos[len(codigo_pais):]
        else:
            return None
    else:
        if not s.isdigit():
            return None
        if len(s) == 8:
            local = s
        elif len(s) == len(codigo_pais) + 8 and s.startswith(codigo_pais):
            local = s[len(codigo_pais):]
        else:
            return None
    if local[0] not in "234567":
        return None
    return f"+{codigo_pais}{local}"


def enmascarar_telefono(tel: str | None) -> str | None:
    if not tel:
        return tel
    return tel[:4] + "****" + tel[-4:] if len(tel) > 8 else "****" + tel[-2:]


def enmascarar_documento(doc: str | None) -> str | None:
    if not doc:
        return doc
    return "*" * max(len(doc) - 4, 0) + doc[-4:]


_RE_TARJETA = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_RE_DPI = re.compile(r"\b\d{4}\s?\d{5}\s?\d{4}\b")
_RE_TEL = re.compile(r"(?<!\d)(?:\+?502[\s-]?)?[2-7]\d{3}[\s-]?\d{4}(?!\d)")
_RE_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def enmascarar_pii(texto: str | None) -> str:
    """Reemplaza tarjetas, DPI, teléfonos y correos (R-07). Conserva los últimos 4 dígitos."""
    if not texto:
        return texto or ""

    def _ult4(m):
        d = re.sub(r"\D", "", m.group(0))
        return "****-" + d[-4:]

    t = _RE_TARJETA.sub(_ult4, texto)
    t = _RE_DPI.sub(_ult4, t)
    t = _RE_TEL.sub(lambda m: "****" + re.sub(r"\D", "", m.group(0))[-4:], t)
    t = _RE_CORREO.sub("[correo oculto]", t)
    return t


# ---------------------------------------------------------------- importes
def a_decimal(valor, max_dig=14, dec=2) -> Decimal:
    if valor is None or str(valor).strip() == "":
        raise ValueError("Monto vacío")
    s = str(valor).strip().replace("Q", "").replace(",", "").replace(" ", "")
    try:
        d = Decimal(s)
    except InvalidOperation as e:
        raise ValueError("Monto inválido") from e
    if not d.is_finite():
        raise ValueError("Monto inválido")
    d = d.quantize(Decimal(1).scaleb(-dec), rounding=ROUND_HALF_UP)
    if len(d.as_tuple().digits) > max_dig:
        raise ValueError("Monto demasiado grande")
    return d


def celda_segura(valor) -> str:
    """Previene inyección de fórmulas en CSV/Excel (=, +, -, @, tab, CR)."""
    s = "" if valor is None else str(valor)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s
