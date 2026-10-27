"""Sources: which feeds the Radar reads, from `radar/sources.yaml`."""

from dataclasses import dataclass
from pathlib import Path

import yaml

SOURCES = Path(__file__).with_name("sources.yaml")
FORMATS = ("feed", "hf_papers", "hn")
TRUST = ("primary", "builder", "research", "opinion")


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    format: str
    trust: str
    max_items: int = 15
    min_score: int = 0


def load_sources(path: Path = SOURCES) -> list[Source]:
    raw = yaml.safe_load(path.read_text())["sources"]
    sources = [Source(**s) for s in raw]
    for s in sources:
        if s.format not in FORMATS:
            raise ValueError(f"{s.id}: unknown format {s.format!r}")
        if s.trust not in TRUST:
            raise ValueError(f"{s.id}: unknown trust {s.trust!r}")
        if not s.url.startswith("https://"):
            raise ValueError(f"{s.id}: url must be https")
    return sources
