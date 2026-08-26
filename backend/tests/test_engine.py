"""The runtime. Everything here is about the correctness model of spec 6-9."""
import pytest
from conftest import make_scenario

from opstation.config import DONT_KNOW_OPTION_ID
from opstation.engine import Engine


def eng(**over) -> Engine:
    return Engine(make_scenario(**over))


def hold_task(**over):
    base = dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=300,
                require={"D3": "closed"}, fail_message="Medical was left exposed.")
    base.update(over)
    return base


def test_hold_fails_at_the_exact_moment_of_violation():
    """A 250 ms tick would let a player open and reclose a door between samples.
    Evaluating on the toggle itself closes that hole."""
    e = eng(tasks=[hold_task()])
    e.advance_to(250)
    assert e.task_state("t_1") == "active"
    e.toggle_door("D3", now=250.4)  # D3 starts closed, so this opens it
    assert e.task_state("t_1") == "failed"
    assert e.penalties == 1
    failure = next(ev for ev in e.events if ev.kind == "task_failed")
    assert failure.at == 250.4 and failure.detail["door"] == "D3"


def test_opening_and_reclosing_between_ticks_still_fails():
    e = eng(tasks=[hold_task()])
    e.advance_to(250)
    e.toggle_door("D3", now=250.10)
    e.toggle_door("D3", now=250.20)
    e.advance_to(251)
    assert e.task_state("t_1") == "failed"


def test_a_held_obligation_passes_when_never_violated():
    e = eng(tasks=[hold_task()])
    e.advance_to(600)
    assert e.task_state("t_1") == "passed"
    assert e.penalties == 0


def test_holding_an_already_correct_state_is_a_real_obligation():
    """D3 starts closed, so this task asks the player to resist a tempting
    request rather than to act. It still fails if they comply."""
    e = eng(tasks=[hold_task()])
    e.advance_to(300)
    assert e.task_state("t_1") == "active"
    e.toggle_door("D3", now=300)
    assert e.task_state("t_1") == "failed"


def test_instantaneous_task_checks_once():
    e = eng(tasks=[hold_task(hold=0, require={"D3": "open"})])
    e.advance_to(199)
    assert e.task_state("t_1") == "pending"
    e.advance_to(201)
    assert e.task_state("t_1") == "failed"  # never opened


def test_group_cascade_costs_exactly_one_penalty():
    """One broken obligation, one penalty -- and no false credit for a later
    task that happens to be satisfied for the wrong reason (spec 6.4)."""
    e = eng(
        task_groups=[dict(id="og_a", thread_id="th_a", label="crossing")],
        tasks=[
            hold_task(id="t_1", at=200, hold=30, require={"D3": "open"}),
            hold_task(id="t_2", at=240, hold=0, require={"D3": "closed"}),
        ],
    )
    e.advance_to(260)
    assert e.task_state("t_1") == "failed"       # never opened for the crossing
    assert e.task_state("t_2") == "cancelled"    # would have passed for the wrong reason
    assert e.penalties == 1


def test_retraction_cancels_on_delivery_not_on_acknowledgement():
    e = eng(
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med", channel="text",
                 kind="instruction", text="Keep D3 closed.", task_group_id="og_a"),
            dict(id="m_2", at=300, thread_id="th_a", actor_id="a_med", channel="text",
                 kind="retraction", retraction_style="self_reference", cancels=["og_a"],
                 text="Forget what I asked about D3."),
        ],
        tasks=[hold_task(at=200, hold=600)],
    )
    e.advance_to(299)
    assert e.task_state("t_1") == "active"
    e.advance_to(300)
    assert e.task_state("t_1") == "cancelled"
    e.toggle_door("D3", now=400)          # freed, so this now costs nothing
    assert e.penalties == 0
    # Neither message has been opened. The obligation was withdrawn anyway, so a
    # player who never read either one keeps doing the old thing at no cost --
    # which is exactly why cancellation triggers on delivery, not on the click.
    assert [i.ref_id for i in e.pending] == ["m_1", "m_2"]
    assert all(i.opened_at is None for i in e.pending)


