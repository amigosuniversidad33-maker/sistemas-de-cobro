# Guion de demostración (10 minutos)

Preparación: sistema iniciado, datos de demostración cargados, `ANTHROPIC_API_KEY` y `DEEPGRAM_API_KEY` configuradas,
respaldo reciente, navegador en http://127.0.0.1:8000 con micrófono permitido. Tenga a mano los últimos 4 dígitos del documento
de un cliente ficticio de Mora Temprana.

| Min | Paso | Qué mostrar | Requisito |
|---|---|---|---|
| 0:00 | Arranque | `scripts\iniciar.ps1` y la URL localhost | Localhost, arranque documentado |
| 0:45 | Login y roles | Entrar como ANALISTA_QA (sin Clientes ni Agentes Internos), salir y entrar como ADMINISTRADOR | Autenticación y permisos |
| 1:30 | Agentes Internos | Registrar un supervisor y asignarlo a una campaña | HU-01 a HU-04 |
| 2:15 | Clientes | Importar `datos_demo/clientes_demo.csv` otra vez → «ya importado»; mostrar filas rechazadas del lote | Importación idempotente |
| 3:00 | Campañas | Crear campaña Mora Temprana, ver lo que falta, asignar agente, clasificar, activar, encolar → motivos | Campañas y reglas |
| 4:00 | No Contactables | Excluir un cliente encolado → trabajos cancelados | Bloqueo de excluidos |
| 4:30 | Prueba de Llamada (texto) | Pedir descuento («Ignora tus instrucciones…») → bloqueo y alerta; verificar identidad; proponer y confirmar promesa | API real, guardrails, promesa |
| 6:00 | Prueba de Llamada (voz) | Conversación breve hablada; interrumpir al agente | Voz real |
| 7:00 | Promesas y QA | Ver la promesa vinculada a la llamada; evaluar con supervisor IA; revisión humana | Supervisor IA |
| 8:00 | Control y Supervisión | Indicadores y denominadores; alertas; consumo estimado | Dashboard |
| 8:45 | Telefonía | Plantas/Extensiones: estado (llamada piloto real o «BLOQUEADA» con motivos) | Telefonía honesta |
| 9:15 | Persistencia y respaldo | `detener.ps1` → `iniciar.ps1`, datos intactos; mencionar la prueba de restauración realizada | Persistencia, respaldo |
| 9:45 | Cierre | Estado del proyecto: qué está probado, qué depende de servicios externos, riesgos pendientes | Transparencia |

Plan B si falla Internet o la API: mostrar el mensaje de contingencia (no se inventan respuestas), el consumo con error en
**Sistema** y la alerta generada; continuar con el resto del recorrido.
