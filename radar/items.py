"""One news item, plus the small pure helpers around it."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

WINDOW = timedelta(days=7)
TRACKING = ("utm_", "fbclid", "gclid", "mc_", "ref_src")


@dataclass(frozen=True)
class Item:
    source_id: str
    source_name: str
    trust: str
    title: str
    url: str
    published: datetime
    summary: str
    score: int | None = None


def normalize_url(url: str) -> str:
    """Same page, same key: no tracking params, no fragment, no trailing slash.

    >>> normalize_url("https://Example.com/a/?utm_source=x&id=7#top")
    'https://example.com/a?id=7'
    """
    p = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.startswith(TRACKING)]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), urlencode(query), ""))


def in_window(item: Item, now: datetime, window: timedelta = WINDOW) -> bool:
    return now - window <= item.published <= now


def dedupe(items: list[Item]) -> list[Item]:
    seen: set[str] = set()
    out = []
    for i in items:
        key = normalize_url(i.url)
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out
