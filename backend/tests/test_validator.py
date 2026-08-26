"""Validator rules. Each test names the rule it pins down, and several use the
spec's own worked examples so the document and the code cannot drift apart."""
from conftest import make_scenario

from opstation.validator import validate


def rules_fired(scenario) -> set[str]:
    return {f.rule for f in validate(scenario).errors}


def test_a_task_cannot_precede_the_message_that_creates_it():
    sc = make_scenario(tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=50,
                                  hold=0, require={"D3": "closed"}, fail_message="x")])
    assert "V3" in rules_fired(sc)


def test_unknown_door_is_rejected():
    sc = make_scenario(tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200,
                                  hold=0, require={"D14": "closed"}, fail_message="x")])
    assert "V4" in rules_fired(sc)


def test_task_must_leave_time_to_read_its_message():
    """V7: a message the player has not had time to read cannot carry an
    obligation. read_cost of this text plus 10s slack lands after at=105."""
    sc = make_scenario(tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=105,
                                  hold=0, require={"D3": "open"}, fail_message="x")])
    assert "V7" in rules_fired(sc)


def test_messages_too_close_together():
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med", channel="text",
             kind="instruction", text="One."),
        dict(id="m_2", at=103, thread_id="th_a", actor_id="a_sec", channel="text",
             kind="status", text="Two."),
    ])
    assert "V9" in rules_fired(sc)


def test_hold_window_may_not_outlive_the_session():
    sc = make_scenario(tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=1600,
                                  hold=100, require={"D3": "closed"}, fail_message="x")])
    assert "V10" in rules_fired(sc)


def test_contradictory_overlap_is_unsolvable():
    """V13 + V14: the spec's 6.4 example, broken. Two live obligations demand
    opposite states on D3 at the same moment."""
    sc = make_scenario(tasks=[
        dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=30,
             require={"D3": "open"}, fail_message="x"),
        dict(id="t_2", group_id="og_a", message_id="m_1", at=220, hold=0,
             require={"D3": "closed"}, fail_message="y"),
    ])
    fired = rules_fired(sc)
    assert "V13" in fired


def test_the_specs_own_crossing_example_is_solvable():
    sc = make_scenario(tasks=[
        dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=30,
             require={"D3": "open"}, fail_message="You didn't have D3 open."),
        dict(id="t_2", group_id="og_a", message_id="m_1", at=240, hold=0,
             require={"D3": "closed"}, fail_message="You didn't close D3 afterwards."),
    ])
    report = validate(sc)
    assert "V13" not in {f.rule for f in report.errors}
    assert "V14" not in {f.rule for f in report.errors}
    assert report.simulation["solvable"]


def test_already_satisfied_instruction_is_a_silent_free_pass():
    """V15: D3 starts closed, so "close D3 now" asks for nothing."""
    sc = make_scenario(tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200,
                                  hold=0, require={"D3": "closed"}, fail_message="x")])
    assert "V15" in rules_fired(sc)


def test_holding_an_already_correct_state_is_exempt_from_v15():
    sc = make_scenario(tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200,
                                  hold=300, require={"D3": "closed"}, fail_message="x")])
    assert "V15" not in rules_fired(sc)


def test_redundant_re_requirement_inside_one_group():
    sc = make_scenario(tasks=[
        dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=60,
             require={"D3": "open"}, fail_message="x"),
        dict(id="t_2", group_id="og_a", message_id="m_1", at=400, hold=60,
             require={"D3": "open"}, fail_message="y"),
    ])
    assert "V16" in rules_fired(sc)


def test_a_temptation_with_no_live_hold_is_just_noise():
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_med", channel="text",
             kind="instruction", text="Keep D3 closed.", task_group_id="og_a"),
        dict(id="m_2", at=200, thread_id="th_a", actor_id="a_civ2", channel="text",
             kind="tempting_request", text="Could you open D6 for me?"),
    ])
    assert "V17" in rules_fired(sc)


def test_a_real_temptation_passes_v17():
    sc = make_scenario(
        threads=[
            dict(id="th_a", title="Medical hold", catalogue_key="k", grade="ordinary",
                 phase_span=(1, 5), debrief_summary="s"),
            dict(id="th_b", title="Resident traffic", catalogue_key="k2", grade="ordinary",
                 phase_span=(1, 5), debrief_summary="s"),
        ],
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Keep D3 closed.", task_group_id="og_a"),
            dict(id="m_2", at=300, thread_id="th_b", actor_id="a_civilian", channel="text",
                 kind="tempting_request",
                 text="Door Control, can you open D3? My colleague is waiting inside."),
        ],
        tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=600,
                    require={"D3": "closed"}, fail_message="x")],
    )
    assert "V17" not in rules_fired(sc)


