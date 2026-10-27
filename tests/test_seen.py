import json
from datetime import UTC, date, datetime

from radar.items import Item
from radar.seen import load, only_new, remember, save


def item(url: str) -> Item:
    return Item(
        source_id="s",
        source_name="S",
        trust="builder",
        title="t",
        url=url,
        published=datetime(2026, 10, 30, tzinfo=UTC),
        summary="",
    )


def test_items_sent_last_week_do_not_come_back(tmp_path):
    seen = remember({}, [item("https://a.com/x?utm_source=1")], date(2026, 10, 25))
    fresh = only_new([item("https://a.com/x"), item("https://b.com/y")], seen)
    assert [i.url for i in fresh] == ["https://b.com/y"]


def test_old_entries_are_pruned_after_60_days():
    seen = {"https://old.com": "2026-08-01", "https://new.com": "2026-10-20"}
    kept = remember(seen, [], date(2026, 11, 1))
    assert kept == {"https://new.com": "2026-10-20"}


def test_load_missing_or_broken_file_is_empty_and_save_round_trips(tmp_path):
    p = tmp_path / "seen.json"
    assert load(p) == {}
    p.write_text("{broken")
    assert load(p) == {}
    save(p, {"https://a.com": "2026-10-25"})
    assert json.loads(p.read_text()) == {"https://a.com": "2026-10-25"}
    assert load(p) == {"https://a.com": "2026-10-25"}
