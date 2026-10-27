from datetime import UTC, datetime

from radar import main as radar_main
from radar.collect import Collected
from radar.items import Item
from radar.mail import MailError
from radar.seen import load, save
from radar.transcripts import TranscriptError

NOW = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)
OLD = Item("s", "S", "primary", "Old", "https://example.com/old", NOW, "s")
NEW = Item("s", "S", "primary", "New", "https://example.com/new", NOW, "s")
POD = Item("m", "Moonshots", "opinion", "Episode 1", "https://pod.example/1.mp3", NOW, "notes")


def no_transcripts(items):
    return {}


def run(tmp_path, dry=False, send_fails=False, items=(OLD, NEW), transcripts=no_transcripts):
    seen_path = tmp_path / "seen.json"
    save(seen_path, {"https://example.com/old": "2026-10-19"})
    calls = {"llm": [], "sent": []}

    def call(msgs, schema):
        if "claims" in schema["properties"]:
            return '{"claims": [{"claim": "AGI is here.", "quote": "agi is already here"}]}'
        calls["llm"].append(msgs[1]["content"])
        return '{"shipped": [{"id": 1, "line": "x"}], "ideas": [], "checks": [], "model_moves": []}'

    def send(subject, body):
        if send_fails:
            raise MailError("alert email failed: SMTPException")
        calls["sent"].append((subject, body))

    code = radar_main.run(
        now=NOW,
        seen_path=seen_path,
        profile="p",
        collect=lambda now: Collected(items=list(items)),
        transcripts=transcripts,
        call=call,
        send=send,
        dry=dry,
    )
    return code, calls, load(seen_path)


def test_real_run_sends_new_items_then_remembers_them(tmp_path):
    code, calls, seen = run(tmp_path)
    assert code == 0
    assert "New" in calls["llm"][0] and "Old" not in calls["llm"][0]  # last week's item never comes back
    ((_, body),) = calls["sent"]
    assert NEW.url in body
    assert "https://example.com/new" in seen


def test_dry_run_prints_but_never_sends_or_remembers(tmp_path, capsys):
    code, calls, seen = run(tmp_path, dry=True)
    assert code == 0 and calls["sent"] == []
    assert "https://example.com/new" not in seen
    assert NEW.url in capsys.readouterr().out


def test_failed_send_keeps_items_for_the_next_try(tmp_path):
    code, _, seen = run(tmp_path, send_fails=True)
    assert code == 1
    assert "https://example.com/new" not in seen


def test_profile_file_exists_and_has_the_core_stack():
    text = radar_main.PROFILE.read_text()
    for word in ("RAG", "MCP", "agents", "Python"):
        assert word in text


def test_a_transcribed_podcast_reaches_the_ranking_as_its_claims(tmp_path):
    _, calls, _ = run(
        tmp_path, items=(NEW, POD), transcripts=lambda items: {POD.url: "I think AGI is already here."}
    )
    prompt = calls["llm"][0]
    assert "AGI is here." in prompt and 'Quote: "agi is already here"' in prompt
    assert "Episode 1" not in prompt


def test_transcripts_down_still_sends_and_says_so(tmp_path):
    def down(items):
        raise TranscriptError("transcripts DB unreachable")

    code, calls, _ = run(tmp_path, items=(NEW, POD), transcripts=down)
    ((_, body),) = calls["sent"]
    assert code == 0 and "Episode 1" in calls["llm"][0]
    assert "Podcast transcripts (transcripts DB unreachable)" in body
