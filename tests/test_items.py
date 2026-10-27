from datetime import UTC, datetime, timedelta

from radar.items import Item, dedupe, in_window, normalize_url

NOW = datetime(2026, 11, 1, 23, 0, tzinfo=UTC)


def item(url: str, days_ago: float = 1, title: str = "t") -> Item:
    return Item(
        source_id="s",
        source_name="S",
        trust="builder",
        title=title,
        url=url,
        published=NOW - timedelta(days=days_ago),
        summary="",
    )


def test_normalize_drops_tracking_fragment_and_trailing_slash():
    assert (
        normalize_url("HTTPS://Example.com/a/?utm_source=x&id=7&fbclid=1#top") == "https://example.com/a?id=7"
    )
    assert normalize_url("https://example.com/") == "https://example.com"


def test_window_is_the_last_7_days():
    assert in_window(item("https://a", 6.9), NOW)
    assert not in_window(item("https://a", 7.1), NOW)
    assert not in_window(item("https://a", -1), NOW)  # future dates are bogus


def test_dedupe_keeps_first_of_same_normalized_url():
    a = item("https://example.com/x?utm_medium=rss", title="first")
    b = item("https://example.com/x/", title="second")
    assert [i.title for i in dedupe([a, b])] == ["first"]
