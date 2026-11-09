# Registro de decisiones

Formato: decisión · justificación · diferencia con los documentos originales (Avance del Sprint 1 = **AV**, Entrega Fase Final = **EF**).

## Contradicciones y vacíos detectados en los documentos

| # | Contradicción o vacío | Fuente | Resolución aplicada |
|---|---|---|---|
| C1 | El objetivo general dice «soporte una capacidad de 65,000 llamadas diarias», pero el alcance la declara meta futura. | AV p.4 (3.2) vs AV p.3 (2.3) | Se trata como **meta futura de arquitectura**. El piloto usa 1 canal y no afirma esa capacidad. El panel la muestra como «meta de diseño (futura)». |
| C2 | La fórmula LNC = LS − LC − LR cuenta como «sin contestar» los fallos técnicos y las llamadas en curso. | AV p.12 (6.5) | Se separan **estado técnico**, **resultado de contacto** y **resultado de cobranza**. Las tasas de contacto usan como denominador LC + LR + LNC; los fallos técnicos tienen tasa propia sobre LS. |
| C3 | DS-06 inserta la promesa en MySQL **antes** de que el cliente confirme. | EF p.11 | La promesa se registra **solo después** de una confirmación explícita en un turno posterior a la propuesta, con frase literal verificada y clave de idempotencia. |
| C4 | DS-01/DER-02 almacenan `token_jwt` en la tabla de sesiones (texto plano). | EF p.3, p.6 | Sesiones con **token opaco en cookie HttpOnly**; en BD solo se guarda su **hash SHA-256**. Ver D3. |
| C5 | DER-01 no incluye `hash_password`; DER-02 sí. `estado` aparece como BOOL (DER) y como texto (AV 9.6). | EF p.2–3, AV p.20 | Se unifica: `hash_password` obligatorio y `estado` VARCHAR (`ACTIVO`/`INACTIVO`) más bloqueo temporal. |
| C6 | La promesa se vincula a `id_llamada` (DER-01) o a `id_cliente_campana` (DER-03). | EF p.2, p.4 | `tb_promesa_pago` referencia **cliente, deuda, campaña, cliente_campaña y llamada**. |
| C7 | La campaña lleva `modulo_mora/dias_min/dias_max` (DER-01) o referencia `MODULO_MORA` (DER-03). | EF p.2, p.4 | Normalizado en `tb_tramo_mora` (1–30 y 31–60). Fuera de rango: `GESTION_ESPECIAL` (requiere regla explícita, no se asigna automáticamente) y `AL_DIA`. Coincide con DF-03. |
| C8 | La llamada se vincula a extensión (DER-01) o a canal (DER-04). | EF p.2, p.5 | Se guardan ambos. |
| C9 | El cliente tiene `contactable` (DER-01) y además existe `NO_CONTACTABLE` (DER-03). | EF p.2, p.4 | Se conservan ambos: la tabla registra motivo, origen y vigencia. |
| C10 | R-05 propone apagado a las 19:55 mientras la ventana regulada es 08:00–20:00. | EF p.79 | Ventana configurable por campaña con fin **exclusivo** (20:00 ya no marca), verificada al encolar y antes de originar. Si se desea margen, configure 19:55 en la campaña. La ventana es una **política inicial**, no una afirmación legal verificada. |
| C11 | R-01 indica «levantar dinámicamente un nodo secundario». | EF p.80 | Fuera de alcance del piloto. Solo se implementa alerta por saturación ≥ 95 % y no se origina sin canal libre. |
| C12 | Entrenamiento menciona «ajuste de los modelos de voz Deepgram». | AV p.6 | No hay fine-tuning. Entrenamiento = guiones versionados + casos de prueba + evaluaciones + prueba de latencia/calidad de voz. |
| C13 | DS-05/DC-03 describen streaming bidireccional en tiempo real con FreeSWITCH. | EF p.10, p.18 | Implementado un **puente de medios por archivos y turnos** (TTS WAV → `uuid_broadcast`; `uuid_record` → STT). El streaming por WebSocket (p. ej. `mod_audio_stream`) queda **pendiente**. |
| C14 | El presupuesto incluye hosting de staging (Q 3,600) y recomienda la Opción C (Whisper + Piper). | AV p.26–28 | La entrega es en **localhost** (sin hosting). Se conserva Deepgram como indica el stack; la Opción C queda como alternativa operativa futura. Los créditos gratuitos de Deepgram no se asumen: deben verificarse. |
| C15 | «Rechazada» = el cliente respondió y rechazó. No se define qué ocurre con ocupado o rechazo antes de contestar. | AV p.8 | `USER_BUSY` y `CALL_REJECTED` (sin contestar) se clasifican como **SIN_CONTESTAR**; las causas de red/gateway como **fallo técnico**; «rechazada» solo si hubo conversación y el agente la marca como rechazo temprano. |
| C16 | Agentes «sin intervención humana», pero el piloto requiere revisión humana. | AV p.4 | El agente puede invocar `solicitar_revision_humana`; QA admite revisión humana; los supervisores humanos no marcan llamadas. |
| C17 | Numeración interna del documento (módulos 2.1–2.13 dentro de la sección 4; referencias a «sección 4.3»). | AV p.5 | Editorial; no afecta al sistema. |

