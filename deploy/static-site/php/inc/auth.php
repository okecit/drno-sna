<?php
// DRNO — inti autentikasi berbasis sesi PHP. Kompatibel PHP 7.4 – 8.x (cPanel).
if (basename($_SERVER['SCRIPT_FILENAME'] ?? '') === 'auth.php') { http_response_code(403); exit; }

define('DRNO_ROOT', dirname(__DIR__));
define('DRNO_PRIVATE', DRNO_ROOT . '/private');
define('DRNO_USERS', DRNO_PRIVATE . '/users.php');
define('DRNO_IDLE_MIN', 60);         // keluar otomatis setelah 60 menit tanpa aktivitas
define('DRNO_ABS_HOURS', 12);        // sesi maksimal 12 jam
define('DRNO_MAX_FAIL', 5);          // percobaan gagal sebelum dikunci
define('DRNO_LOCK_MIN', 15);         // lama penguncian

function drno_https() {
  return (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
}

function drno_session() {
  if (session_status() === PHP_SESSION_ACTIVE) return;
  session_name('DRNOSESS');
  session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'secure' => drno_https(), 'httponly' => true, 'samesite' => 'Strict']);
  ini_set('session.use_strict_mode', '1');
  session_start();
}

function drno_headers() {
  header('X-Frame-Options: SAMEORIGIN');
  header('X-Content-Type-Options: nosniff');
  header('Referrer-Policy: no-referrer');
  header('X-Robots-Tag: noindex, nofollow');
  header('Cache-Control: no-store');
}

// Disimpan sebagai JSON di dalam berkas .php yang berhenti di baris pertama: aman walau .htaccess tidak
// berlaku (dibuka dari browser hanya menghasilkan 403), dan dibaca dengan file_get_contents (bukan include)
// sehingga tidak terkena cache OPcache saat akun baru ditambahkan.
define('DRNO_USERS_GUARD', "<?php http_response_code(403); exit; ?>\n");
function drno_users() {
  if (!is_file(DRNO_USERS)) return [];
  clearstatcache(true, DRNO_USERS);
  $raw = (string) file_get_contents(DRNO_USERS);
  $json = substr($raw, strpos($raw, "\n") + 1);
  $u = json_decode($json, true);
  return is_array($u) ? $u : [];
}

function drno_save_users(array $users) {
  if (!is_dir(DRNO_PRIVATE)) mkdir(DRNO_PRIVATE, 0750, true);
  $php = DRNO_USERS_GUARD . json_encode($users, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
  $tmp = DRNO_USERS . '.tmp';
  file_put_contents($tmp, $php, LOCK_EX);
  @chmod($tmp, 0640);
  rename($tmp, DRNO_USERS);
}

function drno_log($event, $user = '') {
  $ip = $_SERVER['REMOTE_ADDR'] ?? '-';
  $line = sprintf("%s\t%s\t%s\t%s\n", gmdate('c'), $ip, $event, preg_replace('/[^\w.@-]/', '', $user));
  @file_put_contents(DRNO_PRIVATE . '/access_log.tsv', $line, FILE_APPEND | LOCK_EX);
}

// Pembatasan percobaan login per IP (berbasis berkas, tanpa database)
function drno_lock_file() { return DRNO_PRIVATE . '/lock_' . hash('sha256', $_SERVER['REMOTE_ADDR'] ?? '-') . '.json'; }
function drno_locked_for() {
  $f = drno_lock_file();
  if (!is_file($f)) return 0;
  $d = json_decode((string) file_get_contents($f), true) ?: [];
  if (($d['n'] ?? 0) >= DRNO_MAX_FAIL) {
    $left = ($d['t'] ?? 0) + DRNO_LOCK_MIN * 60 - time();
    if ($left > 0) return $left;
    @unlink($f);
  }
  return 0;
}
function drno_fail() {
  $f = drno_lock_file();
  $d = is_file($f) ? (json_decode((string) file_get_contents($f), true) ?: []) : [];
  $d['n'] = ($d['n'] ?? 0) + 1; $d['t'] = time();
  @file_put_contents($f, json_encode($d), LOCK_EX);
}
function drno_clear_fail() { @unlink(drno_lock_file()); }

function drno_csrf() {
  drno_session();
  if (empty($_SESSION['csrf'])) $_SESSION['csrf'] = bin2hex(random_bytes(32));
  return $_SESSION['csrf'];
}
function drno_check_csrf($t) { return is_string($t) && !empty($_SESSION['csrf']) && hash_equals($_SESSION['csrf'], $t); }

function drno_current_user() {
  drno_session();
  if (empty($_SESSION['user'])) return null;
  $now = time();
  if ($now - ($_SESSION['last'] ?? 0) > DRNO_IDLE_MIN * 60 || $now - ($_SESSION['since'] ?? 0) > DRNO_ABS_HOURS * 3600) {
    drno_logout(); return null;
  }
  $users = drno_users();
  if (!isset($users[$_SESSION['user']]) || !empty($users[$_SESSION['user']]['disabled'])) { drno_logout(); return null; }
  $_SESSION['last'] = $now;
  return $_SESSION['user'];
}

function drno_require_login($json = false) {
  $u = drno_current_user();
  if ($u) return $u;
  if ($json) { http_response_code(401); header('Content-Type: application/json'); echo '{"error":"login"}'; exit; }
  header('Location: login.php'); exit;
}

function drno_login($user, $pass) {
  $users = drno_users();
  $ok = isset($users[$user]) && empty($users[$user]['disabled']) && password_verify($pass, $users[$user]['hash']);
  if (!$ok) { password_verify($pass, '$2y$10$zkuj6hfffB2RktkuOSWRn.wR.zR/eaetN.XnLtoUhuRBvF91K89Cm'); return false; } // waktu respons seragam
  if (password_needs_rehash($users[$user]['hash'], PASSWORD_DEFAULT)) { $users[$user]['hash'] = password_hash($pass, PASSWORD_DEFAULT); drno_save_users($users); }
  session_regenerate_id(true);
  $_SESSION['user'] = $user; $_SESSION['since'] = time(); $_SESSION['last'] = time();
  return true;
}

function drno_logout() {
  drno_session();
  $_SESSION = [];
  if (ini_get('session.use_cookies')) { $p = session_get_cookie_params(); setcookie(session_name(), '', time() - 42000, $p['path'], $p['domain'] ?? '', $p['secure'], $p['httponly']); }
  session_destroy();
}

function e($s) { return htmlspecialchars((string) $s, ENT_QUOTES, 'UTF-8'); }

function drno_page($title, $body) {
  drno_headers();
  header('Content-Type: text/html; charset=utf-8');
  echo '<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex, nofollow"><link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22%3E%3Ctext y=%22.9em%22 font-size=%2290%22%3E%F0%9F%95%B8%EF%B8%8F%3C/text%3E%3C/svg%3E"><title>' . e($title) . ' · DRNO</title><link rel="stylesheet" href="assets/drno-theme.css"><link rel="stylesheet" href="assets/login.css"></head><body><main class="lg"><div class="lg-card"><div class="lg-brand">DRNO</div><div class="lg-sub">Digital Radicalization Network Observatory</div>' . $body . '<p class="lg-foot">Akses terbatas untuk peneliti terdaftar. Aktivitas masuk dicatat.</p></div></main></body></html>';
}
