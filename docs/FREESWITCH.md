# Telefonía piloto con FreeSWITCH y SIP

Estado actual: **BLOQUEADA** hasta contar con FreeSWITCH instalado, una troncal SIP contratada y un número de prueba autorizado.
Sin estos tres elementos el proyecto debe reportarse **incompleto en telefonía**. La voz en el navegador no sustituye este requisito.

## 1. Qué necesita

| Elemento | Detalle |
|---|---|
| FreeSWITCH 1.10.x | Licencia MPL 1.1 (código abierto). En Windows el instalador oficial está descontinuado; opciones: **WSL2 con Debian 12** (recomendado) o una VM Linux en la misma red privada |
| Troncal SIP | Proveedor con salida a Guatemala; usuario, contraseña, dominio/proxy. Costo aproximado de piloto en el presupuesto: Q 800 |
| Número autorizado | Su propio celular u otro número cuyo dueño autorizó la prueba |
| Carpeta compartida | Una ruta que vean tanto FreeSWITCH como el backend (`FREESWITCH_DIR_AUDIO`) |
| Red | Puertos UDP 5060 (SIP) y 16384–32768 (RTP) hacia el proveedor; si hay NAT, configurar `ext-rtp-ip`/`ext-sip-ip` |

Justificación de WSL2: FreeSWITCH no se distribuye oficialmente para Windows. Confirme primero que su Windows tiene WSL2
(`wsl --status`). El resto del sistema **no** requiere WSL2.

## 2. Instalación (WSL2 Debian 12)

FreeSWITCH requiere un token gratuito de SignalWire para el repositorio oficial. Siga la guía oficial vigente:
https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Installation/ . Al terminar, verifique: `fs_cli -x status`.

## 3. Endurecimiento obligatorio

1. **Cambie la contraseña predeterminada `ClueCon`** del Event Socket en `/etc/freeswitch/autoload_configs/event_socket.conf.xml`:
   ```xml
   <param name="listen-ip" value="127.0.0.1"/>   <!-- o la IP privada; nunca 0.0.0.0 -->
   <param name="listen-port" value="8021"/>
   <param name="password" value="UNA_CLAVE_LARGA_Y_UNICA"/>
   <param name="apply-inbound-acl" value="loopback.auto"/>
   ```
   Copie esa clave a `FREESWITCH_ESL_PASSWORD` en `backend\.env`.
2. Cambie `default_password` en `vars.xml` (por defecto `1234`).
3. No exponga 8021 ni el perfil interno a Internet; solo el perfil externo hacia el proveedor SIP.

## 4. Gateway SIP

`/etc/freeswitch/sip_profiles/external/proveedor.xml` (los datos los entrega su proveedor):
```xml
<include>
  <gateway name="gw_proveedor">
    <param name="username" value="USUARIO_SIP"/>
    <param name="password" value="CLAVE_SIP"/>
    <param name="proxy" value="sip.proveedor.example"/>
    <param name="register" value="true"/>
  </gateway>
</include>
```
`fs_cli -x "sofia profile external rescan"` y `fs_cli -x "sofia status gateway gw_proveedor"` → debe decir `REGED`.

## 5. Carpeta de audio compartida

En WSL2 la carpeta de Windows `C:\cobros_audio` se ve como `/mnt/c/cobros_audio`. El backend escribe y lee en Windows y
FreeSWITCH reproduce y graba en la misma carpeta. Configure:
- `.env`: `FREESWITCH_DIR_AUDIO=C:\cobros_audio`
- Para que FreeSWITCH use la ruta correcta, cree el enlace en WSL: `sudo ln -s /mnt/c/cobros_audio /cobros_audio` y ajuste
  `FREESWITCH_DIR_AUDIO=/cobros_audio` **solo si** backend y FreeSWITCH corren en el mismo Linux. Si el backend corre en Windows y
  FreeSWITCH en WSL2, las rutas difieren: esta configuración mixta debe validarse en la prueba M-11 (riesgo R-08).

## 6. Configuración en la aplicación

1. `.env`: `TELEFONIA_HABILITADA=true`, `FREESWITCH_ESL_PASSWORD=…`, `FREESWITCH_DIR_AUDIO=…`, `DEEPGRAM_API_KEY=…`.
2. **Plantas FreeSWITCH**: IP `127.0.0.1` (WSL2 reenvía localhost) o la IP privada de la VM, puerto 8021, capacidad 1 → *Verificar ESL*.
3. **Extensiones SIP**: crear troncal con gateway `gw_proveedor`, extensión con 1 canal y **autorizar su número**.
4. Importar un cliente ficticio cuyo teléfono sea su número autorizado; crear campaña, activar y **Encolar marcación**.
5. El worker (`iniciar.ps1` lo inicia) toma el trabajo, vuelve a verificar las reglas y origina.

## 7. Verificación (prueba M-11)

- Su teléfono suena; al contestar escucha el saludo (Deepgram TTS) y puede responder después de cada mensaje.
- En **Llamadas** aparece con canal «TELEFONÍA REAL», eventos `ORIGINATE_SOLICITADO`, `CONTESTADA`, `COLGADA`, `CANAL_LIBERADO`.
- En **Extensiones SIP** el canal vuelve a LIBRE.
- Si no contesta: resultado SIN_CONTESTAR. Si el gateway falla: FALLIDA (fallo técnico) y alerta.

## 8. Limitaciones conocidas

- Puente de medios por turnos (no streaming): no hay interrupción del interlocutor durante la locución telefónica y la ventana de
  escucha termina al detectar el silencio del cliente (`TELEFONIA_SILENCIO_FIN_SEG`, `TELEFONIA_MAX_SEGUNDOS_TURNO`). El streaming bidireccional con `mod_audio_stream` (módulo de terceros, revisar su
  licencia) queda pendiente.
- Un canal concurrente. La meta de 65,000 llamadas/día no ha sido probada.
