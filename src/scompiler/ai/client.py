"""client.py - Model access behind a tiny interface so tests and providers are swappable."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable, Dict, List, Optional, Protocol, Sequence

DEFAULT_MODEL = "claude-sonnet-5-5"  # override with --model or SCOMPILER_MODEL
# Google retires/renames models often, so default to an alias and let --model override it.
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
PROVIDERS = ("auto", "gemini", "anthropic")


class AIUnavailable(RuntimeError):
    """No usable AI backend (missing SDK / API key) or the call itself failed."""


class AIClient(Protocol):
    def complete(self, system: str, messages: List[Dict[str, str]]) -> str: ...


class AnthropicClient:
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        max_tokens: int = 1000,
        timeout: float = 30.0,
    ) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise AIUnavailable("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError:
            raise AIUnavailable("the 'anthropic' package is not installed (pip install anthropic)")
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=key, timeout=timeout)
        self.model = model or os.environ.get("SCOMPILER_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens

    def complete(self, system: str, messages: List[Dict[str, str]]) -> str:
        try:
            resp = self._client.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=system, messages=messages
            )
        except self._anthropic.APIError as exc:
            raise AIUnavailable(f"API call failed: {exc}") from exc
        return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


class GeminiClient:
    """Google Gemini over plain REST (stdlib only, no SDK to install).

    Key: GEMINI_API_KEY (or GOOGLE_API_KEY). Free-tier keys from Google AI Studio work.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        max_output_tokens: int = 4096,  # headroom: "thinking" models spend tokens before answering
        timeout: float = 60.0,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise AIUnavailable("GEMINI_API_KEY is not set")
        self._key = key
        self.model = model or os.environ.get("SCOMPILER_MODEL") or DEFAULT_GEMINI_MODEL
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout
        self.retries = retries
        self._sleep = sleep

    # ---- HTTP -------------------------------------------------------------
    def _request(self, url: str, body: Optional[dict] = None) -> dict:
        data = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"x-goog-api-key": self._key}
        if data is not None:
            headers["Content-Type"] = "application/json"
        delay = 2.0
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = _gemini_error_text(exc)
                if exc.code in (429, 500, 503) and attempt < self.retries:
                    self._sleep(delay)
                    delay *= 3
                    continue
                raise AIUnavailable(_gemini_hint(exc.code, detail, self.model)) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                raise AIUnavailable(f"could not reach the Gemini API: {exc}") from exc
        raise AIUnavailable("Gemini API retries exhausted")  # pragma: no cover

    # ---- public -----------------------------------------------------------
    def complete(self, system: str, messages: List[Dict[str, str]]) -> str:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "model" if m["role"] == "assistant" else "user",
                    "parts": [{"text": m["content"]}],
                }
                for m in messages
            ],
            "generationConfig": {
                "maxOutputTokens": self.max_output_tokens,
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        model = self.model if self.model.startswith("models/") else f"models/{self.model}"
        data = self._request(f"{GEMINI_BASE}/{model}:generateContent", body)

        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise AIUnavailable(f"Gemini blocked the prompt ({block})")
        candidates = data.get("candidates") or []
        if not candidates:
            raise AIUnavailable("Gemini returned no candidates")
        cand = candidates[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise AIUnavailable(
                f"Gemini returned no text (finishReason={cand.get('finishReason', '?')})"
            )
        return text

    def list_models(self) -> List[str]:
        """Model names this key can call generateContent on (for --list-models)."""
        names: List[str] = []
        url = f"{GEMINI_BASE}/models?pageSize=100"
        data = self._request(url)
        for m in data.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                names.append(m["name"].removeprefix("models/"))
        return names


def _gemini_error_text(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
        return str(payload.get("error", {}).get("message", "")) or str(exc)
    except Exception:  # noqa: BLE001 - best-effort message extraction
        return str(exc)


def _gemini_hint(code: int, detail: str, model: str) -> str:
    hints = {
        400: "bad request (is the API key valid and unrestricted?)",
        401: "API key rejected",
        403: "API key rejected or not allowed to use this model",
        404: f"model {model!r} not found; run with --list-models and pass one via --model",
        429: "rate limit hit (free tier is limited per minute/day); wait a minute and retry",
    }
    prefix = hints.get(code, f"HTTP {code}")
    return f"Gemini API error: {prefix}. Server said: {detail}"


def resolve_client(provider: str = "auto", model: Optional[str] = None) -> AIClient:
    """Pick a backend. auto = Gemini if a Google key is set, else Anthropic if its key is set."""
    if provider == "gemini":
        return GeminiClient(model=model)
    if provider == "anthropic":
        return AnthropicClient(model=model)
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return GeminiClient(model=model)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicClient(model=model)
    raise AIUnavailable("no API key found (set GEMINI_API_KEY or ANTHROPIC_API_KEY)")


class ScriptedClient:
    """Returns canned replies in order. For tests and offline demos; never hits the network."""

    def __init__(self, replies: Sequence[str]) -> None:
        self._replies = list(replies)
        self.calls: List[List[Dict[str, str]]] = []

    def complete(self, system: str, messages: List[Dict[str, str]]) -> str:
        self.calls.append([dict(m) for m in messages])
        if not self._replies:
            raise AIUnavailable("ScriptedClient ran out of replies")
        return self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
