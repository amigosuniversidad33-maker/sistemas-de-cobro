#!/bin/bash
# El Event Socket acepta solo equipos de la MISMA red local de la VM (lista localnet.auto de FreeSWITCH), además de la
# clave larga. Así no hay que editarlo cada vez que la computadora cambia de red (casa, universidad).
# Uso (en la VM):  sudo bash esl_red_local.sh
set -euo pipefail
CONF=/etc/freeswitch/autoload_configs/event_socket.conf.xml
sed -i 's#name="apply-inbound-acl" value="[^"]*"#name="apply-inbound-acl" value="localnet.auto"#' "$CONF"
systemctl restart freeswitch
sleep 6
grep apply-inbound-acl "$CONF"
echo ESL_ACTUALIZADO
