"""Lensa teori sebagai alat analisis (v0.3).

Dua lensa dipilih karena dapat dioperasionalkan dengan data yang DRNO benar-benar punya
(interaksi publik teramati + label konteks/stance hasil mesin):

A. Structural Holes (Burt, 1992) + Strength of Weak Ties (Granovetter, 1973)
   - constraint & effective size per akun (Burt)
   - peran broker Gould & Fernandez (1989): coordinator, itinerant, gatekeeper, representative, liaison
   - kekuatan ikatan (frekuensi + resiprositas) dan uji: apakah jembatan antarkomunitas didominasi ikatan lemah?

B. Homofili (McPherson, Smith-Lovin & Cook, 2001) + Social Identity Theory (Tajfel & Turner, 1979)
   - E-I index (Krackhardt & Stern, 1988) dan assortativity per atribut (stance & konteks dominan akun)
   - uji permutasi: apakah homofili melebihi yang diharapkan secara acak?
   - matriks pencampuran stance x stance
   - penanda identitas kelompok (eksploratif): rasio pronomina in-group (kami/kita) vs out-group (mereka/kalian)

Batas interpretasi (dipaksakan di keluaran):
- Brokerage = posisi struktural, bukan peran organisasi atau pengaruh.
- Homofili pada data observasional tidak membedakan seleksi dari pengaruh (Shalizi & Thomas, 2011).
- Atribut akun berasal dari klasifikasi mesin atas unggahan; bukan identitas atau ideologi orang.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict

import networkx as nx

from .nlp import clean

# ---------------- A. Structural holes & weak ties ----------------


def structural_holes(G: nx.DiGraph):
    """Constraint dan effective size Burt (graf tak berarah berbobot)."""
    U = nx.Graph()
    for u, v, d in G.edges(data=True):
        w = d.get("weight", 1)
        if U.has_edge(u, v):
            U[u][v]["weight"] += w
        else:
            U.add_edge(u, v, weight=w)
    cons = nx.constraint(U, weight="weight")
    eff = nx.effective_size(U, weight="weight")
    return {n: {"constraint": None if cons[n] != cons[n] else round(cons[n], 4),  # NaN untuk isolat
                "effective_size": None if eff[n] != eff[n] else round(eff[n], 3),
                "n_contacts": U.degree(n)} for n in U.nodes}


ROLES = ("coordinator", "itinerant", "gatekeeper", "representative", "liaison")


def brokerage_roles(G: nx.DiGraph, group: dict):
    """Gould & Fernandez (1989). Untuk tiap triad a->v->b tanpa a->b:
    coordinator: a,v,b satu kelompok | itinerant: a,b sekelompok, v beda | representative: a,v sekelompok, b beda
    gatekeeper: v,b sekelompok, a beda | liaison: ketiganya beda."""
    out = {n: dict.fromkeys(ROLES, 0) for n in G.nodes}
    for v in G.nodes:
        preds, succs = list(G.predecessors(v)), list(G.successors(v))
        gv = group.get(v)
        for a in preds:
            for b in succs:
                if a == b or G.has_edge(a, b):
                    continue
                ga, gb = group.get(a), group.get(b)
                if ga == gv == gb:
                    r = "coordinator"
                elif ga == gb != gv:
                    r = "itinerant"
                elif ga == gv != gb:
                    r = "representative"
                elif gv == gb != ga:
                    r = "gatekeeper"
                else:
                    r = "liaison"
                out[v][r] += 1
    for v in out:
        out[v]["total"] = sum(out[v][r] for r in ROLES)
    return out


def tie_strength(G: nx.DiGraph, community: dict, weak_max: int = 1):
    """Ikatan lemah = total interaksi dua arah <= weak_max DAN tidak resiprokal.
    Mengembalikan daftar ikatan tak berarah + ringkasan uji Granovetter."""
    seen, ties = set(), []
    for u, v in G.edges():
        key = tuple(sorted((u, v)))
        if key in seen:
            continue
        seen.add(key)
        w_uv = G[u][v]["weight"] if G.has_edge(u, v) else 0
        w_vu = G[v][u]["weight"] if G.has_edge(v, u) else 0
        recip = w_uv > 0 and w_vu > 0
        total = w_uv + w_vu
        strength = "lemah" if (total <= weak_max and not recip) else "kuat"
        bridge = community.get(u) != community.get(v)
        ties.append({"a": key[0], "b": key[1], "total": total, "reciprocal": recip, "strength": strength, "bridge": bridge})
    summ = []
    for kind in (True, False):
        sub = [t for t in ties if t["bridge"] == kind]
        weak = sum(t["strength"] == "lemah" for t in sub)
        summ.append({"tie_type": "antarkomunitas (jembatan)" if kind else "dalam komunitas", "ties": len(sub),
                     "weak": weak, "strong": len(sub) - weak, "weak_share": round(weak / len(sub), 4) if sub else None})
    return ties, summ


# ---------------- B. Homofili & identitas sosial ----------------


def account_attributes(posts, field: str, min_posts: int = 2):
    """Atribut akun = label mayoritas dari unggahannya (hasil mesin). Akun dengan < min_posts
    atau tanpa mayoritas jelas -> 'tidak_cukup_data'."""
    by = defaultdict(Counter)
    for p in posts:
        by[p["author_id_pseudonym"]][p[field]] += 1
    out = {}
    for a, c in by.items():
        n = sum(c.values())
        lab, k = c.most_common(1)[0]
        out[a] = lab if (n >= min_posts and k / n > 0.5) else "tidak_cukup_data"
    return out


def ei_index(G, attr: dict, skip=("tidak_cukup_data",)):
    """E-I = (E - I) / (E + I) atas ikatan tak berarah antar-node berlabel. -1 = homofili penuh."""
    E = I = 0
    for u, v in G.to_undirected().edges():
        au, av = attr.get(u), attr.get(v)
        if au is None or av is None or au in skip or av in skip:
            continue
        if au == av:
            I += 1
        else:
            E += 1
    return (E - I) / (E + I) if (E + I) else None, E, I


def homophily_test(G, attr: dict, n_perm: int = 500, seed: int = 42):
    """E-I teramati vs distribusi null dari pengacakan label (struktur graf tetap)."""
    obs, E, I = ei_index(G, attr)
    nodes = [n for n in G.nodes if attr.get(n) not in (None, "tidak_cukup_data")]
    labels = [attr[n] for n in nodes]
    rng = random.Random(seed)
    null = []
    for _ in range(n_perm):
        rng.shuffle(labels)
        val, _, _ = ei_index(G, dict(zip(nodes, labels)))
        if val is not None:
            null.append(val)
    null.sort()
    if obs is None or not null:
        return {"ei_observed": None}
    p = sum(1 for x in null if x <= obs) / len(null)  # satu sisi: lebih homofil dari acak
    U = G.to_undirected().subgraph(nodes).copy()
    nx.set_node_attributes(U, {n: attr[n] for n in nodes}, "lab")
    try:
        assort = nx.attribute_assortativity_coefficient(U, "lab")
    except ZeroDivisionError:
        assort = None
    return {"ei_observed": round(obs, 4), "external_ties": E, "internal_ties": I,
            "ei_null_low": round(null[int(0.025 * len(null))], 4), "ei_null_mean": round(sum(null) / len(null), 4),
            "ei_null_high": round(null[int(0.975 * len(null)) - 1], 4), "p_value": round(p, 4),
            "assortativity": None if assort is None or assort != assort else round(assort, 4),
            "labelled_nodes": len(nodes), "n_perm": n_perm}


def mixing_matrix(G, attr: dict):
    c = Counter()
    for u, v in G.edges():
        au, av = attr.get(u), attr.get(v)
        if au and av:
            c[(au, av)] += 1
    return [{"source_attr": a, "target_attr": b, "ties": n} for (a, b), n in sorted(c.items())]


IN_GROUP = {"kami", "kita"}
OUT_GROUP = {"mereka", "kalian"}


def identity_markers(posts, community: dict):
    """Eksploratif: frekuensi pronomina in-group/out-group per komunitas (per 1.000 kata).
    Indikator linguistik kasar untuk lensa Social Identity Theory; bukan ukuran identitas."""
    agg = defaultdict(lambda: {"words": 0, "in_group": 0, "out_group": 0, "posts": 0})
    for p in posts:
        c = community.get(p["author_id_pseudonym"])
        if c is None:
            continue
        w = clean(p["text"]).split()
        d = agg[c]
        d["posts"] += 1
        d["words"] += len(w)
        d["in_group"] += sum(x in IN_GROUP for x in w)
        d["out_group"] += sum(x in OUT_GROUP for x in w)
    rows = []
    for c, d in sorted(agg.items()):
        k = 1000 / d["words"] if d["words"] else 0
        rows.append({"community": c, "posts": d["posts"], "in_group_per_1k": round(d["in_group"] * k, 2),
                     "out_group_per_1k": round(d["out_group"] * k, 2)})
    return rows


def run_lenses(G: nx.DiGraph, posts, community: dict, metrics: dict | None = None):
    """Hitung kedua lensa sekaligus. Mengembalikan dict tabel siap ekspor."""
    sh = structural_holes(G)
    br = brokerage_roles(G, community)
    ties, tsum = tie_strength(G, community)
    nodes = []
    for n in G.nodes:
        row = {"node_id": n, "community": community.get(n), **sh.get(n, {}), **br[n]}
        if metrics:
            row["betweenness"] = metrics.get(n, {}).get("betweenness")
        nodes.append(row)
    stance = account_attributes(posts, "stance")
    ctx = account_attributes(posts, "context")
    hom = [{"attribute": "stance", **homophily_test(G, stance)}, {"attribute": "konteks", **homophily_test(G, ctx)}]
    return {"broker_nodes": nodes, "tie_summary": tsum, "homophily": hom,
            "mixing_stance": mixing_matrix(G, stance), "identity": identity_markers(posts, community)}