def test_derived_task_must_match_the_graph_exactly():
    """V23 with the spec's own 6.8 example. The service sector cut is D7+D9 --
    the Hangar Bay 3 bypass is what puts D9 there."""
    def with_require(require):
        return make_scenario(tasks=[dict(
            id="t_1", group_id="og_a", message_id="m_1", at=200, hold=300,
            require=require, fail_message="x",
            derived_from=dict(isolation_target="service_sector", include_hangar_doors=True),
        )])

    good = {"D7": "closed", "D9": "closed", "H4": "closed", "H5": "closed"}
    assert "V23" not in rules_fired(with_require(good))
    # One door short: the plausible answer that leaves the back route open.
    assert "V23" in rules_fired(with_require({"D7": "closed", "H4": "closed", "H5": "closed"}))
    # Interior doors must never be required.
    assert "V23" in rules_fired(with_require(good | {"D10": "closed"}))


def test_derived_task_must_be_named_in_its_message():
    sc = make_scenario(
        messages=[dict(id="m_1", at=100, thread_id="th_a", actor_id="a_engineering",
                       channel="text", kind="instruction",
                       text="Close it up down there, would you.", task_group_id="og_a")],
        tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=300,
                    require={"D7": "closed", "D9": "closed"}, fail_message="x",
                    derived_from=dict(isolation_target="service_sector"))],
    )
    assert "V25" in rules_fired(sc)


def test_unsealable_target_is_rejected():
    sc = make_scenario(tasks=[dict(
        id="t_1", group_id="og_a", message_id="m_1", at=200, hold=300,
        require={"D7": "closed"}, fail_message="x",
        derived_from=dict(isolation_target="STO"),
    )])
    assert "V24" in rules_fired(sc)


def test_retraction_of_something_already_finished_is_a_no_op():
    sc = make_scenario(
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Keep D3 closed for five minutes.",
                 task_group_id="og_a"),
            dict(id="m_2", at=900, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="retraction", retraction_style="explicit", cancels=["og_a"],
                 text="Forget the D3 restriction."),
        ],
        tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=100,
                    require={"D3": "closed"}, fail_message="x")],
    )
    assert "V26" in rules_fired(sc)


def test_retraction_with_no_teeth_is_decoration():
    sc = make_scenario(
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Keep D3 closed.", task_group_id="og_a"),
            dict(id="m_2", at=400, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="retraction", retraction_style="explicit", cancels=["og_a"],
                 text="Forget the D3 restriction."),
        ],
        tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=600,
                    require={"D3": "closed"}, fail_message="x")],
    )
    assert "V29" in rules_fired(sc)


def test_retraction_backed_by_an_opposite_state_task_has_teeth():
    sc = make_scenario(
        task_groups=[dict(id="og_a", thread_id="th_a", label="Keep D3 closed"),
                     dict(id="og_b", thread_id="th_a", label="Open D3 for transfer")],
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Keep D3 closed.", task_group_id="og_a"),
            dict(id="m_2", at=400, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="retraction", retraction_style="explicit", cancels=["og_a"],
                 text="Forget the D3 restriction."),
            dict(id="m_3", at=600, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Open D3 now for the patient transfer.",
                 task_group_id="og_b"),
        ],
        tasks=[
            dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=600,
                 require={"D3": "closed"}, fail_message="x"),
            dict(id="t_2", group_id="og_b", message_id="m_3", at=650, hold=60,
                 require={"D3": "open"}, fail_message="y"),
        ],
    )
    assert "V29" not in rules_fired(sc)


def test_cross_actor_retraction_must_name_the_other_actor():
    sc = make_scenario(
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Keep D3 closed.", task_group_id="og_a"),
            dict(id="m_2", at=400, thread_id="th_a", actor_id="a_security", channel="text",
                 kind="retraction", retraction_style="cross_actor", cancels=["og_a"],
                 text="That D3 restriction is no longer needed."),
        ],
        tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=600,
                    require={"D3": "closed"}, fail_message="x")],
    )
    assert "V28" in rules_fired(sc)


