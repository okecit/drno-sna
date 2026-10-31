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
