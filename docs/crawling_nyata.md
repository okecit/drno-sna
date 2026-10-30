# Crawling Nyata via API Resmi

DRNO **tidak** melakukan scraping, login otomatis, atau melewati CAPTCHA. Setiap platform
dijalankan hanya dengan kredensial resmi milik peneliti dan dasar akses (`DRNO_LEGAL_BASIS_*`).

## Ringkasan akses per platform

| Platform | API | Yang Anda butuhkan | Data | Jaringan (SNA) |
|---|---|---|---|---|
| X/Twitter | X API v2, recent search | Akun developer, kredit pay-per-use, Bearer Token | Post 7 hari terakhir | Ya: reply, mention, quote |
| YouTube | Data API v3 | API key Google Cloud | Video + komentar publik | Ya: komentar, balasan |
| Instagram | Graph API, Hashtag Search | Akun IG Business/Creator + Page, aplikasi Meta, App Review fitur *Instagram Public Content Access* | Caption media 24 jam terakhir per hashtag; maks. 30 hashtag/7 hari | **Tidak**: API tidak memberi pemilik media |
| Facebook | Graph API, Pages | Aplikasi Meta, App Review fitur *Page Public Content Access*, verifikasi bisnis | Posting + komentar dari Page yang Anda tentukan | Terbatas: identitas komentator sering tidak dikembalikan |

Catatan penting:
- **Biaya X**: dibebankan per post dan per profil yang dikembalikan. Batasi `--max`, pantau konsol developer.
- **Instagram menolak hashtag yang dianggap sensitif** dengan error generik. DRNO mencatatnya di `skipped`; jangan menyimpulkan "tidak ada percakapan".
- **Meta Content Library & API** adalah jalur riset yang lebih lengkap untuk Facebook/Instagram (akses untuk lembaga akademik melalui aplikasi ke Meta, dijalankan di lingkungan Meta). Ajukan melalui UIN bila FB/IG menjadi sumber utama.
- TikTok, Telegram, Discord: tidak diintegrasikan tanpa akses riset resmi/izin tertulis.

## Langkah

```bash
cd backend && pip install -r requirements.txt
cp ../.env.example ../.env   # isi kunci pseudonim, kredensial, dan legal basis
set -a; source ../.env; set +a

# 1. Crawling (contoh)
python -m drno.crawl x --query '(radikalisasi OR terorisme OR deradikalisasi OR "kontra-narasi") AND NOT lowongan' \
       --from 2026-10-16 --to 2026-10-22 --max 300
python -m drno.crawl youtube --query 'deradikalisasi OR "kontra narasi" OR "moderasi beragama"' --from 2026-09-01 --to 2026-10-22 --max-videos 20
python -m drno.crawl instagram --hashtags moderasiberagama,kontranarasi --from 2026-10-21 --to 2026-10-22
python -m drno.crawl facebook --from 2026-10-01 --to 2026-10-22

# 2. Analisis + ekspor dataset dashboard (termasuk rincian per platform)
python -m drno.analyze --out exports_real
#    opsional: sentimen model Transformer (unduh model; wajib divalidasi)
python -m drno.analyze --out exports_real --sentiment-model w11wo/indonesian-roberta-base-sentiment-classifier

# 3. Penjadwalan otomatis
celery -A drno.tasks worker -B --loglevel=info
```

## Memperbarui dashboard dengan data nyata

Folder `exports_real/` berisi CSV dengan struktur yang sama dengan dataset dashboard
(`overview.csv` memuat `data_mode=real`, sehingga banner berubah otomatis). Kirimkan CSV
tersebut di percakapan dan minta dashboard diperbarui. **Jangan kirim `posts_REAL.csv`** bila
tidak perlu: file itu memuat teks unggahan; dashboard hanya butuh agregat.

## Sebelum hasil dikutip
1. Anotasi manual sampel acak (dua pengode) untuk konteks, stance, dan sentimen.
2. Laporkan Cohen's kappa dan precision/recall per kategori.
3. Laporkan versi kamus, rentang waktu, query asli per platform, dan isi `runs.jsonl`/`collection_run`.
