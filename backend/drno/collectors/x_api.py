"""X API v2 resmi — Recent Search (7 hari terakhir). Token: X_BEARER_TOKEN.

Biaya: X memakai harga pay-per-use (dibebankan per post dan per profil yang dikembalikan).
Tetapkan max_records secara ketat dan pantau konsol developer X.

Interaksi teramati dari metadata resmi:
- reply   : in_reply_to_user_id
- mention : entities.mentions[].id
- repost  : referenced_tweets type 'retweeted' -> penulis post asal (includes.tweets)
- quote   : referenced_tweets type 'quoted'    -> penulis post asal
"""
import os

from .base import Collector, JobConfig, NotConfigured
from .http import check, make_client

API = "https://api.x.com/2"


class XCollector(Collector):
    platform = "x"

    def __init__(self, bearer: str | None = None, transport=None, **kw):
        super().__init__(**kw)
        self.token = bearer or os.environ.get("X_BEARER_TOKEN")
        if not self.token:
            raise NotConfigured("X_BEARER_TOKEN dari X API resmi belum tersedia")
        self.http = make_client(transport)
        self.http.headers["Authorization"] = f"Bearer {self.token}"

    def _get(self, params):
        return check(self.http.get(f"{API}/tweets/search/recent", params=params))

    @staticmethod
    def to_x_query(job: JobConfig) -> str:
        """X memakai sintaks sendiri: spasi=AND, OR, -istilah=NOT, "frasa". Dipakai bila job.query_native kosong."""
        q = job.query.replace(" AND NOT ", " -").replace(" AND ", " ").replace("NOT ", "-")
        lang = {"id": "in"}.get(job.language, job.language)  # X memakai kode 'in' untuk bahasa Indonesia
        return f"({q}) lang:{lang} -is:retweet" if lang else q

    def fetch(self, job: JobConfig):
        token, n = None, 0
        while n < job.max_records:
            res = self.with_backoff(self._get, {
                "query": job.query_native or self.to_x_query(job), "max_results": min(100, max(10, job.max_records - n)),
                "start_time": f"{job.date_from}T00:00:00Z" if job.date_from else None,
                "tweet.fields": "created_at,author_id,lang,public_metrics,referenced_tweets,entities,in_reply_to_user_id,conversation_id",
                "expansions": "author_id,referenced_tweets.id,referenced_tweets.id.author_id,entities.mentions.username,in_reply_to_user_id",
                "user.fields": "username", **({"next_token": token} if token else {})})
            ref_author = {t["id"]: t.get("author_id") for t in res.get("includes", {}).get("tweets", [])}
            for t in res.get("data", []):
                n += 1
                inter = []
                if t.get("in_reply_to_user_id"):
                    inter.append((t["in_reply_to_user_id"], "reply"))
                for m in t.get("entities", {}).get("mentions", []):
                    if m.get("id") and m["id"] != t.get("in_reply_to_user_id"):
                        inter.append((m["id"], "mention"))
                for ref in t.get("referenced_tweets", []):
                    if ref["type"] in ("retweeted", "quoted") and ref_author.get(ref["id"]):
                        inter.append((ref_author[ref["id"]], "repost"))
                pm = t.get("public_metrics", {})
                yield {"id": t["id"], "author": t["author_id"], "ts": t["created_at"], "text": t["text"],
                       "url": f"https://x.com/i/web/status/{t['id']}", "lang": t.get("lang"),
                       "likes": sum(pm.get(k, 0) for k in ("like_count", "retweet_count", "reply_count", "quote_count")),
                       "reply_to": next((f"x:{r['id']}" for r in t.get("referenced_tweets", []) if r["type"] == "replied_to"), None),
                       "repost_of": next((f"x:{r['id']}" for r in t.get("referenced_tweets", []) if r["type"] in ("retweeted", "quoted")), None),
                       "_interactions": inter}
            token = res.get("meta", {}).get("next_token")
            if not token:
                break

    def to_record(self, raw, job, matched):
        rec = self.base_record(native_post_id=raw["id"], native_author_id=raw["author"], ts=raw["ts"], text=raw["text"],
                               url=raw["url"], job=job, matched=matched, reply_to=raw.get("reply_to"),
                               repost_of=raw.get("repost_of"), engagement_count=raw.get("likes", 0),
                               mention=[self.author_key(t) for t, ty in raw["_interactions"] if ty == "mention"])
        rec["language"] = raw.get("lang") or job.language
        return rec
