<?php
// Tinjauan kandidat Page Facebook publik bernada serupa (hasil `drno.sh discover-pages`).
// Semua pengguna masuk boleh membaca; hanya admin yang memutuskan. Page yang diterima ikut di-crawl
// (facebook_sc) pada siklus worker berikutnya. Setiap keputusan dicatat di access_log.
require __DIR__ . '/inc/auth.php';
$me = drno_require_login(true);
drno_headers();
header('Content-Type: application/json; charset=utf-8');
define('DRNO_PAGE_CAND', DRNO_PRIVATE . '/page_candidates.json');
define('DRNO_PAGE_REV', DRNO_PRIVATE . '/page_review.json');

function pr_decode($raw, $key) {
  $d = $raw ? json_decode($raw, true) : null;
  return (is_array($d) && isset($d[$key]) && is_array($d[$key])) ? $d : [$key => []];
}
function pr_out($rev, $admin) {
  $cand = pr_decode(@file_get_contents(DRNO_PAGE_CAND), 'candidates');
  echo json_encode(['can_review' => $admin, 'candidates' => $cand['candidates'], 'updated' => $cand['updated'] ?? null,
                    'min_followers' => $cand['min_followers'] ?? null, 'decisions' => $rev['decisions']], JSON_UNESCAPED_UNICODE);
}

$users = drno_users();
$admin = (($users[$me]['role'] ?? '') === 'admin');
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
if ($method === 'GET') { pr_out(pr_decode(@file_get_contents(DRNO_PAGE_REV), 'decisions'), $admin); exit; }
if ($method !== 'POST') { http_response_code(405); exit; }
if (!$admin) { http_response_code(403); echo '{"error":"Hanya admin yang dapat meninjau Page."}'; exit; }

$in = json_decode((string) file_get_contents('php://input'), true);
if (!is_array($in) || !drno_check_csrf($in['csrf'] ?? '')) { http_response_code(400); echo '{"error":"Sesi kedaluwarsa. Muat ulang halaman."}'; exit; }
$handle = trim((string) ($in['handle'] ?? ''));
$act = (string) ($in['action'] ?? '');
$note = mb_substr(trim((string) ($in['note'] ?? '')), 0, 200, 'UTF-8');
if (!preg_match('/^[A-Za-z0-9.\-_]{2,80}$/', $handle) || !in_array($act, ['accept', 'reject', 'undo'], true)) {
  http_response_code(400); echo '{"error":"Input tidak valid."}'; exit;
}

$fh = fopen(DRNO_PAGE_REV, 'c+');
if (!$fh || !flock($fh, LOCK_EX)) { http_response_code(500); echo '{"error":"Berkas tinjauan tidak dapat dikunci."}'; exit; }
$d = pr_decode(stream_get_contents($fh), 'decisions');
$d['decisions'] = array_values(array_filter($d['decisions'], function ($x) use ($handle) { return strcasecmp($x['handle'] ?? '', $handle) !== 0; }));
if ($act !== 'undo') {
  $d['decisions'][] = ['handle' => $handle, 'decision' => $act, 'reviewer' => $me, 'at' => gmdate('c'), 'note' => $note];
}
$d['updated'] = gmdate('c');
ftruncate($fh, 0); rewind($fh);
fwrite($fh, json_encode($d, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
fflush($fh); flock($fh, LOCK_UN); fclose($fh);
@chmod(DRNO_PAGE_REV, 0640);
drno_log('page_' . $act, $me);
pr_out($d, true);
