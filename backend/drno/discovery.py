"""Penemuan kata kunci tersembunyi (Extended Module A).

Dua jenis usulan, keduanya berstatus 'usulan' sampai ditinjau peneliti
(lihat KeywordDictionary.suggest/review):

- asosiasi : istilah yang jauh lebih sering muncul pada unggahan yang memuat
             penanda pemicu (kelompok ideologis/jaringan) daripada unggahan lain.
             Skor = z log-odds dengan prior Dirichlet (Monroe, Colaresi & Quinn 2008).
- samaran  : ejaan terselubung/salah ketik dari istilah pemicu, mis. "th0gut", "t4ghut",
             "thoghut" (angka pengganti huruf atau selisih satu huruf).

Catatan metodologis: istilah yang berasosiasi dengan penanda pemicu BUKAN bukti
radikalisme; banyak di antaranya berasal dari pemberitaan atau kontra-narasi.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .keywords import KeywordDictionary, normalize

TRIGGER_GROUPS = {"ideologis", "jaringan_ekstrem"}

STOPWORDS = set("""
yang dan di ke dari ini itu untuk dengan pada adalah dalam tidak akan juga atau karena oleh sebagai bisa ada
kami kita saya aku kamu anda dia mereka nya lagi sudah telah masih hanya saja jadi kalau jika agar supaya
tapi tetapi namun serta lebih sangat banyak semua setiap para bagi tentang hingga sampai seperti antara
setelah sebelum ketika saat secara bahwa maka pun dapat harus perlu mau ingin buat bikin sih kok deh dong
yg gak ga nggak enggak tak udah aja kan nih tuh juga lah klo kalo utk dgn dr pd tdk sdh jg bgt banget
the and for that this with you are was have not but from they will what about your all can just
https http www com youtube video channel subscribe like share komentar link watch shorts short viral fyp
tahun hari bulan minggu waktu orang hal cara apa siapa mana kenapa mengapa bagaimana berapa
satu dua tiga empat lima ada adanya oleh terhadap kepada sendiri baru lain lainnya hal tersebut
bukan bila guna hati sebut disebut istilah begitu begini memang sebenarnya benar betul paling makin semakin
sama beda kata bilang tahu lihat dengar baca jangan boleh bisa pernah selalu sering kadang nanti tadi
""".split())
# Kosakata keagamaan umum: lazim di semua wacana keislaman, jadi tidak informatif sebagai istilah tersembunyi
GENERIC_RELIGIOUS = set("islam allah agama muslim umat quran ayat nabi rasul ustadz ustaz ulama iman sholat shalat doa".split())

LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_TOKEN = re.compile(r"[a-z0-9@$]*[a-z][a-z0-9@$]*")


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(normalize(text)) if len(t) >= 4 and t not in STOPWORDS and not t.isdigit()]


def _grams(text: str) -> set[str]:
    ts = tokens(text)
    return set(ts) | {f"{a} {b}" for a, b in zip(ts, ts[1:])}


VOWELS = set("aiueo")


def _edit1(a: str, b: str) -> bool:
    """True bila a dan b berselisih satu langkah yang lazim pada transliterasi Arab-Indonesia:
    ganti vokal (thagut/thogut), sisip/hapus 'h' atau vokal (thoghut), atau huruf ganda.
    Ganti konsonan (takfir/takdir) sengaja TIDAK dihitung agar kata umum tidak tertangkap."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [(x, y) for x, y in zip(a, b) if x != y]
        return len(diff) == 1 and diff[0][0] in VOWELS and diff[0][1] in VOWELS
    s, l = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(l)):
        if l[:i] + l[i + 1:] == s:
            c = l[i]
            return c == "h" or c in VOWELS or (i > 0 and l[i - 1] == c) or (i + 1 < len(l) and l[i + 1] == c)
    return False


def _trigger_terms(kd: KeywordDictionary) -> dict[str, dict]:
    return {t: e for t, e in kd.current.terms.items() if TRIGGER_GROUPS & set(e["groups"])}


