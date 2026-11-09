"""Cifras en palabras para la voz del agente: «Q 14,577.63» -> «catorce mil quinientos setenta y siete quetzales con
sesenta y tres centavos». Las voces leen mal los separadores de miles y los decimales; en palabras no hay ambigüedad.
Solo cambia lo que se pronuncia: la pantalla y la transcripción conservan la cifra original."""
import re

_UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
             "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno",
             "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho",
             "veintinueve"]
_DECENAS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
_CENTENAS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
             "ochocientos", "novecientos"]
_MONEDAS = {"Q": ("quetzal", "quetzales"), "US$": ("dólar", "dólares"), "$": ("dólar", "dólares")}


def _apocopar(palabras: str) -> str:
    """Delante de un sustantivo: «uno» -> «un», «veintiuno» -> «veintiún» (un quetzal, veintiún mil)."""
    if palabras.endswith("veintiuno"):
        return palabras[:-len("veintiuno")] + "veintiún"
    if palabras.endswith("uno"):
        return palabras[:-3] + "un"
    return palabras


def _menor_mil(n: int) -> str:
    if n < 30:
        return _UNIDADES[n]
    if n < 100:
        d, u = divmod(n, 10)
        return _DECENAS[d] + (f" y {_UNIDADES[u]}" if u else "")
    if n == 100:
        return "cien"
    c, resto = divmod(n, 100)
    return _CENTENAS[c] + (f" {_menor_mil(resto)}" if resto else "")


def numero_a_letras(n: int, apocope: bool = False) -> str:
    """Entero en palabras (hasta 999,999,999,999). apocope=True cuando sigue un sustantivo (quetzales, centavos)."""
    if n < 0:
        return "menos " + numero_a_letras(-n, apocope)
    if n == 0:
        return "cero"
    partes = []
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    if millones:
        partes.append("un millón" if millones == 1 else f"{_apocopar(numero_a_letras(millones))} millones")
    if miles:
        partes.append("mil" if miles == 1 else f"{_apocopar(_menor_mil(miles))} mil")
    if unidades:
        partes.append(_menor_mil(unidades))
    texto = " ".join(partes)
    if apocope and unidades:
        texto = _apocopar(texto)
    if apocope and not unidades and not miles and millones:
        texto += " de"  # «un millón de quetzales»
    return texto


def _entero_y_centavos(cifra: str) -> tuple[int, int]:
    limpia = cifra.replace(",", "")
    if "." in limpia:
        entero, dec = limpia.split(".", 1)
        return int(entero or 0), int((dec + "0")[:2])
    return int(limpia), 0


def monto_a_letras(cifra: str, simbolo: str = "Q") -> str:
    entero, centavos = _entero_y_centavos(cifra)
    singular, plural = _MONEDAS.get(simbolo, _MONEDAS["Q"])
    texto = f"{numero_a_letras(entero, apocope=True)} {singular if entero == 1 else plural}"
    if centavos:
        texto += f" con {numero_a_letras(centavos, apocope=True)} {'centavo' if centavos == 1 else 'centavos'}"
    return texto


_CIFRA = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
# (?!\d|,\d): la cifra termina donde no sigue otro dígito; una coma de la frase («Q 14,577.63, con…») no la corta.
_CON_SIMBOLO = re.compile(rf"(US\$|\$|Q)\s?({_CIFRA})(?!\d|,\d)")
_CON_PALABRA = re.compile(rf"(?<![\w.,])({_CIFRA})\s*(quetzales|quetzal|dólares|dolares|dólar|dolar)\b", re.IGNORECASE)
_CON_MILES = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+)(?:\.(\d{1,2}))?(?!\d|,\d)")


def cifras_para_voz(texto: str) -> str:
    """Montos con moneda y cifras con separador de miles, en palabras. Fechas, días y números sueltos no cambian."""
    texto = _CON_SIMBOLO.sub(lambda m: monto_a_letras(m[2], m[1]), texto or "")
    texto = _CON_PALABRA.sub(lambda m: monto_a_letras(m[1], "US$" if m[2].lower().startswith("d") else "Q"), texto)

    def miles(m):
        entero = numero_a_letras(int(m[1].replace(",", "")))
        return entero + (f" punto {numero_a_letras(int(m[2]))}" if m[2] else "")
    return _CON_MILES.sub(miles, texto)
