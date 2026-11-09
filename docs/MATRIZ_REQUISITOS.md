# Matriz de requisitos y pruebas

Fuentes: **AV** = Avance.SistemadeCobro.grupo2 (página del PDF); **EF** = ENTREGA_FASE_FINAL (página del PDF); **PR** = prompt de implementación (sección).
Estados: **IP** implementada y probada · **IS** implementada sin validación externa · **SIM** probada con doble/simulador · **BLQ** bloqueada · **PEN** pendiente.
Pruebas: nombre de prueba automatizada (`tests/`) o **M-n** = prueba manual de `docs/PRUEBAS.md`.

| ID | Requisito | Fuente | Módulo | Prioridad | Fase | Criterio de aceptación | Prueba | Estado |
|---|---|---|---|---|---|---|---|---|
| R01 | Registrar usuarios internos (HU-01) | AV p.18; EF p.30 (CU-01) | Agentes Internos | Alta | 1 | Valida obligatorios, guarda con hash, muestra el usuario | `test_crear_modificar_y_asignar_rol` | IP |
| R02 | Consultar usuarios con filtros (HU-02) | AV p.18; EF CU-02 | Agentes Internos | Alta | 1 | Listado paginado con rol y estado | `test_entradas_maliciosas` + M-2 | IP |
| R03 | Modificar usuarios (HU-03) | AV p.18 | Agentes Internos | Alta | 1 | Cambios persistidos y auditados | `test_crear_modificar_y_asignar_rol` | IP |
| R04 | Asignar roles y permisos RBAC (HU-04, CU-03) | AV p.19; EF p.32 | Agentes Internos | Alta | 1 | Denegación por defecto; sesiones revocadas al cambiar rol | `test_permisos_por_rol` | IP |
| R05 | Login con hash y bloqueo por intentos (DS-01, DF-01) | EF p.6, p.64 | Seguridad | Alta | 1 | Mensaje genérico, bloqueo tras 5 fallos, cookie HttpOnly | `test_mensaje_generico_sin_enumeracion`, `test_bloqueo_por_fuerza_bruta`, `test_cookie_de_sesion_httponly_y_samesite` | IP |
| R06 | Sesiones con expiración y revocación; cierre efectivo | PR §10 | Seguridad | Alta | 1 | 401 tras inactividad, revocación o logout | `test_sesion_expirada_por_inactividad`, `test_sesion_revocada`, `test_login_y_logout` | IP |
| R07 | Sin registro público; primer admin por procedimiento seguro | PR §10 | Seguridad | Alta | 1 | API exige sesión; admin por CLI con contraseña oculta | `test_sin_registro_publico` + M-1 | IP |
| R08 | Bitácora de auditoría | EF p.3 (DER-02) | Seguridad | Alta | 1 | Operaciones sensibles registradas sin secretos | `test_bitacora_sin_contrasenas` | IP |
| R09 | Asignación de supervisión por campaña | EF p.3; AV p.5 (2.3) | Agentes Internos | Media | 1 | Supervisor solo ve sus campañas; ajenas → 404 | `test_alcance_por_campana` | IP |
| R10 | Carga masiva CSV/Excel con reporte de rechazados (HU-07, CU-07, DS-02, DF-02) | AV p.16; EF p.7, p.36 | Clientes | Alta | 2 | Filas válidas guardadas, inválidas reportadas, archivo repetido no duplica | `test_importacion_validaciones_y_repetida` | IP |
| R11 | Validar/sanitizar teléfono, documento, monto, mora (CU-08) | EF p.37 | Clientes | Alta | 2 | E.164, DECIMAL, rechazo de fórmulas y archivos inválidos | `test_normalizacion_y_celdas_seguras`, `test_archivos_invalidos` | IP |
| R12 | Crear y parametrizar campaña (HU-05, CU-04, DS-03) | AV p.16; EF p.8, p.33 | Campañas | Alta | 2 | Nombre, vigencia, mensaje, prioridad, horario, agente | M-3 | IP |
| R13 | Clasificar por tramo 1–30 / 31–60; fuera de rango con regla explícita (CU-05, DF-03) | AV p.6; EF p.34, p.66 | Campañas | Alta | 2 | Solo deudas del tramo; >60 = gestión especial sin asignación automática | `test_clasificacion_respeta_tramos` | IP |
| R14 | Estados activa/pausada/finalizada; no activar incompletas (CU-06) | AV p.6; EF p.35 | Campañas | Alta | 2 | Transiciones válidas; activación exige agente, guion, clientes, fechas | `test_transiciones_de_estado_invalidas`, `_campana_activa` | IP |
| R15 | Lista de no contactables y filtro previo (CU-18, CU-19, DS-09, DF-04) | AV p.6; EF p.14, p.47 | No Contactables | Alta | 2 | Exclusión cancela trabajos encolados; re-verificación antes de originar | `test_flujo_campana_exclusion_despues_de_encolar`, `test_exclusion_detectada_justo_antes_de_originar` | IP |
| R16 | Ventana horaria 08:00–20:00 configurable (CU-31, R-05) | AV p.9; EF p.60, p.79 | Control | Alta | 2 | Límites probados 07:59/08:00/19:59/20:00 | `test_ventana_horaria_en_limites` | IP |
| R17 | Intentos, tiempo mínimo, simultaneidad, presupuesto antes de marcar | PR §7 | Campañas | Alta | 2 | Motivos de bloqueo reportados al encolar | `test_flujo_campana_exclusion_despues_de_encolar` | IP |
| R18 | Campaña pausada antes de marcar cancela trabajos | PR §13 | Campañas | Alta | 5 | Trabajo CANCELADO y re-verificación rechaza | `test_campana_pausada_antes_de_marcar` | IP |
| R19 | Configurar agente IA: guion, tono, personalidad, voz (HU-09, CU-12) | AV p.5; EF p.41 | Agentes IA | Media | 3 | CRUD con voces Aura-2 es | M-4 | IP |
| R20 | Severidad automática por tramo (CU-13) | AV p.5; EF p.42 | Agentes IA | Media | 3 | Severidad forzada por tramo; solo cambia tono/prioridad | M-4 | IP |
| R21 | Guiones versionados y casos de prueba (CU-14) | AV p.6; EF p.43 | Entrenamiento | Media | 3 | Versiones, publicación, archivo; la llamada guarda la versión | M-5 | IP |
| R22 | Pruebas de comprensión y calibración STT/TTS (CU-15, CU-21) | EF p.44, p.50 | Entrenamiento / Prueba | Media | 4 | Evaluación de casos contra API real; latencia TTS medida | M-6, M-8 | IS |
| R23 | Conversación por texto con API real | PR §4.9 | Prueba de Llamada | Alta | 3 | Respuesta del modelo real, herramientas y registro | `test_flujo_completo_con_promesa_confirmada` (SIM) + M-6 | IS |
| R24 | Promesa: IA propone, backend valida, cliente confirma, se registra una vez (CU-16, DS-06, DF-08) | AV p.6; EF p.11, p.45, p.71 | Promesas | Alta | 3 | Sin confirmación/fecha inválida/monto excesivo no registra; doble confirmación = 1 registro | `test_promesa_sin_confirmacion_fecha_invalida_y_monto_excesivo`, `test_confirmacion_en_el_mismo_turno_no_se_acepta` | IP (SIM) |
| R25 | Seguimiento, cumplimiento manual auditado y reingreso por incumplimiento (CU-17) | AV p.6; EF p.46 | Promesas | Alta | 2 | Vencidas → INCUMPLIDA + reingreso con reglas | `test_flujo_completo_con_promesa_confirmada` + M-7 | IP |
| R26 | No revelar deuda antes de verificar identidad | PR §10 | Seguridad IA | Alta | 3 | Herramienta niega y guardrail bloquea | `test_no_revela_deuda_sin_verificar` | IP |
| R27 | Guardrails, contingencia y cierre tras 3 bloqueos (CU-28, DS-10, DF-11, R-03) | EF p.15, p.57, p.74, p.80 | Seguridad IA | Alta | 3 | Respuesta bloqueada reemplazada; 4.º bloqueo cierra | `test_manipulacion_y_descuentos_bloqueados` | IP |
| R28 | Enmascarar PII y cifrar grabaciones (CU-29, R-07) | EF p.58, p.80 | Seguridad IA | Alta | 4 | Transcripciones enmascaradas; audio Fernet | `test_bitacora_sin_contrasenas` + M-9 | IS |
| R29 | Fallos y cuota del proveedor: timeouts, reintentos, contingencia, sin acciones financieras | PR §8; EF R-04 | Agentes IA | Alta | 3 | 429/5xx → contingencia, llamada FALLIDA, alerta, sin promesa | `test_fallo_del_proveedor_usa_contingencia` | IP |
| R30 | Presupuesto por interacción y diario | PR §8 | Sistema | Alta | 3 | Al agotarse no se llama al proveedor | `test_presupuesto_agotado_bloquea` | IP |
| R31 | Speech-to-Text / Text-to-Speech Deepgram (HU-10, DS-05, DF-07) | AV p.17, p.22; EF p.10, p.70 | Prueba de Llamada | Media | 4 | Conversación de voz completa persistida | M-8 | IS |
| R32 | Registrar y consultar llamadas con filtros (HU-08, CU-09, CU-10) | AV p.5; EF p.38–39 | Llamadas | Media | 3 | Filtros por campaña, fecha, módulo; estado técnico separado | M-10 | IP |
| R33 | Grabaciones y transcripciones con acceso controlado (CU-11) | EF p.40 | Llamadas | Media | 4 | Permiso `grabaciones.ver`, auditoría al escuchar | M-9 | IS |
| R34 | Supervisor QA: adherencia, puntaje, evidencia, revisión humana (CU-22, CU-23, DS-08, DF-09) | AV p.7; EF p.13, p.51–52, p.72 | QA / Análisis | Media | 3 | Resultado estructurado, evidencia verificada, sin evaluaciones inventadas | `test_supervisor_qa_estructurado_y_evidencia`, `test_supervisor_qa_sin_proveedor_no_inventa` | IP (SIM) |
| R35 | Supervisor IA de seguridad y reglas deterministas | PR §8; EF p.29 (DARQ-04) | Seguridad IA | Media | 6 | Alertas por fuerza bruta, presupuesto, fallas, saturación | `test_reglas_deterministas_activan_pausa_ante_fallas` | IP / IS |
| R36 | Plantas FreeSWITCH: registro, capacidad, verificación (CU-24, CU-25) | AV p.7; EF p.53–54 | Plantas FreeSWITCH | Baja | 5 | Solo IP privada/localhost; verificación ESL | `test_host_publico_rechazado`, `test_autenticacion_esl` | SIM |
| R37 | Extensiones SIP, troncales, canales concurrentes (CU-26, CU-27, DC-02) | AV p.7; EF p.17, p.55–56 | Extensiones SIP | Baja | 5 | Canal reservado y liberado; capacidad respetada | `test_originate_sin_respuesta_libera_canal`, `test_recuperacion_de_trabajos_y_liberacion_de_canales` | SIM |
| R38 | Integración FreeSWITCH/SIP y llamada piloto a número autorizado (HU-11, DS-04, DF-05) | AV p.17; EF p.9, p.68 | Llamadas | Baja (objetivo) | 5 | Llamada real comprobada | `test_numero_no_autorizado_no_se_marca` + M-11 | **BLQ** |
| R39 | Eventos idempotentes y fuera de orden | PR §13 | Llamadas | Alta | 5 | Evento repetido ignorado | `test_eventos_duplicados_y_fuera_de_orden` | IP |
| R40 | Cola durable y recuperación tras reinicio | PR §5 | Sistema | Alta | 5 | Trabajos/canales recuperados sin doble marcación | `test_recuperacion_de_trabajos_y_liberacion_de_canales` | IP |
| R41 | Clasificación de resultados (DF-06); fallos técnicos ≠ sin contestar | EF p.69; PR §11 | Llamadas | Alta | 5 | GATEWAY_DOWN = fallo técnico | `test_fallo_tecnico_no_cuenta_como_sin_contestar` | IP |
| R42 | Dashboard ejecutivo: LS, LC, LR, LNC, tasas, por módulo, promesas, ventana, meta (HU-12, CU-30, DF-12) | AV p.8, p.12; EF p.59, p.75 | Control y Supervisión | Baja | 6 | Datos persistidos, denominadores definidos, sin división por cero | `test_dashboard_consistente` | IP |
| R43 | Alertas por saturación de canales o fallas (CU-32) | EF p.61 | Control y Supervisión | Media | 6 | Alerta registrada y visible | `test_reglas_deterministas_activan_pausa_ante_fallas` | IP |
| R44 | Exportar reportes CSV (CU-33) | EF p.62 | Llamadas / Clientes | Baja | 6 | CSV con prevención de fórmulas y auditoría | `test_normalizacion_y_celdas_seguras` + M-10 | IP (PDF no implementado) |
| R45 | Dimensionamiento Ley de Little (sección 6) | AV p.9–12; EF p.80 | Plantas FreeSWITCH | Baja | 6 | Reproduce 90.28/min, 87.2 y 164.8 canales como estimación | M-12 | IP |
| R46 | Matriz de riesgos R-01 a R-08 con controles | EF p.79 | Seguridad IA | Media | 6 | Visible con NR y control del piloto | M-12 | IP |
| R47 | Pausa de emergencia | PR §10 | Control | Alta | 5 | Bloquea nuevas marcaciones/conversaciones | `test_pausa_de_emergencia` | IP |
| R48 | Persistencia tras reiniciar | PR §3 | Sistema | Alta | 1 | Datos visibles después de reiniciar | `test_persistencia_despues_de_reiniciar` + M-13 | IP (SQLite) |
| R49 | Respaldo y restauración comprobados | PR §3, §16 | Sistema | Alta | 6 | Restauración devuelve el estado previo; clave incorrecta falla | `test_respaldo_y_restauracion_cifrados` + M-14 | IP (SQLite) / IS (MySQL) |
| R50 | Sin secretos en frontend y logs; CSRF, CSP, origen | PR §10 | Seguridad | Alta | 1 | Escaneo y cabeceras verificadas | `test_sin_secretos_en_frontend`, `test_csrf_obligatorio`, `test_origen_externo_rechazado`, `test_cabeceras_de_seguridad` | IP |
| R51 | 65,000 llamadas/día | AV p.4, p.9 | Arquitectura | Futura | — | Requiere pruebas de capacidad | — | PEN |
