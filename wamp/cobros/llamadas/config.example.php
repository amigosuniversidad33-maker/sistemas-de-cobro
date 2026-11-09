<?php
// ===== CONFIGURACIÓN DEL MÓDULO DE LLAMADAS =====
// 1) Cree una cuenta gratis en https://www.twilio.com/try-twilio
// 2) En el Console copie el Account SID y el Auth Token
// 3) Compre/obtenga un número Twilio con capacidad de Voz (la cuenta de prueba trae saldo)

define('TWILIO_SID',   ''); // Account SID
define('TWILIO_TOKEN', '');                 // Auth Token
define('TWILIO_FROM',  '');                       // Su número Twilio (formato E.164)

// Base de datos (WAMP por defecto: usuario root sin contraseña)
define('DB_HOST', '127.0.0.1');
define('DB_PUERTOS', [3306, 3308, 3307, 8889]); // se prueba cada uno: WAMP (3306/3308), MySQL (3307), MAMP en Mac (8889)
define('DB_NAME', 'cobros_llamadas'); // base separada: no toca cobros_ia
define('DB_USER', 'root');
define('DB_CLAVES', ['', 'root']);   // WAMP: sin contraseña · MAMP: root

function db() {
    static $pdo = null;
    if ($pdo === null) {
        $ultimoError = null;
        foreach (DB_PUERTOS as $puerto) {
            foreach (DB_CLAVES as $clave) {
                try {
                    $pdo = new PDO('mysql:host=' . DB_HOST . ';port=' . $puerto . ';charset=utf8mb4', DB_USER, $clave, [
                        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                        PDO::ATTR_TIMEOUT => 2,
                    ]);
                    break 2;
                } catch (PDOException $e) { $ultimoError = $e; }
            }
        }
        if ($pdo === null) {
            throw new RuntimeException('No se encontró MySQL (puertos 3306/3308/3307/8889). Encienda WAMP o MAMP. ' . ($ultimoError ? $ultimoError->getMessage() : ''));
        }
        // Crea la base y las tablas solas la primera vez
        $pdo->exec('CREATE DATABASE IF NOT EXISTS `' . DB_NAME . '` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');
        $pdo->exec('USE `' . DB_NAME . '`');
        $pdo->exec("CREATE TABLE IF NOT EXISTS telefonos (
            id INT AUTO_INCREMENT PRIMARY KEY, nombre VARCHAR(120) NOT NULL, telefono VARCHAR(20) NOT NULL,
            monto DECIMAL(10,2) NOT NULL DEFAULT 0, creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        $pdo->exec("CREATE TABLE IF NOT EXISTS llamadas (
            id INT AUTO_INCREMENT PRIMARY KEY, telefono_id INT NOT NULL, call_sid VARCHAR(64), estado VARCHAR(30),
            duracion INT DEFAULT NULL, error TEXT, creado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (telefono_id) REFERENCES telefonos(id) ON DELETE CASCADE)");
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

function twilio_configurado() {
    return strpos(TWILIO_SID, 'xxxx') === false && TWILIO_TOKEN !== 'REEMPLAZAR' && strpos(TWILIO_FROM, 'xxxx') === false;
}

function h($s) { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
