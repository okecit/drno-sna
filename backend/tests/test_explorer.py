from drno.explorer import entities, geo, mentions, provinces_in


def _p(author, text, kws, platform="youtube", day="2026-10-30"):
    return {"author_id_pseudonym": author, "text": text, "keyword_matched": kws, "platform": platform,
            "timestamp": f"{day}T00:00:00Z", "engagement_count": 3, "url": "https://contoh/" + author}


PUBLIC = {"yo_kanal": {"type": "channel", "name": "Kanal Berita Besar"}}


def test_provinces_longest_alias_and_ambiguous_city_names():
    assert provinces_in("Densus geledah ponpes di Sukoharjo") == {"JT"}
    assert provinces_in("Penangkapan di Kepulauan Riau") == {"KR"}  # bukan juga "Riau"
    assert provinces_in("kelompok itu akan menyerang dan serang balik") == set()  # kata kerja, bukan kota
    assert provinces_in("Polisi tangkap terduga di Serang dan Poso") == {"BT", "ST"}


def test_mentions_text_only_for_public_sources():
    posts = [_p("yo_kanal", "Bahaya paham takfiri", ["takfir"]), _p("yo_warga", "komentar warga soal takfiri", ["takfir"]),
             _p("media:ANTARA", "JI dibubarkan", ["jamaah islamiyah"], platform="news")]
    daily, public = mentions(posts, PUBLIC, {"takfir": ["ideologis"], "jamaah islamiyah": ["jaringan_ekstrem"]})
    assert {r["source"] for r in public} == {"Kanal Berita Besar", "ANTARA"}
    assert not any("warga" in r["excerpt"] for r in public)
    assert sum(r["posts"] for r in daily if r["keyword"] == "takfir") == 2  # individu tetap terhitung agregat


def test_entities_names_only_public_and_geo_counts():
    posts = [_p("yo_kanal", "aparat thogut di Jakarta", ["thaghut"]), _p("yo_warga", "di Bandung", [])]
    rows = {r["entity_id"]: r for r in entities(posts, [], PUBLIC, {"thaghut"})}
    assert rows["yo_kanal"]["display_name"] == "Kanal Berita Besar" and rows["yo_kanal"]["trigger_posts"] == 1
    assert rows["yo_warga"]["display_name"] == "" and rows["yo_warga"]["type"] == "account"
    g = {r["code"]: r for r in geo(posts, {"thaghut"})}
    assert g["JK"]["trigger_posts"] == 1 and g["JB"]["posts"] == 1 and len(g) == 38


def test_anon_labels_readable_roles_without_identity():
    from drno.explorer import anon_labels
    posts = [_p("yo_kecil", "video", []), dict(_p("yo_w1", "komentar", []), reply_to="youtube:v1"), dict(_p("yo_w2", "komentar", []), reply_to="youtube:v1"),
             _p("media:ANTARA", "berita", [], platform="news")]
    inter = [{"source": "yo_w1", "target": "yo_kecil"}, {"source": "yo_w1", "target": "yo_kecil"}, {"source": "yo_w2", "target": "yo_kecil"}]
    lab = anon_labels(posts, inter, {})
    assert lab == {"yo_kecil": "Pengunggah #1", "yo_w1": "Komentator #1", "yo_w2": "Komentator #2"}  # media publik tidak diberi label anonim


def test_sentiment_lexicon_tone_not_topic():
    from drno.nlp import BaselineClassifier
    s = lambda t: BaselineClassifier().sentiment(t).label
    assert s("Satu orang tewas dalam ledakan bom di Makassar") == "negatif"  # "satu" bukan kata positif
    assert s("Kajian tentang terorisme dan radikalisme") == "netral"        # kata topik crawl tidak menentukan nada
    assert s("Warga Poso hidup rukun dan damai") == "positif"


def test_geo_counts_negative_sentiment_per_province():
    posts = [dict(_p("a", "teror di Poso", []), sentiment="negatif"), dict(_p("b", "Poso damai", []), sentiment="positif"),
             dict(_p("c", "bom di Poso", []), sentiment="negatif"), dict(_p("d", "Bali indah", []), sentiment="netral")]
    g = {r["code"]: r for r in geo(posts, set())}
    assert (g["ST"]["negative_posts"], g["ST"]["positive_posts"], g["ST"]["negative_share"]) == (2, 1, 0.667)
    assert g["BA"]["negative_posts"] == 0 and g["BA"]["negative_share"] == 0.0 and g["AC"]["negative_share"] == 0


def test_leaks_migration_coded_and_cross_page_brokers():
    from drno.explorer import leaks, mask, migration_signals
    assert migration_signals("japri ana ya, gabung grup kajian t.me/xyz") == ["telegram", "pesan_pribadi", "ajakan_gabung"]
    assert migration_signals("saya pikir begitu") == []
    assert mask("cek t.me/abc123 atau 081234567890 @budi") == "cek [tautan tertutup] atau [nomor] [akun]"
    posts = [dict(_p("page:A", "posting A", [], platform="facebook"), post_id="facebook:1"),
             dict(_p("page:B", "posting B", [], platform="facebook"), post_id="facebook:2"),
             dict(_p("fa_x", "pemerintah thogut, japri ya", ["thaghut"], platform="facebook"), post_id="facebook:c1", reply_to="facebook:1"),
             dict(_p("fa_x", "setuju", [], platform="facebook"), post_id="facebook:c2", reply_to="facebook:2"),
             dict(_p("fa_y", "biasa saja", [], platform="facebook"), post_id="facebook:c3", reply_to="facebook:1")]
    pub = {"page:A": {"name": "Page A"}}
    sig, acc = leaks(posts, [], pub, {"thaghut"})
    assert len(sig) == 1 and sig[0]["signals"] == "pesan_pribadi" and sig[0]["context"] == "Page A" and "fa_x" == sig[0]["entity_id"]
    assert [a["entity_id"] for a in acc] == ["fa_x"] and acc[0]["spaces"] == 2 and acc[0]["score"] == 3 + 2 + 1
