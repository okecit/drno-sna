import os

os.environ.setdefault("DRNO_PSEUDONYM_KEY", "k" * 40)

import httpx  # noqa: E402

from drno.collectors.base import JobConfig  # noqa: E402
from drno.collectors.facebook import FacebookPagesCollector, resolve_pages  # noqa: E402
from drno.explorer import entity_kind  # noqa: E402
from drno.keywords import KeywordDictionary  # noqa: E402


def _transport():
    def handler(req):
        p = req.url.path
        if p.endswith("/123/posts"):
            return httpx.Response(200, json={"data": [{"id": "123_1", "message": "Waspada propaganda terorisme di media sosial",
                                                        "created_time": "2026-10-30T01:00:00+0000", "permalink_url": "https://fb/1"}]})
        if p.endswith("/123_1/comments"):
            return httpx.Response(200, json={"data": [{"id": "c1", "message": "setuju", "created_time": "2026-10-30T02:00:00+0000", "from": {"id": "999"}}]})
        if p.endswith("/123"):
            return httpx.Response(200, json={"id": "123", "name": "Badan Contoh Publik"})
        if p.endswith("/bnptri"):
            return httpx.Response(200, json={"id": "456", "name": "BNPT RI", "link": "https://facebook.com/bnptri"})
        return httpx.Response(404, json={"error": {"message": "Page tidak ditemukan"}})
    return httpx.MockTransport(handler)


def test_page_named_commenter_pseudonymous():
    col = FacebookPagesCollector(token="t", page_ids=["123"], transport=_transport())
    job = JobConfig(platform="facebook", query="terorisme", date_from="2026-10-01", date_to="2026-10-31", legal_basis="uji")
    recs, inter, rep = col.run(job, lambda t: "terorisme" in t, KeywordDictionary.baseline().match)
    post, comment = recs
    assert post["author_id_pseudonym"] == "page:123" and post["public_entity_name"] == "Badan Contoh Publik"
    assert post["author_type"] == "organization_public"
    assert comment["author_id_pseudonym"].startswith("fa_") and "public_entity_name" not in comment
    assert inter and inter[0]["target"] == "page:123"
    assert entity_kind("page:123", {"page:123": {"type": "organization_public", "name": "Badan Contoh Publik"}}) == ("page", "Badan Contoh Publik")
    assert entity_kind("page:777", {}) == ("page", "777")  # tanpa nama: tetap tampil sebagai ID


def test_resolve_pages_from_username_and_url():
    rows = resolve_pages(["bnptri", "https://www.facebook.com/tidakada/"], token="t", transport=_transport())
    assert rows[0]["id"] == "456" and rows[0]["name"] == "BNPT RI"
    assert rows[1]["id"] == "" and "tidak ditemukan" in rows[1]["error"]
