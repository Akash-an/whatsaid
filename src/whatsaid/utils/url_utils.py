"""URL extraction, normalisation, and platform detection utilities."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import tldextract
from urlextract import URLExtract

_extractor = URLExtract()

# Tracking query-string keys to strip when normalising URLs.
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "igshid", "fbclid", "si", "share_id"}
)

# Domain → human-readable platform name.
# Use a callable value for context-sensitive mappings.
_PLATFORM_MAP: dict[str, str | object] = {
    "instagram": "Instagram",
    "youtube": "YouTube",
    "youtu": "YouTube",        # youtu.be short links
    "goo": "Google Maps",      # goo.gl short links
    "booking": "Booking.com",
    "airbnb": "Airbnb",
    "tripadvisor": "Tripadvisor",
    "reddit": "Reddit",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "fb": "Facebook",
    "agoda": "Agoda",
}


def extract_urls(text: str) -> list[str]:
    """Return all URLs found in *text*."""
    return _extractor.find_urls(text)


def normalize_url(url: str) -> str:
    """Strip tracking parameters and normalise *url* to a canonical form."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    clean_qs = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in _TRACKING_PARAMS]
    path = parsed.path.rstrip("/")

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        path,
        parsed.params,
        urlencode(clean_qs),
        parsed.fragment,
    ))


def get_platform(url: str) -> str:
    """Detect and return a human-readable platform name for *url*."""
    domain = tldextract.extract(url).domain.lower()

    if domain == "google":
        return "Google Maps" if ("/maps" in url or "/search" in url) else "Google"

    return _PLATFORM_MAP.get(domain, "Other")  # type: ignore[return-value]
