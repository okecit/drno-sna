"""Uji konektor Scrapling terhadap server HTTP lokal sungguhan (Fetcher asli, tanpa internet)."""
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("scrapling.fetchers")

from drno.collectors.base import JobConfig  # noqa: E402
from drno.collectors.web_scrapling import ScraplingWebCollector, load_sources  # noqa: E402
from drno.keywords import KeywordDictionary, compile_query  # noqa: E402

TODAY = datetime.now(timezone.utc).replace(microsecond=0)
D_IN = (TODAY - timedelta(days=1)).isoformat()
D_OLD = (TODAY - timedelta(days=40)).isoformat()
SEEN = []


def article(title, date, body):
    ld = json.dumps({"@context": "https://schema.org", "@type": "NewsArticle", "headline": title, "datePublished": date, "articleBody": body})
    return f'<html><head><script type="application/ld+json">{ld}</script></head><body><article><p>{body}</p></article></body></html>'


def make_handler(kind):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="text/html"):
            self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(body.encode())

        def do_GET(self):
            SEEN.append((kind, self.path, self.headers.get("User-Agent"), self.headers.get("Referer")))
            base = f"http://{self.headers['Host']}"
            if kind == "ok":
                if self.path == "/robots.txt":
                    return self.send(200, "User-agent: *\nDisallow: /terlarang/\nCrawl-delay: 0\n", "text/plain")
                if self.path == "/sitemap-news.xml":
                    urls = [("/berita/1", D_IN), ("/terlarang/2", D_IN), ("/berita/3", D_OLD), ("/berita/4", D_IN)]
                    items = "".join(f"<url><loc>{base}{u}</loc><lastmod>{d}</lastmod></url>" for u, d in urls)
                    return self.send(200, f'<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>', "application/xml")
                if self.path == "/berita/1":
                    return self.send(200, article("BNPT perkuat deradikalisasi", D_IN, "Program deradikalisasi diperluas ke daerah."))
                if self.path == "/berita/4":
                    return self.send(200, article("Harga cabai naik", D_IN, "Pasar tradisional ramai."))
                return self.send(200, article("x", D_IN, "radikalisasi"))
            if kind == "limit":
                if self.path == "/robots.txt":
                    return self.send(404, "")
                return self.send(429, "too many")
            if kind == "captcha":
                if self.path == "/robots.txt":
                    return self.send(200, "User-agent: *\nAllow: /\n", "text/plain")
                return self.send(200, "<html><title>Just a moment...</title><div class='cf-challenge'>captcha</div></html>")
    return H


@pytest.fixture(scope="module")
def servers():
    out = {}
    for kind in ("ok", "limit", "captcha"):
        srv = HTTPServer(("127.0.0.1", 0), make_handler(kind))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        out[kind] = f"http://127.0.0.1:{srv.server_port}"
    yield out


def job():
    return JobConfig(platform="web", query="radikalisasi OR deradikalisasi OR terorisme",
                     date_from=(TODAY - timedelta(days=7)).date().isoformat(), date_to=TODAY.date().isoformat(), legal_basis="uji")


def test_polite_crawl_end_to_end(servers, monkeypatch):
    monkeypatch.setenv("DRNO_PSEUDONYM_KEY", "k" * 40)
    SEEN.clear()
    src = [{"name": "Portal Uji", "enabled": True, "legal_basis": "uji", "sitemaps": [servers["ok"] + "/sitemap-news.xml"], "domain": servers["ok"][7:]}]
    col = ScraplingWebCollector(sources=src, contact="peneliti@example.ac.id", min_delay=0.05, _allow_private_for_tests=True)
    recs, inter, rep = col.run(job(), compile_query(job().query), KeywordDictionary.baseline().match)
    assert rep.status == "success"
    assert [r["url"].rsplit("/", 2)[-2:] for r in recs] == [["berita", "1"]]   # /3 lama, /4 tidak relevan, /terlarang/2 dilarang robots
    assert recs[0]["author_id_pseudonym"] == "media:Portal Uji" and recs[0]["source_method"] == "scrapling" and inter == []
    assert not any(p == "/terlarang/2" for _, p, _, _ in SEEN)                  # robots.txt dipatuhi: tidak pernah diminta
    uas = {ua for _, _, ua, _ in SEEN}
    assert all(ua.startswith("DRNO-research/") for ua in uas)                  # identitas jujur, bukan menyamar Chrome
    assert all(ref is None for _, _, _, ref in SEEN)                            # tanpa referer palsu


def test_rate_limit_and_challenge_stop_not_bypass(servers):
    srcs = [{"name": "Sibuk", "enabled": True, "legal_basis": "uji", "sitemaps": [servers["limit"] + "/s.xml"], "domain": servers["limit"][7:]},
            {"name": "Captcha", "enabled": True, "legal_basis": "uji", "listing_urls": [servers["captcha"] + "/"], "domain": servers["captcha"][7:]}]
    col = ScraplingWebCollector(sources=srcs, min_delay=0.01, _allow_private_for_tests=True)
    recs, _, _ = col.run(job(), lambda t: True, lambda t: [])
    assert recs == []
    assert "429" in col.blocked[servers["limit"][7:]] and "CAPTCHA" in col.blocked[servers["captcha"][7:]]


def test_forbidden_stealth_options_rejected(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"sources": [{"name": "X", "enabled": True, "legal_basis": "a", "sitemaps": ["https://x.id/s.xml"], "solve_cloudflare": True}]}))
    with pytest.raises(ValueError, match="terlarang"):
        load_sources(str(p))
    p.write_text(json.dumps({"sources": [{"name": "X", "enabled": True, "sitemaps": ["https://x.id/s.xml"]}]}))
    with pytest.raises(ValueError, match="legal_basis"):
        load_sources(str(p))


def test_mixed_source_domains_rejected(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"sources": [{"name": "X", "enabled": True, "legal_basis": "a",
                                           "sitemaps": ["https://x.id/s.xml"],
                                           "listing_urls": ["https://other.id/news"]}]}))
    with pytest.raises(ValueError, match="mencampur domain"):
        load_sources(str(p))


def test_outside_allowlist_is_skipped():
    src = [{"name": "X", "enabled": True, "legal_basis": "a", "sitemaps": ["https://x.id/s.xml"], "domain": "x.id"}]
    col = ScraplingWebCollector(sources=src, fetch=lambda url: None)
    assert col.get("http://127.0.0.1/internal") is None
    assert "allowlist" in col.skipped[-1][1]
