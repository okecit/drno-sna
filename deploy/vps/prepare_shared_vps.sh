#!/usr/bin/env bash
# Prasyarat DRNO untuk VPS yang sudah menjalankan Nginx + Directus.
# Jalankan sebagai root. Skrip ini tidak mengubah SSH, Nginx, UFW, user sudo,
# grup docker, maupun service Directus.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Jalankan sebagai root." >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq ca-certificates curl unzip rsync

if command -v docker >/dev/null 2>&1; then
  docker compose version >/dev/null 2>&1 || {
    echo "Docker sudah ada tetapi plugin Compose tidak ditemukan." >&2
    echo "Hentikan agar paket dari repository berbeda tidak tercampur." >&2
    exit 1
  }
else
  # Repository apt resmi Docker; tidak memakai pola curl | sh.
  # Rujukan: https://docs.docker.com/engine/install/ubuntu/
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  . /etc/os-release
  suite=${UBUNTU_CODENAME:-$VERSION_CODENAME}
  arch=$(dpkg --print-architecture)
  printf '%s\n' \
    'Types: deb' \
    'URIs: https://download.docker.com/linux/ubuntu' \
    "Suites: $suite" \
    'Components: stable' \
    "Architectures: $arch" \
    'Signed-By: /etc/apt/keyrings/docker.asc' \
    > /etc/apt/sources.list.d/docker.sources

  apt-get update -q
  apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

systemctl enable --now docker
docker version >/dev/null
docker compose version

echo "Prasyarat Docker siap. User drno tetap tanpa sudo dan tanpa grup docker."
