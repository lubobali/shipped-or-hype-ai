"""Read every source for the last 7 days. One broken source never stops the rest.

Dry run (prints counts, writes nothing): `python3 -m radar.collect`
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlencode

from radar.config import Source, load_sources
from radar.fetch import FetchError, fetch
from radar.items import WINDOW, Item, dedupe, in_window
from radar.parse import ParseError, parse


@dataclass
class Collected:
    items: list[Item] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)  # source name → short reason


def _iso_week(d: datetime) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def source_url(src: Source, now: datetime) -> list[str]:
    """The real URL(s) to read this week (some APIs take the week as a parameter)."""
    if src.format == "hf_papers":  # the last 7 days can span two ISO weeks
        return [f"{src.url}?week={_iso_week(now)}", f"{src.url}?week={_iso_week(now - WINDOW)}"]
    if src.format == "hn":
        since = int((now - WINDOW).timestamp())
        query = {
            "tags": "story",
            "numericFilters": f"created_at_i>{since},points>={src.min_score}",
            "hitsPerPage": 100,
        }
        return [f"{src.url}?{urlencode(query)}"]
    return [src.url]


def collect(sources: list[Source], now: datetime, fetch: Callable[[str], bytes] = fetch) -> Collected:
    result = Collected()
    for src in sources:
        try:
            found = [i for url in source_url(src, now) for i in parse(fetch(url), src)]
        except (FetchError, ParseError) as err:
            result.failures[src.name] = str(err) or type(err).__name__
            continue
        fresh = sorted((i for i in found if in_window(i, now)), key=lambda i: i.published, reverse=True)
        result.items.extend(dedupe(fresh)[: src.max_items])
    result.items = dedupe(result.items)
    return result


def main() -> None:
    now = datetime.now(UTC)
    result = collect(load_sources(), now)
    by_source: dict[str, int] = {}
    for i in result.items:
        by_source[i.source_name] = by_source.get(i.source_name, 0) + 1
    print(f"week ending {now:%Y-%m-%d}: {len(result.items)} items")
    for name, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"  {n:3d}  {name}")
    for name, why in result.failures.items():
        print(f"  FAIL {name}: {why}")


if __name__ == "__main__":
    main()
