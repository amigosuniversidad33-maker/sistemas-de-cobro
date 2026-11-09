# Registro de pruebas

## 1. Pruebas automatizadas ejecutadas

- **Fecha:** 17-oct-2026 · **Entorno:** Linux del asistente, Python 3.13, FastAPI 0.141.1, SQLAlchemy 2.0.53, **SQLite** (archivo temporal).
- **Tipo:** unitarias e integración de API (TestClient). El proveedor LLM es un **doble de prueba explícito** (`tests/conftest.py::LLMDoble`)
  y FreeSWITCH es un **servidor Event Socket simulado** (`tests/test_telefonia.py::ESLSimulado`). No se llamó a APIs reales.
- **Resultado:** 51 de 51 aprobadas. Comando: `python -m pytest -q` (en Windows: `scripts\pruebas.ps1`).

| Archivo | Pruebas | Qué cubre |
|---|---|---|
| `test_seguridad.py` | 19 | Login/logout, cookie HttpOnly/SameSite, enumeración, fuerza bruta, expiración, revocación, hash del token, CSRF, origen, permisos por rol, registro público, alcance por campaña (registros ajenos → 404), entradas maliciosas, contraseña débil, CRUD de usuarios, bitácora sin contraseñas, secretos en frontend, estado sin secretos, cabeceras |
| `test_cobranza.py` | 15 | Teléfonos y celdas seguras, ventana horaria en límites, importación e idempotencia, archivos inválidos, exclusión después de encolar, re-verificación antes de originar, campaña pausada, telefonía bloqueada, pausa de emergencia, eventos duplicados/fuera de orden, recuperación de trabajos y canales, persistencia tras reiniciar, transiciones, clasificación por tramos, respaldo/restauración cifrados |
| `test_ia.py` | 11 | Flujo completo con promesa confirmada una vez, no revelar deuda sin verificar, promesa sin confirmación / fecha inválida / monto excesivo / respuesta negativa, confirmación en el mismo turno, manipulación y descuentos, fallo del proveedor (429), presupuesto agotado, supervisor QA con evidencia verificada, supervisor sin proveedor no inventa, consistencia del dashboard, pausa automática por regla |
| `test_telefonia.py` | 6 | Comandos ESL validados (inyección), host público rechazado, autenticación ESL, NO_ANSWER libera canal, GATEWAY_DOWN = fallo técnico, número no autorizado |

Además: recorrido automatizado en Chromium de los 16 módulos con el administrador (sin errores de JavaScript), conversación de texto
sin credencial (muestra contingencia y registra el fallo), validación de formularios y vista móvil (390 px).
Scripts PowerShell: sintaxis validada con PowerShell 7.4 (no ejecutados en Windows).

**Límites:** estas pruebas no sustituyen la verificación en su computadora. No se probaron MySQL, Windows, Anthropic, Deepgram, micrófono ni FreeSWITCH reales.

## 2. Pruebas manuales en su computadora (registrar resultado y fecha)

| ID | Prueba | Pasos | Resultado esperado | Resultado |
|---|---|---|---|---|
| M-1 | Instalación y primer administrador | `instalar.ps1`, `mysql_crear_bd.sql`, `inicializar_bd.ps1` | Sin errores; usuario creado | |
| M-2 | Acceso por localhost y permisos | Ingresar como admin; crear un ANALISTA_QA; ingresar con él | El analista no ve Clientes ni Agentes Internos | |
| M-3 | Importación y campaña | Clientes → importar `datos_demo/clientes_demo.csv`; Campañas → crear, asignar agente, clasificar, activar | 30 válidos, 5 rechazados; campaña ACTIVA | |
| M-4 | Agente IA | Editar agente: voz, tono; asignar guion de otro tramo | Severidad se ajusta al tramo | |
| M-5 | Guiones versionados | Nueva versión → publicar → asignar | La llamada registra la versión usada | |
| M-6 | **Conversación con API real** | Configurar `ANTHROPIC_API_KEY`; Prueba de Llamada → texto; verificar con los 4 últimos dígitos del documento; proponer y confirmar promesa | Respuestas reales; promesa en Promesas de Pago; consumo registrado en Sistema | |
| M-7 | Promesa y cumplimiento | Marcar cumplida con observación; ver Auditoría | Estado CUMPLIDA y registro `PROMESA_CUMPLIDA_MANUAL` | |
| M-8 | **Voz real** | Configurar `DEEPGRAM_API_KEY`; canal Voz en navegador; permitir micrófono; hablar, callar, interrumpir | Transcripción, respuesta hablada, fin de turno por silencio, interrupción detiene el audio | |
| M-9 | Grabaciones cifradas | Configurar `GRABACIONES_CLAVE`; repetir M-8; abrir la llamada y escuchar | El archivo en `datos/grabaciones` no es audio legible; se reproduce desde la app y queda auditado | |
| M-10 | Llamadas, filtros y exportación | Llamadas → filtros → Exportar CSV | CSV sin fórmulas ejecutables | |
| M-11 | **Llamada piloto FreeSWITCH** | Seguir `docs/FREESWITCH.md`; autorizar su número; encolar | Teléfono suena, conversación por turnos, canal liberado, eventos registrados | |
| M-12 | Dimensionamiento y riesgos | Plantas → calcular; Seguridad IA → matriz | R ≈ 90.28/min; C ≈ 87.2 (promedio) | |
| M-13 | Persistencia | `detener.ps1`, reiniciar Windows, `iniciar.ps1` | Datos intactos | |
| M-14 | Respaldo y restauración MySQL | `respaldo.ps1`; crear un usuario; `detener.ps1`; `restaurar.ps1 <archivo>`; `iniciar.ps1` | El usuario creado después del respaldo ya no existe | |
| M-15 | Supervisor QA real | Llamadas → abrir conversación finalizada → Evaluar | Evaluación con hallazgos y evidencia | |
