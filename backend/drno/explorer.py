"""Dataset modul eksplorasi dashboard: Entity Explorer, Mention Explorer, Geomap.

Privasi (data nyata): nama dan cuplikan teks HANYA untuk entitas publik (media, Page, kanal
publik yang lolos ambang subscriber). Akun individu tampil sebagai pseudonim dan agregat.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .keywords import normalize

PUBLIC_TYPES = ("media", "page", "channel")


def entity_kind(node: str, public_names: dict) -> tuple[str, str]:
    """(jenis, nama tampilan) sebuah penulis. Nama kosong untuk akun individu."""
    if node.startswith("media:"):
        return "media", node.split(":", 1)[1]
    pub = public_names.get(node, {})
    if node.startswith("page:"):
        return "page", pub.get("name") or node.split(":", 1)[1]   # nama Page bila sudah diambil dari Graph API
    if pub.get("type") == "channel" and pub.get("name"):
        return "channel", pub["name"]
    return "account", ""


def entities(posts, inter, public_names, triggers: set, comm=None, metrics=None, limit: int = 600) -> list[dict]:
    comm, metrics = comm or {}, metrics or {}
    agg = defaultdict(lambda: {"posts": 0, "trigger": 0, "eng": 0, "plat": Counter(), "days": [], "kw": Counter()})
    for p in posts:
        a = agg[p["author_id_pseudonym"]]
        a["posts"] += 1
        a["eng"] += int(p.get("engagement_count") or 0)
        a["plat"][p["platform"]] += 1
        a["days"].append(str(p["timestamp"])[:10])
        kws = set(p.get("keyword_matched") or [])
        a["kw"].update(kws)
        if kws & triggers:
            a["trigger"] += 1
    deg_in, deg_out = Counter(i["target"] for i in inter), Counter(i["source"] for i in inter)
    rows = []
    for n, a in agg.items():
        kind, name = entity_kind(n, public_names)
        rows.append({"entity_id": n, "display_name": name, "type": kind, "platform": a["plat"].most_common(1)[0][0],
                     "posts": a["posts"], "trigger_posts": a["trigger"], "engagement": a["eng"],
                     "interactions_in": deg_in.get(n, 0), "interactions_out": deg_out.get(n, 0),
                     "community": comm.get(n, ""), "pagerank": round(metrics.get(n, {}).get("pagerank", 0), 6),
                     "first_seen": min(a["days"]), "last_seen": max(a["days"]),
                     "top_keywords": ";".join(k for k, _ in a["kw"].most_common(3))})
    # Entitas publik selalu disertakan; sisanya diurutkan menurut unggahan pemicu lalu volume
    rows.sort(key=lambda r: (r["type"] == "account", -r["trigger_posts"], -r["posts"], -r["interactions_in"]))
    return rows[:limit]


def mentions(posts, public_names, groups_of: dict, limit: int = 500) -> tuple[list[dict], list[dict]]:
    """(agregat harian per kata kunci & platform, cuplikan dari sumber publik saja)."""
    daily = Counter()
    public = []
    for p in posts:
        kws = p.get("keyword_matched") or []
        day = str(p["timestamp"])[:10]
        for k in kws:
            daily[(day, k, p["platform"])] += 1
        kind, name = entity_kind(p["author_id_pseudonym"], public_names)
        if kws and kind in PUBLIC_TYPES:
            text = " ".join(str(p["text"]).split())
            public.append({"day": day, "source": name, "type": kind, "platform": p["platform"], "keywords": ";".join(kws),
                           "groups": ";".join(sorted({g for k in kws for g in groups_of.get(k, [])})),
                           "excerpt": text[:180] + ("…" if len(text) > 180 else ""), "url": p.get("url") or "",
                           "engagement": int(p.get("engagement_count") or 0)})
    rows = [{"day": d, "keyword": k, "group": "/".join(groups_of.get(k, [])), "platform": pl, "posts": n} for (d, k, pl), n in sorted(daily.items())]
    public.sort(key=lambda r: r["day"], reverse=True)
    return rows, public[:limit]


# ---------------- Geografi: penyebutan provinsi ----------------
# kode, nama, alias (huruf kecil; dicocokkan sebagai kata utuh)
PROVINCES = [
    ("AC", "Aceh", ["aceh", "banda aceh", "lhokseumawe"]),
    ("SU", "Sumatera Utara", ["sumatera utara", "sumut", "deli serdang"]),
    ("SB", "Sumatera Barat", ["sumatera barat", "sumbar", "bukittinggi"]),
    ("RI", "Riau", ["riau", "pekanbaru"]),
    ("KR", "Kepulauan Riau", ["kepulauan riau", "kepri", "batam", "tanjungpinang"]),
    ("JA", "Jambi", ["jambi"]),
    ("SS", "Sumatera Selatan", ["sumatera selatan", "sumsel", "palembang"]),
    ("BB", "Kepulauan Bangka Belitung", ["bangka belitung", "pangkalpinang"]),
    ("BE", "Bengkulu", ["bengkulu"]),
    ("LA", "Lampung", ["lampung"]),
    ("JK", "DKI Jakarta", ["dki jakarta", "jakarta", "dki"]),
    ("BT", "Banten", ["banten", "tangerang", "cilegon"]),
    ("JB", "Jawa Barat", ["jawa barat", "jabar", "bandung", "bekasi", "bogor", "cirebon", "tasikmalaya", "sukabumi", "cianjur"]),
    ("JT", "Jawa Tengah", ["jawa tengah", "jateng", "semarang", "surakarta", "sukoharjo", "klaten", "boyolali", "karanganyar",
                           "sragen", "cilacap", "purwokerto", "banyumas", "magelang", "pekalongan"]),
    ("YO", "DI Yogyakarta", ["yogyakarta", "jogja", "jogjakarta", "sleman", "bantul"]),
    ("JI", "Jawa Timur", ["jawa timur", "jatim", "surabaya", "sidoarjo", "lamongan", "kediri", "jember", "banyuwangi", "madura",
                          "pasuruan", "gresik", "probolinggo"]),
    ("BA", "Bali", ["bali", "denpasar"]),
    ("NB", "Nusa Tenggara Barat", ["nusa tenggara barat", "ntb", "mataram", "lombok", "dompu", "sumbawa"]),
    ("NT", "Nusa Tenggara Timur", ["nusa tenggara timur", "ntt", "kupang", "flores"]),
    ("KB", "Kalimantan Barat", ["kalimantan barat", "kalbar", "pontianak"]),
    ("KT", "Kalimantan Tengah", ["kalimantan tengah", "kalteng", "palangka raya", "palangkaraya"]),
    ("KS", "Kalimantan Selatan", ["kalimantan selatan", "kalsel", "banjarmasin"]),
    ("KI", "Kalimantan Timur", ["kalimantan timur", "kaltim", "samarinda", "balikpapan"]),
    ("KU", "Kalimantan Utara", ["kalimantan utara", "kaltara", "tarakan"]),
    ("SA", "Sulawesi Utara", ["sulawesi utara", "sulut", "manado"]),
    ("GO", "Gorontalo", ["gorontalo"]),
    ("ST", "Sulawesi Tengah", ["sulawesi tengah", "sulteng", "poso"]),
    ("SR", "Sulawesi Barat", ["sulawesi barat", "sulbar", "mamuju"]),
    ("SN", "Sulawesi Selatan", ["sulawesi selatan", "sulsel", "makassar"]),
    ("SG", "Sulawesi Tenggara", ["sulawesi tenggara", "sultra", "kendari"]),
    ("MA", "Maluku", ["maluku", "ambon"]),
    ("MU", "Maluku Utara", ["maluku utara", "malut", "ternate"]),
    ("PA", "Papua", ["papua", "jayapura"]),
    ("PB", "Papua Barat", ["papua barat", "manokwari"]),
    ("PD", "Papua Barat Daya", ["papua barat daya", "sorong"]),
    ("PT", "Papua Tengah", ["papua tengah", "nabire", "timika"]),
    ("PE", "Papua Pegunungan", ["papua pegunungan", "wamena"]),
    ("PS", "Papua Selatan", ["papua selatan", "merauke"]),
]
# Nama kota yang juga kata umum (serang = menyerang, malang, medan, solo, palu, ...):
# hanya dihitung bila ditulis berhuruf kapital pada teks asli.
AMBIGUOUS = {"Serang": "BT", "Depok": "JB", "Garut": "JB", "Solo": "JT", "Kudus": "JT", "Tegal": "JT", "Malang": "JI",
             "Medan": "SU", "Padang": "SB", "Bima": "NB", "Palu": "ST"}

_ALIASES = sorted(((a, code) for code, _, al in PROVINCES for a in al), key=lambda x: -len(x[0]))


def provinces_in(text: str) -> set[str]:
    t = " " + normalize(text) + " "
    found = set()
    for alias, code in _ALIASES:  # alias terpanjang dulu: "kepulauan riau" tidak ikut terhitung "riau"
        pat = r"(?<![\w])" + re.escape(alias) + r"(?!\w)"
        if re.search(pat, t):
            found.add(code)
            t = re.sub(pat, " ", t)
    for word, code in AMBIGUOUS.items():
        if re.search(r"(?<![\w])" + word + r"(?!\w)", str(text)):
            found.add(code)
    return found


def geo(posts, triggers: set) -> list[dict]:
    """Penyebutan per provinsi + sentimen (hasil leksikon baseline) unggahan yang menyebutnya."""
    n, trig, neg, pos, kw = Counter(), Counter(), Counter(), Counter(), defaultdict(Counter)
    for p in posts:
        codes = provinces_in(p["text"])
        kws = set(p.get("keyword_matched") or [])
        s = p.get("sentiment")
        for c in codes:
            n[c] += 1
            kw[c].update(kws)
            if kws & triggers:
                trig[c] += 1
            if s == "negatif":
                neg[c] += 1
            elif s == "positif":
                pos[c] += 1
    return [{"code": code, "province": name, "posts": n.get(code, 0), "trigger_posts": trig.get(code, 0),
             "negative_posts": neg.get(code, 0), "positive_posts": pos.get(code, 0),
             "negative_share": round(neg[code] / n[code], 3) if n.get(code) else 0,
             "top_keywords": ";".join(k for k, _ in kw[code].most_common(3))} for code, name, _ in PROVINCES]
