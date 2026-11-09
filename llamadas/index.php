<?php
require __DIR__ . '/config.php';

$msg = ''; $tipo = 'ok';

function normalizar($tel) {
    $tel = preg_replace('/[^\d+]/', '', $tel);
    if (preg_match('/^\d{8}$/', $tel)) $tel = '+502' . $tel; // número de Guatemala sin código
    if ($tel !== '' && $tel[0] !== '+') $tel = '+' . $tel;
    return $tel;
}

try {
    $accion = $_POST['accion'] ?? '';

    if ($accion === 'agregar') {
        $nombre = trim($_POST['nombre'] ?? '');
        $tel    = normalizar($_POST['telefono'] ?? '');
        $monto  = (float)($_POST['monto'] ?? 0);
        if ($nombre === '' || !preg_match('/^\+\d{8,15}$/', $tel)) {
            $msg = 'Escriba un nombre y un teléfono válido (ej. 55551234 o +50255551234).'; $tipo = 'err';
        } else {
            db()->prepare('INSERT INTO telefonos (nombre, telefono, monto) VALUES (?,?,?)')->execute([$nombre, $tel, $monto]);
            $msg = "Número $tel agregado.";
        }
    }

    if ($accion === 'eliminar') {
        db()->prepare('DELETE FROM telefonos WHERE id=?')->execute([(int)$_POST['id']]);
        $msg = 'Número eliminado.';
    }

    if ($accion === 'llamar') {
        $st = db()->prepare('SELECT * FROM telefonos WHERE id=?');
        $st->execute([(int)$_POST['id']]);
        $c = $st->fetch();
        if ($c) {
            $texto = 'Buen día ' . $c['nombre'] . '. Le llamamos del departamento de cobros. '
                   . 'Su saldo pendiente es de ' . number_format($c['monto'], 2) . ' quetzales. '
                   . 'Si desea realizar su pago, marque el número uno. Para hablar con un asesor, marque el número dos.';
            $twiml = '<Response>'
                   . '<Gather numDigits="1" timeout="6">'
                   . '<Say language="es-MX" voice="Polly.Mia">' . h($texto) . '</Say>'
                   . '</Gather>'
                   . '<Say language="es-MX" voice="Polly.Mia">Gracias por su atención. Que tenga buen día.</Say>'
                   . '</Response>';

            $r = twilio('POST', '/Calls.json', [
                'To'    => $c['telefono'],
                'From'  => TWILIO_FROM,
                'Twiml' => $twiml,   // TwiML en línea: no necesita URL pública, funciona desde localhost
            ]);

            $ins = db()->prepare('INSERT INTO llamadas (telefono_id, call_sid, estado, error) VALUES (?,?,?,?)');
            if ($r['ok']) {
                $ins->execute([$c['id'], $r['data']['sid'], $r['data']['status'], null]);
                $msg = 'Llamando a ' . $c['telefono'] . '… su teléfono debería sonar en unos segundos.';
            } else {
                $ins->execute([$c['id'], null, 'error', $r['error']]);
                $msg = 'Twilio rechazó la llamada: ' . $r['error']; $tipo = 'err';
            }
        }
    }

    if ($accion === 'actualizar') {
        foreach (db()->query("SELECT id, call_sid FROM llamadas WHERE call_sid IS NOT NULL AND estado NOT IN ('completed','failed','busy','no-answer','canceled')") as $l) {
            $r = twilio('GET', '/Calls/' . $l['call_sid'] . '.json');
            if ($r['ok']) {
                db()->prepare('UPDATE llamadas SET estado=?, duracion=? WHERE id=?')
                    ->execute([$r['data']['status'], (int)$r['data']['duration'], $l['id']]);
            }
        }
        $msg = 'Estados actualizados.';
    }

    $telefonos = db()->query('SELECT * FROM telefonos ORDER BY id DESC')->fetchAll();
    $historial = db()->query('SELECT l.*, t.nombre, t.telefono FROM llamadas l JOIN telefonos t ON t.id=l.telefono_id ORDER BY l.id DESC LIMIT 30')->fetchAll();
} catch (Throwable $e) {
    $msg = 'Error: ' . $e->getMessage() . ' — ¿ya ejecutó instalar.sql y revisó config.php?'; $tipo = 'err';
    $telefonos = $telefonos ?? []; $historial = $historial ?? [];
}

$estados = ['queued'=>'En cola','initiated'=>'Iniciada','ringing'=>'Timbrando','in-progress'=>'En curso',
            'completed'=>'Completada','busy'=>'Ocupado','no-answer'=>'No contestó','failed'=>'Falló',
            'canceled'=>'Cancelada','error'=>'Error'];