## Decisiones técnicas

| # | Decisión | Justificación |
|---|---|---|
| D1 | **Monolito modular** FastAPI + proceso **worker** separado. | Plazo de 14 días; evita microservicios. Las tareas críticas no dependen de memoria. |
| D2 | **Cola durable en MySQL** (`tb_trabajo`) con `SELECT … FOR UPDATE SKIP LOCKED`. | Sobrevive a reinicios sin introducir Redis/RabbitMQ. Al reiniciar, los trabajos de marcación interrumpidos se marcan FALLIDO (no se re-marcan para evitar doble llamada); los demás se reintentan. |
| D3 | **Cookies HttpOnly + SameSite=Strict + token CSRF ligado a la sesión**, en lugar de JWT. | Revocación inmediata en servidor, nada en `localStorage`. El frontend y la API comparten origen. En HTTPS: `COOKIE_SECURE=true`. |
| D4 | **scrypt** (hashlib/OpenSSL, N=2^17, r=8, p=1) en lugar de **bcrypt** indicado en EF. | Algoritmo mantenido y recomendado por OWASP, resistente a memoria, no trunca a 72 bytes y no requiere compilar dependencias en Windows. Formato autodescriptivo para migrar parámetros. |
| D5 | Llamada HTTP directa a la **API Messages de Anthropic** (sin SDK), detrás de `ProveedorLLM`. | Menos dependencias y control explícito de timeouts, reintentos y cuotas. Cambiar de proveedor = implementar la interfaz. Modelos por `.env` (`claude-haiku-5-5` agente, `claude-sonnet-5-5` supervisores); **verificar disponibilidad en su consola** antes de la demo. |
| D6 | Herramientas del agente con **validación determinista en backend**; el prompt no contiene datos de la deuda. | La seguridad no depende del prompt. El agente no ejecuta SQL ni modifica saldos, permisos o políticas. |
| D7 | **Guardrails deterministas** antes de TTS; >3 bloqueos cierran la llamada; mensaje de contingencia de EF 6.2. | R-03. |
| D8 | Grabaciones cifradas con **Fernet** (`cryptography`); sin clave no se guarda audio. | CU-29 / R-07. Cifrado real, no permisos de archivo. |
| D9 | Respaldos cifrados con Fernet (`RESPALDO_CLAVE`); `mysqldump` con archivo de opciones temporal. | Respaldo protegido; credenciales fuera de la línea de comandos. |
| D10 | Convención **TB_Nombre → tabla `tb_nombre`** (minúsculas). | MySQL en Windows (`lower_case_table_names=1`) y Linux producen el mismo esquema. |
| D11 | Fechas en UTC; reglas y presentación en **America/Guatemala** (`zoneinfo` + `tzdata`). | Requisito del prompt. Guatemala no usa horario de verano. |
| D12 | Pruebas automatizadas con **SQLite** y doble de prueba del LLM; MySQL, APIs reales y FreeSWITCH en pruebas manuales. | El entorno de desarrollo del asistente no tenía MySQL ni credenciales. Ver `docs/PRUEBAS.md`. |
| D13 | Dos usuarios MySQL: `cobros_app` (DML) y `cobros_migra` (DDL/respaldos). | Privilegios mínimos. |
| D14 | Telefonía **deshabilitada por defecto** y limitada a **números autorizados**; 1 canal. | No llamar a destinatarios no autorizados; piloto de bajo volumen. |
| D15 | Pausa de emergencia: cancela trabajos de marcación pendientes y bloquea nuevas conversaciones; la llamada activa termina su turno y se cierra. Activación automática solo por regla determinista (≥80 % de fallas del proveedor en 15 min con ≥5 solicitudes). | Requisito de seguridad operativa. |
| D16 | Frontend sin dependencias externas (íconos SVG propios estilo Lucide, sin CDN) y CSP `default-src 'self'`. | Funciona sin Internet y reduce superficie de XSS. |
