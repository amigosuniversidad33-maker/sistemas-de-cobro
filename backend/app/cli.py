"""Comandos de administración.

  python -m app.cli semilla              Carga catálogos (roles, permisos, tramos, política, guiones, agentes, riesgos)
  python -m app.cli crear-admin          Crea el PRIMER administrador (pide la contraseña sin mostrarla)
  python -m app.cli demo                 Carga clientes ficticios y una campaña de demostración
  python -m app.cli purgar               Aplica la política de retención (pide confirmación)
  python -m app.cli verificar            Muestra qué dependencias externas están configuradas (sin mostrar secretos)
"""
import argparse
import getpass
import sys
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, update

from .config import get_settings
from .db import sesion_db
from .models import (
    Bitacora,
    Campana,
    CampanaAgente,
    AgenteIA,
    Grabacion,
    Rol,
    Sesion,
    TramoMora,
    Transcripcion,
    TurnoConversacion,
    Usuario,
    ahora_utc,
)
from .security import hash_password, validar_fortaleza

DEMO_CSV = Path(__file__).resolve().parents[2] / "datos_demo" / "clientes_demo.csv"


def cmd_semilla(_):
    from .semilla import cargar_catalogos

    with sesion_db() as db:
        cargar_catalogos(db)
    print("Catálogos cargados.")


def cmd_crear_admin(args):
    with sesion_db() as db:
        rol = db.execute(select(Rol).where(Rol.nombre == "ADMINISTRADOR")).scalar_one_or_none()
        if rol is None:
            sys.exit("Primero ejecute: python -m app.cli semilla")
        hay_admin = db.execute(select(func.count(Usuario.id_usuario)).where(Usuario.id_rol == rol.id_rol)).scalar_one()
        if hay_admin and not args.forzar:
            if args.generar:
                print("YA_EXISTE")
                return
            sys.exit("Ya existe un administrador. Los demás usuarios se crean desde la aplicación (módulo Agentes Internos).")
        usuario = (args.usuario or input("Usuario: ")).strip().lower()
        nombre = args.nombre or input("Nombre: ").strip()
        apellido = args.apellido or input("Apellido: ").strip()
        correo = (args.correo or input("Correo: ")).strip().lower()
        if args.generar:
            # Contraseña aleatoria de un solo uso (se muestra una vez; no hay contraseñas fijas en el código)
            import secrets
            import string

            p1 = (secrets.choice(string.ascii_uppercase) + secrets.choice(string.ascii_lowercase)
                  + secrets.choice(string.digits) + "-" + secrets.token_urlsafe(9))
            db.add(Usuario(usuario=usuario, nombre=nombre, apellido=apellido, correo=correo, id_rol=rol.id_rol,
                           hash_password=hash_password(p1), estado="ACTIVO"))
            print(f"USUARIO={usuario}")
            print(f"PASSWORD={p1}")
            return
        while True:
            p1 = getpass.getpass("Contraseña (mín. 10, 3 tipos de caracteres): ")
            p2 = getpass.getpass("Repita la contraseña: ")
            if p1 != p2:
                print("No coinciden.")
                continue
            try:
                validar_fortaleza(p1)
                break
            except Exception as e:  # HTTPException con detalle
                print(getattr(e, "detail", str(e)))
        db.add(Usuario(usuario=usuario, nombre=nombre, apellido=apellido, correo=correo, id_rol=rol.id_rol,
                       hash_password=hash_password(p1), estado="ACTIVO"))
    print(f"Administrador '{usuario}' creado.")


def cmd_restablecer_clave(args):
    """Nueva contraseña para un usuario que la olvidó. Se escribe en la terminal sin mostrarse (nunca va en argumentos).
    También desbloquea la cuenta y revoca sus sesiones abiertas."""
    from .auditoria import auditar

    with sesion_db() as db:
        u = db.execute(select(Usuario).where(Usuario.usuario == args.usuario.strip().lower())).scalar_one_or_none()
        if u is None:
            sys.exit(f"No existe el usuario '{args.usuario}'.")
        while True:
            p1 = getpass.getpass(f"Nueva contraseña para '{u.usuario}' (mín. 10, 3 tipos de caracteres; no se ve al escribir): ")
            p2 = getpass.getpass("Repita la contraseña: ")
            if p1 != p2:
                print("No coinciden.")
                continue
            try:
                validar_fortaleza(p1)
                break
            except Exception as e:  # HTTPException con detalle
                print(getattr(e, "detail", str(e)))
        u.hash_password = hash_password(p1)
        u.intentos_fallidos, u.bloqueado_hasta, u.estado = 0, None, "ACTIVO"
        db.execute(update(Sesion).where(Sesion.id_usuario == u.id_usuario, Sesion.revocada_en.is_(None))
                   .values(revocada_en=ahora_utc()))
        auditar(db, "CLAVE_RESTABLECIDA_CLI", "usuario", u.id_usuario, {"usuario": u.usuario})
    print(f"Contraseña de '{u.usuario}' actualizada. Ya puede iniciar sesión.")


