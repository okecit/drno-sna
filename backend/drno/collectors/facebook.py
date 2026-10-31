"""Facebook Pages API (Graph API resmi) — posting dan komentar publik dari Page.

Syarat (Meta): fitur *Page Public Content Access* (App Review + verifikasi bisnis) untuk Page yang
tidak Anda kelola. Kredensial: META_ACCESS_TOKEN. Daftar Page (FB_PAGE_IDS) ditentukan peneliti,
mis. Page media berita, lembaga, dan organisasi publik; Graph API tidak menyediakan pencarian
kata kunci lintas seluruh Facebook.

Interaksi teramati:
- comment       : komentator -> Page pemilik posting
- comment_reply : pembalas   -> penulis komentar induk
Field 'from' pada komentar pengguna sering tidak dikembalikan oleh API; tanpa itu edge tidak dibuat.

Alternatif riset yang lebih lengkap: Meta Content Library & API (akses lewat aplikasi peneliti
ke Meta; dijalankan di lingkungan Meta) — integrasikan hanya setelah akses disetujui.
"""
import os

from .base import Collector, JobConfig, NotConfigured
from .http import check, make_client

API = "https://graph.facebook.com/v25.0"


class FacebookPagesCollector(Collector):
    platform = "facebook"

    def __init__(self, token=None, page_ids=None, transport=None, max_posts_per_page=100, **kw):
        super().__init__(**kw)
        self.token = token or os.environ.get("META_ACCESS_TOKEN")
        ids = page_ids or [p for p in os.environ.get("FB_PAGE_IDS", "").split(",") if p]
        if not (self.token and ids):
            raise NotConfigured("META_ACCESS_TOKEN dan FB_PAGE_IDS belum tersedia")
        self.page_ids = ids
        self.http = make_client(transport)
        self.max_posts = max_posts_per_page
        self._names: dict[str, str | None] = {}

    def _get(self, path, params):
        return check(self.http.get(f"{API}/{path}", params={**params, "access_token": self.token}))

    def _paged(self, path, params, cap):
        n = 0
        while True:
            res = self.with_backoff(self._get, path, params)
            for d in res.get("data", []):
                yield d
                n += 1
                if n >= cap:
                    return
            nxt = res.get("paging", {}).get("cursors", {}).get("after")
            if not (nxt and res.get("paging", {}).get("next")):
                return
            params = {**params, "after": nxt}

    def page_name(self, page):
        """Nama publik Page (entitas publik), di-cache. Gagal mengambil nama -> None (node tampil sebagai ID)."""
        if page not in self._names:
            try:
                self._names[page] = self.with_backoff(self._get, page, {"fields": "name"}).get("name")
            except Exception:  # noqa: BLE001 - nama hanya label tampilan
                self._names[page] = None
        return self._names[page]

    def fetch(self, job: JobConfig):
        for page in self.page_ids:
            name = self.page_name(page)
            for p in self._paged(f"{page}/posts", {"fields": "id,message,created_time,permalink_url,shares,reactions.summary(true).limit(0),comments.summary(true).limit(0)",
                                                    "since": job.date_from, "until": job.date_to, "limit": 50}, self.max_posts):
                eng = (p.get("reactions", {}).get("summary", {}).get("total_count", 0) + p.get("comments", {}).get("summary", {}).get("total_count", 0)
                       + p.get("shares", {}).get("count", 0))
                yield {"id": p["id"], "author": page, "author_type": "organization_public", "page_name": name, "ts": p["created_time"],
                       "text": p.get("message", ""), "url": p.get("permalink_url"), "likes": eng}
                for c in self._paged(f"{p['id']}/comments", {"fields": "id,message,created_time,from,like_count,parent{id,from}", "filter": "stream", "limit": 100}, 2000):
                    who = (c.get("from") or {}).get("id")
                    parent_who = ((c.get("parent") or {}).get("from") or {}).get("id")
                    if c.get("parent"):
                        inter = [(parent_who, "comment_reply")] if (who and parent_who) else []
                    else:
                        inter = [(page, "comment")] if who else []
                    yield {"id": c["id"], "author": who or "fb_unknown_commenter", "ts": c["created_time"], "text": c.get("message", ""),
                           "url": p.get("permalink_url"), "likes": c.get("like_count", 0), "reply_to": f"facebook:{(c.get('parent') or {}).get('id') or p['id']}",
                           "_thread": p["id"], "_interactions": inter}

    def author_key(self, native_author_id) -> str:
        sid = str(native_author_id)
        if sid in self.page_ids:
            return f"page:{sid}"  # Page publik = entitas publik, tidak dipseudonimkan
        return "fb_unknown_commenter" if sid == "fb_unknown_commenter" else super().author_key(sid)

    def to_record(self, raw, job, matched):
        rec = self.base_record(native_post_id=raw["id"], native_author_id=raw["author"], ts=raw["ts"], text=raw["text"],
                               url=raw["url"], job=job, matched=matched, reply_to=raw.get("reply_to"), engagement_count=raw.get("likes", 0))
        # Page = entitas publik: nama publiknya disimpan (author.public_entity_name). Komentator tetap pseudonim.
        if raw.get("author_type") == "organization_public":
            rec["author_type"] = "organization_public"
            if raw.get("page_name"):
                rec["public_entity_name"] = raw["page_name"]
        return rec


def resolve_pages(names, token=None, transport=None) -> list[dict]:
    """Cari ID & nama Page dari nama pengguna atau URL (mis. 'bnptri', 'https://www.facebook.com/kemenag.ri')."""
    import re
    token = token or os.environ.get("META_ACCESS_TOKEN")
    if not token:
        raise NotConfigured("META_ACCESS_TOKEN belum tersedia")
    http, out = make_client(transport), []
    for raw in names:
        handle = re.sub(r"^(https?://)?(www\.|m\.)?facebook\.com/", "", raw.strip()).strip("/").split("?")[0]
        if not handle:
            continue
        r = http.get(f"{API}/{handle}", params={"fields": "id,name,link", "access_token": token})
        j = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        out.append({"input": raw, "id": j.get("id", ""), "name": j.get("name", ""), "link": j.get("link", ""),
                    "error": (j.get("error") or {}).get("message", "") if r.status_code != 200 else ""})
    return out
