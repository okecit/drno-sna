import networkx as nx

from drno import nlp, sna
from drno.synthetic import generate


def test_religious_term_alone_is_not_violence_support():
    clf = nlp.BaselineClassifier()
    for t in ["jihad melawan hawa nafsu", "hijrah kaffah", "sejarah khilafah"]:
        assert clf.context(t).label != "dukungan_kekerasan"


def test_violence_label_always_goes_to_manual_review():
    clf = nlp.BaselineClassifier()
    p = clf.context("angkat senjata serang mereka")
    assert p.label == "dukungan_kekerasan" and p.is_uncertain


def test_edges_require_evidence():
    G = sna.build_interaction_graph([{"source": "a", "target": "b", "type": "reply", "post_id": None,
                                      "timestamp": "2026-01-01", "platform": "x"}])
    assert G.number_of_edges() == 0


def test_interaction_and_narrative_networks_separate():
    d = generate(1)
    G = sna.build_interaction_graph(d["interactions"])
    N = sna.build_narrative_cooccurrence(d["posts"])
    assert G.graph["kind"] == "interaction" and N.graph["kind"] == "narrative_cooccurrence"
    assert not set(G.nodes) & set(N.nodes)


def test_betweenness_matches_hand_calculation():
    # graf ilustratif slide 15 PPT: D = 9, C = E = 8 (tak dinormalisasi)
    G = nx.Graph([("A","B"),("A","C"),("B","C"),("C","D"),("D","E"),("E","F"),("E","G"),("F","G")])
    b = nx.betweenness_centrality(G, normalized=False)
    assert b["D"] == 9 and b["C"] == 8 and b["E"] == 8
    assert round(nx.density(G), 2) == 0.38


def test_all_synthetic_records_flagged():
    d = generate(2)
    assert all(p["is_synthetic"] and p["source_method"] == "synthetic" for p in d["posts"])


def test_exports(tmp_path):
    d = generate(3)
    G = sna.build_interaction_graph(d["interactions"])
    sna.analyze(G)
    g, x = sna.export_graph(G, str(tmp_path / "net"))
    assert nx.read_graphml(g).number_of_nodes() == G.number_of_nodes()


def test_emotion_baseline():
    assert nlp.emotion("Mengecam aksi teror, kekerasan bukan jalan").label in ("anger", "fear")
    assert nlp.emotion("Moderasi beragama meneguhkan toleransi").label == "trust"
    assert nlp.emotion("berita cuaca hari ini").label == "netral"


def test_empty_period_does_not_crash():
    # Regresi: minggu tanpa interaksi (mis. hanya artikel berita) dulu menggagalkan seluruh analisis
    snaps = sna.temporal_snapshots([], [("W01", "2026-01-01", "2026-01-07")])
    assert snaps[0]["summary"]["n_nodes"] == 0 and snaps[0]["metrics"] == {}
