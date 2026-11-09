"""Proveedor LOCAL de reglas (sin IA externa ni costo). Se usa automáticamente cuando no hay ANTHROPIC_API_KEY.

Implementa la misma interfaz que el proveedor de Anthropic: decide qué herramientas pedir y qué responder a
partir del guion de cobranza. Las herramientas siguen validándose en el backend (identidad, saldo, plazo,
confirmación explícita), así que las reglas de negocio son idénticas. En la interfaz se identifica como
"Agente local de reglas"; no es un modelo de lenguaje.
"""
import ast
import json
import re
import unicodedata
from datetime import date, timedelta

from ..utils import hoy_local
from .proveedor import RespuestaLLM

NOMBRE = "local"
MODELO = "agente-local-reglas-v1"

_DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
          "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
_DIGITOS_PALABRA = {"cero": 0, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
                    "ocho": 8, "nueve": 9}
_AFIRM = re.compile(r"\b(si|confirmo|de acuerdo|acepto|correcto|claro|asi es|esta bien|ok|okay|dale|perfecto)\b")
_NEG = re.compile(r"\b(no|nunca|todavia no|tal vez|quizas?|no se)\b")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _dinero(monto, moneda="GTQ") -> str:
    simbolo = "Q" if moneda == "GTQ" else "US$"
    return f"{simbolo} {float(monto):,.2f}"


def _fecha_texto(iso: str) -> str:
    d = date.fromisoformat(iso)
    nombres = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre"]
    return f"{nombres[d.weekday()]} {d.day} de {meses[d.month - 1]}"


