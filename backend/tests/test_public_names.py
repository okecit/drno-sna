import os

os.environ.setdefault("DRNO_PSEUDONYM_KEY", "k" * 40)

from drno.analyze import export_sna_explorer  # noqa: E402
from drno.maintenance import is_public_channel  # noqa: E402
from drno.storage import JsonlStore  # noqa: E402


def test_public_channel_threshold():
    assert is_public_channel({"subscriberCount": "250000"}, 10000)
    assert not is_public_channel({"subscriberCount": "800"}, 10000)  # kanal pribadi kecil tetap pseudonim
    assert not is_public_channel({"subscriberCount": "900000", "hiddenSubscriberCount": True}, 10000)


def test_only_public_entities_get_display_names(tmp_path):
    import networkx as nx
    G = nx.DiGraph([("yo_warga", "yo_kanal"), ("yo_warga", "media:ANTARA")])
    metrics = {n: {"in_degree": 0, "out_degree": 0, "betweenness": 0, "pagerank": 0} for n in G}
    posts = [{"author_id_pseudonym": n, "engagement_count": 0, "sentiment": "netral", "emotion": "netral", "post_id": n,
              "timestamp": "2026-10-30T00:00:00Z", "text": "teks", "is_synthetic": False} for n in G]
    inter = [{"source": s, "target": t, "post_id": s, "timestamp": "2026-10-30T00:00:00Z", "type": "comment", "platform": "youtube"} for s, t in G.edges]
    out = {}
    export_sna_explorer(posts, inter, G, metrics, {n: 0 for n in G}, lambda name, rows, f: out.setdefault(name, rows), real=True,
                        public_names={"yo_kanal": {"type": "channel", "name": "Kanal Berita Besar"}})
    rows = {r["node_id"]: r for r in out["sna_nodes.csv"]}
    assert rows["yo_kanal"]["display_name"] == "Kanal Berita Besar" and rows["yo_kanal"]["node_type"] == "channel"
    assert rows["media:ANTARA"]["display_name"] == "ANTARA"
    assert rows["yo_warga"]["display_name"] == "" and rows["yo_warga"]["node_type"] == "account"


def test_jsonl_store_keeps_only_public_names(tmp_path):
    store = JsonlStore(str(tmp_path))
    store._append("authors.jsonl", [{"author": "yo_kanal", "type": "channel", "name": "Kanal Berita Besar"}])
    assert store.load_public_names() == {"yo_kanal": {"type": "channel", "name": "Kanal Berita Besar"}}
