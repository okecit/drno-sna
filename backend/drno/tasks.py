"""Scheduler (Celery + Redis). Menjalankan job pengumpulan sesuai interval & batas API.

celery -A drno.tasks worker -B --loglevel=info
"""
import os

from celery import Celery

from .collectors.base import JobConfig, NotConfigured
from .keywords import KeywordDictionary, compile_query

app = Celery("drno", broker=os.environ.get("REDIS_URL", "redis://redis:6379/0"))
app.conf.beat_schedule = {
    # contoh: tiap 6 jam; jadwal nyata disimpan di tabel collection_job
    "youtube-6h": {"task": "drno.tasks.collect", "schedule": 6 * 3600,
                   "args": ("youtube", '(radikalisasi OR terorisme OR "kontra-narasi") AND NOT "lowongan"')},
    "x-6h": {"task": "drno.tasks.collect", "schedule": 6 * 3600,
             "args": ("x", '(radikalisasi OR terorisme OR deradikalisasi OR "kontra-narasi")')},
    # recent_media IG hanya 24 jam -> wajib harian
    "instagram-daily": {"task": "drno.tasks.collect", "schedule": 24 * 3600, "args": ("instagram", "")},
    "facebook-daily": {"task": "drno.tasks.collect", "schedule": 24 * 3600,
                       "args": ("facebook", '(radikalisasi OR terorisme OR deradikalisasi OR "kontra-narasi")')},
}


@app.task(bind=True, max_retries=3, default_retry_delay=600)
def collect(self, platform: str, query: str):
    from .collectors.facebook import FacebookPagesCollector
    from .collectors.instagram import InstagramHashtagCollector
    from .collectors.x_api import XCollector
    from .collectors.youtube import YouTubeCollector
    from .storage import get_store
    registry = {"youtube": YouTubeCollector, "x": XCollector, "facebook": FacebookPagesCollector,
                "instagram": lambda: InstagramHashtagCollector(hashtags=os.environ.get("IG_HASHTAGS", "").split(","))}
    try:
        col = registry[platform]()
    except (KeyError, NotConfigured) as e:
        return {"status": "skipped", "reason": str(e)}  # dicatat, tidak dipaksa
    kd = KeywordDictionary.baseline()
    from datetime import date, timedelta
    today = date.today()
    job = JobConfig(platform=platform, query=query or "*", date_from=(today - timedelta(days=7)).isoformat(),
                    date_to=today.isoformat(),
                    legal_basis=os.environ.get("DRNO_LEGAL_BASIS_" + platform.upper(), ""))
    pred = (lambda t: True) if platform == "instagram" else compile_query(query)
    records, inter, rep = col.run(job, pred, kd.match)
    return get_store().save(records, inter, rep, job)
