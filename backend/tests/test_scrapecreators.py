import os

os.environ.setdefault("DRNO_PSEUDONYM_KEY", "k" * 40)

import httpx  # noqa: E402

from drno.collectors.base import JobConfig  # noqa: E402
from drno.collectors.scrapecreators_fb import ScrapeCreatorsFacebookCollector, _ts, page_handle  # noqa: E402
from drno.keywords import KeywordDictionary  # noqa: E402


def _transport(seen):
    def handler(req):
        seen.append(req)
        if req.url.path == "/v1/facebook/profile/posts":
            return httpx.Response(200, json={"posts": [
                {"id": "p2", "text": "Waspada propaganda terorisme", "url": "https://fb/p2", "publishTime": 1761800000, "reactionCount": 5, "commentCount": 2,
                 "author": {"name": "Lembaga Publik Contoh"}},
                {"id": "p1", "text": "Posting lama soal terorisme", "url": "https://fb/p1", "publishTime": 1700000000}]})
        if req.url.path == "/v1/facebook/post/comments":
            return httpx.Response(200, json={"comments": [
                {"id": "c1", "text": "setuju", "created_at": "2025-10-30T05:00:00Z", "reaction_count": 1, "author": {"name": "Budi Warga", "id": "100001"}}]})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def _job():
    return JobConfig(platform="facebook_sc", query="terorisme", date_from="2025-10-01", date_to="2025-10-31", legal_basis="uji")


def test_page_named_commenter_pseudonymized_and_name_not_stored():
    seen = []
    col = ScrapeCreatorsFacebookCollector(api_key="k", pages=["https://www.facebook.com/lembagacontoh/"], transport=_transport(seen))
    recs, inter, rep = col.run(_job(), lambda t: "terorisme" in t, KeywordDictionary.baseline().match)
    post, comment = recs  # posting lama (sebelum date_from) tidak diambil
    assert post["author_id_pseudonym"] == "page:lembagacontoh" and post["public_entity_name"] == "Lembaga Publik Contoh"
    assert post["source_method"] == "scrapecreators" and post["platform"] == "facebook"
    assert comment["author_id_pseudonym"].startswith("fa_") and "Budi" not in str(comment)
    assert inter[0]["target"] == "page:lembagacontoh"
    assert all(r.headers["x-api-key"] == "k" for r in seen)


def test_credit_cap_stops_calls():
    seen = []
    col = ScrapeCreatorsFacebookCollector(api_key="k", pages=["a", "b", "c"], transport=_transport(seen), max_calls=2)
    col.run(_job(), lambda t: True, KeywordDictionary.baseline().match)
    assert len(seen) == 2 and col.calls == 2


def test_helpers():
    assert page_handle("https://m.facebook.com/bnptri/?ref=x") == "bnptri" and page_handle("123456") == "123456"
    assert _ts(1761800000) == _ts(1761800000000) == _ts("2025-10-30T04:53:20Z")


def test_comment_replies_create_commenter_to_commenter_edges():
    def handler(req):
        if req.url.path == "/v1/facebook/profile/posts":
            return httpx.Response(200, json={"posts": [{"id": "p2", "text": "terorisme", "url": "https://fb/p2", "publishTime": 1761800000}]})
        if req.url.path == "/v1/facebook/post/comments":
            return httpx.Response(200, json={"comments": [
                {"id": "c1", "text": "a", "created_at": "2025-10-30T05:00:00Z", "reply_count": 2, "feedback_id": "f1", "expansion_token": "e1",
                 "author": {"name": "Budi Warga", "id": "100001"}}]})
        if req.url.path == "/v1/facebook/post/comment/replies":
            assert req.url.params["feedback_id"] == "f1" and req.url.params["expansion_token"] == "e1"
            return httpx.Response(200, json={"replies": [
                {"id": "r1", "text": "b", "created_at": "2025-10-30T06:00:00Z", "author": {"name": "Sari Warga", "id": "100002"}}]})
        return httpx.Response(404)
    col = ScrapeCreatorsFacebookCollector(api_key="k", pages=["lembagacontoh"], transport=httpx.MockTransport(handler))
    recs, inter, _ = col.run(_job(), lambda t: "terorisme" in t, KeywordDictionary.baseline().match)
    post, c1, r1 = recs
    assert r1["reply_to"] == "facebook:c1" and "Sari" not in str(r1)
    edge = [i for i in inter if i["type"] == "comment_reply"][0]
    assert edge["source"] == r1["author_id_pseudonym"] and edge["target"] == c1["author_id_pseudonym"]
