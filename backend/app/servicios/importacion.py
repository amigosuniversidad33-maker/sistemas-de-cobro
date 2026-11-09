"""Carga masiva de clientes y deudas (HU-07, DS-02, DF-02). Idempotente y transaccional."""
import csv
import hashlib
import io
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Cliente, Deuda, LoteImportacion, TramoMora
from ..utils import a_decimal, normalizar_telefono

COLUMNAS_REQUERIDAS = ["documento", "nombre", "telefono", "referencia", "saldo", "dias_mora"]
COLUMNAS_OPCIONALES = ["telefono_alterno", "moneda"]
MONEDAS = {"GTQ", "USD"}
MAX_FILAS = 5000
_RE_DOC = re.compile(r"^[A-Za-z0-9\-]{4,30}$")
_RE_REF = re.compile(r"^[A-Za-z0-9\-_/]{1,40}$")


class ErrorImportacion(Exception):
    def __init__(self, mensaje: str, codigo: int = 422):
        super().__init__(mensaje)
        self.codigo = codigo


def clasificar_tramo(dias_mora: int, tramos: list[TramoMora]) -> str:
    for t in tramos:
        if t.dias_min <= dias_mora <= t.dias_max:
            return t.codigo
    return "AL_DIA" if dias_mora <= 0 else "GESTION_ESPECIAL"


def _leer_filas(nombre: str, contenido: bytes) -> list[dict]:
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if ext == "csv":
        if contenido[:4] == b"PK\x03\x04":
            raise ErrorImportacion("El archivo .csv no es texto plano.")
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = contenido.decode("latin-1")
        muestra = texto[:2048]
        delim = ";" if muestra.count(";") > muestra.count(",") else ","
        lector = csv.DictReader(io.StringIO(texto), delimiter=delim)
        if lector.fieldnames is None:
            raise ErrorImportacion("El archivo está vacío.")
        filas = []
        for f in lector:
            filas.append({(k or "").strip().lower(): (v or "").strip() if isinstance(v, str) else v for k, v in f.items()})
        return filas
    if ext == "xlsx":
        if contenido[:4] != b"PK\x03\x04":
            raise ErrorImportacion("El archivo .xlsx no es válido.")
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
        except Exception as e:  # archivo corrupto
            raise ErrorImportacion("No se pudo leer el archivo Excel.") from e
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        try:
            enc = [str(c or "").strip().lower() for c in next(it)]
        except StopIteration:
            raise ErrorImportacion("El archivo está vacío.")
        filas = []
        for fila in it:
            if fila is None or all(c is None or str(c).strip() == "" for c in fila):
                continue
            filas.append({enc[i]: ("" if c is None else str(c).strip()) for i, c in enumerate(fila) if i < len(enc)})
        wb.close()
        return filas
    raise ErrorImportacion("Formato no permitido. Use .csv o .xlsx.")


def importar(db: Session, nombre_archivo: str, contenido: bytes, id_usuario: int | None) -> LoteImportacion:
    nombre_archivo = re.sub(r"[^\w.\- ]", "_", nombre_archivo)[:200]
    huella = hashlib.sha256(contenido).hexdigest()
    previo = db.execute(select(LoteImportacion).where(LoteImportacion.archivo_hash == huella)).scalar_one_or_none()
    if previo is not None:
        raise ErrorImportacion(f"Este archivo ya fue importado (lote #{previo.id_lote}). No se duplicaron registros.", 409)

    filas = _leer_filas(nombre_archivo, contenido)
    if not filas:
        raise ErrorImportacion("El archivo no contiene registros.")
    if len(filas) > MAX_FILAS:
        raise ErrorImportacion(f"Máximo {MAX_FILAS} filas por archivo.")
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in filas[0]]
    if faltan:
        raise ErrorImportacion("Faltan columnas obligatorias: " + ", ".join(faltan))

    tramos = list(db.execute(select(TramoMora)).scalars())
    lote = LoteImportacion(archivo=nombre_archivo, archivo_hash=huella, id_usuario=id_usuario, errores=[])
    db.add(lote)
    db.flush()
    errores, validos, actualizados = [], 0, 0
    vistos: set[tuple[str, str]] = set()

    for n, f in enumerate(filas, start=2):  # fila 1 = encabezado
        motivos = []
        doc = (f.get("documento") or "").replace(" ", "")
        nombre = re.sub(r"\s+", " ", f.get("nombre") or "").strip()
        ref = (f.get("referencia") or "").strip()
        tel = normalizar_telefono(f.get("telefono"))
        tel2 = normalizar_telefono(f.get("telefono_alterno")) if f.get("telefono_alterno") else None
        moneda = (f.get("moneda") or "GTQ").strip().upper()
        if not _RE_DOC.match(doc):
            motivos.append("documento inválido")
        if not (2 <= len(nombre) <= 160) or re.search(r"[<>=]", nombre):
            motivos.append("nombre inválido")
        if not _RE_REF.match(ref):
            motivos.append("referencia inválida")
        if tel is None:
            motivos.append("teléfono inválido")
        if f.get("telefono_alterno") and tel2 is None:
            motivos.append("teléfono alterno inválido")
        if moneda not in MONEDAS:
            motivos.append("moneda no permitida")
        try:
            saldo = a_decimal(f.get("saldo"))
            if saldo <= 0:
                motivos.append("saldo debe ser mayor que cero")
        except ValueError as e:
            saldo = None
            motivos.append(str(e).lower())
        try:
            dias = int(float(str(f.get("dias_mora")).strip()))
            if dias < 0 or dias > 3650:
                motivos.append("días de mora fuera de rango")
        except (TypeError, ValueError):
            dias = None
            motivos.append("días de mora inválidos")
        if (doc, ref) in vistos:
            motivos.append("registro duplicado dentro del archivo")
        if motivos:
            errores.append({"fila": n, "documento": doc[-4:].rjust(len(doc), "*") if doc else "", "motivos": motivos})
            continue
        vistos.add((doc, ref))

        cli = db.execute(select(Cliente).where(Cliente.documento == doc)).scalar_one_or_none()
        es_nuevo = cli is None
        if es_nuevo:
            cli = Cliente(documento=doc, nombre=nombre, telefono=tel, telefono_alterno=tel2, telefono_valido=True,
                          id_lote=lote.id_lote)
            db.add(cli)
            db.flush()
        else:
            cli.nombre, cli.telefono, cli.telefono_valido = nombre, tel, True
            if tel2:
                cli.telefono_alterno = tel2
        deuda = db.execute(select(Deuda).where(Deuda.id_cliente == cli.id_cliente, Deuda.referencia == ref)).scalar_one_or_none()
        tramo = clasificar_tramo(dias, tramos)
        if deuda is None:
            db.add(Deuda(id_cliente=cli.id_cliente, referencia=ref, saldo=saldo, moneda=moneda, dias_mora=dias, tramo=tramo))
            validos += 1
        else:
            deuda.saldo, deuda.moneda, deuda.dias_mora, deuda.tramo, deuda.estado = saldo, moneda, dias, tramo, "ACTIVA"
            actualizados += 1

    lote.registros_validos = validos
    lote.registros_actualizados = actualizados
    lote.registros_rechazados = len(errores)
    lote.errores = errores[:1000]
    return lote