def trigger_counts(posts, kd: KeywordDictionary) -> list[dict]:
    """Frekuensi tiap istilah pemicu (dengan variannya) per platform."""
    trig = _trigger_terms(kd)
    rows = []
    for t, e in trig.items():
        hit = [p for p in posts if t in p["keyword_matched"]]
        if not hit:
            continue
        plat = Counter(p["platform"] for p in hit)
        days = sorted(p["timestamp"][:10] for p in hit)
        rows.append({"term": t, "group": "/".join(e["groups"]), "posts": len(hit), "youtube": plat.get("youtube", 0),
                     "news": plat.get("news", 0), "other": len(hit) - plat.get("youtube", 0) - plat.get("news", 0),
                     "first_seen": days[0], "last_seen": days[-1]})
    return sorted(rows, key=lambda r: -r["posts"])


def disguised_variants(posts, kd: KeywordDictionary, min_count: int = 1) -> list[dict]:
    """Token yang merupakan samaran (angka->huruf) atau salah eja satu huruf dari istilah pemicu satu kata."""
    trig = _trigger_terms(kd)
    known = {v: t for t, e in kd.current.terms.items() for v in e["variants"]}
    single = {v: t for t, e in trig.items() for v in e["variants"] if " " not in v and not v.startswith("#") and len(v) >= 6}
    seen, posts_of = Counter(), {}
    for p in posts:
        for tok in set(tokens(p["text"])):
            if tok in known:
                continue
            base = tok.translate(LEET)
            target = single.get(base) if base != tok else None
            kind = "angka_pengganti" if target else None
            if not target:
                target = next((t for v, t in single.items() if _edit1(base, v)), None)
                kind = "salah_eja" if target else None
            if target:
                seen[(tok, target, kind)] += 1
                posts_of.setdefault((tok, target, kind), set()).add(p["platform"])
    return [{"term": tok, "kind": "samaran", "detail": kind, "related_to": target, "posts_with_trigger": n, "posts_total": n,
             "lift": "", "zscore": "", "platforms": "/".join(sorted(posts_of[(tok, target, kind)]))}
            for (tok, target, kind), n in seen.most_common() if n >= min_count]


def associated_terms(posts, kd: KeywordDictionary, top: int = 40, min_df: int = 3, min_lift: float = 3.0) -> list[dict]:
    """Istilah (uni/bigram) yang berasosiasi kuat dengan unggahan berpenanda pemicu."""
    trig = set(_trigger_terms(kd))
    known = {v for e in kd.current.terms.values() for v in e["variants"]} | set(kd.current.terms)
    # Potongan istilah kamus multi-kata ("kafir", "harbi" dari "kafir harbi") bukan temuan baru
    known |= {w for v in list(known) for w in v.split()} | GENERIC_RELIGIOUS
    A, B = Counter(), Counter()
    co = {}
    nA = nB = 0
    for p in posts:
        g = _grams(p["text"])
        hits = trig & set(p["keyword_matched"])
        if hits:
            nA += 1
            A.update(g)
            for x in g:
                co.setdefault(x, Counter()).update(hits)
        else:
            nB += 1
            B.update(g)
    if nA < 3:
        return []
    vocab = [x for x, n in A.items() if n >= min_df and x not in known and not all(part in known for part in x.split())]
    alpha = 0.5
    a0 = alpha * max(1, len(vocab))
    out = []
    for x in vocab:
        ya, yb = A[x], B.get(x, 0)
        la = math.log((ya + alpha) / (nA + a0 - ya - alpha))
        lb = math.log((yb + alpha) / (nB + a0 - yb - alpha))
        z = (la - lb) / math.sqrt(1 / (ya + alpha) + 1 / (yb + alpha))
        lift = (ya / nA) / ((yb + 1) / (nB + 1))
        out.append({"term": x, "kind": "asosiasi", "detail": "bigram" if " " in x else "kata", "posts_with_trigger": ya,
                    "posts_total": ya + yb, "lift": round(lift, 2), "zscore": round(z, 2),
                    "related_to": "/".join(t for t, _ in co[x].most_common(3)), "platforms": ""})
    out.sort(key=lambda r: -r["zscore"])
    return [r for r in out if r["zscore"] >= 2.0 and r["lift"] >= min_lift][:top]


def hidden_terms(posts, kd: KeywordDictionary) -> list[dict]:
    return disguised_variants(posts, kd) + associated_terms(posts, kd)
