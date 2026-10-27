"""The weekly run: collect → drop what earlier emails showed → rank → email the reader.

    python3 -m radar.main --dry-run   # prints the email; sends nothing, remembers nothing
    python3 -m radar.main             # the real weekly run (cron / systemd timer)

Podcast episodes you already transcribed (optional DB) are swapped for their
biggest claims (each with a checked quote), so the email can check them.

Items are remembered only after the email really went out, so a failed
send is retried with the same items next time.
"""

import argparse
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from radar import seen as seen_store
from radar.claims import expand_podcasts
from radar.collect import Collected, collect
from radar.config import load_sources
from radar.items import Item
from radar.llm import call_openrouter
from radar.mail import MailError, render, send
from radar.rank import rank
from radar.transcripts import TranscriptError, load_transcripts

ROOT = Path(__file__).resolve().parent.parent
PROFILE = Path(__file__).parent / "profile.md"


def run(  # noqa: PLR0913 — every outside effect is passed in (the test seam)
    now: datetime,
    seen_path: Path,
    profile: str,
    collect: Callable[[datetime], Collected],
    transcripts: Callable[[list[Item]], dict[str, str]],
    call: Callable[[list[dict], dict], str],
    send: Callable[[str, str], None],
    dry: bool = False,
) -> int:
    seen = seen_store.load(seen_path)
    collected = collect(now)
    items = seen_store.only_new(collected.items, seen)
    failures = dict(collected.failures)
    try:
        found = transcripts(items)
    except TranscriptError as err:
        found = {}
        failures["Podcast transcripts"] = str(err)
    digest = rank(expand_podcasts(items, found, call), profile, call)
    subject, body = render(digest, now, items_read=len(items), failures=failures)
    if dry:
        print(f"Subject: {subject}\n\n{body}")
        return 0
    try:
        send(subject, body)
    except MailError as err:
        print(err, file=sys.stderr)
        return 1
    seen_store.save(seen_path, seen_store.remember(seen, items, now.date()))
    print(f"sent: {subject}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m radar.main", description="Weekly AI Radar email.")
    parser.add_argument("--dry-run", action="store_true", help="print the email, send nothing")
    args = parser.parse_args(argv)
    env = os.environ
    state = Path(env.get("RADAR_STATE_DIR") or ROOT / "state")
    state.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    return run(
        now=datetime.now(UTC),
        seen_path=state / "seen.json",
        profile=PROFILE.read_text(),
        collect=lambda now: collect(sources, now),
        transcripts=lambda items: load_transcripts(
            env.get("RADAR_TRANSCRIPTS_DB_URL"), items, table=env.get("RADAR_TRANSCRIPTS_TABLE")
        ),
        call=lambda msgs, schema: call_openrouter(msgs, schema, env),
        send=lambda subject, body: send(subject, body, env),
        dry=args.dry_run,
    )


if __name__ == "__main__":
    sys.exit(main())
