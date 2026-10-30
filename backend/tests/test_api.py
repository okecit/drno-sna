from fastapi.testclient import TestClient

from drno.api import app

c = TestClient(app)


def test_every_response_flags_synthetic():
    for path in ["/health", "/overview", "/narratives", "/temporal", "/network"]:
        r = c.get(path)
        assert r.status_code == 200 and r.json()["is_synthetic"] is True


def test_network_filter_and_caution():
    r = c.get("/network", params={"start": "2026-02-09", "end": "2026-02-22", "types": ["reply"]}).json()
    assert "caution" in r and r["summary"]["n_edges"] > 0


def test_export_formats():
    for f in ["csv", "json", "graphml", "gexf"]:
        assert c.get(f"/export/{f}").status_code == 200
