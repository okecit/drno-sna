"""Keyword Intelligence (Bagian 3 dan Extended Module A, C).

- Kamus kata kunci berversi; setiap perubahan dicatat (riwayat longitudinal).
- Pembangkitan varian: kapitalisasi, hashtag, transliterasi Arab-Indonesia, salah eja umum.
- Parser Boolean: AND, OR, NOT, "frasa", tanda kurung.
- Usulan kata kunci semantik hanya masuk ke status 'pending' sampai ditinjau peneliti.

Catatan metodologis: kemunculan kata kunci adalah kriteria PENGAMBILAN DATA,
bukan indikator sikap. Istilah keagamaan umum ditandai sebagai kelompok
pembanding (baseline) agar korpus tidak menyamakan wacana keagamaan dengan ekstremisme.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

GROUPS = {
    "radikalisasi": ["radikalisasi", "radikalisme", "ekstremisme", "ekstremisme kekerasan",
                     "paham radikal", "intoleransi", "deradikalisasi", "kontra radikalisasi"],
    "terorisme": ["terorisme", "teroris", "jaringan terorisme", "propaganda terorisme",
                  "pendanaan terorisme", "perekrutan terorisme", "pencegahan terorisme", "kontra terorisme"],
    "narasi_digital": ["propaganda digital", "narasi ekstremisme", "legitimasi kekerasan", "ujaran kebencian",
                       "polarisasi ideologis", "identitas kelompok", "mobilisasi digital"],
    "keagamaan": ["jihad", "kaffah", "hijrah", "syariat", "tauhid", "dakwah"],
    "ideologis": ["thaghut", "hakimiyah", "takfir", "jahiliyah"],
    "politik_keagamaan": ["khilafah", "daulah", "negara islam", "demokrasi", "sekularisme"],
    "konflik": ["radikalisasi", "ekstremisme kekerasan", "propaganda terorisme", "legitimasi kekerasan"],
    "pencegahan": ["moderasi beragama", "deradikalisasi", "kontra-narasi", "toleransi"],
}
# Istilah keagamaan umum = pembanding, BUKAN sinyal ekstremisme
BASELINE_GROUPS = {"keagamaan"}

# Varian transliterasi Arab-Indonesia & salah eja yang umum (dapat diperluas peneliti)
TRANSLIT = {
    "thaghut": ["thogut", "taghut", "thagut", "toghut", "taghout"],
    "kaffah": ["kafah", "kaaffah", "kaffa"],
    "syariat": ["syariah", "syari'at", "syari'ah", "shariah", "sharia"],
    "khilafah": ["khalifah", "khilafa", "kilafah"],
    "hakimiyah": ["hakimiyyah", "hakimiya"],
    "takfir": ["takfiri", "takfiriyah"],
    "jahiliyah": ["jahiliah", "jahiliyyah"],
    "tauhid": ["tawhid", "tauheed"],
    "daulah": ["dawlah", "daula"],
    "jihad": ["jihaad"],
}


def normalize(text: str) -> str:
    """Huruf kecil, buang diakritik, rapikan apostrof & spasi."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", t).strip()


def variants(term: str) -> list[str]:
    """Varian sebuah istilah: bentuk dasar, transliterasi, hashtag, tanpa spasi/tanda hubung."""
    base = normalize(term)
    out = {base}
    out.update(normalize(v) for v in TRANSLIT.get(base, []))
    for v in list(out):
        compact = re.sub(r"[\s\-']", "", v)
        out.add(compact)
        out.add("#" + compact)
        if "-" in v:
            out.add(v.replace("-", " "))
    return sorted(out)


@dataclass
class DictionaryVersion:
    label: str
    created_by: str
    note: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    terms: dict = field(default_factory=dict)  # term -> {group, variants, baseline}


