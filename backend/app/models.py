"""Modelo de datos unificado a partir de DER-01, DER-02, DER-03 y DER-04.

Convención: entidad lógica TB_Nombre -> tabla física en minúsculas `tb_nombre`.
Se usan minúsculas porque MySQL en Windows (lower_case_table_names=1) las convierte
y en Linux distingue mayúsculas; así el esquema es idéntico en ambos sistemas.

Reglas: fechas internas en UTC (DATETIME sin zona, siempre UTC); importes DECIMAL(14,2)
con moneda explícita ISO-4217; teléfonos en formato E.164 (+502XXXXXXXX).
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

BigId = BigInteger().with_variant(Integer, "sqlite")


def ahora_utc() -> datetime:
    """Fecha/hora actual en UTC sin tzinfo (formato de almacenamiento)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============================================================ SEGURIDAD (DER-02)
class Rol(Base):
    __tablename__ = "tb_rol"
    id_rol: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    descripcion: Mapped[str | None] = mapped_column(String(255))
    permisos: Mapped[list["RolPermiso"]] = relationship(back_populates="rol", cascade="all, delete-orphan")


class Permiso(Base):
    __tablename__ = "tb_permiso"
    id_permiso: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(80), unique=True)
    modulo: Mapped[str] = mapped_column(String(60))
    accion: Mapped[str] = mapped_column(String(60))
    descripcion: Mapped[str | None] = mapped_column(String(255))


class RolPermiso(Base):
    __tablename__ = "tb_rol_permiso"
    __table_args__ = (UniqueConstraint("id_rol", "id_permiso", name="uq_rol_permiso"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_rol: Mapped[int] = mapped_column(ForeignKey("tb_rol.id_rol", ondelete="CASCADE"))
    id_permiso: Mapped[int] = mapped_column(ForeignKey("tb_permiso.id_permiso", ondelete="CASCADE"))
    rol: Mapped[Rol] = relationship(back_populates="permisos")
    permiso: Mapped[Permiso] = relationship()


class Usuario(Base):
    __tablename__ = "tb_usuario"
    id_usuario: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80))
    apellido: Mapped[str] = mapped_column(String(80))
    correo: Mapped[str] = mapped_column(String(160), unique=True)
    usuario: Mapped[str] = mapped_column(String(50), unique=True)
    hash_password: Mapped[str] = mapped_column(String(255))  # omisión corregida del diseño preliminar
    id_rol: Mapped[int] = mapped_column(ForeignKey("tb_rol.id_rol"))
    estado: Mapped[str] = mapped_column(String(15), default="ACTIVO")  # ACTIVO | INACTIVO
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc)
    rol: Mapped[Rol] = relationship()


class Sesion(Base):
    """Sesiones con cookie opaca. Solo se guarda el HASH SHA-256 del token (no el token)."""

    __tablename__ = "tb_sesion"
    __table_args__ = (Index("ix_sesion_usuario", "id_usuario"),)
    id_sesion: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    creada: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    expira: Mapped[datetime] = mapped_column(DateTime)
    ultimo_uso: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    revocada_en: Mapped[datetime | None] = mapped_column(DateTime)
    ip_origen: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    usuario: Mapped[Usuario] = relationship()


