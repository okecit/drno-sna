import os

os.environ.setdefault("DRNO_PSEUDONYM_KEY", "k" * 40)

import httpx  # noqa: E402

from drno.collectors.base import JobConfig  # noqa: E402
from drno.collectors.scrapecreators_social import ScrapeCreatorsInstagramCollector, ScrapeCreatorsXCollector, _split  # noqa: E402
from drno.keywords import KeywordDictionary  # noqa: E402

KD = KeywordDictionary.baseline()


def _job(p):
    return JobConfig(platform=p, query="thogut", date_from="2026-10-01", date_to="2026-10-31", legal_basis="uji")


def _x_transport(seen):
    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"posts": [
            {"rest_id": "t1", "url": "https://x.com/a/status/t1",
             "core": {"user_results": {"result": {"rest_id": "u1", "legacy": {"screen_name": "BeritaBesar", "name": "Berita Besar", "followers_count": 250000}}}},
             "legacy": {"full_text": "Polisi: jaringan thogut ditangkap @warga_biasa", "created_at": "Thu Oct 30 05:00:00 +0000 2026",
                        "favorite_count": 3, "entities": {"user_mentions": [{"id_str": "u2", "screen_name": "warga_biasa"}]}}},
            {"rest_id": "t2", "core": {"user_results": {"result": {"rest_id": "u3", "legacy": {"screen_name": "akun_kecil", "followers_count": 40}}}},
             "legacy": {"full_text": "pemerintah thogut", "created_at": "Fri Oct 31 05:00:00 +0000 2026", "in_reply_to_user_id_str": "u1",
                        "in_reply_to_status_id_str": "t1"}},
            {"rest_id": "t0", "legacy": {"full_text": "thogut lama", "created_at": "Mon Jan 01 00:00:00 +0000 2024"}}], "cursor": None})
    return httpx.MockTransport(handler)


def test_x_public_named_individual_pseudonymized_with_edges():
    seen = []
    col = ScrapeCreatorsXCollector(api_key="k", queries=["thogut"], transport=_x_transport(seen))
    recs, inter, rep = col.run(_job("x_sc"), lambda t: "thogut" in t, KD.match)
    big, small = recs  # posting 2024 di luar rentang tidak diambil
    assert big["public_entity_name"] == "@BeritaBesar (Berita Besar)" and big["author_type"] == "channel"
    assert "public_entity_name" not in small and "akun_kecil" not in str(small)
    assert {i["type"] for i in inter} == {"mention", "reply"} and all(i["platform"] == "x" for i in inter)
    assert seen[0].url.path == "/v1/twitter/search/posts" and seen[0].headers["x-api-key"] == "k"


def _ig_transport(seen):
    def handler(req):
        seen.append(req)
        if req.url.path == "/v1/instagram/search/hashtag":
            return httpx.Response(200, json={"posts": [
                {"id": "m1", "shortcode": "ABC", "taken_at": "2026-10-30T05:00:00Z", "caption": {"text": "#deradikalisasi itu penting"}, "like_count": 9,
                 "owner": {"id": "o1", "username": "lembaga_resmi", "full_name": "Lembaga Resmi", "is_verified": True}}]})
        return httpx.Response(200, json={"comments": [
            {"id": "c1", "text": "setuju", "created_at": "2026-10-30T06:00:00Z", "user": {"id": "w9", "username": "siti_warga", "is_verified": False}}]})
    return httpx.MockTransport(handler)


def test_instagram_verified_named_commenter_pseudonymized():
    seen = []
    col = ScrapeCreatorsInstagramCollector(api_key="k", hashtags=["#deradikalisasi"], transport=_ig_transport(seen), comment_posts=1)
    recs, inter, rep = col.run(_job("instagram_sc"), lambda t: True, KD.match)
    post, comment = recs
    assert post["public_entity_name"] == "@lembaga_resmi (Lembaga Resmi)" and post["url"] == "https://www.instagram.com/p/ABC/"
    assert comment["author_id_pseudonym"].startswith("in_") and "siti" not in str(comment)
    assert inter[0]["type"] == "comment" and inter[0]["target"] == post["author_id_pseudonym"]
    assert seen[0].url.params["hashtag"] == "deradikalisasi" and seen[1].url.path == "/v2/instagram/post/comments"


def test_credit_cap_and_split():
    seen = []
    col = ScrapeCreatorsXCollector(api_key="k", queries=["a", "b", "c"], transport=_x_transport(seen), max_calls=2)
    col.run(_job("x_sc"), lambda t: True, KD.match)
    assert len(seen) == 2
    assert _split('thogut,"kafir harbi", deradikalisasi') == ["thogut", "kafir harbi", "deradikalisasi"]
