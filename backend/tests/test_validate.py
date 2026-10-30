import csv

from drno import validate
from drno.analyze import annotate_all
from drno.synthetic import generate


def test_kappa_known_values():
    assert validate.cohen_kappa(list("aabb"), list("aabb")) == 1.0
    assert validate.cohen_kappa(list("abab"), list("baba")) == -1.0


def test_prf():
    r = {x["label"]: x for x in validate.prf(["a", "a", "b"], ["a", "b", "b"])}
    assert r["a"]["precision"] == 1.0 and r["a"]["recall"] == 0.5


def test_sample_includes_rare_strata_and_hides_machine_labels(tmp_path):
    posts = generate(5)["posts"]
    annotate_all(posts)
    n = validate.write_sample(posts, 120, tmp_path)
    assert n == 120
    rows = list(csv.DictReader(open(tmp_path / "coder_A.csv", encoding="utf-8")))
    assert "mesin_context" not in rows[0] and rows[0]["context"] == ""
    key = list(csv.DictReader(open(tmp_path / "_kunci.csv", encoding="utf-8")))
    assert any(k["mesin_context"] == "tidak_dapat_dipastikan" for k in key)


def test_score_roundtrip(tmp_path):
    posts = generate(6)["posts"]
    annotate_all(posts)
    validate.write_sample(posts, 40, tmp_path)
    key = {r["item_id"]: r for r in csv.DictReader(open(tmp_path / "_kunci.csv", encoding="utf-8"))}
    for c in ("A", "B"):
        f = tmp_path / f"coder_{c}.csv"
        rows = list(csv.DictReader(open(f, encoding="utf-8")))
        for r in rows:  # simulasi: pengode setuju dengan mesin
            for t in validate.TASKS:
                r[t] = key[r["item_id"]][f"mesin_{t}"]
        with open(f, "w", newline="", encoding="utf-8") as h:
            w = csv.DictWriter(h, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    rep = validate.score(tmp_path / "coder_A.csv", tmp_path / "coder_B.csv", tmp_path / "_kunci.csv")
    assert rep["stance"]["kappa"] == 1.0 and rep["stance"]["accuracy"] == 1.0


def test_real_mode_hides_individual_post_text(tmp_path, monkeypatch):
    from drno.analyze import export_dashboard
    d = generate(8)
    export_dashboard(d["posts"], d["interactions"], tmp_path, "real")
    rows = list(csv.DictReader(open(tmp_path / "sna_posts.csv", encoding="utf-8")))
    assert rows and all(r["text"] == "" for r in rows if not r["node_id"].startswith(("media:", "page:")))
