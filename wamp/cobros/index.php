<?php
/*
 * Acceso de un clic al Sistema Outbound de Cobros con IA:  http://localhost/cobros/
 * Funciona con WAMP (Windows) y con MAMP o Apache de Homebrew (Mac).
 * Si el sistema ya está en ejecución, redirige a http://127.0.0.1:8000.
 * Si no, lo inicia en segundo plano (backend/arranque.py) y muestra el progreso.
 * Solo responde a solicitudes desde este mismo equipo. No recibe parámetros que se usen en comandos.
 */
declare(strict_types=1);

$RAIZ = '__RAIZ_PROYECTO__';
$ES_WINDOWS = DIRECTORY_SEPARATOR === '\\';
if (strpos($RAIZ, '__') === 0) {   // valor por defecto si se copió a mano
    $RAIZ = $ES_WINDOWS ? 'C:/sistema-cobros' : ((getenv('HOME') ?: ('/Users/' . get_current_user())) . '/sistema-cobros');
}
$BACK = $RAIZ . '/backend';
$URL_SISTEMA = 'http://127.0.0.1:8000/';

if (!in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1'], true)) {
    http_response_code(403);
    exit('Acceso permitido solo desde este equipo.');
}
header('Cache-Control: no-store');
header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; img-src data:");
header('X-Frame-Options: DENY');

function e(string $t): string { return htmlspecialchars($t, ENT_QUOTES, 'UTF-8'); }

function sistema_activo(): bool {
    $ctx = stream_context_create(['http' => ['timeout' => 2, 'ignore_errors' => true]]);
    $r = @file_get_contents('http://127.0.0.1:8000/api/salud', false, $ctx);
    return $r !== false && strpos($r, '"ok"') !== false;
}

function buscar_python(string $back, bool $win): ?string {
    if ($win) {
        $venv = $back . '/.venv/Scripts/python.exe';
        $patrones = [
            'C:/Users/*/AppData/Local/Programs/Python/Python3*/python.exe',
            'C:/Program Files/Python3*/python.exe',
            'C:/Python3*/python.exe',
        ];
    } else {
        // Mac: instalador de python.org o Homebrew (el python3 de Apple es 3.9 y no sirve: se requiere 3.11+)
        $venv = $back . '/.venv/bin/python';
        $patrones = [
            '/Library/Frameworks/Python.framework/Versions/3.1[1-9]/bin/python3',
            '/opt/homebrew/bin/python3.1[1-9]',
            '/usr/local/bin/python3.1[1-9]',
        ];
    }
    if (is_file($venv)) { return $venv; }
    $hallados = [];
    foreach ($patrones as $p) { foreach (glob($p) ?: [] as $f) { $hallados[] = $f; } }
    rsort($hallados, SORT_NATURAL);   // la versión más reciente primero
    return $hallados[0] ?? null;
}

function lanzar(string $python, string $script, bool $win): void {
    if ($win) {
        $cmd = 'start "" /B "' . str_replace('/', '\\', $python) . '" "' . str_replace('/', '\\', $script) . '" --fondo';
        pclose(popen($cmd, 'r'));
        return;
    }
    // Mac: proceso independiente de Apache, sin salida
    $cmd = 'nohup ' . escapeshellarg($python) . ' ' . escapeshellarg($script) . ' --fondo > /dev/null 2>&1 &';
    exec($cmd);
}

$estadoArchivo = $BACK . '/datos/arranque.json';
$bloqueo = $BACK . '/datos/arranque.lock';
$primerAcceso = $BACK . '/datos/primer_acceso.txt';
$estado = is_file($estadoArchivo) ? (json_decode((string)file_get_contents($estadoArchivo), true) ?: []) : [];
$activo = sistema_activo();

// Credenciales del primer acceso: se muestran una sola vez y se eliminan
$credenciales = null;
if ($activo && is_file($primerAcceso)) {
    $credenciales = (string)file_get_contents($primerAcceso);
    @unlink($primerAcceso);
}

if ($activo && $credenciales === null) {
    header('Location: ' . $URL_SISTEMA);
    exit;
}

