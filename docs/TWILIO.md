# Llamada real a su celular con Twilio (prueba)

Con esto el agente **llama de verdad a su teléfono** (el mismo número de su WhatsApp), habla con voz neuronal en español
y entiende lo que usted responde. No necesita FreeSWITCH, troncal SIP ni Deepgram.

> Una llamada *por WhatsApp* no se puede automatizar en este proyecto: Meta exige empresa verificada, permiso previo del
> usuario y un servidor de medios WebRTC. Por eso se usa una llamada telefónica normal a su número.

## 1. Cuenta de Twilio (gratis, unos 10 minutos)
1. Regístrese en **https://www.twilio.com/try-twilio** (la cuenta de prueba trae crédito gratuito).
2. En la consola, copie **Account SID** y **Auth Token** (sección *Account Info*).
3. Obtenga un número: *Phone Numbers › Manage › Buy a number* (con el crédito de prueba). Cópielo en formato `+1…`.
4. Verifique su celular: *Phone Numbers › Manage › Verified Caller IDs › Add* → escriba `+502` y sus 8 dígitos y confirme
   el código que le llega. **La cuenta de prueba solo puede llamar a números verificados.**
5. Habilite Guatemala: *Voice › Settings › Geo permissions* → marque **Guatemala**.

La cuenta de prueba reproduce un aviso corto de Twilio al inicio de cada llamada; después habla el agente.

## 2. URL pública con ngrok (para que Twilio hable con su computadora)
1. Descargue ngrok desde **https://ngrok.com/download** y cree una cuenta gratuita; ejecute una vez
   `ngrok config add-authtoken SU_TOKEN`.
2. Con el sistema iniciado, abra una terminal y ejecute:
   ```powershell
   ngrok http 8000
   ```
3. Deje esa ventana abierta durante la prueba. El sistema **detecta solo** la dirección `https://xxxx.ngrok-free.app`
   (consulta la API local de ngrok en `127.0.0.1:4040`), así que no hace falta copiarla ni reiniciar cuando cambia.
   Si usa otro túnel, escriba su dirección en `URL_PUBLICA`.

**Seguridad:** por esa dirección pública el sistema **solo** acepta los avisos de Twilio con firma válida. La interfaz, el
inicio de sesión y los datos siguen accesibles solo desde su computadora.

## 3. Configurar `backend\.env`
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=su_auth_token
TWILIO_NUMERO=+1xxxxxxxxxx
TWILIO_MOTOR_VOZ=deepgram
TWILIO_VOZ=Polly.Mia-Neural
URL_PUBLICA=
```
Guarde y reinicie (`DETENER.bat` y `INICIAR.bat`).

### Voz y velocidad del agente en la llamada
- `TWILIO_MOTOR_VOZ=deepgram` (recomendado): el agente habla por teléfono con **su misma voz Aura-2** (la elegida en
  Agentes IA), que suena más natural que la voz de Twilio. Requiere `DEEPGRAM_API_KEY` y consume créditos Deepgram. Cada
  audio se sirve por un enlace aleatorio de un solo turno que expira en 5 minutos. Si Deepgram falla, ese turno se dice
  con `TWILIO_VOZ` (queda el evento `TTS_RESPALDO` en la llamada).
- `TWILIO_MOTOR_VOZ=twilio`: usa siempre `TWILIO_VOZ` (sin costo Deepgram).
- **Velocidad**: se configura por agente (Agentes IA › Editar › *Velocidad de la voz*, o en Prueba de Llamada con el
  control deslizante y **Guardar en el agente**). 1.00 es normal; 0.85–0.95 suele sonar más pausado y natural por
  teléfono. Con Deepgram se envía el parámetro `speed`; si la cuenta no lo admite, la voz sale a 1.00×. Con la voz de
  Twilio se aplica con SSML `<prosody rate>`.

Voces disponibles en español (cambie `TWILIO_VOZ`): `Polly.Mia-Neural` (mujer, México), `Polly.Andres-Neural` (hombre,
México), `Polly.Lupe-Neural` (mujer, EE. UU.), `Polly.Pedro-Neural` (hombre, EE. UU.). Verifique el catálogo vigente en
la documentación de Twilio («Text-to-speech voices»).

## 4. Hacer la llamada
1. **Extensiones SIP › Números autorizados**: agregue su celular (8 dígitos).
2. **Prueba de Llamada**: elija el agente y busque un cliente de prueba.
3. En **Llamada real a su celular (Twilio)** escriba su número y pulse **Llamar ahora**.
4. Conteste. Para el recorrido completo diga: «Sí, soy yo», los **últimos 4 dígitos del documento** del cliente (los ve
   en Clientes y Deudas), «Puedo pagar 500 quetzales el viernes» y «Sí, lo confirmo».
5. La conversación aparece en pantalla mientras ocurre y queda en **Llamadas** como «TELEFONÍA REAL». La promesa queda en
   **Promesas de Pago**.

## Problemas frecuentes
| Mensaje | Solución |
|---|---|
| «Ese número no está autorizado» | Agréguelo en Extensiones SIP › Números autorizados |
| «Twilio rechazó la llamada (400): … unverified» | Verifique su número en Twilio (paso 1.4) |
| «… not authorized to call +502…» | Active Guatemala en Geo permissions (paso 1.5) |
| Suena pero el agente no habla | ngrok cerrado, o `URL_PUBLICA` escrita a mano y distinta a la de ngrok (déjela vacía) |
| «Firma de Twilio inválida» en los registros | `TWILIO_AUTH_TOKEN` o `URL_PUBLICA` no coinciden |

Costo: cada minuto de llamada a Guatemala consume crédito de prueba (consulte la tarifa vigente en Twilio).
