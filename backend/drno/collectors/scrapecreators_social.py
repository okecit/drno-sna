"""X dan Instagram lewat ScrapeCreators (layanan scraping PIHAK KETIGA, bukan API resmi platform).

Konsekuensi metodologis yang WAJIB dicatat peneliti (lihat juga scrapecreators_fb.py):
- source_method = "scrapecreators"; dasar hukum terpisah DRNO_LEGAL_BASIS_X_SC / DRNO_LEGAL_BASIS_INSTAGRAM_SC.
- Penemuan posting X dan hashtag Instagram berbasis indeks Google: cakupan tidak lengkap, tidak urut waktu.
- Akun individu dipseudonimkan (HMAC); username/nama hanya masukan HMAC dan tidak disimpan.
  Nama tampil hanya untuk akun publik besar: X dengan pengikut >= DRNO_PUBLIC_MIN_FOLLOWERS (default 10.000),
  Instagram berstatus verified.
- Kredit dibatasi per run (DRNO_SC_MAX_CALLS).
Bentuk respons dipetakan defensif; verifikasi pada uji pertama dengan kunci valid (crawl --dry-run).
"""
from __future__ import annotations

import os

from ..privacy import pseudonymize
from .base import Collector, JobConfig, NotConfigured
from .http import check, make_client
from .scrapecreators_fb import API, _first, _ts

DEFAULT_X_QUERIES = 'thogut,"kafir harbi","anshorut daulah","jamaah islamiyah","paham takfiri",deradikalisasi,"terorisme indonesia"'


def _split(s: str) -> list[str]:
    """Pisah koma dengan menghormati tanda kutip: 'a,"b c",d' -> ['a', 'b c', 'd']."""
    out, cur, q = [], "", False
    for ch in s:
        if ch == '"':
            q = not q
        elif ch == "," and not q:
            out.append(cur.strip()); cur = ""
            continue
        else:
            cur += ch
    out.append(cur.strip())
    return [x for x in out if x]


class _SCBase(Collector):
    source_method = "scrapecreators"

    def __init__(self, api_key=None, transport=None, max_calls=None, **kw):
        super().__init__(**kw)
        self.key = api_key or os.environ.get("SCRAPECREATORS_API_KEY")
        if not self.key:
            raise NotConfigured("SCRAPECREATORS_API_KEY belum tersedia")
        self.http = make_client(transport)
        self.max_calls = int(max_calls or os.environ.get("DRNO_SC_MAX_CALLS", 60))
        self.calls = 0
        self.public: dict[str, str] = {}  # id native -> nama publik (hanya akun publik besar)

    def _call(self, path, params):
        if self.calls >= self.max_calls:
            return None  # batas kredit per run tercapai
        self.calls += 1
        return self.with_backoff(lambda: check(self.http.get(f"{API}{path}", params=params, headers={"x-api-key": self.key})))

    def author_key(self, native_author_id) -> str:
        return pseudonymize(self.platform, str(native_author_id))

    def _record(self, raw, job, matched):
        rec = self.base_record(native_post_id=raw["id"], native_author_id=raw["author"], ts=raw["ts"], text=raw["text"], url=raw.get("url"),
                               job=job, matched=matched, reply_to=raw.get("reply_to"), engagement_count=raw.get("likes", 0))
        name = self.public.get(str(raw["author"]))
        if name:  # akun publik besar: ID tetap pseudonim, nama publik disimpan sebagai label
            rec["author_type"], rec["public_entity_name"] = "channel", name
        return rec

    to_record = _record


