<?php
// Kelola pengguna (khusus admin): tambah peneliti, ganti kata sandi, nonaktifkan, hapus.
require __DIR__ . '/inc/auth.php';
$me = drno_require_login();
$users = drno_users();
if (($users[$me]['role'] ?? '') !== 'admin') { http_response_code(403); drno_page('Ditolak', '<div class="lg-err">Hanya admin.</div><p><a href="index.php">Kembali</a></p>'); exit; }
$msg = ''; $err = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
  if (!drno_check_csrf($_POST['csrf'] ?? '')) { $err = 'Sesi formulir kedaluwarsa.'; }
  else {
    $act = $_POST['act'] ?? ''; $u = strtolower(trim((string) ($_POST['username'] ?? ''))); $p = (string) ($_POST['password'] ?? '');
    if ($act === 'add' || $act === 'reset') {
      if (!preg_match('/^[a-z0-9._-]{3,32}$/', $u)) $err = 'Nama pengguna tidak valid.';
      elseif (strlen($p) < 12) $err = 'Kata sandi minimal 12 karakter.';
      elseif ($act === 'add' && isset($users[$u])) $err = 'Pengguna sudah ada.';
      elseif ($act === 'reset' && !isset($users[$u])) $err = 'Pengguna tidak ditemukan.';
      else {
        $role = $act === 'add' ? (($_POST['role'] ?? '') === 'admin' ? 'admin' : 'viewer') : $users[$u]['role'];
        $users[$u] = array_merge($users[$u] ?? ['created' => gmdate('c')], ['hash' => password_hash($p, PASSWORD_DEFAULT), 'role' => $role, 'disabled' => false]);
        drno_save_users($users); drno_log($act === 'add' ? 'user_add' : 'user_reset', $u); $msg = $act === 'add' ? "Pengguna $u ditambahkan." : "Kata sandi $u diganti.";
      }
    } elseif (($act === 'toggle' || $act === 'delete') && isset($users[$u])) {
      if ($u === $me) $err = 'Tidak bisa menonaktifkan/menghapus akun sendiri.';
      else {
        if ($act === 'toggle') $users[$u]['disabled'] = empty($users[$u]['disabled']); else unset($users[$u]);
        drno_save_users($users); drno_log('user_' . $act, $u); $msg = 'Perubahan disimpan.';
      }
    }
  }
}
$csrf = e(drno_csrf());
$rows = '';
foreach ($users as $name => $info) {
  $rows .= '<tr><td>' . e($name) . '</td><td>' . e($info['role'] ?? 'viewer') . '</td><td>' . (!empty($info['disabled']) ? 'nonaktif' : 'aktif') . '</td><td class="lg-act">'
    . ($name === $me ? '<span class="lg-note">(Anda)</span>' :
      '<form method="post"><input type="hidden" name="csrf" value="' . $csrf . '"><input type="hidden" name="act" value="toggle"><input type="hidden" name="username" value="' . e($name) . '"><button>' . (!empty($info['disabled']) ? 'Aktifkan' : 'Nonaktifkan') . '</button></form>'
      . '<form method="post" onsubmit="return confirm(\'Hapus pengguna ini?\')"><input type="hidden" name="csrf" value="' . $csrf . '"><input type="hidden" name="act" value="delete"><input type="hidden" name="username" value="' . e($name) . '"><button>Hapus</button></form>')
    . '</td></tr>';
}
drno_page('Kelola pengguna', '<h1 class="lg-h">Kelola pengguna</h1>' . ($msg ? '<div class="lg-ok">' . e($msg) . '</div>' : '') . ($err ? '<div class="lg-err">' . e($err) . '</div>' : '')
 . '<table class="lg-table"><thead><tr><th>Pengguna</th><th>Peran</th><th>Status</th><th></th></tr></thead><tbody>' . $rows . '</tbody></table>'
 . '<h2 class="lg-h2">Tambah pengguna</h2><form method="post"><input type="hidden" name="csrf" value="' . $csrf . '"><input type="hidden" name="act" value="add">
 <label>Nama pengguna<input name="username" required></label><label>Kata sandi awal (min. 12)<input name="password" type="password" required autocomplete="new-password"></label>
 <label>Peran<select name="role"><option value="viewer">viewer (lihat dashboard)</option><option value="admin">admin (kelola pengguna)</option></select></label><button>Tambah</button></form>'
 . '<h2 class="lg-h2">Ganti kata sandi</h2><form method="post"><input type="hidden" name="csrf" value="' . $csrf . '"><input type="hidden" name="act" value="reset">
 <label>Nama pengguna<input name="username" required></label><label>Kata sandi baru (min. 12)<input name="password" type="password" required autocomplete="new-password"></label><button>Simpan</button></form>
 <p><a href="index.php">← Kembali ke dashboard</a></p>');
