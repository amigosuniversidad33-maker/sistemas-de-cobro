# Llamada real con FreeSWITCH en una VM Linux y Zoiper

Así lo indicó el ingeniero: FreeSWITCH corre en una **máquina virtual Linux** y el sistema web se conecta a ella por IP con
el **Event Socket** de FreeSWITCH (puerto 8021, protegido con contraseña). En el celular o en otra computadora se instala
**Zoiper**, que se registra como una **extensión** de FreeSWITCH (por ejemplo la 1000). Desde **Prueba de Llamada** el
sistema llama a esa extensión y el agente IA conversa por voz.

No hace falta troncal SIP ni número público: la llamada no sale a la red telefónica, se queda dentro de su red local.

```
 Windows (este equipo)                         VM Linux (Debian 12)                Celular
 +--------------------------+   ESL 8021/TCP   +----------------------+  SIP 5060  +---------+
 | Sistema web + worker     | ---------------> | FreeSWITCH           | <--------> | Zoiper  |
 | C:\cobros_audio  (SMB) <-+---- carpeta ---->| /mnt/cobros_audio    |    RTP     | ext 1000|
 +--------------------------+    compartida    +----------------------+            +---------+
```

Todo debe estar en la **misma red Wi-Fi/LAN** (computadora, VM y celular).

## 1. Máquina virtual
1. VirtualBox (o VMware) con **Debian 12**, 2 GB de RAM, 2 CPU, 20 GB de disco.
2. Red del adaptador: **Adaptador puente (Bridged)**, para que la VM tenga una IP de su Wi-Fi (p. ej. `192.168.1.50`)
   visible para el celular. Véala con `ip -4 addr`.

## 2. Instalar FreeSWITCH en la VM
FreeSWITCH requiere un token gratuito de SignalWire para el repositorio oficial. Siga la guía oficial vigente:
https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Installation/ (sección Debian, paquetes
`freeswitch-meta-all`). Instale también `cifs-utils` (para la carpeta compartida):
```bash
sudo apt-get install -y cifs-utils
sudo systemctl enable --now freeswitch
fs_cli -x status
```

## 3. Event Socket (el «socket» para el sistema web)
Edite `/etc/freeswitch/autoload_configs/event_socket.conf.xml`:
```xml
<param name="listen-ip" value="0.0.0.0"/>
<param name="listen-port" value="8021"/>
<param name="password" value="UNA_CLAVE_LARGA_Y_UNICA"/>
<param name="apply-inbound-acl" value="lan"/>
```
En `/etc/freeswitch/autoload_configs/acl.conf.xml`, dentro de `<list name="lan" default="deny">`, permita **solo** la IP de
su computadora Windows (véala con `ipconfig`): `<node type="allow" cidr="192.168.1.20/32"/>`.
Reinicie: `sudo systemctl restart freeswitch`. **Nunca** abra el puerto 8021 a Internet ni deje la clave `ClueCon`.

## 4. Extensiones para Zoiper
FreeSWITCH trae las extensiones 1000 a 1019. Cambie la clave por defecto (`1234`) en `/etc/freeswitch/vars.xml`:
```xml
<X-PRE-PROCESS cmd="set" data="default_password=OTRA_CLAVE_SEGURA"/>
```
y reinicie FreeSWITCH.

En **Zoiper** (celular o PC) agregue una cuenta SIP:
- Usuario: `1000` · Contraseña: la `default_password` · Dominio/Host: la IP de la VM (`192.168.1.50`), puerto 5060, UDP.
- Debe quedar en verde («Registered»). En la VM compruébelo con `fs_cli -x "sofia status profile internal reg"`.

## 5. Carpeta de audio compartida (puente de voz)
El agente habla con audios WAV que crea el sistema, y lo que usted responde se graba en WAV para reconocerlo; ambos viajan
por una carpeta compartida entre Windows y la VM.
1. En Windows cree `C:\cobros_audio` › clic derecho › Propiedades › Compartir › con su usuario (lectura y escritura).
2. En la VM:
   ```bash
   sudo mkdir -p /mnt/cobros_audio
   sudo mount -t cifs //192.168.1.20/cobros_audio /mnt/cobros_audio -o username=SU_USUARIO_WINDOWS,uid=freeswitch,gid=freeswitch,file_mode=0660,dir_mode=0770
   ```
   Para que quede fijo, agréguelo a `/etc/fstab` usando un archivo de credenciales con permisos 600.

### Alternativa sin carpeta compartida (la que usa este equipo): copia por SSH
Si la VM tiene acceso SSH con llave, el sistema copia cada audio con `scp` (OpenSSH viene con Windows) y no hace falta
compartir carpetas de Windows. El instalador `scripts/vm/instalar_freeswitch.sh` crea `/var/lib/cobros_audio` en la VM.
```
FREESWITCH_DIR_AUDIO=C:\sistema-cobros\backend\datos\audio_fs
FREESWITCH_DIR_AUDIO_REMOTO=/var/lib/cobros_audio
FREESWITCH_SSH_DESTINO=cobros@192.168.1.19
FREESWITCH_SSH_LLAVE=C:\Users\USUARIO\.ssh\cobros_vm
```

## 6. Configurar `backend\.env`
```
TELEFONIA_HABILITADA=true
FREESWITCH_ESL_PASSWORD=UNA_CLAVE_LARGA_Y_UNICA
FREESWITCH_DIR_AUDIO=C:\cobros_audio
FREESWITCH_DIR_AUDIO_REMOTO=/mnt/cobros_audio
DEEPGRAM_API_KEY=...
```
Reinicie el sistema (`DETENER.bat` como administrador si lo inició desde WAMP; luego `INICIAR.bat`).

## 7. Registrar la VM y la extensión en el sistema
1. **Plantas FreeSWITCH** › Nueva: IP de la VM (`192.168.1.50`), puerto 8021, capacidad 2 › **Verificar ESL** → DISPONIBLE.
2. **Extensiones SIP** › Nueva extensión: planta de la VM, número `1000`, **Troncal: Sin troncal**, 1 canal.
   Solo las extensiones sin troncal pueden recibir esta llamada de prueba.

## 8. Hacer la llamada
**Prueba de Llamada** › elija agente y cliente ficticio › tarjeta **Llamada real a extensión Zoiper (FreeSWITCH)** ›
**Llamar a la extensión**. Zoiper suena; conteste y hable después de cada mensaje del agente. La conversación aparece en
pantalla y queda en **Llamadas** (canal TELEFONÍA, destino «Ext. 1000»). El worker debe estar en ejecución (lo inicia
`INICIAR.bat`).

## Problemas frecuentes
| Mensaje | Causa / solución |
|---|---|
| `USER_NOT_REGISTERED` | Zoiper no está en verde: revise usuario, clave, IP o que estén en la misma red |
| Error ESL de conexión | IP o puerto incorrectos, firewall de la VM o ACL `lan` sin la IP de Windows |
| Error ESL de autenticación | `FREESWITCH_ESL_PASSWORD` distinta a la de `event_socket.conf.xml` |
| Contesta pero no se oye al agente | La carpeta compartida no está montada o `FREESWITCH_DIR_AUDIO_REMOTO` no coincide |
| El agente no le entiende | Hable después del mensaje. El turno termina tras 0.6 s de silencio (`TELEFONIA_SILENCIO_FIN_SEG`); si le corta, súbalo a 1.0. La muletilla «Ajá.» se cambia o desactiva con `TELEFONIA_MULETILLA` |

Limitación: el audio va por turnos (no hay interrupción mientras el agente habla). Un canal a la vez en el piloto.
