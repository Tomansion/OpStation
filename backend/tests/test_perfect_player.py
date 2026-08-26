"""The validator says a scenario is solvable. This proves the runtime agrees.

The validator's perfect-player simulation and the engine are two separate
implementations of the same rules -- one plans, one enforces. If they ever drift,
a scenario would pass validation and still be unwinnable, which is the worst
failure this system can have. So the trace the simulation produces is replayed
through the real engine and must score zero.
"""
import pytest
from conftest import make_scenario

from opstation.engine import Engine
from opstation.validator import validate
from opstation.validator.simulate import simulate


def play_the_trace(scenario, station, tick=0.25) -> Engine:
    """Drive the engine with the simulation's toggles and nothing else."""
    sim = simulate(scenario, station, tick=tick)
    engine = Engine(scenario, station=station)
    pending = sorted(sim.trace.toggles, key=lambda t: t.at)
    index = 0
    now = 0.0
    end = float(scenario.duration_seconds)
    while now <= end:
        # Toggles land exactly on the second the obligation opens, and must be
        # applied before the window is evaluated at that instant.
        while index < len(pending) and pending[index].at <= now:
            toggle = pending[index]
            engine.set_door(toggle.door, toggle.to_state, now=toggle.at)
            index += 1
        engine.advance_to(now)
        now = round(now + tick, 4)
    engine.advance_to(end)
    return engine


def test_the_perfect_trace_scores_zero_on_a_crossing(station):
    """The spec's own §6.4 example: open D3 for a crossing, then close it."""
    scenario = make_scenario(tasks=[
        dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=30,
             require={"D3": "open"}, fail_message="crossing blocked"),
        dict(id="t_2", group_id="og_a", message_id="m_1", at=240, hold=0,
             require={"D3": "closed"}, fail_message="left open"),
    ])
    engine = play_the_trace(scenario, station)
    assert engine.penalties == 0
    assert engine.task_state("t_1") == "passed"
    assert engine.task_state("t_2") == "passed"


def test_the_perfect_trace_seals_a_sector_through_the_bypass(station):
    """A derived obligation: the trace has to close D9 as well as D7, because
    Hangar Bay 3 bridges the two corridors."""
    scenario = make_scenario(
        messages=[dict(id="m_1", at=100, thread_id="th_a", actor_id="a_engineering",
                       channel="text", kind="instruction",
                       text="Engineering. Seal the service sector until we find the leak.",
                       task_group_id="og_a")],
        tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=300,
                    require={"D7": "closed", "D9": "closed"},
                    fail_message="the service sector is still open",
                    derived_from=dict(isolation_target="service_sector"))],
    )
    sim = simulate(scenario, station)
    assert {t.door for t in sim.trace.toggles} == {"D7", "D9"}
    engine = play_the_trace(scenario, station)
    assert engine.penalties == 0


def test_a_retracted_obligation_needs_no_action_at_all(station):
    scenario = make_scenario(
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Hold D5 closed.", task_group_id="og_a"),
            dict(id="m_2", at=150, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="retraction", retraction_style="explicit", cancels=["og_a"],
                 text="Forget the D5 hold."),
        ],
        tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=300,
                    require={"D5": "closed"}, fail_message="x")],
    )
    sim = simulate(scenario, station)
    assert sim.trace.toggles == []          # cancelled before it ever began
    assert "t_1" in sim.cancelled_task_ids
    engine = play_the_trace(scenario, station)
    assert engine.penalties == 0
    assert engine.task_state("t_1") == "cancelled"


def test_every_playable_scenario_in_the_bank_is_actually_winnable(station):
    """The real check, against whatever the generator has produced. Skips when
    the bank is empty so a fresh clone still passes."""
    from opstation import bank

    playable = [e for e in bank.listing() if e.valid]
    if not playable:
        pytest.skip("the bank is empty")
    for entry in playable:
        scenario = bank.load(entry.scenario_id)
        report = validate(scenario)
        assert report.simulation["solvable"], f"{entry.scenario_id} is not solvable"
        engine = play_the_trace(scenario, station)
        failed = [o.task_id for o in engine.task_outcomes() if o.state == "failed"]
        assert not failed, f"{entry.scenario_id}: perfect trace still failed {failed}"
        assert engine.penalties == 0, f"{entry.scenario_id} cost {engine.penalties}"