class ScrapeCreatorsXCollector(_SCBase):
    platform = "x"

    def __init__(self, queries=None, pages=None, min_followers=None, **kw):
        super().__init__(**kw)
        self.queries = queries or _split(os.environ.get("DRNO_SC_X_QUERIES", DEFAULT_X_QUERIES))
        self.pages = int(pages or os.environ.get("DRNO_SC_X_PAGES", 1))
        self.min_followers = int(min_followers or os.environ.get("DRNO_PUBLIC_MIN_FOLLOWERS", 10000))

    @staticmethod
    def _user(t):
        u = t.get("author") or (((t.get("core") or {}).get("user_results") or {}).get("result")) or t.get("user") or {}
        leg = u.get("legacy") or u
        return {"id": str(_first(u, "rest_id", "id_str", "id", default="") or _first(leg, "id_str", default="")),
                "handle": _first(leg, "screen_name", "username", "handle", default=""), "name": _first(leg, "name", default=""),
                "followers": int(_first(leg, "followers_count", "followers", default=0) or 0)}

    def fetch(self, job: JobConfig):
        d0, d1 = _ts(f"{job.date_from}T00:00:00+00:00"), _ts(f"{job.date_to}T23:59:59+00:00")
        for q in self.queries:
            cursor = None
            for _ in range(self.pages):
                res = self._call("/v1/twitter/search/posts", {"query": q, **({"cursor": cursor} if cursor else {})})
                if res is None:
                    return
                for t in _first(res, "posts", "tweets", "results", "data", default=[]) or []:
                    leg = t.get("legacy") or t
                    ts = _ts(_first(leg, "created_at", default=None) or _first(t, "created_at", "createdAt"))
                    if not ts or (d0 and ts < d0) or (d1 and ts > d1):
                        continue
                    u = self._user(t)
                    ident = u["id"] or (f"handle:{u['handle'].lower()}" if u["handle"] else None)
                    if not ident:
                        continue
                    if u["followers"] >= self.min_followers and u["handle"]:
                        self.public[ident] = f"@{u['handle']}" + (f" ({u['name']})" if u["name"] else "")
                    inter = []
                    for m in ((leg.get("entities") or {}).get("user_mentions") or []):
                        mid = _first(m, "id_str", "id") or (f"handle:{str(m.get('screen_name', '')).lower()}" if m.get("screen_name") else None)
                        if mid and str(mid) != ident:
                            inter.append((str(mid), "mention"))
                    rid = _first(leg, "in_reply_to_user_id_str", "in_reply_to_user_id")
                    if rid:
                        inter.append((str(rid), "reply"))
                    pid = str(_first(t, "rest_id", "id", default="") or _first(leg, "id_str", default=""))
                    yield {"id": pid, "author": ident, "ts": ts, "text": _first(leg, "full_text", "text", default="") or _first(t, "full_text", "text", default=""),
                           "url": _first(t, "url"), "likes": int(_first(leg, "favorite_count", default=0) or 0) + int(_first(leg, "retweet_count", default=0) or 0),
                           "reply_to": f"x:{_first(leg, 'in_reply_to_status_id_str')}" if _first(leg, "in_reply_to_status_id_str") else None,
                           "_interactions": inter}
                cursor = _first(res, "cursor", "next_cursor")
                if not cursor:
                    break


class ScrapeCreatorsInstagramCollector(_SCBase):
    platform = "instagram"

    def __init__(self, hashtags=None, window=None, comment_posts=None, **kw):
        super().__init__(**kw)
        tags = hashtags or [h for h in (os.environ.get("IG_SC_HASHTAGS") or os.environ.get("IG_HASHTAGS", "")).split(",") if h.strip()]
        if not tags:
            raise NotConfigured("IG_SC_HASHTAGS / IG_HASHTAGS belum diisi")
        self.hashtags = [h.strip().lstrip("#") for h in tags]
        self.window = window or os.environ.get("DRNO_SC_IG_WINDOW", "last-week")
        self.comment_posts = int(comment_posts if comment_posts is not None else os.environ.get("DRNO_SC_IG_COMMENT_POSTS", 5))

    def fetch(self, job: JobConfig):
        d0, d1 = _ts(f"{job.date_from}T00:00:00+00:00"), _ts(f"{job.date_to}T23:59:59+00:00")
        commented = 0
        for tag in self.hashtags:
            res = self._call("/v1/instagram/search/hashtag", {"hashtag": tag, "date_posted": self.window})
            if res is None:
                return
            for p in _first(res, "posts", "items", "results", "data", default=[]) or []:
                ts = _ts(_first(p, "taken_at", "created_at", "timestamp", "post_time"))
                if not ts or (d0 and ts < d0) or (d1 and ts > d1):
                    continue
                o = p.get("owner") or p.get("user") or {}
                ident = str(_first(o, "id", "pk", default="") or (f"handle:{str(o.get('username', '')).lower()}" if o.get("username") else ""))
                if not ident:
                    continue
                if o.get("is_verified") and o.get("username"):
                    self.public[ident] = f"@{o['username']}" + (f" ({o['full_name']})" if o.get("full_name") else "")
                cap = p.get("caption")
                text = (cap.get("text") if isinstance(cap, dict) else cap) or _first(p, "text", default="") or ""
                sc = _first(p, "shortcode", "code")
                url = _first(p, "url", "permalink") or (f"https://www.instagram.com/p/{sc}/" if sc else None)
                pid = str(_first(p, "id", "pk", default="") or sc)
                yield {"id": pid, "author": ident, "ts": ts, "text": text, "url": url,
                       "likes": int(_first(p, "like_count", "likes", default=0) or 0) + int(_first(p, "comment_count", "comments", default=0) or 0)}
                if url and commented < self.comment_posts:
                    commented += 1
                    yield from self._comments(url, pid, ident)

    def _comments(self, url, pid, owner):
        res = self._call("/v2/instagram/post/comments", {"url": url})
        for c in (_first(res or {}, "comments", "data", default=[]) or []):
            u = c.get("user") or c.get("owner") or {}
            ident = str(_first(u, "id", "pk", default="") or (f"handle:{str(u.get('username', '')).lower()}" if u.get("username") else ""))
            ts = _ts(_first(c, "created_at", "taken_at", "timestamp"))
            if not ts:
                continue
            yield {"id": str(_first(c, "id", "pk")), "author": ident or "ig_unknown_commenter", "ts": ts, "text": _first(c, "text", default="") or "",
                   "url": url, "likes": int(_first(c, "like_count", default=0) or 0), "reply_to": f"instagram:{pid}", "_thread": pid,
                   "_interactions": [(owner, "comment")] if ident and ident != owner else []}
