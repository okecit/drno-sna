"""Pseudonimisasi & retensi (Bagian 9).

Identitas akun individual diganti HMAC-SHA256(platform:id) dengan kunci rahasia yang
disimpan di luar database (variabel lingkungan DRNO_PSEUDONYM_KEY). Tanpa kunci, pseudonim
tidak dapat dibalik. Akun media/organisasi publik boleh memakai nama publiknya.
"""
import hashlib
import hmac
import os
from datetime import date, timedelta


def _key() -> bytes:
    k = os.environ.get("DRNO_PSEUDONYM_KEY")
    if not k:
        raise RuntimeError("Set DRNO_PSEUDONYM_KEY (minimal 32 karakter acak) sebelum memproses data nyata.")
    return k.encode()


def pseudonymize(platform: str, native_id: str, key: bytes | None = None) -> str:
    digest = hmac.new(key or _key(), f"{platform}:{native_id}".encode(), hashlib.sha256).hexdigest()
    return f"{platform[:2]}_{digest[:16]}"


def content_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.lower().split()).encode()).hexdigest()


def retention_until(days: int = 730) -> date:
    return date.today() + timedelta(days=days)
