"""Configuración central. Todos los valores salen de variables de entorno / archivo .env.

Secretos (claves API, contraseña MySQL, ESL) NUNCA se escriben en el código.
"""
from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Aplicación ---
    app_nombre: str = "Sistema Outbound de Cobros con IA"
    app_host: str = "127.0.0.1"  # solo localhost por defecto: no exponer a la red
    # true = también la abren otras computadoras de la MISMA red local (http://IP-de-este-equipo:8000). Nunca por Internet.
    acceso_red_local: bool = False
    app_port: int = 8000
    entorno: str = "local"  # local | pruebas | produccion
    zona_horaria: str = "America/Guatemala"

    # --- Base de datos ---
    database_url: str = "mysql+pymysql://cobros_app:CAMBIAR@127.0.0.1:3306/cobros_ia?charset=utf8mb4"
    # Usuario con permisos de DDL solo para migraciones y respaldos (opcional; si está vacío se usa database_url)
    database_url_migraciones: str = ""
    mysql_bin_dir: str = ""
    respaldo_clave: str = ""
    db_echo: bool = False

    # --- Sesiones y seguridad ---
    cookie_secure: bool = False  # True cuando se sirva por HTTPS
    sesion_inactividad_min: int = 30
    sesion_absoluta_horas: int = 8
    login_max_intentos_usuario: int = 5
    login_bloqueo_min: int = 15
    login_max_fallos_ip_15min: int = 20
    # Parámetros scrypt (OWASP: N=2^17, r=8, p=1). En pruebas se reducen.
    scrypt_n: int = 2 ** 17
    scrypt_r: int = 8
    scrypt_p: int = 1
    tamano_max_importacion_mb: int = 5

    # --- Proveedor LLM (Anthropic por defecto) ---
    llm_proveedor: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_modelo: str = "claude-haiku-5-5"
    anthropic_modelo_supervisor: str = "claude-sonnet-5-5"
    anthropic_url: str = "https://api.anthropic.com/v1/messages"
    anthropic_version: str = "2023-06-01"
    llm_timeout_seg: float = 30.0
    llm_reintentos: int = 2
    llm_max_tokens_respuesta: int = 400
    llm_max_tokens_supervisor: int = 1500
    # Precios de REFERENCIA para estimar costo (USD por millón de tokens). No es facturación real.
    llm_precio_entrada_mtok: Decimal = Decimal("1.00")
    llm_precio_salida_mtok: Decimal = Decimal("5.00")

    # --- Deepgram ---
    deepgram_api_key: str = ""
    deepgram_stt_modelo: str = "nova-3"
    deepgram_tts_modelo: str = "aura-2-diana-es"
    deepgram_idioma: str = "es"
    deepgram_timeout_seg: float = 30.0
    deepgram_precio_stt_min: Decimal = Decimal("0.0077")  # referencia, verificar tarifa vigente
    deepgram_precio_tts_1k_car: Decimal = Decimal("0.030")  # referencia, verificar tarifa vigente
    voz_max_audio_mb: int = 5
    voz_max_segundos_turno: int = 30

    # --- Presupuesto (USD estimado) ---
    presupuesto_diario_usd: Decimal = Decimal("2.00")
    presupuesto_interaccion_usd: Decimal = Decimal("0.20")
    max_turnos_conversacion: int = 30
    max_duracion_conversacion_seg: int = 600

    # --- Grabaciones (cifrado Fernet/AES-128-CBC + HMAC) ---
    grabaciones_dir: str = "datos/grabaciones"
    grabaciones_clave: str = ""  # vacío => no se guardan grabaciones de audio

    # --- Telefonía FreeSWITCH ---
    telefonia_habilitada: bool = False
    freeswitch_esl_password: str = ""
    freeswitch_dir_audio: str = ""  # carpeta compartida entre FreeSWITCH y backend (ruta vista por el backend)
    # Ruta de esa MISMA carpeta vista por FreeSWITCH cuando corre en otra máquina (VM Linux), p. ej. /mnt/cobros_audio.
    # Vacío = misma ruta en ambos (FreeSWITCH en este equipo).
    freeswitch_dir_audio_remoto: str = ""
    # Si FreeSWITCH está en otra máquina sin carpeta compartida: los audios se copian por scp (OpenSSH de Windows).
    freeswitch_ssh_destino: str = ""  # p. ej. cobros@192.168.1.19
    freeswitch_ssh_llave: str = ""  # llave privada autorizada en la VM
    freeswitch_ssh_known_hosts: str = "datos/freeswitch_known_hosts"  # huella fijada de la VM (equipo desconocido = rechazo)
    telefonia_solo_numeros_autorizados: bool = True
    telefonia_originate_timeout_seg: int = 45
    # Turno del cliente: termina al detectar su silencio, no tras un tiempo fijo.
    telefonia_silencio_fin_seg: float = 0.6  # silencio tras hablar que marca el fin del turno
    telefonia_muletilla: str = ""  # frase corta al callar el cliente mientras se prepara la respuesta (vacío = ninguna)
    telefonia_espera_inicio_seg: float = 6.0  # si no empieza a hablar en este tiempo, se considera silencio
    telefonia_max_segundos_turno: int = 15

    # --- Retención (días) ---
    retencion_transcripciones_dias: int = 180
    retencion_grabaciones_dias: int = 90
    retencion_bitacora_dias: int = 365
    retencion_sesiones_dias: int = 30

    # --- Worker ---
    worker_intervalo_seg: float = 3.0
    worker_bloqueo_seg: int = 300

    nombre_empresa: str = Field(default="Financiera Progreso")

    # --- Llamada real de prueba con Twilio (alternativa a FreeSWITCH para el piloto) ---
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_numero: str = ""  # número Twilio en formato +1XXXXXXXXXX
    twilio_voz: str = "Polly.Mia-Neural"  # voz neuronal en español (México)
    twilio_idioma: str = "es-MX"
    url_publica: str = ""  # https://… del túnel; vacío = se detecta el túnel de ngrok abierto en este equipo
    # Voz del agente en la llamada: "deepgram" (la misma voz Aura-2 del agente, más natural) o "twilio" (<Say> con TWILIO_VOZ).
    # Si Deepgram falla en un turno, ese turno se dice con la voz de Twilio.
    twilio_motor_voz: str = "deepgram"
    ngrok_api_url: str = "http://127.0.0.1:4040/api/tunnels"  # API local del agente ngrok (solo este equipo)


@lru_cache
def get_settings() -> Settings:
    return Settings()
