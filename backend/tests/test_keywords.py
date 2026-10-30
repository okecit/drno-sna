from drno.keywords import KeywordDictionary, compile_query, variants


def test_transliteration_and_hashtag_variants():
    v = variants("thaghut")
    assert {"thogut", "taghut", "#thaghut"} <= set(v)


def test_match_is_case_and_hashtag_insensitive():
    kd = KeywordDictionary.baseline()
    assert "thaghut" in kd.match("Narasi TAGHUT ramai #Thogut")
    assert "moderasi beragama" in kd.match("dukung #ModerasiBeragama")


def test_no_partial_word_match():
    kd = KeywordDictionary.baseline()
    assert "teroris" not in kd.match("pengusaha properti")


def test_boolean_query():
    q = compile_query('(khilafah OR daulah) AND NOT "moderasi beragama"')
    assert q("sejarah khilafah")
    assert not q("khilafah dan moderasi beragama")
    assert not q("berita cuaca")


def test_semantic_suggestion_requires_review_and_versions():
    kd = KeywordDictionary.baseline()
    n0 = len(kd.versions)
    kd.suggest("propaganda digital", "konten provokatif", 0.71, "minilm")
    assert len(kd.versions) == n0  # usulan tidak langsung masuk kamus
    kd.review("konten provokatif", accept=True, reviewer="peneliti", group="narasi_digital", note="uji")
    assert len(kd.versions) == n0 + 1 and "konten provokatif" in kd.current.terms
    assert "konten provokatif" not in kd.versions[0].terms  # versi lama tidak berubah


def test_religious_terms_marked_baseline():
    kd = KeywordDictionary.baseline()
    assert kd.current.terms["jihad"]["baseline"] is True