?>
<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Llamadas de cobro</title>
<style>
  :root { --bg:#f4f6f8; --card:#fff; --tx:#1d2733; --mut:#6b7785; --pri:#0f6b5c; --err:#b42318; --line:#e3e7ec; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:Segoe UI, Arial, sans-serif; background:var(--bg); color:var(--tx); }
  .wrap { max-width:960px; margin:0 auto; padding:24px 16px; }
  h1 { font-size:22px; margin:0 0 4px; } .sub { color:var(--mut); margin:0 0 20px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px; margin-bottom:18px; }
  h2 { font-size:16px; margin:0 0 12px; }
  form.add { display:grid; grid-template-columns:2fr 1.5fr 1fr auto; gap:10px; }
  input { padding:10px; border:1px solid var(--line); border-radius:6px; font-size:14px; width:100%; }
  button { padding:9px 14px; border:0; border-radius:6px; background:var(--pri); color:#fff; font-size:14px; cursor:pointer; }
  button.sec { background:#e8ecef; color:var(--tx); } button.del { background:transparent; color:var(--err); padding:6px 8px; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { text-align:left; padding:9px 8px; border-bottom:1px solid var(--line); }
  th { color:var(--mut); font-weight:600; font-size:12px; text-transform:uppercase; }
  .msg { padding:12px 14px; border-radius:8px; margin-bottom:16px; background:#e6f4f1; color:var(--pri); }
  .msg.err { background:#fdecea; color:var(--err); }
  .acc { display:flex; gap:4px; } .vacio { color:var(--mut); }
  @media (max-width:640px) { form.add { grid-template-columns:1fr; } table { font-size:13px; } }
</style>
</head>
<body>
<div class="wrap">
  <h1>Llamadas de cobro</h1>
  <p class="sub">Agregue sus números de teléfono y presione “Llamar” para hacer una llamada real.</p>

  <?php if ($msg): ?><div class="msg <?= $tipo === 'err' ? 'err' : '' ?>"><?= h($msg) ?></div><?php endif; ?>

  <div class="card">
    <h2>Agregar número</h2>
    <form class="add" method="post">
      <input type="hidden" name="accion" value="agregar">
      <input name="nombre" placeholder="Nombre" required>
      <input name="telefono" placeholder="Teléfono (ej. 55551234)" required>
      <input name="monto" type="number" step="0.01" min="0" placeholder="Saldo Q">
      <button>Agregar</button>
    </form>
  </div>

  <div class="card">
    <h2>Números registrados</h2>
    <?php if (!$telefonos): ?><p class="vacio">Aún no hay números.</p><?php else: ?>
    <table>
      <tr><th>Nombre</th><th>Teléfono</th><th>Saldo</th><th></th></tr>
      <?php foreach ($telefonos as $t): ?>
      <tr>
        <td><?= h($t['nombre']) ?></td><td><?= h($t['telefono']) ?></td><td>Q <?= number_format($t['monto'], 2) ?></td>
        <td class="acc">
          <form method="post"><input type="hidden" name="accion" value="llamar"><input type="hidden" name="id" value="<?= $t['id'] ?>"><button>📞 Llamar</button></form>
          <form method="post" onsubmit="return confirm('¿Eliminar este número?')"><input type="hidden" name="accion" value="eliminar"><input type="hidden" name="id" value="<?= $t['id'] ?>"><button class="del">Eliminar</button></form>
        </td>
      </tr>
      <?php endforeach; ?>
    </table>
    <?php endif; ?>
  </div>

  <div class="card">
    <h2 style="display:flex;justify-content:space-between;align-items:center">Historial de llamadas
      <form method="post"><input type="hidden" name="accion" value="actualizar"><button class="sec">Actualizar estados</button></form>
    </h2>
    <?php if (!$historial): ?><p class="vacio">Sin llamadas todavía.</p><?php else: ?>
    <table>
      <tr><th>Fecha</th><th>Nombre</th><th>Teléfono</th><th>Estado</th><th>Duración</th></tr>
      <?php foreach ($historial as $l): ?>
      <tr>
        <td><?= h($l['creado']) ?></td><td><?= h($l['nombre']) ?></td><td><?= h($l['telefono']) ?></td>
        <td title="<?= h($l['error']) ?>"><?= h($estados[$l['estado']] ?? $l['estado']) ?></td>
        <td><?= $l['duracion'] !== null ? (int)$l['duracion'] . ' s' : '—' ?></td>
      </tr>
      <?php endforeach; ?>
    </table>
    <?php endif; ?>
  </div>
</div>
</body>
</html>