class IntentoLogin(Base):
    """Registro durable para limitar fuerza bruta por IP (sin guardar el usuario en claro)."""

    __tablename__ = "tb_intento_login"
    __table_args__ = (Index("ix_intento_ip_fecha", "ip", "fecha"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    ip: Mapped[str] = mapped_column(String(45))
    usuario_hash: Mapped[str] = mapped_column(String(64))
    exito: Mapped[bool] = mapped_column(Boolean)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class Bitacora(Base):
    __tablename__ = "tb_bitacora"
    __table_args__ = (Index("ix_bitacora_fecha", "fecha"), Index("ix_bitacora_entidad", "entidad", "id_entidad"))
    id_log: Mapped[int] = mapped_column(BigId, primary_key=True)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    accion: Mapped[str] = mapped_column(String(80))
    entidad: Mapped[str] = mapped_column(String(60))
    id_entidad: Mapped[str | None] = mapped_column(String(40))
    detalle: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(45))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    usuario: Mapped[Usuario | None] = relationship()


# ============================================================ COBRANZA (DER-03)
class TramoMora(Base):
    """MODULO_MORA del DER-03."""

    __tablename__ = "tb_tramo_mora"
    __table_args__ = (CheckConstraint("dias_min <= dias_max", name="ck_tramo_rango"),)
    id_tramo: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nombre: Mapped[str] = mapped_column(String(80))
    dias_min: Mapped[int] = mapped_column(Integer)
    dias_max: Mapped[int] = mapped_column(Integer)
    prioridad: Mapped[int] = mapped_column(Integer, default=1)
    tono_permitido: Mapped[str] = mapped_column(String(255))
    severidad: Mapped[int] = mapped_column(Integer, default=1)


class LoteImportacion(Base):
    """CARGA_LOTE del DER-03. El hash del archivo impide importar dos veces el mismo archivo."""

    __tablename__ = "tb_lote_importacion"
    id_lote: Mapped[int] = mapped_column(Integer, primary_key=True)
    archivo: Mapped[str] = mapped_column(String(255))
    archivo_hash: Mapped[str] = mapped_column(String(64), unique=True)
    registros_validos: Mapped[int] = mapped_column(Integer, default=0)
    registros_actualizados: Mapped[int] = mapped_column(Integer, default=0)
    registros_rechazados: Mapped[int] = mapped_column(Integer, default=0)
    errores: Mapped[list | None] = mapped_column(JSON)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class Cliente(Base):
    __tablename__ = "tb_cliente"
    __table_args__ = (Index("ix_cliente_telefono", "telefono"),)
    id_cliente: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_lote: Mapped[int | None] = mapped_column(ForeignKey("tb_lote_importacion.id_lote", ondelete="SET NULL"))
    nombre: Mapped[str] = mapped_column(String(160))
    documento: Mapped[str] = mapped_column(String(30), unique=True)
    telefono: Mapped[str | None] = mapped_column(String(16))  # E.164
    telefono_alterno: Mapped[str | None] = mapped_column(String(16))
    telefono_valido: Mapped[bool] = mapped_column(Boolean, default=False)
    contactable: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    deudas: Mapped[list["Deuda"]] = relationship(back_populates="cliente")


class Deuda(Base):
    __tablename__ = "tb_deuda"
    __table_args__ = (
        UniqueConstraint("id_cliente", "referencia", name="uq_deuda_cliente_ref"),
        CheckConstraint("saldo >= 0", name="ck_deuda_saldo"),
        Index("ix_deuda_mora", "dias_mora"),
    )
    id_deuda: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_cliente: Mapped[int] = mapped_column(ForeignKey("tb_cliente.id_cliente", ondelete="CASCADE"))
    referencia: Mapped[str] = mapped_column(String(40))
    saldo: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    moneda: Mapped[str] = mapped_column(String(3), default="GTQ")
    dias_mora: Mapped[int] = mapped_column(Integer)
    tramo: Mapped[str | None] = mapped_column(String(30))  # código de tb_tramo_mora o GESTION_ESPECIAL
    estado: Mapped[str] = mapped_column(String(15), default="ACTIVA")  # ACTIVA | CERRADA
    fecha_actualizacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc)
    cliente: Mapped[Cliente] = relationship(back_populates="deudas")


class Campana(Base):
    __tablename__ = "tb_campana"
    __table_args__ = (Index("ix_campana_estado", "estado"),)
    id_campana: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    id_tramo: Mapped[int] = mapped_column(ForeignKey("tb_tramo_mora.id_tramo"))
    estado: Mapped[str] = mapped_column(String(15), default="BORRADOR")  # BORRADOR|ACTIVA|PAUSADA|FINALIZADA
    fecha_inicio: Mapped[date | None] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    mensaje_base: Mapped[str | None] = mapped_column(Text)
    prioridad: Mapped[int] = mapped_column(Integer, default=1)
    hora_inicio: Mapped[str] = mapped_column(String(5), default="08:00")  # hora local America/Guatemala
    hora_fin: Mapped[str] = mapped_column(String(5), default="20:00")
    max_intentos_dia: Mapped[int] = mapped_column(Integer, default=2)
    max_intentos_total: Mapped[int] = mapped_column(Integer, default=6)
    minutos_entre_intentos: Mapped[int] = mapped_column(Integer, default=120)
    max_concurrencia: Mapped[int] = mapped_column(Integer, default=1)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    tramo: Mapped[TramoMora] = relationship()
    agentes: Mapped[list["CampanaAgente"]] = relationship(back_populates="campana", cascade="all, delete-orphan")


class AsignacionSupervision(Base):
    __tablename__ = "tb_asignacion_supervision"
    __table_args__ = (UniqueConstraint("id_usuario", "id_campana", name="uq_supervision"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_usuario: Mapped[int] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="CASCADE"))
    id_campana: Mapped[int] = mapped_column(ForeignKey("tb_campana.id_campana", ondelete="CASCADE"))
    alcance: Mapped[str] = mapped_column(String(15), default="GESTION")  # LECTURA | GESTION


