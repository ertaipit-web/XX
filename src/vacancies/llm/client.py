"""LLM client abstraction with Ollama and Mock providers.

The client is intentionally small: it exposes a single `generate()` method that
returns plain text, plus `generate_json()` that parses a JSON object out of the
model response. Retries, timeouts and a hard output-length cap keep local model
calls bounded and safe.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when an LLM call fails after exhausting retries."""


@dataclass
class LLMConfig:
    """Configuration for an LLM provider."""

    provider: str = "ollama"          # "ollama" | "mock"
    model: str = "qwen2.5-coder:3b"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.2
    timeout: float = 120.0
    max_retries: int = 2
    retry_delay: float = 1.0
    max_output_tokens: int = 512
    enabled: bool = True              # master switch (fallback to heuristics if False)


class BaseLLMClient:
    """Common interface for LLM clients."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.calls: int = 0  # simple call counter for limits/observability

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        raise NotImplementedError

    def generate_json(
        self, prompt: str, system: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Generate a response and parse the first JSON object from it.

        Returns None if no valid JSON object can be extracted.
        """
        raw = self.generate(prompt, system=system)
        return self._extract_json(raw)

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        """Extract the first JSON object from a model response."""
        if not text:
            return None
        # Strip common markdown fences
        cleaned = re.sub(r"```(?:json)?", "", text).strip("` \n")
        # Fast path
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass
        # Balanced-brace scan for the first object
        start = cleaned.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : i + 1]
                    try:
                        data = json.loads(candidate)
                        return data if isinstance(data, dict) else None
                    except json.JSONDecodeError:
                        return None
        return None


class OllamaClient(BaseLLMClient):
    """Client for a local Ollama server."""

    def __init__(self, config: LLMConfig) -> None:
        super().__init__(config)
        try:
            import requests  # local import keeps this optional
        except ImportError as e:  # pragma: no cover
            raise LLMError("requests is required for OllamaClient") from e
        self._requests = requests

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        url = f"{self.config.base_url.rstrip('/')}/api/generate"
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_output_tokens,
            },
        }
        if system:
            payload["system"] = system

        attempts = self.config.max_retries + 1
        last_error: Optional[Exception] = None
        for attempt in range(1, attempts + 1):
            try:
                resp = self._requests.post(url, json=payload, timeout=self.config.timeout)
                if resp.status_code != 200:
                    raise LLMError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")
                data = resp.json()
                self.calls += 1
                return str(data.get("response", ""))
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.warning("LLM call failed (attempt %d/%d): %s", attempt, attempts, e)
                if attempt < attempts:
                    time.sleep(self.config.retry_delay)

        raise LLMError(f"Ollama call failed after {attempts} attempts: {last_error}")


class MockLLMClient(BaseLLMClient):
    """Deterministic client for tests and offline mode.

    Responses are supplied per-call (FIFO) or via a default fallback. This makes
    tests independent of a running Ollama server.
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        responses: Optional[List[str]] = None,
        default_response: str = "{}",
        raise_on_call: bool = False,
    ) -> None:
        super().__init__(config or LLMConfig(provider="mock"))
        self._responses = list(responses or [])
        self._default = default_response
        self.raise_on_call = raise_on_call
        self.prompts: List[str] = []

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        if self.raise_on_call:
            raise LLMError("MockLLMClient configured to fail")
        if self._responses:
            return self._responses.pop(0)
        return self._default


def build_llm_client(config: LLMConfig) -> BaseLLMClient:
    """Factory: build a client from config, falling back to Mock if disabled."""
    if not config.enabled or config.provider == "mock":
        return MockLLMClient(config)
    if config.provider == "ollama":
        return OllamaClient(config)
    raise LLMError(f"Unknown LLM provider: {config.provider}")
