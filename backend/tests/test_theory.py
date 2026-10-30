import networkx as nx

from drno import theory


def test_brokerage_roles_classification():
    G = nx.DiGraph()
    G.add_edges_from([("a", "v"), ("v", "b")])
    g = {"a": 1, "v": 2, "b": 3}
    assert theory.brokerage_roles(G, g)["v"]["liaison"] == 1
    assert theory.brokerage_roles(G, {"a": 1, "v": 2, "b": 1})["v"]["itinerant"] == 1
    assert theory.brokerage_roles(G, {"a": 1, "v": 1, "b": 2})["v"]["representative"] == 1
    assert theory.brokerage_roles(G, {"a": 1, "v": 2, "b": 2})["v"]["gatekeeper"] == 1
    G.add_edge("a", "b")  # triad tertutup -> bukan brokerage
    assert theory.brokerage_roles(G, g)["v"]["total"] == 0


def test_constraint_lower_for_bridge():
    G = nx.DiGraph([("a", "b"), ("b", "c"), ("c", "a"), ("c", "d"), ("d", "e"), ("e", "f"), ("f", "d")])
    nx.set_edge_attributes(G, 1, "weight")
    sh = theory.structural_holes(G)
    assert sh["c"]["constraint"] < sh["a"]["constraint"]


def test_weak_ties_and_reciprocity():
    G = nx.DiGraph()
    G.add_edge("a", "b", weight=1)
    G.add_edge("b", "a", weight=1)
    G.add_edge("a", "c", weight=1)
    ties, summ = theory.tie_strength(G, {"a": 0, "b": 0, "c": 1})
    d = {(t["a"], t["b"]): t for t in ties}
    assert d[("a", "b")]["strength"] == "kuat" and d[("a", "c")]["strength"] == "lemah" and d[("a", "c")]["bridge"]


def test_homophily_detects_assortative_network():
    G = nx.DiGraph()
    attr = {}
    for grp in ("menolak", "netral"):
        ns = [f"{grp}{i}" for i in range(10)]
        for i in range(10):
            attr[ns[i]] = grp
            G.add_edge(ns[i], ns[(i + 1) % 10])
            G.add_edge(ns[i], ns[(i + 3) % 10])
    G.add_edge("menolak0", "netral0")
    r = theory.homophily_test(G, attr, n_perm=200)
    assert r["ei_observed"] < r["ei_null_low"] and r["p_value"] < 0.05


def test_insufficient_data_label():
    posts = [{"author_id_pseudonym": "a", "stance": "menolak"}]
    assert theory.account_attributes(posts, "stance")["a"] == "tidak_cukup_data"
