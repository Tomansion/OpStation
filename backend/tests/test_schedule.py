"""The scheduler's promises.

Everything here is a property the generator relies on: the model is allowed to
write colliding, over-long, badly spaced obligations, and the scenario that comes
out the other side must still be playable.
"""
from opstation.config import difficulty as load_difficulty
from opstation.generate.assemble import assemble
from opstation.generate.plan import BeatSpec, GroupSpec, Plan, TaskSpec, ThreadSpec
from opstation.generate.schedule import MAX_HOLD_FRACTION, Scheduler
from opstation.station import station as load_station
from opstation.validator import validate
from opstation.validator.simulate import simulate

DURATION = 1620


def beat(key, thread, phase, group, tasks, **over):
    return BeatSpec(
        key=f"{thread}:{key}", thread_key=thread, phase=phase,
        actor_type=over.pop("actor", "cargo"), channel="text",
        kind=over.pop("kind", "instruction"),
        text=over.pop("text", f"Door Control. Instruction {key} for the record."),
        creates_group=group, tasks=tasks, **over,
    )


def plan_with(threads) -> Plan:
    return Plan(
        name="Scheduler fixture", duration_seconds=DURATION,
        actor_names={t: t.title() for t in
                     ("security", "construction", "cargo", "medical", "civilian", "system")},
        threads=threads,
    )


def test_a_head_on_collision_is_resolved():
    """Two threads demanding opposite states on D7 over the same window is what
    parallel thread-writing produces. It must not survive into the scenario."""
    a = ThreadSpec(key="a", title="A", catalogue_key="k", grade="ordinary", debrief_summary="")
    b = ThreadSpec(key="b", title="B", catalogue_key="k", grade="finale", debrief_summary="")
    a.groups = [GroupSpec("a_hold", "a", "Hold D7 closed")]
    b.groups = [GroupSpec("b_open", "b", "Hold D7 open")]
    a.beats = [beat("b1", "a", 2, "a_hold",
                    [TaskSpec(hold=400, fail_message="x", require={"D7": "closed"})])]
    b.beats = [beat("b1", "b", 2, "b_open",
                    [TaskSpec(hold=400, fail_message="y", require={"D7": "open"})])]
    plan = plan_with([a, b])

    Scheduler(plan, load_difficulty(), load_station()).run()
    scenario, _ = assemble(plan, station=load_station(), scenario_id="sc_x")
    sim = simulate(scenario, load_station())
    assert sim.conflicts == []
    assert sim.solvable


def test_absurd_holds_are_capped():
    a = ThreadSpec(key="a", title="A", catalogue_key="k", grade="finale", debrief_summary="")
    a.groups = [GroupSpec("a_hold", "a", "Hold")]
    a.beats = [beat("b1", "a", 1, "a_hold",
                    [TaskSpec(hold=3600, fail_message="x", require={"D3": "closed"})])]
    plan = plan_with([a])
    schedule = Scheduler(plan, load_difficulty(), load_station()).run()
    holds = [hold for _at, hold in schedule.task_times.values()]
    assert max(holds) <= int(MAX_HOLD_FRACTION * DURATION)


def test_no_obligation_outlives_the_session():
    a = ThreadSpec(key="a", title="A", catalogue_key="k", grade="finale", debrief_summary="")
    a.groups = [GroupSpec("a_hold", "a", "Hold")]
    a.beats = [
        beat(f"b{i}", "a", 5, "a_hold",
             [TaskSpec(hold=480, fail_message="x", require={"D3": "closed"})])
        for i in range(1, 6)
    ]
    plan = plan_with([a])
    schedule = Scheduler(plan, load_difficulty(), load_station()).run()
    for key, (at, hold) in schedule.task_times.items():
        if key in schedule.dropped_tasks:
            continue
        assert at + hold <= DURATION, f"{at}+{hold} runs past the session"


def test_messages_keep_their_minimum_spacing():
    """Retractions and temptations are placed by where they must land, not by the
    running cursor, so spacing is enforced afterwards."""
    a = ThreadSpec(key="a", title="A", catalogue_key="k", grade="finale", debrief_summary="")
    a.groups = [GroupSpec("a_hold", "a", "Hold D3 closed")]
    a.beats = [
        beat("b1", "a", 2, "a_hold",
             [TaskSpec(hold=400, fail_message="x", require={"D3": "closed"})]),
        beat("b2", "a", 2, None, [], kind="retraction",
             text="Forget the D3 restriction.", cancels=["a_hold"]),
        beat("b3", "a", 2, None, [], kind="status", text="Nothing further from us."),
    ]
    plan = plan_with([a])
    Scheduler(plan, load_difficulty(), load_station()).run()
    times = sorted(b.at for b in plan.beats if b.at is not None)
    gap = load_difficulty()["min_message_gap_seconds"]
    assert all(b - a >= gap for a, b in zip(times, times[1:])), times


