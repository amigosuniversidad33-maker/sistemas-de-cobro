"""Interfaz de proveedor LLM. Implementación por defecto: API Messages de Anthropic (HTTP directo).

Para cambiar de proveedor basta con implementar `ProveedorLLM.generar` y registrarlo en `obtener_proveedor`.
"""
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from ..config import get_settings


class ErrorProveedor(Exception):
    def __init__(self, codigo: str, mensaje: str = "", reintentable: bool = False):
        super().__init__(f"{codigo}: {mensaje}")
        self.codigo = codigo
        self.reintentable = reintentable


@dataclass
class RespuestaLLM:
    bloques: list[dict]
    stop_reason: str
    tokens_entrada: int
    tokens_salida: int
    modelo: str
    latencia_ms: int
    proveedor: str = "anthropic"
    intentos: int = 1
    extra: dict = field(default_factory=dict)

    @property
    def texto(self) -> str:
        return "".join(b.get("text", "") for b in self.bloques if b.get("type") == "text").strip()

    @property
    def usos_herramienta(self) -> list[dict]:
        return [b for b in self.bloques if b.get("type") == "tool_use"]


class ProveedorLLM(Protocol):
    nombre: str

    def generar(self, *, system: str, messages: list[dict], max_tokens: int, tools: list[dict] | None = None,
                tool_choice: dict | None = None, modelo: str | None = None) -> RespuestaLLM: ...


CODIGOS_REINTENTABLES = {408, 409, 429, 500, 502, 503, 504, 529}


class AnthropicProveedor:
    nombre = "anthropic"

    def __init__(self, cliente_http: httpx.Client | None = None):
        self.s = get_settings()
        self._http = cliente_http

    def _cliente(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=httpx.Timeout(self.s.llm_timeout_seg, connect=10.0))
        return self._http

    def generar(self, *, system, messages, max_tokens, tools=None, tool_choice=None, modelo=None) -> RespuestaLLM:
        if not self.s.anthropic_api_key:
            raise ErrorProveedor("SIN_CREDENCIAL", "ANTHROPIC_API_KEY no está configurada en .env")
        modelo = modelo or self.s.anthropic_modelo
        cuerpo = {"model": modelo, "max_tokens": max_tokens, "system": system, "messages": messages}
        if tools:
            cuerpo["tools"] = tools
        if tool_choice:
            cuerpo["tool_choice"] = tool_choice
        cabeceras = {"x-api-key": self.s.anthropic_api_key, "anthropic-version": self.s.anthropic_version,
                     "content-type": "application/json"}
        ultimo_error: ErrorProveedor | None = None
        for intento in range(1, self.s.llm_reintentos + 2):
            t0 = time.monotonic()
            try:
                r = self._cliente().post(self.s.anthropic_url, json=cuerpo, headers=cabeceras)
            except httpx.TimeoutException:
                ultimo_error = ErrorProveedor("TIMEOUT", "Tiempo de espera agotado", True)
            except httpx.HTTPError as e:
                ultimo_error = ErrorProveedor("RED", type(e).__name__, True)
            else:
                lat = int((time.monotonic() - t0) * 1000)
                if r.status_code == 200:
                    d = r.json()
                    uso = d.get("usage", {})
                    return RespuestaLLM(bloques=d.get("content", []), stop_reason=d.get("stop_reason", ""),
                                        tokens_entrada=int(uso.get("input_tokens", 0)),
                                        tokens_salida=int(uso.get("output_tokens", 0)), modelo=d.get("model", modelo),
                                        latencia_ms=lat, intentos=intento)
                tipo = ""
                try:
                    tipo = r.json().get("error", {}).get("type", "")
                except ValueError:
                    pass
                ultimo_error = ErrorProveedor(f"HTTP_{r.status_code}", tipo, r.status_code in CODIGOS_REINTENTABLES)
                if r.status_code in CODIGOS_REINTENTABLES and intento <= self.s.llm_reintentos:
                    espera = min(float(r.headers.get("retry-after", 2 ** (intento - 1)) or 1), 5.0)
                    time.sleep(espera)
                    continue
            if ultimo_error and ultimo_error.reintentable and intento <= self.s.llm_reintentos:
                time.sleep(min(2 ** (intento - 1), 4))
                continue
            break
        raise ultimo_error or ErrorProveedor("DESCONOCIDO")


_proveedor_actual: ProveedorLLM | None = None


def obtener_proveedor() -> ProveedorLLM:
    global _proveedor_actual
    if _proveedor_actual is None:
        s = get_settings()
        if s.llm_proveedor == "local" or (s.llm_proveedor == "anthropic" and not s.anthropic_api_key):
            # Sin clave de API: agente local de reglas (sin costo, sin IA externa), identificado en la interfaz.
            from .local import ProveedorLocal

            _proveedor_actual = ProveedorLocal()
        elif s.llm_proveedor == "anthropic":
            _proveedor_actual = AnthropicProveedor()
        else:
            raise ErrorProveedor("PROVEEDOR_NO_SOPORTADO", s.llm_proveedor)
    return _proveedor_actual


def descripcion_proveedor() -> dict:
    p = obtener_proveedor()
    if getattr(p, "nombre", "") == "local":
        return {"proveedor": "local", "etiqueta": "Agente local de reglas (sin IA externa)", "modelo": "agente-local-reglas-v1"}
    return {"proveedor": p.nombre, "etiqueta": "Anthropic (API real)", "modelo": get_settings().anthropic_modelo}


def establecer_proveedor(p: ProveedorLLM | None) -> None:
    """Permite sustituir el proveedor (pruebas unitarias con dobles de prueba explícitos)."""
    global _proveedor_actual
    _proveedor_actual = p
