#!/bin/bash
# Instala y asegura FreeSWITCH en Debian 12 para el piloto con Zoiper (ver docs/ZOIPER_FREESWITCH.md).
# Uso (en la VM):  sudo bash instalar_freeswitch.sh <IP_DE_WINDOWS>
# - Pide el token de SignalWire sin mostrarlo.
# - Genera claves aleatorias para el Event Socket y las extensiones (nada queda con 1234 ni ClueCon).
# - El Event Socket solo acepta conexiones desde la IP de Windows indicada.
set -euo pipefail
IP_WINDOWS="${1:?Indique la IP de la computadora Windows, p. ej. 192.168.1.12}"
USUARIO="${SUDO_USER:-cobros}"
CRED="/home/$USUARIO/cobros_freeswitch.txt"

if [ "$(id -u)" -ne 0 ]; then echo "Ejecute con sudo."; exit 1; fi

read -r -s -p "Pegue su token de SignalWire (no se mostrará) y pulse Enter: " TOKEN
echo
[ -n "$TOKEN" ] || { echo "Token vacío."; exit 1; }

echo "== Paquetes base"
apt-get update -q
apt-get install -y -q gnupg2 wget lsb-release ca-certificates curl openssl

echo "== Repositorio oficial de FreeSWITCH (SignalWire)"
CODIGO="$(curl -sS -u "signalwire:$TOKEN" -o /usr/share/keyrings/signalwire-freeswitch-repo.gpg -w '%{http_code}' \
  https://freeswitch.signalwire.com/repo/deb/debian-release/signalwire-freeswitch-repo.gpg || true)"
if [ "$CODIGO" != "200" ] || [ ! -s /usr/share/keyrings/signalwire-freeswitch-repo.gpg ]; then
  rm -f /usr/share/keyrings/signalwire-freeswitch-repo.gpg
  echo "ERROR: SignalWire respondió HTTP $CODIGO al descargar la llave del repositorio."
  [ "$CODIGO" = "401" ] && echo "El token no fue aceptado: use un «Personal Access Token» (Space > Personal Access Tokens)."
  exit 1
fi
install -m 600 /dev/null /etc/apt/auth.conf.d/freeswitch.conf
echo "machine freeswitch.signalwire.com login signalwire password $TOKEN" > /etc/apt/auth.conf.d/freeswitch.conf
echo "deb [signed-by=/usr/share/keyrings/signalwire-freeswitch-repo.gpg] https://freeswitch.signalwire.com/repo/deb/debian-release/ $(lsb_release -sc) main" \
  > /etc/apt/sources.list.d/freeswitch.list
unset TOKEN
apt-get update -q

echo "== Instalando FreeSWITCH (puede tardar varios minutos)"
apt-get install -y -q freeswitch-meta-vanilla freeswitch-mod-commands freeswitch-mod-event-socket freeswitch-mod-sndfile
[ -d /etc/freeswitch ] || cp -a /usr/share/freeswitch/conf/vanilla /etc/freeswitch

echo "== Claves nuevas"
CLAVE_ESL="$(openssl rand -hex 16)"
CLAVE_EXT="$(shuf -i 10000000-99999999 -n 1)"

echo "== Event Socket: escucha en la red local, solo acepta a $IP_WINDOWS"
cat > /etc/freeswitch/autoload_configs/event_socket.conf.xml <<EOF
<configuration name="event_socket.conf" description="Socket Client">
  <settings>
    <param name="nat-map" value="false"/>
    <param name="listen-ip" value="0.0.0.0"/>
    <param name="listen-port" value="8021"/>
    <param name="password" value="$CLAVE_ESL"/>
    <param name="apply-inbound-acl" value="cobros_esl"/>
  </settings>
</configuration>
EOF
if ! grep -q 'name="cobros_esl"' /etc/freeswitch/autoload_configs/acl.conf.xml; then
  sed -i "s#</network-lists>#    <list name=\"cobros_esl\" default=\"deny\">\n      <node type=\"allow\" cidr=\"$IP_WINDOWS/32\"/>\n      <node type=\"allow\" cidr=\"127.0.0.1/32\"/>\n    </list>\n  </network-lists>#" \
    /etc/freeswitch/autoload_configs/acl.conf.xml
fi

echo "== Clave de las extensiones 1000-1019"
sed -i "s#default_password=[^\"]*#default_password=$CLAVE_EXT#" /etc/freeswitch/vars.xml

echo "== Carpeta de audio del agente"
mkdir -p /var/lib/cobros_audio
chown freeswitch:freeswitch /var/lib/cobros_audio
chmod 2775 /var/lib/cobros_audio
usermod -aG freeswitch "$USUARIO"

systemctl enable freeswitch
systemctl restart freeswitch
sleep 8

install -m 600 -o "$USUARIO" -g "$USUARIO" /dev/null "$CRED"
cat > "$CRED" <<EOF
FREESWITCH_ESL_PASSWORD=$CLAVE_ESL
CLAVE_EXTENSIONES=$CLAVE_EXT
EOF

echo
fs_cli -p "$CLAVE_ESL" -x "status" | head -3 || true
echo
echo "============================================================"
echo " FreeSWITCH instalado."
echo " Zoiper:  usuario 1000   dominio $(hostname -I | awk '{print $1}')   contraseña $CLAVE_EXT"
echo " (Las claves quedaron en $CRED, solo legible por $USUARIO.)"
echo "============================================================"
