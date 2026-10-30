"""Uji konektor nyata terhadap format respons API resmi (httpx.MockTransport, tanpa jaringan)."""
import json

import httpx
import pytest

from drno.analyze import export_dashboard
from drno.collectors.base import JobConfig, NotConfigured
from drno.collectors.facebook import FacebookPagesCollector
from drno.collectors.instagram import InstagramHashtagCollector
from drno.collectors.x_api import XCollector
from drno.collectors.youtube import YouTubeCollector
from drno.keywords import KeywordDictionary, compile_query
from drno.storage import JsonlStore


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("DRNO_PSEUDONYM_KEY", "k" * 40)


def job(p, q="radikalisasi OR terorisme OR deradikalisasi"):
    return JobConfig(platform=p, query=q, date_from="2026-10-15", date_to="2026-10-22", max_records=100, legal_basis="uji")


def run(col, j, pred=None):
    kd = KeywordDictionary.baseline()
    return col.run(j, pred or compile_query(j.query), kd.match)


X_PAGE = {"data": [
    {"id": "1", "author_id": "u1", "created_at": "2026-10-20T01:00:00Z", "text": "Kami menolak terorisme @u2", "lang": "in",
     "entities": {"mentions": [{"id": "u2", "username": "b"}]}, "public_metrics": {"like_count": 3, "retweet_count": 1}},
    {"id": "2", "author_id": "u3", "created_at": "2026-10-20T02:00:00Z", "text": "Setuju, deradikalisasi penting", "lang": "in",
     "in_reply_to_user_id": "u1", "referenced_tweets": [{"type": "replied_to", "id": "1"}]},
    {"id": "3", "author_id": "u4", "created_at": "2026-10-20T03:00:00Z", "text": "RT radikalisasi daring", "lang": "in",
     "referenced_tweets": [{"type": "quoted", "id": "9"}]},
    {"id": "4", "author_id": "u5", "created_at": "2026-10-20T04:00:00Z", "text": "cuaca cerah hari ini", "lang": "in"}],
    "includes": {"tweets": [{"id": "9", "author_id": "u9"}]}, "meta": {"result_count": 4}}


def test_x_connector_parses_interactions():
    seen = {}
    def h(req):
        seen["auth"] = req.headers["authorization"]; seen["q"] = req.url.params["query"]
        return httpx.Response(200, json=X_PAGE)
    col = XCollector(bearer="T", transport=httpx.MockTransport(h))
    recs, inter, rep = run(col, job("x"))
    assert seen["auth"] == "Bearer T" and "lang:in" in seen["q"]
    assert rep.status == "success" and len(recs) == 3  # post 'cuaca' tersaring
    assert {i["type"] for i in inter} == {"mention", "reply", "repost"}
    assert all(r["author_id_pseudonym"].startswith("x_") and "u1" not in r["author_id_pseudonym"] for r in recs)
    assert all(r["is_synthetic"] is False for r in recs)


def test_x_rate_limit_backoff(monkeypatch):
    calls = {"n": 0}
    def h(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"retry-after": "0"}) if calls["n"] == 1 else httpx.Response(200, json=X_PAGE)
    monkeypatch.setattr("time.sleep", lambda s: None)
    recs, _, rep = run(XCollector(bearer="T", transport=httpx.MockTransport(h)), job("x"))
    assert calls["n"] == 2 and len(recs) == 3


def test_youtube_comments_and_replies():
    def h(req):
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "v1"}, "snippet": {"channelId": "chA", "publishedAt": "2026-10-18T00:00:00Z",
                                  "title": "Diskusi deradikalisasi", "description": ""}}]})
        return httpx.Response(200, json={"items": [{"snippet": {"topLevelComment": {"id": "c1", "snippet": {
            "authorChannelId": {"value": "chB"}, "publishedAt": "2026-10-18T01:00:00Z", "textOriginal": "mantap kajiannya", "likeCount": 2}}},
            "replies": {"comments": [{"id": "c2", "snippet": {"authorChannelId": {"value": "chC"}, "publishedAt": "2026-10-18T02:00:00Z",
                                                              "textOriginal": "setuju"}}]}}]})
    recs, inter, rep = run(YouTubeCollector(api_key="K", transport=httpx.MockTransport(h)), job("youtube"))
    assert len(recs) == 3  # video + komentar + balasan (komentar dipertahankan sebagai bagian percakapan)
    assert sorted(i["type"] for i in inter) == ["comment", "comment_reply"]