class ClienteCampana(Base):
    __tablename__ = "tb_cliente_campana"
    __table_args__ = (
        UniqueConstraint("id_campana", "id_deuda", name="uq_campana_deuda"),
        Index("ix_cc_estado", "id_campana", "estado_gestion"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_cliente: Mapped[int] = mapped_column(ForeignKey("tb_cliente.id_cliente", ondelete="CASCADE"))
    id_campana: Mapped[int] = mapped_column(ForeignKey("tb_campana.id_campana", ondelete="CASCADE"))
    id_deuda: Mapped[int] = mapped_column(ForeignKey("tb_deuda.id_deuda", ondelete="CASCADE"))
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_intento: Mapped[datetime | None] = mapped_column(DateTime)
    # PENDIENTE|EN_COLA|EN_LLAMADA|CONTACTADO|PROMESA|EXCLUIDO|AGOTADO|CERRADO
    estado_gestion: Mapped[str] = mapped_column(String(15), default="PENDIENTE")
    prioridad: Mapped[int] = mapped_column(Integer, default=1)
    cliente: Mapped[Cliente] = relationship()
    deuda: Mapped[Deuda] = relationship()
    campana: Mapped[Campana] = relationship()


class NoContactable(Base):
    __tablename__ = "tb_no_contactable"
    __table_args__ = (Index("ix_nc_telefono", "telefono", "activo"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_cliente: Mapped[int | None] = mapped_column(ForeignKey("tb_cliente.id_cliente", ondelete="CASCADE"))
    telefono: Mapped[str | None] = mapped_column(String(16))
    # NUMERO_INVALIDO | SOLICITUD_NO_CONTACTO | PROCESO_LEGAL | OTRO
    motivo: Mapped[str] = mapped_column(String(30))
    detalle: Mapped[str | None] = mapped_column(String(255))
    origen: Mapped[str] = mapped_column(String(15), default="MANUAL")  # MANUAL|AGENTE_IA|IMPORTACION
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    cliente: Mapped[Cliente | None] = relationship()


# ============================================================ IA (DER-01/02/04)
class PoliticaIA(Base):
    __tablename__ = "tb_politica_ia"
    __table_args__ = (UniqueConstraint("nombre", "version", name="uq_politica_version"),)
    id_politica: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    plazo_max_dias: Mapped[int] = mapped_column(Integer, default=15)
    monto_min_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("10.00"))
    max_bloqueos: Mapped[int] = mapped_column(Integer, default=3)
    max_intentos_identidad: Mapped[int] = mapped_column(Integer, default=3)
    mensaje_contingencia: Mapped[str] = mapped_column(String(500))
    temas_prohibidos: Mapped[str | None] = mapped_column(Text)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    reglas: Mapped[list["ReglaGuardrail"]] = relationship(back_populates="politica", cascade="all, delete-orphan")


class ReglaGuardrail(Base):
    __tablename__ = "tb_regla_guardrail"
    id_regla: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_politica: Mapped[int] = mapped_column(ForeignKey("tb_politica_ia.id_politica", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(20))  # SALIDA | ENTRADA
    patron: Mapped[str] = mapped_column(String(300))  # expresión regular (validada al guardar)
    accion: Mapped[str] = mapped_column(String(15))  # BLOQUEAR | ALERTAR
    descripcion: Mapped[str | None] = mapped_column(String(255))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    politica: Mapped[PoliticaIA] = relationship(back_populates="reglas")


class Guion(Base):
    __tablename__ = "tb_guion"
    __table_args__ = (UniqueConstraint("nombre", "version", name="uq_guion_version"),)
    id_guion: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    contenido: Mapped[str] = mapped_column(Text)
    tramo: Mapped[str] = mapped_column(String(30))
    frases_obligatorias: Mapped[list | None] = mapped_column(JSON)
    estado: Mapped[str] = mapped_column(String(15), default="BORRADOR")  # BORRADOR|PUBLICADO|ARCHIVADO
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class CasoUso(Base):
    """CASO_USO_CONVERSACIONAL del DER-04 (módulo Entrenamiento)."""

    __tablename__ = "tb_caso_uso"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_guion: Mapped[int] = mapped_column(ForeignKey("tb_guion.id_guion", ondelete="CASCADE"))
    intencion: Mapped[str] = mapped_column(String(100))
    entrada_cliente: Mapped[str] = mapped_column(Text)
    respuesta_esperada: Mapped[str] = mapped_column(Text)
    debe_contener: Mapped[str | None] = mapped_column(String(255))  # palabras separadas por |
    no_debe_contener: Mapped[str | None] = mapped_column(String(255))


class EvaluacionCaso(Base):
    __tablename__ = "tb_evaluacion_caso"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_caso: Mapped[int] = mapped_column(ForeignKey("tb_caso_uso.id", ondelete="CASCADE"))
    id_agente: Mapped[int] = mapped_column(ForeignKey("tb_agente_ia.id_agente", ondelete="CASCADE"))
    aprobado: Mapped[bool] = mapped_column(Boolean)
    respuesta_obtenida: Mapped[str | None] = mapped_column(Text)
    detalle: Mapped[str | None] = mapped_column(String(500))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class AgenteIA(Base):
    __tablename__ = "tb_agente_ia"
    id_agente: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    voz_deepgram: Mapped[str] = mapped_column(String(60))
    velocidad_voz: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("1.00"))  # 0.70 lenta a 1.40 rápida
    tono: Mapped[str] = mapped_column(String(80))
    personalidad: Mapped[str | None] = mapped_column(String(255))
    severidad: Mapped[int] = mapped_column(Integer, default=1)  # 1 a 3, ajustado por tramo
    id_guion: Mapped[int | None] = mapped_column(ForeignKey("tb_guion.id_guion", ondelete="SET NULL"))
    id_politica: Mapped[int | None] = mapped_column(ForeignKey("tb_politica_ia.id_politica", ondelete="SET NULL"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Tools opcionales activas para este agente (las básicas siempre lo están). None = las recomendadas.
    herramientas: Mapped[list | None] = mapped_column(JSON)
    # Tiempos de la llamada telefónica: espera antes de que hable al contestar y silencio que cierra el turno del cliente.
    espera_inicio_seg: Mapped[Decimal] = mapped_column(Numeric(3, 1), default=Decimal("0.0"))
    silencio_fin_seg: Mapped[Decimal] = mapped_column(Numeric(3, 1), default=Decimal("2.0"))
    # Silencio máximo esperando a que el cliente empiece a hablar; después el agente pregunta si lo escucha.
    silencio_max_seg: Mapped[Decimal] = mapped_column(Numeric(3, 1), default=Decimal("6.0"))
    guion: Mapped[Guion | None] = relationship()
    politica: Mapped[PoliticaIA | None] = relationship()
    skills: Mapped[list["AgenteSkill"]] = relationship(cascade="all, delete-orphan", lazy="selectin")


class Skill(Base):
    """Conocimiento o técnica escrita por especialistas (no generada por IA). Versionada como los guiones:
    una versión no se edita; para cambiarla se crea una nueva. Ámbito AGENTE (negociación) o SUPERVISOR (calidad)."""

    __tablename__ = "tb_skill"
    __table_args__ = (UniqueConstraint("nombre", "version", name="uq_skill_version"),)
    id_skill: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    ambito: Mapped[str] = mapped_column(String(15), default="AGENTE")  # AGENTE | SUPERVISOR
    cuando_usar: Mapped[str] = mapped_column(String(255))
    contenido: Mapped[str] = mapped_column(Text)
    autor: Mapped[str] = mapped_column(String(120))  # especialista que la definió
    estado: Mapped[str] = mapped_column(String(15), default="BORRADOR")  # BORRADOR|PUBLICADO|ARCHIVADO
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class AgenteSkill(Base):
    __tablename__ = "tb_agente_skill"
    __table_args__ = (UniqueConstraint("id_agente", "id_skill", name="uq_agente_skill"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_agente: Mapped[int] = mapped_column(ForeignKey("tb_agente_ia.id_agente", ondelete="CASCADE"))
    id_skill: Mapped[int] = mapped_column(ForeignKey("tb_skill.id_skill", ondelete="CASCADE"))
    skill: Mapped[Skill] = relationship(lazy="joined")


class HerramientaVersion(Base):
    """Texto editable de una tool: lo que lee el agente (descripcion) y, si aplica, el texto que devuelve
    (p. ej. el aviso legal). El comportamiento y las validaciones están en el código. Versionada: no se edita."""

    __tablename__ = "tb_herramienta"
    __table_args__ = (UniqueConstraint("nombre", "version", name="uq_herramienta_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(60))
    version: Mapped[int] = mapped_column(Integer, default=1)
    descripcion: Mapped[str] = mapped_column(String(1000))
    texto_respuesta: Mapped[str | None] = mapped_column(String(1000))
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class PreguntaFrecuente(Base):
    """Respuestas aprobadas que la tool de dudas consulta en tiempo real (dónde pagar, horarios, etc.)."""

    __tablename__ = "tb_pregunta_frecuente"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pregunta: Mapped[str] = mapped_column(String(255))
    palabras_clave: Mapped[str] = mapped_column(String(255))
    respuesta: Mapped[str] = mapped_column(String(1000))
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class CampanaAgente(Base):
    __tablename__ = "tb_campana_agente"
    __table_args__ = (UniqueConstraint("id_campana", "id_agente", name="uq_campana_agente"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_campana: Mapped[int] = mapped_column(ForeignKey("tb_campana.id_campana", ondelete="CASCADE"))
    id_agente: Mapped[int] = mapped_column(ForeignKey("tb_agente_ia.id_agente", ondelete="CASCADE"))
    campana: Mapped[Campana] = relationship(back_populates="agentes")
    agente: Mapped[AgenteIA] = relationship()


# ============================================================ TELEFONÍA (DER-04)
class PlantaFreeswitch(Base):
    __tablename__ = "tb_planta_freeswitch"
    id_planta: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    ip: Mapped[str] = mapped_column(String(45))  # solo red privada / localhost (validado)
    puerto_esl: Mapped[int] = mapped_column(Integer, default=8021)
    capacidad_canales: Mapped[int] = mapped_column(Integer, default=1)
    estado: Mapped[str] = mapped_column(String(20), default="SIN_VERIFICAR")  # DISPONIBLE|NO_DISPONIBLE|SIN_VERIFICAR
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    ultima_verificacion: Mapped[datetime | None] = mapped_column(DateTime)


class TroncalSIP(Base):
    """Las credenciales SIP viven en la configuración de FreeSWITCH, no en esta tabla."""

    __tablename__ = "tb_troncal_sip"
    id_troncal: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_planta: Mapped[int] = mapped_column(ForeignKey("tb_planta_freeswitch.id_planta", ondelete="CASCADE"))
    nombre: Mapped[str] = mapped_column(String(80), unique=True)
    gateway: Mapped[str] = mapped_column(String(60))  # nombre del gateway sofia en FreeSWITCH
    proveedor: Mapped[str | None] = mapped_column(String(80))
    max_canales: Mapped[int] = mapped_column(Integer, default=1)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)


class ExtensionSIP(Base):
    __tablename__ = "tb_extension_sip"
    __table_args__ = (UniqueConstraint("id_planta", "numero", name="uq_extension_planta"),)
    id_extension: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_planta: Mapped[int] = mapped_column(ForeignKey("tb_planta_freeswitch.id_planta", ondelete="CASCADE"))
    id_troncal: Mapped[int | None] = mapped_column(ForeignKey("tb_troncal_sip.id_troncal", ondelete="SET NULL"))
    numero: Mapped[str] = mapped_column(String(20))
    canales_max: Mapped[int] = mapped_column(Integer, default=1)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    planta: Mapped[PlantaFreeswitch] = relationship()
    troncal: Mapped[TroncalSIP | None] = relationship()


class CanalConcurrente(Base):
    __tablename__ = "tb_canal_concurrente"
    id_canal: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_extension: Mapped[int] = mapped_column(ForeignKey("tb_extension_sip.id_extension", ondelete="CASCADE"))
    estado: Mapped[str] = mapped_column(String(15), default="LIBRE")  # LIBRE | OCUPADO | BLOQUEADO
    id_llamada: Mapped[int | None] = mapped_column(BigId)
    ocupado_desde: Mapped[datetime | None] = mapped_column(DateTime)
    extension: Mapped[ExtensionSIP] = relationship()


class NumeroAutorizado(Base):
    """Números de prueba autorizados para el piloto telefónico."""

    __tablename__ = "tb_numero_autorizado"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telefono: Mapped[str] = mapped_column(String(16), unique=True)
    descripcion: Mapped[str] = mapped_column(String(160))
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


# ============================================================ LLAMADAS / QA (DER-01/04)
class Llamada(Base):
    """Interacción del agente. Separa estado técnico, resultado de contacto y resultado de cobranza."""

    __tablename__ = "tb_llamada"
    __table_args__ = (
        Index("ix_llamada_inicio", "inicio"),
        Index("ix_llamada_campana", "id_campana", "inicio"),
        Index("ix_llamada_cliente", "id_cliente"),
    )
    id_llamada: Mapped[int] = mapped_column(BigId, primary_key=True)
    canal: Mapped[str] = mapped_column(String(20))  # TEXTO | VOZ_NAVEGADOR | TELEFONIA
    modo: Mapped[str] = mapped_column(String(15))  # PRUEBA | REAL
    id_campana: Mapped[int | None] = mapped_column(ForeignKey("tb_campana.id_campana", ondelete="SET NULL"))
    id_cliente_campana: Mapped[int | None] = mapped_column(ForeignKey("tb_cliente_campana.id", ondelete="SET NULL"))
    id_cliente: Mapped[int | None] = mapped_column(ForeignKey("tb_cliente.id_cliente", ondelete="SET NULL"))
    id_deuda: Mapped[int | None] = mapped_column(ForeignKey("tb_deuda.id_deuda", ondelete="SET NULL"))
    id_agente: Mapped[int | None] = mapped_column(ForeignKey("tb_agente_ia.id_agente", ondelete="SET NULL"))
    id_guion: Mapped[int | None] = mapped_column(ForeignKey("tb_guion.id_guion", ondelete="SET NULL"))
    version_guion: Mapped[int | None] = mapped_column(Integer)
    id_politica: Mapped[int | None] = mapped_column(ForeignKey("tb_politica_ia.id_politica", ondelete="SET NULL"))
    version_politica: Mapped[int | None] = mapped_column(Integer)
    id_extension: Mapped[int | None] = mapped_column(ForeignKey("tb_extension_sip.id_extension", ondelete="SET NULL"))
    id_canal: Mapped[int | None] = mapped_column(ForeignKey("tb_canal_concurrente.id_canal", ondelete="SET NULL"))
    uuid_freeswitch: Mapped[str | None] = mapped_column(String(64), unique=True)
    destino_enmascarado: Mapped[str | None] = mapped_column(String(20))
    estado_tecnico: Mapped[str] = mapped_column(String(15), default="EN_CURSO")  # PENDIENTE|EN_CURSO|FINALIZADA|FALLIDA|CANCELADA
    resultado_contacto: Mapped[str | None] = mapped_column(String(15))  # CONTESTADA|RECHAZADA|SIN_CONTESTAR
    resultado_cobranza: Mapped[str | None] = mapped_column(String(25))  # PROMESA|NEGATIVA|NO_CONTACTO|REVISION_HUMANA|SIN_RESULTADO
    identidad_verificada: Mapped[bool] = mapped_column(Boolean, default=False)
    intentos_identidad: Mapped[int] = mapped_column(Integer, default=0)
    bloqueos_guardrail: Mapped[int] = mapped_column(Integer, default=0)
    turnos: Mapped[int] = mapped_column(Integer, default=0)
    promesa_propuesta: Mapped[dict | None] = mapped_column(JSON)
    motivo_fallo: Mapped[str | None] = mapped_column(String(255))
    duracion_seg: Mapped[int | None] = mapped_column(Integer)
    costo_estimado_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    inicio: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    fin: Mapped[datetime | None] = mapped_column(DateTime)
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    cliente: Mapped[Cliente | None] = relationship()
    deuda: Mapped[Deuda | None] = relationship()
    agente: Mapped[AgenteIA | None] = relationship()
    campana: Mapped[Campana | None] = relationship()


class TurnoConversacion(Base):
    """Fragmentos de la transcripción (texto ya enmascarado)."""

    __tablename__ = "tb_turno_conversacion"
    __table_args__ = (UniqueConstraint("id_llamada", "orden", name="uq_turno_orden"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    id_llamada: Mapped[int] = mapped_column(ForeignKey("tb_llamada.id_llamada", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)
    rol: Mapped[str] = mapped_column(String(10))  # AGENTE | CLIENTE | SISTEMA
    texto: Mapped[str] = mapped_column(Text)
    bloqueado: Mapped[bool] = mapped_column(Boolean, default=False)
    confianza_stt: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class EventoLlamada(Base):
    """Eventos idempotentes: `clave_evento` única evita doble conteo de eventos repetidos."""

    __tablename__ = "tb_evento_llamada"
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    id_llamada: Mapped[int] = mapped_column(ForeignKey("tb_llamada.id_llamada", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(40))
    clave_evento: Mapped[str] = mapped_column(String(120), unique=True)
    datos: Mapped[dict | None] = mapped_column(JSON)
    fecha_evento: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class Grabacion(Base):
    __tablename__ = "tb_grabacion"
    id_grabacion: Mapped[int] = mapped_column(BigId, primary_key=True)
    id_llamada: Mapped[int] = mapped_column(ForeignKey("tb_llamada.id_llamada", ondelete="CASCADE"))
    ruta_audio: Mapped[str] = mapped_column(String(255))
    formato: Mapped[str] = mapped_column(String(40))
    cifrada: Mapped[bool] = mapped_column(Boolean, default=True)
    duracion_seg: Mapped[int | None] = mapped_column(Integer)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class Transcripcion(Base):
    __tablename__ = "tb_transcripcion"
    id_transcripcion: Mapped[int] = mapped_column(BigId, primary_key=True)
    id_llamada: Mapped[int] = mapped_column(ForeignKey("tb_llamada.id_llamada", ondelete="CASCADE"), unique=True)
    id_grabacion: Mapped[int | None] = mapped_column(ForeignKey("tb_grabacion.id_grabacion", ondelete="SET NULL"))
    texto: Mapped[str] = mapped_column(Text)
    confianza: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class EvaluacionQA(Base):
    __tablename__ = "tb_evaluacion_qa"
    id_qa: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_llamada: Mapped[int] = mapped_column(ForeignKey("tb_llamada.id_llamada", ondelete="CASCADE"))
    id_transcripcion: Mapped[int | None] = mapped_column(ForeignKey("tb_transcripcion.id_transcripcion", ondelete="SET NULL"))
    puntaje: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    cumple_guion: Mapped[bool] = mapped_column(Boolean)
    trato_adecuado: Mapped[bool] = mapped_column(Boolean)
    confirmacion_correcta: Mapped[bool | None] = mapped_column(Boolean)
    compromisos_fuera_politica: Mapped[bool] = mapped_column(Boolean, default=False)
    incertidumbre: Mapped[str] = mapped_column(String(10))  # BAJA|MEDIA|ALTA
    hallazgos: Mapped[list | None] = mapped_column(JSON)
    resumen: Mapped[str | None] = mapped_column(Text)
    observacion: Mapped[str | None] = mapped_column(String(500))
    proveedor: Mapped[str] = mapped_column(String(30))
    modelo: Mapped[str] = mapped_column(String(80))
    version_prompt: Mapped[str] = mapped_column(String(20))
    estado_revision: Mapped[str] = mapped_column(String(15), default="PENDIENTE")  # PENDIENTE|REVISADA
    revisado_por: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    puntaje_humano: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class PruebaLlamada(Base):
    __tablename__ = "tb_prueba_llamada"
    id_prueba: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_agente: Mapped[int | None] = mapped_column(ForeignKey("tb_agente_ia.id_agente", ondelete="SET NULL"))
    id_llamada: Mapped[int | None] = mapped_column(ForeignKey("tb_llamada.id_llamada", ondelete="SET NULL"))
    tipo: Mapped[str] = mapped_column(String(20))  # TEXTO | VOZ_NAVEGADOR | TTS | TELEFONIA
    resultado: Mapped[str] = mapped_column(String(30))
    calidad_voz: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    latencia_ms: Mapped[int | None] = mapped_column(Integer)
    detalle: Mapped[str | None] = mapped_column(String(500))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


# ============================================================ PROMESAS (DER-03)
class PromesaPago(Base):
    """Una promesa NO es un pago. Vinculada a cliente, deuda, campaña y llamada."""

    __tablename__ = "tb_promesa_pago"
    __table_args__ = (
        CheckConstraint("monto > 0", name="ck_promesa_monto"),
        Index("ix_promesa_estado_fecha", "estado", "fecha_compromiso"),
    )
    id_promesa: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_cliente: Mapped[int] = mapped_column(ForeignKey("tb_cliente.id_cliente"))
    id_deuda: Mapped[int] = mapped_column(ForeignKey("tb_deuda.id_deuda"))
    id_campana: Mapped[int | None] = mapped_column(ForeignKey("tb_campana.id_campana", ondelete="SET NULL"))
    id_cliente_campana: Mapped[int | None] = mapped_column(ForeignKey("tb_cliente_campana.id", ondelete="SET NULL"))
    id_llamada: Mapped[int] = mapped_column(ForeignKey("tb_llamada.id_llamada"))
    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    moneda: Mapped[str] = mapped_column(String(3))
    fecha_compromiso: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(15), default="PENDIENTE")  # PENDIENTE|CUMPLIDA|INCUMPLIDA|CANCELADA
    clave_idempotencia: Mapped[str] = mapped_column(String(80), unique=True)
    frase_confirmacion: Mapped[str | None] = mapped_column(String(255))
    confirmada_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    id_usuario_cumplimiento: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_cumplimiento: Mapped[datetime | None] = mapped_column(DateTime)
    observacion: Mapped[str | None] = mapped_column(String(255))
    cliente: Mapped[Cliente] = relationship()
    deuda: Mapped[Deuda] = relationship()
    campana: Mapped[Campana | None] = relationship()


class SeguimientoPromesa(Base):
    __tablename__ = "tb_seguimiento_promesa"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_promesa: Mapped[int] = mapped_column(ForeignKey("tb_promesa_pago.id_promesa", ondelete="CASCADE"))
    resultado: Mapped[str] = mapped_column(String(30))
    reingreso_campana: Mapped[bool] = mapped_column(Boolean, default=False)
    observacion: Mapped[str | None] = mapped_column(String(255))
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha_revision: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


# ============================================================ OPERACIÓN
class Trabajo(Base):
    """Cola durable en MySQL: sobrevive a reinicios; se reclama con SELECT ... FOR UPDATE SKIP LOCKED."""

    __tablename__ = "tb_trabajo"
    __table_args__ = (Index("ix_trabajo_estado", "estado", "disponible_en"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30))  # MARCAR | LLAMAR_EXTENSION | QA_LLAMADA | REVISAR_PROMESAS | SUPERVISION_SEGURIDAD
    estado: Mapped[str] = mapped_column(String(15), default="PENDIENTE")  # PENDIENTE|EN_PROCESO|COMPLETADO|FALLIDO|CANCELADO
    payload: Mapped[dict] = mapped_column(JSON)
    clave_idempotencia: Mapped[str] = mapped_column(String(120), unique=True)
    intentos: Mapped[int] = mapped_column(Integer, default=0)
    max_intentos: Mapped[int] = mapped_column(Integer, default=3)
    disponible_en: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    bloqueado_por: Mapped[str | None] = mapped_column(String(80))
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime)
    resultado: Mapped[str | None] = mapped_column(String(500))
    creado: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc)


class Alerta(Base):
    __tablename__ = "tb_alerta"
    __table_args__ = (Index("ix_alerta_estado", "estado", "fecha"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(50))
    severidad: Mapped[str] = mapped_column(String(10))  # BAJA|MEDIA|ALTA|CRITICA
    origen: Mapped[str] = mapped_column(String(20))  # REGLA | SUPERVISOR_IA | AGENTE_IA
    mensaje: Mapped[str] = mapped_column(String(500))
    recomendacion: Mapped[str | None] = mapped_column(String(500))
    detalle: Mapped[dict | None] = mapped_column(JSON)
    clave: Mapped[str | None] = mapped_column(String(120), unique=True)  # evita alertas duplicadas
    estado: Mapped[str] = mapped_column(String(12), default="ABIERTA")  # ABIERTA|RECONOCIDA|CERRADA
    id_usuario_cierre: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class ConsumoAPI(Base):
    __tablename__ = "tb_consumo_api"
    __table_args__ = (Index("ix_consumo_fecha", "fecha"),)
    id: Mapped[int] = mapped_column(BigId, primary_key=True)
    proveedor: Mapped[str] = mapped_column(String(30))
    servicio: Mapped[str] = mapped_column(String(30))  # AGENTE | SUPERVISOR_QA | SUPERVISOR_SEG | STT | TTS
    modelo: Mapped[str] = mapped_column(String(80))
    version_prompt: Mapped[str | None] = mapped_column(String(20))
    id_llamada: Mapped[int | None] = mapped_column(ForeignKey("tb_llamada.id_llamada", ondelete="SET NULL"))
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0)
    tokens_salida: Mapped[int] = mapped_column(Integer, default=0)
    segundos_audio: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    caracteres: Mapped[int] = mapped_column(Integer, default=0)
    costo_estimado_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    exito: Mapped[bool] = mapped_column(Boolean)
    codigo_error: Mapped[str | None] = mapped_column(String(60))
    latencia_ms: Mapped[int | None] = mapped_column(Integer)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc)


class Configuracion(Base):
    __tablename__ = "tb_configuracion"
    clave: Mapped[str] = mapped_column(String(60), primary_key=True)
    valor: Mapped[str] = mapped_column(String(500))
    descripcion: Mapped[str | None] = mapped_column(String(255))
    id_usuario: Mapped[int | None] = mapped_column(ForeignKey("tb_usuario.id_usuario", ondelete="SET NULL"))
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=ahora_utc, onupdate=ahora_utc)


class Riesgo(Base):
    """Matriz de riesgos del documento de la fase final (R-01 a R-08)."""

    __tablename__ = "tb_riesgo"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    categoria: Mapped[str] = mapped_column(String(120))
    probabilidad: Mapped[int] = mapped_column(Integer)
    impacto: Mapped[int] = mapped_column(Integer)
    disparador: Mapped[str] = mapped_column(String(255))
    componente: Mapped[str] = mapped_column(String(120))
    estrategia: Mapped[str] = mapped_column(String(500))
    control_implementado: Mapped[str] = mapped_column(String(500))
