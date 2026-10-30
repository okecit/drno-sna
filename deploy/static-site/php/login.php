<?php
require __DIR__ . '/inc/auth.php';
drno_session();
if (!drno_users()) { header('Location: setup.php'); exit; }
if (drno_current_user()) { header('Location: index.php'); exit; }
$err = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
  $user = strtolower(trim((string) ($_POST['username'] ?? '')));
  $pass = (string) ($_POST['password'] ?? '');
  $wait = drno_locked_for();
  if (!drno_check_csrf($_POST['csrf'] ?? '')) {
    $err = 'Sesi formulir kedaluwarsa. Silakan coba lagi.';
  } elseif ($wait > 0) {
    $err = 'Terlalu banyak percobaan. Coba lagi dalam ' . ceil($wait / 60) . ' menit.';
    drno_log('login_locked', $user);
  } elseif (drno_login($user, $pass)) {
    drno_clear_fail(); drno_log('login_ok', $user);
    header('Location: index.php'); exit;
  } else {
    drno_fail(); drno_log('login_fail', $user);
    $err = 'Nama pengguna atau kata sandi salah.';
  }
}
$msg = isset($_GET['out']) ? '<div class="lg-ok">Anda telah keluar.</div>' : (isset($_GET['idle']) ? '<div class="lg-ok">Sesi berakhir karena tidak aktif. Silakan masuk lagi.</div>' : '');
drno_page('Masuk', $msg . ($err ? '<div class="lg-err" role="alert">' . e($err) . '</div>' : '') . '
<form method="post" autocomplete="on">
  <input type="hidden" name="csrf" value="' . e(drno_csrf()) . '">
  <label>Nama pengguna<input name="username" autocomplete="username" required autofocus maxlength="64" value="' . e($_POST['username'] ?? '') . '"></label>
  <label>Kata sandi<input name="password" type="password" autocomplete="current-password" required maxlength="200"></label>
  <button type="submit">Masuk</button>
</form>');
