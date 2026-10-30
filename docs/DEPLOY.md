# Menaikkan DRNO ke Domain Hosting (dengan Halaman Login)

DRNO tayang sebagai situs dengan **halaman login**. Login ditangani PHP (sesi server), sehingga
data CSV **tidak bisa** diunduh tanpa masuk: folder `data/` ditutup, dan data hanya dikirim lewat `data.php`
kepada pengguna yang sudah login.

| | A. Shared hosting (cPanel) | B. VPS (Ubuntu + Docker) |
|---|---|---|
| Yang tayang | Dashboard + login (PHP) | Dashboard + login + crawling terjadwal |
| Crawling & analisis | Di laptop/PC Anda, hasil diunggah | Otomatis di server tiap N jam |
| Syarat hosting | PHP 7.4 atau lebih baru (semua cPanel modern) | Docker |

---

## A. Shared hosting (cPanel)

### 1. Unggah
1. cPanel → **Select PHP Version** / **MultiPHP Manager**: pastikan PHP **7.4 – 8.3**.
2. cPanel → **File Manager** → `public_html` → buat folder `drno` (atau arahkan subdomain `drno.domainanda.ac.id` ke folder itu).
3. Unggah `drno_web_upload.zip` ke folder tersebut → klik kanan → **Extract**.
4. Aktifkan *Show Hidden Files* (File Manager → Settings) dan pastikan `.htaccess` ikut terekstrak,
   termasuk di dalam `data/`, `inc/`, dan `private/`.

### 2. Buat akun admin pertama
1. Buka `https://domainanda.ac.id/drno/` → otomatis diarahkan ke **Setup awal**.
2. Ambil **kode setup** dari berkas `private/setup_key.txt` (buka lewat File Manager → Edit).
3. Isi kode setup, nama pengguna admin, dan kata sandi (min. 12 karakter) → **Buat admin**.
4. Halaman setup otomatis terkunci permanen setelah admin dibuat, dan `setup_key.txt` terhapus.

### 3. Tambah peneliti lain
Masuk sebagai admin → klik **Kelola pengguna** di kanan atas dashboard → tambah pengguna dengan peran
`viewer` (hanya melihat) atau `admin` (bisa mengelola pengguna). Di sini juga tersedia ganti kata sandi,
nonaktifkan, dan hapus pengguna.

### 4. Pasang HTTPS (wajib)
cPanel → **SSL/TLS Status** → **Run AutoSSL**. Setelah gembok tampil, hapus tanda `#` pada dua baris
"Paksa HTTPS" di `.htaccess` utama. Login lewat HTTP biasa mengirim kata sandi tanpa enkripsi.

### 5. Memperbarui data nyata
```bash
cp .env.example .env    # isi kredensial API, DRNO_PSEUDONYM_KEY, legal basis, FTP_*
./scripts/update_dashboard.sh   # crawl -> analisis -> rakit situs -> unggah folder data/ via FTPS
```
Pembaruan hanya mengganti isi `data/`; akun pengguna di `private/users.php` **tidak pernah ditimpa**.
Mengunggah ulang paket lengkap juga aman: `users.php` tidak ada di dalam paket.

---

## B. VPS (Docker)
1. Ubuntu 22.04/24.04, min. 2 vCPU / 4 GB RAM. `curl -fsSL https://get.docker.com | sh`
2. DNS **A record** `drno.domainanda.ac.id` → IP VPS; buka port 80 & 443.
3. `cp .env.example .env` → isi `POSTGRES_PASSWORD`, `DRNO_PSEUDONYM_KEY`, kredensial API, `DRNO_LEGAL_BASIS_*`, `DRNO_DOMAIN`.
4. `docker compose -f deploy/vps/docker-compose.prod.yml --env-file .env up -d --build`
5. Kode setup admin: `docker compose -f deploy/vps/docker-compose.prod.yml logs worker | grep "Kode setup"`.
   Buka `https://drno.domainanda.ac.id` dan buat admin seperti langkah A-2. HTTPS dipasang otomatis oleh Caddy.

---

## Fitur keamanan login
- Kata sandi disimpan sebagai hash bcrypt (`password_hash`), tidak pernah dalam teks biasa.
- Sesi: cookie `HttpOnly`, `SameSite=Strict`, `Secure` di HTTPS; ID sesi diganti saat login.
- Keluar otomatis setelah **60 menit** tidak aktif; sesi maksimal **12 jam**.
- Dikunci **15 menit** setelah **5** percobaan gagal dari IP yang sama.
- Perlindungan CSRF pada semua formulir.
- Log akses (`private/access_log.tsv`): masuk berhasil/gagal, keluar, perubahan pengguna.
- Data CSV, akun, log, dan kode setup tidak bisa dibuka langsung dari browser (403).

## Lupa kata sandi
- Pengguna biasa: minta admin mengganti lewat **Kelola pengguna**.
- Satu-satunya admin lupa: lewat File Manager hapus `private/users.php` (semua akun terhapus), lalu unggah
  `private/setup_key.txt` dari paket baru (`python scripts/build_static_site.py` mencetak kodenya) dan ulangi setup.

## Daftar periksa sebelum go-live
- [ ] `https://domain/drno/data/overview.csv` → **403**; `https://domain/drno/data.php?f=overview.csv` tanpa login → **401**.
- [ ] `https://domain/drno/private/users.php` → **403**.
- [ ] HTTPS aktif dan pengalihan HTTP→HTTPS dinyalakan.
- [ ] Setup sudah dilakukan (halaman setup menolak akses).
- [ ] `.env` dan `DRNO_PSEUDONYM_KEY` **tidak** ada di hosting.
- [ ] Persetujuan etik mencakup penayangan agregat di web terbatas; domain atas nama akademik.

## Mengatasi masalah
| Gejala | Penyebab | Solusi |
|---|---|---|
| Teks kode PHP tampil di layar / file terunduh | PHP tidak aktif untuk folder itu | Aktifkan PHP di MultiPHP Manager |
| 500 Internal Server Error | Versi PHP < 7.4, atau baris `.htaccess` tidak didukung | Naikkan versi PHP; beri `#` pada baris `Options -Indexes` |
| Setelah login kembali lagi ke halaman login | Cookie diblokir, atau campuran http/https | Buka selalu dengan `https://`; nyalakan pengalihan HTTPS |
| "Gagal memuat data" setelah login | Folder `data/` tidak terunggah | Unggah ulang `data/` (manifest.json paling akhir) |
| Gagal membuat admin / menambah pengguna | Folder `private/` tidak bisa ditulis | File Manager → Permissions `private/` = 755 (atau 750) |
| Server Nginx tanpa `.htaccess` | Aturan penolakan tidak berlaku | Minta hosting menolak akses ke `/data/`, `/private/`, `/inc/`; `users.php` tetap aman karena berhenti di baris pertama |
