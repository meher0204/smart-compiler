"""GeminiClient tests: the HTTP layer is faked, nothing touches the network."""

import io
import json
import urllib.error

import pytest

from scompiler.ai import AIUnavailable, GeminiClient, resolve_client
from scompiler.ai.client import AnthropicClient


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def ok(payload):
    return FakeResponse(json.dumps(payload).encode())


def http_error(code, message="boom"):
    body = io.BytesIO(json.dumps({"error": {"message": message}}).encode())
    return urllib.error.HTTPError("http://x", code, "err", {}, body)


@pytest.fixture
def fake_http(monkeypatch):
    """Queue of responses/exceptions; records every request made."""
    state = {"queue": [], "requests": []}

    def fake_urlopen(req, timeout=None):
        state["requests"].append(req)
        item = state["queue"].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return state


def reply_payload(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


def test_request_shape_and_roles(fake_http):
    fake_http["queue"].append(ok(reply_payload('{"a": 1}')))
    client = GeminiClient(model="gemini-test", api_key="KEY")
    text = client.complete(
        "SYS", [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"},
                {"role": "user", "content": "q2"}]
    )
    assert text == '{"a": 1}'
    req = fake_http["requests"][0]
    assert req.full_url.endswith("/models/gemini-test:generateContent")
    assert req.get_header("X-goog-api-key") == "KEY"
    assert "key=" not in req.full_url  # key goes in a header, never in the URL
    body = json.loads(req.data)
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_thought_parts_are_ignored(fake_http):
    payload = {"candidates": [{"content": {"parts": [
        {"text": "internal reasoning", "thought": True}, {"text": "ANSWER"}]}}]}
    fake_http["queue"].append(ok(payload))
    assert GeminiClient(api_key="K").complete("s", [{"role": "user", "content": "q"}]) == "ANSWER"


def test_retries_on_429_then_succeeds(fake_http):
    sleeps = []
    fake_http["queue"] += [http_error(429), ok(reply_payload("fine"))]
    client = GeminiClient(api_key="K", sleep=sleeps.append)
    assert client.complete("s", [{"role": "user", "content": "q"}]) == "fine"
    assert len(fake_http["requests"]) == 2 and sleeps == [2.0]


def test_gives_up_after_retries(fake_http):
    fake_http["queue"] += [http_error(429)] * 3
    client = GeminiClient(api_key="K", sleep=lambda s: None)
    with pytest.raises(AIUnavailable, match="rate limit"):
        client.complete("s", [{"role": "user", "content": "q"}])


def test_404_points_to_list_models(fake_http):
    fake_http["queue"].append(http_error(404, "not found"))
    with pytest.raises(AIUnavailable, match="--list-models"):
        GeminiClient(api_key="K", model="nope").complete("s", [{"role": "user", "content": "q"}])


def test_blocked_and_empty_replies(fake_http):
    c = GeminiClient(api_key="K")
    fake_http["queue"].append(ok({"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(AIUnavailable, match="blocked"):
        c.complete("s", [{"role": "user", "content": "q"}])
    fake_http["queue"].append(ok({"candidates": [{"finishReason": "MAX_TOKENS"}]}))
    with pytest.raises(AIUnavailable, match="MAX_TOKENS"):
        c.complete("s", [{"role": "user", "content": "q"}])


def test_network_failure_is_reported(fake_http):
    fake_http["queue"].append(urllib.error.URLError("no wifi"))
    with pytest.raises(AIUnavailable, match="could not reach"):
        GeminiClient(api_key="K").complete("s", [{"role": "user", "content": "q"}])


def test_list_models_filters_to_generate_content(fake_http):
    fake_http["queue"].append(ok({"models": [
        {"name": "models/a-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]},
    ]}))
    assert GeminiClient(api_key="K").list_models() == ["a-flash"]


def test_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(AIUnavailable, match="GEMINI_API_KEY"):
        GeminiClient()


def test_google_api_key_env_is_accepted(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "abc")
    assert GeminiClient().model  # constructed without raising


def test_resolve_client_auto(monkeypatch):
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(AIUnavailable, match="GEMINI_API_KEY or ANTHROPIC_API_KEY"):
        resolve_client("auto")
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert isinstance(resolve_client("auto"), GeminiClient)
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    try:
        assert isinstance(resolve_client("auto"), AnthropicClient)
    except AIUnavailable:  # anthropic SDK not installed in this environment
        pass
