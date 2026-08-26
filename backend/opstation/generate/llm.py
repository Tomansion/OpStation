"""LiteLLM wrapper. Generation-time only -- the runtime never calls an LLM."""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from ..paths import load_dotenv

DEFAULT_MODEL = "mistral/mistral-large-latest"


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def add(self, response: Any) -> None:
        self.calls += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0


@dataclass
class LLM:
    model: str = ""
    temperature: float = 0.7
    max_retries: int = 3
    #: Per-call wall-clock limit. Without one a stalled socket blocks the whole
    #: pipeline indefinitely -- which is exactly what happened the first time
    #: this ran unattended.
    timeout: float = 240.0
    usage: Usage = field(default_factory=Usage)
    log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        load_dotenv()
        self.model = self.model or os.environ.get("OPSTATION_LLM_MODEL") or DEFAULT_MODEL

    def json(self, system: str, user: str, *, temperature: float | None = None) -> Any:
        """One call that must return a JSON object.

        `response_format={"type": "json_object"}` does the heavy lifting; the
        brace-slicing fallback exists because a model that wraps its JSON in
        prose should cost a retry, not a whole generation run.
        """
        import litellm

        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = litellm.completion(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=self.temperature if temperature is None else temperature,
                    response_format={"type": "json_object"},
                    timeout=self.timeout,
                    num_retries=0,
                )
                self.usage.add(response)
                content = response.choices[0].message.content or ""
                return _parse_json(content)
            except Exception as exc:  # noqa: BLE001 - retried, then surfaced
                last = exc
                self.log.append(f"attempt {attempt} failed: {type(exc).__name__}: {exc}")
                if attempt < self.max_retries:
                    time.sleep(2 * attempt)
        raise LLMError(f"{self.model} failed after {self.max_retries} attempts: {last}")


def _parse_json(content: str) -> Any:
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    start, end = content.find("{"), content.rfind("}")
    if start != -1 and end > start:
        return json.loads(content[start:end + 1])
    raise LLMError(f"response was not JSON: {content[:300]!r}")
