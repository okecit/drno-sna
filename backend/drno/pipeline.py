"""Pipeline riset otomatis (Extended Module F):
Keyword Dictionary → Data Collection → Cleaning → Context Classification → NLP →
Network Construction → SNA → Dashboard → Research Export.

Jalankan demonstrasi sintetis:  python -m drno.pipeline --synthetic --out ../exports
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from . import nlp, sna
from .synthetic import generate, periods


def run_synthetic(out_dir: str, seed: int = 7) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = generate(seed)
    posts, inter, authors = data["posts"], data["interactions"], data["authors"]

    # NLP (baseline)
    clf = nlp.BaselineClassifier()
    ann = {}
    for p in posts:
        preds = nlp.annotate(p, clf)
        ann[p["post_id"]] = preds
        d = {x.task: x for x in preds}
        p.update(context=d["context"].label, context_conf=d["context"].confidence,
                 stance=d["stance"].label, sentiment=d["sentiment"].label,
                 uncertain=d["context"].is_uncertain)
    queue = nlp.manual_review_queue(ann)

    # SNA — jaringan interaksi (keseluruhan)
    meta = {a["author_pseudonym"]: {"platform": a["platform"], "author_type": a["author_type"]} for a in authors}
    G = sna.build_interaction_graph(inter, nodes_meta=meta)
    summary, metrics, comm = sna.analyze(G)
    # Jaringan ko-okurensi narasi — terpisah
    N = sna.build_narrative_cooccurrence(posts)
    nsum, nmet, ncomm = sna.analyze(N)
    # Temporal (mingguan)
    snaps = sna.temporal_snapshots(inter, periods(), nodes_meta=meta)

    # ---- Ekspor ----
    sna.export_graph(G, str(out / "interaction_network_SYNTHETIC"))
    sna.export_graph(N, str(out / "narrative_cooccurrence_SYNTHETIC"))
    fields = ["post_id", "platform", "timestamp", "text", "url", "author_id_pseudonym", "language", "keyword_matched",
              "reply_to", "mention", "repost_of", "engagement_count", "collection_time", "source_method", "is_synthetic",
              "context", "context_conf", "stance", "sentiment", "uncertain"]
    with open(out / "posts_SYNTHETIC.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for p in posts:
            w.writerow({**p, "keyword_matched": ";".join(p["keyword_matched"]), "mention": ";".join(p["mention"])})
    json.dump({"meta": data["meta"], "summary": summary, "narrative_summary": nsum,
               "dictionary_history": data["dictionary"].history(), "manual_review_queue_size": len(queue),
               "temporal": [{k: v for k, v in s.items() if k in ("period", "start", "end", "summary")} for s in snaps]},
              open(out / "summary_SYNTHETIC.json", "w"), ensure_ascii=False, indent=2)
    return {"data": data, "G": G, "N": N, "summary": summary, "nsum": nsum, "metrics": metrics, "comm": comm,
            "snaps": snaps, "queue": queue, "posts": posts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true", required=True,
                    help="Hanya mode sintetis tersedia sampai konektor resmi dikonfigurasi")
    ap.add_argument("--out", default="exports")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    r = run_synthetic(a.out, a.seed)
    print(json.dumps(r["summary"], indent=2), "\nnarasi:", json.dumps(r["nsum"]), "\nantrean validasi:", len(r["queue"]))


if __name__ == "__main__":
    main()
