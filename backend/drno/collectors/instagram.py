"""Instagram Graph API — Hashtag Search (resmi).

Syarat (Meta): akun Instagram Business/Creator terhubung ke Facebook Page, aplikasi Meta dengan
fitur *Instagram Public Content Access* yang lolos App Review, dan User access token.
Kredensial: META_ACCESS_TOKEN, IG_USER_ID.

Batasan resmi yang memengaruhi desain riset:
- maksimal 30 hashtag unik per 7 hari bergulir per akun;
- recent_media hanya mengembalikan media 24 jam terakhir -> harus dijadwalkan harian;
- field username/pemilik TIDAK dapat diminta -> tidak ada node akun, tidak ada jaringan interaksi;
- hashtag yang dianggap sensitif oleh Meta mengembalikan error generik.
Karena itu data IG di DRNO hanya dipakai untuk analisis konten (konteks, stance, sentimen),
tidak untuk SNA.
"""
import os

import httpx

from .base import Collector, JobConfig, NotConfigured
from .http import check, make_client

API = "https://graph.facebook.com/v25.0"
UNKNOWN_OWNER = "ig_hashtag_media"  # penanda: pemilik tidak tersedia dari API


class InstagramHashtagCollector(Collector):
    platform = "instagram"

    def __init__(self, token=None, ig_user_id=None, hashtags=None, transport=None, include_top=False, **kw):
        super().__init__(**kw)
        self.token = token or os.environ.get("META_ACCESS_TOKEN")
        self.user = ig_user_id or os.environ.get("IG_USER_ID")
        if not (self.token and self.user):
            raise NotConfigured("META_ACCESS_TOKEN dan IG_USER_ID (akun Business/Creator) belum tersedia")
        self.hashtags = hashtags or []
        if len(self.hashtags) > 30:
            raise ValueError("Instagram membatasi 30 hashtag unik per 7 hari; kurangi daftar")
        self.http = make_client(transport)
        self.include_top = include_top
        self.skipped: list[tuple[str, str]] = []  # (hashtag, alasan)

    def _get(self, path, params):
        return check(self.http.get(f"{API}/{path}", params={**params, "access_token": self.token}))

    def fetch(self, job: JobConfig):
        for tag in self.hashtags:
            tag = tag.lstrip("#").lower().replace(" ", "")
            try:
                hid = self.with_backoff(self._get, "ig_hashtag_search", {"user_id": self.user, "q": tag})["data"][0]["id"]
            except (httpx.HTTPStatusError, IndexError, KeyError) as e:
                self.skipped.append((tag, f"hashtag ditolak/tidak ditemukan: {e.__class__.__name__}"))
                continue
            for edge in ["recent_media"] + (["top_media"] if self.include_top else []):
                after = None
                while True:
                    res = self.with_backoff(self._get, f"{hid}/{edge}", {
                        "user_id": self.user, "limit": 50, "fields": "id,caption,media_type,comments_count,like_count,permalink,timestamp",
                        **({"after": after} if after else {})})
                    for m in res.get("data", []):
                        if not m.get("timestamp"):
                            continue
                        yield {"id": m["id"], "author": UNKNOWN_OWNER, "ts": m["timestamp"], "text": m.get("caption") or "",
                               "url": m.get("permalink"), "likes": (m.get("like_count") or 0) + (m.get("comments_count") or 0),
                               "hashtag": tag}
                    after = res.get("paging", {}).get("cursors", {}).get("after") if res.get("paging", {}).get("next") else None
                    if not after:
                        break

    def author_key(self, native_author_id) -> str:
        return UNKNOWN_OWNER if native_author_id == UNKNOWN_OWNER else super().author_key(native_author_id)

    def to_record(self, raw, job, matched):
        return self.base_record(native_post_id=raw["id"], native_author_id=raw["author"], ts=raw["ts"], text=raw["text"],
                                url=raw["url"], job=job, matched=matched, engagement_count=raw.get("likes", 0))
