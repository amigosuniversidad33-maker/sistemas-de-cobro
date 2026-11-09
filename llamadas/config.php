<?php
// ===== CONFIGURACIÓN DEL MÓDULO DE LLAMADAS =====
// 1) Cree una cuenta gratis en https://www.twilio.com/try-twilio
// 2) En el Console copie el Account SID y el Auth Token
// 3) Compre/obtenga un número Twilio con capacidad de Voz (la cuenta de prueba trae saldo)

define('TWILIO_SID',   'ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'); // Account SID
define('TWILIO_TOKEN', 'su_auth_token_aqui');                 // Auth Token
define('TWILIO_FROM',  '+1xxxxxxxxxx');                       // Su número Twilio (formato E.164)

// Base de datos (WAMP por defecto: usuario root sin contraseña)
define('DB_HOST', 'localhost');
define('DB_NAME', 'cobros');
define('DB_USER', 'root');
define('DB_PASS', '');

function db() {
    static $pdo = null;
    if ($pdo === null) {
        $pdo = new PDO('mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4', DB_USER, DB_PASS, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
    }
    return $pdo;
}

// Llamada genérica a la API REST de Twilio (sin Composer, solo cURL)
function twilio($method, $path, $data = []) {
    $url = 'https://api.twilio.com/2010-04-01/Accounts/' . TWILIO_SID . $path;
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_USERPWD        => TWILIO_SID . ':' . TWILIO_TOKEN,
        CURLOPT_TIMEOUT        => 30,
    ]);
    if ($method === 'POST') {
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($data));
    }
    $resp = curl_exec($ch);
    $err  = curl_error($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    if ($resp === false) return ['ok' => false, 'error' => 'cURL: ' . $err];
    $json = json_decode($resp, true);
    if ($code >= 400) return ['ok' => false, 'error' => $json['message'] ?? $resp];
    return ['ok' => true, 'data' => $json];
}

function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
