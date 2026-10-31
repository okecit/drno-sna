from drno.discovery import associated_terms, disguised_variants, trigger_counts
from drno.keywords import KeywordDictionary


def _posts(texts, platform="youtube"):
    kd = KeywordDictionary.baseline()
    return [{"text": t, "platform": platform, "timestamp": f"2026-10-{i % 28 + 1:02d}T00:00:00Z", "keyword_matched": kd.match(t)}
            for i, t in enumerate(texts)], kd


def test_disguised_spelling_detected_but_common_words_ignored():
    posts, kd = _posts(["aparat th0gut harus dilawan", "thoghut itu musuh", "semua sudah takdir Allah", "dash kamera mobil"])
    found = {(r["term"], r["related_to"], r["detail"]) for r in disguised_variants(posts, kd)}
    assert ("th0gut", "thaghut", "angka_pengganti") in found
    assert ("thoghut", "thaghut", "salah_eja") in found
    assert not any(t in ("takdir", "dash") for t, _, _ in found)


def test_associated_terms_rank_terms_near_triggers():
    texts = ["thaghut wajib dikufuri hijrah ke daulah"] * 6 + ["kafir harbi wajib dikufuri"] * 3 + ["resep rendang enak sekali"] * 30
    posts, kd = _posts(texts)
    terms = [r["term"] for r in associated_terms(posts, kd)]
    assert "dikufuri" in terms
    assert "rendang" not in terms
    assert "thaghut" not in terms  # istilah kamus tidak diusulkan ulang


def test_trigger_counts_by_platform():
    posts, kd = _posts(["Densus tangkap simpatisan Anshorut Daulah", "aparat thogut"], platform="news")
    rows = {r["term"]: r for r in trigger_counts(posts, kd)}
    assert rows["ansharut daulah"]["news"] == 1 and rows["thaghut"]["posts"] == 1


def test_trigger_spellings_report_forms_actually_used():
    posts, kd = _posts(["pemerintah thogut", "hukum THOGUT", "#thagut viral", "makna thaghut"])
    row = {r["term"]: r for r in trigger_counts(posts, kd)}["thaghut"]
    assert row["spellings"].split(";")[0] == "thogut:2"
    assert {"thagut:1", "thaghut:1"} <= set(row["spellings"].split(";"))
    assert "thagut" in row["variants"].split(";")


def test_trigger_terms_kept_in_narrative_map_even_without_pairs():
    from drno import sna
    posts, kd = _posts(["aparat thogut"] + ["terorisme radikalisme"] * 3)
    N = sna.build_narrative_cooccurrence(posts, keep={"thaghut"})
    assert "thaghut" in N and N.nodes["thaghut"]["frequency"] == 1 and N.has_edge("terorisme", "radikalisme")
