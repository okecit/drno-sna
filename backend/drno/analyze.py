"""Analisis & ekspor untuk dashboard — berlaku sama untuk data NYATA dan SINTETIS.

  python -m drno.analyze --out exports_real                 # baca store (JSONL/PostgreSQL)
  python -m drno.analyze --out exports_real --sentiment-model w11wo/indonesian-roberta-base-sentiment-classifier

Menghasilkan CSV yang strukturnya sama dengan dataset dashboard, termasuk rincian per platform:
platform_context.csv, platform_sentiment.csv, platform_stance.csv, platform_summary.csv.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from . import discovery, explorer, nlp, sna
from .keywords import KeywordDictionary

PLATFORM_NOTES = {
    "x": "Recent search 7 hari; interaksi reply/mention/repost tersedia",
    "youtube": "Video + komentar publik; interaksi komentar dan balasan",
    "instagram": "Hashtag search: tanpa pemilik akun, tanpa jaringan; konten saja",
    "facebook": "Page terpilih (PPCA); komentator sering tidak teridentifikasi",
    "news": "RSS & Scrapling (sitemap, robots.txt dipatuhi); akun = media; teks tidak ditayangkan",
    "reddit": "Belum diimplementasikan untuk data nyata",
}


class TransformerSentiment:  # pragma: no cover - unduh model
    def __init__(self, model):
        from transformers import pipeline
        self.p = pipeline("text-classification", model=model, truncation=True)
        self.name = model

    def __call__(self, text):
        r = self.p(text[:1000])[0]
        lab = r["label"].lower()
        lab = {"positive": "positif", "negative": "negatif", "neutral": "netral"}.get(lab, lab)
        return nlp.Prediction("sentiment", lab, round(float(r["score"]), 3), self.name, "hf")


def week_start(ts: str) -> date:
    d = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    return d - timedelta(days=d.weekday())


def annotate_all(posts, sentiment_model=None):
    clf = nlp.BaselineClassifier()
    tsent = TransformerSentiment(sentiment_model) if sentiment_model else None
    ann = {}
    for p in posts:
        ctx = clf.context(p["text"])
        sen = tsent(p["text"]) if tsent else clf.sentiment(p["text"])
        preds = [ctx, clf.stance(ctx), sen]
        ann[p["post_id"]] = preds
        p["emotion"] = nlp.emotion(p["text"]).label
        p.update(context=ctx.label, context_conf=ctx.confidence, stance=preds[1].label, sentiment=sen.label,
                 sentiment_conf=sen.confidence, uncertain=ctx.is_uncertain)
    return ann


def export_dashboard(posts, inter, out, mode: str, sentiment_model=None, public_names: dict | None = None):
    """public_names: {pseudonim: {"type", "name"}} hanya untuk entitas publik (kanal, media, Page)."""
    public_names = public_names or {}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if not posts:
        raise SystemExit("Tidak ada unggahan di store. Jalankan drno.crawl dulu.")
    ann = annotate_all(posts, sentiment_model)
    queue = nlp.manual_review_queue(ann)
    kd = KeywordDictionary.baseline()
    for p in posts:
        if not p.get("keyword_matched"):
            p["keyword_matched"] = kd.match(p["text"])
    triggers = {t for t, e in kd.current.terms.items() if discovery.TRIGGER_GROUPS & set(e["groups"])}
    weeks = sorted({week_start(p["timestamp"]) for p in posts})
    wlab = {w: f"W{w.isocalendar()[1]:02d}-{w.year}" for w in weeks}
    lab = lambda ts: wlab[week_start(ts)]
    start = {v: k.isoformat() for k, v in wlab.items()}

    def w(name, rows, fields):
        with open(out / name, "w", newline="", encoding="utf-8") as f:
            cw = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            cw.writeheader()
            cw.writerows(rows)

    G = sna.build_interaction_graph(inter)
    summary, metrics, comm = sna.analyze(G) if G.number_of_edges() else ({"n_nodes": 0, "density": 0, "modularity": None}, {}, {})
    accounts = {p["author_id_pseudonym"] for p in posts if not p["author_id_pseudonym"].endswith(("_hashtag_media", "unknown_commenter"))}
    w("overview.csv", [{"total_posts": len(posts), "total_accounts": len(accounts), "total_interactions": len(inter),
                        "manual_review_queue": len(queue), "uncertain_share": round(sum(p["uncertain"] for p in posts) / len(posts), 4),
                        "network_density": summary.get("density"), "modularity": summary.get("modularity"),
                        "n_communities": len(set(comm.values())), "data_mode": mode}],
      ["total_posts", "total_accounts", "total_interactions", "manual_review_queue", "uncertain_share", "network_density", "modularity", "n_communities", "data_mode"])
    c = Counter((lab(p["timestamp"]), p["platform"]) for p in posts)
    w("weekly_platform.csv", [{"week": k[0], "week_start": start[k[0]], "platform": k[1], "posts": v} for k, v in sorted(c.items())], ["week", "week_start", "platform", "posts"])
    w("context_counts.csv", [{"context": k, "posts": v} for k, v in Counter(p["context"] for p in posts).most_common()], ["context", "posts"])
    sw = Counter((lab(p["timestamp"]), p["stance"]) for p in posts)
    w("stance_weekly.csv", [{"week": k[0], "week_start": start[k[0]], "stance": k[1], "posts": v} for k, v in sorted(sw.items())], ["week", "week_start", "stance", "posts"])
    kw = Counter(k for p in posts for k in p["keyword_matched"]); top = [k for k, _ in kw.most_common(8)]
    # Kata kunci pemicu (thaghut, kafir harbi, JI, ...) selalu ikut ditampilkan walau tidak masuk 8 teratas
    top += [k for k, _ in kw.most_common() if k in triggers and k not in top][:12]
    kwc = Counter((lab(p["timestamp"]), k) for p in posts for k in p["keyword_matched"] if k in top)
    w("keyword_weekly.csv", [{"week": wlab[x], "week_start": x.isoformat(), "keyword": k, "posts": kwc.get((wlab[x], k), 0)} for x in weeks for k in top], ["week", "week_start", "keyword", "posts"])
    # --- Kata kunci pemicu & usulan istilah tersembunyi (wajib ditinjau peneliti) ---
    w("trigger_terms.csv", discovery.trigger_counts(posts, kd),
      ["term", "group", "posts", "youtube", "news", "other", "first_seen", "last_seen", "spellings", "variants"])
    w("hidden_terms.csv", discovery.hidden_terms(posts, kd),
      ["term", "kind", "detail", "related_to", "posts_with_trigger", "posts_total", "lift", "zscore", "platforms"])

    # --- Rincian per platform ---
    for field, name in (("context", "platform_context.csv"), ("sentiment", "platform_sentiment.csv"), ("stance", "platform_stance.csv")):
        cc = Counter((p["platform"], p[field]) for p in posts)
        w(name, [{"platform": k[0], field: k[1], "posts": v} for k, v in sorted(cc.items())], ["platform", field, "posts"])
    rows = []
    for plat in sorted({p["platform"] for p in posts}):
        ps = [p for p in posts if p["platform"] == plat]
        rows.append({"platform": plat, "posts": len(ps), "accounts": len({p["author_id_pseudonym"] for p in ps} & accounts),
                     "interactions": sum(1 for i in inter if i["platform"] == plat),
                     "uncertain_share": round(sum(p["uncertain"] for p in ps) / len(ps), 4),
                     "violence_flag_review": sum(1 for p in ps if p["context"] == "dukungan_kekerasan"),
                     "note": PLATFORM_NOTES.get(plat, "")})
    w("platform_summary.csv", rows, ["platform", "posts", "accounts", "interactions", "uncertain_share", "violence_flag_review", "note"])

    # --- Modul eksplorasi: entitas, penyebutan kata kunci, sebaran wilayah ---
    w("entities.csv", explorer.entities(posts, inter, public_names, triggers, comm, metrics),
      ["entity_id", "display_name", "anon_label", "type", "platform", "posts", "trigger_posts", "engagement", "interactions_in", "interactions_out",
       "community", "pagerank", "first_seen", "last_seen", "top_keywords"])
    m_daily, m_public = explorer.mentions(posts, public_names, {t: e["groups"] for t, e in kd.current.terms.items()})
    w("mentions_daily.csv", m_daily, ["day", "keyword", "group", "platform", "posts"])
    w("mentions_public.csv", m_public, ["day", "source", "type", "platform", "keywords", "groups", "excerpt", "url", "engagement"])
    # Titik bocor: hanya istilah pemicu inti (kamus v1.0-v1.1), bukan istilah tinjauan yang bisa berupa kata umum
    coded = {t for t, e in kd.versions[1].terms.items() if discovery.TRIGGER_GROUPS & set(e["groups"])}
    l_sig, l_acc = explorer.leaks(posts, inter, public_names, coded)
    w("leak_signals.csv", l_sig, ["day", "platform", "entity_id", "anon_label", "signals", "coded_terms", "excerpt", "context"])
    w("leak_accounts.csv", l_acc, ["entity_id", "anon_label", "platform", "posts", "coded_posts", "migration_signals", "migration_types",
                                   "spaces", "top_terms", "first_seen", "last_seen", "score"])
    w("geo_provinces.csv", explorer.geo(posts, triggers),
      ["code", "province", "posts", "trigger_posts", "negative_posts", "positive_posts", "negative_share", "top_keywords"])

    if G.number_of_edges():
        nf = ["node_id", "platform", "author_type", "community", "degree", "in_degree", "out_degree", "betweenness", "closeness", "eigenvector", "pagerank"]
        plat_of = {}
        for p in posts:
            plat_of.setdefault(p["author_id_pseudonym"], p["platform"])
        for i in inter:
            plat_of.setdefault(i["target"], i["platform"])
        def atype(n):
            if n.startswith("media:"):
                return "media"
            if n.startswith("page:"):
                return "organization_public"
            return "channel" if public_names.get(n, {}).get("type") == "channel" else "individual"
        w("nodes.csv", [{"node_id": n, "platform": plat_of.get(n), "author_type": atype(n), "community": comm[n], **metrics[n]} for n in G.nodes], nf)
        ew = Counter((i["source"], i["target"], lab(i["timestamp"]), i["type"]) for i in inter)
        w("edges_weekly.csv", [{"source": k[0], "target": k[1], "week": k[2], "type": k[3], "count": v} for k, v in ew.items()], ["source", "target", "week", "type", "count"])
        periods = [(wlab[x], x.isoformat(), (x + timedelta(days=6)).isoformat()) for x in weeks]
        snaps = sna.temporal_snapshots(inter, periods)
        w("temporal.csv", [{"week": s["period"], "week_start": s["start"], **{k: s["summary"].get(k) for k in ("n_nodes", "n_edges", "density", "modularity", "n_components")}} for s in snaps],
          ["week", "week_start", "n_nodes", "n_edges", "density", "modularity", "n_components"])
        ccx = Counter((comm.get(p["author_id_pseudonym"]), p["context"]) for p in posts if p["author_id_pseudonym"] in comm)
        w("community_context.csv", [{"community": k[0], "context": k[1], "posts": v} for k, v in sorted(ccx.items())], ["community", "context", "posts"])
        topb = sorted(metrics, key=lambda n: -metrics[n]["betweenness"])[:8]
        w("position_change.csv", [{"week": s["period"], "week_start": s["start"], "node_id": n, "betweenness": s["metrics"].get(n, {}).get("betweenness", 0)} for s in snaps for n in topb],
          ["week", "week_start", "node_id", "betweenness"])
        sna.export_graph(G, str(out / f"interaction_network_{mode.upper()}"))
        export_sna_explorer(posts, inter, G, metrics, comm, w, real=(mode == "real"), public_names=public_names)
        # --- Lensa teori (v0.3) ---
        from .theory import ROLES, run_lenses
        L = run_lenses(G, posts, comm, metrics)
        w("broker_nodes.csv", L["broker_nodes"], ["node_id", "community", "constraint", "effective_size", "n_contacts", *ROLES, "total", "betweenness"])
        w("tie_summary.csv", L["tie_summary"], ["tie_type", "ties", "weak", "strong", "weak_share"])
        w("homophily.csv", L["homophily"], ["attribute", "ei_observed", "external_ties", "internal_ties", "ei_null_low", "ei_null_mean",
                                            "ei_null_high", "p_value", "assortativity", "labelled_nodes", "n_perm"])
        w("mixing_stance.csv", L["mixing_stance"], ["source_attr", "target_attr", "ties"])
        w("identity_markers.csv", L["identity"], ["community", "posts", "in_group_per_1k", "out_group_per_1k"])
    N = sna.build_narrative_cooccurrence(posts, keep=triggers)
    if N.number_of_edges():
        sna.analyze(N)
        terms = kd.current.terms
        w("narrative_nodes.csv", [{"term": n, "frequency": N.nodes[n]["frequency"], "group": "/".join(terms.get(n, {}).get("groups", [])),
                                   "baseline": terms.get(n, {}).get("baseline", False), "cluster": N.nodes[n]["community"]} for n in N.nodes],
          ["term", "frequency", "group", "baseline", "cluster"])
        w("narrative_edges.csv", [{"source": a, "target": b, "weight": d["weight"]} for a, b, d in N.edges(data=True)], ["source", "target", "weight"])
        sna.export_graph(N, str(out / f"narrative_cooccurrence_{mode.upper()}"))
    fields = ["post_id", "platform", "timestamp", "text", "url", "author_id_pseudonym", "language", "keyword_matched", "reply_to", "repost_of",
              "engagement_count", "source_method", "is_synthetic", "context", "context_conf", "stance", "sentiment", "sentiment_conf", "uncertain"]
    w(f"posts_{mode.upper()}.csv", [{**p, "keyword_matched": ";".join(p["keyword_matched"])} for p in posts], fields)
    w("manual_review_queue.csv", [{"post_id": pid} for pid in queue], ["post_id"])
    return {"posts": len(posts), "interactions": len(inter), "review_queue": len(queue), "weeks": len(weeks), "graph": summary}


def export_sna_explorer(posts, inter, G, metrics, comm, w, real: bool = False, public_names: dict | None = None):
    """Dataset untuk SNA Explorer (gaya graf interaktif): node teragregasi, edge harian dengan
    sentimen/emosi unggahan pembentuknya, dan contoh unggahan per node teratas.
    display_name hanya diisi untuk entitas publik (media, Page, kanal pemilik video); akun individu kosong."""
    public_names = public_names or {}
    by_post = {p["post_id"]: p for p in posts}
    agg = defaultdict(lambda: {"posts": 0, "engagement": 0, "sent": Counter(), "emo": Counter()})
    for p in posts:
        a = agg[p["author_id_pseudonym"]]
        a["posts"] += 1
        a["engagement"] += int(p.get("engagement_count") or 0)
        a["sent"][p["sentiment"]] += 1
        a["emo"][p["emotion"]] += 1
    plat_of = {}
    for i in inter:
        plat_of.setdefault(i["source"], i["platform"])
        plat_of.setdefault(i["target"], i["platform"])
    atype = lambda n: explorer.entity_kind(n, public_names)[0]
    display = lambda n: explorer.entity_kind(n, public_names)[1]
    labels = explorer.anon_labels(posts, inter, public_names)  # "Pengunggah #n" / "Komentator #n" untuk akun berpseudonim
    rows = []
    for n in G.nodes:
        a = agg[n]
        m = metrics[n]
        rows.append({"node_id": n, "display_name": display(n), "anon_label": labels.get(n, ""), "platform": plat_of.get(n), "node_type": atype(n), "community": comm[n],
                     "degree": G.in_degree(n) + G.out_degree(n), "in_degree": m["in_degree"], "out_degree": m["out_degree"],
                     "betweenness": m["betweenness"], "pagerank": m["pagerank"], "engagement": a["engagement"], "posts": a["posts"],
                     "sentiment": a["sent"].most_common(1)[0][0] if a["sent"] else "tidak_ada_unggahan",
                     **{f"e_{e}": a["emo"].get(e, 0) for e in nlp.EMOTIONS + ["netral"]}})
    w("sna_nodes.csv", rows, ["node_id", "display_name", "anon_label", "platform", "node_type", "community", "degree", "in_degree", "out_degree", "betweenness", "pagerank",
                              "engagement", "posts", "sentiment", *[f"e_{e}" for e in nlp.EMOTIONS + ["netral"]]])
    ec = Counter()
    for i in inter:
        p = by_post.get(i["post_id"], {})
        ec[(i["source"], i["target"], i["timestamp"][:10], i["type"], i["platform"], p.get("sentiment", "netral"), p.get("emotion", "netral"))] += 1
    w("sna_edges.csv", [{"source": k[0], "target": k[1], "day": k[2], "type": k[3], "platform": k[4], "sentiment": k[5], "emotion": k[6], "count": v}
                        for k, v in ec.items()], ["source", "target", "day", "type", "platform", "sentiment", "emotion", "count"])
    # Privasi (data nyata): teks unggahan hanya untuk entitas publik (media/Page); akun individu tidak ditampilkan teksnya
    public_only = any(not p.get("is_synthetic") for p in posts)
    PUBLIC = ("media", "page", "channel")
    top = sorted((r for r in rows if not public_only or r["node_type"] in PUBLIC), key=lambda r: -r["degree"])[:60]
    # Aturan privasi: pada data NYATA, teks unggahan akun individu tidak diekspor ke dashboard;
    # hanya media/Page/kanal publik yang teksnya ditampilkan. Individu tetap terlihat sebagai agregat.
    show_text = lambda r: (not real) or r["node_type"] in PUBLIC
    out = []
    for r in top:
        ps = sorted((p for p in posts if p["author_id_pseudonym"] == r["node_id"]), key=lambda p: -int(p.get("engagement_count") or 0))[:3]
        for p in ps:
            t = " ".join(p["text"].split())
            out.append({"node_id": r["node_id"], "post_id": p["post_id"], "day": p["timestamp"][:10], "engagement": p.get("engagement_count") or 0,
                        "sentiment": p["sentiment"], "emotion": p["emotion"],
                        "text": (t[:180] + ("…" if len(t) > 180 else "")) if show_text(r) else ""})
    w("sna_posts.csv", out, ["node_id", "post_id", "day", "engagement", "sentiment", "emotion", "text"])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="drno.analyze")
    ap.add_argument("--out", default="exports_real")
    ap.add_argument("--sentiment-model", default=None, help="Model HuggingFace sentimen bahasa Indonesia (opsional)")
    a = ap.parse_args(argv)
    from .storage import get_store
    store = get_store()
    posts, inter, _ = store.load()
    posts = [p for p in posts if not p.get("is_synthetic")]
    print(export_dashboard(posts, inter, a.out, "real", a.sentiment_model, public_names=store.load_public_names()))


if __name__ == "__main__":
    main()
