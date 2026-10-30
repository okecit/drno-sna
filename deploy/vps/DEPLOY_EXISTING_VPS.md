# Deployment DRNO pada VPS 103.247.8.105

Dokumen ini menggantikan alur Caddy/hardening pada paket upstream. VPS sudah
menjalankan Nginx, Certbot, Directus, PostgreSQL 14, dan MariaDB. DRNO harus
tetap terisolasi dan tidak boleh mengambil port atau direktori milik CMS.

## Pemetaan layanan

| Komponen | Penempatan |
|---|---|
| Nginx + TLS | Host, sudah aktif; `drno.site` diteruskan ke `127.0.0.1:3001` |
| Web DRNO | Container Apache/PHP, hanya bind `127.0.0.1:3001:80` |
| Database DRNO | Container PostgreSQL 16, hanya network internal Compose |
| Worker DRNO | Container Python, network internal Compose |
| Backup | `/home/drno/backups`, tidak dibuka ke web |
| Directus | Tetap di `127.0.0.1:8055`, tidak diubah |

## Batas keamanan

- User `drno` tidak mendapat sudo dan tidak masuk grup `docker`.
- Docker Compose dijalankan oleh root; file aplikasi tetap dimiliki `drno:drno`.
- Jangan menjalankan Caddy, `harden.sh` upstream, atau menyalin key root ke user `drno`.
- Jangan membuka port PostgreSQL, API, atau port `3001` ke alamat publik.
- `.env` harus berada di `shared/.env`, mode `0600`, dan tidak masuk arsip release.
- Coming Soon tetap aktif sampai container web lulus health check.

## Struktur release

```text
/home/drno/apps/drno-site/
├── current -> releases/<timestamp>/drno
├── releases/
│   └── <timestamp>/drno/
└── shared/
    ├── .env
    └── sources.json

/home/drno/backups/
```

Pada setiap release:

1. Ekstrak source ke direktori timestamp baru.
2. Buat symlink `.env` ke `shared/.env`.
3. Buat symlink `config/sources.json` ke `shared/sources.json` bila crawling web diaktifkan.
4. Buat symlink `backups` ke `/home/drno/backups`.
5. Validasi Compose sebelum mengganti symlink `current`.

## Urutan go-live

1. Pasang prasyarat sebagai root dengan `prepare_shared_vps.sh`.
2. Buat `.env` dengan `./deploy/vps/init.sh drno.site` dan simpan kunci pseudonim di luar VPS.
3. Jalankan `docker compose ... config` untuk validasi.
4. Jalankan stack DRNO tanpa mengubah Nginx.
5. Pastikan `curl http://127.0.0.1:3001/robots.txt` menghasilkan HTTP 200.
6. Backup konfigurasi Nginx Coming Soon.
7. Pasang `nginx-drno.site.conf`, jalankan `nginx -t`, lalu reload Nginx.
8. Verifikasi `drno.site`, `cms.ikaluinjkt.com`, port publik, login, dan backup.

## Rollback

Jika health check atau login gagal:

1. Kembalikan konfigurasi Nginx Coming Soon dan reload Nginx.
2. Jalankan `./deploy/vps/drno.sh down` hanya dari project Compose `drno`.
3. Jangan menghentikan Nginx, PM2 Directus, PostgreSQL host, atau MariaDB host.

## Catatan kapasitas

VPS hanya memiliki 1 vCPU dan sekitar 2,2 GB RAM. Compose sudah diberi limit
lebih kecil dan worker produksi tidak memasang model Transformer. Deployment
pertama harus memakai data sintetis, dipantau ketat, dan memiliki swap yang
memadai. Model NLP berat tidak boleh diaktifkan pada kapasitas ini.