def cmd_demo(_):
    from .servicios import campanas as srv
    from .servicios import importacion

    with sesion_db() as db:
        try:
            lote = importacion.importar(db, DEMO_CSV.name, DEMO_CSV.read_bytes(), None)
            print(f"Lote #{lote.id_lote}: {lote.registros_validos} nuevos, {lote.registros_actualizados} actualizados, "
                  f"{lote.registros_rechazados} rechazados (las filas inválidas son intencionales para demostrar validaciones).")
        except importacion.ErrorImportacion as e:
            print(f"Importación: {e}")
        from .utils import hoy_local

        hoy = hoy_local()
        for codigo, nombre in (("MORA_TEMPRANA", "Demo Recordatorio / Mora Temprana"), ("MORA_TARDIA", "Demo Mora Tardía")):
            if db.execute(select(Campana).where(Campana.nombre == nombre)).scalar_one_or_none():
                continue
            tramo = db.execute(select(TramoMora).where(TramoMora.codigo == codigo)).scalar_one()
            c = Campana(nombre=nombre, id_tramo=tramo.id_tramo, fecha_inicio=hoy, fecha_fin=hoy + timedelta(days=30),
                        mensaje_base="Recordatorio de pago de su crédito (datos ficticios).", estado="BORRADOR")
            db.add(c)
            db.flush()
            ag = next((a for a in db.execute(select(AgenteIA)).scalars() if a.guion and a.guion.tramo == codigo), None)
            if ag:
                db.add(CampanaAgente(id_campana=c.id_campana, id_agente=ag.id_agente))
            db.flush()
            db.refresh(c)
            print(f"Campaña '{nombre}': {srv.clasificar_y_asignar(db, c)}")
    print("Datos de demostración listos (todos ficticios).")


def cmd_purgar(args):
    s = get_settings()
    if not args.si:
        r = input("Esto ELIMINA datos según la política de retención. Escriba ELIMINAR para continuar: ")
        if r.strip() != "ELIMINAR":
            sys.exit("Cancelado.")
    ahora = ahora_utc()
    with sesion_db() as db:
        n_ses = db.execute(delete(Sesion).where(Sesion.expira < ahora - timedelta(days=s.retencion_sesiones_dias))).rowcount
        n_bit = db.execute(delete(Bitacora).where(Bitacora.fecha < ahora - timedelta(days=s.retencion_bitacora_dias))).rowcount
        n_tr = db.execute(update(Transcripcion).where(Transcripcion.fecha < ahora - timedelta(days=s.retencion_transcripciones_dias))
                          .values(texto="[eliminada por retención]")).rowcount
        n_turn = db.execute(update(TurnoConversacion).where(
            TurnoConversacion.fecha < ahora - timedelta(days=s.retencion_transcripciones_dias)).values(texto="[eliminado]")).rowcount
        viejas = db.execute(select(Grabacion).where(Grabacion.fecha < ahora - timedelta(days=s.retencion_grabaciones_dias))).scalars().all()
        base = Path(s.grabaciones_dir)
        for g in viejas:
            (base / g.ruta_audio).unlink(missing_ok=True)
            db.delete(g)
    print(f"Sesiones: {n_ses}, bitácora: {n_bit}, transcripciones: {n_tr}, turnos: {n_turn}, grabaciones: {len(viejas)}")


def cmd_verificar(_):
    s = get_settings()
    def si(v):
        return "configurada" if v else "FALTA"
    print(f"Base de datos: {s.database_url.split('@')[-1]}")
    print(f"Anthropic API key: {si(s.anthropic_api_key)}  (modelo agente: {s.anthropic_modelo}, supervisor: {s.anthropic_modelo_supervisor})")
    print(f"Deepgram API key: {si(s.deepgram_api_key)}  (STT: {s.deepgram_stt_modelo}, TTS: {s.deepgram_tts_modelo})")
    print(f"Clave de grabaciones: {si(s.grabaciones_clave)}")
    print(f"Telefonía habilitada: {s.telefonia_habilitada}; ESL password: {si(s.freeswitch_esl_password)}; "
          f"carpeta audio: {s.freeswitch_dir_audio or 'FALTA'}")
    try:
        with sesion_db() as db:
            db.execute(select(1))
        print("Conexión a base de datos: OK")
    except Exception as e:
        print(f"Conexión a base de datos: ERROR ({type(e).__name__})")


def main():
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("semilla").set_defaults(f=cmd_semilla)
    a = sub.add_parser("crear-admin")
    a.add_argument("--usuario")
    a.add_argument("--nombre")
    a.add_argument("--apellido")
    a.add_argument("--correo")
    a.add_argument("--forzar", action="store_true", help="Permite crear otro administrador")
    a.add_argument("--generar", action="store_true", help="Genera una contraseña aleatoria y la muestra una vez")
    a.set_defaults(f=cmd_crear_admin)
    r = sub.add_parser("restablecer-clave", help="Nueva contraseña para un usuario (se escribe sin mostrarse)")
    r.add_argument("--usuario", default="admin")
    r.set_defaults(f=cmd_restablecer_clave)
    sub.add_parser("demo").set_defaults(f=cmd_demo)
    pu = sub.add_parser("purgar")
    pu.add_argument("--si", action="store_true")
    pu.set_defaults(f=cmd_purgar)
    sub.add_parser("verificar").set_defaults(f=cmd_verificar)
    args = p.parse_args()
    args.f(args)


if __name__ == "__main__":
    main()
