<?php
// Pembuatan akun admin PERTAMA. Hanya berfungsi selama belum ada pengguna; setelah itu terkunci permanen.
require __DIR__ . '/inc/auth.php';
drno_session();
if (drno_users()) { http_response_code(403); drno_page('Setup', '<div class="lg-err">Setup sudah selesai. Halaman ini dinonaktifkan.</div><p><a href="login.php">Ke halaman masuk</a></p>'); exit; }
$err = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
  $u = strtolower(trim((string) ($_POST['username'] ?? '')));
  $p = (string) ($_POST['password'] ?? '');
  $setupKey = (string) ($_POST['setup_key'] ?? '');
  $expected = is_file(DRNO_PRIVATE . '/setup_key.txt') ? trim((string) file_get_contents(DRNO_PRIVATE . '/setup_key.txt')) : '';
  if (!drno_check_csrf($_POST['csrf'] ?? '')) $err = 'Sesi formulir kedaluwarsa.';
  elseif ($expected === '' || !hash_equals($expected, $setupKey)) $err = 'Kode setup salah. Lihat berkas private/setup_key.txt melalui File Manager.';
  elseif (!preg_match('/^[a-z0-9._-]{3,32}$/', $u)) $err = 'Nama pengguna 3–32 karakter: huruf kecil, angka, titik, minus, garis bawah.';
  elseif (strlen($p) < 12) $err = 'Kata sandi minimal 12 karakter.';
  elseif ($p !== ($_POST['password2'] ?? '')) $err = 'Konfirmasi kata sandi tidak sama.';
  else {
    drno_save_users([$u => ['hash' => password_hash($p, PASSWORD_DEFAULT), 'role' => 'admin', 'created' => gmdate('c')]]);
    @unlink(DRNO_PRIVATE . '/setup_key.txt');
    drno_log('setup_admin', $u);
    header('Location: login.php'); exit;
  }
}
drno_page('Setup awal', '<h1 class="lg-h">Buat akun admin pertama</h1><p class="lg-note">Kode setup ada di berkas <code>private/setup_key.txt</code> (buka lewat File Manager hosting). Halaman ini otomatis terkunci setelah admin dibuat.</p>'
 . ($err ? '<div class="lg-err" role="alert">' . e($err) . '</div>' : '') . '
<form method="post"><input type="hidden" name="csrf" value="' . e(drno_csrf()) . '">
<label>Kode setup<input name="setup_key" required autocomplete="off"></label>
<label>Nama pengguna admin<input name="username" required autocomplete="username" value="' . e($_POST['username'] ?? '') . '"></label>
<label>Kata sandi (min. 12 karakter)<input name="password" type="password" required autocomplete="new-password"></label>
<label>Ulangi kata sandi<input name="password2" type="password" required autocomplete="new-password"></label>
<button type="submit">Buat admin</button></form>');
