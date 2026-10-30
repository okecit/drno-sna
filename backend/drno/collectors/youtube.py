"""YouTube Data API v3 (resmi). Kunci: YOUTUBE_API_KEY. Kuota harian Google berlaku
(search.list mahal dibanding commentThreads.list; atur max_records & interval).

Interaksi teramati:
- comment       : penulis komentar  -> kanal pemilik video
- comment_reply : penulis balasan   -> penulis komentar induk
"""
import os

from .base import Collector, JobConfig, NotConfigured, RateLimited
from .http import check, make_client

API = "https://www.googleapis.com/youtube/v3"


class YouTubeCollector(Collector):
    platform = "youtube"

    def __init__(self, api_key: str | None = None, transport=None, max_videos: int = 50, **kw):
        super().__init__(**kw)
        self.key = api_key or os.environ.get("YOUTUBE_API_KEY")
        if not self.key:
            raise NotConfigured("YOUTUBE_API_KEY belum diisi")
        self.http = make_client(transport)
        self.max_videos = max_videos

    def _get(self, path, params):
        r = self.http.get(f"{API}/{path}", params={**params, "key": self.key})
        if r.status_code == 403 and "quota" in r.text.lower():
            raise RateLimited(retry_after=3600)
        if r.status_code == 403 and "commentsdisabled" in r.text.lower():
            return {"items": []}
        return check(r)

    def fetch(self, job: JobConfig):
        page, n = None, 0
        while n < self.max_videos:
            res = self.with_backoff(self._get, "search", {
                "part": "snippet", "q": job.query_native or job.query, "type": "video", "maxResults": 50, "order": "date",
                "publishedAfter": f"{job.date_from}T00:00:00Z", "publishedBefore": f"{job.date_to}T23:59:59Z",
                "relevanceLanguage": job.language, "regionCode": "ID", **({"pageToken": page} if page else {})})
            for it in res.get("items", []):
                n += 1
                sn, vid = it["snippet"], it["id"]["videoId"]
                yield {"id": vid, "author": sn["channelId"], "ts": sn["publishedAt"], "text": f'{sn["title"]}. {sn.get("description", "")}',
                       "url": f"https://www.youtube.com/watch?v={vid}"}
                yield from self._comments(vid, sn["channelId"])
                if n >= self.max_videos:
                    break
            page = res.get("nextPageToken")
            if not page:
                break

    def _comments(self, vid, owner):
        page = None
        while True:
            res = self.with_backoff(self._get, "commentThreads", {"part": "snippet,replies", "videoId": vid, "maxResults": 100,
                                                                   "textFormat": "plainText", **({"pageToken": page} if page else {})})
            for th in res.get("items", []):
                top = th["snippet"]["topLevelComment"]
                s = top["snippet"]
                a = s.get("authorChannelId", {}).get("value")
                yield {"id": top["id"], "author": a or "anon", "ts": s["publishedAt"], "text": s.get("textOriginal", ""),
                       "url": f"https://www.youtube.com/watch?v={vid}&lc={top['id']}", "likes": s.get("likeCount", 0),
                       "reply_to": f"youtube:{vid}", "_thread": vid, "_interactions": [(owner, "comment")] if a else []}
                for rp in th.get("replies", {}).get("comments", []):
                    r = rp["snippet"]
                    ra = r.get("authorChannelId", {}).get("value")
                    yield {"id": rp["id"], "author": ra or "anon", "ts": r["publishedAt"], "text": r.get("textOriginal", ""),
                           "url": f"https://www.youtube.com/watch?v={vid}&lc={rp['id']}", "likes": r.get("likeCount", 0),
                           "reply_to": f"youtube:{top['id']}", "_thread": vid, "_interactions": [(a, "comment_reply")] if (ra and a) else []}
            page = res.get("nextPageToken")
            if not page:
                break

    def to_record(self, raw, job, matched):
        return self.base_record(native_post_id=raw["id"], native_author_id=raw["author"], ts=raw["ts"], text=raw["text"],
                                url=raw["url"], job=job, matched=matched, reply_to=raw.get("reply_to"),
                                engagement_count=raw.get("likes", 0))
