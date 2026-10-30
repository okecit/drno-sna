<?php
require __DIR__ . '/inc/auth.php';
drno_session();
if ($_SERVER['REQUEST_METHOD'] === 'POST' && drno_check_csrf($_POST['csrf'] ?? '')) {
  drno_log('logout', $_SESSION['user'] ?? '');
  drno_logout();
}
header('Location: login.php?out=1');
