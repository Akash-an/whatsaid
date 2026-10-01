"""Tests for llm/fetchers.py — platform-specific metadata fetchers.

All HTTP calls are mocked so these tests run fully offline.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from whatsaid.llm.fetchers import (
    FetchResult,
    fetch_generic,
    fetch_instagram,
    fetch_youtube,
    fetch_for_url,
)


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

YOUTUBE_OEMBED_RESPONSE = {
    "title": "My Awesome Video",
    "author_name": "CoolChannel",
    "thumbnail_url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg",
    "width": 480,
    "height": 270,
}


def test_fetch_youtube_returns_title_and_author():
    """oEmbed API response should map to FetchResult fields."""
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = YOUTUBE_OEMBED_RESPONSE
        mock_get.return_value = mock_resp

        result = fetch_youtube("https://www.youtube.com/watch?v=abc123")

    assert isinstance(result, FetchResult)
    assert result.title == "My Awesome Video"
    assert result.author == "CoolChannel"
    assert result.thumbnail_url == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    assert result.raw_text is None or isinstance(result.raw_text, str)


def test_fetch_youtube_short_url():
    """youtu.be short links should also hit the oEmbed endpoint."""
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {**YOUTUBE_OEMBED_RESPONSE, "title": "Short URL Video"}
        mock_get.return_value = mock_resp

        result = fetch_youtube("https://youtu.be/abc123")

    assert result.title == "Short URL Video"
    called_url = mock_get.call_args[0][0]
    assert "oembed" in called_url


def test_fetch_youtube_shorts_rewrites_url():
    """YouTube Shorts URLs (/shorts/ID) must be rewritten to ?v=ID for oEmbed."""
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {**YOUTUBE_OEMBED_RESPONSE, "title": "Shorts Video"}
        mock_get.return_value = mock_resp

        result = fetch_youtube("https://www.youtube.com/shorts/abc123")

    assert result.title == "Shorts Video"
    # The URL passed to requests.get must NOT contain /shorts/
    called_url = mock_get.call_args[0][0]
    assert "/shorts/" not in called_url
    assert "abc123" in called_url


def test_fetch_youtube_non_200_returns_empty():
    """Non-200 status should return a FetchResult with no data rather than raising."""
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.side_effect = Exception("not json")
        mock_get.return_value = mock_resp

        result = fetch_youtube("https://www.youtube.com/watch?v=bad")

    assert result.title is None
    assert result.error is not None


# ---------------------------------------------------------------------------
# Instagram
# ---------------------------------------------------------------------------

INSTAGRAM_OEMBED_RESPONSE = {
    "title": "Sunset vibes 🌅 by @travelgram",
    "html": "<blockquote>...</blockquote>",
    "version": "1.0",
}


def test_fetch_instagram_returns_title_from_oembed():
    """Meta tokenless oEmbed returns title for public posts.
    The @handle in the title should be extracted into result.author.
    """
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = INSTAGRAM_OEMBED_RESPONSE
        mock_get.return_value = mock_resp

        result = fetch_instagram("https://www.instagram.com/p/ABC123/")

    assert result.title == "Sunset vibes 🌅 by @travelgram"
    # @travelgram extracted from oEmbed title
    assert result.author == "travelgram"
    # account_handle also stored in extra
    assert result.extra is not None
    assert result.extra.get("account_handle") == "travelgram"
    # Meta removed thumbnail from tokenless endpoint — should be None
    assert result.thumbnail_url is None
    assert result.error is None


def test_fetch_instagram_instaloader_success():
    """If instaloader succeeds, it should return full caption and hashtags without hitting oEmbed."""
    with patch("instaloader.Post.from_shortcode") as mock_from_shortcode:
        mock_post = MagicMock()
        mock_post.owner_username = "testuser"
        mock_post.caption = "Look at my cool post! #awesome"
        mock_post.caption_hashtags = ["awesome"]
        mock_from_shortcode.return_value = mock_post
        
        with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
            result = fetch_instagram("https://www.instagram.com/p/SHORTCODE/")
            
            # Should not have fallen back to oEmbed
            mock_get.assert_not_called()
            
    assert result.author == "testuser"
    assert result.description == "Look at my cool post! #awesome"
    assert result.extra["hashtags"] == ["awesome"]
    assert result.extra["provider"] == "instaloader"


def test_fetch_instagram_handle_extracted_from_profile_url():
    """Account handle should be parsed from profile-style URLs even without oEmbed title."""
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"title": "Some post with no @mention"}
        mock_get.return_value = mock_resp

        result = fetch_instagram("https://www.instagram.com/freediving_srilanka?igsi=abc")

    assert result.author == "freediving_srilanka"
    assert result.extra.get("account_handle") == "freediving_srilanka"


def test_fetch_instagram_api_error_in_json():
    """Instagram oEmbed returns 200 with error JSON for private/bad URLs."""
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "error": {"message": "Invalid parameter", "code": 100}
        }
        mock_get.return_value = mock_resp

        result = fetch_instagram("https://www.instagram.com/p/PRIVATE/")

    assert result.error is not None
    assert result.title is None


def test_fetch_instagram_blocked_returns_error():
    """Non-200 status should return FetchResult with error but still carry any handle."""
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {}
        mock_get.return_value = mock_resp

        result = fetch_instagram("https://www.instagram.com/p/BLOCKED/")

    assert result.error is not None


def test_extract_instagram_handle_from_profile_url():
    """_extract_instagram_handle should parse standalone profile URLs."""
    from whatsaid.llm.fetchers import _extract_instagram_handle
    assert _extract_instagram_handle("https://www.instagram.com/freediving_srilanka?igsi=x") == "freediving_srilanka"
    assert _extract_instagram_handle("https://www.instagram.com/@myaccount") == "myaccount"


def test_extract_instagram_handle_none_for_shortcode_only():
    """Reel shortcode-only URLs don't contain the account handle."""
    from whatsaid.llm.fetchers import _extract_instagram_handle
    assert _extract_instagram_handle("https://www.instagram.com/reel/DcxMQ6ez1g_/") is None


