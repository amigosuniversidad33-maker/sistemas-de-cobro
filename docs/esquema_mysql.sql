CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE tb_intento_login (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    ip VARCHAR(45) NOT NULL, 
    usuario_hash VARCHAR(64) NOT NULL, 
    exito BOOL NOT NULL, 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_intento_ip_fecha ON tb_intento_login (ip, fecha);

CREATE TABLE tb_permiso (
    id_permiso INTEGER NOT NULL AUTO_INCREMENT, 
    codigo VARCHAR(80) NOT NULL, 
    modulo VARCHAR(60) NOT NULL, 
    accion VARCHAR(60) NOT NULL, 
    descripcion VARCHAR(255), 
    PRIMARY KEY (id_permiso), 
    UNIQUE (codigo)
);

CREATE TABLE tb_planta_freeswitch (
    id_planta INTEGER NOT NULL AUTO_INCREMENT, 
    nombre VARCHAR(80) NOT NULL, 
    ip VARCHAR(45) NOT NULL, 
    puerto_esl INTEGER NOT NULL, 
    capacidad_canales INTEGER NOT NULL, 
    estado VARCHAR(20) NOT NULL, 
    activa BOOL NOT NULL, 
    ultima_verificacion DATETIME, 
    PRIMARY KEY (id_planta), 
    UNIQUE (nombre)
);

CREATE TABLE tb_politica_ia (
    id_politica INTEGER NOT NULL AUTO_INCREMENT, 
    nombre VARCHAR(100) NOT NULL, 
    version INTEGER NOT NULL, 
    activa BOOL NOT NULL, 
    plazo_max_dias INTEGER NOT NULL, 
    monto_min_pct NUMERIC(5, 2) NOT NULL, 
    max_bloqueos INTEGER NOT NULL, 
    max_intentos_identidad INTEGER NOT NULL, 
    mensaje_contingencia VARCHAR(500) NOT NULL, 
    temas_prohibidos TEXT, 
    fecha_creacion DATETIME NOT NULL, 
    PRIMARY KEY (id_politica), 
    CONSTRAINT uq_politica_version UNIQUE (nombre, version)
);

CREATE TABLE tb_riesgo (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    codigo VARCHAR(10) NOT NULL, 
    nombre VARCHAR(120) NOT NULL, 
    categoria VARCHAR(120) NOT NULL, 
    probabilidad INTEGER NOT NULL, 
    impacto INTEGER NOT NULL, 
    disparador VARCHAR(255) NOT NULL, 
    componente VARCHAR(120) NOT NULL, 
    estrategia VARCHAR(500) NOT NULL, 
    control_implementado VARCHAR(500) NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (codigo)
);

CREATE TABLE tb_rol (
    id_rol INTEGER NOT NULL AUTO_INCREMENT, 
    nombre VARCHAR(50) NOT NULL, 
    descripcion VARCHAR(255), 
    PRIMARY KEY (id_rol), 
    UNIQUE (nombre)
);

CREATE TABLE tb_trabajo (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    tipo VARCHAR(30) NOT NULL, 
    estado VARCHAR(15) NOT NULL, 
    payload JSON NOT NULL, 
    clave_idempotencia VARCHAR(120) NOT NULL, 
    intentos INTEGER NOT NULL, 
    max_intentos INTEGER NOT NULL, 
    disponible_en DATETIME NOT NULL, 
    bloqueado_por VARCHAR(80), 
    bloqueado_hasta DATETIME, 
    resultado VARCHAR(500), 
    creado DATETIME NOT NULL, 
    actualizado DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (clave_idempotencia)
);

CREATE INDEX ix_trabajo_estado ON tb_trabajo (estado, disponible_en);

CREATE TABLE tb_tramo_mora (
    id_tramo INTEGER NOT NULL AUTO_INCREMENT, 
    codigo VARCHAR(30) NOT NULL, 
    nombre VARCHAR(80) NOT NULL, 
    dias_min INTEGER NOT NULL, 
    dias_max INTEGER NOT NULL, 
    prioridad INTEGER NOT NULL, 
    tono_permitido VARCHAR(255) NOT NULL, 
    severidad INTEGER NOT NULL, 
    PRIMARY KEY (id_tramo), 
    CONSTRAINT ck_tramo_rango CHECK (dias_min <= dias_max), 
    UNIQUE (codigo)
);

CREATE TABLE tb_regla_guardrail (
    id_regla INTEGER NOT NULL AUTO_INCREMENT, 
    id_politica INTEGER NOT NULL, 
    tipo VARCHAR(20) NOT NULL, 
    patron VARCHAR(300) NOT NULL, 
    accion VARCHAR(15) NOT NULL, 
    descripcion VARCHAR(255), 
    activa BOOL NOT NULL, 
    PRIMARY KEY (id_regla), 
    FOREIGN KEY(id_politica) REFERENCES tb_politica_ia (id_politica) ON DELETE CASCADE
);

CREATE TABLE tb_rol_permiso (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    id_rol INTEGER NOT NULL, 
    id_permiso INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_permiso) REFERENCES tb_permiso (id_permiso) ON DELETE CASCADE, 
    FOREIGN KEY(id_rol) REFERENCES tb_rol (id_rol) ON DELETE CASCADE, 
    CONSTRAINT uq_rol_permiso UNIQUE (id_rol, id_permiso)
);

