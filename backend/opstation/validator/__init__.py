"""Scenario validation (spec 13).

    report = validate(scenario)
    if report.ok: publish()
    else: repair(report.for_llm())

A scenario that fails is stored as `invalid` and never offered for play.
"""
from __future__ import annotations

from pathlib import Path

from ..config import Difficulty, difficulty as load_difficulty
from ..models import Scenario
from ..station import Station, station as load_station
from .findings import Finding, Report
from .rules import ALL_RULES, Ctx
from .simulate import Simulation, simulate

__all__ = ["validate", "Report", "Finding", "Ctx", "simulate", "Simulation"]


def validate(
    scenario: Scenario,
    *,
    station: Station | None = None,
    difficulty: Difficulty | None = None,
    audio_dir: Path | None = None,
) -> Report:
    """Run every rule. `audio_dir` is None before the TTS pass, which makes V5
    skip -- the pipeline re-validates with audio present afterwards."""
    st = station or load_station()
    diff = difficulty or load_difficulty()
    sim = simulate(scenario, st, tick=diff.tick_seconds)
    ctx = Ctx(scenario=scenario, station=st, difficulty=diff, sim=sim, audio_dir=audio_dir)

    report = Report(
        scenario_id=scenario.scenario_id,
        simulation=sim.report(),
        difficulty_fingerprint=diff.validator_fingerprint(),
        station_version=st.version,
        rules_run=[f"V{int(f.__name__[1:])}" for f in ALL_RULES],
    )
    for rule in ALL_RULES:
        try:
            report.add(list(rule(ctx)))
        except Exception as exc:  # noqa: BLE001 - a crashing rule must not hide the rest
            report.add([
                Finding(
                    f"V{int(rule.__name__[1:])}",
                    f"rule crashed on this scenario: {type(exc).__name__}: {exc}",
                )
            ])
    report.stats = {
        "messages": len(scenario.messages),
        "tasks": len(scenario.tasks),
        "task_groups": len(scenario.task_groups),
        "threads": len(scenario.threads),
        "incident_threads": sum(1 for t in scenario.threads if t.grade in ("ordinary", "finale")),
        "everyday_exchanges": sum(1 for t in scenario.threads if t.grade == "everyday"),
        "retractions": len(scenario.retractions()),
        "derived_tasks": sum(1 for t in scenario.tasks if t.derived_from),
        "tempting_requests": sum(1 for m in scenario.messages if m.kind == "tempting_request"),
        "radio_messages": sum(1 for m in scenario.messages if m.channel == "radio"),
        "challenges_in_session": len(scenario.challenges),
        "challenges_debrief": len(scenario.debrief_challenges),
        "cancelled_tasks": len(sim.cancelled_task_ids),
        "solvable": sim.solvable,
    }
    return report
