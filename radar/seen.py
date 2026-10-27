"""Remember what earlier emails already showed, so it never comes back."""

import json
import os
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from radar.items import Item, normalize_url

KEEP = timedelta(days=60)


def load(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def only_new(items: Iterable[Item], seen: dict[str, str]) -> list[Item]:
    return [i for i in items if normalize_url(i.url) not in seen]


def remember(seen: dict[str, str], items: Iterable[Item], today: date) -> dict[str, str]:
    cutoff = (today - KEEP).isoformat()
    kept = {url: day for url, day in seen.items() if day >= cutoff}
    for i in items:
        kept.setdefault(normalize_url(i.url), today.isoformat())
    return kept


def save(path: Path, seen: dict[str, str]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(seen, indent=1, sort_keys=True))
    os.replace(tmp, path)  # atomic: a crash never leaves half a file