CREATE TABLE tb_troncal_sip (
    id_troncal INTEGER NOT NULL AUTO_INCREMENT, 
    id_planta INTEGER NOT NULL, 
    nombre VARCHAR(80) NOT NULL, 
    gateway VARCHAR(60) NOT NULL, 
    proveedor VARCHAR(80), 
    max_canales INTEGER NOT NULL, 
    activa BOOL NOT NULL, 
    PRIMARY KEY (id_troncal), 
    FOREIGN KEY(id_planta) REFERENCES tb_planta_freeswitch (id_planta) ON DELETE CASCADE, 
    UNIQUE (nombre)
);

CREATE TABLE tb_usuario (
    id_usuario INTEGER NOT NULL AUTO_INCREMENT, 
    nombre VARCHAR(80) NOT NULL, 
    apellido VARCHAR(80) NOT NULL, 
    correo VARCHAR(160) NOT NULL, 
    usuario VARCHAR(50) NOT NULL, 
    hash_password VARCHAR(255) NOT NULL, 
    id_rol INTEGER NOT NULL, 
    estado VARCHAR(15) NOT NULL, 
    intentos_fallidos INTEGER NOT NULL, 
    bloqueado_hasta DATETIME, 
    ultimo_acceso DATETIME, 
    fecha_creacion DATETIME NOT NULL, 
    fecha_actualizacion DATETIME NOT NULL, 
    PRIMARY KEY (id_usuario), 
    FOREIGN KEY(id_rol) REFERENCES tb_rol (id_rol), 
    UNIQUE (correo), 
    UNIQUE (usuario)
);

CREATE TABLE tb_alerta (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    tipo VARCHAR(50) NOT NULL, 
    severidad VARCHAR(10) NOT NULL, 
    origen VARCHAR(20) NOT NULL, 
    mensaje VARCHAR(500) NOT NULL, 
    recomendacion VARCHAR(500), 
    detalle JSON, 
    clave VARCHAR(120), 
    estado VARCHAR(12) NOT NULL, 
    id_usuario_cierre INTEGER, 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_usuario_cierre) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL, 
    UNIQUE (clave)
);

CREATE INDEX ix_alerta_estado ON tb_alerta (estado, fecha);

CREATE TABLE tb_bitacora (
    id_log BIGINT NOT NULL AUTO_INCREMENT, 
    id_usuario INTEGER, 
    accion VARCHAR(80) NOT NULL, 
    entidad VARCHAR(60) NOT NULL, 
    id_entidad VARCHAR(40), 
    detalle JSON, 
    ip VARCHAR(45), 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id_log), 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL
);

CREATE INDEX ix_bitacora_entidad ON tb_bitacora (entidad, id_entidad);

CREATE INDEX ix_bitacora_fecha ON tb_bitacora (fecha);

