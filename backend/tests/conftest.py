import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from opstation.config import difficulty as load_difficulty  # noqa: E402
from opstation.models import Scenario  # noqa: E402
from opstation.station import station as load_station  # noqa: E402


@pytest.fixture(scope="session")
def station():
    return load_station()


@pytest.fixture(scope="session")
def diff():
    return load_difficulty()


def make_scenario(**over) -> Scenario:
    """A minimal well-formed scenario. Tests override only what they exercise --
    they assert on specific rules, not on a whole publishable scenario."""
    base = dict(
        scenario_id="sc_test",
        name="test",
        duration_seconds=1620,
        station_version=load_station().version,
        actors=[
            dict(id=f"a_{t}", type=t, name=f"{t.title()} Person",
                 portrait=f"{t}.png", voice=t)
            for t in ("security", "construction", "cargo", "medical", "civilian", "system")
        ],
        threads=[dict(id="th_a", title="Test thread", catalogue_key="k", grade="ordinary",
                      phase_span=(1, 5), debrief_summary="s")],
        task_groups=[dict(id="og_a", thread_id="th_a", label="Keep D3 closed")],
        messages=[dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med",
                       channel="text", kind="instruction",
                       text="Door Control, Medical. Keep D3 closed.", task_group_id="og_a")],
        tasks=[],
    )
    base.update(over)
    return Scenario.model_validate(base)


@pytest.fixture
def scenario_factory():
    return make_scenario
