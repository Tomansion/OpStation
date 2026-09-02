"""Turn a scheduled Plan into a Scenario.

Everything mechanical happens here, so the LLM never has to get it right:
sequential ids, sorted messages, `read_cost`, derived `require` maps computed
from the door graph, the difficulty fingerprint, and the end-of-shift sealing
obligation that V21 demands.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..config import Difficulty, Voices, difficulty as load_difficulty, voices as load_voices
from ..models import (
    Actor, Challenge, DerivedFrom, GeneratorInfo, Message, Option, Scenario, Task, TaskGroup, Thread,
)
from ..station import Station, door_sort_key
from .plan import BeatSpec, Plan, TaskSpec
from .schedule import Schedule, Scheduler

SEAL_GROUP_KEY = "og_end_of_shift"

#: The set of message kinds is closed (spec 11.1), but models reach for words
#: outside it -- "confirmation" for a release, "alert" for a status. Mapping them
#: is better than rejecting the scenario over a synonym, and better than widening
#: the enum: `kind` is load-bearing for the admin page and for V17.
KIND_SYNONYMS = {
    "confirmation": "resolution",
    "confirm": "resolution",
    "clear": "resolution",
    "clearance": "resolution",
    "release": "resolution",
    "closed": "resolution",
    "complete": "resolution",
    "alert": "status",
    "warning": "status",
    "info": "status",
    "notice": "status",
    "report": "status",
    "request": "tempting_request",
    "escalation": "update",
    "correction": "supersede",
}


#: Challenge kinds are a closed set too (spec 8.3). Same reasoning as message
#: kinds: the admin page and the "one of each per group of three" target read it.
CHALLENGE_KIND_SYNONYMS = {
    "withdrawn": "provenance",
    "retraction": "provenance",
    "source": "provenance",
    "authority": "provenance",
    "who": "provenance",
    "chronology": "time",
    "timing": "time",
    "duration": "time",
    "when": "time",
    "status": "thread",
    "state": "thread",
    "event": "thread",
    "incident": "thread",
}


def _challenge_kind(raw: str) -> str:
    from ..config import CHALLENGE_KINDS

    kind = (raw or "thread").strip().lower()
    if kind in CHALLENGE_KINDS:
        return kind
    return CHALLENGE_KIND_SYNONYMS.get(kind, "thread")


def _kind(raw: str) -> str:
    from ..config import MESSAGE_KINDS

    kind = (raw or "status").strip().lower()
    if kind in MESSAGE_KINDS:
        return kind
    return KIND_SYNONYMS.get(kind, "status")


def assemble(
    plan: Plan,
    *,
    station: Station,
    difficulty: Difficulty | None = None,
    voices: Voices | None = None,
    scenario_id: str,
    model: str = "",
    seed: int | None = None,
    attempts: int = 0,
    language: str = "en",
) -> tuple[Scenario, Schedule]:
    diff = difficulty or load_difficulty()
    voice_map = voices or load_voices(language)

    _ensure_end_of_shift_seal(plan, station)
    schedule = Scheduler(plan, diff, station).run()

    actors = _actors(plan, voice_map)
    actor_id = {a.type: a.id for a in actors}

    used_threads = {b.thread_key for b in plan.beats if b.at is not None}
    threads = [
        Thread(
            id=_thread_id(t.key),
            title=t.title,
            catalogue_key=t.catalogue_key,
            grade=t.grade,
            phase_span=t.phase_span,
            debrief_summary=t.debrief_summary,
        )
        for t in plan.threads
        if t.key in used_threads
    ]
    used_groups = {
        b.creates_group for b in plan.beats
        if b.at is not None and b.creates_group
    }
    groups = [
        TaskGroup(id=_group_id(g.key), thread_id=_thread_id(g.thread_key), label=g.label)
        for g in plan.groups
        if g.key in used_groups and g.thread_key in used_threads
    ]

    # Messages get their ids from their position on the finished timeline, so
    # m_012 is always the twelfth thing the player hears.
    ordered = sorted(
        (b for b in plan.beats if b.at is not None), key=lambda b: (b.at, b.thread_key, b.key)
    )
    message_id: dict[str, str] = {}
    messages: list[Message] = []
    for index, beat in enumerate(ordered, start=1):
        mid = f"m_{index:03d}"
        message_id[beat.key] = mid
        # A withdrawal the scheduler could not keep becomes ordinary traffic:
        # `cancels` only belongs on a retraction (spec 11.1), and one that
        # cancels nothing is invisible to the player anyway.
        demoted = beat.key in schedule.demoted_retractions
        messages.append(
            Message(
                id=mid,
                at=int(beat.at),
                thread_id=_thread_id(beat.thread_key),
                actor_id=actor_id.get(beat.actor_type, actors[0].id),
                channel=beat.channel if beat.channel in ("text", "radio") else "text",
                kind="status" if demoted else _kind(beat.kind),
                text=beat.text,
                task_group_id=_group_id(beat.creates_group) if beat.creates_group else None,
                cancels=[] if demoted else [_group_id(c) for c in beat.cancels],
                retraction_style=None if demoted else beat.retraction_style,
                read_cost=diff.read_cost(beat.text) if beat.channel == "text" else None,
            )
        )

    tasks: list[Task] = []
    counter = 0
    implicit: dict[str, TaskGroup] = {}
    for beat in ordered:
        for spec in beat.tasks:
            if id(spec) in schedule.dropped_tasks or id(spec) not in schedule.task_times:
                continue
            at, hold = schedule.task_times[id(spec)]
            counter += 1
            # A beat with tasks but no declared obligation gets its own group.
            # Falling back to the sealing group would put an unrelated task on
            # the finale thread and break V3 and V21 together.
            group_key = beat.creates_group
            if not group_key:
                group_key = f"{beat.thread_key}_implicit_{beat.key.split(':')[-1]}"
                if group_key not in implicit:
                    implicit[group_key] = TaskGroup(
                        id=_group_id(group_key),
                        thread_id=_thread_id(beat.thread_key),
                        label=f"Unnamed obligation from {beat.key}",
                    )
            tasks.append(
                Task(
                    id=f"t_{counter:03d}",
                    group_id=_group_id(group_key),
                    message_id=message_id[beat.key],
                    at=at,
                    hold=hold,
                    require=_require_for(spec, station),
                    fail_message=spec.fail_message,
                    confirm=(hold == 0 and spec.delay == 0),
                    derived_from=(
                        DerivedFrom(
                            isolation_target=spec.isolation_target,
                            include_hangar_doors=spec.include_hangar_doors,
                        )
                        if spec.isolation_target
                        else None
                    ),
                )
            )

    groups += list(implicit.values())
    challenges = [
        _challenge(c, actor_id, actors, message_id, plan, index)
        for index, c in enumerate(plan.challenges, start=1)
    ]

    scenario = Scenario(
        scenario_id=scenario_id,
        name=plan.name,
        duration_seconds=plan.duration_seconds,
        station_version=station.version,
        language=language,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        generator=GeneratorInfo(model=model, template_version="1", seed=seed, attempts=attempts),
        difficulty_fingerprint=diff.validator_fingerprint(),
        actors=actors,
        threads=threads,
        task_groups=groups,
        messages=messages,
        tasks=tasks,
        challenges=[c for c in challenges if c.slot == "in_session"],
        debrief_challenges=[c for c in challenges if c.slot == "debrief"],
    )
    return scenario, schedule


# --------------------------------------------------------------------- pieces

def _thread_id(key: str) -> str:
    return key if key.startswith("th_") else f"th_{key}"


def _group_id(key: str | None) -> str:
    if key is None:
        return ""
    return key if key.startswith("og_") else f"og_{key}"


def _actors(plan: Plan, voices: Voices) -> list[Actor]:
    from ..config import ACTOR_TYPES

    return [
        Actor(
            id=f"a_{t}",
            type=t,
            name=plan.actor_names.get(t) or t.title(),
            portrait=f"{t}.png",
            voice=voices.voice_for(t),
            speaker=voices.speaker_for(t),
        )
        for t in ACTOR_TYPES
    ]


def _require_for(spec: TaskSpec, station: Station) -> dict[str, str]:
    """A derived task's doors come from the graph, not from the LLM. This is
    what makes V23 a tautology at generation time and a real check afterwards,
    if the map ever changes."""
    if spec.seal_station:
        return {d.id: "closed" for d in sorted(station.hangar_doors, key=lambda x: door_sort_key(x.id))}
    if spec.isolation_target and spec.isolation_target in station.isolation_targets:
        cut = station.target_cut(spec.isolation_target)
        return cut.required(spec.include_hangar_doors)
    return {k: v for k, v in sorted(spec.require.items(), key=lambda kv: door_sort_key(kv[0]))}


def _challenge(spec, actor_id, actors, message_id, plan: Plan, index: int) -> Challenge:
    options = [
        Option(id=f"o{i}", text=str(o.get("text", "")).strip(), correct=bool(o.get("correct")))
        for i, o in enumerate(spec.options, start=1)
    ]
    depends = [
        message_id[d] if d in message_id else _group_id(d) if plan.group(d) else d
        for d in spec.depends_on
    ]
    return Challenge(
        id=f"q_{index:03d}",
        at=int(spec.at or 0),
        slot=spec.slot,
        kind=_challenge_kind(spec.kind),
        thread_id=_thread_id(spec.thread_key),
        actor_id=actor_id.get(spec.actor_type, actors[0].id),
        channel=spec.channel if spec.channel in ("text", "radio") else "text",
        prompt=spec.prompt,
        options=options,
        explanation=spec.explanation,
        pretext=spec.pretext or None,
        depends_on=depends,
    )


def _seal_pin(plan: Plan, hold: int, read_cost: float, slack: int) -> int:
    """Where the sealing beat must sit for its window to close last."""
    from .schedule import SEAL_TAIL

    return max(0, plan.duration_seconds - SEAL_TAIL - hold - int(read_cost) - slack - 1)


def _ensure_end_of_shift_seal(plan: Plan, station: Station) -> None:
    """V21: the shift ends with an explicit obligation to seal every hangar door.

    Structural, so it is guaranteed rather than requested. If the finale thread
    already wrote a sealing beat, that one is used and its `require` map is
    replaced with the real hangar-door set.
    """
    from .plan import BeatSpec, GroupSpec, TaskSpec

    from ..config import difficulty as _difficulty

    diff = _difficulty()
    existing = [b for b in plan.beats if any(t.seal_station for t in b.tasks)]
    if existing:
        # Keep exactly one. Two sealing beats in different threads would put the
        # sealing group on one thread and its message on another (V3), and would
        # leave V21 looking at whichever happened to end last.
        finale_key = next((t.key for t in plan.threads if t.grade == "finale"), None)
        keeper = next((b for b in existing if b.thread_key == finale_key), existing[-1])
        for beat in existing:
            if beat is keeper:
                continue
            beat.tasks = [t for t in beat.tasks if not t.seal_station]
        hold = max((t.hold for t in keeper.tasks if t.seal_station), default=90)
        keeper.phase = 5
        keeper.pin_at = _seal_pin(
            plan, hold, diff.read_cost(keeper.text),
            int(diff["task_slack_after_message_seconds"]),
        )
        keeper.tasks = [t for t in keeper.tasks if t.seal_station]
        keeper.creates_group = SEAL_GROUP_KEY
        thread = plan.thread_of(keeper.thread_key)
        if thread and not any(g.key == SEAL_GROUP_KEY for g in thread.groups):
            thread.groups.append(
                GroupSpec(
                    key=SEAL_GROUP_KEY,
                    thread_key=keeper.thread_key,
                    label="Station sealed for end of shift",
                )
            )
        return

    finale = next((t for t in plan.threads if t.grade == "finale"), None)
    if finale is None:
        finale = plan.threads[0]
    finale.groups.append(
        GroupSpec(key=SEAL_GROUP_KEY, thread_key=finale.key,
                  label="Station sealed for end of shift")
    )
    seal_text = (
        "END OF SHIFT PROTOCOL. Confirm every hangar door — H1, H2, H3, H4 and "
        "H5 — is closed and remains closed for handover."
    )
    finale.beats.append(
        BeatSpec(
            key="b_end_of_shift",
            pin_at=_seal_pin(
                plan, 90, diff.read_cost(seal_text),
                int(diff["task_slack_after_message_seconds"]),
            ),
            thread_key=finale.key,
            phase=5,
            actor_type="system",
            channel="text",
            kind="instruction",
            text=seal_text,
            creates_group=SEAL_GROUP_KEY,
            tasks=[
                TaskSpec(
                    hold=90,
                    seal_station=True,
                    fail_message=(
                        "HANDOVER REJECTED — a hangar door was open at end of shift. "
                        "The station was left unsealed."
                    ),
                )
            ],
        )
    )
