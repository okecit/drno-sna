<?php
// Gerbang data: CSV/manifest hanya dikirim ke pengguna yang sudah masuk.
require __DIR__ . '/inc/auth.php';
drno_require_login(true);
$f = (string) ($_GET['f'] ?? '');
if (!preg_match('/^[a-z0-9_]+\.(csv|json)$/', $f) || preg_match('/^(posts_|manual_review)/', $f)) { http_response_code(400); exit; }
$path = DRNO_ROOT . '/data/' . $f;
if (!is_file($path)) { http_response_code(404); exit; }
drno_headers();
header('Content-Type: ' . (substr($f, -4) === 'json' ? 'application/json' : 'text/csv') . '; charset=utf-8');
header('Content-Length: ' . filesize($path));
readfile($path);
