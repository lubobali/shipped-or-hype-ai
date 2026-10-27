import io
import json
import urllib.error

import pytest

from radar.llm import LLMError, call_openrouter

ENV = {"OPENROUTER_API_KEY": "sk-or-SECRET", "RADAR_MODEL": "some/model"}
MSGS = [{"role": "user", "content": "hi"}]
SCHEMA = {"type": "object"}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def ok(content: str):
    body = {"choices": [{"message": {"content": content}}]}

    def opener(req, timeout):
        opener.req = req
        return FakeResponse(json.dumps(body).encode())

    return opener


def http_error(code: int):
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(b"sk-or-SECRET echoed"))

    return opener


def test_sends_strict_json_schema_and_returns_content():
    opener = ok('{"a": 1}')
    assert call_openrouter(MSGS, SCHEMA, ENV, opener=opener) == '{"a": 1}'
    sent = json.loads(opener.req.data)
    assert sent["model"] == "some/model"
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert "tools" not in sent  # summarize only, no tools
    assert opener.req.full_url.startswith("https://openrouter.ai/")


def test_missing_key_is_a_clear_error():
    with pytest.raises(LLMError, match="OPENROUTER_API_KEY"):
        call_openrouter(MSGS, SCHEMA, {}, opener=ok("{}"))


@pytest.mark.parametrize(
    ("code", "reason"), [(402, "cost cap reached"), (429, "HTTP 429"), (500, "HTTP 500")]
)
def test_http_errors_are_short_and_never_leak_the_key(code, reason):
    with pytest.raises(LLMError) as err:
        call_openrouter(MSGS, SCHEMA, ENV, opener=http_error(code))
    assert reason in str(err.value)
    assert "SECRET" not in str(err.value)


def test_empty_answer_is_an_error():
    with pytest.raises(LLMError, match="empty"):
        call_openrouter(MSGS, SCHEMA, ENV, opener=ok(""))
