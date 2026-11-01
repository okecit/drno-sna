import json

import httpx

from drno.page_discovery import PageDiscovery, accepted_pages, candidate_handle, discover

PROFILES = {
    "PageTakfiri": {"name": "Page Takfiri", "category": "Tokoh publik", "followerCount": 52000},
    "PageNetral": {"name": "Page Netral", "category": "Organisasi keagamaan", "followerCount": 90000},
    "PageKecil": {"name": "Page Kecil", "category": "Komunitas", "followerCount": 900},
    "OrangBiasa": {"name": "Orang Biasa", "isPrivate": True},
    "ProfilTanpaKategori": {"name": "Profil Pribadi", "followerCount": 500000},
}
POSTS = {"PageTakfiri": ["pemerintah thogut wajib dijauhi", "demokrasi itu thaghut", "doa pagi"], "PageNetral": ["doa pagi", "kajian fiqih", "infaq"]}


def _transport(seen):
    def handler(req):
        seen.append(req.url.path)
        if req.url.path == "/v1/google/search":
            return httpx.Response(200, json={"results": [
                {"url": f"https://www.facebook.com/{h}/posts/1", "title": h} for h in PROFILES] + [
                {"url": "https://www.facebook.com/groups/123/", "title": "grup"}, {"url": "https://www.facebook.com/profile.php?id=9", "title": "profil"}]})
        h = req.url.params.get("url", "").rsplit("/", 1)[-1]
        if req.url.path == "/v1/facebook/profile":
            return httpx.Response(200, json=PROFILES.get(h, {}))
        if req.url.path == "/v1/facebook/profile/posts":
            return httpx.Response(200, json={"posts": [{"text": t} for t in POSTS.get(h, [])]})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_candidate_handle_rejects_groups_and_profile_php():
    assert candidate_handle("https://www.facebook.com/PageTakfiri/posts/1") == "PageTakfiri"
    assert candidate_handle("https://m.facebook.com/groups/123/") is None
    assert candidate_handle("https://www.facebook.com/profile.php?id=9") is None


def test_only_public_pages_above_threshold_scored(tmp_path):
    seen = []
    pd = PageDiscovery(api_key="k", transport=_transport(seen), queries=['"pemerintah thogut"'], max_candidates=10)
    pd.min_tone = 0.0
    out = {c["handle"]: c for c in pd.run(exclude=set())}
    assert set(out) == {"PageTakfiri", "PageNetral"}  # privat, tanpa kategori, dan di bawah ambang dibuang
    assert out["PageTakfiri"]["tone_score"] == 0.67 and "thaghut" in out["PageTakfiri"]["matched_terms"]
    assert out["PageNetral"]["tone_score"] == 0.0
    assert "OrangBiasa" not in json.dumps(list(out.values()))
    pd2 = PageDiscovery(api_key="k", transport=_transport([]), queries=["x"])  # default: nada minimal 1/3 posting
    assert [c["handle"] for c in pd2.run(exclude=set())] == ["PageTakfiri"]


def test_discover_writes_candidates_and_accepted_pages(tmp_path, monkeypatch):
    cand, rev = tmp_path / "cand.json", tmp_path / "rev.json"
    rev.write_text(json.dumps({"decisions": [{"handle": "PageNetral", "decision": "reject"}]}), encoding="utf-8")
    monkeypatch.setenv("FB_SC_PAGES", "")
    res = discover(str(cand), str(rev), api_key="k", transport=_transport([]), queries=["x"])
    data = json.loads(cand.read_text(encoding="utf-8"))
    assert res["new_candidates"] == 1 and [c["handle"] for c in data["candidates"]] == ["PageTakfiri"]  # yang ditolak tidak diusulkan ulang
    rev.write_text(json.dumps({"decisions": [{"handle": "PageTakfiri", "decision": "accept"}, {"handle": "bad/handle", "decision": "accept"}]}), encoding="utf-8")
    assert accepted_pages(str(rev)) == ["https://www.facebook.com/PageTakfiri"]
