"""Facebook Page publik lewat ScrapeCreators (layanan scraping PIHAK KETIGA, bukan API resmi Meta).

Dipakai sebagai alternatif sementara selama Page Public Content Access (Graph API) belum disetujui.
Konsekuensi metodologis yang WAJIB dicatat peneliti:
- Data diperoleh di luar ketentuan Meta lewat penyedia komersial; dasar hukum dicatat terpisah
  (DRNO_LEGAL_BASIS_FACEBOOK_SC) dan source_method = "scrapecreators".
- Hanya Page publik yang ditentukan peneliti (FB_SC_PAGES: URL/ID Page), bukan profil pribadi atau grup.
- Nama penulis komentar HANYA dipakai sebagai masukan HMAC pseudonim dan tidak pernah disimpan.
- Pemakaian kredit dibatasi per run (DRNO_SC_MAX_CALLS) karena endpoint posting hanya memberi 3 posting/panggilan.

Bentuk respons ScrapeCreators dipetakan secara defensif (nama field alternatif ditangani) dan
harus diverifikasi pada uji pertama dengan kunci yang valid (crawl --dry-run).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from ..privacy import pseudonymize
from .base import Collector, JobConfig, NotConfigured
from .http import check, make_client

API = "https://api.scrapecreators.com"


def _ts(v) -> str | None:
    """publishTime/created_at bisa berupa epoch (detik/milidetik) atau string ISO -> ISO UTC."""
    if v in (None, ""):
        return None
    try:
        x = float(v)
        if x > 1e12:
            x /= 1000
        return datetime.fromtimestamp(x, tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        s = str(v).replace("Z", "+00:00")
        for parse in (datetime.fromisoformat, lambda t: datetime.strptime(t, "%a %b %d %H:%M:%S %z %Y")):  # ISO / format X
            try:
                d = parse(s)
                return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
            except ValueError:
                continue
        return None


def _first(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def page_handle(page: str) -> str:
    """'https://www.facebook.com/bnptri/' -> 'bnptri'; ID angka dibiarkan."""
    h = re.sub(r"^(https?://)?(www\.|m\.|web\.)?facebook\.com/", "", page.strip()).split("?")[0].strip("/")
    return h.split("/")[0] if h else page.strip()


class ScrapeCreatorsFacebookCollector(Collector):
    platform = "facebook"
    source_method = "scrapecreators"

    def __init__(self, api_key=None, pages=None, transport=None, max_posts_per_page=None, comment_pages=None, max_calls=None, **kw):
        super().__init__(**kw)
        self.key = api_key or os.environ.get("SCRAPECREATORS_API_KEY")
        pages = pages or [p for p in os.environ.get("FB_SC_PAGES", "").split(",") if p.strip()]
        if not (self.key and pages):
            raise NotConfigured("SCRAPECREATORS_API_KEY dan FB_SC_PAGES belum tersedia")
        self.pages = [p.strip() for p in pages]
        self.handles = {page_handle(p) for p in self.pages}
        self.http = make_client(transport)
        self.max_posts = int(max_posts_per_page or os.environ.get("DRNO_SC_POSTS_PER_PAGE", 9))
        self.comment_pages = int(comment_pages or os.environ.get("DRNO_SC_COMMENT_PAGES", 1))
        self.max_calls = int(max_calls or os.environ.get("DRNO_SC_MAX_CALLS", 60))
        self.calls = 0
        self.names: dict[str, str] = {}

    def _get(self, path, params):
        if self.calls >= self.max_calls:
            raise StopIteration  # batas kredit per run tercapai
        self.calls += 1
        return check(self.http.get(f"{API}{path}", params=params, headers={"x-api-key": self.key}))

    def _call(self, path, params):
        try:
            return self.with_backoff(self._get, path, params)
        except StopIteration:
            return None

    def _page_param(self, page):
        return {"pageId": page} if page.isdigit() else {"url": page if page.startswith("http") else f"https://www.facebook.com/{page}"}

    def fetch(self, job: JobConfig):
        d0 = _ts(f"{job.date_from}T00:00:00+00:00")
        d1 = _ts(f"{job.date_to}T23:59:59+00:00")
        for page in self.pages:
            handle = page_handle(page)
            cursor, got, stop = None, 0, False
            while got < self.max_posts and not stop:
                res = self._call("/v1/facebook/profile/posts", {**self._page_param(page), **({"cursor": cursor} if cursor else {})})
                if not res:
                    return
                posts = _first(res, "posts", "data", default=[]) or []
                for p in posts:
                    ts = _ts(_first(p, "publishTime", "publish_time", "created_at", "createdAt"))
                    if not ts:
                        continue
                    if d0 and ts < d0:
                        stop = True  # posting diurutkan terbaru dulu
                        break
                    if d1 and ts > d1:
                        continue
                    name = _first(p.get("author") or {}, "name") or _first(res, "name", "pageName")
                    if name:
                        self.names[handle] = name
                    got += 1
                    eng = int(_first(p, "reactionCount", "reaction_count", default=0) or 0) + int(_first(p, "commentCount", "comment_count", default=0) or 0)
                    pid = str(_first(p, "id", "post_id"))
                    url = _first(p, "url", "permalink")
                    yield {"id": pid, "author": f"page::{handle}", "ts": ts, "text": _first(p, "text", "message", default="") or "",
                           "url": url, "likes": eng, "page": handle}
                    yield from self._comments(url, pid, handle, _first(p, "feedback_id", "feedbackId"))
                    if got >= self.max_posts:
                        break
                cursor = _first(res, "cursor", "next_cursor")
                if not cursor or not posts:
                    break

    def _comments(self, url, pid, handle, feedback_id=None):
        cursor = None
        for _ in range(self.comment_pages):
            params = {"feedback_id": feedback_id} if feedback_id else {"url": url}
            res = self._call("/v1/facebook/post/comments", {**params, **({"cursor": cursor} if cursor else {})})
            if not res:
                return
            for c in _first(res, "comments", "data", default=[]) or []:
                ts = _ts(_first(c, "created_at", "createdAt", "publishTime"))
                a = c.get("author") or {}
                # identitas komentator -> kunci HMAC saja; nama tidak disimpan di record
                ident = _first(a, "id", "profile_id", "url") or (f"name:{a['name']}" if a.get("name") else None)
                if not ts:
                    continue
                yield {"id": str(_first(c, "id", "comment_id")), "author": ident or "fb_unknown_commenter", "ts": ts,
                       "text": _first(c, "text", "message", default="") or "", "url": url,
                       "likes": int(_first(c, "reaction_count", "reactionCount", default=0) or 0),
                       "reply_to": f"facebook:{pid}", "_thread": pid,
                       "_interactions": [(f"page::{handle}", "comment")] if ident else []}
            cursor = _first(res, "cursor", "next_cursor")
            if not cursor:
                return

    def author_key(self, native_author_id) -> str:
        sid = str(native_author_id)
        if sid.startswith("page::"):
            return f"page:{sid[6:]}"  # Page publik = entitas publik
        if sid == "fb_unknown_commenter":
            return sid
        return pseudonymize("facebook", sid)

    def to_record(self, raw, job, matched):
        rec = self.base_record(native_post_id=raw["id"], native_author_id=raw["author"], ts=raw["ts"], text=raw["text"],
                               url=raw["url"], job=job, matched=matched, reply_to=raw.get("reply_to"), engagement_count=raw.get("likes", 0))
        if raw.get("page"):
            rec["author_type"] = "organization_public"
            rec["public_entity_name"] = self.names.get(raw["page"]) or raw["page"]
        return rec
