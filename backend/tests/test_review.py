import json

from drno.discovery import hidden_terms
from drno.keywords import DEFAULT_QUERY, KeywordDictionary, compile_query, default_query, load_review


def _review(tmp_path, decisions):
    p = tmp_path / "keyword_review.json"
    p.write_text(json.dumps({"decisions": decisions}), encoding="utf-8")
    return str(p)


def test_accepted_terms_become_dictionary_version_and_query(tmp_path, monkeypatch):
    path = _review(tmp_path, [{"term": "Zimmi", "decision": "accept", "group": "ideologis"},
                              {"term": "dakwah sunnah", "decision": "accept", "group": "keagamaan"},
                              {"term": "dikufuri", "decision": "reject"},
                              {"term": "aneh", "decision": "accept", "group": "kelompok_palsu"}])
    accepted, rejected = load_review(path)
    assert accepted == {"zimmi": "ideologis", "dakwah sunnah": "keagamaan"} and rejected == {"dikufuri"}
    monkeypatch.setenv("DRNO_KEYWORD_REVIEW", path)
    kd = KeywordDictionary.baseline()
    assert kd.current.label == "v1.2-tinjauan-peneliti" and "zimmi" in kd.match("hukum kafir zimmi")
    assert "zimmi" not in kd.versions[1].terms  # v1.1 tetap utuh
    q = default_query(path)
    assert "zimmi" in q and "dakwah sunnah" not in q  # pembanding keagamaan tidak memperluas crawl
    assert compile_query(q)("bahas kafir zimmi") and not compile_query(DEFAULT_QUERY)("bahas kafir zimmi")


def test_rejected_terms_not_suggested_again(tmp_path):
    kd = KeywordDictionary.baseline()
    texts = ["thaghut wajib dikufuri hijrah"] * 6 + ["resep rendang enak sekali"] * 30
    posts = [{"text": t, "platform": "youtube", "timestamp": "2026-10-30T00:00:00Z", "keyword_matched": kd.match(t)} for t in texts]
    assert "dikufuri" in {r["term"] for r in hidden_terms(posts, kd, review_path=str(tmp_path / "tidak_ada.json"))}
    path = _review(tmp_path, [{"term": "dikufuri", "decision": "reject"}])
    assert "dikufuri" not in {r["term"] for r in hidden_terms(posts, kd, review_path=path)}


def test_missing_or_broken_review_file_is_ignored(tmp_path):
    (tmp_path / "rusak.json").write_text("{bukan json", encoding="utf-8")
    assert load_review(str(tmp_path / "rusak.json")) == ({}, set())
    assert default_query(str(tmp_path / "tidak_ada.json")) == DEFAULT_QUERY
