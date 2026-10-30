#!/usr/bin/env bash
# Membuat .env produksi dengan rahasia acak. Jalankan SEKALI dari root proyek: ./deploy/vps/init.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
if [ -f .env ]; then echo ".env sudah ada - tidak ditimpa (kunci pseudonim lama harus dipertahankan)."; exit 1; fi
DOMAIN=${1:-}
[ -n "$DOMAIN" ] || read -rp "Domain/subdomain (mis. drno.domainanda.ac.id): " DOMAIN
rand() {
  local n=$1 raw
  # Hindari pola `tr | head` di bawah pipefail (tr dapat keluar 141/SIGPIPE).
  # Hex tetap memberi 128-bit entropy untuk 32 karakter dan 192-bit untuk 48.
  raw=$(openssl rand -hex "$(( (n + 1) / 2 ))")
  printf '%s' "${raw:0:n}"
}
sed -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand 32)|" \
    -e "s|^DRNO_PSEUDONYM_KEY=.*|DRNO_PSEUDONYM_KEY=$(rand 48)|" \
    -e "s|^DRNO_DOMAIN=.*|DRNO_DOMAIN=$DOMAIN|" \
    -e "s|^DRNO_STORE=.*|DRNO_STORE=postgres|" \
    .env.example > .env
chmod 600 .env
mkdir -p backups && chmod 700 backups
echo "✓ .env dibuat (izin 600)."
echo "  WAJIB: simpan salinan DRNO_PSEUDONYM_KEY di luar VPS (pengelola kata sandi)."
echo "  Isi kredensial API & DRNO_LEGAL_BASIS_* di .env, lalu: ./deploy/vps/drno.sh up"
