"""Social Network Analysis (Bagian 6 dan Extended Module D).

Dua jaringan dijaga TERPISAH:
- Jaringan interaksi (connection): node = akun berpseudonim / kanal / entitas publik,
  edge berarah = reply, mention, repost, comment, comment_reply yang tercatat (dengan post_id bukti).
- Jaringan ko-okurensi narasi (contagion/isi): node = istilah atau narasi, edge = muncul bersama
  dalam unggahan yang sama. Jaringan ini TIDAK menyatakan hubungan antarorang.

Metrik adalah ukuran posisi struktural. Tidak ada fungsi di modul ini yang menurunkan
afiliasi, peran organisasi, atau keterlibatan kriminal dari metrik jaringan.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

import networkx as nx

INTERACTION_TYPES = {"reply", "mention", "repost", "comment", "comment_reply"}


def build_interaction_graph(interactions, nodes_meta=None, types=None, platforms=None, start=None, end=None):
    """interactions: iterable dict {source, target, type, post_id, timestamp(ISO), platform}."""
    G = nx.DiGraph(kind="interaction")
    types = set(types or INTERACTION_TYPES)
    for it in interactions:
        if it["type"] not in types:
            continue
        if platforms and it["platform"] not in platforms:
            continue
        ts = it["timestamp"][:10]
        if (start and ts < start) or (end and ts > end):
            continue
        if not it.get("post_id"):
            continue  # tanpa bukti relasi, tidak ada edge
        s, t = it["source"], it["target"]
        if s == t:
            continue
        if G.has_edge(s, t):
            e = G[s][t]
            e["weight"] += 1
            e["types"][it["type"]] = e["types"].get(it["type"], 0) + 1
            e["evidence"].append(it["post_id"])
        else:
            G.add_edge(s, t, weight=1, types={it["type"]: 1}, evidence=[it["post_id"]])
    if nodes_meta:
        for n in G.nodes:
            G.nodes[n].update(nodes_meta.get(n, {}))
    return G


def build_narrative_cooccurrence(posts, field="keyword_matched", min_weight=2, keep=()):
    """Jaringan ko-okurensi istilah/narasi dari unggahan. Tidak menyangkut relasi antarakun.
    keep: istilah yang tetap ditampilkan (mis. kata kunci pemicu) walau belum punya pasangan >= min_weight."""
    G = nx.Graph(kind="narrative_cooccurrence")
    freq = Counter()
    pairs = Counter()
    for p in posts:
        items = sorted(set(p.get(field) or []))
        freq.update(items)
        pairs.update(combinations(items, 2))
    for (a, b), w in pairs.items():
        if w >= min_weight:
            G.add_edge(a, b, weight=w)
    for t in keep:
        if freq[t] and t not in G:
            G.add_node(t)
    for n in G.nodes:
        G.nodes[n]["frequency"] = freq[n]
    return G


def detect_communities(G, seed=42, resolution=1.0):
    """Louvain (networkx). Untuk Leiden gunakan igraph+leidenalg bila tersedia."""
    U = G.to_undirected() if G.is_directed() else G
    if U.number_of_edges() == 0:
        return {n: i for i, n in enumerate(U.nodes)}, 0.0
    try:  # pragma: no cover - opsional
        import igraph as ig
        import leidenalg
        g = ig.Graph.from_networkx(U)
        part = leidenalg.find_partition(g, leidenalg.ModularityVertexPartition, seed=seed, weights="weight")
        names = g.vs["_nx_name"]
        comm = {names[v]: ci for ci, members in enumerate(part) for v in members}
        algo = "leiden"
    except Exception:
        comms = nx.community.louvain_communities(U, weight="weight", seed=seed, resolution=resolution)
        comms = sorted(comms, key=len, reverse=True)
        comm = {n: ci for ci, members in enumerate(comms) for n in members}
        algo = "louvain"
    groups = defaultdict(set)
    for n, c in comm.items():
        groups[c].add(n)
    Q = nx.community.modularity(U, groups.values(), weight="weight")
    G.graph["community_algorithm"] = algo
    return comm, Q


def node_metrics(G):
    """Degree, in/out-degree, betweenness, closeness, eigenvector, PageRank (dinormalisasi)."""
    U = G.to_undirected() if G.is_directed() else G
    n = G.number_of_nodes()
    m = {}
    if n == 0:  # periode tanpa interaksi (mis. hanya berita) — bukan galat
        return m
    deg = nx.degree_centrality(U)
    btw = nx.betweenness_centrality(G, normalized=True, weight=None) if n <= 5000 else \
        nx.betweenness_centrality(G, k=min(500, n), normalized=True, seed=42)
    clo = nx.closeness_centrality(G)
    try:
        eig = nx.eigenvector_centrality(U, max_iter=1000, weight="weight")
    except nx.PowerIterationFailedConvergence:
        eig = {k: 0.0 for k in G}
    pr = nx.pagerank(G, weight="weight") if n else {}
    ind = dict(G.in_degree()) if G.is_directed() else dict(G.degree())
    outd = dict(G.out_degree()) if G.is_directed() else dict(G.degree())
    for v in G.nodes:
        m[v] = {"degree": round(deg.get(v, 0), 5), "in_degree": ind.get(v, 0), "out_degree": outd.get(v, 0),
                "betweenness": round(btw.get(v, 0), 5), "closeness": round(clo.get(v, 0), 5),
                "eigenvector": round(eig.get(v, 0), 5), "pagerank": round(pr.get(v, 0), 6)}
    return m


def graph_summary(G, modularity=None):
    U = G.to_undirected() if G.is_directed() else G
    return {"kind": G.graph.get("kind"), "n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(),
            "density": round(nx.density(G), 5) if G.number_of_nodes() > 1 else 0.0,
            "n_components": nx.number_connected_components(U) if U.number_of_nodes() else 0,
            "modularity": None if modularity is None else round(modularity, 4),
            "community_algorithm": G.graph.get("community_algorithm")}


def analyze(G, seed=42):
    comm, Q = detect_communities(G, seed=seed)
    metrics = node_metrics(G)
    for v in G.nodes:
        G.nodes[v].update(metrics[v])
        G.nodes[v]["community"] = comm.get(v, -1)
    return graph_summary(G, Q), metrics, comm


def temporal_snapshots(interactions, periods, **kw):
    """periods: list (label, start_iso, end_iso). Hasil per periode: ringkasan + metrik node."""
    out = []
    for label, s, e in periods:
        G = build_interaction_graph(interactions, start=s, end=e, **kw)
        summary, metrics, comm = analyze(G)
        out.append({"period": label, "start": s, "end": e, "summary": summary, "metrics": metrics, "community": comm})
    return out


def position_change(snapshots, node, metric="betweenness"):
    """Lintasan posisi struktural satu node lintas periode (deskriptif, bukan inferensi peran)."""
    return [(s["period"], s["metrics"].get(node, {}).get(metric)) for s in snapshots]


def export_graph(G, path_base):
    """GraphML + GEXF. Atribut kompleks (list/dict) diserialisasi sebagai string."""
    H = G.copy()
    for _, _, d in H.edges(data=True):
        for k, v in list(d.items()):
            if isinstance(v, (list, dict)):
                d[k] = str(v)
    for _, d in H.nodes(data=True):
        for k, v in list(d.items()):
            if isinstance(v, (list, dict)) or v is None:
                d[k] = "" if v is None else str(v)
    for k, v in list(H.graph.items()):
        if v is None:
            H.graph[k] = ""
    nx.write_graphml(H, f"{path_base}.graphml")
    nx.write_gexf(H, f"{path_base}.gexf")
    return f"{path_base}.graphml", f"{path_base}.gexf"
