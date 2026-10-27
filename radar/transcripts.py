"""Optional: full podcast transcripts from your own Postgres, read-only.

If you already transcribe podcasts somewhere, point RADAR_TRANSCRIPTS_DB_URL
at that database and RADAR_TRANSCRIPTS_TABLE at a table (or view) with:
audio_url, episode_title, transcript. Episodes are matched by their audio
URL, then by title. Use a login that can only SELECT those columns, in a
read-only session. Not set, or the DB is down → the email still goes out
with the episode's show notes, and says the transcripts were missing.
"""

import re
from collections.abc import Callable

import psycopg

from radar.items import Item, normalize_url

CONNECT_TIMEOUT = 10
DEFAULT_TABLE = "podcast_transcripts"
TABLE_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?")
SQL = """
SELECT audio_url, episode_title, transcript
FROM {table}
WHERE audio_url = ANY(%s) OR episode_title = ANY(%s)
"""


class TranscriptError(RuntimeError):
    """The transcripts DB could not be read (never carries the URL or password)."""


def load_transcripts(
    db_url: str | None,
    items: list[Item],
    table: str | None = None,
    connect: Callable = psycopg.connect,
) -> dict[str, str]:
    """{episode item url: full transcript} for the podcast items already transcribed."""
    pods = [i for i in items if i.trust == "opinion"]
    if not db_url or not pods:
        return {}
    table = table or DEFAULT_TABLE
    if not TABLE_RE.fullmatch(table):  # an identifier can't be a query parameter
        raise TranscriptError("bad table name in RADAR_TRANSCRIPTS_TABLE")
    by_url = {normalize_url(i.url): i.url for i in pods}
    by_title = {i.title.strip(): i.url for i in pods}
    try:
        with connect(db_url, connect_timeout=CONNECT_TIMEOUT) as conn:
            rows = conn.execute(SQL.format(table=table), ([i.url for i in pods], list(by_title))).fetchall()
    except (psycopg.Error, OSError):
        raise TranscriptError("transcripts DB unreachable") from None
    found: dict[str, str] = {}
    for audio_url, title, text in rows:
        key = by_url.get(normalize_url(audio_url or "")) or by_title.get((title or "").strip())
        if key and text:
            found.setdefault(key, text)
    return found
