"""One call to OpenRouter. Summarize only: no tools, strict JSON back.

The key comes from the job's own root-only env file and never appears in
an error, a log line or the email. HTTP 402 = the key's monthly cap is hit.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Mapping

URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5.5"
TIMEOUT = 180
MAX_TOKENS = 6000
CAP_HIT = 402


class LLMError(RuntimeError):
    """The model gave no usable answer (the email then goes out as links only)."""


def call_openrouter(
    messages: list[dict],
    schema: dict,
    env: Mapping[str, str],
    opener=urllib.request.urlopen,
) -> str:
    key = env.get("OPENROUTER_API_KEY")
    if not key:
        raise LLMError("OPENROUTER_API_KEY missing")
    body = {
        "model": env.get("RADAR_MODEL") or DEFAULT_MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": 0.2,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "radar_digest", "strict": True, "schema": schema},
        },
    }
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Title": "shipped-or-hype-ai",
            "HTTP-Referer": "https://github.com/lubobali/shipped-or-hype-ai",
        },
        method="POST",
    )
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as err:
        raise LLMError("cost cap reached" if err.code == CAP_HIT else f"HTTP {err.code}") from None
    except (OSError, ValueError) as err:
        raise LLMError(type(err).__name__) from None
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise LLMError("unexpected answer shape") from None
    if not content or not content.strip():
        raise LLMError("empty answer")
    return content