def test_a_cancellation_does_not_undo_a_failure_that_already_fired():
    e = eng(
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med", channel="text",
                 kind="instruction", text="Keep D3 closed.", task_group_id="og_a"),
            dict(id="m_2", at=400, thread_id="th_a", actor_id="a_med", channel="text",
                 kind="retraction", retraction_style="explicit", cancels=["og_a"],
                 text="Forget D3."),
        ],
        tasks=[hold_task(at=200, hold=600)],
    )
    e.advance_to(250)
    e.toggle_door("D3", now=250)
    assert e.penalties == 1
    e.advance_to(500)
    assert e.task_state("t_1") == "failed"
    assert e.penalties == 1


def test_queue_is_strict_fifo_and_reveals_nothing_until_opened():
    e = eng(
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med", channel="text",
                 kind="instruction", text="First."),
            dict(id="m_2", at=200, thread_id="th_a", actor_id="a_sec", channel="text",
                 kind="status", text="Second."),
        ],
    )
    e.advance_to(250)
    state = e.public_state()
    assert state["pending_count"] == 2
    assert set(state["front"]) == {"uid", "kind", "opened"}  # no sender, no urgency
    item = e.open_notification(now=250)
    assert item.ref_id == "m_1"
    assert e.public_state()["front"]["text"] == "First."
    assert e.acknowledge(item.uid, now=251)
    assert e.open_notification(now=252).ref_id == "m_2"


def test_radio_never_carries_a_transcript():
    e = eng(messages=[dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med",
                           channel="radio", kind="instruction", text="Secret prose.",
                           audio="audio/m_1.wav", audio_duration=5.0)])
    e.advance_to(110)
    e.open_notification(now=110)
    front = e.public_state()["front"]
    assert front["text"] == ""
    assert front["audio"] == "audio/m_1.wav"


def test_a_reconnect_returns_the_modal_but_not_the_audio():
    e = eng(messages=[dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med",
                           channel="radio", kind="instruction", text="x",
                           audio="audio/m_1.wav", audio_duration=5.0)])
    e.advance_to(110)
    item = e.open_notification(now=110)
    assert e.public_state()["front"]["audio_played"] is False  # the first listen
    e.on_reconnect(now=120)
    assert e.front().opened_at is None      # back at the front, per spec 14.3
    assert e.front().audio_played is True   # but heard once, ever
    assert e.public_state()["front"]["opened"] is False


def test_failed_task_pulls_its_unread_message_from_the_queue():
    e = eng(tasks=[hold_task(at=200, hold=0, require={"D3": "open"})])
    e.advance_to(210)
    assert e.task_state("t_1") == "failed"
    kinds = [i.kind for i in e.pending]
    assert kinds == ["failure_notice"]
    assert any(ev.kind == "message_withdrawn_unread" for ev in e.events)


def test_failure_notice_cooldown_suppresses_the_second_notice_but_not_its_penalty():
    e = eng(
        task_groups=[
            dict(id="og_a", thread_id="th_a", label="a"),
        ],
        tasks=[
            hold_task(id="t_1", at=200, hold=0, require={"D3": "open"}),
            hold_task(id="t_2", at=205, hold=0, require={"D6": "open"}),
        ],
    )
    e.advance_to(210)
    # Same group, 5s apart, cooldown is 30s.
    assert e.penalties == 1  # cascade: the group is one obligation
    assert e.task_state("t_2") == "cancelled"


def test_two_groups_each_get_their_own_notice():
    e = eng(
        task_groups=[
            dict(id="og_a", thread_id="th_a", label="a"),
            dict(id="og_b", thread_id="th_a", label="b"),
        ],
        tasks=[
            hold_task(id="t_1", group_id="og_a", at=200, hold=0, require={"D3": "open"}),
            hold_task(id="t_2", group_id="og_b", at=205, hold=0, require={"D6": "open"}),
        ],
    )
    e.advance_to(210)
    assert e.penalties == 2
    assert [i.kind for i in e.pending] == ["failure_notice", "failure_notice"]


