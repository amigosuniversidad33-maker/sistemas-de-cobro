"""Autenticación, sesiones, CSRF, permisos por rol/campaña, entradas maliciosas y secretos."""
import re
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Bitacora, Rol, Sesion, Usuario, ahora_utc
from app.security import hash_password, sha256

from .conftest import PASSWORD, cliente_autenticado


def test_login_y_logout(admin):
    assert admin.get("/api/auth/yo").json()["usuario"]["rol"] == "ADMINISTRADOR"
    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.get("/api/auth/yo").status_code == 401


def test_cookie_de_sesion_httponly_y_samesite():
    c = TestClient(app, base_url="http://127.0.0.1:8000")
    r = c.post("/api/auth/login", json={"usuario": "admin", "password": PASSWORD})
    cookie = [v for k, v in r.headers.multi_items() if k == "set-cookie" and v.startswith("sc_sesion=")][0]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie.replace("Strict", "strict")


def test_mensaje_generico_sin_enumeracion():
    c = TestClient(app, base_url="http://127.0.0.1:8000")
    r1 = c.post("/api/auth/login", json={"usuario": "admin", "password": "incorrecta"})
    r2 = c.post("/api/auth/login", json={"usuario": "no_existe_xyz", "password": "incorrecta"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"]


def test_bloqueo_por_fuerza_bruta(db):
    rol = db.execute(select(Rol).where(Rol.nombre == "AUDITOR")).scalar_one()
    db.add(Usuario(usuario="victima", nombre="Vic", apellido="Tima", correo="victima@prueba.local", id_rol=rol.id_rol,
                   hash_password=hash_password(PASSWORD)))
    db.commit()
    c = TestClient(app, base_url="http://127.0.0.1:8000")
    for _ in range(5):
        assert c.post("/api/auth/login", json={"usuario": "victima", "password": "mala"}).status_code == 401
    # Bloqueada: ni siquiera la contraseña correcta funciona durante el bloqueo
    assert c.post("/api/auth/login", json={"usuario": "victima", "password": PASSWORD}).status_code == 401


def test_sesion_expirada_por_inactividad(db):
    c = cliente_autenticado("admin")
    token = c.cookies.get("sc_sesion")
    ses = db.execute(select(Sesion).where(Sesion.token_hash == sha256(token))).scalar_one()
    ses.ultimo_uso = ahora_utc() - timedelta(hours=2)
    db.commit()
    assert c.get("/api/auth/yo").status_code == 401


def test_sesion_revocada(db):
    c = cliente_autenticado("admin")
    token = c.cookies.get("sc_sesion")
    ses = db.execute(select(Sesion).where(Sesion.token_hash == sha256(token))).scalar_one()
    ses.revocada_en = ahora_utc()
    db.commit()
    assert c.get("/api/auth/yo").status_code == 401


def test_token_no_se_guarda_en_texto_plano(db):
    c = cliente_autenticado("admin")
    token = c.cookies.get("sc_sesion")
    assert db.execute(select(Sesion).where(Sesion.token_hash == token)).first() is None


def test_csrf_obligatorio(admin):
    del admin.headers["X-CSRF-Token"]
    r = admin.post("/api/usuarios", json={})
    assert r.status_code == 403


def test_origen_externo_rechazado(admin):
    r = admin.post("/api/auth/logout", headers={"Origin": "http://sitio-malicioso.example"})
    assert r.status_code == 403


def test_permisos_por_rol():
    analista = cliente_autenticado("analista")
    assert analista.get("/api/clientes").status_code == 403
    assert analista.post("/api/usuarios", json={"nombre": "Xx", "apellido": "Yy", "correo": "a@b.co", "id_rol": 1,
                                                "usuario": "nuevo", "password": "Abcdefgh12!"}).status_code == 403
    assert analista.post("/api/sistema/emergencia", json={"activar": True, "motivo": "prueba"}).status_code == 403
    assert analista.get("/api/qa").status_code == 200


def test_sin_registro_publico():
    c = TestClient(app, base_url="http://127.0.0.1:8000")
    assert c.post("/api/usuarios", json={}).status_code in (401, 403)


def test_alcance_por_campana(admin, db):
    tramo = admin.get("/api/tramos").json()[0]
    a = admin.post("/api/campanas", json={"nombre": "Campaña alcance A", "id_tramo": tramo["id_tramo"]}).json()
    b = admin.post("/api/campanas", json={"nombre": "Campaña alcance B", "id_tramo": tramo["id_tramo"]}).json()
    sup = db.execute(select(Usuario).where(Usuario.usuario == "supervisor")).scalar_one()
    assert admin.post("/api/supervision", json={"id_usuario": sup.id_usuario, "id_campana": a["id_campana"]}).status_code == 201
    s = cliente_autenticado("supervisor")
    ids = [c["id_campana"] for c in s.get("/api/campanas").json()["items"]]
    assert a["id_campana"] in ids and b["id_campana"] not in ids
    assert s.get(f"/api/campanas/{b['id_campana']}").status_code == 404  # registro ajeno: no se revela
    assert s.post(f"/api/campanas/{b['id_campana']}/estado", json={"estado": "ACTIVA"}).status_code == 404


def test_entradas_maliciosas(admin):
    r = admin.get("/api/usuarios", params={"q": "' OR 1=1; DROP TABLE tb_usuario; --"})
    assert r.status_code == 200 and r.json()["total"] == 0
    r = admin.post("/api/usuarios", json={"nombre": "<script>alert(1)</script>", "apellido": "Pérez", "correo": "x@y.co",
                                          "id_rol": 1, "usuario": "xss", "password": "Abcdefgh12!"})
    assert r.status_code == 422
    r = admin.post("/api/usuarios", json={"nombre": "Ana", "apellido": "Pérez", "correo": "no-es-correo", "id_rol": 1,
                                          "usuario": "ana", "password": "Abcdefgh12!"})
    assert r.status_code == 422


def test_contrasena_debil_rechazada(admin):
    r = admin.post("/api/usuarios", json={"nombre": "Ana", "apellido": "Pérez", "correo": "ana@y.co", "id_rol": 1,
                                          "usuario": "ana2", "password": "aaaaaaaaaa"})
    assert r.status_code == 422


def test_crear_modificar_y_asignar_rol(admin):
    roles = {r["nombre"]: r["id_rol"] for r in admin.get("/api/roles").json()}
    r = admin.post("/api/usuarios", json={"nombre": "María José", "apellido": "Velásquez", "correo": "mj@prueba.local",
                                          "id_rol": roles["AUDITOR"], "usuario": "mjose", "password": "Segura-2026-xx"})
    assert r.status_code == 201, r.text
    uid = r.json()["id_usuario"]
    assert admin.post("/api/usuarios", json={"nombre": "Otra", "apellido": "Persona", "correo": "mj@prueba.local",
                                             "id_rol": roles["AUDITOR"], "usuario": "otra", "password": "Segura-2026-xx"}).status_code == 409
    r = admin.put(f"/api/usuarios/{uid}", json={"nombre": "María José", "apellido": "Velásquez Ávila",
                                                "correo": "mj@prueba.local", "id_rol": roles["AUDITOR"]})
    assert r.json()["apellido"] == "Velásquez Ávila"
    r = admin.post(f"/api/usuarios/{uid}/rol", json={"id_rol": roles["SUPERVISOR"]})
    assert r.json()["rol"] == "SUPERVISOR"


def test_bitacora_sin_contrasenas(db):
    for b in db.execute(select(Bitacora)).scalars():
        assert "password" not in str(b.detalle or "").lower()
        assert PASSWORD not in str(b.detalle or "")


def test_sin_secretos_en_frontend():
    raiz = Path(__file__).resolve().parents[2] / "frontend"
    for f in raiz.rglob("*"):
        if f.is_file() and f.suffix in (".js", ".html", ".css"):
            t = f.read_text(encoding="utf-8")
            # Se permiten los NOMBRES de variables en mensajes de ayuda, nunca valores de claves.
            assert not re.search(r"sk-ant-[A-Za-z0-9]|(api[_-]?key|password|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{12,}|Token [a-f0-9]{20,}", t, re.I), f
            assert "localStorage.setItem(\"token" not in t


def test_estado_del_sistema_no_expone_secretos(admin):
    import os

    r = admin.get("/api/sistema/estado").text
    assert os.environ["ANTHROPIC_API_KEY"] not in r and "credencial_configurada" in r


def test_cabeceras_de_seguridad(admin):
    r = admin.get("/api/auth/yo")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_acceso_desde_la_red_local(monkeypatch):
    """Con ACCESO_RED_LOCAL, otra computadora de la red local entra por la IP; desde Internet o por túnel, no."""
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import app

    vecino = TestClient(app, base_url="http://192.168.1.12:8000", client=("192.168.1.30", 50000))
    monkeypatch.setattr(get_settings(), "acceso_red_local", False)
    assert vecino.get("/api/salud").status_code == 403  # desactivado
    monkeypatch.setattr(get_settings(), "acceso_red_local", True)
    assert vecino.get("/api/salud").status_code == 200
    assert vecino.get("/api/salud", headers={"X-Forwarded-For": "8.8.8.8"}).status_code == 403  # túnel
    internet = TestClient(app, base_url="http://192.168.1.12:8000", client=("8.8.8.8", 50000))
    assert internet.get("/api/salud").status_code == 403
    dominio = TestClient(app, base_url="http://cobros.ejemplo.com:8000", client=("192.168.1.30", 50000))
    assert dominio.get("/api/salud").status_code == 403  # Host con nombre de dominio (DNS rebinding)


def test_pantallas_con_version_y_sin_salir_de_frontend():
    """El index apunta a /static/v<versión>/ (el navegador no usa copias viejas) y esa ruta no permite salir de frontend."""
    import re

    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    v = re.search(r'"/static/v(\w+)/js/app\.js"', c.get("/").text)[1]
    assert c.get(f"/static/v{v}/js/app.js").status_code == 200
    for ruta in ("../backend/.env", "..%2Fbackend%2F.env", "../../Windows/win.ini"):
        assert c.get(f"/static/v{v}/{ruta}").status_code == 404


def test_restablecer_clave_por_cli(monkeypatch):
    """La nueva contraseña se pide sin mostrarse, desbloquea la cuenta y revoca las sesiones abiertas."""
    import argparse

    from sqlalchemy import select

    from app import cli
    from app.db import SessionLocal
    from app.models import Usuario
    from app.security import verificar_password

    nueva = "Clave-Segura-2026"  # la misma de conftest, para no afectar a otras pruebas que usan este usuario
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: nueva)
    with SessionLocal() as db:
        u = db.execute(select(Usuario).where(Usuario.usuario == "supervisor")).scalar_one()
        u.intentos_fallidos = 9
        db.commit()
    cli.cmd_restablecer_clave(argparse.Namespace(usuario="supervisor"))
    with SessionLocal() as db:
        u = db.execute(select(Usuario).where(Usuario.usuario == "supervisor")).scalar_one()
        assert verificar_password(nueva, u.hash_password) and u.intentos_fallidos == 0
