"""Klien HTTP bersama. Dapat diganti httpx.MockTransport untuk pengujian."""
import httpx

from .base import RateLimited

UA = {"User-Agent": "DRNO-research/0.2 (penelitian akademik)"}


def make_client(transport=None) -> httpx.Client:
    return httpx.Client(timeout=30, headers=UA, transport=transport)


def check(r: httpx.Response):
    if r.status_code == 429:
        ra = r.headers.get("retry-after") or r.headers.get("x-rate-limit-reset")
        raise RateLimited(retry_after=float(ra) if ra and float(ra) < 3600 else 60)
    r.raise_for_status()
    return r.json()
