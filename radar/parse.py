"""Bytes from a source → Items. Feeds are untrusted input: XML goes through
defusedxml (no entity bombs, no external entities), text is stripped to
plain words, and only http(s) links survive."""

import json
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from radar.config import Source
from radar.items import Item

ATOM = "{http://www.w3.org/2005/Atom}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
SUMMARY_LIMIT = 500
# Hacker News is not only about AI: keep stories whose title says so.
AI_WORDS = re.compile(
    r"\b(ai|llms?|gpt\S*|claude|anthropic|openai|gemini|deepseek|qwen|llama|mistral|"
    r"agents?|agentic|rag|mcp|inference|transformers?|embeddings?|fine-?tun\w*|"
    r"models?|nvidia|copilot|prompt\w*)\b",
    re.IGNORECASE,
)


class ParseError(ValueError):
    """The source answered, but not with something we can read."""


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def clean_text(html: str, limit: int = SUMMARY_LIMIT) -> str:
    """HTML → one line of plain text, cut at `limit` with an ellipsis.

    >>> clean_text("<p>Hi <b>there</b></p><script>x()</script>")
    'Hi there'
    """
    p = _Text()
    p.feed(html or "")
    text = " ".join(" ".join(p.parts).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _http(url: str | None) -> str | None:
    url = (url or "").strip()
    return url if url.startswith(("https://", "http://")) else None


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    return (d if d.tzinfo else d.replace(tzinfo=UTC)).astimezone(UTC)


def _item(src: Source, title, url, published, summary, score=None) -> Item | None:  # noqa: PLR0913 — one row of fields
    url, title = _http(url), clean_text(title or "", 300)
    if not (url and title and published):
        return None
    return Item(src.id, src.name, src.trust, title, url, published, clean_text(summary or ""), score)


def _text(el, tag: str) -> str | None:
    found = el.find(tag)
    return found.text if found is not None else None


def _rss_link(it) -> str | None:
    """<link>, else a permalink <guid>, else the audio file (podcasts often have no <link>)."""
    guid = it.find("guid")
    enclosure = it.find("enclosure")
    return (
        _text(it, "link")
        or (guid.text if guid is not None and guid.get("isPermaLink", "true") == "true" else None)
        or (enclosure.get("url") if enclosure is not None else None)
    )


def _feed(data: bytes, src: Source) -> list[Item]:
    try:
        root = ElementTree.fromstring(data)
    except (ElementTree.ParseError, DefusedXmlException) as err:
        raise ParseError(type(err).__name__) from None
    out = []
    for it in root.iter("item"):  # RSS 2.0
        summary = _text(it, CONTENT) or _text(it, "description")
        out.append(_item(src, _text(it, "title"), _rss_link(it), _date(_text(it, "pubDate")), summary))
    for e in root.iter(f"{ATOM}entry"):  # Atom
        links = e.findall(f"{ATOM}link")
        link = next((x.get("href") for x in links if x.get("rel", "alternate") == "alternate"), None)
        when = _date(_text(e, f"{ATOM}published") or _text(e, f"{ATOM}updated"))
        summary = _text(e, f"{ATOM}summary") or _text(e, f"{ATOM}content")
        out.append(_item(src, _text(e, f"{ATOM}title"), link, when, summary))
    return [i for i in out if i]


def _json(data: bytes):
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as err:
        raise ParseError(type(err).__name__) from None


def _hf(data: bytes, src: Source) -> list[Item]:
    out = []
    for row in _json(data):
        paper = row.get("paper") or {}
        score = int(paper.get("upvotes") or 0)
        if score < src.min_score or not paper.get("id"):
            continue
        url = f"https://huggingface.co/papers/{paper['id']}"
        out.append(
            _item(src, paper.get("title"), url, _date(row.get("publishedAt")), paper.get("summary"), score)
        )
    return [i for i in out if i]


def _hn(data: bytes, src: Source) -> list[Item]:
    out = []
    for hit in _json(data).get("hits", []):
        score, title = int(hit.get("points") or 0), hit.get("title") or ""
        if score < src.min_score or not AI_WORDS.search(title):
            continue
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        out.append(_item(src, title, url, _date(hit.get("created_at")), "", score))
    return [i for i in out if i]


PARSERS = {"feed": _feed, "hf_papers": _hf, "hn": _hn}


def parse(data: bytes, src: Source) -> list[Item]:
    return PARSERS[src.format](data, src)
