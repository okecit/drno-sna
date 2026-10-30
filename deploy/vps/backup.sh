#!/usr/bin/env bash
# Cadangan harian 02:00 WIB: dump PostgreSQL + akun & log login (private/). Simpan N hari.
set -u
KEEP=${DRNO_BACKUP_KEEP_DAYS:-14}
mkdir -p /backups
run_backup() {
  local ts; ts=$(date +%Y%m%d-%H%M)
  if pg_dump -Fc -f "/backups/drno-db-$ts.dump.tmp" && mv "/backups/drno-db-$ts.dump.tmp" "/backups/drno-db-$ts.dump"; then
    echo "[$(date '+%F %T')] db -> drno-db-$ts.dump"
  else
    echo "[$(date '+%F %T')] GAGAL dump database"; rm -f "/backups/drno-db-$ts.dump.tmp"
  fi
  tar czf "/backups/drno-site-private-$ts.tgz" -C /site private 2>/dev/null && echo "[$(date '+%F %T')] akun -> drno-site-private-$ts.tgz"
  find /backups -name 'drno-*' -mtime +"$KEEP" -delete
}
[ "${1:-}" = "now" ] && { run_backup; exit 0; }
while true; do
  now=$(date +%s)
  if [ "$(date +%H)" -lt 2 ]; then next=$(date -d "today 02:00" +%s); else next=$(date -d "tomorrow 02:00" +%s); fi
  sleep $((next - now))
  run_backup
done
