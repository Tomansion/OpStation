"""Deterministic repair functions in generate/repair.py -- pure arithmetic
fixes that should never need an LLM call to get right."""
from conftest import make_scenario

from opstation.generate.repair import (
    _fix_message_spacing,
    _fix_speaker_mismatch,
    _trim_excess_retractions,
)
from opstation.validator.findings import Finding


def test_v9_moves_the_earlier_message_back_when_there_is_room():
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med", channel="text",
             kind="instruction", text="One."),
        dict(id="m_2", at=102, thread_id="th_a", actor_id="a_sec", channel="text",
             kind="status", text="Two."),
    ], tasks=[])
    findings = [Finding("V9", "only 2s after m_1", "m_2")]
    log = _fix_message_spacing(sc, findings)
    assert log
    by_id = {m.id: m for m in sc.messages}
    assert by_id["m_2"].at - by_id["m_1"].at >= 6


def test_v9_advances_the_later_message_and_its_own_tasks_when_no_room_to_retreat():
    """The earlier message cannot retreat past 0, so the later message must
    move forward instead -- taking its own task with it so V7's reading slack
    does not shrink."""
    sc = make_scenario(messages=[
        dict(id="m_1", at=1, thread_id="th_a", actor_id="a_med", channel="text",
             kind="instruction", text="One."),
        dict(id="m_2", at=3, thread_id="th_a", actor_id="a_sec", channel="text",
             kind="status", text="Two."),
    ], tasks=[dict(id="t_1", group_id="og_a", message_id="m_2", at=20, hold=30,
                   require={"D3": "closed"}, fail_message="x")])
    findings = [Finding("V9", "only 2s after m_1", "m_2")]
    log = _fix_message_spacing(sc, findings)
    assert log
    by_id = {m.id: m for m in sc.messages}
    assert by_id["m_2"].at - by_id["m_1"].at >= 6
    moved_task = next(t for t in sc.tasks if t.id == "t_1")
    assert moved_task.at == 20 + (6 - 2)  # shifted by exactly the shortfall


def test_no_findings_means_no_change():
    sc = make_scenario()
    before = [m.at for m in sc.messages]
    assert _fix_message_spacing(sc, []) == []
    assert [m.at for m in sc.messages] == before


def test_v6_reassigns_speaker_to_the_actor_the_text_names():
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_system", channel="text",
             kind="status", text="Construction confirms the D13 hold is released."),
    ])
    findings = [Finding("V6", "spoken by system but introduces itself as "
                              "['construction']", "m_1")]
    log = _fix_speaker_mismatch(sc, findings)
    assert log
    assert sc.messages_by_id["m_1"].actor_id == "a_construction"


def test_v6_does_nothing_without_findings():
    sc = make_scenario()
    assert _fix_speaker_mismatch(sc, []) == []


def _retraction(mid, at):
    return dict(id=mid, at=at, thread_id="th_a", actor_id="a_med", channel="radio",
                kind="retraction", retraction_style="explicit", cancels=["og_a"],
                text=f"Forget what I said about D3 ({mid}).")


def test_v30_trims_the_most_recent_retractions_first_when_over_quota():
    """schedule.py deliberately keeps one more retraction than the quota, as
    insurance against later attrition -- on a run where nothing is lost, this
    trims the surplus back down rather than leaving too many (V30)."""
    sc = make_scenario(messages=[
        _retraction("m_1", 100), _retraction("m_2", 300),
        _retraction("m_3", 500), _retraction("m_4", 700),
    ])
    findings = [Finding("V30", "4 retractions, expected 2-3")]
    log = _trim_excess_retractions(sc, findings)
    assert log
    kinds = {m.id: m.kind for m in sc.messages}
    assert sum(1 for k in kinds.values() if k == "retraction") == 3
    # The latest-scheduled one gives way first.
    assert kinds["m_4"] == "status"
    assert kinds["m_1"] == kinds["m_2"] == kinds["m_3"] == "retraction"


def test_v30_does_nothing_when_not_over_quota():
    sc = make_scenario(messages=[_retraction("m_1", 100), _retraction("m_2", 300)])
    findings = [Finding("V30", "2 retractions, expected 2-3")]
    assert _trim_excess_retractions(sc, findings) == []
    assert all(m.kind == "retraction" for m in sc.messages)
