"""Kerangka konektor (Bagian 4).

Setiap konektor:
- hanya memakai API resmi / RSS / sumber yang mengizinkan pengambilan data;
- tidak melewati CAPTCHA, login, paywall, atau komunitas privat;
- menghormati rate limit (backoff eksponensial) dan mencatat setiap run ke audit log;
- memseudonimkan akun individual SEBELUM data disimpan;
- menandai setiap record dengan source_method dan is_synthetic=False.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..privacy import content_hash, pseudonymize, retention_until


class NotConfigured(RuntimeError):
    """Kredensial/izin resmi belum tersedia — konektor tidak dijalankan."""


@dataclass
class JobConfig:
    platform: str
    query: str
    date_from: str
    date_to: str
    language: str = "id"
    max_records: int = 1000
    interval_minutes: int | None = None
    legal_basis: str = ""
    query_native: str | None = None  # query dalam sintaks asli platform (opsional)


@dataclass
class RunReport:
    status: str = "running"
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0
    errors: list = field(default_factory=list)


class Collector(ABC):
    platform: str = "base"
    source_method: str = "official_api"

    def __init__(self, max_retries: int = 5):
        self.max_retries = max_retries
        self._seen: set[str] = set()

    @abstractmethod
    def fetch(self, job: JobConfig):
        """Generator item mentah dari sumber resmi."""

    @abstractmethod
    def to_record(self, raw: dict, job: JobConfig, matched: list[str]) -> dict:
        """Petakan item mentah ke skema post standar."""

    def with_backoff(self, fn, *a, **kw):
        for attempt in range(self.max_retries):
            try:
                return fn(*a, **kw)
            except RateLimited as e:
                time.sleep(min(900, (2 ** attempt) * (e.retry_after or 5)))
        raise RuntimeError("Rate limit berulang; run ditandai rate_limited")

    def run(self, job: JobConfig, predicate, matcher, keep_unmatched_comments: bool = True):
        """Jalankan job. Mengembalikan (records, interactions, report).

        predicate: fungsi Boolean dari compile_query. Unggahan utama yang tidak lolos dibuang.
        Komentar/balasan pada unggahan yang lolos tetap disimpan (keep_unmatched_comments) karena
        merupakan bagian percakapan; kolom keyword_matched mencatat apakah komentar itu sendiri cocok.
        """
        if not job.legal_basis:
            raise NotConfigured("legal_basis wajib diisi (ToS/izin akses yang menjadi dasar pengambilan)")
        rep, out, inter = RunReport(), [], []
        kept_parents: set[str] = set()
        try:
            for raw in self.fetch(job):
                rep.fetched += 1
                text = raw.get("text") or ""
                parent = raw.get("_thread")
                if not predicate(text) and not (keep_unmatched_comments and parent and parent in kept_parents):
                    continue
                if not parent:
                    kept_parents.add(str(raw.get("id")))
                rec = self.to_record(raw, job, matcher(text))
                key = rec["content_hash"] + rec["author_id_pseudonym"] + rec["timestamp"]
                if key in self._seen:
                    rep.duplicates += 1
                    continue
                self._seen.add(key)
                for tgt_native, itype in raw.get("_interactions", []):
                    if tgt_native is None or str(tgt_native) == str(raw.get("author")):
                        continue
                    inter.append({"source": rec["author_id_pseudonym"], "target": self.author_key(tgt_native),
                                  "type": itype, "post_id": rec["post_id"], "timestamp": rec["timestamp"], "platform": self.platform})
                out.append(rec)
                rep.inserted += 1
                if rep.inserted >= job.max_records:
                    break
            rep.status = "success"
        except Exception as e:  # dicatat, tidak ditelan diam-diam
            rep.status = "partial" if out else "failed"
            rep.errors.append(repr(e))
        return out, inter, rep

    def author_key(self, native_author_id) -> str:
        return pseudonymize(self.platform, str(native_author_id))

    # util umum
    def base_record(self, *, native_post_id, native_author_id, ts, text, url, job, matched, **extra):
        return {
            "post_id": f"{self.platform}:{native_post_id}", "platform": self.platform, "timestamp": ts,
            "text": text, "url": url, "author_id_pseudonym": self.author_key(native_author_id),
            "language": job.language, "keyword_matched": matched, "reply_to": extra.get("reply_to"),
            "mention": extra.get("mention", []), "repost_of": extra.get("repost_of"),
            "engagement_count": extra.get("engagement_count", 0),
            "collection_time": datetime.now(timezone.utc).isoformat(), "source_method": self.source_method,
            "is_synthetic": False, "content_hash": content_hash(text), "retention_until": str(retention_until()),
        }


class RateLimited(Exception):
    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