def test_extract_at_mention_returns_first_handle():
    """_extract_at_mention should find first @handle in a string."""
    from whatsaid.llm.fetchers import _extract_at_mention
    assert _extract_at_mention("See this post by @rajesh_m0111: some caption") == "rajesh_m0111"
    assert _extract_at_mention("no mention here") is None


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

GENERIC_HTML = """
<html>
<head>
  <title>Amazing Article - My Blog</title>
  <meta property="og:title" content="Amazing Article" />
  <meta property="og:description" content="This is a great read about Python." />
  <meta name="twitter:title" content="Amazing Article (Twitter)" />
</head>
<body><p>Body text here.</p></body>
</html>
"""


def test_fetch_generic_prefers_og_title():
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = GENERIC_HTML
        mock_get.return_value = mock_resp

        result = fetch_generic("https://myblog.com/amazing-article")

    assert result.title == "Amazing Article"
    assert "Python" in result.description


def test_fetch_generic_falls_back_to_html_title():
    html_no_og = "<html><head><title>Fallback Title</title></head><body></body></html>"
    with patch("whatsaid.llm.fetchers.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html_no_og
        mock_get.return_value = mock_resp

        result = fetch_generic("https://example.com/page")

    assert result.title == "Fallback Title"


def test_fetch_generic_request_exception():
    with patch("whatsaid.llm.fetchers.requests.get", side_effect=Exception("timeout")):
        result = fetch_generic("https://unreachable.example.com/")

    assert result.error is not None
    assert result.title is None


# ---------------------------------------------------------------------------
# fetch_for_url dispatcher
# ---------------------------------------------------------------------------

def test_fetch_for_url_routes_youtube():
    with patch("whatsaid.llm.fetchers.fetch_youtube") as mock_yt:
        mock_yt.return_value = FetchResult(title="YT Video")
        result = fetch_for_url("https://www.youtube.com/watch?v=abc")

    mock_yt.assert_called_once()
    assert result.title == "YT Video"


def test_fetch_for_url_routes_instagram():
    with patch("whatsaid.llm.fetchers.fetch_instagram") as mock_ig:
        mock_ig.return_value = FetchResult(title="IG Post")
        result = fetch_for_url("https://www.instagram.com/p/XYZ/")

    mock_ig.assert_called_once()
    assert result.title == "IG Post"


def test_fetch_for_url_routes_generic_for_unknown():
    with patch("whatsaid.llm.fetchers.fetch_generic") as mock_gen:
        mock_gen.return_value = FetchResult(title="Some Article")
        result = fetch_for_url("https://somewebsite.com/article")

    mock_gen.assert_called_once()
    assert result.title == "Some Article"