def test_no_immediate_re_imposition():
    sc = make_scenario(
        task_groups=[dict(id="og_a", thread_id="th_a", label="Keep D3 closed"),
                     dict(id="og_b", thread_id="th_a", label="Keep D3 closed again")],
        messages=[
            dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Keep D3 closed.", task_group_id="og_a"),
            dict(id="m_2", at=400, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="retraction", retraction_style="explicit", cancels=["og_a"],
                 text="Forget the D3 restriction."),
            dict(id="m_3", at=420, thread_id="th_a", actor_id="a_medical", channel="text",
                 kind="instruction", text="Actually keep D3 closed after all.",
                 task_group_id="og_b"),
        ],
        tasks=[
            dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=600,
                 require={"D3": "closed"}, fail_message="x"),
            dict(id="t_2", group_id="og_b", message_id="m_3", at=460, hold=60,
                 require={"D3": "closed"}, fail_message="y"),
        ],
    )
    assert "V31" in rules_fired(sc)


def test_invented_places_are_rejected():
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
             kind="instruction", text="Seal Hangar Bay 9 and clear Deck 4."),
    ])
    assert "V32" in rules_fired(sc)


def test_station_version_must_match(station):
    sc = make_scenario(station_version="v1")
    assert "V33" in rules_fired(sc)


def test_a_scenario_with_no_tasks_is_rejected():
    assert "V14" in rules_fired(make_scenario())


def test_idioms_and_slang_are_rejected():
    """V35: most players are not native speakers and a spoken message is heard
    once, so reading difficulty is a confound rather than a style preference."""
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_construction", channel="radio",
             kind="instruction", text="Door Control. Vent starts in two mikes, keep an eye on D13."),
    ])
    assert "V35" in rules_fired(sc)


def test_plain_terse_prose_passes_v35():
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_construction", channel="radio",
             kind="instruction", text="Door Control, Construction. Close D13 now. "
                                     "It stays closed until I clear it."),
    ])
    assert "V35" not in rules_fired(sc)


def test_a_very_long_sentence_is_rejected():
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_medical", channel="text",
             kind="instruction",
             text="Door Control, this is Medical speaking to you now about the patient "
                  "in the Medical Bay who came in through Hangar Bay 1 earlier and who "
                  "we now believe may have been exposed to something we cannot yet "
                  "identify, so please keep D3 closed."),
    ])
    assert "V35" in rules_fired(sc)


def test_a_time_question_may_answer_with_durations():
    """V19's distractor rule is about the option set, not every option: a "how
    long" question has durations for answers, and "twelve hours" is a plausible
    wrong answer rather than generic filler."""
    sc = make_scenario(
        tasks=[dict(id="t_1", group_id="og_a", message_id="m_1", at=200, hold=300,
                    require={"D3": "closed"}, fail_message="x")],
        challenges=[dict(
            id="q_1", at=900, slot="in_session", kind="time", thread_id="th_a",
            actor_id="a_security", channel="text", pretext="Writing the report.",
            prompt="How long was the Medical Bay sealed?",
            options=[dict(id="o1", text="Five minutes.", correct=True),
                     dict(id="o2", text="Twelve hours."), dict(id="o3", text="Two days."),
                     dict(id="o4", text="Thirty seconds.")],
            explanation="Five minutes, from 00:03.", depends_on=["m_1"],
        )],
    )
    findings = [f for f in validate(sc).errors if f.rule == "V19"]
    assert not findings, findings


def test_a_message_may_not_introduce_itself_as_somebody_else():
    """A voice is the only cue that identifies a speaker, and that is what makes
    provenance answerable. A message spoken by one actor while introducing itself
    as another destroys it."""
    sc = make_scenario(messages=[
        dict(id="m_1", at=100, thread_id="th_a", actor_id="a_construction", channel="radio",
             kind="instruction",
             text="Officer Ruiz. Close D12 now."),
    ], actors=[
        dict(id=f"a_{t}", type=t, name=n, portrait=f"{t}.png", voice=t)
        for t, n in (("security", "Officer Kade Ruiz"), ("construction", "Foreman Eli Voss"),
                     ("cargo", "Chen"), ("medical", "Dr Zhao"),
                     ("civilian", "Morrow"), ("system", "Station Control"))
    ])
    assert "V6" in rules_fired(sc)


def test_a_cross_actor_withdrawal_is_attributed():
    from opstation.generate.pipeline import _attribute_to

    assert _attribute_to("Forget what I said about D12.", "construction") == \
        "Forget what Construction said about D12."
    assert _attribute_to("Forget my earlier instruction on D3.", "medical") == \
        "Forget Medical's earlier instruction on D3."
    # Nothing to attribute: left alone rather than mangled.
    assert _attribute_to("Stand down on the vent hold.", "cargo") == \
        "Stand down on the vent hold."
