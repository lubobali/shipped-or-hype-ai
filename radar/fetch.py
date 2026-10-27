"""Download one source. HTTPS only, size-capped, short timeout."""

import urllib.request

MAX_BYTES = 5_000_000
TIMEOUT = 20
USER_AGENT = "shipped-or-hype-ai/0.1 (+https://github.com/lubobali/shipped-or-hype-ai; weekly reader)"


class FetchError(RuntimeError):
    """The source could not be read this week (the email says so)."""


def fetch(url: str, opener=urllib.request.urlopen) -> bytes:
    if not url.startswith("https://"):
        raise FetchError("not https")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            if not resp.geturl().startswith("https://"):
                raise FetchError("redirected off https")
            data = resp.read(MAX_BYTES + 1)
    except FetchError:
        raise
    except Exception as err:  # network, TLS, HTTP status: one short reason
        raise FetchError(type(err).__name__) from None
    if len(data) > MAX_BYTES:
        raise FetchError("too big")
    return data
