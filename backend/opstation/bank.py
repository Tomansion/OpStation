"""The scenario bank.

Flat files, no database. A scenario directory holds its `scenario.json`, its
`validation.json` report and its pre-rendered audio. Only scenarios whose
report passed are offered for play.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import difficulty as load_difficulty
from .models import Scenario
from . import paths
from .station import station as load_station


@dataclass
class BankEntry:
    scenario_id: str
    name: str
    language: str
    duration_seconds: int
    threads: int
    messages: int
    valid: bool
    station_version: str
    generated_at: str
    has_audio: bool
    radio_messages: int
    tunables_match: bool
    failed_rules: list[str]

    def as_json(self) -> dict:
        return self.__dict__ | {"playable": self.playable}

    @property
    def playable(self) -> bool:
        """Audio failure voids a session, so a scenario with missing audio is
        not offered rather than degraded (spec 5.1)."""
        return self.valid and (self.radio_messages == 0 or self.has_audio)


def _validation(directory: Path) -> dict:
    path = directory / "validation.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def entry_for(directory: Path) -> BankEntry | None:
    path = directory / "scenario.json"
    if not path.exists():
        return None
    try:
        scenario = Scenario.load(path)
    except Exception:  # noqa: BLE001 - a broken file is listed as invalid, not fatal
        return BankEntry(
            scenario_id=directory.name, name="(unreadable)", language="en",
            duration_seconds=0, threads=0,
            messages=0, valid=False, station_version="", generated_at="", has_audio=False,
            radio_messages=0, tunables_match=False, failed_rules=["unreadable"],
        )
    report = _validation(directory)
    radio = sum(1 for m in scenario.messages if m.channel == "radio")
    audio_dir = directory / "audio"
    rendered = len(list(audio_dir.glob("*.wav"))) if audio_dir.exists() else 0
    want = load_difficulty().validator_fingerprint()
    return BankEntry(
        scenario_id=scenario.scenario_id,
        name=scenario.name,
        language=scenario.language,
        duration_seconds=scenario.duration_seconds,
        threads=sum(1 for t in scenario.threads if t.grade in ("ordinary", "finale")),
        messages=len(scenario.messages),
        valid=bool(report.get("ok")) and scenario.status == "valid",
        station_version=scenario.station_version,
        generated_at=scenario.generated_at,
        has_audio=rendered >= radio and radio > 0,
        radio_messages=radio,
        tunables_match=scenario.difficulty_fingerprint == want,
        failed_rules=list(report.get("failed_rules") or []),
    )


def listing(root: Path | None = None) -> list[BankEntry]:
    root = root or paths.SCENARIOS_DIR
    if not root.exists():
        return []
    entries = [entry_for(d) for d in sorted(root.iterdir()) if d.is_dir()]
    return [e for e in entries if e is not None]


def load(scenario_id: str) -> Scenario:
    path = paths.scenario_dir(scenario_id) / "scenario.json"
    if not path.exists():
        raise FileNotFoundError(f"no scenario {scenario_id!r} in the bank")
    return Scenario.load(path)


def validation_report(scenario_id: str) -> dict:
    return _validation(paths.scenario_dir(scenario_id))


def audio_root(scenario_id: str) -> Path:
    return paths.scenario_dir(scenario_id)


def station_version_ok(scenario: Scenario) -> bool:
    return scenario.station_version == load_station().version