CREATE TABLE tb_campana (
    id_campana INTEGER NOT NULL AUTO_INCREMENT, 
    nombre VARCHAR(120) NOT NULL, 
    id_tramo INTEGER NOT NULL, 
    estado VARCHAR(15) NOT NULL, 
    fecha_inicio DATE, 
    fecha_fin DATE, 
    mensaje_base TEXT, 
    prioridad INTEGER NOT NULL, 
    hora_inicio VARCHAR(5) NOT NULL, 
    hora_fin VARCHAR(5) NOT NULL, 
    max_intentos_dia INTEGER NOT NULL, 
    max_intentos_total INTEGER NOT NULL, 
    minutos_entre_intentos INTEGER NOT NULL, 
    max_concurrencia INTEGER NOT NULL, 
    id_usuario INTEGER, 
    fecha_creacion DATETIME NOT NULL, 
    PRIMARY KEY (id_campana), 
    FOREIGN KEY(id_tramo) REFERENCES tb_tramo_mora (id_tramo), 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL, 
    UNIQUE (nombre)
);

CREATE INDEX ix_campana_estado ON tb_campana (estado);

CREATE TABLE tb_configuracion (
    clave VARCHAR(60) NOT NULL, 
    valor VARCHAR(500) NOT NULL, 
    descripcion VARCHAR(255), 
    id_usuario INTEGER, 
    actualizado DATETIME NOT NULL, 
    PRIMARY KEY (clave), 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL
);

CREATE TABLE tb_extension_sip (
    id_extension INTEGER NOT NULL AUTO_INCREMENT, 
    id_planta INTEGER NOT NULL, 
    id_troncal INTEGER, 
    numero VARCHAR(20) NOT NULL, 
    canales_max INTEGER NOT NULL, 
    activa BOOL NOT NULL, 
    PRIMARY KEY (id_extension), 
    FOREIGN KEY(id_planta) REFERENCES tb_planta_freeswitch (id_planta) ON DELETE CASCADE, 
    FOREIGN KEY(id_troncal) REFERENCES tb_troncal_sip (id_troncal) ON DELETE SET NULL, 
    CONSTRAINT uq_extension_planta UNIQUE (id_planta, numero)
);

CREATE TABLE tb_guion (
    id_guion INTEGER NOT NULL AUTO_INCREMENT, 
    nombre VARCHAR(100) NOT NULL, 
    version INTEGER NOT NULL, 
    contenido TEXT NOT NULL, 
    tramo VARCHAR(30) NOT NULL, 
    frases_obligatorias JSON, 
    estado VARCHAR(15) NOT NULL, 
    id_usuario INTEGER, 
    fecha_creacion DATETIME NOT NULL, 
    PRIMARY KEY (id_guion), 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL, 
    CONSTRAINT uq_guion_version UNIQUE (nombre, version)
);

CREATE TABLE tb_lote_importacion (
    id_lote INTEGER NOT NULL AUTO_INCREMENT, 
    archivo VARCHAR(255) NOT NULL, 
    archivo_hash VARCHAR(64) NOT NULL, 
    registros_validos INTEGER NOT NULL, 
    registros_actualizados INTEGER NOT NULL, 
    registros_rechazados INTEGER NOT NULL, 
    errores JSON, 
    id_usuario INTEGER, 
    fecha_carga DATETIME NOT NULL, 
    PRIMARY KEY (id_lote), 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL, 
    UNIQUE (archivo_hash)
);

CREATE TABLE tb_numero_autorizado (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    telefono VARCHAR(16) NOT NULL, 
    descripcion VARCHAR(160) NOT NULL, 
    id_usuario INTEGER, 
    fecha_registro DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL, 
    UNIQUE (telefono)
);

CREATE TABLE tb_sesion (
    id_sesion INTEGER NOT NULL AUTO_INCREMENT, 
    id_usuario INTEGER NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    csrf_hash VARCHAR(64) NOT NULL, 
    creada DATETIME NOT NULL, 
    expira DATETIME NOT NULL, 
    ultimo_uso DATETIME NOT NULL, 
    revocada_en DATETIME, 
    ip_origen VARCHAR(45), 
    user_agent VARCHAR(255), 
    PRIMARY KEY (id_sesion), 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE CASCADE, 
    UNIQUE (token_hash)
);

CREATE INDEX ix_sesion_usuario ON tb_sesion (id_usuario);

