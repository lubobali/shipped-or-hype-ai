import json
from datetime import UTC, datetime

from radar.claims import MAX_CHARS, expand_podcasts, extract_claims
from radar.items import Item
from radar.llm import LLMError

T = datetime(2026, 10, 26, tzinfo=UTC)
EP = Item(
    "moonshots", "Moonshots", "opinion", "Chamath: AGI Is Here", "https://pod.example/ep1.mp3", T, "notes"
)
NEWS = Item("openai", "OpenAI", "primary", "GPT ships", "https://openai.com/x", T, "")
TEXT = "So Chamath said: I think AGI is already here, honestly. And robot brains halve in cost every 3 weeks."


def answer(*claims):
    return lambda msgs, schema: json.dumps({"claims": [{"claim": c, "quote": q} for c, q in claims]})


def test_claims_become_opinion_items_linked_to_the_episode():
    got = extract_claims(EP, TEXT, answer(("AGI is already here.", "I think AGI is already here, honestly")))
    (c,) = got
    assert c.trust == "opinion" and c.url == EP.url and c.source_name == "Moonshots"
    assert c.title == "AGI is already here."
    assert c.summary == 'Quote: "I think AGI is already here, honestly"'


def test_a_claim_whose_quote_is_not_in_the_transcript_is_dropped():
    got = extract_claims(
        EP,
        TEXT,
        answer(
            ("Made up.", "GPT-7 launches tomorrow for free"),
            ("Robot brains get cheap fast.", "robot brains  HALVE in cost every 3 weeks"),  # spacing/case ok
        ),
    )
    assert [c.title for c in got] == ["Robot brains get cheap fast."]


def test_curly_quotes_still_match():
    text = "He said it’s “the year of agents” for sure."
    got = extract_claims(EP, text, answer(("Agents year.", 'it\'s "the year of agents" for sure')))
    assert len(got) == 1


def test_at_most_five_claims():
    q = "I think AGI is already here, honestly"
    assert len(extract_claims(EP, TEXT, answer(*[(f"c{n}", q) for n in range(9)]))) == 5


def test_prompt_marks_the_transcript_untrusted_and_caps_its_size():
    seen = {}

    def call(msgs, schema):
        seen["msgs"] = msgs
        return '{"claims": []}'

    extract_claims(EP, "x" * (MAX_CHARS + 5000), call)
    system, user = (m["content"] for m in seen["msgs"])
    assert "untrusted" in system
    assert len(user) < MAX_CHARS + 1000


def test_llm_failure_gives_no_claims():
    def capped(msgs, schema):
        raise LLMError("cost cap reached")

    assert extract_claims(EP, TEXT, capped) == []
    assert extract_claims(EP, TEXT, lambda m, s: "not json") == []


def test_expand_swaps_a_transcribed_episode_for_its_claims_and_keeps_the_rest():
    q = "I think AGI is already here, honestly"
    out = expand_podcasts([NEWS, EP], {EP.url: TEXT}, answer(("AGI is here.", q)))
    assert [i.title for i in out] == ["GPT ships", "AGI is here."]


def test_expand_keeps_the_episode_when_no_claim_survives():
    out = expand_podcasts([EP], {EP.url: TEXT}, answer(("Made up.", "not in the text at all")))
    assert out == [EP]


def test_prompt_keeps_claims_short():
    seen = {}

    def call(msgs, schema):
        seen["system"] = msgs[0]["content"]
        return '{"claims": []}'

    extract_claims(EP, TEXT, call)
    assert "20 words" in seen["system"]


def test_an_overlong_claim_is_cut_to_the_limit():
    long_claim = "word " * 80
    (c,) = extract_claims(EP, TEXT, answer((long_claim, "I think AGI is already here, honestly")))
    assert len(c.title) <= 160
