"""The Monday email: plain text, one screen, every line with its source link.

Plain text on purpose: no HTML from feed text can ever render. Plain SMTP
(port 465 = TLS, any other port = STARTTLS). The
password never appears in a message, a log line or an error.
"""

import smtplib
from collections.abc import Mapping
from datetime import datetime, timedelta
from email.message import EmailMessage

from radar.items import WINDOW
from radar.rank import Digest, Line

REQUIRED = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "RADAR_EMAIL_TO")
PREFIX = "[AI Radar]"
SSL_PORT = 465
TIMEOUT = 30
RULE = "-" * 40
LABELS = {"backs": "BACKED BY A SOURCE", "partly": "PARTLY BACKED", "contradicts": "SOURCES SAY OTHERWISE"}


class MailError(RuntimeError):
    """The email could not be sent."""


def _lines(rows: list[Line]) -> list[str]:
    out = []
    for r in rows:
        out += [f"- {r.line}", f"  {r.item.source_name} · {r.item.url}"]
    return out


def render(digest: Digest, now: datetime, items_read: int, failures: Mapping[str, str]) -> tuple[str, str]:
    week = now.isocalendar().week
    start = now - WINDOW + timedelta(days=1)
    head = f"AI RADAR · week {week} · {start:%b %-d} – {now:%b %-d, %Y}"
    body = [head, ""]
    if digest.degraded:
        body += [f"Links only this week: {digest.degraded.removeprefix('links only: ')}", ""]

    if not (digest.shipped or digest.ideas or digest.checks or digest.model_moves):
        body += ["Nothing new this week.", ""]
    if digest.shipped:
        body += ["1. SHIPPED THIS WEEK", *_lines(digest.shipped), ""]
    if digest.ideas:
        body.append("2. BUILD IDEAS (2 days or less)")
        for n, idea in enumerate(digest.ideas):
            body += [
                f"{chr(65 + n)}. {idea.title}  [{idea.cluster} · {idea.effort_days:g} days]",
                f"  What: {idea.what}",
                f"  New tech: {idea.tech}",
                *(f"  Source: {i.url}" for i in idea.items),
                "",
            ]
    if digest.checks:
        body.append("3. PODCAST CLAIMS, CHECKED")
        for c in digest.checks:
            quote = [f"  {c.item.summary}"] if c.item.summary.startswith("Quote: ") else []
            body += [
                f"[{LABELS.get(c.stance, 'UNVERIFIED')}]",
                f'  "{c.item.title}" ({c.item.source_name})',
                *quote,
                f"  What the evidence says: {c.verdict}",
                *(f"  Evidence: {e.url}" for e in c.evidence),
                f"  Episode: {c.item.url}",
                "",
            ]
    if digest.model_moves:
        body += ["4. MODEL MOVES", *_lines(digest.model_moves), ""]

    body += [RULE, f"{items_read} items read."]
    if failures:
        body.append("Couldn't read: " + ", ".join(f"{name} ({why})" for name, why in failures.items()))

    subject = f"Week {week}: {len(digest.shipped)} shipped, {len(digest.ideas)} build ideas"
    if digest.degraded:
        subject += " (links only)"
    return subject, "\n".join(body) + "\n"


def send(  # noqa: PLR0913 — the two SMTP classes are the test seam
    subject: str,
    body: str,
    env: Mapping[str, str],
    smtp=smtplib.SMTP,
    smtp_ssl=smtplib.SMTP_SSL,
    prefix: str = PREFIX,
) -> None:
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        raise MailError(f"email not configured: {', '.join(missing)} missing")
    port = int(env.get("SMTP_PORT") or 587)
    msg = EmailMessage()
    msg["Subject"] = f"{prefix} {subject}"
    msg["From"] = env.get("RADAR_EMAIL_FROM") or env["SMTP_USER"]
    msg["To"] = env["RADAR_EMAIL_TO"]
    msg.set_content(body)
    try:
        with (smtp_ssl if port == SSL_PORT else smtp)(env["SMTP_HOST"], port, timeout=TIMEOUT) as s:
            if port != SSL_PORT:
                s.starttls()
            s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
            s.send_message(msg)
    except (OSError, smtplib.SMTPException) as err:
        raise MailError(f"email failed: {type(err).__name__}") from None
