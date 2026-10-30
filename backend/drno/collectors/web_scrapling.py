"""Pengumpul portal berita & situs publik dengan Scrapling (mode sopan / *polite*).

Prinsip yang DIPAKSAKAN kode (bukan sekadar anjuran):
- Hanya domain yang terdaftar & diaktifkan peneliti di config/sources.json, masing-masing dengan legal_basis.
- robots.txt dipatuhi (termasuk Crawl-delay); robots tidak terbaca karena galat server -> domain dilewati.
- Identitas jujur: User-Agent DRNO + kontak. Penyamaran browser (impersonate), header "siluman",
  StealthyFetcher, solve_cloudflare, dan proxy rotation DITOLAK.
- Jeda minimal antarpermintaan per domain (default 5 detik); 403/429/503 atau halaman tantangan
  anti-bot/CAPTCHA -> domain dihentikan untuk siklus ini (tidak dicoba menembus).
- Penemuan artikel lewat sitemap (disediakan situs untuk mesin) atau halaman indeks + pola tautan.
- Metadata + teks artikel dipakai untuk analisis internal. Dashboard terautentikasi
  hanya dapat menampilkan cuplikan singkat dari media/Page publik; teks akun individu
  tidak diekspor pada mode data nyata.
"""
from __future__ import annotations

import json
import ipaddress
import os
import re
import socket
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from .base import Collector, JobConfig, NotConfigured

FORBIDDEN_KEYS = {"stealth", "stealthy", "solve_cloudflare", "impersonate", "stealthy_headers", "proxy", "proxies",
                  "proxy_rotator", "real_chrome", "hide_canvas", "cdp_url"}
CHALLENGE_MARKERS = ("cf-challenge", "challenge-platform", "captcha", "g-recaptcha", "hcaptcha", "turnstile",
                     "just a moment...", "attention required", "access denied")
ARTICLE_TYPES = {"NewsArticle", "Article", "ReportageNewsArticle", "AnalysisNewsArticle", "OpinionNewsArticle", "BlogPosting"}
REDIRECT_STATUS = {301, 302, 303, 307, 308}


def _parsed_http_url(url: str):
    u = urlparse(str(url).strip())
    if u.scheme not in {"http", "https"} or not u.hostname or u.username or u.password:
        raise ValueError(f"URL sumber tidak aman/tidak valid: {url!r}")
    return u