def extraer_fecha(texto: str) -> tuple[date | None, str]:
    """Devuelve (fecha, texto_sin_la_fecha)."""
    t = _norm(texto)
    hoy = hoy_local()
    pats = [
        (r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
        (r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b",
         lambda m: date(int(m[3]) + (2000 if int(m[3]) < 100 else 0) if m[3] else hoy.year, int(m[2]), int(m[1]))),
        (r"\b(\d{1,2}) de (" + "|".join(_MESES) + r")\b", lambda m: date(hoy.year, _MESES[m[2]], int(m[1]))),
        (r"\bpasado manana\b", lambda m: hoy + timedelta(days=2)),
        (r"\bmanana\b", lambda m: hoy + timedelta(days=1)),
        (r"\bhoy\b", lambda m: hoy),
        (r"\ben (\d{1,2}) dias\b", lambda m: hoy + timedelta(days=int(m[1]))),
        (r"\b(?:la )?proxima semana\b", lambda m: hoy + timedelta(days=7)),
        (r"\b(?:el )?(" + "|".join(_DIAS) + r")\b", lambda m: hoy + timedelta(days=(_DIAS[m[1]] - hoy.weekday()) % 7 or 7)),
        (r"\bquincena\b", lambda m: date(hoy.year, hoy.month, 15) if hoy.day < 15 else
         (date(hoy.year, hoy.month, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)),
        (r"\bfin de mes\b", lambda m: (date(hoy.year, hoy.month, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)),
        (r"\bel (\d{1,2})\b", lambda m: date(hoy.year, hoy.month, int(m[1])) if int(m[1]) >= hoy.day else
         (date(hoy.year, hoy.month, 28) + timedelta(days=4)).replace(day=int(m[1]))),
    ]
    for patron, fn in pats:
        m = re.search(patron, t)
        if m:
            try:
                f = fn(m)
            except ValueError:
                continue
            return f, t[:m.start()] + " " + t[m.end():]
    return None, t


def extraer_monto(texto_sin_fecha: str) -> float | None:
    t = texto_sin_fecha
    m = re.search(r"(?:q|quetzales?|\$|us\$)\s*(\d[\d,]*(?:\.\d{1,2})?)", t) or \
        re.search(r"(\d[\d,]*(?:\.\d{1,2})?)\s*(?:quetzales?|dolares?|q\b)", t)
    if not m:
        candidatos = [x for x in re.findall(r"\b\d[\d,]*(?:\.\d{1,2})?\b", t) if len(re.sub(r"\D", "", x)) != 4 or "," in x or "." in x]
        candidatos = [c for c in candidatos if float(c.replace(",", "")) >= 50]
        if not candidatos:
            return None
        return float(candidatos[-1].replace(",", ""))
    return float(m.group(1).replace(",", ""))


class ProveedorLocal:
    nombre = NOMBRE

    def _resp(self, texto: str = "", herramientas: list[tuple[str, dict]] | None = None) -> RespuestaLLM:
        bloques = [{"type": "text", "text": texto}] if texto else []
        for i, (n, a) in enumerate(herramientas or []):
            bloques.append({"type": "tool_use", "id": f"local_{n}_{i}", "name": n, "input": a})
        return RespuestaLLM(bloques=bloques, stop_reason="tool_use" if herramientas else "end_turn", tokens_entrada=0,
                            tokens_salida=0, modelo=MODELO, latencia_ms=1, proveedor=NOMBRE)

    # ---------------------------------------------------------------- punto de entrada
    def generar(self, *, system, messages, max_tokens, tools=None, tool_choice=None, modelo=None) -> RespuestaLLM:
        if tool_choice and tool_choice.get("name") == "registrar_evaluacion":
            return self._evaluar_qa(messages[-1]["content"])
        if tool_choice and tool_choice.get("name") == "registrar_alertas":
            return self._alertas(messages[-1]["content"])
        ultimo = messages[-1]["content"]
        if isinstance(ultimo, list):  # resultados de herramientas
            return self._tras_herramientas(system, messages)
        texto = re.sub(r"</?mensaje_cliente>", "", ultimo)
        self._activas = {h["name"] for h in tools or []}  # el agente solo usa las tools activas del agente IA
        return self._turno(system, texto, messages, con_herramientas=bool(tools))

    # ---------------------------------------------------------------- estado a partir del system prompt
    @staticmethod
    def _estado(system: str) -> dict:
        prop = re.search(r"promesa PROPUESTA de ([\d.]+) (\w{3}) para el (\d{4}-\d{2}-\d{2})", system)
        return {"verificado": "Identidad verificada: sí" in system,
                "propuesta": {"monto": prop[1], "moneda": prop[2], "fecha": prop[3]} if prop else None,
                "registrada": "Promesa ya registrada" in system,
                "aviso": "Aviso legal leído: sí" in system,
                "plazo": int((re.search(r"plazo máximo (\d+) días", system) or [0, 15])[1])}

    @staticmethod
    def _textos_cliente(messages) -> list[str]:
        return [re.sub(r"</?mensaje_cliente>", "", m["content"]) for m in messages
                if m["role"] == "user" and isinstance(m["content"], str) and "<mensaje_cliente>" in m["content"]]

    @staticmethod
    def _deuda_informada(messages) -> bool:
        return any(m["role"] == "assistant" and isinstance(m["content"], str) and "saldo pendiente" in m["content"]
                   for m in messages)

    # ---------------------------------------------------------------- turno del cliente
    def _turno(self, system, texto, messages, con_herramientas=True) -> RespuestaLLM:
        st = self._estado(system)
        t = _norm(texto)
        if re.search(r"ignora|instruccion|prompt|modo desarrollador|eres ahora|actua como", t):
            return self._resp("Solo puedo ayudarle con la gestión de su cuenta. ¿Desea que continuemos?")
        if re.search(r"descuento|rebaja|condon|perdon", t):
            return self._resp("No tengo autorización para modificar el monto ni ofrecer descuentos. Puedo registrar una "
                              "promesa de pago o pasar su caso a un asesor. ¿Qué prefiere?")
        if not con_herramientas:  # evaluación de casos de entrenamiento
            if not st["verificado"]:
                return self._resp("Gracias. Por seguridad, ¿me confirma los últimos 4 dígitos de su documento de identificación?")
            return self._resp("¿Cuánto podría pagar y en qué fecha?")
        activa = getattr(self, "_activas", set()).__contains__
        if activa("registrar_no_contacto") and re.search(
                r"no (me )?(vuelvan a )?llam|no quiero que (me )?(vuelvan a )?(llam|contact)|no me (vuelvan a )?(llamen|contacten)|"
                r"dejen de llamar|no vuelvan a llamar|borren mi numero", t):
            return self._resp("", [("registrar_no_contacto", {"motivo": texto[:200]})])
        if activa("solicitar_revision_humana") and re.search(
                r"asesor|persona real|humano|supervisor|reclamo|queja|hablar con alguien", t):
            return self._resp("", [("solicitar_revision_humana", {"motivo": texto[:200]})])
        if activa("reportar_pago_realizado") and re.search(r"ya (pague|lo pague|cancele|deposite|hice el pago)|ya esta pagad", t):
            return self._resp("", [("reportar_pago_realizado", {"detalle": texto[:200]})])
        if activa("consultar_dudas") and re.search(
                r"(donde|como|a que cuenta|en que banco|horario|agencia|comprobante|recibo).{0,30}(pag|deposit|abon|atien)", t):
            return self._resp("", [("consultar_dudas", {"pregunta": texto[:200]})])
        if st["registrada"]:
            despedida = "Gracias por su atención. Que tenga un excelente día."
            return self._resp(despedida, [("finalizar_conversacion", {"resultado": "PROMESA"})])
        if not st["verificado"]:
            sin_fechas = re.sub(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}(/\d{2,4})?|(q|\$|us\$)\s*[\d,.]+|[\d,.]+\s*(quetzales?|dolares?)",
                                " ", t)
            # Por voz los dígitos llegan como «44, 42», «4 4 4 2» o «cuatro cuatro cuatro dos»: se unen antes de buscarlos.
            sin_fechas = re.sub(r"\b(cero|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\b",
                                lambda m: str(_DIGITOS_PALABRA[m[1]]), sin_fechas)
            digitos = re.findall(r"(?<!\d)\d{4}(?!\d)", re.sub(r"(?<=\d)[\s,.;-]+(?=\d)", "", sin_fechas))
            if digitos:
                return self._resp("", [("verificar_identidad", {"ultimos_digitos": digitos[-1]})])
            if re.search(r"no soy|equivocad|no conozco|no vive|no esta|numero incorrecto", t):
                despedida = "Disculpe la molestia. Que tenga buen día."
                return self._resp(despedida, [("finalizar_conversacion", {"resultado": "NO_ES_TITULAR"})])
            if re.search(r"no (puedo|tengo tiempo)|ocupad|despues|luego|cuelg|adios", t):
                despedida = "Entiendo. Le contactaremos en otro momento. Que tenga buen día."
                return self._resp(despedida, [("finalizar_conversacion", {"resultado": "RECHAZO_TEMPRANO"})])
            if activa("dar_aviso_legal") and not st["aviso"]:
                return self._resp("", [("dar_aviso_legal", {})])
            return self._resp("Gracias. Por seguridad, ¿me confirma los últimos 4 dígitos de su documento de identificación?")
        # Identidad verificada
        if st["propuesta"]:
            if _AFIRM.search(t) and not _NEG.search(t):
                return self._resp("", [("confirmar_promesa", {"frase_cliente": texto.strip()[:200]})])
            if _NEG.search(t):
                return self._resp("Entendido. ¿Qué monto y fecha le serían posibles? Puedo registrar una promesa dentro de "
                                  f"los próximos {st['plazo']} días.")
        fecha, resto = extraer_fecha(texto)
        monto = extraer_monto(resto)
        total = re.search(r"\b(todo|total|completo|la deuda completa)\b", t)
        if total or (monto and fecha) or not self._deuda_informada(messages):
            return self._resp("", [("consultar_deuda", {})])
        if monto and not fecha:
            return self._resp(f"Perfecto, {_dinero(monto)}. ¿En qué fecha realizaría el pago?")
        if fecha and not monto:
            anterior = None
            for previo in reversed(self._textos_cliente(messages)[:-1]):
                anterior = extraer_monto(extraer_fecha(previo)[1])
                if anterior:
                    break
            if anterior:
                return self._resp("", [("proponer_promesa", {"monto": anterior, "fecha": fecha.isoformat()})])
            return self._resp(f"Anotado el {_fecha_texto(fecha.isoformat())}. ¿Qué monto podría pagar ese día?")
        if re.search(r"no (puedo|tengo)|sin dinero|desemple|no me alcanza", t):
            return self._resp("Comprendo su situación. ¿Podría hacer un abono parcial en los próximos días? Si lo prefiere, "
                              "paso su caso a un asesor.")
        return self._resp(f"¿Cuánto podría pagar y en qué fecha? Puedo registrar una promesa dentro de los próximos {st['plazo']} días.")

    # ---------------------------------------------------------------- después de ejecutar herramientas
    def _tras_herramientas(self, system, messages) -> RespuestaLLM:
        asistente = messages[-2]["content"]
        usos = [b for b in asistente if b.get("type") == "tool_use"]
        texto_previo = "".join(b.get("text", "") for b in asistente if b.get("type") == "text")
        resultados = {}
        for b in messages[-1]["content"]:
            try:
                resultados[b["tool_use_id"]] = json.loads(b["content"])
            except (ValueError, KeyError):
                resultados[b.get("tool_use_id")] = {}
        u = usos[-1]
        r = resultados.get(u["id"], {})
        nombre = u["name"]
        cliente = self._textos_cliente(messages)
        ultimo_cliente = cliente[-1] if cliente else ""

        if nombre == "finalizar_conversacion":
            return self._resp(texto_previo or "Gracias por su atención.")
        if nombre == "dar_aviso_legal":
            return self._resp(f"Gracias. {r.get('aviso', '')} Por seguridad, ¿me confirma los últimos 4 dígitos de su "
                              "documento de identificación?")
        if nombre == "consultar_dudas":
            if r.get("encontrada"):
                return self._resp(f"{r['respuesta']} ¿Le puedo ayudar a dejar un acuerdo de pago?")
            return self._resp("No tengo ese dato confirmado en este momento; un asesor se lo puede confirmar. "
                              "¿Le parece si mientras tanto dejamos un acuerdo de pago?")
        if nombre == "reportar_pago_realizado":
            despedida = ("Muchas gracias por avisarnos. Vamos a verificar su pago y mientras tanto no le volveremos a "
                         "llamar por esta deuda. Que tenga un excelente día.")
            return self._resp(despedida, [("finalizar_conversacion", {"resultado": "PAGO_REPORTADO"})])
        if nombre == "verificar_identidad":
            if r.get("verificado"):
                return self._resp("", [("consultar_deuda", {})])
            if "agotados" in str(r.get("error", "")) or r.get("intentos_restantes", 1) <= 0:
                despedida = "No pude verificar su identidad. Un asesor se comunicará con usted. Que tenga buen día."
                return self._resp(despedida, [("finalizar_conversacion", {"resultado": "NO_ES_TITULAR"})])
            return self._resp("Los dígitos no coinciden con nuestros registros. ¿Podría repetirlos, por favor?")
        if nombre == "consultar_deuda":
            if "error" in r:
                return self._resp("Por seguridad, ¿me confirma los últimos 4 dígitos de su documento de identificación?")
            fecha, resto = extraer_fecha(ultimo_cliente)
            monto = extraer_monto(resto)
            if re.search(r"\b(todo|total|completo)\b", _norm(ultimo_cliente)):
                monto = float(r["saldo"])
            if monto and fecha:
                return self._resp("", [("proponer_promesa", {"monto": monto, "fecha": fecha.isoformat()})])
            texto = (f"Gracias por confirmar. Su saldo pendiente es de {_dinero(r['saldo'], r['moneda'])}, con "
                     f"{r['dias_mora']} días de atraso. ¿Cuánto y en qué fecha podría realizar el pago?")
            if monto and not fecha:
                texto = (f"Su saldo pendiente es de {_dinero(r['saldo'], r['moneda'])}. ¿En qué fecha pagaría "
                         f"{_dinero(monto, r['moneda'])}?")
            return self._resp(texto)
        if nombre == "proponer_promesa":
            if r.get("valida"):
                a = u["input"]
                return self._resp(f"Para confirmar: realizará un pago de {_dinero(a['monto'])} el "
                                  f"{_fecha_texto(a['fecha'])}. ¿Lo confirma?")
            return self._resp(f"No puedo registrar ese compromiso. {r.get('error', '')} ¿Qué otro monto o fecha le sería posible?")
        if nombre == "confirmar_promesa":
            if r.get("registrada"):
                despedida = ("Listo, su promesa de pago quedó registrada. Recuerde que puede pagar en cualquier agencia. "
                             "Gracias por su atención, que tenga buen día.")
                return self._resp(despedida, [("finalizar_conversacion", {"resultado": "PROMESA"})])
            return self._resp("Para registrarla necesito su confirmación. ¿Confirma el monto y la fecha indicados?")
        if nombre == "registrar_no_contacto":
            despedida = "Entendido, registré su solicitud y no volveremos a contactarle. Que tenga buen día."
            return self._resp(despedida, [("finalizar_conversacion", {"resultado": "NO_CONTACTO"})])
        if nombre == "solicitar_revision_humana":
            despedida = "He registrado su solicitud; un asesor revisará su caso y se comunicará con usted. Gracias por su paciencia."
            return self._resp(despedida, [("finalizar_conversacion", {"resultado": "REVISION_HUMANA"})])
        return self._resp("¿En qué más puedo ayudarle?")

    # ---------------------------------------------------------------- supervisores por reglas
    def _evaluar_qa(self, contenido: str) -> RespuestaLLM:
        m = re.search(r"<transcripcion>\n?(.*?)\n?</transcripcion>", contenido, re.S)
        transcripcion = m.group(1) if m else ""
        lineas = [l for l in transcripcion.splitlines() if l.strip()]
        frases = re.search(r"FRASES OBLIGATORIAS: (.*)", contenido)
        frases = [f.strip() for f in (frases.group(1) if frases else "").split(",") if f.strip() and f.strip() != "n/d"]
        hay_promesa = "PROMESA REGISTRADA EN SISTEMA: sí" in contenido
        agente = [l for l in lineas if "] AGENTE:" in l]
        hallazgos, puntaje = [], 100.0
        for f in frases:
            linea = next((l for l in agente if _norm(f) in _norm(l)), None)
            if linea:
                hallazgos.append({"tipo": "FRASE_OBLIGATORIA", "descripcion": f"Se dijo «{f}».",
                                  "evidencia": linea.split(": ", 1)[1][:200], "turno": int(re.search(r"\[(\d+)\]", linea)[1])})
            else:
                puntaje -= 15
                hallazgos.append({"tipo": "FRASE_FALTANTE", "descripcion": f"No se encontró la frase obligatoria «{f}».",
                                  "evidencia": "", "turno": None})
        bloqueos = [l for l in lineas if "bloqueada por guardrails" in l]
        if bloqueos:
            puntaje -= 10 * len(bloqueos)
            hallazgos.append({"tipo": "GUARDRAIL", "descripcion": "Hubo respuestas bloqueadas por política.",
                              "evidencia": bloqueos[0].split(": ", 1)[1][:200], "turno": int(re.search(r"\[(\d+)\]", bloqueos[0])[1])})
        verif = next((l for l in agente if "dígitos" in l), None)
        saldo = next((l for l in agente if "saldo pendiente" in l), None)
        if saldo and (not verif or lineas.index(verif) > lineas.index(saldo)):
            puntaje -= 30
            hallazgos.append({"tipo": "PRIVACIDAD", "descripcion": "Se informó el saldo antes de solicitar verificación.",
                              "evidencia": saldo.split(": ", 1)[1][:200], "turno": None})
        confirmacion = None
        if hay_promesa:
            pregunta = next((l for l in agente if "¿Lo confirma?" in l), None)
            confirmacion = pregunta is not None
            if pregunta:
                hallazgos.append({"tipo": "CONFIRMACION", "descripcion": "Se pidió confirmación explícita del compromiso.",
                                  "evidencia": pregunta.split(": ", 1)[1][:200], "turno": None})
            else:
                puntaje -= 25
        evaluacion = {"puntaje": max(0.0, puntaje), "cumple_guion": puntaje >= 70, "trato_adecuado": not bloqueos,
                      "confirmacion_correcta": confirmacion, "compromisos_fuera_politica": False,
                      "incertidumbre": "MEDIA", "hallazgos": hallazgos,
                      "resumen": "Evaluación automática por reglas (sin modelo de IA): frases obligatorias, verificación "
                                 "antes de informar la deuda, bloqueos de política y confirmación de promesas. "
                                 "Requiere revisión humana para aspectos de tono."}
        return self._resp("", [("registrar_evaluacion", evaluacion)])

    def _alertas(self, contenido: str) -> RespuestaLLM:
        try:
            m = ast.literal_eval(re.search(r"<metricas>(.*)</metricas>", contenido, re.S).group(1))
        except Exception:
            m = {}
        alertas = []
        if m.get("llamadas_api_total") and m.get("llamadas_api_fallidas", 0) / m["llamadas_api_total"] > 0.3:
            alertas.append({"tipo": "FALLAS_API", "severidad": "ALTA", "mensaje": "Más del 30 % de las solicitudes a APIs fallaron.",
                            "recomendacion": "Verifique credenciales, saldo y conexión a Internet."})
        if m.get("logins_fallidos", 0) >= 10:
            alertas.append({"tipo": "LOGINS_FALLIDOS", "severidad": "MEDIA",
                            "mensaje": f"{m['logins_fallidos']} inicios de sesión fallidos en 24 h.",
                            "recomendacion": "Revise la bitácora y las cuentas bloqueadas."})
        if m.get("bloqueos_guardrail", 0) >= 5:
            alertas.append({"tipo": "GUARDRAILS", "severidad": "MEDIA",
                            "mensaje": f"{m['bloqueos_guardrail']} respuestas bloqueadas por política en 24 h.",
                            "recomendacion": "Revise el guion y los casos de entrenamiento."})
        return self._resp("", [("registrar_alertas", {"alertas": alertas})])