def test_the_shift_ends_with_the_station_sealed():
    a = ThreadSpec(key="a", title="A", catalogue_key="k", grade="finale", debrief_summary="")
    a.groups = [GroupSpec("a_hold", "a", "Hold")]
    a.beats = [beat("b1", "a", 1, "a_hold",
                    [TaskSpec(hold=200, fail_message="x", require={"D3": "closed"})])]
    plan = plan_with([a])
    scenario, _ = assemble(plan, station=load_station(), scenario_id="sc_seal")
    hangars = {d.id for d in load_station().hangar_doors}

    last = max(scenario.tasks, key=lambda t: (t.at + t.hold, t.at))
    required = {}
    for task in scenario.tasks_of_group(last.group_id):
        required.update(task.require)
    assert hangars <= set(required)
    assert all(state == "closed" for door, state in required.items() if door in hangars)

    report = validate(scenario)
    assert "V21" not in {f.rule for f in report.errors}


def test_a_derived_task_gets_its_doors_from_the_graph():
    """The model names a place; the cut-set comes from the map. The Hangar Bay 3
    bypass means the service sector needs D9 as well as D7, and nobody has to
    remember that."""
    a = ThreadSpec(key="a", title="A", catalogue_key="k", grade="finale", debrief_summary="")
    a.groups = [GroupSpec("a_seal", "a", "Seal the service sector")]
    a.beats = [beat("b1", "a", 3, "a_seal",
                    [TaskSpec(hold=300, fail_message="x", isolation_target="service_sector",
                              include_hangar_doors=True)],
                    text="Engineering. Seal the service sector until we find the leak.")]
    plan = plan_with([a])
    scenario, _ = assemble(plan, station=load_station(), scenario_id="sc_derived")
    derived = next(t for t in scenario.tasks if t.derived_from)
    assert derived.require == {"D7": "closed", "D9": "closed", "H4": "closed", "H5": "closed"}
    report = validate(scenario)
    assert "V23" not in {f.rule for f in report.errors}
    assert "V25" not in {f.rule for f in report.errors}


def test_the_scheduler_is_idempotent():
    """The scheduler runs several times over one plan -- once to find obligation
    windows for the temptation stage, once for the challenge stage, once at
    assembly. If a run mutated the plan, the third run would see a different
    scenario from the first, and the effects would compound. This caught a real
    bug where withdrawals were demoted a second time and vanished entirely."""
    def build():
        t = ThreadSpec(key="a", title="A", catalogue_key="k", grade="finale",
                       debrief_summary="")
        t.groups = [GroupSpec("a_hold", "a", "Hold D3 closed")]
        t.beats = [
            beat("b1", "a", 2, "a_hold",
                 [TaskSpec(hold=300, fail_message="x", require={"D3": "closed"})],
                 actor="medical", text="Medical. Hold D3 closed for the ward."),
            beat("b2", "a", 3, None, [], actor="medical", kind="retraction",
                 text="Forget the D3 hold.", cancels=["a_hold"],
                 retraction_style="explicit"),
        ]
        return plan_with([t])

    plan = build()
    seen = []
    for _ in range(3):
        for b in plan.beats:
            b.at = None if b.pin_at is None else b.pin_at
        schedule = Scheduler(plan, load_difficulty(), load_station()).run()
        seen.append((
            sorted(b.kind for b in plan.beats),
            sorted(schedule.demoted_retractions),
            sorted(schedule.task_times.values()),
        ))
    assert seen[0] == seen[1] == seen[2]


def test_a_withdrawal_lands_inside_what_it_withdraws():
    """V26 rejects a retraction that cancels nothing still pending, so it must
    land inside a live window or not be a retraction at all. A short obligation
    offers no room, and the scheduler has to notice rather than place the
    withdrawal after its target already expired."""
    for hold in (0, 5, 30, 120, 400):
        t = ThreadSpec(key="a", title="A", catalogue_key="k", grade="finale",
                       debrief_summary="")
        t.groups = [GroupSpec("a_hold", "a", "Hold D3 closed")]
        t.beats = [
            beat("b1", "a", 2, "a_hold",
                 [TaskSpec(hold=hold, fail_message="x", require={"D3": "closed"})],
                 actor="medical", text="Medical. Hold D3 closed."),
            beat("b2", "a", 3, None, [], actor="medical", kind="retraction",
                 text="Forget the D3 hold.", cancels=["a_hold"],
                 retraction_style="explicit"),
        ]
        plan = plan_with([t])
        schedule = Scheduler(plan, load_difficulty(), load_station()).run()
        retraction = next(b for b in plan.beats if b.kind == "retraction")
        at, held = next(iter(schedule.task_times.values()))
        if retraction.key in schedule.demoted_retractions:
            assert held < 20, f"hold {hold}s had room but was demoted anyway"
        else:
            assert at <= retraction.at <= at + held, (
                f"hold {hold}s: withdrawal at {retraction.at} is outside [{at},{at + held}]"
            )


