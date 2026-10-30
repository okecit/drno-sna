# Crawling Harian Portal Berita & Situs Publik dengan Scrapling

DRNO memakai **Scrapling** hanya dalam **mode sopan**: `Fetcher` HTTP biasa, identitas jujur, robots.txt dipatuhi.
Fitur Scrapling untuk menyamar sebagai browser dan menembus Cloudflare/CAPTCHA (**StealthyFetcher**,
`solve_cloudflare`, `impersonate`, proxy rotation) **sengaja ditolak oleh kode**: master prompt DRNO melarang
melewati CAPTCHA dan pembatasan akses, dan data yang diperoleh dengan cara itu sulit dipertanggungjawabkan
di hadapan komite etik maupun penelaah jurnal.

> Catatan penting: secara bawaan, Scrapling menyamar sebagai Google Chrome dan mengirim *referer* palsu
> dari google.com. DRNO mematikan perilaku ini; setiap permintaan memakai
> `User-Agent: DRNO-research/0.8 (penelitian akademik; +https://drno.site; KONTAK)`.

## Cakupan yang tepat
| Cocok | Tidak dipakai |
|---|---|
| Portal berita Indonesia (lewat sitemap berita) | X, Instagram, Facebook, TikTok → pakai API resmi |
| Situs lembaga/ormas publik, rilis pers | Halaman yang butuh login atau di balik paywall |
| Publikasi & forum terbuka yang mengizinkan | Situs yang memblokir (403/429/CAPTCHA) — dihentikan, tidak ditembus |

## Aturan yang dipaksakan kode
- Hanya sumber di `config/sources.json` dengan `"enabled": true` **dan** `legal_basis` terisi.
- robots.txt dibaca dulu; jalur yang dilarang tidak pernah diminta; `Crawl-delay` dihormati.
- Jeda minimal per domain `DRNO_SCRAPE_DELAY` (default 5 detik).
- HTTP 403/429/503 atau halaman tantangan anti-bot → domain dihentikan untuk siklus itu dan dicatat.
- Teks artikel disimpan untuk analisis internal, **tidak** pernah ditayangkan di dashboard; ikut aturan retensi.

## Menambah sumber
1. Salin `config/sources.example.json` → `config/sources.json`.
2. Untuk setiap situs: buka `https://situs/robots.txt` (cari baris `Sitemap:`; sitemap berita biasanya
   `sitemap-news.xml`) dan baca ketentuan penggunaannya.
3. Isi entri:
```json
{ "name": "Nama Media", "enabled": true,
  "legal_basis": "robots.txt mengizinkan; ToS tidak melarang riset non-komersial; persetujuan etik No. ...",
  "sitemaps": ["https://www.situs.co.id/sitemap-news.xml"],
  "body_selector": "article p", "max_articles": 50 }
```
   Tanpa sitemap: pakai `"listing_urls": ["https://situs/kanal/nasional"]` dan `"link_pattern": "/read/\\d+"`.
4. Uji tanpa menyimpan: `./deploy/vps/drno.sh scrape-test` → periksa judul/tanggal yang tampil, `blocked`, dan `skipped`.

## Jadwal
Worker menjalankan crawling web **sekali per 24 jam** (`DRNO_SCRAPE_EVERY_HOURS`), rentang 2 hari terakhir
agar artikel yang terlambat masuk sitemap tidak terlewat. Duplikat otomatis diabaikan.
Jalankan manual: `./deploy/vps/drno.sh scrape-now`.

## Etika & hukum (ringkas)
- Hak cipta: penyimpanan teks untuk analisis riset internal, bukan penerbitan ulang. Kutipan di artikel ilmiah tetap singkat dan bersumber.
- UU PDP: nama jurnalis/narasumber tidak disimpan sebagai entitas; akun = media.
- Bila situs meminta berhenti, nonaktifkan sumbernya (`"enabled": false`).
