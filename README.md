# DRNO — Digital Radicalization Network Observatory

Sistem riset akademik untuk mengumpulkan, mengolah, memvisualisasikan, dan menganalisis
**percakapan publik** di media digital Indonesia mengenai radikalisasi, ekstremisme kekerasan,
dan terorisme.

> DRNO memetakan **wacana publik tentang** radikalisasi. DRNO **tidak** menetapkan seseorang
> sebagai radikal atau teroris, tidak memeringkat individu, dan tidak menyimpulkan afiliasi
> dari kedekatan node atau sentralitas.

**Status: v0.8.** Crawling harian portal berita & situs publik dengan Scrapling (mode sopan): `docs/SCRAPLING.md`. **v0.7:** Siap produksi VPS: `docs/DEPLOY_VPS.md` (Caddy HTTPS, healthcheck, backup harian, retensi, pengamanan server). **v0.6:** Halaman login (PHP: sesi, bcrypt, CSRF, penguncian, kelola pengguna). **v0.5:** Siap hosting: situs statis mandiri (deploy/), panduan docs/DEPLOY.md. **v0.4:** SNA Explorer gaya graf interaktif (pengaturan kiri, graf tengah, node insight kanan) + klasifikasi emosi Plutchik baseline.

Untuk VPS bersama `103.247.8.105` yang sudah memakai Nginx dan Directus, gunakan
`deploy/vps/DEPLOY_EXISTING_VPS.md`. Jangan menjalankan Caddy atau hardening upstream.

**v0.3:** Lensa teori: Structural Holes + Weak Ties dan Homofili + Identitas Sosial (`drno/theory.py`, `docs/lensa_teori.md`). Konektor nyata untuk X, YouTube, Instagram, dan Facebook siap dijalankan dengan kredensial
resmi Anda (`docs/crawling_nyata.md`). Data bawaan repositori tetap SINTETIS.

## Status tahapan

| # | Tahap | Status v0.1 |
|---|---|---|
| 1 | Arsitektur sistem | Selesai — `docs/architecture.md` |
| 2 | Struktur database | Selesai — `db/schema.sql` (fakta, hasil mesin, interpretasi dipisah) |
| 3 | Konektor sumber resmi | X API v2, YouTube Data API v3, Instagram Hashtag Search, Facebook Pages API, RSS berita: terimplementasi dan diuji terhadap format respons resmi (tanpa jaringan). Uji dengan kredensial nyata: dilakukan peneliti. TikTok/Telegram/Discord: sengaja tidak diintegrasikan |
| 4 | Pipeline NLP | Baseline berbasis aturan + kerangka Transformer/BERTopic. Model belum dilatih |
| 5 | Mesin SNA | Selesai — jaringan interaksi & ko-okurensi narasi terpisah, 9 metrik, Louvain/Leiden, temporal |
| 6 | Dashboard | Prototipe dashboard data sintetis (dipublikasikan terpisah). Frontend Next.js: tahap berikut |
| 7 | Scheduler | Celery + Redis — `drno/tasks.py` |
| 8 | Dataset sintetis | Selesai — `drno/synthetic.py` |
| 9 | Uji validitas, keamanan, performa | 29 uji otomatis lulus; alur PostgreSQL diuji; uji validitas sintetis (sirkuler — lihat catatan); uji keamanan & performa: belum |
| 10 | Dokumentasi | README ini + `docs/` |

## Instalasi

```bash
cp .env.example .env          # isi kata sandi, kunci pseudonim, kredensial API resmi
docker compose up -d --build  # PostgreSQL (skema otomatis), Redis, API, worker
```

Tanpa Docker (pengembangan):

```bash
cd backend
pip install fastapi uvicorn httpx networkx pandas pytest
python -m drno.pipeline --synthetic --out ../exports    # pipeline end-to-end sintetis
uvicorn drno.api:app --reload                            # API di http://127.0.0.1:8000/docs
python -m pytest -q tests                                # 16 uji
PYTHONPATH=. python ../scripts/validate_synthetic.py     # validasi klasifier (sintetis)
```

## Konfigurasi job pengumpulan

Setiap job wajib menyertakan `legal_basis` (ToS atau izin akses). Konektor menolak berjalan
tanpa itu. Contoh query Boolean:

```
(khilafah OR daulah OR "negara islam") AND (radikalisasi OR terorisme) AND NOT "lowongan kerja"
```

Varian transliterasi (thaghut/thogut/taghut), hashtag, dan kapitalisasi ditangani otomatis
(`drno/keywords.py`). Usulan istilah dari semantic discovery masuk status `pending` dan
**hanya** masuk kamus setelah diterima peneliti; setiap perubahan membuat versi kamus baru.

## Ekspor

`exports/`: `posts_SYNTHETIC.csv`, `summary_SYNTHETIC.json`,
`interaction_network_SYNTHETIC.{graphml,gexf}`, `narrative_cooccurrence_SYNTHETIC.{graphml,gexf}`.
Nama file sintetis selalu berakhiran `_SYNTHETIC`.

## Dokumen

- `docs/architecture.md` — arsitektur & alur data
- `docs/ethics_validity.md` — etika, validitas, keterbatasan
- `docs/SCRAPLING.md` — crawling harian portal berita & situs publik (Scrapling, mode sopan)
- `docs/DEPLOY_VPS.md` — runbook produksi VPS (langkah demi langkah, operasi, insiden)
- `docs/DEPLOY.md` — menaikkan ke domain hosting (cPanel atau VPS)
- `docs/crawling_nyata.md` — crawling nyata per platform, langkah, batasan
- `docs/kaitan_ppt.md` — kaitan dengan presentasi *SNA dalam Kajian Radikalisasi Digital*
