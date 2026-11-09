"""La voz del agente dice los montos en palabras: miles, millones y centavos sin ambigüedad."""
import pytest

from app.voz.cifras import monto_a_letras, numero_a_letras
from app.voz.deepgram import texto_para_voz


@pytest.mark.parametrize("n, esperado", [
    (0, "cero"), (1, "uno"), (15, "quince"), (21, "veintiuno"), (31, "treinta y uno"), (100, "cien"), (101, "ciento uno"),
    (500, "quinientos"), (1000, "mil"), (1001, "mil uno"), (2500, "dos mil quinientos"), (21000, "veintiún mil"),
    (14577, "catorce mil quinientos setenta y siete"), (100000, "cien mil"), (1_000_000, "un millón"),
    (2_350_000, "dos millones trescientos cincuenta mil"),
])
def test_numero_a_letras(n, esperado):
    assert numero_a_letras(n) == esperado


@pytest.mark.parametrize("cifra, simbolo, esperado", [
    ("14,577.63", "Q", "catorce mil quinientos setenta y siete quetzales con sesenta y tres centavos"),
    ("1.00", "Q", "un quetzal"), ("21", "Q", "veintiún quetzales"), ("0.01", "Q", "cero quetzales con un centavo"),
    ("1,000,000", "Q", "un millón de quetzales"), ("1,201.05", "US$", "mil doscientos un dólares con cinco centavos"),
    ("1,457.7", "Q", "mil cuatrocientos cincuenta y siete quetzales con setenta centavos"),
])
def test_monto_a_letras(cifra, simbolo, esperado):
    assert monto_a_letras(cifra, simbolo) == esperado


def test_texto_del_agente_con_montos():
    assert texto_para_voz("Su saldo pendiente es de Q 14,577.63, con 30 días de atraso.") == (
        "Su saldo pendiente es de catorce mil quinientos setenta y siete quetzales con sesenta y tres centavos con "
        "30 días de atraso.")
    assert texto_para_voz("Puedo pagar 500 quetzales el viernes") == "Puedo pagar quinientos quetzales el viernes"
    assert texto_para_voz("La fecha es 2026-11-12.") == "La fecha es 2026-11-12."  # fechas sin cambio
