"""Platform yang sengaja TIDAK diintegrasikan tanpa akses riset resmi/izin tertulis."""
from .base import NotConfigured

RESTRICTED = {"tiktok": "TikTok Research API (aplikasi peneliti)", "telegram": "izin admin kanal/grup",
              "discord": "izin server", "reddit": "Reddit Data API resmi (belum diimplementasikan)"}


def get_restricted(platform: str):
    raise NotConfigured(f"{platform}: hanya diintegrasikan dengan {RESTRICTED.get(platform, 'akses resmi')}")
