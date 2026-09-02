"""Difficulty tunables and pinned voices.

`config/difficulty.json` holds everything that shapes pressure (spec 9.1). The
generator reads the same file the runtime does, so a scenario is generated
against the tunables it will be played with, and a scenario records the values
it was validated against (V34).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .paths import DIFFICULTY_FILE, voices_file

ACTOR_TYPES: tuple[str, ...] = (
    "security",
    "construction",
    "cargo",
    "medical",
    "civilian",
    "system",
)

MESSAGE_KINDS: frozenset[str] = frozenset({
    "instruction", "update", "supersede", "retraction", "status",
    "tempting_request", "resolution", "reopen", "chatter",
})

RETRACTION_STYLES: frozenset[str] = frozenset({
    "explicit", "self_reference", "cross_actor", "partial",
})

CHALLENGE_KINDS: frozenset[str] = frozenset({"thread", "time", "provenance"})

#: Supplied by the UI, never present in a scenario (spec 8.1).
DONT_KNOW_OPTION_ID = "dont_know"
DONT_KNOW_OPTION_TEXT = "I don't know."


@dataclass(frozen=True)
class Difficulty:
    raw: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    # Frequently used values, named so call sites read as prose.
    @property
    def tick_seconds(self) -> float:
        return self.raw["tick_ms"] / 1000.0

    @property
    def volumes(self) -> dict[str, Any]:
        return self.raw["volumes"]

    def validator_fingerprint(self) -> dict[str, Any]:
        """The subset of tunables the validator depends on. Stored in a
        scenario so the admin page can flag a mismatch with the running
        config (V34) -- changing one of these invalidates the bank."""
        return {k: self.raw[k] for k in self.raw["validator_keys"]}

    def read_cost(self, text: str, audio_duration: float | None = None) -> float:
        """Seconds the player needs to consume a message (spec 5.3)."""
        if audio_duration is not None:
            return round(audio_duration + self.raw["read_cost_base_seconds"], 2)
        words = len(text.split())
        raw = self.raw["read_cost_base_seconds"] + words / self.raw["read_cost_words_per_second"]
        return round(
            min(max(raw, self.raw["read_cost_min_seconds"]), self.raw["read_cost_max_seconds"]), 2
        )

    def read_budget_for_phase(self, phase: int) -> float:
        if phase <= 1:
            return self.raw["read_budget_phase1"]
        if phase >= 5:
            return self.raw["read_budget_finale"]
        return self.raw["read_budget_mid"]


@dataclass(frozen=True)
class Voices:
    raw: dict[str, Any]

    def voice_for(self, actor_type: str) -> str:
        return self.raw["assignment"][actor_type]["voice"]

    def speaker_for(self, actor_type: str) -> int | None:
        """The pinned speaker id inside a multi-speaker model, e.g. the French
        `upmc` voice's `jessica`/`pierre` pair. None for a single-speaker model."""
        return self.raw["assignment"][actor_type].get("speaker_id")

    def post_filter_for(self, actor_type: str) -> str | None:
        return self.raw["assignment"][actor_type].get("post_filter")

    def ffmpeg_filter(self, name: str) -> str:
        return self.raw["post_filters"][name]["ffmpeg"]


@lru_cache(maxsize=1)
def difficulty(path: Path | None = None) -> Difficulty:
    return Difficulty(json.loads((path or DIFFICULTY_FILE).read_text(encoding="utf-8")))


@lru_cache(maxsize=None)
def voices(language: str = "en", path: Path | None = None) -> Voices:
    return Voices(json.loads((path or voices_file(language)).read_text(encoding="utf-8")))


#: Phase boundaries as fractions of duration_seconds (spec 2.1).
PHASE_BOUNDS: tuple[tuple[int, float, float], ...] = (
    (1, 0.00, 0.15),
    (2, 0.15, 0.38),
    (3, 0.38, 0.60),
    (4, 0.60, 0.80),
    (5, 0.80, 1.00),
)


def phase_at(at: float, duration_seconds: int) -> int:
    """Which difficulty phase a moment falls in."""
    frac = at / duration_seconds if duration_seconds else 0.0
    for phase, lo, hi in PHASE_BOUNDS:
        if lo <= frac < hi:
            return phase
    return 5
