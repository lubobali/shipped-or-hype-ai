import smtplib
from datetime import UTC, datetime

import pytest

from radar.items import Item
from radar.mail import MailError, render, send
from radar.rank import Check, Digest, Idea, Line

NOW = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)


def item(n: int, trust: str = "primary") -> Item:
    return Item(f"s{n}", f"Source {n}", trust, f"Title {n}", f"https://example.com/{n}", NOW, "s")


A, B, POD = item(1), item(2, "builder"), item(3, "opinion")
CLAIM = Item(
    "m", "Moonshots", "opinion", "AGI is here.", "https://pod.example/1.mp3", NOW, 'Quote: "AGI is here"'
)

FULL = Digest(
    shipped=[Line(A, "Thing 1 is out.")],
    ideas=[Idea("Tiny agent", "Build a small agent.", "Thing 1", 1.5, "agents", [A, B])],
    checks=[Check(POD, "Nothing shipped backs it.", [], stance="unverified")],
    model_moves=[Line(B, "Cheaper model.")],
)


def test_every_part_is_there_with_its_links():
    subject, body = render(FULL, NOW, items_read=79, failures={})
    assert "week 44" in subject.lower()
    for part in ("SHIPPED", "BUILD IDEAS", "PODCAST CLAIMS", "MODEL MOVES"):
        assert part in body
    for url in (A.url, B.url, POD.url):
        assert url in body
    assert "1.5 days" in body and "agents" in body
    assert "UNVERIFIED" in body
    assert "79 items" in body


@pytest.mark.parametrize(
    ("stance", "label"),
    [
        ("backs", "BACKED BY A SOURCE"),
        ("partly", "PARTLY BACKED"),
        ("contradicts", "SOURCES SAY OTHERWISE"),
    ],
)
def test_check_label_and_evidence(stance, label):
    d = Digest(checks=[Check(POD, "v", [A], stance=stance)])
    _, body = render(d, NOW, items_read=1, failures={})
    assert label in body and "UNVERIFIED" not in body and A.url in body


def test_a_transcript_claim_shows_its_quote():
    _, body = render(Digest(checks=[Check(CLAIM, "v", [], "unverified")]), NOW, items_read=1, failures={})
    assert '"AGI is here." (Moonshots)' in body and 'Quote: "AGI is here"' in body


def test_degraded_week_says_why_at_the_top():
    d = Digest(shipped=[Line(A, A.title)], degraded="links only: cost cap reached")
    subject, body = render(d, NOW, items_read=5, failures={})
    assert "links only" in subject
    assert body.splitlines()[2].startswith("Links only this week: cost cap reached")


def test_broken_sources_are_listed():
    _, body = render(FULL, NOW, items_read=3, failures={"Bad Feed": "timed out"})
    assert "Bad Feed (timed out)" in body


def test_empty_week_still_renders():
    subject, body = render(Digest(), NOW, items_read=0, failures={})
    assert "nothing new" in body.lower() and subject


ENV = {
    "SMTP_HOST": "smtp.example",
    "SMTP_USER": "u@example",
    "SMTP_PASSWORD": "PW-SECRET",
    "RADAR_EMAIL_TO": "me@example",
}


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port, timeout):
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, user, pw):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_send_goes_only_to_the_reader():
    FakeSMTP.sent = []
    send("Subj", "Body", ENV, smtp=FakeSMTP, smtp_ssl=FakeSMTP)
    (msg,) = FakeSMTP.sent
    assert msg["To"] == "me@example" and msg["Subject"] == "[AI Radar] Subj"


def test_missing_settings_are_named():
    with pytest.raises(MailError, match="RADAR_EMAIL_TO"):
        send("s", "b", {k: v for k, v in ENV.items() if k != "RADAR_EMAIL_TO"})


def test_smtp_failure_never_leaks_the_password():
    class Broken(FakeSMTP):
        def login(self, user, pw):
            raise smtplib.SMTPAuthenticationError(535, b"bad PW-SECRET")

    with pytest.raises(MailError) as err:
        send("s", "b", ENV, smtp=Broken, smtp_ssl=Broken)
    assert "SECRET" not in str(err.value)
