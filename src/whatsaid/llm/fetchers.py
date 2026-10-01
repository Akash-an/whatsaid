"""Platform-specific metadata fetchers for resource enrichment.

Each fetcher returns a ``FetchResult`` dataclass with normalised fields.
They never raise — errors are captured in ``FetchResult.error``.

Supported platforms:
    - YouTube  — via the public oEmbed API (no auth, no key required).
                 Handles regular watch URLs, youtu.be short links, AND
                 YouTube Shorts (``/shorts/VIDEO_ID``).
    - Instagram — via Meta's tokenless oEmbed endpoint
                 (``graph.facebook.com/v25.0/instagram_oembed``).
                 Plain HTTP requests are blocked by Instagram's TLS
                 fingerprinting, so browser-UA scraping is unreliable.
    - Generic  — via requests + BeautifulSoup, reading og:/twitter:/title
                 meta tags in priority order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Browser-like headers (used for generic fetches)
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_TIMEOUT = 10  # seconds


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class FetchResult:
    """Normalised metadata from a fetched URL.

    Fields are all optional so callers can gracefully handle partial results.
    ``error`` is set when the fetch failed entirely or was blocked.
    """

    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    thumbnail_url: Optional[str] = None
    raw_text: Optional[str] = None
    extra: dict = field(default_factory=dict)
    error: Optional[str] = None

    def has_content(self) -> bool:
        """Return True if at least one content field is populated."""
        return any([self.title, self.author, self.description, self.raw_text])


# ---------------------------------------------------------------------------
# YouTube — oEmbed API
# ---------------------------------------------------------------------------

_YOUTUBE_OEMBED_BASE = "https://www.youtube.com/oembed"


def _normalize_youtube_url(url: str) -> str:
    """Rewrite Shorts and youtu.be URLs to a standard watch URL for oEmbed.

    oEmbed does not support ``/shorts/VIDEO_ID`` — it returns 4xx.
    youtu.be short links work fine as-is, but we normalise them too for
    consistency.
    """
    # /shorts/VIDEO_ID  →  ?v=VIDEO_ID
    shorts_match = re.search(r"youtube\.com/shorts/([A-Za-z0-9_-]+)", url)
    if shorts_match:
        return f"https://www.youtube.com/watch?v={shorts_match.group(1)}"

    # youtu.be/VIDEO_ID  →  ?v=VIDEO_ID
    short_match = re.search(r"youtu\.be/([A-Za-z0-9_-]+)", url)
    if short_match:
        return f"https://www.youtube.com/watch?v={short_match.group(1)}"

    return url


def fetch_youtube(url: str) -> FetchResult:
    """Fetch YouTube video metadata via the public oEmbed endpoint.

    No API key or account is required.
    Returns title, author_name, and thumbnail_url on success.
    """
    watch_url = _normalize_youtube_url(url)
    oembed_url = f"{_YOUTUBE_OEMBED_BASE}?{urlencode({'url': watch_url, 'format': 'json'})}"
    try:
        resp = requests.get(oembed_url, headers=_HEADERS, timeout=_TIMEOUT)
        if resp.status_code == 401:
            return FetchResult(error="YouTube oEmbed: video is private or unlisted")
        if resp.status_code != 200:
            return FetchResult(error=f"YouTube oEmbed returned HTTP {resp.status_code}")

        data = resp.json()
        return FetchResult(
            title=data.get("title"),
            author=data.get("author_name"),
            thumbnail_url=data.get("thumbnail_url"),
            extra={
                "author_url": data.get("author_url"),
                "provider": "YouTube oEmbed",
            },
        )
    except Exception as exc:
        return FetchResult(error=f"YouTube fetch failed: {exc}")


# ---------------------------------------------------------------------------
# Instagram — Meta tokenless oEmbed
# ---------------------------------------------------------------------------
import instaloader

# Global Instaloader client for reuse. We use quiet mode and don't require login.
_INSTALOADER = instaloader.Instaloader(quiet=True, max_connection_attempts=1)
_INSTAGRAM_OEMBED_URL = "https://graph.facebook.com/v25.0/instagram_oembed"


def fetch_instagram(url: str) -> FetchResult:
    """Fetch Instagram post/reel metadata.

    Tries to use `instaloader` first to scrape the exact caption and hashtags.
    Since unauthenticated scraping is prone to rate limits or login walls, it
    gracefully falls back to Meta's tokenless oEmbed API.
    """
    # Extract account handle from URL path before hitting the API.
    account_from_url = _extract_instagram_handle(url)
    shortcode = _extract_instagram_shortcode(url)

    # 1. Try Instaloader first
    if shortcode:
        try:
            post = instaloader.Post.from_shortcode(_INSTALOADER.context, shortcode)
            author = post.owner_username or account_from_url
            caption = post.caption or ""
            
            return FetchResult(
                title=f"Instagram post by @{author}" if author else "Instagram post",
                description=caption,
                author=author,
                extra={
                    "account_handle": author,
                    "hashtags": post.caption_hashtags,
                    "provider": "instaloader"
                }
            )
        except Exception:
            # Instaloader blocked, rate-limited, or post not found. Fall back to oEmbed.
            pass

    # 2. Fall back to oEmbed
    try:
        resp = requests.get(
            _INSTAGRAM_OEMBED_URL,
            params={"url": url},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 400:
            # Still return what we extracted from the URL itself
            return FetchResult(
                author=account_from_url,
                error="Instagram oEmbed: content may be private or URL format unrecognised",
                extra={"account_handle": account_from_url, "provider": "Instagram oEmbed"},
            )
        if resp.status_code != 200:
            return FetchResult(
                author=account_from_url,
                error=f"Instagram oEmbed returned HTTP {resp.status_code}",
                extra={"account_handle": account_from_url},
            )

        data = resp.json()
        if "error" in data:
            err_msg = data["error"].get("message", "Unknown error")
            return FetchResult(
                author=account_from_url,
                error=f"Instagram oEmbed API error: {err_msg}",
                extra={"account_handle": account_from_url},
            )

        raw_title = data.get("title") or ""
        # Priority: handle from URL path is definitive; fall back to @mention
        # in the oEmbed title only when the URL doesn't expose the account.
        handle_in_title = _extract_at_mention(raw_title) if not account_from_url else None
        account_handle = account_from_url or handle_in_title

        return FetchResult(
            title=raw_title or None,
            author=account_handle,
            extra={
                "account_handle": account_handle,
                "html": data.get("html"),
                "provider": "Instagram oEmbed",
            },
        )
    except Exception as exc:
        return FetchResult(
            author=account_from_url,
            error=f"Instagram fetch failed: {exc}",
            extra={"account_handle": account_from_url},
        )


def _extract_instagram_handle(url: str) -> Optional[str]:
    """Pull the account handle out of an Instagram URL, if determinable."""
    m = re.search(r"instagram\.com/@?([A-Za-z0-9_.]+)/(?:p|reel|tv)/", url)
    if m:
        return m.group(1)

    m = re.search(r"instagram\.com/@?([A-Za-z0-9_.]{2,30})/?(?:\?|$)", url)
    if m and m.group(1).lower() not in ("p", "reel", "tv", "reels", "explore"):
        return m.group(1)

    return None


def _extract_instagram_shortcode(url: str) -> Optional[str]:
    """Extract the post shortcode from an Instagram URL."""
    m = re.search(r"instagram\.com/(?:[A-Za-z0-9_.]+)?/?(?:p|reel|tv|reels)/([A-Za-z0-9_-]+)", url)
    if m:
        return m.group(1)
    return None


def _extract_at_mention(text: str) -> Optional[str]:
    """Return the first @handle found in *text*, without the @ prefix."""
    m = re.search(r"@([A-Za-z0-9_.]+)", text)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Generic — HTML meta tag scraping
# ---------------------------------------------------------------------------

def fetch_generic(url: str) -> FetchResult:
    """Fetch generic page metadata from og:, twitter:, or HTML <title> tags.

    Priority order:
        Title:       og:title > twitter:title > <title>
        Description: og:description > twitter:description > meta[name=description]
        Thumbnail:   og:image > twitter:image
    """
    try:
        resp = requests.get(
            url, headers=_HEADERS, timeout=_TIMEOUT, allow_redirects=True
        )
        if resp.status_code not in (200, 301, 302):
            return FetchResult(error=f"HTTP {resp.status_code}")

        soup = BeautifulSoup(resp.text, "html.parser")

        title = (
            _get_meta(soup, "og:title")
            or _get_meta(soup, "twitter:title")
            or (soup.title.string.strip() if soup.title else None)
        )
        description = (
            _get_meta(soup, "og:description")
            or _get_meta_name(soup, "twitter:description")
            or _get_meta_name(soup, "description")
        )
        thumbnail = _get_meta(soup, "og:image") or _get_meta_name(soup, "twitter:image")

        # Collect a short body-text snippet for LLM context
        body_text = soup.get_text(separator=" ", strip=True)
        raw_snippet = re.sub(r"\s+", " ", body_text)[:500] if body_text else None

        return FetchResult(
            title=title,
            description=description,
            thumbnail_url=thumbnail,
            raw_text=raw_snippet,
            extra={"provider": "Generic HTML scrape"},
        )
    except Exception as exc:
        return FetchResult(error=f"Generic fetch failed: {exc}")


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

from ..logging import get_logger
logger = get_logger(__name__)

def fetch_for_url(url: str) -> FetchResult:
    """Route *url* to the appropriate platform fetcher.

    Detection is done via substring matching — mirrors the logic in
    ``url_utils.get_platform()``.

    Platform routing:
        youtube.com / youtu.be  →  fetch_youtube  (oEmbed, handles Shorts)
        instagram.com           →  fetch_instagram (Meta tokenless oEmbed)
        everything else         →  fetch_generic   (HTML og:/twitter: scrape)
    """
    url_lower = url.lower()

    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        platform = "youtube"
        func = fetch_youtube
    elif "instagram.com" in url_lower:
        platform = "instagram"
        func = fetch_instagram
    else:
        platform = "generic"
        func = fetch_generic

    logger.debug("Dispatching to fetcher", extra={"url": url, "platform_detected": platform})
    
    import time
    start = time.time()
    result = func(url)
    duration_ms = int((time.time() - start) * 1000)
    
    logger.debug("HTTP response received", extra={"duration_ms": duration_ms, "url": url, "has_error": bool(result.error)})
    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _get_meta(soup: BeautifulSoup, property_name: str) -> Optional[str]:
    """Return content of ``<meta property="...">``."""
    tag = soup.find("meta", attrs={"property": property_name})
    if tag and tag.get("content"):
        return str(tag["content"]).strip() or None
    return None


def _get_meta_name(soup: BeautifulSoup, name: str) -> Optional[str]:
    """Return content of ``<meta name="...">``."""
    tag = soup.find("meta", attrs={"name": name})
    if tag and tag.get("content"):
        return str(tag["content"]).strip() or None
    return None