CREATE TABLE tb_agente_ia (
    id_agente INTEGER NOT NULL AUTO_INCREMENT, 
    nombre VARCHAR(80) NOT NULL, 
    voz_deepgram VARCHAR(60) NOT NULL, 
    tono VARCHAR(80) NOT NULL, 
    personalidad VARCHAR(255), 
    severidad INTEGER NOT NULL, 
    id_guion INTEGER, 
    id_politica INTEGER, 
    activo BOOL NOT NULL, 
    PRIMARY KEY (id_agente), 
    FOREIGN KEY(id_guion) REFERENCES tb_guion (id_guion) ON DELETE SET NULL, 
    FOREIGN KEY(id_politica) REFERENCES tb_politica_ia (id_politica) ON DELETE SET NULL, 
    UNIQUE (nombre)
);

CREATE TABLE tb_asignacion_supervision (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    id_usuario INTEGER NOT NULL, 
    id_campana INTEGER NOT NULL, 
    alcance VARCHAR(15) NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_campana) REFERENCES tb_campana (id_campana) ON DELETE CASCADE, 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE CASCADE, 
    CONSTRAINT uq_supervision UNIQUE (id_usuario, id_campana)
);

CREATE TABLE tb_canal_concurrente (
    id_canal INTEGER NOT NULL AUTO_INCREMENT, 
    id_extension INTEGER NOT NULL, 
    estado VARCHAR(15) NOT NULL, 
    id_llamada BIGINT, 
    ocupado_desde DATETIME, 
    PRIMARY KEY (id_canal), 
    FOREIGN KEY(id_extension) REFERENCES tb_extension_sip (id_extension) ON DELETE CASCADE
);

CREATE TABLE tb_caso_uso (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    id_guion INTEGER NOT NULL, 
    intencion VARCHAR(100) NOT NULL, 
    entrada_cliente TEXT NOT NULL, 
    respuesta_esperada TEXT NOT NULL, 
    debe_contener VARCHAR(255), 
    no_debe_contener VARCHAR(255), 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_guion) REFERENCES tb_guion (id_guion) ON DELETE CASCADE
);

CREATE TABLE tb_cliente (
    id_cliente INTEGER NOT NULL AUTO_INCREMENT, 
    id_lote INTEGER, 
    nombre VARCHAR(160) NOT NULL, 
    documento VARCHAR(30) NOT NULL, 
    telefono VARCHAR(16), 
    telefono_alterno VARCHAR(16), 
    telefono_valido BOOL NOT NULL, 
    contactable BOOL NOT NULL, 
    fecha_creacion DATETIME NOT NULL, 
    PRIMARY KEY (id_cliente), 
    FOREIGN KEY(id_lote) REFERENCES tb_lote_importacion (id_lote) ON DELETE SET NULL, 
    UNIQUE (documento)
);

CREATE INDEX ix_cliente_telefono ON tb_cliente (telefono);

CREATE TABLE tb_campana_agente (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    id_campana INTEGER NOT NULL, 
    id_agente INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_agente) REFERENCES tb_agente_ia (id_agente) ON DELETE CASCADE, 
    FOREIGN KEY(id_campana) REFERENCES tb_campana (id_campana) ON DELETE CASCADE, 
    CONSTRAINT uq_campana_agente UNIQUE (id_campana, id_agente)
);

CREATE TABLE tb_deuda (
    id_deuda INTEGER NOT NULL AUTO_INCREMENT, 
    id_cliente INTEGER NOT NULL, 
    referencia VARCHAR(40) NOT NULL, 
    saldo NUMERIC(14, 2) NOT NULL, 
    moneda VARCHAR(3) NOT NULL, 
    dias_mora INTEGER NOT NULL, 
    tramo VARCHAR(30), 
    estado VARCHAR(15) NOT NULL, 
    fecha_actualizacion DATETIME NOT NULL, 
    PRIMARY KEY (id_deuda), 
    CONSTRAINT ck_deuda_saldo CHECK (saldo >= 0), 
    FOREIGN KEY(id_cliente) REFERENCES tb_cliente (id_cliente) ON DELETE CASCADE, 
    CONSTRAINT uq_deuda_cliente_ref UNIQUE (id_cliente, referencia)
);

