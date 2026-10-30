"""Dataset SINTETIS untuk prototipe (Bagian 10, tahap 8).

Semua record bertanda is_synthetic=True dan source_method='synthetic'. Teks dibangkitkan
dari templat; tidak ada akun, unggahan, atau peristiwa nyata. Teks kategori dukungan
kekerasan SENGAJA disamarkan ([TEKS DISAMARKAN]) agar dataset tidak memuat propaganda.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .keywords import KeywordDictionary
from .privacy import content_hash, pseudonymize

KEY = b"synthetic-demo-key-not-for-real-data"
START = datetime(2026, 1, 5, tzinfo=timezone.utc)  # tanggal fiktif; 12 minggu
WEEKS = 12

ARCHETYPES = {
    # nama: (jumlah akun, distribusi platform, kategori konteks dominan, aktivitas)
    "media": (10, {"news": 0.6, "facebook": 0.4}, "pemberitaan", 6),
    "kontra_narasi": (40, {"x": 0.45, "instagram": 0.35, "youtube": 0.2}, "kontra_narasi", 3),
    "akademik": (25, {"youtube": 0.6, "x": 0.4}, "kajian_akademik", 2),
    "keagamaan_umum": (90, {"instagram": 0.45, "youtube": 0.35, "facebook": 0.2}, "diskusi_keagamaan_umum", 2),
    "kritik_politik": (60, {"x": 0.6, "facebook": 0.4}, "kritik_politik_sosial", 3),
    "penolakan": (35, {"facebook": 0.5, "x": 0.5}, "penolakan_kekerasan", 2),
    "kluster_sensitif": (12, {"x": 0.7, "youtube": 0.3}, "dukungan_kekerasan", 2),
}
IG_OWNER = "ig_hashtag_media"  # meniru API: pemilik media hashtag tidak tersedia

TEMPLATES = {
    "pemberitaan": ["Densus menangkap terduga anggota jaringan terorisme, dilaporkan kepolisian #terorisme",
                    "BNPT: program deradikalisasi diikuti mantan napiter, menurut polisi berjalan baik",
                    "Sidang perkara pendanaan terorisme kembali digelar, jaksa menghadirkan saksi"],
    "kontra_narasi": ["Meluruskan makna jihad: kontra-narasi untuk anak muda, islam rahmatan lil alamin #moderasiberagama",
                      "Kontra narasi terhadap propaganda digital: kenali legitimasi kekerasan di media sosial",
                      "Moderasi beragama bukan melemahkan tauhid, justru meneguhkan toleransi"],
    "kajian_akademik": ["Seminar penelitian radikalisasi dan ekstremisme kekerasan di ruang digital, dosen dan mahasiswa",
                        "Studi teori identitas kelompok dan polarisasi ideologis: kajian akademik terbaru",
                        "Jurnal: konsep hakimiyah dan khilafah dalam sejarah pemikiran politik, sebuah kajian akademik"],
    "diskusi_keagamaan_umum": ["Kajian ustaz pekan ini tentang hijrah dan istiqamah, yuk pengajian",
                               "Dakwah yang sejuk itu penting, tauhid dulu baru yang lain",
                               "Hijrah kaffah dimulai dari sholat tepat waktu, kajian ba'da maghrib"],
    "kritik_politik_sosial": ["Kebijakan pemerintah soal kontra terorisme perlu diawasi dpr agar tidak represif",
                              "Ketidakadilan dan korupsi memicu polarisasi ideologis, demokrasi kita diuji",
                              "Isu khilafah sering dipakai untuk menyerang lawan politik, kritik terhadap pemerintah",
                              "Mereka di dpr harus mendengar kritik kita soal kebijakan kontra terorisme"],
    "penolakan_kekerasan": ["Kami menolak kekerasan atas nama agama, terorisme tidak dibenarkan",
                            "Mengecam aksi teror, kekerasan bukan jalan, ujaran kebencian harus dihentikan",
                            "Kutuk keras propaganda terorisme di media sosial",
                            "Jangan biarkan mereka menyebar ujaran kebencian, kita menolak kekerasan"],
    "dukungan_kekerasan": ["[TEKS DISAMARKAN — kategori sintetis: dukungan kekerasan] thaghut daulah",
                           "[TEKS DISAMARKAN — kategori sintetis: dukungan kekerasan] takfir jahiliyah",
                           "[TEKS DISAMARKAN — kategori sintetis: dukungan kekerasan]"],
}
CROSS_PROB = 0.12  # peluang interaksi lintas komunitas


def generate(seed: int = 7):
    rng = random.Random(seed)
    kd = KeywordDictionary.baseline("generator-sintetis")
    authors, posts, interactions = [], [], []
    by_arch = {}
    for arch, (n, plat, cat, act) in ARCHETYPES.items():
        ids = []
        for i in range(n):
            plat_i = rng.choices(list(plat), weights=list(plat.values()))[0]
            if arch == "media":
                pid = f"media:Media Sintetis {i + 1}" if plat_i == "news" else f"page:Page Sintetis {i + 1}"
            else:
                pid = pseudonymize(plat_i, f"{arch}-{i}", KEY)
            authors.append({"author_pseudonym": pid, "platform": plat_i, "archetype": arch,
                            "author_type": "media" if arch == "media" else "individual", "is_synthetic": True})
            ids.append(pid)
        by_arch[arch] = ids
    plat_of = {a["author_pseudonym"]: a["platform"] for a in authors}
    arch_of = {a["author_pseudonym"]: a["archetype"] for a in authors}

    pc = 0
    for w in range(WEEKS):
        # peristiwa fiktif minggu ke-7: lonjakan pemberitaan & penolakan
        surge = 2.2 if w in (6, 7) else 1.0
        for arch, ids in by_arch.items():
            cat, act = ARCHETYPES[arch][2], ARCHETYPES[arch][3]
            mult = surge if arch in ("media", "penolakan", "kontra_narasi", "kritik_politik") else 1.0
            if arch == "kluster_sensitif" and w >= 8:
                mult = 0.4  # penurunan aktivitas sintetis setelah peristiwa
            for a in ids:
                lam = act * mult / 2.5
                n_posts = sum(1 for _ in range(6) if rng.random() < lam / 6)
                for _ in range(n_posts):
                    ts = START + timedelta(weeks=w, days=rng.random() * 7)
                    text = rng.choice(TEMPLATES[cat])
                    # sebagian kecil unggahan keluar dari kategori dominan (realisme)
                    if rng.random() < 0.15:
                        text = rng.choice(TEMPLATES[rng.choice([k for k in TEMPLATES if k != "dukungan_kekerasan"])])
                    pc += 1
                    pid = f"syn:{pc:06d}"
                    is_ig = plat_of[a] == "instagram"
                    p = {"post_id": pid, "platform": plat_of[a], "timestamp": ts.isoformat(), "text": text,
                         "url": None, "author_id_pseudonym": IG_OWNER if is_ig else a, "language": "id", "keyword_matched": kd.match(text),
                         "reply_to": None, "mention": [], "repost_of": None,
                         "engagement_count": int(rng.paretovariate(1.6) * (8 if arch == "media" else 2)),
                         "collection_time": None, "source_method": "synthetic", "is_synthetic": True,
                         "content_hash": content_hash(text + pid), "archetype": arch}
                    # interaksi teramati (sintetis)
                    if rng.random() < 0.65 and arch != "media" and not is_ig:
                        same = rng.random() > CROSS_PROB
                        pool = ids if same else rng.choice([v for k, v in by_arch.items() if k != arch])
                        if rng.random() < 0.25:
                            pool = by_arch["media"]  # akun individu sering me-mention media
                        pool = [t for t in pool if plat_of[t] == plat_of[a]] or [t for t in ids if plat_of[t] == plat_of[a]]
                        tgt = rng.choice(pool)
                        if tgt != a and plat_of[a] != "news":
                            itype = rng.choices(["reply", "mention", "repost", "comment"], weights=[4, 3, 3, 2])[0]
                            if itype == "mention":
                                p["mention"] = [tgt]
                            elif itype == "repost":
                                p["repost_of"] = f"of:{tgt}"
                            else:
                                p["reply_to"] = f"to:{tgt}"
                            interactions.append({"source": a, "target": tgt, "type": itype, "post_id": pid,
                                                 "timestamp": p["timestamp"], "platform": p["platform"]})
                    posts.append(p)
    return {"authors": authors, "posts": posts, "interactions": interactions, "dictionary": kd,
            "meta": {"seed": seed, "start": START.date().isoformat(), "weeks": WEEKS, "is_synthetic": True,
                     "note": "DATA SINTETIS — bukan hasil crawling nyata"}}


def periods(weeks=WEEKS, step=1):
    out = []
    for w in range(0, weeks, step):
        s = (START + timedelta(weeks=w)).date().isoformat()
        e = (START + timedelta(weeks=w + step) - timedelta(days=1)).date().isoformat()
        out.append((f"M{w + 1:02d}" if step == 1 else f"P{w // step + 1}", s, e))
    return out
