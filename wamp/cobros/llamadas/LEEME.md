# Módulo de llamadas reales — Sistema de Cobros

## Instalación (10 minutos)

1. **Copie la carpeta** `llamadas` dentro de su proyecto:
   `C:\wamp64\www\cobros\llamadas\`
2. **Cree las tablas:** abra http://localhost/phpmyadmin, entre a la pestaña *SQL*,
   pegue el contenido de `instalar.sql` y presione *Continuar*.
3. **Cree su cuenta Twilio** (gratis, trae saldo de prueba): https://www.twilio.com/try-twilio
   - En el Console copie **Account SID** y **Auth Token**.
   - Obtenga un número Twilio con Voz (*Phone Numbers → Buy a number*; con la cuenta de prueba no tiene costo).
4. **Verifique sus números** (obligatorio en cuenta de prueba): *Phone Numbers → Verified Caller IDs*
   → agregue el celular de cada integrante del equipo (+502…). Twilio les manda un código.
5. **Permita llamadas a Guatemala:** *Voice → Settings → Geo Permissions* → marque **Guatemala**.
6. **Edite `config.php`** con su SID, Token y número Twilio. Si su base no se llama `cobros`, cámbiela ahí.
7. **Active cURL en WAMP** si no lo está: clic en el ícono de WAMP → PHP → Extensiones PHP → `php_curl`.
8. Abra **http://localhost/cobros/llamadas/**, agregue un número y presione **📞 Llamar**.

## Qué escucha la persona

Una voz en español que dice su nombre y saldo pendiente, y le pide marcar 1 para pagar o 2 para hablar con un asesor.
El texto está en `index.php` (variable `$texto`) por si quiere cambiarlo.

## Si algo falla

El mensaje rojo arriba muestra el motivo exacto que devuelve Twilio. Los más comunes:
- *"The number is unverified"* → falta el paso 4.
- *"Permission to call... not enabled"* → falta el paso 5.
- *"Authenticate"* → SID o Token mal copiados en `config.php`.
- *"Call to undefined function curl_init"* → falta el paso 7.

## Enlazarlo desde su sistema
Agregue en su menú principal: `<a href="llamadas/">Llamadas</a>`