CREATE INDEX ix_deuda_mora ON tb_deuda (dias_mora);

CREATE TABLE tb_evaluacion_caso (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    id_caso INTEGER NOT NULL, 
    id_agente INTEGER NOT NULL, 
    aprobado BOOL NOT NULL, 
    respuesta_obtenida TEXT, 
    detalle VARCHAR(500), 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_agente) REFERENCES tb_agente_ia (id_agente) ON DELETE CASCADE, 
    FOREIGN KEY(id_caso) REFERENCES tb_caso_uso (id) ON DELETE CASCADE
);

CREATE TABLE tb_no_contactable (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    id_cliente INTEGER, 
    telefono VARCHAR(16), 
    motivo VARCHAR(30) NOT NULL, 
    detalle VARCHAR(255), 
    origen VARCHAR(15) NOT NULL, 
    activo BOOL NOT NULL, 
    id_usuario INTEGER, 
    fecha_registro DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_cliente) REFERENCES tb_cliente (id_cliente) ON DELETE CASCADE, 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL
);

CREATE INDEX ix_nc_telefono ON tb_no_contactable (telefono, activo);

CREATE TABLE tb_cliente_campana (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    id_cliente INTEGER NOT NULL, 
    id_campana INTEGER NOT NULL, 
    id_deuda INTEGER NOT NULL, 
    intentos INTEGER NOT NULL, 
    ultimo_intento DATETIME, 
    estado_gestion VARCHAR(15) NOT NULL, 
    prioridad INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_campana) REFERENCES tb_campana (id_campana) ON DELETE CASCADE, 
    FOREIGN KEY(id_cliente) REFERENCES tb_cliente (id_cliente) ON DELETE CASCADE, 
    FOREIGN KEY(id_deuda) REFERENCES tb_deuda (id_deuda) ON DELETE CASCADE, 
    CONSTRAINT uq_campana_deuda UNIQUE (id_campana, id_deuda)
);

CREATE INDEX ix_cc_estado ON tb_cliente_campana (id_campana, estado_gestion);

CREATE TABLE tb_llamada (
    id_llamada BIGINT NOT NULL AUTO_INCREMENT, 
    canal VARCHAR(20) NOT NULL, 
    modo VARCHAR(15) NOT NULL, 
    id_campana INTEGER, 
    id_cliente_campana INTEGER, 
    id_cliente INTEGER, 
    id_deuda INTEGER, 
    id_agente INTEGER, 
    id_guion INTEGER, 
    version_guion INTEGER, 
    id_politica INTEGER, 
    version_politica INTEGER, 
    id_extension INTEGER, 
    id_canal INTEGER, 
    uuid_freeswitch VARCHAR(64), 
    destino_enmascarado VARCHAR(20), 
    estado_tecnico VARCHAR(15) NOT NULL, 
    resultado_contacto VARCHAR(15), 
    resultado_cobranza VARCHAR(25), 
    identidad_verificada BOOL NOT NULL, 
    intentos_identidad INTEGER NOT NULL, 
    bloqueos_guardrail INTEGER NOT NULL, 
    turnos INTEGER NOT NULL, 
    promesa_propuesta JSON, 
    motivo_fallo VARCHAR(255), 
    duracion_seg INTEGER, 
    costo_estimado_usd NUMERIC(12, 6) NOT NULL, 
    inicio DATETIME NOT NULL, 
    fin DATETIME, 
    id_usuario INTEGER, 
    PRIMARY KEY (id_llamada), 
    FOREIGN KEY(id_agente) REFERENCES tb_agente_ia (id_agente) ON DELETE SET NULL, 
    FOREIGN KEY(id_campana) REFERENCES tb_campana (id_campana) ON DELETE SET NULL, 
    FOREIGN KEY(id_canal) REFERENCES tb_canal_concurrente (id_canal) ON DELETE SET NULL, 
    FOREIGN KEY(id_cliente) REFERENCES tb_cliente (id_cliente) ON DELETE SET NULL, 
    FOREIGN KEY(id_cliente_campana) REFERENCES tb_cliente_campana (id) ON DELETE SET NULL, 
    FOREIGN KEY(id_deuda) REFERENCES tb_deuda (id_deuda) ON DELETE SET NULL, 
    FOREIGN KEY(id_extension) REFERENCES tb_extension_sip (id_extension) ON DELETE SET NULL, 
    FOREIGN KEY(id_guion) REFERENCES tb_guion (id_guion) ON DELETE SET NULL, 
    FOREIGN KEY(id_politica) REFERENCES tb_politica_ia (id_politica) ON DELETE SET NULL, 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL, 
    UNIQUE (uuid_freeswitch)
);