def test_instagram_hashtag_no_owner_no_network():
    def h(req):
        if req.url.path.endswith("ig_hashtag_search"):
            if req.url.params["q"] == "sensitif":
                return httpx.Response(400, json={"error": {"message": "generic"}})
            return httpx.Response(200, json={"data": [{"id": "h1"}]})
        return httpx.Response(200, json={"data": [{"id": "m1", "caption": "#moderasiberagama itu indah", "timestamp": "2026-10-21T10:00:00+0000",
                                                   "like_count": 5, "comments_count": 1, "permalink": "https://instagram.com/p/x"}]})
    col = InstagramHashtagCollector(token="T", ig_user_id="U", hashtags=["moderasiberagama", "sensitif"], transport=httpx.MockTransport(h))
    recs, inter, rep = run(col, job("instagram"), pred=lambda t: True)
    assert len(recs) == 1 and recs[0]["author_id_pseudonym"] == "ig_hashtag_media" and inter == []
    assert col.skipped and col.skipped[0][0] == "sensitif"


def test_instagram_hashtag_limit():
    with pytest.raises(ValueError):
        InstagramHashtagCollector(token="T", ig_user_id="U", hashtags=[f"h{i}" for i in range(31)])


def test_facebook_page_comments_with_missing_from():
    def h(req):
        if req.url.path.endswith("/posts"):
            return httpx.Response(200, json={"data": [{"id": "P_1", "message": "Polisi: terorisme ditangani", "created_time": "2026-10-19T00:00:00+0000",
                                                       "permalink_url": "https://fb.com/1"}]})
        return httpx.Response(200, json={"data": [
            {"id": "c1", "message": "tolak radikalisasi", "created_time": "2026-10-19T01:00:00+0000", "from": {"id": "fbU1"}},
            {"id": "c2", "message": "setuju", "created_time": "2026-10-19T02:00:00+0000"},
            {"id": "c3", "message": "betul", "created_time": "2026-10-19T03:00:00+0000", "from": {"id": "fbU2"}, "parent": {"id": "c1", "from": {"id": "fbU1"}}}]})
    col = FacebookPagesCollector(token="T", page_ids=["P"], transport=httpx.MockTransport(h))
    recs, inter, rep = run(col, job("facebook"))
    assert len(recs) == 4
    assert recs[0]["author_id_pseudonym"] == "page:P"
    assert sorted(i["type"] for i in inter) == ["comment", "comment_reply"]  # c2 tanpa 'from' -> tanpa edge


def test_missing_credentials_and_legal_basis(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    with pytest.raises(NotConfigured):
        XCollector()
    col = XCollector(bearer="T", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=X_PAGE)))
    j = job("x"); j.legal_basis = ""
    with pytest.raises(NotConfigured):
        run(col, j)


def test_real_store_to_dashboard_exports(tmp_path):
    store = JsonlStore(tmp_path / "data")
    col = XCollector(bearer="T", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=X_PAGE)))
    j = job("x"); recs, inter, rep = run(col, j)
    store.save(recs, inter, rep, j)
    store.save(recs, inter, rep, j)  # dedup
    posts, it, runs = store.load()
    assert len(posts) == 3 and len(runs) == 2 and runs[1]["inserted"] == 0
    res = export_dashboard(posts, it, tmp_path / "out", "real")
    assert res["posts"] == 3
    for f in ["platform_context.csv", "platform_sentiment.csv", "platform_stance.csv", "platform_summary.csv", "overview.csv", "posts_REAL.csv"]:
        assert (tmp_path / "out" / f).exists()
    assert "real" in (tmp_path / "out" / "overview.csv").read_text()
