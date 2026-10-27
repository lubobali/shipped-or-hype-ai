from datetime import UTC, datetime
from pathlib import Path

from radar.collect import collect, source_url
from radar.config import Source, load_sources
from radar.fetch import FetchError

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 27, 23, 0, tzinfo=UTC)


def test_real_sources_file_is_valid_and_has_every_trust_kind():
    sources = load_sources()
    assert {s.trust for s in sources} == {"primary", "builder", "research", "opinion"}
    assert all(s.url.startswith("https://") for s in sources)
    assert len({s.id for s in sources}) == len(sources)


def test_week_based_urls():
    hf = Source(
        id="hf",
        name="HF",
        url="https://huggingface.co/api/daily_papers",
        format="hf_papers",
        trust="research",
        min_score=50,
    )
    assert source_url(hf, NOW) == [
        "https://huggingface.co/api/daily_papers?week=2026-W44",
        "https://huggingface.co/api/daily_papers?week=2026-W43",
    ]
    hn = Source(
        id="hn",
        name="HN",
        url="https://hn.algolia.com/api/v1/search",
        format="hn",
        trust="builder",
        min_score=300,
    )
    (url,) = source_url(hn, NOW)  # since = NOW - 7 days = 2026-10-20 23:00 UTC
    assert "numericFilters=created_at_i%3E1792537200%2Cpoints%3E%3D300" in url
    assert "tags=story" in url


def test_one_broken_source_never_stops_the_others():
    good = Source(id="good", name="Good", url="https://good.example/feed", format="feed", trust="builder")
    bad = Source(id="bad", name="Bad", url="https://bad.example/feed", format="feed", trust="primary")

    def fake_fetch(url: str) -> bytes:
        if "bad" in url:
            raise FetchError("timed out")
        return (FIX / "rss.xml").read_bytes()

    result = collect([bad, good], NOW, fetch=fake_fetch)
    assert [i.title for i in result.items] == ["New model ships with 1M context"]  # old one is out of window
    assert result.failures == {"Bad": "timed out"}


def test_items_are_newest_first_and_capped_per_source():
    s = Source(id="a", name="A", url="https://a.example/feed", format="feed", trust="builder", max_items=1)
    result = collect([s], NOW, fetch=lambda url: (FIX / "atom.xml").read_bytes())
    assert [i.title for i in result.items] == ["Trying the new agent SDK"]