CREATE INDEX ix_llamada_campana ON tb_llamada (id_campana, inicio);

CREATE INDEX ix_llamada_cliente ON tb_llamada (id_cliente);

CREATE INDEX ix_llamada_inicio ON tb_llamada (inicio);

CREATE TABLE tb_consumo_api (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    proveedor VARCHAR(30) NOT NULL, 
    servicio VARCHAR(30) NOT NULL, 
    modelo VARCHAR(80) NOT NULL, 
    version_prompt VARCHAR(20), 
    id_llamada BIGINT, 
    tokens_entrada INTEGER NOT NULL, 
    tokens_salida INTEGER NOT NULL, 
    segundos_audio NUMERIC(10, 2) NOT NULL, 
    caracteres INTEGER NOT NULL, 
    costo_estimado_usd NUMERIC(12, 6) NOT NULL, 
    exito BOOL NOT NULL, 
    codigo_error VARCHAR(60), 
    latencia_ms INTEGER, 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_llamada) REFERENCES tb_llamada (id_llamada) ON DELETE SET NULL
);

CREATE INDEX ix_consumo_fecha ON tb_consumo_api (fecha);

CREATE TABLE tb_evento_llamada (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    id_llamada BIGINT NOT NULL, 
    tipo VARCHAR(40) NOT NULL, 
    clave_evento VARCHAR(120) NOT NULL, 
    datos JSON, 
    fecha_evento DATETIME NOT NULL, 
    fecha_registro DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_llamada) REFERENCES tb_llamada (id_llamada) ON DELETE CASCADE, 
    UNIQUE (clave_evento)
);

CREATE TABLE tb_grabacion (
    id_grabacion BIGINT NOT NULL AUTO_INCREMENT, 
    id_llamada BIGINT NOT NULL, 
    ruta_audio VARCHAR(255) NOT NULL, 
    formato VARCHAR(40) NOT NULL, 
    cifrada BOOL NOT NULL, 
    duracion_seg INTEGER, 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id_grabacion), 
    FOREIGN KEY(id_llamada) REFERENCES tb_llamada (id_llamada) ON DELETE CASCADE
);

CREATE TABLE tb_promesa_pago (
    id_promesa INTEGER NOT NULL AUTO_INCREMENT, 
    id_cliente INTEGER NOT NULL, 
    id_deuda INTEGER NOT NULL, 
    id_campana INTEGER, 
    id_cliente_campana INTEGER, 
    id_llamada BIGINT NOT NULL, 
    monto NUMERIC(14, 2) NOT NULL, 
    moneda VARCHAR(3) NOT NULL, 
    fecha_compromiso DATE NOT NULL, 
    estado VARCHAR(15) NOT NULL, 
    clave_idempotencia VARCHAR(80) NOT NULL, 
    frase_confirmacion VARCHAR(255), 
    confirmada_en DATETIME NOT NULL, 
    id_usuario_cumplimiento INTEGER, 
    fecha_cumplimiento DATETIME, 
    observacion VARCHAR(255), 
    PRIMARY KEY (id_promesa), 
    CONSTRAINT ck_promesa_monto CHECK (monto > 0), 
    FOREIGN KEY(id_campana) REFERENCES tb_campana (id_campana) ON DELETE SET NULL, 
    FOREIGN KEY(id_cliente) REFERENCES tb_cliente (id_cliente), 
    FOREIGN KEY(id_cliente_campana) REFERENCES tb_cliente_campana (id) ON DELETE SET NULL, 
    FOREIGN KEY(id_deuda) REFERENCES tb_deuda (id_deuda), 
    FOREIGN KEY(id_llamada) REFERENCES tb_llamada (id_llamada), 
    FOREIGN KEY(id_usuario_cumplimiento) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL, 
    UNIQUE (clave_idempotencia)
);

