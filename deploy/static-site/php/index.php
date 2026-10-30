<?php
require __DIR__ . '/inc/auth.php';
drno_session();
if (!drno_users()) { header('Location: setup.php'); exit; }
$had = !empty($_SESSION['user']);
$user = drno_current_user();
if (!$user) { header('Location: login.php' . ($had ? '?idle=1' : '')); exit; }
drno_headers();
header('Content-Type: text/html; charset=utf-8');
header("Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'self'");
$users = drno_users();
$bar = '<div class="drno-userbar"><span>Masuk sebagai <b>' . e($user) . '</b>' . (($users[$user]['role'] ?? '') === 'admin' ? ' · <a href="users.php">Kelola pengguna</a>' : '') . '</span>'
  . '<form method="post" action="logout.php"><input type="hidden" name="csrf" value="' . e(drno_csrf()) . '"><button type="submit">Keluar</button></form></div>';
$html = file_get_contents(DRNO_PRIVATE . '/app.html');
echo str_replace('<!--DRNO_USERBAR-->', $bar, $html);
