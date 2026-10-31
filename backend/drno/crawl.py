"""Crawling NYATA melalui API resmi.

Contoh:
  python -m drno.crawl x --query '(radikalisasi OR terorisme OR "kontra-narasi") AND NOT lowongan' --from 2026-10-15 --to 2026-10-22 --max 300
  python -m drno.crawl youtube --query 'deradikalisasi' --from 2026-09-01 --to 2026-10-22 --max-videos 20
  python -m drno.crawl instagram --hashtags moderasiberagama,kontranarasi --from 2026-10-21 --to 2026-10-22
  python -m drno.crawl facebook --from 2026-10-01 --to 2026-10-22      # Page dari FB_PAGE_IDS
Setelah itu:  python -m drno.analyze --out exports_real
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .collectors.base import JobConfig, NotConfigured
from .keywords import DEFAULT_QUERY, KeywordDictionary, compile_query
from .storage import get_store


def build(platform, a):
    if platform == "x":
        from .collectors.x_api import XCollector
        return XCollector()
    if platform == "youtube":
        from .collectors.youtube import YouTubeCollector
        return YouTubeCollector(max_videos=a.max_videos)
    if platform == "instagram":
        from .collectors.instagram import InstagramHashtagCollector
        return InstagramHashtagCollector(hashtags=[h for h in (a.hashtags or "").split(",") if h])
    if platform == "facebook":
        from .collectors.facebook import FacebookPagesCollector
        return FacebookPagesCollector()
    if platform == "web":
        from .collectors.web_scrapling import ScraplingWebCollector
        return ScraplingWebCollector(sources_path=a.sources)
    from .collectors.gated import get_restricted
    return get_restricted(platform)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="drno.crawl")
    ap.add_argument("platform", choices=["x", "youtube", "instagram", "facebook", "web", "tiktok", "telegram", "discord", "reddit"])
    ap.add_argument("--query", default=os.environ.get("DRNO_QUERY") or DEFAULT_QUERY,
                    help="Ekspresi Boolean DRNO (dipakai juga sebagai filter lokal)")
    ap.add_argument("--native-query", default=None, help="Query dalam sintaks asli platform (opsional)")
    ap.add_argument("--hashtags", default=None, help="Instagram: daftar hashtag dipisah koma (maks. 30 per 7 hari)")
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--lang", default="id")
    ap.add_argument("--max", type=int, default=500)
    ap.add_argument("--max-videos", type=int, default=20)
    ap.add_argument("--dry-run", action="store_true", help="tampilkan hasil tanpa menyimpan (uji sumber baru)")
    ap.add_argument("--sources", default=None, help="web: berkas konfigurasi sumber (default config/sources.json atau $DRNO_SOURCES)")
    a = ap.parse_args(argv)

    legal = os.environ.get(f"DRNO_LEGAL_BASIS_{a.platform.upper()}", "")
    if a.platform == "web" and not legal:
        legal = "per sumber: lihat legal_basis di config/sources.json"  # tiap sumber wajib punya legal_basis sendiri
    job = JobConfig(platform=a.platform, query=a.query, query_native=a.native_query, date_from=a.date_from, date_to=a.date_to,
                    language=a.lang, max_records=a.max, legal_basis=legal)
    try:
        col = build(a.platform, a)
        kd = KeywordDictionary.baseline()
        pred = (lambda t: True) if a.platform == "instagram" else compile_query(a.query)  # IG sudah tersaring hashtag
        records, inter, rep = col.run(job, pred, kd.match)
    except NotConfigured as e:
        print(f"[DRNO] Konektor {a.platform} tidak dijalankan: {e}", file=sys.stderr)
        return 2
    if a.dry_run:
        for r in records[:20]:
            print(f"- {r['timestamp'][:10]} | {r['author_id_pseudonym']} | {r['text'][:110]}")
        print(json.dumps({"dry_run": True, "status": rep.status, "fetched": rep.fetched, "matched": len(records),
                          "blocked": getattr(col, "blocked", {}), "skipped": getattr(col, "skipped", [])[:20]}, ensure_ascii=False, indent=2))
        return 0
    run = get_store().save(records, inter, rep, job)
    skipped = getattr(col, "skipped", [])
    print(json.dumps({**run, "interactions": len(inter), "skipped": skipped}, ensure_ascii=False, indent=2))
    return 0 if rep.status in ("success", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
