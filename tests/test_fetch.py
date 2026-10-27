import io

import pytest

from radar.fetch import MAX_BYTES, FetchError, fetch


class Resp(io.BytesIO):
    def __init__(self, data: bytes, url: str = "https://example.com/feed"):
        super().__init__(data)
        self._url = url

    def geturl(self) -> str:
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_for(data: bytes, final_url: str = "https://example.com/feed"):
    seen = {}

    def opener(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        seen["timeout"] = timeout
        return Resp(data, final_url)

    return opener, seen


def test_fetch_returns_bytes_with_our_user_agent_and_timeout():
    opener, seen = opener_for(b"<rss/>")
    assert fetch("https://example.com/feed", opener=opener) == b"<rss/>"
    assert "shipped-or-hype-ai" in seen["ua"]
    assert seen["timeout"] == 20


def test_fetch_refuses_plain_http_and_http_redirects():
    opener, _ = opener_for(b"x")
    with pytest.raises(FetchError):
        fetch("http://example.com/feed", opener=opener)
    opener, _ = opener_for(b"x", final_url="http://evil.example/feed")
    with pytest.raises(FetchError):
        fetch("https://example.com/feed", opener=opener)


def test_fetch_refuses_huge_bodies():
    opener, _ = opener_for(b"x" * (MAX_BYTES + 1))
    with pytest.raises(FetchError):
        fetch("https://example.com/feed", opener=opener)
