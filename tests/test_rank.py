import json
from datetime import UTC, datetime

import pytest

from radar.items import Item
from radar.llm import LLMError
from radar.rank import Digest, build_messages, links_only, parse_digest, rank

T = datetime(2026, 10, 26, 12, 0, tzinfo=UTC)


def item(n: int, trust: str = "primary", title: str | None = None) -> Item:
    return Item(
        source_id=f"s{n}",
        source_name=f"Source {n}",
        trust=trust,
        title=title or f"Thing {n} shipped",
        url=f"https://example.com/{n}",
        published=T,
        summary=f"Details about thing {n}.",
    )


ITEMS = [item(1), item(2, "builder"), item(3, "research"), item(4, "opinion", "AGI next year, they say")]


def answer(**over) -> str:
    base = {
        "shipped": [{"id": 1, "line": "Thing 1 is out."}],
        "ideas": [
            {
                "title": "Try thing 1",
                "what": "A tiny agent.",
                "tech": "Thing 1",
                "effort_days": 1.5,
                "cluster": "agents",
                "ids": [1],
            }
        ],
        "checks": [{"id": 4, "verdict": "Nothing shipped backs it.", "evidence_ids": [], "stance": "none"}],
        "model_moves": [{"id": 2, "line": "Cheaper model."}],
    }
    return json.dumps(base | over)


def test_prompt_has_items_and_profile_but_no_urls():
    msgs = build_messages(ITEMS, profile="Python, RAG, MCP")
    text = "\n".join(m["content"] for m in msgs)
    assert "[1]" in text and "Thing 1 shipped" in text and "Python, RAG, MCP" in text
    assert "https://" not in text  # links are attached in Python, never by the model


def test_every_entry_gets_its_link_from_python():
    d = parse_digest(answer(), ITEMS)
    assert d.shipped[0].item.url == "https://example.com/1"
    assert d.ideas[0].items[0].url == "https://example.com/1"
    assert d.model_moves[0].item.url == "https://example.com/2"
    assert d.checks[0].item.url == "https://example.com/4"
    assert d.degraded is None


def test_unknown_ids_are_dropped_no_link_no_item():
    raw = answer(
        shipped=[{"id": 99, "line": "Made up."}, {"id": 1, "line": "Real."}],
        ideas=[{"title": "x", "what": "x", "tech": "x", "effort_days": 1, "cluster": "rag", "ids": [77]}],
    )
    d = parse_digest(raw, ITEMS)
    assert [s.line for s in d.shipped] == ["Real."]
    assert d.ideas == []  # an idea needs at least one real source


def test_urls_written_by_the_model_are_removed():
    raw = answer(shipped=[{"id": 1, "line": "Read more at https://evil.example/x now"}])
    assert "evil" not in parse_digest(raw, ITEMS).shipped[0].line


def test_counts_are_capped_and_effort_is_max_two_days():
    raw = answer(
        shipped=[{"id": 1, "line": str(n)} for n in range(9)],
        ideas=[
            {"title": str(n), "what": "w", "tech": "t", "effort_days": 9, "cluster": "rag", "ids": [1]}
            for n in range(6)
        ],
    )
    d = parse_digest(raw, ITEMS)
    assert len(d.shipped) == 5 and len(d.ideas) == 3
    assert all(i.effort_days <= 2 for i in d.ideas)


def test_checks_are_only_for_opinion_items_once_each_and_capped():
    rows = [{"id": n, "verdict": "v", "evidence_ids": [], "stance": "none"} for n in (1, 4, 4)]
    assert [c.item.trust for c in parse_digest(answer(checks=rows), ITEMS).checks] == ["opinion"]
    pods = [item(n, "opinion") for n in range(1, 10)]
    rows = [{"id": n, "verdict": "v", "evidence_ids": [], "stance": "none"} for n in range(1, 10)]
    assert len(parse_digest(answer(checks=rows, shipped=[], ideas=[], model_moves=[]), pods).checks) == 4


@pytest.mark.parametrize(
    ("evidence", "stance", "expected"),
    [
        ([], "backs", "unverified"),  # no source, no claim of backing
        ([4], "backs", "unverified"),  # opinion can't back opinion
        ([1], "backs", "backs"),
        ([3], "contradicts", "contradicts"),  # sources that say the claim is wrong
        ([1], "partly", "partly"),  # sources back the gist, not the specifics
        ([], "partly", "unverified"),
        ([1], "none", "unverified"),
    ],
)
def test_check_stance_needs_a_non_opinion_source(evidence, stance, expected):
    raw = answer(checks=[{"id": 4, "verdict": "v", "evidence_ids": evidence, "stance": stance}])
    assert parse_digest(raw, ITEMS).checks[0].stance == expected


def test_prompt_asks_for_the_new_tech_not_the_old_stack():
    system = build_messages(ITEMS, profile="p")[0]["content"]
    assert "tech = the new thing" in system


def test_bad_json_falls_back_to_links_only():
    d = rank(ITEMS, profile="p", call=lambda msgs, schema: "not json")
    assert d.degraded and "links only" in d.degraded


def test_cost_cap_falls_back_to_links_only():
    def capped(msgs, schema):
        raise LLMError("cost cap reached")

    d = rank(ITEMS, profile="p", call=capped)
    assert "cost cap reached" in d.degraded
    assert d.ideas == [] and d.checks == []
    assert {s.item.url for s in d.shipped} <= {i.url for i in ITEMS}


def test_links_only_prefers_primary_then_builder_and_skips_opinion():
    d = links_only(ITEMS, reason="x")
    assert [s.item.trust for s in d.shipped] == ["primary", "builder", "research"]
    assert all(s.line == s.item.title for s in d.shipped)


def test_empty_week_is_a_valid_digest():
    d = rank([], profile="p", call=lambda m, s: pytest.fail("no items, no LLM call"))
    assert isinstance(d, Digest) and d.shipped == []


def test_links_only_takes_at_most_two_per_source_for_variety():
    many = [
        Item("cc", "Claude Code", "primary", f"v{n}", f"https://example.com/v{n}", T, "") for n in range(5)
    ]
    d = links_only([*many, item(7)], reason="x")
    assert [s.item.source_name for s in d.shipped] == ["Claude Code", "Claude Code", "Source 7"]
