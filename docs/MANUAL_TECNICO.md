# Manual técnico

## 1. Arquitectura

```
Navegador (HTML/CSS/JS, tema azul)  ──HTTP 127.0.0.1:8000──▶  FastAPI (app.main)
                                                                │  routers por módulo
                                                                │  security (sesiones, CSRF, RBAC, alcance)
                                                                │  servicios (importación, reglas, campañas, promesas, consumo)
                                                                │  ia (proveedor LLM, agente+herramientas, guardrails, supervisores)
                                                                │  voz (Deepgram STT/TTS, grabaciones Fernet)
                                                                ▼
                                                           MySQL 8 (cobros_ia)  ◀── Worker (app.worker): cola tb_trabajo
                                                                                     ├─ MARCAR → telefonia.marcador → FreeSWITCH (ESL :8021)
                                                                                     ├─ QA_LLAMADA → supervisor QA
                                                                                     ├─ REVISAR_PROMESAS (cada hora)
                                                                                     └─ reglas deterministas (cada minuto)
Servicios externos (Internet): api.anthropic.com · api.deepgram.com · proveedor SIP (vía FreeSWITCH)
```

- **Monolito modular** con un proceso adicional (worker). Sin microservicios ni Kubernetes.
- Frontend servido por FastAPI en el mismo origen: no se habilita CORS.
- Capas de los diagramas DARQ-01/DCOMP-01..04: presentación (`frontend/`), negocio (`app/routers`, `app/servicios`),
  IA (`app/ia`, `app/voz`), datos/telefonía (`app/models.py`, `app/telefonia`).

## 2. Modelo de datos (unificación DER-01 a DER-04)

41 tablas `tb_*` (ver `docs/esquema_mysql.sql`). Principales:

| Grupo | Tablas |
|---|---|
| Seguridad (DER-02) | `tb_rol`, `tb_permiso`, `tb_rol_permiso`, `tb_usuario` (+`hash_password`, bloqueo), `tb_sesion` (hash de token y CSRF), `tb_intento_login`, `tb_bitacora`, `tb_asignacion_supervision` |
| Cobranza (DER-03) | `tb_tramo_mora` (MODULO_MORA), `tb_lote_importacion` (CARGA_LOTE, hash único), `tb_cliente`, `tb_deuda` (DECIMAL + moneda), `tb_campana`, `tb_campana_agente`, `tb_cliente_campana`, `tb_no_contactable`, `tb_promesa_pago`, `tb_seguimiento_promesa` |
| IA (DER-01/02/04) | `tb_agente_ia`, `tb_guion` (versionado), `tb_caso_uso`, `tb_evaluacion_caso`, `tb_politica_ia` (versionada), `tb_regla_guardrail` |
| Operación (DER-04) | `tb_llamada` (estado técnico / contacto / cobranza separados; versiones de guion y política), `tb_turno_conversacion`, `tb_evento_llamada` (clave única idempotente), `tb_grabacion`, `tb_transcripcion`, `tb_evaluacion_qa`, `tb_prueba_llamada` |
| Telefonía (DER-04) | `tb_planta_freeswitch`, `tb_troncal_sip`, `tb_extension_sip`, `tb_canal_concurrente`, `tb_numero_autorizado` |
| Control | `tb_trabajo` (cola durable), `tb_alerta`, `tb_consumo_api`, `tb_configuracion`, `tb_riesgo` |

Reglas: PK/FK en todas las relaciones; unicidad en usuario, correo, documento, (cliente, referencia), (campaña, deuda),
(nombre, versión) de guion y política, clave de idempotencia de promesas, eventos y trabajos; índices en fechas de llamadas,
estados de cola, teléfono y mora para filtros y reportes. Importes `NUMERIC(14,2)`. Fechas UTC.

**Idempotencia:** importaciones (hash SHA-256 del archivo + upsert por documento/referencia), promesas (`llamada:{id}:deuda:{id}`),
eventos (`uuid:TIPO`), trabajos (`marcar:{cc}:{intento}:{aleatorio}` + verificación «YA_EN_COLA»), alertas periódicas (clave por hora).

## 3. Flujos críticos

**Reglas pre-marcación** (`servicios/reglas.py`) al encolar y antes de originar: pausa de emergencia, campaña activa y vigente,
estado de gestión, deuda activa, teléfono válido, exclusión (por cliente o teléfono), ventana horaria local, intentos totales y
diarios, tiempo mínimo, llamada simultánea, promesa vigente, presupuesto; al originar además capacidad del piloto, canal libre y
número autorizado. Concurrencia: los canales se reservan con `FOR UPDATE SKIP LOCKED`; una exclusión o pausa posterior al encolado
cancela los trabajos pendientes y, si el worker ya tomó el trabajo, la re-verificación lo rechaza.

