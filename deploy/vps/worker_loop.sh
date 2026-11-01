#!/usr/bin/env bash
# Worker produksi: crawl -> analisis -> rakit situs -> salin ke volume web, berkala.
# Tidak pernah menimpa akun/log di /site/private. Gagal satu siklus tidak menghentikan worker.
# Catatan: `set -e` tidak berlaku di fungsi yang dipanggil dalam if/&&/||, jadi setiap langkah
# kritis diperiksa eksplisit dengan `|| return 1`.
set -u
APP=${DRNO_APP_DIR:-/app}
SITE=${DRNO_SITE_DIR:-/site}
INTERVAL=${DRNO_INTERVAL_HOURS:-6}
WWW_UID=${DRNO_WWW_UID:-33}   # www-data pada image php:apache
# Keputusan tinjauan istilah ditulis dashboard (review.php) ke volume situs; dibaca kamus & crawl
export DRNO_KEYWORD_REVIEW=${DRNO_KEYWORD_REVIEW:-$SITE/private/keyword_review.json}
log() { echo "[$(date '+%F %T')] $*"; }

fix_site_permissions() {
  # Apache berjalan sebagai www-data (uid 33). Berkas publik boleh dibaca,
  # sedangkan akun, log, dan setup key tetap hanya untuk www-data.
  chmod 755 "$SITE" || return 1
  local item
  for item in index.php login.php logout.php data.php review.php setup.php users.php robots.txt .htaccess; do
    [ ! -e "$SITE/$item" ] || chmod 644 "$SITE/$item" || return 1
  done
  for item in assets inc data; do
    [ ! -d "$SITE/$item" ] || find "$SITE/$item" -type d -exec chmod 755 {} + || return 1
    [ ! -d "$SITE/$item" ] || find "$SITE/$item" -type f -exec chmod 644 {} + || return 1
  done
  if [ -d "$SITE/private" ]; then
    chown -R "$WWW_UID:$WWW_UID" "$SITE/private" || return 1
    find "$SITE/private" -type d -exec chmod 750 {} + || return 1
    find "$SITE/private" -type f -exec chmod 640 {} + || return 1
  fi
}

