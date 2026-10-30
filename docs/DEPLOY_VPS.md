# Runbook Produksi DRNO di VPS

> **Khusus VPS 103.247.8.105:** jangan ikuti runbook Caddy di bawah ini. VPS tersebut
> sudah menjalankan Nginx dan Directus. Gunakan
> `deploy/vps/DEPLOY_EXISTING_VPS.md`; Caddy, `harden.sh` upstream, sudo tanpa
> password, dan grup Docker untuk user `drno` sengaja tidak digunakan.

Arsitektur (Docker Compose, satu VPS):

```
Internet ──443/80──▶ caddy (HTTPS otomatis, HSTS, header keamanan)
                        └──▶ web (PHP 8.3 + Apache: login, dashboard, gerbang data)
                                 ▲ volume "site"
worker (crawl → analisis → rakit situs, tiap N jam) ─┘
   └──▶ db (PostgreSQL 16, tidak terbuka ke internet)
backup (pg_dump + akun login, tiap 02.00 WIB) ──▶ ./backups
api (opsional, hanya 127.0.0.1)
```

## 0. Spesifikasi
- Ubuntu 22.04 / 24.04, **min. 2 vCPU, 4 GB RAM, 40 GB SSD**.
- Domain/subdomain atas nama akademik, mis. `drno.domainanda.ac.id`.

## 1. Siapkan server (sekali)
```bash
# sebagai root di VPS baru
adduser drno && usermod -aG sudo drno
mkdir -p /home/drno/.ssh && cp ~/.ssh/authorized_keys /home/drno/.ssh/ && chown -R drno:drno /home/drno/.ssh
# uji dulu dari laptop: ssh drno@IP_VPS  (harus berhasil dengan kunci)
```
Salin kode ke VPS (dari laptop): `scp DRNO_v0.7_source.zip drno@IP_VPS:~` → di VPS: `unzip DRNO_v0.7_source.zip && cd drno`.
```bash
sudo bash deploy/vps/harden.sh drno   # ufw (22/80/443), fail2ban, update otomatis, SSH tanpa kata sandi, Docker
exit                                  # logout-login ulang agar grup docker aktif
```

## 2. DNS
Di pengelola domain: **A record** `drno` → IP VPS. Tunggu sampai `ping drno.domainanda.ac.id` menunjuk ke IP VPS.
Caddy baru bisa memasang HTTPS setelah DNS benar.

## 3. Konfigurasi
```bash
./deploy/vps/init.sh drno.domainanda.ac.id email@domainanda.ac.id   # .env dengan rahasia acak, izin 600
nano .env    # isi YOUTUBE_API_KEY, DRNO_LEGAL_BASIS_YOUTUBE, (X/Meta bila ada)
./deploy/vps/drno.sh check
```
**Segera simpan `DRNO_PSEUDONYM_KEY` di luar VPS** (pengelola kata sandi). Bila hilang, pseudonim data baru
tidak lagi cocok dengan data lama; bila bocor, pseudonim dapat dicocokkan ulang ke akun asli.

## 4. Naikkan
```bash
./deploy/vps/drno.sh up          # build + jalankan semua layanan
./deploy/vps/drno.sh logs worker # pantau siklus pertama
./deploy/vps/drno.sh setup-key   # kode untuk membuat admin pertama
```
Buka `https://drno.domainanda.ac.id` → Setup awal → buat admin → masuk → **Kelola pengguna** untuk peneliti lain.

## 5. Verifikasi go-live
```bash
./deploy/vps/drno.sh verify
```
Semua baris harus ✓: login 200, `data/` 403, `data.php` tanpa login 401, `private/` & `inc/` 403, `.env` 403,
HSTS aktif, HTTP dialihkan ke HTTPS. Lalu: `./deploy/vps/drno.sh backup` dan pastikan berkas muncul di `backups/`.

## Operasi harian
| Kebutuhan | Perintah |
|---|---|
| Status layanan & kesehatan | `./deploy/vps/drno.sh ps` |
| Log worker / web / caddy | `./deploy/vps/drno.sh logs worker` |
| Jalankan pembaruan sekarang | `./deploy/vps/drno.sh run-now` |
| Isi database | `./deploy/vps/drno.sh stats` |
| Cadangan manual | `./deploy/vps/drno.sh backup` |
| Pulihkan database | `./deploy/vps/drno.sh restore backups/drno-db-YYYYMMDD-HHMM.dump` |
| Pulihkan akun login | `./deploy/vps/drno.sh restore-users backups/drno-site-private-YYYYMMDD-HHMM.tgz` |
| Perbarui ke versi baru | salin kode baru (jangan timpa `.env` & `backups/`) → `./deploy/vps/drno.sh update` |

## Cadangan
- Otomatis 02.00 WIB, disimpan 14 hari (`DRNO_BACKUP_KEEP_DAYS`).
- **Salin ke luar VPS** secara berkala, mis. dari laptop: `rsync -av drno@IP_VPS:~/drno/backups/ ./drno-backups/`.
- Uji pemulihan minimal sekali sebelum memakai data nyata.

## Perilaku yang perlu diketahui
- Sebelum ada data nyata, situs menampilkan **data sintetis** (banner oranye). Setelah crawling pertama berhasil, banner menjadi "DATA NYATA".
- Siklus gagal (API down, kuota habis) **tidak** merusak situs: tampilan terakhir tetap tayang dan galat tercatat di log.
- Situs tidak pernah diganti dengan paket kosong; akun & log login tidak pernah ditimpa pembaruan.
- Retensi: unggahan melewati `retention_until` (default 730 hari) dihapus otomatis sekali sehari, beserta interaksinya.
- Log container dirotasi (5 × 10 MB per layanan). Log Caddy memuat alamat IP pengunjung; ini ikut prinsip minimisasi data.

## Bila terjadi insiden
- **Kata sandi pengguna bocor**: admin → Kelola pengguna → ganti / nonaktifkan.
- **`.env` atau `DRNO_PSEUDONYM_KEY` bocor**: hentikan worker (`docker compose ... stop worker`), cabut & ganti
  semua API key di konsol penyedia, ganti `POSTGRES_PASSWORD`, dan konsultasikan ke komite etik. Mengganti kunci
  pseudonim berarti memulai seri data baru.
- **Server diretas**: jangan pakai ulang; buat VPS baru, pulihkan dari cadangan di luar VPS.
