# Facebook: Page Public Content Access (PPCA)

DRNO mengambil **posting dan komentar publik dari Page Facebook yang Anda tentukan** lewat Graph API resmi.
Graph API tidak menyediakan pencarian kata kunci di seluruh Facebook; yang dipantau adalah daftar Page
(media, lembaga, ormas publik). Scraping halaman Facebook tidak dipakai (di balik login, dilarang ketentuan Meta).

Untuk membaca Page yang **tidak Anda kelola**, aplikasi Meta wajib mendapat fitur
**Page Public Content Access** lewat App Review dan verifikasi bisnis.

## 1. Siapkan aplikasi Meta

1. Masuk ke <https://developers.facebook.com> → **My Apps → Create App**, pilih tipe **Business**.
2. Hubungkan aplikasi ke **Business Portfolio** (Meta Business Suite) milik lembaga Anda, lalu selesaikan
   **Business Verification** (dokumen legal lembaga, domain/email resmi).
3. Di dashboard aplikasi: **App Review → Permissions and Features** → cari **Page Public Content Access**
   → **Request advanced access**.
4. Lengkapi **Privacy Policy URL** (mis. halaman kebijakan privasi proyek di situs lembaga) dan ikon aplikasi.

## 2. Draf teks App Review (salin ke formulir; sesuaikan bagian dalam [kurung])

**How will your app use Page Public Content Access?**

> DRNO (Digital Radicalization Network Observatory) is an academic research project at [nama institusi]
> that studies public discourse about radicalization, terrorism and counter-narratives in Indonesia.
> We use Page Public Content Access only to read public posts and public comments from a fixed list of
> public Pages chosen by the research team (news media, government agencies such as counter-terrorism and
> religious-affairs bodies, and public civil-society organizations). We do not search or collect data from
> personal profiles, groups or private content.
>
> The data is used to (1) measure how often and in which context topics such as terrorism prevention and
> counter-narratives are discussed, and (2) build aggregated, pseudonymized interaction networks
> (commenter → Page) for social-network analysis. Individual commenters are pseudonymized immediately with
> a keyed HMAC; their names are never stored or displayed. Only the Pages' own public names are shown.
> Results are shown in a password-protected research dashboard for the research team and in aggregated
> academic publications. Data is retained for a limited period ([24] months) and then deleted. The project
> has ethics approval [nomor persetujuan etik] and complies with Indonesia's Personal Data Protection Law (UU PDP).
> We do not sell data, run advertising, or make decisions about individuals.

**Step-by-step instructions for the reviewer (screencast)**

> 1. Log in to the DRNO dashboard (test credentials provided below).
> 2. Open "Per platform" → Facebook to see the list of monitored public Pages.
> 3. Open "Network" to see the aggregated, pseudonymized commenter → Page network.
> 4. Open "Mention Explorer" to see keyword mentions from public Page posts.

Rekam video layar (screencast) singkat yang menunjukkan langkah di atas. Buat **akun dashboard khusus
reviewer** (peran *viewer*) lewat menu *Kelola pengguna*; jangan memberikan akun admin.

## 3. Setelah disetujui

1. Buat **token akses jangka panjang** (System User token dari Business Settings disarankan, karena tidak
   kedaluwarsa seperti token pengguna).
2. Simpan token ke VPS lewat skrip pengisi kunci (kunci tidak tampil di layar), lalu cari ID Page:

   ```bash
   ssh drno-vps "cd /home/drno/apps/drno-site/current && docker compose -f deploy/vps/docker-compose.prod.yml --env-file .env run --rm --no-deps -T -w /app/backend worker python -m drno.maintenance fb-pages https://www.facebook.com/<page1> https://www.facebook.com/<page2>"
   ```

   Perintah ini mencetak ID dan nama tiap Page serta baris `FB_PAGE_IDS=...` yang siap disalin ke skrip pengisi.
3. Isi `DRNO_LEGAL_BASIS_FACEBOOK` (dasar hukum + nomor persetujuan etik). Konektor menolak berjalan tanpanya.
4. Worker mengambil Facebook otomatis setiap 6 jam. Page tampil dengan **nama publiknya** di Network dan
   Entity Explorer; komentator tetap pseudonim.

## 4. Memilih Page yang dipantau

Pilih Page **publik** yang relevan dan seimbang (pemberitaan, pencegahan, kontra-narasi, wacana keagamaan),
mis. media berita nasional, lembaga negara (penanggulangan terorisme, urusan agama), ormas keagamaan besar,
dan lembaga riset/kampus. Hindari Page milik individu non-publik. Catat alasan pemilihan tiap Page di
protokol riset agar bias seleksi dapat dipertanggungjawabkan.

## Batasan yang perlu dicatat di metode

- Field `from` (identitas komentator) sering tidak dikembalikan Graph API; tanpa itu edge interaksi tidak
  dibuat, sehingga jaringan Facebook bisa lebih jarang daripada YouTube.
- Cakupan terbatas pada Page terpilih; tidak mewakili seluruh percakapan Facebook.
- Alternatif yang lebih luas untuk riset: **Meta Content Library** (akses peneliti lewat ICPSR).
