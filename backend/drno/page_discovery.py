"""Penemu Page Facebook publik dengan nada serupa (Extended Module A) lewat ScrapeCreators.

Hasilnya HANYA usulan untuk ditinjau peneliti (page_review.php); tidak ada Page yang di-crawl sebelum diterima.
Batas etik yang dipaksakan kode:
- Hanya Page publik (punya kategori Page, tidak privat) dengan pengikut >= DRNO_PUBLIC_MIN_FOLLOWERS.
- Profil pribadi, grup, dan akun di bawah ambang DIBUANG tanpa mencatat nama/URL-nya.
- Skor nada = porsi posting sampel yang memuat penanda ideologis/jaringan kamus DRNO; ini kriteria
  pengambilan, BUKAN bukti sikap atau afiliasi Page tersebut.

  python -m drno.maintenance discover-pages      # kredit kira-kira: kueri + 2 x kandidat
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

import httpx

from .collectors.http import check, make_client
from .collectors.scrapecreators_fb import API, _first, page_handle
from .keywords import KeywordDictionary

# Nada takfiri / anti-thaghut (dipilih peneliti); ejaan Indonesia didahulukan
DEFAULT_QUERIES = ['"pemerintah thogut"', '"hukum thaghut"', '"kafir harbi"', '"demokrasi syirik"', '"daulah islamiyah"',
                   '"tauhid hakimiyah"', '"aparat thogut"', '"khilafah" "thoghut"']
TONE_GROUPS = {"ideologis", "jaringan_ekstrem", "politik_keagamaan"}
# Segmen URL Facebook yang bukan Page publik (atau tidak bisa dipastikan Page)
NOT_PAGE = {"groups", "group", "watch", "share", "profile.php", "people", "events", "photo", "photo.php", "story.php", "permalink.php",
            "hashtag", "login", "reel", "reels", "videos", "marketplace", "gaming", "notes", "pages", "p", "media", "help", "policies"}


def candidate_handle(url: str) -> str | None:
    m = re.match(r"^https?://(?:www\.|m\.|web\.|id-id\.)?facebook\.com/([^/?#]+)", url.strip())
    if not m:
        return None
    h = m.group(1)
    if h.lower() in NOT_PAGE or not re.fullmatch(r"[A-Za-z0-9.\-_]{2,80}", h):
        return None
    return h


def load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


class PageDiscovery:
    def __init__(self, api_key=None, transport=None, min_followers=None, max_candidates=None, queries=None, kd=None):
        self.key = api_key or os.environ.get("SCRAPECREATORS_API_KEY")
        if not self.key:
            raise RuntimeError("SCRAPECREATORS_API_KEY belum tersedia")
        self.http = make_client(transport)
        self.min_followers = int(min_followers or os.environ.get("DRNO_PUBLIC_MIN_FOLLOWERS", 10000))
        self.max_candidates = int(max_candidates or os.environ.get("DRNO_DISCOVERY_MAX_CANDIDATES", 10))
        self.queries = queries or DEFAULT_QUERIES
        # Page yang hanya memberitakan istilah (skor nada 0) tidak diusulkan; default: >= 1 dari 3 posting sampel
        self.min_tone = float(os.environ.get("DRNO_DISCOVERY_MIN_TONE", 0.33))
        kd = kd or KeywordDictionary.baseline()
        self.kd = kd
        self.tone_terms = {t for t, e in kd.current.terms.items() if TONE_GROUPS & set(e["groups"])}
        self.calls = 0

    def _get(self, path, params):
        self.calls += 1
        try:
            return check(self.http.get(f"{API}{path}", params=params, headers={"x-api-key": self.key}))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {}
            raise

    def search(self) -> dict[str, dict]:
        """handle -> {found_via, title} dari pencarian Google site:facebook.com."""
        found: dict[str, dict] = {}
        for q in self.queries:
            res = self._get("/v1/google/search", {"query": f"site:facebook.com {q}", "region": "ID"})
            for r in _first(res, "results", "organic", "data", default=[]) or []:
                h = candidate_handle(str(_first(r, "url", "link", default="")))
                if h and h.lower() not in found:
                    found[h.lower()] = {"handle": h, "found_via": q, "title": str(_first(r, "title", default=""))[:140]}
        return found

    def evaluate(self, handle: str) -> dict | None:
        """Detail Page + skor nada; None bila bukan Page publik di atas ambang (tidak dicatat)."""
        url = f"https://www.facebook.com/{handle}"
        prof = self._get("/v1/facebook/profile", {"url": url, "cache_max_age": "30d"})
        if not prof or prof.get("isPrivate") or prof.get("accountDoesNotExist") or not prof.get("category"):
            return None  # profil pribadi / tak ada / bukan Page
        followers = int(_first(prof, "followerCount", "likeCount", default=0) or 0)
        if followers < self.min_followers:
            return None
        posts = _first(self._get("/v1/facebook/profile/posts", {"url": url}), "posts", default=[]) or []
        hits, terms = 0, set()
        for p in posts:
            m = set(self.kd.match(str(p.get("text") or ""))) & self.tone_terms
            if m:
                hits += 1
                terms |= m
        return {"handle": handle, "url": url, "name": _first(prof, "name", "title", default=handle), "category": prof.get("category"),
                "followers": followers, "posts_sampled": len(posts), "tone_posts": hits,
                "tone_score": round(hits / len(posts), 2) if posts else 0.0, "matched_terms": sorted(terms)}

    def run(self, exclude: set[str]) -> list[dict]:
        found = self.search()
        out = []
        for key, meta in found.items():
            if key in exclude:
                continue
            if len(out) >= self.max_candidates:
                break
            c = self.evaluate(meta["handle"])
            if c and c["tone_score"] >= self.min_tone:
                out.append({**c, "found_via": meta["found_via"], "search_title": meta["title"],
                            "discovered_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        return out


def discover(candidates_path: str | None = None, review_path: str | None = None, **kw) -> dict:
    """Jalankan penemuan dan gabungkan ke berkas kandidat (kandidat lama dipertahankan)."""
    candidates_path = candidates_path or os.environ.get("DRNO_PAGE_CANDIDATES", "config/page_candidates.json")
    review_path = review_path or os.environ.get("DRNO_PAGE_REVIEW", "config/page_review.json")
    store = load_json(candidates_path, {"candidates": []})
    min_tone = float(os.environ.get("DRNO_DISCOVERY_MIN_TONE", 0.33))
    have = {c["handle"].lower(): c for c in store.get("candidates", []) if c.get("tone_score", 0) >= min_tone}
    decided = {d["handle"].lower() for d in load_json(review_path, {"decisions": []}).get("decisions", [])}
    seeds = {page_handle(p).lower() for p in os.environ.get("FB_SC_PAGES", "").split(",") if p.strip()}
    pd = PageDiscovery(**kw)
    new = pd.run(exclude=set(have) | decided | seeds)
    for c in new:
        have[c["handle"].lower()] = c
    store = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "min_followers": pd.min_followers,
             "candidates": sorted(have.values(), key=lambda c: (-c["tone_score"], -c["followers"]))}
    os.makedirs(os.path.dirname(os.path.abspath(candidates_path)), exist_ok=True)
    with open(candidates_path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=1)
    return {"new_candidates": len(new), "total_candidates": len(store["candidates"]), "api_calls": pd.calls}


def accepted_pages(review_path: str | None = None) -> list[str]:
    """URL Page yang diterima peneliti lewat dashboard (dipakai crawl facebook_sc)."""
    review_path = review_path or os.environ.get("DRNO_PAGE_REVIEW", "config/page_review.json")
    return [f"https://www.facebook.com/{d['handle']}" for d in load_json(review_path, {"decisions": []}).get("decisions", [])
            if d.get("decision") == "accept" and re.fullmatch(r"[A-Za-z0-9.\-_]{2,80}", str(d.get("handle", "")))]