CREATE INDEX ix_promesa_estado_fecha ON tb_promesa_pago (estado, fecha_compromiso);

CREATE TABLE tb_prueba_llamada (
    id_prueba INTEGER NOT NULL AUTO_INCREMENT, 
    id_agente INTEGER, 
    id_llamada BIGINT, 
    tipo VARCHAR(20) NOT NULL, 
    resultado VARCHAR(30) NOT NULL, 
    calidad_voz NUMERIC(5, 2), 
    latencia_ms INTEGER, 
    detalle VARCHAR(500), 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id_prueba), 
    FOREIGN KEY(id_agente) REFERENCES tb_agente_ia (id_agente) ON DELETE SET NULL, 
    FOREIGN KEY(id_llamada) REFERENCES tb_llamada (id_llamada) ON DELETE SET NULL
);

CREATE TABLE tb_turno_conversacion (
    id BIGINT NOT NULL AUTO_INCREMENT, 
    id_llamada BIGINT NOT NULL, 
    orden INTEGER NOT NULL, 
    rol VARCHAR(10) NOT NULL, 
    texto TEXT NOT NULL, 
    bloqueado BOOL NOT NULL, 
    confianza_stt NUMERIC(5, 4), 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_llamada) REFERENCES tb_llamada (id_llamada) ON DELETE CASCADE, 
    CONSTRAINT uq_turno_orden UNIQUE (id_llamada, orden)
);

CREATE TABLE tb_seguimiento_promesa (
    id INTEGER NOT NULL AUTO_INCREMENT, 
    id_promesa INTEGER NOT NULL, 
    resultado VARCHAR(30) NOT NULL, 
    reingreso_campana BOOL NOT NULL, 
    observacion VARCHAR(255), 
    id_usuario INTEGER, 
    fecha_revision DATETIME NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(id_promesa) REFERENCES tb_promesa_pago (id_promesa) ON DELETE CASCADE, 
    FOREIGN KEY(id_usuario) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL
);

CREATE TABLE tb_transcripcion (
    id_transcripcion BIGINT NOT NULL AUTO_INCREMENT, 
    id_llamada BIGINT NOT NULL, 
    id_grabacion BIGINT, 
    texto TEXT NOT NULL, 
    confianza NUMERIC(5, 4), 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id_transcripcion), 
    FOREIGN KEY(id_grabacion) REFERENCES tb_grabacion (id_grabacion) ON DELETE SET NULL, 
    FOREIGN KEY(id_llamada) REFERENCES tb_llamada (id_llamada) ON DELETE CASCADE, 
    UNIQUE (id_llamada)
);

CREATE TABLE tb_evaluacion_qa (
    id_qa INTEGER NOT NULL AUTO_INCREMENT, 
    id_llamada BIGINT NOT NULL, 
    id_transcripcion BIGINT, 
    puntaje NUMERIC(5, 2) NOT NULL, 
    cumple_guion BOOL NOT NULL, 
    trato_adecuado BOOL NOT NULL, 
    confirmacion_correcta BOOL, 
    compromisos_fuera_politica BOOL NOT NULL, 
    incertidumbre VARCHAR(10) NOT NULL, 
    hallazgos JSON, 
    resumen TEXT, 
    observacion VARCHAR(500), 
    proveedor VARCHAR(30) NOT NULL, 
    modelo VARCHAR(80) NOT NULL, 
    version_prompt VARCHAR(20) NOT NULL, 
    estado_revision VARCHAR(15) NOT NULL, 
    revisado_por INTEGER, 
    puntaje_humano NUMERIC(5, 2), 
    fecha DATETIME NOT NULL, 
    PRIMARY KEY (id_qa), 
    FOREIGN KEY(id_llamada) REFERENCES tb_llamada (id_llamada) ON DELETE CASCADE, 
    FOREIGN KEY(id_transcripcion) REFERENCES tb_transcripcion (id_transcripcion) ON DELETE SET NULL, 
    FOREIGN KEY(revisado_por) REFERENCES tb_usuario (id_usuario) ON DELETE SET NULL
);

INSERT INTO alembic_version (version_num) VALUES ('0001');

