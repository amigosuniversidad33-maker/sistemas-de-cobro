"""Guardrails deterministas (DS-10, DF-11). No dependen del LLM ni de otro supervisor IA."""
import re
from dataclasses import dataclass, field

from ..models import PoliticaIA

MAX_ENTRADA = 1000
MAX_SALIDA = 700

# Reglas fijas que no se pueden desactivar desde la interfaz.
_FIJAS_SALIDA = [
    (re.compile(r"(?:\d[ -]?){13,19}"), "Expone un número de documento o tarjeta"),
    (re.compile(r"(?i)\b(select|insert|update|delete|drop)\b.+\b(from|into|table)\b"), "Contenido técnico no permitido"),
    (re.compile(r"(?i)instrucciones del sistema|system prompt"), "Revela instrucciones internas"),
]
_DATOS_DEUDA = re.compile(r"(?i)(\bQ\s?\d|\$\s?\d|\bUSD\b|\bGTQ\b|\d+[.,]\d{2}\b|\bsaldo\b|d[ií]as de (mora|atraso)|\badeuda\b)")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


@dataclass
class Resultado:
    permitido: bool
    motivos: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)


def _compilar(patron: str):
    try:
        return re.compile(patron, re.IGNORECASE)
    except re.error:
        return None


def validar_patron(patron: str) -> bool:
    if len(patron) > 300:
        return False
    return _compilar(patron) is not None


def revisar_entrada(texto: str, politica: PoliticaIA | None) -> Resultado:
    res = Resultado(permitido=True)
    if len(texto) > MAX_ENTRADA:
        res.permitido = False
        res.motivos.append("Mensaje demasiado largo")
    if politica:
        for r in politica.reglas:
            if r.activa and r.tipo == "ENTRADA":
                rx = _compilar(r.patron)
                if rx and rx.search(texto):
                    (res.alertas if r.accion == "ALERTAR" else res.motivos).append(r.descripcion or r.patron)
                    if r.accion == "BLOQUEAR":
                        res.permitido = False
    return res


def revisar_salida(texto: str, politica: PoliticaIA | None, identidad_verificada: bool) -> Resultado:
    res = Resultado(permitido=True)
    if not texto.strip():
        res.permitido = False
        res.motivos.append("Respuesta vacía")
    if len(texto) > MAX_SALIDA:
        res.permitido = False
        res.motivos.append("Respuesta demasiado larga para voz")
    if _EMOJI.search(texto):
        res.permitido = False
        res.motivos.append("Contiene emojis")
    for rx, desc in _FIJAS_SALIDA:
        if rx.search(texto):
            res.permitido = False
            res.motivos.append(desc)
    if not identidad_verificada and _DATOS_DEUDA.search(texto):
        res.permitido = False
        res.motivos.append("Divulga información de la deuda antes de verificar identidad")
    if politica:
        for r in politica.reglas:
            if r.activa and r.tipo == "SALIDA":
                rx = _compilar(r.patron)
                if rx and rx.search(texto):
                    if r.accion == "BLOQUEAR":
                        res.permitido = False
                        res.motivos.append(r.descripcion or r.patron)
                    else:
                        res.alertas.append(r.descripcion or r.patron)
    return res
