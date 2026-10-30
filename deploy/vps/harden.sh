#!/usr/bin/env bash
# Berkas kompatibilitas untuk paket upstream.
#
# Skrip hardening upstream tidak aman dijalankan pada VPS bersama ini karena dapat
# mengubah SSH, firewall, grup sudo/docker, dan port aplikasi Directus. Gunakan
# prepare_shared_vps.sh untuk memasang prasyarat tanpa menyentuh konfigurasi CMS.
set -euo pipefail

echo "DIBATALKAN: harden.sh upstream tidak digunakan pada VPS bersama." >&2
echo "Jalankan sebagai root: bash deploy/vps/prepare_shared_vps.sh" >&2
exit 2
