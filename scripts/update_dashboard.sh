#!/usr/bin/env bash
# Satu perintah untuk memperbarui dashboard: crawl -> analisis -> rakit situs -> (opsional) unggah FTPS.
# Pakai di laptop/server peneliti. Jadwalkan dengan cron, mis. setiap hari 05:00:
#   0 5 * * * cd /path/drno && ./scripts/update_dashboard.sh >> logs/update.log 2>&1
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && source .env; set +a
FROM=${DRNO_FROM:-$(date -d '-7 days' +%F 2>/dev/null || date -v-7d +%F)}
TO=${DRNO_TO:-$(date +%F)}
cd backend
QUERY=${DRNO_QUERY:-$(python -c 'from drno.keywords import DEFAULT_QUERY; print(DEFAULT_QUERY)')}
YQUERY=${DRNO_YT_QUERY:-'radikalisasi|terorisme|ekstremisme|deradikalisasi|"kontra narasi" -lowongan'}
YQUERY_IDEO=${DRNO_YT_QUERY_IDEO:-'thogut|"pemerintah thaghut"|"aparat thaghut"|"kafir harbi"|"anshorut daulah"|"ansharut daulah"|"jamaah islamiyah"|"simpatisan ISIS"|"eks napiter"|"paham takfiri"|"mantan teroris" -lowongan -film -movie -horor'}
[ -n "${YOUTUBE_API_KEY:-}" ] && python -m drno.crawl youtube --query "$QUERY" --native-query "$YQUERY" --from "$FROM" --to "$TO" --max-videos "${DRNO_YT_VIDEOS:-20}" || echo "[lewati] youtube"
[ -n "${YOUTUBE_API_KEY:-}" ] && DRNO_YT_ORDER=relevance python -m drno.crawl youtube --query "$QUERY" --native-query "$YQUERY_IDEO" --from "$FROM" --to "$TO" --max-videos "${DRNO_YT_VIDEOS:-20}" || echo "[lewati] youtube (ideologis)"
[ -n "${X_BEARER_TOKEN:-}" ]  && python -m drno.crawl x --query "$QUERY" --from "$FROM" --to "$TO" --max "${DRNO_X_MAX:-200}" || echo "[lewati] x"
[ -n "${META_ACCESS_TOKEN:-}" ] && [ -n "${FB_PAGE_IDS:-}" ] && python -m drno.crawl facebook --query "$QUERY" --from "$FROM" --to "$TO" || echo "[lewati] facebook"
[ -n "${META_ACCESS_TOKEN:-}" ] && [ -n "${IG_USER_ID:-}" ] && python -m drno.crawl instagram --hashtags "${IG_HASHTAGS:-}" --from "$FROM" --to "$TO" || echo "[lewati] instagram"
python -m drno.analyze --out ../exports_real
cd ..
python scripts/build_static_site.py --data exports_real --out deploy/dist/drno
if [ -n "${FTP_HOST:-}" ]; then python scripts/publish_ftp.py --site deploy/dist/drno --data-only; fi
echo "Selesai $(date)"