class KeywordDictionary:
    """Kamus berversi. Versi lama tidak pernah diubah; perubahan = versi baru."""

    def __init__(self):
        self.versions: list[DictionaryVersion] = []
        self.suggestions: list[dict] = []

    @classmethod
    def baseline(cls, created_by="peneliti") -> "KeywordDictionary":
        d = cls()
        terms = {}
        for g, items in GROUPS.items():
            for t in items:
                key = normalize(t)
                entry = terms.setdefault(key, {"groups": [], "variants": variants(t), "baseline": False})
                if g not in entry["groups"]:
                    entry["groups"].append(g)
                entry["baseline"] = entry["baseline"] or g in BASELINE_GROUPS
        d.versions.append(DictionaryVersion("v1.0-baseline", created_by, "Kamus awal dari master prompt", terms=terms))
        return d

    @property
    def current(self) -> DictionaryVersion:
        return self.versions[-1]

    def new_version(self, label, created_by, note, add=None, remove=None) -> DictionaryVersion:
        terms = json.loads(json.dumps(self.current.terms))
        for t, g in (add or {}).items():
            terms[normalize(t)] = {"groups": [g], "variants": variants(t), "baseline": g in BASELINE_GROUPS}
        for t in remove or []:
            terms.pop(normalize(t), None)
        v = DictionaryVersion(label, created_by, note, terms=terms)
        self.versions.append(v)
        return v

    # --- Semantic discovery: usulan wajib ditinjau ---
    def suggest(self, seed: str, term: str, similarity: float, model: str):
        self.suggestions.append({"seed": seed, "term": term, "similarity": round(similarity, 3),
                                 "model": model, "status": "pending"})

    def review(self, term: str, accept: bool, reviewer: str, group: str | None = None, note: str = ""):
        for s in self.suggestions:
            if s["term"] == term and s["status"] == "pending":
                s.update(status="accepted" if accept else "rejected", reviewed_by=reviewer, note=note)
                if accept:
                    if not group:
                        raise ValueError("Istilah yang diterima harus diberi kelompok oleh peneliti")
                    self.new_version(f"{self.current.label}+{term}", reviewer,
                                     f"Tambah '{term}' dari usulan semantik ({note})", add={term: group})
                return s
        raise KeyError(term)

    def match(self, text: str) -> list[str]:
        """Istilah kamus yang muncul dalam teks (batas kata; hashtag terdeteksi)."""
        t = normalize(text)
        hits = []
        for term, e in self.current.terms.items():
            for v in e["variants"]:
                pat = r"(?<![\w#])" + re.escape(v) + r"(?!\w)" if not v.startswith("#") else re.escape(v) + r"(?!\w)"
                if re.search(pat, t):
                    hits.append(term)
                    break
        return sorted(hits)

    def history(self) -> list[dict]:
        return [{k: v for k, v in asdict(x).items() if k != "terms"} | {"n_terms": len(x.terms)} for x in self.versions]


# ---------------- Parser Boolean ----------------
_TOKEN = re.compile(r'\s*(\(|\)|"[^"]+"|AND\b|OR\b|NOT\b|[^\s()"]+)')


def _tokens(q: str):
    pos, out = 0, []
    while pos < len(q):
        m = _TOKEN.match(q, pos)
        if not m:
            break
        out.append(m.group(1))
        pos = m.end()
    return out


def compile_query(query: str):
    """Ubah ekspresi Boolean menjadi fungsi predikat(teks)->bool.

    Contoh: '(khilafah OR daulah) AND NOT "moderasi beragama"'.
    Operator default antar-istilah tanpa operator adalah AND. Istilah di-match beserta variannya.
    """
    toks = _tokens(query)
    i = 0

    def term_pred(tok):
        phrase = tok.strip('"')
        vs = variants(phrase)
        def p(text):
            t = normalize(text)
            return any(re.search(r"(?<![\w])" + re.escape(v) + r"(?!\w)", t) for v in vs)
        return p

    def parse_or():
        nonlocal i
        left = parse_and()
        while i < len(toks) and toks[i] == "OR":
            i += 1
            right = parse_and()
            left = (lambda a, b: lambda x: a(x) or b(x))(left, right)
        return left

    def parse_and():
        nonlocal i
        left = parse_not()
        while i < len(toks) and toks[i] not in ("OR", ")"):
            if toks[i] == "AND":
                i += 1
            right = parse_not()
            left = (lambda a, b: lambda x: a(x) and b(x))(left, right)
        return left

    def parse_not():
        nonlocal i
        if i < len(toks) and toks[i] == "NOT":
            i += 1
            inner = parse_not()
            return lambda x: not inner(x)
        return parse_atom()

    def parse_atom():
        nonlocal i
        tok = toks[i]
        i += 1
        if tok == "(":
            e = parse_or()
            if i >= len(toks) or toks[i] != ")":
                raise ValueError("Kurung tidak seimbang")
            i += 1
            return e
        return term_pred(tok)

    if not toks:
        raise ValueError("Query kosong")
    pred = parse_or()
    if i != len(toks):
        raise ValueError(f"Token tidak terduga: {toks[i]}")
    return pred