def _assert_public_destination(url: str) -> None:
    """Tolak localhost, IP privat/link-local/reserved, dan host tanpa DNS publik."""
    u = _parsed_http_url(url)
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except socket.gaierror as e:
        raise ValueError(f"DNS sumber tidak dapat diverifikasi: {u.hostname}") from e
    if not addresses:
        raise ValueError(f"DNS sumber tidak memiliki alamat: {u.hostname}")
    for raw in addresses:
        ip = ipaddress.ip_address(raw.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError(f"Tujuan non-publik ditolak: {u.hostname} -> {ip}")


def _parse_dt(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00")) if fmt is None else datetime.strptime(s, fmt)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def load_sources(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    sources = [s for s in cfg.get("sources", []) if s.get("enabled")]
    for s in sources:
        bad = FORBIDDEN_KEYS & set(map(str.lower, s.keys()))
        if bad:
            raise ValueError(f"Sumber '{s.get('name')}' memakai opsi terlarang {sorted(bad)} (penyamaran/penembusan anti-bot)")
        if not s.get("legal_basis"):
            raise ValueError(f"Sumber '{s.get('name')}' wajib punya legal_basis (dasar izin/ToS)")
        urls = [*s.get("sitemaps", []), *s.get("listing_urls", [])]
        if not urls:
            raise ValueError(f"Sumber '{s.get('name')}' wajib punya sitemaps atau listing_urls")
        parsed = [_parsed_http_url(url) for url in urls]
        domain = parsed[0].netloc.lower()
        if any(u.netloc.lower() != domain for u in parsed):
            raise ValueError(f"Sumber '{s.get('name')}' mencampur domain; buat entri sumber terpisah")
        s["domain"] = domain
    return sources


class ScraplingWebCollector(Collector):
    platform = "news"
    source_method = "scrapling"

    def __init__(self, sources_path: str | None = None, sources: list[dict] | None = None, contact: str | None = None,
                 min_delay: float | None = None, fetch=None, sleep=time.sleep, max_body_chars: int = 6000,
                 _allow_private_for_tests: bool = False, **kw):
        super().__init__(**kw)
        path = sources_path or os.environ.get("DRNO_SOURCES", "config/sources.json")
        if sources is None:
            if not os.path.exists(path):
                raise NotConfigured(f"Berkas sumber {path} tidak ada (salin config/sources.example.json)")
            sources = load_sources(path)
        if not sources:
            raise NotConfigured("Tidak ada sumber yang enabled di config/sources.json")
        self.sources = sources
        self.allowed_domains = {str(s["domain"]).lower() for s in sources}
        contact = contact or os.environ.get("DRNO_CONTACT", "")
        site = os.environ.get("DRNO_DOMAIN", "")
        self.ua = f"DRNO-research/0.8 (penelitian akademik; +https://{site}; {contact})".replace("+https://;", "").strip()
        self.min_delay = float(min_delay if min_delay is not None else os.environ.get("DRNO_SCRAPE_DELAY", 5))
        self._fetch = fetch or self._scrapling_get
        self._sleep = sleep
        self._last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._delay: dict[str, float] = {}
        self.blocked: dict[str, str] = {}
        self.skipped: list[tuple[str, str]] = []
        self.max_body = max_body_chars
        self._allow_private_for_tests = _allow_private_for_tests

    # ---------- HTTP sopan ----------
    def _assert_allowed_url(self, url):
        u = _parsed_http_url(url)
        if u.netloc.lower() not in self.allowed_domains:
            raise ValueError(f"Domain di luar allowlist sumber ditolak: {u.netloc}")
        return u

    def _scrapling_get(self, url):
        from scrapling.fetchers import Fetcher
        # Redirect diikuti manual agar setiap tujuan tetap berada pada domain allowlist
        # dan tidak menuju localhost/jaringan privat.
        current = url
        for _ in range(6):
            self._assert_allowed_url(current)
            if not self._allow_private_for_tests:
                _assert_public_destination(current)
            # impersonate=None & stealthy_headers=False: tidak menyamar sebagai browser.
            r = Fetcher.get(current, impersonate=None, stealthy_headers=False, timeout=30, retries=1, follow_redirects=False,
                            headers={"User-Agent": self.ua, "Accept-Language": "id,en;q=0.5"})
            if r.status not in REDIRECT_STATUS:
                return r
            location = r.headers.get("location") if getattr(r, "headers", None) else None
            if not location:
                return r
            current = urljoin(current, location)
        raise ValueError("Terlalu banyak redirect pada sumber")

    def _wait(self, domain):
        gap = self._delay.get(domain, self.min_delay)
        dt = time.monotonic() - self._last.get(domain, -1e9)
        if dt < gap:
            self._sleep(gap - dt)
        self._last[domain] = time.monotonic()

    def _robots_for(self, domain, scheme):
        if domain in self._robots:
            return self._robots[domain]
        self._wait(domain)
        rp = RobotFileParser()
        try:
            r = self._fetch(f"{scheme}://{domain}/robots.txt")
            if r.status >= 500:
                rp = None
            elif r.status >= 400:
                rp.parse([])            # tidak ada robots.txt -> diizinkan (RFC 9309)
            else:
                rp.parse(r.body.decode("utf-8", "replace").splitlines() if isinstance(r.body, bytes) else str(r.body).splitlines())
                cd = rp.crawl_delay(self.ua) or rp.crawl_delay("*")
                if cd:
                    self._delay[domain] = max(self.min_delay, float(cd))
        except Exception as e:  # noqa: BLE001
            rp = None
            self.skipped.append((domain, f"robots.txt tidak terbaca: {e.__class__.__name__}"))
        self._robots[domain] = rp
        return rp

    def get(self, url):
        """GET dengan robots.txt, jeda, dan deteksi blokir. None bila tidak boleh/terblokir."""
        try:
            u = self._assert_allowed_url(url)
        except ValueError as e:
            self.skipped.append((url, str(e)))
            return None
        domain = u.netloc.lower()
        if domain in self.blocked:
            return None
        rp = self._robots_for(domain, u.scheme or "https")
        if rp is None:
            self.blocked[domain] = "robots.txt tidak dapat dipastikan"
            return None
        if not rp.can_fetch(self.ua, url):
            self.skipped.append((url, "dilarang robots.txt"))
            return None
        self._wait(domain)
        try:
            r = self._fetch(url)
        except Exception as e:  # noqa: BLE001
            self.skipped.append((url, f"galat jaringan: {e.__class__.__name__}"))
            return None
        if r.status in (403, 429, 503):
            self.blocked[domain] = f"HTTP {r.status} - dihentikan, tidak ditembus"
            return None
        body = r.body if isinstance(r.body, (bytes, str)) else b""
        head = (body[:20000].decode("utf-8", "replace") if isinstance(body, bytes) else body[:20000]).lower()
        if any(m in head for m in CHALLENGE_MARKERS) and not r.css('script[type="application/ld+json"]'):
            self.blocked[domain] = "halaman tantangan anti-bot/CAPTCHA - dihentikan, tidak ditembus"
            return None
        if r.status != 200:
            self.skipped.append((url, f"HTTP {r.status}"))
            return None
        return r

    # ---------- penemuan artikel ----------
    def _from_sitemap(self, url, depth=0):
        r = self.get(url)
        if r is None:
            return []
        raw = r.body if isinstance(r.body, bytes) else str(r.body).encode()
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            self.skipped.append((url, "sitemap tidak valid"))
            return []
        ns = lambda t: t.split("}")[-1]
        out = []
        if ns(root.tag) == "sitemapindex" and depth < 1:
            for sm in root:
                loc = next((c.text for c in sm if ns(c.tag) == "loc"), None)
                if loc:
                    out += self._from_sitemap(loc.strip(), depth + 1)
            return out
        for u in root:
            loc = d = title = None
            for c in u.iter():
                t = ns(c.tag)
                if t == "loc" and loc is None:
                    loc = (c.text or "").strip()
                elif t in ("publication_date", "lastmod") and not d:
                    d = _parse_dt(c.text)
                elif t == "title":
                    title = (c.text or "").strip()
            if loc:
                out.append({"url": loc, "date": d, "title": title})
        return out

    def _from_listing(self, src):
        pat = re.compile(src.get("link_pattern", r".+"))
        out, seen = [], set()
        for lu in src.get("listing_urls", []):
            r = self.get(lu)
            if r is None:
                continue
            for href in r.css("a::attr(href)").getall():
                full = urljoin(lu, href.strip()).split("#")[0]
                if urlparse(full).netloc.lower() == src["domain"] and pat.search(full) and full not in seen:
                    seen.add(full)
                    out.append({"url": full, "date": None, "title": None})
        return out

    # ---------- ekstraksi ----------
    def _extract(self, r, src, hint):
        data = {}
        for js in r.css('script[type="application/ld+json"]::text').getall():
            try:
                obj = json.loads(js)
            except (ValueError, TypeError):
                continue
            cands = obj if isinstance(obj, list) else obj.get("@graph", [obj]) if isinstance(obj, dict) else []
            for o in cands:
                t = o.get("@type") if isinstance(o, dict) else None
                t = set(t) if isinstance(t, list) else {t}
                if t & ARTICLE_TYPES:
                    data = o
                    break
            if data:
                break
        meta = lambda sel: (r.css(sel).get() or "").strip()
        title = data.get("headline") or meta('meta[property="og:title"]::attr(content)') or hint.get("title") or meta("title::text")
        desc = data.get("description") or meta('meta[name="description"]::attr(content)') or meta('meta[property="og:description"]::attr(content)')
        dt = (_parse_dt(data.get("datePublished")) or _parse_dt(meta('meta[property="article:published_time"]::attr(content)'))
              or _parse_dt(meta('meta[name="pubdate"]::attr(content)')) or hint.get("date"))
        body = data.get("articleBody") or " ".join(t.strip() for t in r.css(f'{src.get("body_selector", "article p")}::text').getall() if t.strip())
        parts = []
        for x in (title, desc, body):  # buang bagian yang duplikat (mis. description = headline)
            x = (x or "").strip()
            if x and not any(x.lower() in p.lower() for p in parts):
                parts.append(x)
        text = ". ".join(parts)
        return {"title": title, "date": dt, "text": re.sub(r"\s+", " ", text)[: self.max_body]}

    # ---------- antarmuka Collector ----------
    def fetch(self, job: JobConfig):
        d0 = _parse_dt(job.date_from)
        d1 = _parse_dt(job.date_to + "T23:59:59") if job.date_to else None
        for src in self.sources:
            cap = int(src.get("max_articles", 50))
            cands = []
            for sm in src.get("sitemaps", []):
                cands += self._from_sitemap(sm)
            if src.get("listing_urls"):
                cands += self._from_listing(src)
            n, seen = 0, set()
            for c in cands:
                if n >= cap or src["domain"] in self.blocked:
                    break
                if c["url"] in seen or urlparse(c["url"]).netloc.lower() != src["domain"]:
                    continue
                seen.add(c["url"])
                if c["date"] and ((d0 and c["date"] < d0) or (d1 and c["date"] > d1)):
                    continue
                r = self.get(c["url"])
                if r is None:
                    continue
                a = self._extract(r, src, c)
                if not a["date"] or (d0 and a["date"] < d0) or (d1 and a["date"] > d1) or not a["text"]:
                    continue
                n += 1
                yield {"id": c["url"], "author": src["name"], "ts": a["date"].isoformat(), "text": a["text"], "url": c["url"]}
            if src["domain"] in self.blocked:
                self.skipped.append((src["name"], self.blocked[src["domain"]]))

    def author_key(self, native_author_id) -> str:
        return f"media:{native_author_id}"  # entitas publik (media), tidak dipseudonimkan

    def to_record(self, raw, job, matched):
        return self.base_record(native_post_id=raw["id"], native_author_id=raw["author"], ts=raw["ts"], text=raw["text"],
                                url=raw["url"], job=job, matched=matched)
