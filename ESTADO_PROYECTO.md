# Estado del proyecto

**Fecha:** 17-oct-2026 · **Fase actual:** entrega del código completo (Fases 1–6 implementadas en código).
**Pendiente:** verificación en la computadora Windows del equipo, MySQL real, credenciales de API y troncal SIP.

> Generar código no equivale a una aplicación comprobada. Lo marcado «Implementada y probada» se probó en el entorno de
> desarrollo del asistente (Linux, Python 3.13, **SQLite**, proveedor LLM simulado). Nada se ha ejecutado todavía en su Windows.

## Clasificación de funcionalidades

| Funcionalidad | Estado | Evidencia / condición |
|---|---|---|
| Login, logout, sesiones con expiración y revocación, CSRF, bloqueo por fuerza bruta | Implementada y probada | `test_seguridad.py` (SQLite) |
| Usuarios internos, roles, permisos RBAC, asignaciones de supervisión, alcance por campaña | Implementada y probada | `test_seguridad.py` + recorrido en navegador |
| Auditoría de operaciones sensibles | Implementada y probada | Bitácora sin contraseñas (`test_bitacora_sin_contrasenas`) |
| Importación CSV/Excel con validación, reporte de errores e idempotencia | Implementada y probada | `test_importacion_validaciones_y_repetida`, `test_archivos_invalidos` |
| Campañas: estados/transiciones, clasificación 1–30 / 31–60, no activar incompletas | Implementada y probada | `test_cobranza.py` |
| Exclusiones, ventana horaria, intentos, tiempo mínimo, simultaneidad, presupuesto (al encolar y antes de originar) | Implementada y probada | `test_flujo_campana_exclusion_despues_de_encolar`, `test_exclusion_detectada_justo_antes_de_originar`, `test_ventana_horaria_en_limites` |
| Pausa de emergencia (manual y automática por regla determinista) | Implementada y probada | `test_pausa_de_emergencia`, `test_reglas_deterministas_activan_pausa_ante_fallas` |
| Agente conversacional con herramientas validadas, verificación de identidad y promesas confirmadas una sola vez | Implementada y probada **con proveedor simulado** | `test_ia.py`. **Sin validación con la API real de Anthropic** |
| Agente local de reglas (sin clave de API): guion, verificación, promesas validadas | Implementada y probada (simulada, sin IA externa) | `test_agente_local_*` + recorrido en navegador. Se usa automáticamente si falta `ANTHROPIC_API_KEY` y se identifica en pantalla |
| Voz del navegador (Web Speech API) cuando falta Deepgram | Implementada sin validación externa | Chrome/Edge; el reconocimiento de voz del navegador requiere Internet |
| Conversación con API real de Anthropic | Implementada sin validación externa | Requiere `ANTHROPIC_API_KEY` con saldo. Verificado en navegador el camino sin credencial (mensaje de contingencia) |
| Supervisor IA de calidad (estructurado, evidencia verificada, revisión humana) | Implementada y probada con proveedor simulado | `test_supervisor_qa_*`. Falta validación real |
| Supervisor IA de seguridad (métricas sanitizadas, recomendaciones) | Implementada sin validación externa | Reglas deterministas probadas; análisis IA requiere API |
| Guardrails, contingencia, cierre por infracciones, manipulación y descuentos | Implementada y probada | `test_manipulacion_y_descuentos_bloqueados`, `test_no_revela_deuda_sin_verificar` |
| Control de consumo y presupuesto (estimación, no facturación) | Implementada y probada | `test_presupuesto_agotado_bloquea` |
| Voz en navegador: Deepgram STT/TTS, fin de turno por silencio, interrupciones, liberación de recursos | Implementada sin validación externa | Requiere `DEEPGRAM_API_KEY` y micrófono; no probado en este entorno |
| Grabaciones cifradas (Fernet) y acceso auditado | Implementada sin validación externa | Requiere `GRABACIONES_CLAVE` |
| Telefonía: cliente ESL, originate validado, clasificación de causas, liberación de canales, recuperación tras reinicio | Implementada y probada **contra un ESL simulado** | `test_telefonia.py`. No es FreeSWITCH real |
| **Llamada telefónica piloto real** | **Bloqueada** | Falta FreeSWITCH instalado, troncal SIP, número autorizado y prueba real. El proyecto debe reportarse **incompleto en telefonía** hasta comprobarla |
| Streaming de audio en tiempo real (WebSocket, `mod_audio_stream`) | Pendiente | Se usa puente por archivos y turnos (DECISIONES C13) |
| Dashboard ejecutivo con denominadores definidos, sin doble conteo ni división por cero | Implementada y probada | `test_dashboard_consistente` + revisión visual |
| Respaldo y restauración cifrados | Implementada y probada en SQLite; MySQL sin validación externa | `test_respaldo_y_restauracion_cifrados`; con MySQL usa `mysqldump`/`mysql` |
| Persistencia tras reinicio | Probada en SQLite (archivo) | `test_persistencia_despues_de_reiniciar`; repetir en MySQL |
| Migraciones Alembic (upgrade/downgrade) | Probada en SQLite; DDL MySQL generado | `docs/esquema_mysql.sql`; aplicar en MySQL real |
| Scripts PowerShell | Sintaxis validada con PowerShell 7 | No ejecutados en Windows |
| Escalamiento a 65,000 llamadas/día | Pendiente (meta futura) | Solo cálculo de Ley de Little como estimación |
| Fine-tuning de modelos | No aplica | Entrenamiento = guiones versionados + casos + evaluaciones |

## Pruebas realizadas
53 pruebas automatizadas, **53 aprobadas** (Python 3.13, SQLite, LLM simulado, ESL simulado). Recorrido en Chromium de los
16 módulos sin errores de JavaScript. Detalle en `docs/PRUEBAS.md`.

## Errores abiertos
- Ninguno conocido en el recorrido probado. Pendiente confirmar en Windows + MySQL.

## Bloqueos
1. Credenciales de Anthropic con saldo (agente y supervisores reales).
2. Credenciales de Deepgram con saldo (voz).
3. FreeSWITCH + troncal SIP + número de prueba autorizado (llamada piloto).

## Próximo paso exacto
En su computadora: ejecutar `scripts\instalar.ps1`, crear la base con `scripts\mysql_crear_bd.sql`, configurar
`backend\.env`, ejecutar `scripts\inicializar_bd.ps1` y luego `scripts\iniciar.ps1`. Compartir la salida (sin secretos)
y los resultados de `scripts\pruebas.ps1`.
