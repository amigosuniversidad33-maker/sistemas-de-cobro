# CLAUDE.md — Contexto de continuidad

## Objetivo
Sistema Outbound de cobranza por campaña con agentes IA, ejecutable en **localhost** (Windows) para el proyecto académico
de la Universidad Regional de Guatemala. Recorrido: login → roles → usuarios → importar clientes/deudas → campaña →
clasificación por mora → exclusiones/horarios/límites → agente IA con guion y política → conversación real (API) →
voz real (Deepgram) → promesa confirmada → supervisor QA → dashboard/alertas/auditoría → llamada piloto FreeSWITCH/SIP.

## Arquitectura
- `backend/app/main.py` FastAPI (API + frontend estático en el mismo origen, `127.0.0.1:8000`).
- `backend/app/worker.py` proceso separado: cola durable `tb_trabajo` (MARCAR, QA_LLAMADA, REVISAR_PROMESAS, SUPERVISION_SEGURIDAD).
- `app/ia/` proveedor LLM (interfaz + Anthropic HTTP), agente con herramientas validadas, guardrails, supervisores.
- `app/voz/` Deepgram STT/TTS REST y grabaciones cifradas (Fernet).
- `app/telefonia/` cliente ESL mínimo y marcador piloto (puente de medios por archivos).
- `app/servicios/` importación, reglas pre-marcación, campañas, promesas, consumo.
- `app/routers/` endpoints por módulo. `frontend/` SPA vanilla JS (hash router), tema azul.
- MySQL 8 + SQLAlchemy 2 + Alembic (`alembic/versions/0001_esquema_inicial.py`).

## Convenciones
- Tablas `tb_nombre` en minúsculas (entidad lógica TB_Nombre). Importes `Numeric(14,2)` + `moneda`. Teléfonos E.164.
- Fechas UTC sin tzinfo en BD; reglas y UI en America/Guatemala.
- Español en código de dominio, mensajes y UI. Sin emojis. Íconos SVG de `frontend/js/iconos.js`.
- Todo texto dinámico en el frontend pasa por `esc()`. Sin estilos en línea (CSP).
- Cada operación sensible llama a `auditar(...)`. Permisos con `Depends(requiere("modulo.accion"))`.

## Comandos (desde `backend/`, con el venv activo)
- Migrar: `python -m alembic upgrade head` · Nueva migración: `python -m alembic revision --autogenerate -m "..."`
- Catálogos: `python -m app.cli semilla` · Admin: `python -m app.cli crear-admin` · Demo: `python -m app.cli demo`
- API: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` · Worker: `python -m app.worker`
- Pruebas: `python -m pytest -q` · Respaldo: `python -m app.respaldo crear`
- Windows: `scripts\instalar.ps1`, `inicializar_bd.ps1`, `iniciar.ps1`, `detener.ps1`, `respaldo.ps1`, `restaurar.ps1`.

## Reglas de seguridad (no negociables)
- Sin registro público; primer admin por CLI; sin contraseñas en código; scrypt; sesiones revocables.
- Secretos solo en `backend/.env` (nunca en frontend, logs, repo o chat).
- El LLM propone; el backend valida. No revelar deuda antes de verificar identidad. Sin descuentos/condonaciones/amenazas.
- Promesa solo tras confirmación explícita, registrada una vez. Una promesa no es un pago.
- Reglas pre-marcación al encolar **y** antes de originar. Solo números autorizados en el piloto.
- No declarar el sistema «100 % seguro» ni capacidad de 65,000 llamadas sin pruebas.

## Restricciones del proyecto
- Plazo 14 días; entrega en localhost; datos ficticios; telefonía bloqueada hasta tener troncal SIP y número autorizado.
- No borrar datos ni consumir presupuesto no acordado sin autorización.