sync_site() {
  local src=$1
  # Jangan pernah menayangkan paket rusak: wajib ada manifest dengan dataset
  python3 -c "import json,sys; m=json.load(open('$src/data/manifest.json')); sys.exit(0 if m['datasets'] else 1)" 2>/dev/null \
    || { log "paket situs tidak valid (manifest kosong) - dibatalkan"; return 1; }
  mkdir -p "$SITE/private" "$SITE/data" || return 1
  local item
  for item in index.php login.php logout.php data.php review.php setup.php users.php robots.txt .htaccess assets inc; do
    rm -rf "$SITE/$item.new" && cp -r "$src/$item" "$SITE/$item.new" && rm -rf "$SITE/$item" && mv "$SITE/$item.new" "$SITE/$item" || return 1
  done
  cp "$src/private/app.html" "$src/private/.htaccess" "$SITE/private/" || return 1
  [ -f "$SITE/private/users.php" ] || cp "$src/private/setup_key.txt" "$SITE/private/setup_key.txt"
  cp "$src"/data/*.csv "$src/data/.htaccess" "$SITE/data/" || return 1
  cp "$src/data/manifest.json" "$SITE/data/manifest.json.new" && mv "$SITE/data/manifest.json.new" "$SITE/data/manifest.json" || return 1
  fix_site_permissions
}

run_cycle() {
  cd "$APP/backend" || return 1
  local FROM TO Q
  FROM=$(date -d "-7 days" +%F); TO=$(date +%F)
  # Satu sumber kebenaran: default_query() di drno/keywords.py (v1.1 + istilah yang diterima lewat tinjauan dashboard)
  Q=${DRNO_QUERY:-$(python -c 'from drno.keywords import default_query; print(default_query())')}
  # YouTube tidak memahami AND/OR/NOT: pakai sintaks aslinya (| = OR, - = NOT)
  local YQ=${DRNO_YT_QUERY:-'radikalisasi|terorisme|ekstremisme|deradikalisasi|"kontra narasi" -lowongan'}
  # Penanda ideologis berejaan khas Indonesia; diurutkan menurut relevansi karena istilahnya jarang
  local YQI=${DRNO_YT_QUERY_IDEO:-'thogut|"pemerintah thaghut"|"aparat thaghut"|"kafir harbi"|"anshorut daulah"|"ansharut daulah"|"jamaah islamiyah"|"simpatisan ISIS"|"eks napiter"|"paham takfiri"|"mantan teroris" -lowongan -film -movie -horor'}
  # Kegagalan satu platform tidak menggagalkan siklus
  if [ -n "${YOUTUBE_API_KEY:-}" ]; then
    python -m drno.crawl youtube --query "$Q" --native-query "$YQ" --from "$FROM" --to "$TO" --max-videos "${DRNO_YT_VIDEOS:-20}" || log "youtube gagal"
    DRNO_YT_ORDER=relevance python -m drno.crawl youtube --query "$Q" --native-query "$YQI" --from "$FROM" --to "$TO" --max-videos "${DRNO_YT_VIDEOS:-20}" || log "youtube (ideologis) gagal"
    # Nama publik hanya untuk kanal >= DRNO_PUBLIC_CHANNEL_MIN_SUBS subscriber; sisanya tetap pseudonim
    python -m drno.maintenance label-channels >/dev/null || log "label kanal gagal"
  fi
  if [ -n "${X_BEARER_TOKEN:-}" ]; then python -m drno.crawl x --query "$Q" --from "$FROM" --to "$TO" --max "${DRNO_X_MAX:-200}" || log "x gagal"; fi
  if [ -n "${META_ACCESS_TOKEN:-}" ] && [ -n "${FB_PAGE_IDS:-}" ]; then python -m drno.crawl facebook --query "$Q" --from "$FROM" --to "$TO" || log "facebook gagal"; fi
  # Alternatif sementara (pihak ketiga, bukan API resmi Meta); kredit dibatasi DRNO_SC_MAX_CALLS per run
  if [ -n "${SCRAPECREATORS_API_KEY:-}" ] && [ -n "${FB_SC_PAGES:-}" ]; then python -m drno.crawl facebook_sc --query "$Q" --from "$FROM" --to "$TO" || log "facebook (scrapecreators) gagal"; fi
  if [ -n "${META_ACCESS_TOKEN:-}" ] && [ -n "${IG_USER_ID:-}" ]; then python -m drno.crawl instagram --hashtags "${IG_HASHTAGS:-}" --from "$(date -d '-1 days' +%F)" --to "$TO" || log "instagram gagal"; fi
  # Portal berita & situs publik (Scrapling, mode sopan): sekali per DRNO_SCRAPE_EVERY_HOURS (default 24 jam)
  if [ -f "$APP/config/sources.json" ]; then
    local last now every
    last=$(cat "$SITE/private/.last_scrape" 2>/dev/null || echo 0); now=$(date +%s); every=${DRNO_SCRAPE_EVERY_HOURS:-24}
    if [ $((now - last)) -ge $((every * 3600 - 900)) ]; then
      if python -m drno.crawl web --query "$Q" --from "$(date -d '-2 days' +%F)" --to "$TO" --max "${DRNO_WEB_MAX:-500}" --sources "$APP/config/sources.json"; then
        echo "$now" > "$SITE/private/.last_scrape"
      else
        log "web (scrapling) gagal"
      fi
    fi
  fi
  if [ "$(date +%F)" != "$LAST_RETENTION" ]; then
    if python -m drno.maintenance retention; then LAST_RETENTION=$(date +%F); else log "retensi gagal"; fi
  fi
  if ! python -m drno.maintenance has-data; then
    log "belum ada data nyata; situs tetap menampilkan tampilan sebelumnya"
    return 0
  fi
  rm -rf /tmp/exports_real /tmp/site_new
  python -m drno.analyze --out /tmp/exports_real || { log "analisis gagal"; return 1; }
  cd "$APP" || return 1
  python scripts/build_static_site.py --data /tmp/exports_real --out /tmp/site_new >/dev/null || { log "perakitan situs gagal"; return 1; }
  sync_site /tmp/site_new || { log "penyalinan situs gagal"; return 1; }
  log "situs diperbarui dengan data nyata"
}

log "worker mulai; interval ${INTERVAL} jam"
if [ -z "${DRNO_PSEUDONYM_KEY:-}" ] || [ "${#DRNO_PSEUDONYM_KEY}" -lt 32 ]; then
  log "FATAL: DRNO_PSEUDONYM_KEY kosong/terlalu pendek (min. 32)"; sleep 600; exit 1
fi
cd "$APP/backend" && python -m drno.maintenance wait-db || { log "FATAL: database tidak siap"; exit 1; }
if [ ! -f "$SITE/data/manifest.json" ]; then
  log "situs belum ada: tayangkan data sintetis sebagai tampilan awal"
  cd "$APP" && python scripts/build_static_site.py --data exports --out /tmp/site_init >/dev/null && sync_site /tmp/site_init || log "gagal merakit tampilan awal"
fi
fix_site_permissions || log "gagal menormalkan izin volume situs"
[ -f "$SITE/private/setup_key.txt" ] && log "Kode setup admin sudah dibuat. Ambil dengan: ./deploy/vps/drno.sh setup-key"

LAST_RETENTION=""
while true; do
  log "siklus pembaruan dimulai"
  if run_cycle; then log "siklus selesai"; else log "siklus gagal; situs lama tetap tayang"; fi
  date +%s > "$SITE/private/.heartbeat"
  [ "${DRNO_RUN_ONCE:-0}" = "1" ] && break
  sleep $((INTERVAL * 3600))
done
