"""Aplicación FastAPI: API + frontend estático en el mismo origen (http://127.0.0.1:8000)."""
import ipaddress
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .routers import agentes, auth, campanas, clientes, control, conversaciones, exclusiones, llamadas, telefonia, twilio, usuarios

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
MAX_CUERPO = 8 * 1024 * 1024
LIMITE_POR_MINUTO = 600

s = get_settings()
app = FastAPI(title=s.app_nombre, version="1.0.0",
              docs_url="/api/docs" if s.entorno == "local" else None, redoc_url=None, openapi_url="/api/openapi.json" if s.entorno == "local" else None)


def _ip_privada(valor: str) -> bool:
    try:
        ip = ipaddress.ip_address(valor)
    except ValueError:
        return False
    return ip.is_private and not ip.is_link_local


def _acceso_permitido(request: Request) -> bool:
    """Este equipo; o, con ACCESO_RED_LOCAL, otra computadora de la red local que entra por la IP de este equipo.
    Lo que llega por un túnel (cabecera X-Forwarded-For) nunca cuenta como local. Exigir una IP literal en Host
    evita que un sitio externo use un nombre de dominio propio para llegar aquí (DNS rebinding)."""
    if "x-forwarded-for" in request.headers:
        return False
    host = request.headers.get("host", "").rsplit(":", 1)[0].strip("[]")
    if host in ("127.0.0.1", "localhost", "testserver"):
        return True
    ip_cliente = request.client.host if request.client else ""
    return get_settings().acceso_red_local and _ip_privada(host) and _ip_privada(ip_cliente)


class Seguridad(BaseHTTPMiddleware):
    """Cabeceras de seguridad, límite de tamaño, límite de frecuencia y verificación de origen."""

    def __init__(self, app):
        super().__init__(app)
        self.ventanas: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "?"
        # Por un túnel público (ngrok) solo se exponen los webhooks firmados de Twilio; el resto sigue siendo local.
        externo = not _acceso_permitido(request)
        if externo and not request.url.path.startswith(("/api/twilio/voz/", "/api/twilio/estado/", "/api/twilio/audio/")):
            return JSONResponse({"detail": "Acceso permitido solo desde este equipo."}, status_code=403)
        if request.url.path.startswith("/api/"):
            ahora = time.monotonic()
            v = self.ventanas[ip]
            while v and ahora - v[0] > 60:
                v.popleft()
            if len(v) >= LIMITE_POR_MINUTO:
                return JSONResponse({"detail": "Demasiadas solicitudes. Intente en un minuto."}, status_code=429)
            v.append(ahora)
            largo = request.headers.get("content-length")
            if largo and largo.isdigit() and int(largo) > MAX_CUERPO:
                return JSONResponse({"detail": "Solicitud demasiado grande."}, status_code=413)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origen = request.headers.get("origin")
                host = request.headers.get("host", "")
                if origen and origen.split("://", 1)[-1] != host:
                    return JSONResponse({"detail": "Origen no permitido."}, status_code=403)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob: data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        if request.url.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        else:  # pantallas (HTML/JS/CSS): el navegador revisa siempre si cambiaron, así no se queda con versiones viejas
            resp.headers["Cache-Control"] = "no-cache"
        return resp


app.add_middleware(Seguridad)


def traducir_error(e: dict) -> str:
    """Mensajes de validación en español."""
    c = e.get("ctx") or {}
    plantillas = {
        "missing": "Campo obligatorio.",
        "string_too_short": "Debe tener al menos {min_length} caracteres.",
        "string_too_long": "Debe tener como máximo {max_length} caracteres.",
        "string_pattern_mismatch": "Formato inválido.",
        "greater_than_equal": "Debe ser mayor o igual que {ge}.",
        "less_than_equal": "Debe ser menor o igual que {le}.",
        "greater_than": "Debe ser mayor que {gt}.",
        "int_parsing": "Debe ser un número entero.",
        "int_type": "Debe ser un número entero.",
        "float_parsing": "Debe ser un número.",
        "decimal_parsing": "Debe ser un número.",
        "date_from_datetime_parsing": "Fecha inválida (AAAA-MM-DD).",
        "date_parsing": "Fecha inválida (AAAA-MM-DD).",
        "bool_parsing": "Debe ser verdadero o falso.",
        "list_type": "Debe ser una lista.",
        "too_long": "Demasiados elementos.",
        "json_invalid": "JSON inválido.",
    }
    tipo = e.get("type", "")
    if tipo in plantillas:
        try:
            return plantillas[tipo].format(**c)
        except (KeyError, IndexError):
            return plantillas[tipo]
    return str(e.get("msg", "Valor inválido.")).replace("Value error, ", "")


@app.exception_handler(RequestValidationError)
async def validacion(_, exc: RequestValidationError):
    errores = []
    for e in exc.errors():
        campo = ".".join(str(x) for x in e.get("loc", []) if x not in ("body", "query", "path"))
        errores.append({"campo": campo, "mensaje": traducir_error(e)})
    return JSONResponse({"detail": "Revise los campos marcados.", "errores": errores}, status_code=422)


for r in (auth, usuarios, clientes, campanas, exclusiones, agentes, conversaciones, llamadas, telefonia, control, twilio):
    app.include_router(r.router)


@app.get("/api/salud")
def salud():
    return {"estado": "ok"}


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/", include_in_schema=False)
    def inicio():
        return FileResponse(FRONTEND / "index.html")
