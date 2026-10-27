from datetime import UTC, datetime

import psycopg
import pytest

from radar.items import Item
from radar.transcripts import TranscriptError, load_transcripts

T = datetime(2026, 10, 26, tzinfo=UTC)
POD = Item("moonshots", "Moonshots", "opinion", "Chamath: AGI Is Here", "https://pod.example/ep1.mp3", T, "")
POD2 = Item("moonshots", "Moonshots", "opinion", "Robot Brains", "https://pod.example/ep2.mp3", T, "")
NEWS = Item("openai", "OpenAI", "primary", "GPT ships", "https://openai.com/x", T, "")


class FakeConn:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))
        return self

    def fetchall(self):
        return self.rows


def connector(rows):
    conn = FakeConn(rows)

    def connect(url, **kw):
        connect.kw = kw
        return conn

    connect.conn = conn
    return connect


def test_matches_by_audio_url_then_by_title():
    rows = [("https://pod.example/ep1.mp3", "other title", "full text 1"), ("x", "Robot Brains", "text 2")]
    got = load_transcripts("postgresql://u@h/db", [POD, POD2, NEWS], connect=connector(rows))
    assert got == {POD.url: "full text 1", POD2.url: "text 2"}


def test_query_is_parameterized_and_asks_only_for_podcasts():
    c = connector([])
    load_transcripts("postgresql://u@h/db", [POD, NEWS], connect=c)
    ((sql, params),) = c.conn.calls
    assert "%s" in sql and POD.url not in sql  # values never pasted into SQL
    assert [POD.url] in params and NEWS.url not in str(params)
    assert c.kw["connect_timeout"] <= 10


def test_no_podcasts_or_no_url_means_no_db_call():
    def boom(*a, **k):
        pytest.fail("should not connect")

    assert load_transcripts("postgresql://u@h/db", [NEWS], connect=boom) == {}
    assert load_transcripts(None, [POD], connect=boom) == {}


def test_db_errors_are_short_and_hide_the_url():
    def down(url, **kw):
        raise psycopg.OperationalError(f"connection to {url} failed")

    with pytest.raises(TranscriptError) as err:
        load_transcripts("postgresql://reader:SECRET@h/db", [POD], connect=down)
    assert "SECRET" not in str(err.value)


def test_table_name_is_a_setting_and_strictly_checked():
    c = connector([])
    load_transcripts("postgresql://u@h/db", [POD], table="my_schema.pod_texts", connect=c)
    ((sql, _),) = c.conn.calls
    assert "FROM my_schema.pod_texts" in sql
    with pytest.raises(TranscriptError, match="table name"):
        load_transcripts("postgresql://u@h/db", [POD], table="x; DROP TABLE y", connect=c)


def test_default_table_name():
    c = connector([])
    load_transcripts("postgresql://u@h/db", [POD], connect=c)
    assert "FROM podcast_transcripts" in c.conn.calls[0][0]