**Agente** (`ia/agente.py`): Audio → STT → gestor de diálogo/LLM → herramientas validadas → guardrails → TTS → audio.
Herramientas: `verificar_identidad`, `consultar_deuda`, `proponer_promesa`, `confirmar_promesa`, `registrar_no_contacto`,
`solicitar_revision_humana`, `finalizar_conversacion`. Se registra proveedor, modelo, versión de prompt (`agente-v1`), tokens,
latencia y costo estimado por llamada a la API.

**Telefonía** (`telefonia/marcador.py`): control por Event Socket (`api originate … &park()`), audio por archivos compartidos
(`FREESWITCH_DIR_AUDIO`): TTS WAV 8 kHz → `uuid_broadcast`; `uuid_record` (ventana de escucha) → STT. Silencio dos veces → despedida.
Siempre se libera el canal en `finally`; al reiniciar el worker se recuperan llamadas, canales y trabajos huérfanos.

**Pausa de emergencia:** cancela trabajos MARCAR pendientes, devuelve clientes EN_COLA a PENDIENTE y bloquea nuevas conversaciones.
Una llamada telefónica activa no se corta de golpe: el marcador termina el turno en curso, la cierra y no origina más.

## 4. Seguridad y modelo de amenazas

| Amenaza | Control |
|---|---|
| Robo de sesión / XSS | Cookie HttpOnly + SameSite=Strict; CSP `default-src 'self'` sin scripts ni estilos en línea; escape de todo texto dinámico |
| CSRF | Token double-submit ligado al hash guardado en la sesión + verificación de `Origin` |
| Fuerza bruta / enumeración | Bloqueo por usuario (5 fallos/15 min), límite por IP (20 fallos/15 min), mensaje genérico, hash ficticio con mismo costo |
| Escalada de privilegios / IDOR | Permisos en backend, denegación por defecto, alcance por campaña, 404 para registros ajenos, sesiones revocadas al cambiar rol |
| Inyección SQL | ORM con consultas parametrizadas |
| Inyección de comandos telefónicos | Comandos ESL construidos solo con valores validados por regex (UUID, gateway, E.164) |
| SSRF / exposición de FreeSWITCH | Host ESL solo loopback o red privada; la API escucha en 127.0.0.1 |
| Archivos maliciosos | Extensión + firma, 5 MB, 5,000 filas, validación por fila; exportaciones con prevención de fórmulas |
| Prompt injection / alucinaciones | Datos del cliente delimitados como no confiables; herramientas con validación determinista; guardrails de salida; cierre tras >3 bloqueos; supervisor QA con evidencia verificada |
| Fuga de PII | Enmascaramiento en transcripciones, bitácora y listados; datos mínimos al proveedor; grabaciones cifradas |
| Abuso de costos | Presupuesto diario y por interacción; límites de tokens, turnos y duración; pausa automática ante fallas masivas |
| Secretos | Solo en `.env` (fuera de Git); nunca en frontend, respuestas ni logs |

Riesgos pendientes: no hay HTTPS en localhost (no necesario sin exposición a red); el límite de frecuencia por IP es en memoria;
la API real, Deepgram y FreeSWITCH no se han validado; la detección de PII por regex no es exhaustiva. **El sistema no es «100 % seguro».**

**Cifrado real utilizado:** contraseñas con scrypt; tokens de sesión con SHA-256 (no reversible); grabaciones y respaldos con Fernet
(AES-128-CBC + HMAC-SHA256, librería `cryptography`). Los permisos de archivo **no** se consideran cifrado.

## 5. Retención y eliminación

Configurable en `.env`: transcripciones 180 días (texto sustituido), grabaciones 90 días (archivo y registro eliminados),
bitácora 365 días, sesiones expiradas 30 días. Ejecutar `python -m app.cli purgar` (pide confirmación escribiendo ELIMINAR).
Antes de usar datos reales faltan: base legal y aviso de privacidad, verificación de identidad aprobada, política de conservación
acordada con el cliente, control de acceso físico al equipo y prueba de restauración periódica.

## 6. Configuración de proveedores

| Variable | Valor por defecto | Verificar antes de la demo |
|---|---|---|
| `ANTHROPIC_MODELO` | `claude-haiku-5-5` | Disponibilidad en su consola de Anthropic y precio |
| `ANTHROPIC_MODELO_SUPERVISOR` | `claude-sonnet-5-5` | Ídem |
| `DEEPGRAM_STT_MODELO` | `nova-3` (`language=es`) | Soporte de español en su plan |
| `DEEPGRAM_TTS_MODELO` | `aura-2-diana-es` | Catálogo vigente de voces Aura-2 en español |

Endpoints: `POST https://api.anthropic.com/v1/messages` (cabecera `anthropic-version: 2023-06-01`),
`POST https://api.deepgram.com/v1/listen`, `POST https://api.deepgram.com/v1/speak`. Timeouts 30 s, 2 reintentos con espera para
408/409/429/5xx/529. Los costos mostrados son estimaciones con precios configurables; no se consulta el saldo del proveedor.
