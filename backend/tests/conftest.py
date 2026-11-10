"""Configuración de pruebas.

Las pruebas unitarias/integración usan SQLite en un archivo temporal y un proveedor LLM DOBLE DE PRUEBA
explícito (no se llama a la API real). Las integraciones reales (Anthropic, Deepgram, FreeSWITCH, MySQL)
se verifican manualmente según docs/PRUEBAS.md.
"""
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="cobros_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
# El respaldo y las migraciones prefieren DATABASE_URL_MIGRACIONES: si .env la define (MySQL real), las pruebas
# volcarían y restaurarían la base real. Se fuerza a la misma base temporal.
os.environ["DATABASE_URL_MIGRACIONES"] = os.environ["DATABASE_URL"]
os.environ["SCRYPT_N"] = "1024"
os.environ["ANTHROPIC_API_KEY"] = "clave-de-prueba-no-real"
os.environ["DEEPGRAM_API_KEY"] = ""
os.environ["TELEFONIA_HABILITADA"] = "false"
os.environ["PRESUPUESTO_DIARIO_USD"] = "5"
os.environ["GRABACIONES_CLAVE"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.ia import proveedor as prov_mod  # noqa: E402
from app.ia.proveedor import ErrorProveedor, RespuestaLLM  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Rol, Usuario  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.semilla import cargar_catalogos  # noqa: E402

PASSWORD = "Clave-Segura-2026"


class LLMDoble:
    """Doble de prueba: devuelve respuestas programadas, en orden. Registra las solicitudes recibidas."""

    nombre = "doble"

    def __init__(self):
        self.cola: list = []
        self.solicitudes: list[dict] = []

    def texto(self, t: str):
        self.cola.append(RespuestaLLM(bloques=[{"type": "text", "text": t}], stop_reason="end_turn", tokens_entrada=100,
                                      tokens_salida=30, modelo="doble", latencia_ms=5, proveedor="doble"))
        return self

    def herramienta(self, nombre: str, args: dict, texto: str = ""):
        bloques = ([{"type": "text", "text": texto}] if texto else []) + [
            {"type": "tool_use", "id": f"tu_{len(self.cola)}", "name": nombre, "input": args}]
        self.cola.append(RespuestaLLM(bloques=bloques, stop_reason="tool_use", tokens_entrada=100, tokens_salida=30,
                                      modelo="doble", latencia_ms=5, proveedor="doble"))
        return self

    def error(self, codigo="HTTP_429", reintentable=True):
        self.cola.append(ErrorProveedor(codigo, "simulado en prueba", reintentable))
        return self

    def generar(self, **kw):
        self.solicitudes.append(kw)
        if not self.cola:
            raise AssertionError("El doble LLM no tiene más respuestas programadas")
        r = self.cola.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(scope="session", autouse=True)
def base_datos():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        cargar_catalogos(db)
        for usuario, rol in (("admin", "ADMINISTRADOR"), ("analista", "ANALISTA_QA"), ("supervisor", "SUPERVISOR")):
            r = db.execute(select(Rol).where(Rol.nombre == rol)).scalar_one()
            db.add(Usuario(usuario=usuario, nombre=usuario.title(), apellido="Prueba", correo=f"{usuario}@prueba.local",
                           id_rol=r.id_rol, hash_password=hash_password(PASSWORD)))
        db.commit()
    yield


@pytest.fixture
def llm():
    doble = LLMDoble()
    prov_mod.establecer_proveedor(doble)
    yield doble
    prov_mod.establecer_proveedor(None)


def cliente_autenticado(usuario: str = "admin") -> TestClient:
    c = TestClient(app, base_url="http://127.0.0.1:8000")
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": PASSWORD})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = c.cookies.get("sc_csrf")
    return c


@pytest.fixture
def admin():
    return cliente_autenticado("admin")


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()
