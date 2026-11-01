#!/usr/bin/env bash
# Perintah operasional DRNO di VPS:  ./deploy/vps/drno.sh <perintah>
#   check | up | down | ps | logs [svc] | setup-key | stats | scrape-test | scrape-now | run-now | discover-pages | backup | restore F | restore-users F | update | verify | up-api
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] || { echo "Belum ada .env - jalankan ./deploy/vps/init.sh"; exit 1; }
DC=(docker compose -f deploy/vps/docker-compose.prod.yml --env-file .env)
envget() { grep -E "^$1=" .env | tail -1 | cut -d= -f2-; }
case "${1:-help}" in
  check)
    ok=1
    for v in POSTGRES_PASSWORD DRNO_PSEUDONYM_KEY DRNO_DOMAIN; do [ -n "$(envget $v)" ] || { echo "✗ $v kosong"; ok=0; }; done
    k=$(envget DRNO_PSEUDONYM_KEY); [ "${#k}" -ge 32 ] || { echo "✗ DRNO_PSEUDONYM_KEY < 32 karakter"; ok=0; }
    for p in YOUTUBE:YOUTUBE_API_KEY X:X_BEARER_TOKEN FACEBOOK:META_ACCESS_TOKEN INSTAGRAM:META_ACCESS_TOKEN; do
      n=${p%%:*}; c=${p##*:}
      if [ -n "$(envget $c)" ] && [ -z "$(envget DRNO_LEGAL_BASIS_$n)" ]; then echo "✗ $c terisi tetapi DRNO_LEGAL_BASIS_$n kosong"; ok=0; fi
    done
    # Ikuti symlink rilis ke shared/.env; mode symlink sendiri lazimnya 777.
    [ "$(stat -Lc %a .env)" = "600" ] || echo "! izin .env bukan 600 (jalankan: chmod 600 .env)"
    d=$(envget DRNO_DOMAIN); ip=$(getent hosts "$d" | awk '{print $1}' | head -1 || true)
    me=$(curl -s --max-time 5 https://api.ipify.org || true)
    if [ -z "$ip" ]; then echo "! DNS $d belum terbaca"; elif [ -n "$me" ] && [ "$ip" != "$me" ]; then echo "! DNS $d -> $ip, tetapi IP VPS ini $me"; else echo "✓ DNS $d -> $ip"; fi
    [ $ok = 1 ] && echo "✓ konfigurasi siap" || exit 1 ;;
  up)         "$0" check && "${DC[@]}" up -d --build && "${DC[@]}" ps ;;
  up-api)     "${DC[@]}" --profile api up -d --build api ;;
  down)       "${DC[@]}" down ;;
  ps|status)  "${DC[@]}" ps ;;
  logs)       "${DC[@]}" logs -f --tail=200 "${2:-worker}" ;;
  setup-key)  "${DC[@]}" exec web cat /var/www/html/private/setup_key.txt 2>/dev/null || echo "Tidak ada kode setup (admin sudah dibuat)." ;;
  stats)      "${DC[@]}" exec worker python -m drno.maintenance stats ;;
  scrape-test) # uji sumber tanpa menyimpan: ./deploy/vps/drno.sh scrape-test
    "${DC[@]}" exec worker bash -c 'cd /app/backend && python -m drno.crawl web --from "$(date -d "-3 days" +%F)" --to "$(date +%F)" --max 10 --sources /app/config/sources.json --dry-run' ;;
  scrape-now)  # jalankan crawling web sekarang & simpan
    "${DC[@]}" exec worker bash -c 'cd /app/backend && python -m drno.crawl web --from "$(date -d "-2 days" +%F)" --to "$(date +%F)" --sources /app/config/sources.json && date +%s > /site/private/.last_scrape' ;;
  run-now)    "${DC[@]}" restart worker && echo "Worker dimulai ulang: siklus pembaruan berjalan sekarang." ;;
  discover-pages) # usulkan Page Facebook publik bernada serupa (ScrapeCreators, memakai kredit); tinjau di dashboard
    "${DC[@]}" exec worker bash -c 'cd /app/backend && DRNO_PAGE_CANDIDATES=/site/private/page_candidates.json DRNO_PAGE_REVIEW=/site/private/page_review.json python -m drno.maintenance discover-pages && chown 33:33 /site/private/page_candidates.json && chmod 640 /site/private/page_candidates.json' ;;
  backup)     mkdir -p backups && "${DC[@]}" exec backup bash /backup.sh now && ls -lh backups | tail -5 ;;
  restore)
    f=${2:?berikan berkas .dump}; read -rp "Timpa database dengan $f? ketik YA: " a; [ "$a" = "YA" ] || exit 1
    "${DC[@]}" stop worker
    "${DC[@]}" exec -T db pg_restore -U drno -d drno --clean --if-exists < "$f"
    "${DC[@]}" start worker ;;
  restore-users)
    f=${2:?berikan berkas .tgz}; "${DC[@]}" exec -T web bash -c 'tar xzf - -C /var/www/html && chown -R www-data:www-data /var/www/html/private' < "$f" ;;
  update)     "$0" backup || true; "${DC[@]}" up -d --build ;;
  verify)
    B="https://$(envget DRNO_DOMAIN)"
    chk() { c=$(curl -s -o /dev/null -w '%{http_code}' "$B$1"); [ "$c" = "$2" ] && echo "✓ $1 -> $c" || echo "✗ $1 -> $c (harap $2)"; }
    chk_any() { c=$(curl -s -o /dev/null -w '%{http_code}' "$B$1"); case " $2 " in *" $c "*) echo "✓ $1 -> $c";; *) echo "✗ $1 -> $c (harap salah satu: $2)";; esac; }
    # Sebelum admin pertama dibuat, login.php secara benar mengarah (302) ke setup.php.
    chk_any /login.php "200 302"; chk /data/overview.csv 403; chk "/data.php?f=overview.csv" 401; chk /review.php 401; chk /private/keyword_review.json 403; chk /page_review.php 401; chk /private/page_candidates.json 403
    chk /private/users.php 403; chk /inc/auth.php 403; chk /.env 403
    curl -sI "$B/login.php" | grep -qi strict-transport-security && echo "✓ HSTS aktif" || echo "✗ HSTS tidak ada"
    c=$(curl -s -o /dev/null -w '%{http_code}' "http://$(envget DRNO_DOMAIN)/login.php"); case $c in 301|308) echo "✓ HTTP dialihkan ke HTTPS";; *) echo "✗ HTTP -> $c";; esac ;;
  *) sed -n '2,3p' "$0" ;;
esac
