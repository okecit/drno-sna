# Etika, Validitas, dan Keterbatasan

## Aturan yang ditegakkan oleh kode
- Konektor menolak berjalan tanpa `legal_basis` dan kredensial resmi.
- Akun individual disimpan sebagai HMAC pseudonim; kunci di luar database.
- Edge jaringan hanya dibuat bila ada `post_id` bukti interaksi.
- Label `dukungan_kekerasan` selalu masuk antrean validasi manual (confidence dibatasi < 0,6).
- Istilah keagamaan umum (jihad, kaffah, hijrah, syariat, tauhid, dakwah) ditandai sebagai **kelompok pembanding**, bukan sinyal.
- Tidak ada endpoint pemeringkatan individu. API jaringan selalu menyertakan peringatan interpretasi.
- Seluruh record sintetis bertanda `is_synthetic=True`; file ekspor berakhiran `_SYNTHETIC`.

## Keterbatasan yang harus dilaporkan
- **Bias sumber**: platform yang dapat diakses sah (X, YouTube, Reddit, berita) didominasi percakapan *tentang* ekstremisme; komunikasi ekstremis aktual banyak berada di kanal tertutup yang sengaja dikecualikan.
- **Bias kata kunci**: korpus ditentukan kamus; perubahan kamus mengubah populasi. Laporkan versi kamus untuk setiap analisis.
- **Akses API**: tier, kuota, dan ketentuan berubah; data historis terbatas.
- **Homofili vs pengaruh**: pada data observasional keduanya tidak dapat dipisahkan tanpa asumsi kuat (Shalizi & Thomas, 2011).
- **Validitas klasifier**: angka validasi sintetis bersifat sirkuler. Sebelum model dipakai pada data nyata: gold standard anotasi manual dua pengode, laporkan Cohen's kappa, precision/recall per kategori.

## Validasi sintetis v0.1 (sirkuler — hanya uji pipeline)
Klasifier baseline mengenali sekitar 86% unggahan pada kategori dominan arketipenya
(sisanya adalah unggahan "lintas kategori" yang sengaja disisipkan). Untuk kluster sensitif yang teksnya
disamarkan, 0 dari 88 berlabel dukungan kekerasan dan 71 berlabel *tidak dapat dipastikan*:
klasifier tidak menebak ketika tidak ada bukti. Itu perilaku yang diharapkan.

## Kepatuhan
- UU No. 27/2022 tentang Pelindungan Data Pribadi: pseudonim tetap data pribadi bila dapat diidentifikasi ulang.
- Persetujuan komite etik sebelum pengumpulan data nyata.
- Retensi default 730 hari (`retention_until`), dapat diubah sesuai protokol etik.
