"""End-to-end: a real session over the real HTTP + WebSocket surface.

Uses a throwaway bank so the developer's own scenarios are never touched, and a
tiny hand-written scenario so the test exercises the runtime rather than the
generator.
"""
import json

import pytest
from fastapi.testclient import TestClient

from opstation import bank, paths
from opstation.models import Scenario


def build_fixture(root, station) -> Scenario:
    """A two-obligation scenario: hold D3 closed, then open D12 for a crossing."""
    actors = [
        dict(id=f"a_{t}", type=t, name=f"{t.title()} Lead", portrait=f"{t}.png", voice=t)
        for t in ("security", "construction", "cargo", "medical", "civilian", "system")
    ]
    scenario = Scenario.model_validate(dict(
        scenario_id="sc_fixture",
        name="Fixture Shift",
        duration_seconds=200,
        station_version=station.version,
        status="valid",
        actors=actors,
        threads=[
            dict(id="th_med", title="Medical hold", catalogue_key="medical_quarantine",
                 grade="ordinary", phase_span=(1, 5), debrief_summary="D3 held closed."),
            dict(id="th_cargo", title="Cargo crossing", catalogue_key="everyday",
                 grade="finale", phase_span=(1, 5), debrief_summary="D12 crossing."),
        ],
        task_groups=[
            dict(id="og_med", thread_id="th_med", label="Keep D3 closed"),
            dict(id="og_cargo", thread_id="th_cargo", label="Close D12 after the run"),
        ],
        messages=[
            dict(id="m_001", at=1, thread_id="th_med", actor_id="a_medical", channel="text",
                 kind="instruction", text="Door Control, Medical. D3 stays closed.",
                 task_group_id="og_med", read_cost=6.0),
            dict(id="m_002", at=20, thread_id="th_cargo", actor_id="a_cargo", channel="text",
                 kind="instruction", text="Cargo here. Closing D12 behind the pallet run.",
                 task_group_id="og_cargo", read_cost=6.0),
        ],
        tasks=[
            dict(id="t_001", group_id="og_med", message_id="m_001", at=20, hold=60,
                 require={"D3": "closed"},
                 fail_message="MEDICAL BREACH — D3 was opened during the hold."),
            dict(id="t_002", group_id="og_cargo", message_id="m_002", at=40, hold=0,
                 require={"D12": "closed"},
                 fail_message="D12 was left open after the transfer."),
        ],
        challenges=[dict(
            id="q_001", at=120, slot="in_session", kind="provenance", thread_id="th_med",
            actor_id="a_security", channel="text",
            pretext="Security wants to know who locked Medical.",
            prompt="Door Control, Security. Who asked for D3 to stay shut?",
            options=[dict(id="o1", text="Medical.", correct=True), dict(id="o2", text="Cargo."),
                     dict(id="o3", text="Construction."), dict(id="o4", text="Engineering.")],
            explanation="Medical asked at 00:01.", depends_on=["m_001"],
        )],
        debrief_challenges=[dict(
            id="q_002", at=200, slot="debrief", kind="time", thread_id="th_cargo",
            actor_id="a_system", channel="text", pretext="Handover report.",
            prompt="Which door did Cargo ask you to close?",
            options=[dict(id="o1", text="D12.", correct=True), dict(id="o2", text="D3."),
                     dict(id="o3", text="D7."), dict(id="o4", text="H4.")],
            explanation="D12, behind the pallet run.", depends_on=["m_002"],
        )],
    ))
    directory = root / "scenarios" / scenario.scenario_id
    (directory / "audio").mkdir(parents=True, exist_ok=True)
    scenario.dump(directory / "scenario.json")
    # The fixture asserts on runtime behaviour, not on publication, so it carries
    # a hand-written report rather than going through the validator.
    (directory / "validation.json").write_text(json.dumps({"ok": True, "failed_rules": []}))
    return scenario


@pytest.fixture
def client(tmp_path, station, monkeypatch):
    paths.use_data_dir(tmp_path)
    build_fixture(tmp_path, station)
    from websrv import app

    with TestClient(app) as test_client:
        yield test_client
    paths.use_data_dir(paths.ROOT / "data")


def test_station_and_config_are_served(client):
    station = client.get("/api/station").json()
    assert station["version"]
    assert len(station["doors"]) == 18
    config = client.get("/api/config").json()
    # The fifth challenge option comes from the UI, never from a scenario.
    assert config["dont_know"]["text"] == "I don't know."
    assert config["challenge_blocks_doors"] is False


def test_bank_lists_the_fixture(client):
    entries = client.get("/api/scenarios").json()
    assert [e["scenario_id"] for e in entries] == ["sc_fixture"]
    assert entries[0]["playable"] is True


def test_a_session_plays_through(client):
    created = client.post("/api/sessions", json={
        "participant_name": "tester", "scenario_id": "sc_fixture",
    })
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
        snapshot = socket.receive_json()
        assert snapshot["type"] == "snapshot"
        assert snapshot["doors"]["D4"] == "open"
        assert snapshot["doors"]["D3"] == "closed"
        assert snapshot["penalties"] == 0

        socket.send_json({"type": "toggle_door", "door": "D3"})
        state = _await(socket, lambda m: m.get("doors", {}).get("D3") == "open")
        assert state["doors"]["D3"] == "open"

        socket.send_json({"type": "ping"})
        assert _await(socket, lambda m: m.get("type") == "pong")["elapsed"] >= 0


def test_an_unplayable_scenario_is_refused(client, tmp_path):
    directory = tmp_path / "scenarios" / "sc_broken"
    (directory / "audio").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scenarios" / "sc_fixture" / "scenario.json").replace(
        directory / "scenario.json"
    )
    (directory / "validation.json").write_text(json.dumps({"ok": False, "failed_rules": ["V14"]}))
    response = client.post("/api/sessions", json={
        "participant_name": "x", "scenario_id": "sc_broken",
    })
    assert response.status_code in (404, 409)


def test_admin_status_reports_the_bank(client):
    status = client.get("/api/admin/status").json()
    assert status["bank"]["total"] == 1
    assert status["station_version"]
    # One assignment per generation language (spec 11.2), each covering all
    # six actor types.
    assert set(status["voices"]) == {"en", "fr"}
    for assignment in status["voices"].values():
        assert set(assignment) == {
            "security", "construction", "cargo", "medical", "civilian", "system"
        }


def _await(socket, predicate, limit=25):
    for _ in range(limit):
        message = socket.receive_json()
        if predicate(message):
            return message
    raise AssertionError("expected message never arrived")
