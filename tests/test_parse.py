from datetime import UTC, datetime
from pathlib import Path

import pytest

from radar.config import Source
from radar.parse import ParseError, clean_text, parse

FIX = Path(__file__).parent / "fixtures"


def src(fmt: str = "feed", **kw) -> Source:
    return Source(id="s", name="Sample", url="https://example.com/feed", format=fmt, trust="builder", **kw)


def test_rss_items_have_title_url_date_and_plain_summary():
    items = parse((FIX / "rss.xml").read_bytes(), src())
    first = items[0]
    assert first.title == "New model ships with 1M context"
    assert first.url == "https://example.com/post-1?utm_source=rss&id=7"
    assert first.published == datetime(2026, 10, 26, 14, tzinfo=UTC)
    # content:encoded wins over description; tags and <script> are gone.
    assert first.summary == "Full text with a link ."
    assert first.source_name == "Sample"
    assert first.trust == "builder"


def test_rss_drops_non_http_links_and_undated_items():
    titles = [i.title for i in parse((FIX / "rss.xml").read_bytes(), src())]
    assert "Bad link item" not in titles
    assert "No date item" not in titles
    assert titles == ["New model ships with 1M context", "Old news"]


def test_atom_uses_alternate_link_and_published_date():
    items = parse((FIX / "atom.xml").read_bytes(), src())
    assert [i.url for i in items] == [
        "https://example.org/2026/Oct/25/agent-sdk/",
        "https://example.org/releases/v2.1.0",
    ]
    assert items[0].published == datetime(2026, 10, 25, 18, 30, tzinfo=UTC)
    assert items[1].published == datetime(2026, 10, 24, 8, tzinfo=UTC)  # only <updated>
    assert items[0].summary == "I tested it on a real repo."
    assert items[1].summary == "Faster tools"


def test_hf_papers_link_to_the_paper_page_and_keep_upvotes_over_the_floor():
    items = parse((FIX / "hf_papers.json").read_bytes(), src("hf_papers", min_score=50))
    assert len(items) == 1
    assert items[0].url == "https://huggingface.co/papers/2610.11111"
    assert items[0].score == 180


def test_hn_keeps_only_ai_stories_over_the_points_floor():
    items = parse((FIX / "hn.json").read_bytes(), src("hn", min_score=300))
    assert [i.title for i in items] == [
        "DeepInfer: inference framework for DeepSeek models",
        "Ask HN: Show me your LLM agent setup",
    ]
    # No url on Ask HN -> the discussion page.
    assert items[1].url == "https://news.ycombinator.com/item?id=50200000"
    assert items[0].score == 2351


def test_xml_bombs_and_garbage_raise_parse_error():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><rss>&b;</rss>'
    with pytest.raises(ParseError):
        parse(bomb, src())
    with pytest.raises(ParseError):
        parse(b"not xml at all", src())
    with pytest.raises(ParseError):
        parse(b"{broken json", src("hn", min_score=1))


def test_summary_is_capped():
    long = "<p>" + "word " * 400 + "</p>"
    out = clean_text(long, limit=100)
    assert len(out) <= 100
    assert out.endswith("…")


def test_podcast_items_without_link_fall_back_to_permalink_guid_then_audio():
    items = parse((FIX / "podcast.xml").read_bytes(), src())
    assert [i.url for i in items] == ["https://cdn.example.com/ep2.mp3", "https://show.example.com/ep1"]
    assert items[0].summary == "Show notes."
