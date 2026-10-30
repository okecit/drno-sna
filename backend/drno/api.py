"""FastAPI — layanan analisis (tahap prototipe: sumber data sintetis di memori).

Endpoint utama:
  GET /health
  GET /overview                       ringkasan + tren mingguan
  GET /network?start=&end=&types=&platforms=&community=   graf interaksi (JSON Cytoscape)
  GET /narratives                     topik/konteks/stance
  GET /temporal                       metrik jaringan per periode
  GET /export/{fmt}                   csv | json | graphml | gexf
Setiap respons memuat {"is_synthetic": true} selama sumber masih sintetis.
"""
from __future__ import annotations

import os
import tempfile
from collections import Counter

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from . import sna
from .pipeline import run_synthetic

app = FastAPI(title="DRNO API", version="0.1.0")
_OUT = tempfile.mkdtemp(prefix="drno_")
_STATE = run_synthetic(_OUT)
SYN = {"is_synthetic": True, "notice": "DATA SINTETIS — bukan hasil crawling nyata"}


@app.get("/health")
def health():
    return {"status": "ok", **SYN}


@app.get("/overview")
def overview():
    posts = _STATE["posts"]
    weekly = Counter(p["timestamp"][:10] for p in posts)
    return {**SYN, "total_posts": len(posts), "total_accounts": _STATE["summary"]["n_nodes"],
            "total_interactions": len(_STATE["data"]["interactions"]),
            "platforms": Counter(p["platform"] for p in posts), "daily": dict(sorted(weekly.items()))}


@app.get("/network")
def network(start: str | None = None, end: str | None = None, types: list[str] | None = Query(None),
            platforms: list[str] | None = Query(None), community: int | None = None):
    G = sna.build_interaction_graph(_STATE["data"]["interactions"], types=types, platforms=platforms, start=start, end=end)
    summary, metrics, comm = sna.analyze(G)
    nodes = [{"data": {"id": n, "community": comm.get(n), **metrics[n]}} for n in G.nodes
             if community is None or comm.get(n) == community]
    keep = {x["data"]["id"] for x in nodes}
    edges = [{"data": {"source": s, "target": t, "weight": d["weight"], "types": d["types"], "evidence_n": len(d["evidence"])}}
             for s, t, d in G.edges(data=True) if s in keep and t in keep]
    return {**SYN, "summary": summary, "elements": {"nodes": nodes, "edges": edges},
            "caution": "Sentralitas = posisi struktural; bukan bukti afiliasi, peran, atau keterlibatan kriminal."}


@app.get("/narratives")
def narratives():
    posts = _STATE["posts"]
    return {**SYN, "context": Counter(p["context"] for p in posts), "stance": Counter(p["stance"] for p in posts),
            "sentiment": Counter(p["sentiment"] for p in posts), "manual_review_queue": len(_STATE["queue"]),
            "model": "baseline-rules 0.1 (belum divalidasi pada gold standard)"}


@app.get("/platforms")
def platforms():
    """Klasifikasi konteks, stance, dan sentimen per platform."""
    out = {}
    for p in _STATE["posts"]:
        d = out.setdefault(p["platform"], {"posts": 0, "context": Counter(), "stance": Counter(), "sentiment": Counter()})
        d["posts"] += 1
        for k in ("context", "stance", "sentiment"):
            d[k][p[k]] += 1
    return {**SYN, "platforms": out}


@app.get("/temporal")
def temporal():
    return {**SYN, "periods": [{k: s[k] for k in ("period", "start", "end", "summary")} for s in _STATE["snaps"]]}


@app.get("/export/{fmt}")
def export(fmt: str):
    files = {"csv": "posts_SYNTHETIC.csv", "json": "summary_SYNTHETIC.json",
             "graphml": "interaction_network_SYNTHETIC.graphml", "gexf": "interaction_network_SYNTHETIC.gexf"}
    if fmt not in files:
        raise HTTPException(404, "format: csv | json | graphml | gexf")
    return FileResponse(os.path.join(_OUT, files[fmt]), filename=files[fmt])
