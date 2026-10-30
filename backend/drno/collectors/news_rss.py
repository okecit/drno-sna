"""Portal berita Indonesia via RSS publik. Hanya judul, ringkasan, tanggal, sumber, tautan.
Teks lengkap artikel TIDAK diunduh (hak cipta & ToS); akun = media (entitas publik)."""
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from .base import Collector, JobConfig


class NewsRSSCollector(Collector):
    platform = "news"
    source_method = "rss"

    def __init__(self, feeds: dict[str, str], **kw):
        super().__init__(**kw)
        self.feeds = feeds  # {nama_media: url_rss} — diisi peneliti dari RSS resmi media

    def fetch(self, job: JobConfig):
        for media, url in self.feeds.items():
            r = httpx.get(url, timeout=30, headers={"User-Agent": "DRNO-research/0.1 (akademik)"})
            r.raise_for_status()
            for item in ET.fromstring(r.content).iter("item"):
                ts = parsedate_to_datetime(item.findtext("pubDate")).isoformat()
                if not (job.date_from <= ts[:10] <= job.date_to):
                    continue
                yield {"id": item.findtext("link"), "author": media, "ts": ts, "url": item.findtext("link"),
                       "text": f'{item.findtext("title") or ""}. {item.findtext("description") or ""}'}

    def to_record(self, raw, job, matched):
        rec = self.base_record(native_post_id=raw["id"], native_author_id=raw["author"], ts=raw["ts"], text=raw["text"],
                               url=raw["url"], job=job, matched=matched)
        rec["author_id_pseudonym"] = f"media:{raw['author']}"  # entitas publik, bukan individu
        return rec