$error = null;
if (!$activo) {
    if (!is_file($BACK . '/arranque.py')) {
        $error = 'No se encontró el proyecto en ' . $RAIZ . '. Descomprima el ZIP en esa carpeta o ejecute ' . ($ES_WINDOWS ? 'INICIAR.bat' : 'INICIAR.command') . '.';
    } else {
        $enCurso = is_file($bloqueo) && (time() - filemtime($bloqueo) < 900);
        $huboError = ($estado['nivel'] ?? '') === 'error';
        $reintentar = isset($_GET['reintentar']);
        if (!$enCurso && (!$huboError || $reintentar)) {
            $python = buscar_python($BACK, $ES_WINDOWS);
            if ($python === null) {
                $error = $ES_WINDOWS
                    ? 'No se encontró Python. Instale Python 3.13 desde python.org (marque "Add python.exe to PATH") y vuelva a abrir este enlace.'
                    : 'No se encontró Python 3.11 o superior. Instale Python 3.13 desde python.org (instalador para macOS) y vuelva a abrir este enlace.';
            } else {
                lanzar($python, $BACK . '/arranque.py', $ES_WINDOWS);
                $estado = ['nivel' => 'progreso', 'mensaje' => 'Iniciando el sistema...'];
                usleep(800000);
            }
        } elseif ($huboError && !$reintentar) {
            $error = (string)($estado['mensaje'] ?? 'Error desconocido.');
        }
    }
}
$refrescar = !$activo && $error === null;
?><!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<?php if ($refrescar): ?><meta http-equiv="refresh" content="3"><?php endif; ?>
<title>Cobros IA · Inicio</title>
<style>
  :root { --azul: #1d5bd6; --marino: #071a3d; --fondo: #f3f7fd; --texto: #0f1d36; --tenue: #4a5b78; --rojo: #c62f3b; --verde: #0f8a5f; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: "Segoe UI", -apple-system, system-ui, sans-serif;
         background: linear-gradient(160deg, #10337a, var(--marino)); color: var(--texto); padding: 16px; }
  .panel { background: #fff; border-radius: 14px; padding: 32px; width: min(560px, 100%); box-shadow: 0 20px 60px rgba(0,0,0,.35); }
  h1 { margin: 0 0 4px; font-size: 22px; color: #0b2559; }
  p { color: var(--tenue); line-height: 1.5; }
  .estado { display: flex; gap: 12px; align-items: center; background: #f2f7ff; border: 1px solid #c7dafc; border-radius: 10px; padding: 14px; color: #0b2559; }
  .giro { width: 22px; height: 22px; border: 3px solid #c7dafc; border-top-color: var(--azul); border-radius: 50%; animation: g .8s linear infinite; flex: none; }
  @keyframes g { to { transform: rotate(360deg); } }
  .error { background: #fde8ea; border-color: #f5b8bf; color: #8a1c26; }
  .cred { background: #e3f6ee; border: 1px solid #9fd8bf; border-radius: 10px; padding: 14px; font-family: Consolas, Menlo, monospace; white-space: pre-wrap; color: #0b3d2a; font-size: 16px; }
  a.btn { display: inline-block; margin-top: 16px; background: var(--azul); color: #fff; text-decoration: none; padding: 10px 18px; border-radius: 8px; font-weight: 600; }
  small { color: var(--tenue); }
</style>
</head>
<body>
<main class="panel">
  <h1>Sistema Outbound de Cobros con IA</h1>
  <p>Arranque local en <strong>http://127.0.0.1:8000</strong></p>
<?php if ($credenciales !== null): ?>
  <p><strong>Primer acceso.</strong> Anote estas credenciales: se muestran solo esta vez.</p>
  <div class="cred"><?= e($credenciales) ?></div>
  <a class="btn" href="<?= e($URL_SISTEMA) ?>">Entrar al sistema</a>
<?php elseif ($error !== null): ?>
  <div class="estado error"><?= e($error) ?></div>
  <a class="btn" href="?reintentar=1">Reintentar</a>
  <p><small>Detalle en <?= e($BACK) ?>/datos/logs. También puede iniciar con doble clic en <?= $ES_WINDOWS ? 'INICIAR.bat' : 'INICIAR.command' ?>.</small></p>
<?php else: ?>
  <div class="estado"><span class="giro"></span><span><?= e((string)($estado['mensaje'] ?? 'Iniciando...')) ?></span></div>
  <p><small>La primera vez se instalan las dependencias (2 a 5 minutos, requiere Internet). Esta página se actualiza sola.</small></p>
<?php endif; ?>
</main>
</body>
</html>