def busy_plan(threads=6, beats_per_thread=8) -> Plan:
    """A plan of the shape the LLM actually produces: several threads, long
    holds, overlapping doors, crossings, and a withdrawal."""
    doors = ["D1", "D3", "D6", "D7", "D10", "D12", "D13", "H2", "H4", "H5"]
    specs = []
    for t in range(threads):
        key = f"t{t}"
        thread = ThreadSpec(key=key, title=f"Thread {t}", catalogue_key="k",
                            grade="finale" if t == 0 else "ordinary", debrief_summary="")
        thread.groups = [GroupSpec(f"{key}_g{i}", key, f"Obligation {i}")
                         for i in range(beats_per_thread)]
        for i in range(beats_per_thread):
            door = doors[(t * 3 + i) % len(doors)]
            state = "closed" if (t + i) % 3 else "open"
            thread.beats.append(beat(
                f"b{i}", key, min(5, 1 + i * 5 // beats_per_thread), f"{key}_g{i}",
                [TaskSpec(hold=[0, 60, 200, 480][i % 4], fail_message=f"fail {t}.{i}",
                          require={door: state})],
                actor=["security", "cargo", "medical", "civilian", "construction"][i % 5],
                text=f"Door Control. Hold {door} {state} for thread {t}, item {i}.",
            ))
        thread.beats.append(beat(
            "bx", key, 3, None, [], kind="retraction", actor="cargo",
            text=f"Cancel what I asked on thread {t}.", cancels=[f"{key}_g1"],
            retraction_style="explicit",
        ))
        specs.append(thread)
    return plan_with(specs)


def test_a_busy_plan_still_satisfies_every_arithmetic_rule():
    """The scheduler's whole job. These rules are pure arithmetic, so they must
    hold by construction whatever the model wrote."""
    plan = busy_plan()
    plan.challenges = []
    scenario, _ = assemble(plan, station=load_station(), scenario_id="sc_busy")
    report = validate(scenario)
    arithmetic = {"V2", "V3", "V7", "V9", "V10", "V13", "V14", "V23"}
    broken = sorted({f.rule for f in report.errors} & arithmetic)
    assert not broken, "\n".join(
        str(f) for f in report.errors if f.rule in arithmetic
    )
    assert report.simulation["solvable"]


def test_a_busy_plan_keeps_its_withdrawals_answerable():
    """Every retraction that survives must land inside something it cancels."""
    plan = busy_plan()
    scenario, schedule = assemble(plan, station=load_station(), scenario_id="sc_busy2")
    report = validate(scenario)
    assert "V26" not in {f.rule for f in report.errors}, "\n".join(
        str(f) for f in report.errors if f.rule == "V26"
    )


def test_the_beat_parser_survives_shape_variation():
    """Models are inconsistent about singular-or-list and string-or-number. A
    generation run that dies on the shape of one field throws away every call
    that came before it, so the parser coerces rather than raises."""
    from opstation.generate.plan import BeatSpec

    parsed = BeatSpec.parse({
        "key": ["b1"], "phase": "2", "actor": "cargo",
        "creates": ["og_x", "og_y"], "cancels": "og_z",
        "tasks": {"hold": "300", "delay": 15.0, "require": {"d7": "CLOSED"},
                  "fail_message": "  spaced  "},
        "text": "Cargo here.",
    }, "th")
    assert parsed.key == "b1" and parsed.phase == 2
    assert parsed.creates_group == "og_x"
    assert parsed.cancels == ["og_z"]
    assert parsed.tasks[0].require == {"D7": "closed"}
    assert parsed.tasks[0].hold == 300 and parsed.tasks[0].delay == 15
    assert parsed.tasks[0].fail_message == "spaced"


def test_a_nonsense_door_state_is_dropped_not_kept():
    from opstation.generate.plan import TaskSpec as TS

    parsed = TS.parse({"hold": 60, "require": {"D7": "ajar", "D8": "open"},
                       "fail_message": "x"})
    assert parsed.require == {"D8": "open"}
