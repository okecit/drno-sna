<?php
// Tinjauan usulan istilah tersembunyi: semua pengguna yang masuk boleh membaca, hanya admin yang boleh
// memutuskan. Keputusan disimpan di private/keyword_review.json dan dibaca worker pada siklus berikutnya
// (kamus versi baru + perluasan query crawl). Setiap keputusan dicatat di access_log.
require __DIR__ . '/inc/auth.php';
$me = drno_require_login(true);
drno_headers();
header('Content-Type: application/json; charset=utf-8');
define('DRNO_REVIEW', DRNO_PRIVATE . '/keyword_review.json');
$GROUPS = ['ideologis', 'jaringan_ekstrem', 'radikalisasi', 'terorisme', 'narasi_digital', 'politik_keagamaan', 'konflik', 'pencegahan', 'keagamaan'];

function review_decode($raw) {
  $d = $raw ? json_decode($raw, true) : null;
  return (is_array($d) && isset($d['decisions']) && is_array($d['decisions'])) ? $d : ['decisions' => []];
}
function review_out($d, $admin, $groups) {
  echo json_encode(['can_review' => $admin, 'groups' => $groups, 'decisions' => $d['decisions'], 'updated' => $d['updated'] ?? null], JSON_UNESCAPED_UNICODE);
}

$users = drno_users();
$admin = (($users[$me]['role'] ?? '') === 'admin');
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
if ($method === 'GET') { review_out(review_decode(@file_get_contents(DRNO_REVIEW)), $admin, $GROUPS); exit; }
if ($method !== 'POST') { http_response_code(405); exit; }
if (!$admin) { http_response_code(403); echo '{"error":"Hanya admin yang dapat meninjau istilah."}'; exit; }

$in = json_decode((string) file_get_contents('php://input'), true);
if (!is_array($in) || !drno_check_csrf($in['csrf'] ?? '')) { http_response_code(400); echo '{"error":"Sesi kedaluwarsa. Muat ulang halaman."}'; exit; }
$term = mb_strtolower(trim((string) ($in['term'] ?? '')), 'UTF-8');
$act = (string) ($in['action'] ?? '');
$group = (string) ($in['group'] ?? '');
$note = mb_substr(trim((string) ($in['note'] ?? '')), 0, 200, 'UTF-8');
if (!preg_match("/^[\\p{L}\\p{N}@$][\\p{L}\\p{N} '\\-@$]{1,59}$/u", $term) || !in_array($act, ['accept', 'reject', 'undo'], true)
    || ($act === 'accept' && !in_array($group, $GROUPS, true))) {
  http_response_code(400); echo '{"error":"Input tidak valid."}'; exit;
}

$fh = fopen(DRNO_REVIEW, 'c+');
if (!$fh || !flock($fh, LOCK_EX)) { http_response_code(500); echo '{"error":"Berkas tinjauan tidak dapat dikunci."}'; exit; }
$d = review_decode(stream_get_contents($fh));
$d['decisions'] = array_values(array_filter($d['decisions'], function ($x) use ($term) { return ($x['term'] ?? '') !== $term; }));
if ($act !== 'undo') {
  $d['decisions'][] = ['term' => $term, 'decision' => $act, 'group' => $act === 'accept' ? $group : null, 'reviewer' => $me, 'at' => gmdate('c'), 'note' => $note];
}
$d['updated'] = gmdate('c');
ftruncate($fh, 0); rewind($fh);
fwrite($fh, json_encode($d, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT));
fflush($fh); flock($fh, LOCK_UN); fclose($fh);
@chmod(DRNO_REVIEW, 0640);
drno_log('keyword_' . $act, $me);
review_out($d, true, $GROUPS);