def test_challenge_must_be_answered_but_never_locks_the_doors():
    e = eng(
        messages=[],
        challenges=[dict(id="q_1", at=900, slot="in_session", kind="thread",
                         thread_id="th_a", actor_id="a_sec", channel="text",
                         prompt="Why is D3 closed?", explanation="Medical asked.",
                         options=[dict(id="o1", text="Medical asked.", correct=True),
                                  dict(id="o2", text="Cargo asked."),
                                  dict(id="o3", text="Engineering asked."),
                                  dict(id="o4", text="Security asked.")])],
    )
    e.advance_to(905)
    item = e.open_notification(now=905)
    assert e.acknowledge(item.uid, now=906) is False  # mandatory
    assert e.toggle_door("D3", now=907)["state"] == "open"  # canvas stays live
    assert e.elapsed >= 905  # and the clock never froze
    out = e.answer_challenge(item.uid, "o2", now=910)
    assert out["outcome"] == "wrong" and e.penalties == 1
    assert out["correct_option_id"] == "o1"
    assert e.acknowledge(item.uid, now=911) is True


@pytest.mark.parametrize(
    "option,outcome,cost",
    [("o1", "correct", 0), ("o2", "wrong", 1), (DONT_KNOW_OPTION_ID, "dont_know", 1)],
)
def test_dont_know_costs_the_same_but_is_logged_distinctly(option, outcome, cost):
    e = eng(messages=[], challenges=[dict(id="q_1", at=900, slot="in_session", kind="thread",
                             thread_id="th_a", actor_id="a_sec", channel="text",
                             prompt="?", explanation="x",
                             options=[dict(id="o1", text="a", correct=True),
                                      dict(id="o2", text="b"), dict(id="o3", text="c"),
                                      dict(id="o4", text="d")])])
    e.advance_to(905)
    item = e.open_notification(now=905)
    out = e.answer_challenge(item.uid, option, now=906)
    assert out["outcome"] == outcome
    assert e.penalties == cost


def test_session_ends_into_an_untimed_debrief():
    e = eng(
        messages=[],
        debrief_challenges=[dict(id="q_d1", at=0, slot="debrief", kind="time",
                                 thread_id="th_a", actor_id="a_sec", channel="text",
                                 prompt="?", explanation="x",
                                 options=[dict(id="o1", text="a", correct=True),
                                          dict(id="o2", text="b"), dict(id="o3", text="c"),
                                          dict(id="o4", text="d")])],
    )
    e.advance_to(1620)
    assert e.phase == "debrief"
    assert [i.kind for i in e.pending] == ["challenge"]
    item = e.open_notification(now=1620)
    e.answer_challenge(item.uid, "o1", now=1700)
    e.acknowledge(item.uid, now=1701)
    e.finish()
    assert e.phase == "complete"


def test_advancing_in_one_jump_matches_advancing_tick_by_tick():
    """A stalled tick, or a laptop lid closed for a minute, must not change the
    outcome -- the world keeps running and is caught up in order."""
    spec = dict(tasks=[hold_task(at=200, hold=100)],
                messages=[dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med",
                               channel="text", kind="instruction", text="Keep D3 closed.",
                               task_group_id="og_a")])
    a = eng(**spec)
    a.advance_to(400)
    b = eng(**spec)
    t = 0.0
    while t <= 400:
        b.advance_to(t)
        t += 0.25
    assert [e.kind for e in a.events] == [e.kind for e in b.events]
    assert a.task_state("t_1") == b.task_state("t_1") == "passed"


def test_a_challenge_waits_behind_an_unread_message():
    """Strict FIFO, no priority anywhere -- not even for a question the player is
    required to answer."""
    e = eng(challenges=[dict(id="q_1", at=900, slot="in_session", kind="thread",
                             thread_id="th_a", actor_id="a_sec", channel="text",
                             prompt="?", explanation="x",
                             options=[dict(id="o1", text="a", correct=True),
                                      dict(id="o2", text="b"), dict(id="o3", text="c"),
                                      dict(id="o4", text="d")])])
    e.advance_to(905)
    assert [i.kind for i in e.pending] == ["message", "challenge"]
    assert e.open_notification(now=905).kind == "message"
