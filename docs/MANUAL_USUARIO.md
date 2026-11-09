# Manual de usuario

Dirección: **http://127.0.0.1:8000**. Cada usuario ve solo los módulos que su rol permite.

| Rol | Puede |
|---|---|
| ADMINISTRADOR | Todo |
| SUPERVISOR | Ver y operar sus campañas asignadas, exclusiones, promesas, QA, pruebas, pausa de emergencia |
| ANALISTA_QA | Llamadas, QA, Entrenamiento, Prueba de Llamada |
| AUDITOR | Consulta de solo lectura y bitácora |

Identificación de modos en toda la interfaz: **PRUEBA · TEXTO**, **VOZ DE PRUEBA** (navegador) y **TELEFONÍA REAL**.

## Supervisión
**Control y Supervisión** — Panel ejecutivo calculado desde la base: intentos (LS), contestadas (LC), rechazadas (LR), sin
contestar (LNC), fallos técnicos, llamadas en curso, promesas y montos, exclusiones, consumo de APIs, alertas, cumplimiento de la
ventana horaria y avance frente a la meta futura de 65,000. Filtre por fechas, modo y canal. Los denominadores de cada tasa se
explican en pantalla. Botón **Pausa de emergencia** (requiere motivo).

## Call Center
- **Llamadas** — Historial con filtros (campaña, módulo de mora, canal, estado técnico, contacto, fechas). El ícono de ojo abre la
  transcripción enmascarada, eventos, promesa, evaluación QA y grabaciones (si su rol lo permite). Exportar CSV.
- **Agentes IA** — Nombre, voz Aura-2 en español, tono, personalidad, guion y política. La severidad se fija según el tramo del guion.
- **Agentes Internos** — Registrar, consultar, modificar, activar/desactivar usuarios, restablecer contraseñas, permisos por rol y
  asignaciones de supervisión por campaña.
- **Entrenamiento** — Guiones versionados (borrador → publicado → archivado), casos de prueba y evaluación del agente contra la API.
- **Campañas** — Crear (queda en BORRADOR) → asignar agente del mismo tramo → **Clasificar clientes** → **Activar** (el sistema indica
  qué falta) → **Encolar marcación** (muestra cuántos se encolaron y por qué se bloquearon los demás) → Pausar / Finalizar.
- **Promesas de Pago** — Seguimiento; **Marcar cumplida** cuando se verificó el pago (queda auditado); las vencidas pasan a INCUMPLIDA
  y el cliente reingresa a la campaña respetando todas las reglas.
- **No Contactables** — Agregar por cliente o teléfono con motivo (número inválido, no contacto, proceso legal). Cancela de inmediato
  los trabajos pendientes. Retirar una exclusión exige confirmación.
- **Prueba de Llamada** — Elija agente y cliente ficticio. **Texto**: escriba como el cliente. **Voz**: permita el micrófono, hable;
  el turno termina tras ~1 s de silencio; puede interrumpir al agente hablando (manos libres). Para verificar identidad diga los
  últimos 4 dígitos del documento del cliente ficticio (visibles en Clientes y Deudas). Incluye prueba de calidad/latencia de voz.
- **QA / Análisis** — Evaluaciones del supervisor IA con hallazgos y evidencia verificada; registre su revisión humana.

## Infraestructura y Seguridad
- **Plantas FreeSWITCH** — Estado de la telefonía (bloqueos pendientes), plantas y verificación ESL, calculadora de Ley de Little.
- **Extensiones SIP** — Troncales, extensiones, canales (liberar/recuperar) y números autorizados para pruebas.
- **Seguridad IA** — Alertas (reconocer/cerrar), reglas deterministas, supervisor IA de seguridad, políticas versionadas y reglas
  guardrail, matriz de riesgos R-01 a R-08.

## Administración
- **Clientes y Deudas** — Importar CSV/Excel (plantilla descargable), ver errores por lote, consultar y exportar (datos enmascarados).
- **Auditoría** — Bitácora con filtros.
- **Sistema** — Estado de dependencias, parámetros operativos (ventana, presupuestos, canales del piloto), cola de trabajos y consumo.
