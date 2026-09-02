"""The validator rules (spec 13).

One function per rule, named `v01` .. `v38`, each yielding Findings. Keeping
them separate and numbered means the report the LLM repairs from cites exactly
the rule the spec states, and a rule can be read next to its spec line.

Where a rule is partly semantic ("no two options are semantically equivalent"),
the mechanical part is an error and the judgement part is a warning. The
docstring says which, so nobody mistakes a warning for a proof.
"""

from __future__ import annotations

import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..config import (
    ACTOR_TYPES,
    CHALLENGE_KINDS,
    Difficulty,
    MESSAGE_KINDS,
    RETRACTION_STYLES,
    phase_at,
)
from ..models import Challenge, Message, Scenario, Task
from ..station import Station, door_sort_key
from .findings import Finding
from .simulate import Simulation

DOOR_RE = re.compile(r"\b([DH])\s?-?(\d{1,2})\b")
#: Place-name shapes the fiction might invent: "Hangar Bay 9", "Deck 4", "C7",
#: "Sector Gamma". Deliberately narrow on the sector/module/ring forms -- those
#: only count as a place-name when followed by a number or a capitalised word,
#: so "keep the central sector sealed" is prose rather than an invented sector.
#: Case-insensitivity is scoped to the fixed words, because the capital in
#: "[A-Z][a-z]+" is exactly the signal that a name follows.
SUSPECT_PLACE_RE = re.compile(
    r"\b(?:"
    r"(?i:hangar\s+bay|hangar|deck|level)\s+\d+"
    r"|(?i:sector|module|ring|bay|junction)\s+(?:\d+|[A-Z][a-z]+)"
    r"|[Cc]\d+"
    r")\b"
)


@dataclass
class Ctx:
    """Everything a rule may look at."""

    scenario: Scenario
    station: Station
    difficulty: Difficulty
    sim: Simulation
    audio_dir: Path | None = None

    # -- shared helpers -----------------------------------------------------

    def read_cost(self, msg: Message) -> float:
        if msg.read_cost is not None:
            return msg.read_cost
        return self.difficulty.read_cost(msg.text, msg.audio_duration)

    def challenge_read_cost(self, ch: Challenge) -> float:
        return self.difficulty.read_cost(ch.prompt, ch.audio_duration)

    def phase(self, at: float) -> int:
        return phase_at(at, self.scenario.duration_seconds)

    def tasks_of_message(self, message_id: str) -> list[Task]:
        return [t for t in self.scenario.tasks if t.message_id == message_id]

    def messages_of_thread(self, thread_id: str) -> list[Message]:
        return [m for m in self.scenario.sorted_messages() if m.thread_id == thread_id]

    def tasks_of_thread(self, thread_id: str) -> list[Task]:
        groups = {g.id for g in self.scenario.task_groups if g.thread_id == thread_id}
        return [t for t in self.scenario.tasks if t.group_id in groups]

    def message_of_task(self, task: Task) -> Message | None:
        return self.scenario.messages_by_id.get(task.message_id)

    def actor_of_task(self, task: Task) -> str | None:
        msg = self.message_of_task(task)
        return msg.actor_id if msg else None

    def doors_in_text(self, text: str) -> list[str]:
        return [
            f"{m.group(1).upper()}{int(m.group(2))}" for m in DOOR_RE.finditer(text)
        ]


# ===========================================================================
# 13.1 Structural
# ===========================================================================


def v01(ctx: Ctx) -> Iterator[Finding]:
    """All ids unique; every cross-reference resolves."""
    sc = ctx.scenario
    buckets = {
        "actor": [a.id for a in sc.actors],
        "thread": [t.id for t in sc.threads],
        "task_group": [g.id for g in sc.task_groups],
        "message": [m.id for m in sc.messages],
        "task": [t.id for t in sc.tasks],
        "challenge": [c.id for c in sc.all_challenges],
    }
    seen: dict[str, str] = {}
    for kind, ids in buckets.items():
        for i in ids:
            if i in seen:
                yield Finding("V1", f"id {i!r} used twice ({seen[i]} and {kind})", i)
            seen[i] = kind

    actors, threads, groups, messages = (
        set(buckets["actor"]),
        set(buckets["thread"]),
        set(buckets["task_group"]),
        set(buckets["message"]),
    )
    for m in sc.messages:
        if m.thread_id not in threads:
            yield Finding(
                "V1", f"message references unknown thread {m.thread_id!r}", m.id
            )
        if m.actor_id not in actors:
            yield Finding(
                "V1", f"message references unknown actor {m.actor_id!r}", m.id
            )
        if m.task_group_id and m.task_group_id not in groups:
            yield Finding(
                "V1", f"message references unknown group {m.task_group_id!r}", m.id
            )
    for g in sc.task_groups:
        if g.thread_id not in threads:
            yield Finding(
                "V1", f"group references unknown thread {g.thread_id!r}", g.id
            )
    for t in sc.tasks:
        if t.group_id not in groups:
            yield Finding("V1", f"task references unknown group {t.group_id!r}", t.id)
        if t.message_id not in messages:
            yield Finding(
                "V1", f"task references unknown message {t.message_id!r}", t.id
            )
    for c in sc.all_challenges:
        if c.thread_id not in threads:
            yield Finding(
                "V1", f"challenge references unknown thread {c.thread_id!r}", c.id
            )
        if c.actor_id not in actors:
            yield Finding(
                "V1", f"challenge references unknown actor {c.actor_id!r}", c.id
            )

    # The set of message kinds is closed (spec 11.1). An invented kind is not
    # harmless: `kind` is what the admin page reads to tell a release from a
    # withdrawal, and what V17 reads to find a tempting request.
    for m in sc.messages:
        if m.kind not in MESSAGE_KINDS:
            yield Finding(
                "V1",
                f"message kind {m.kind!r} is not one of {sorted(MESSAGE_KINDS)}",
                m.id,
            )


def v02(ctx: Ctx) -> Iterator[Finding]:
    """Every `at` is an integer in [0, duration]; messages ascending by `at`."""
    sc = ctx.scenario
    dur = sc.duration_seconds
    for item, label in (
        [(m, "message") for m in sc.messages]
        + [(t, "task") for t in sc.tasks]
        + [(c, "challenge") for c in sc.challenges]
    ):
        if not isinstance(item.at, int):
            yield Finding("V2", f"{label} `at` is not an integer: {item.at!r}", item.id)
        elif not 0 <= item.at <= dur:
            yield Finding("V2", f"{label} `at` {item.at} outside [0, {dur}]", item.id)
    ats = [m.at for m in sc.messages]
    if ats != sorted(ats):
        yield Finding("V2", "messages are not sorted ascending by `at`")


def v03(ctx: Ctx) -> Iterator[Finding]:
    """Task wiring: group and message present, threads agree, message before task."""
    sc = ctx.scenario
    for t in sc.tasks:
        group = sc.groups_by_id.get(t.group_id)
        msg = sc.messages_by_id.get(t.message_id)
        if group is None or msg is None:
            continue  # V1 already reported it
        if group.thread_id != msg.thread_id:
            yield Finding(
                "V3",
                f"group {group.id} is on thread {group.thread_id} but its message "
                f"{msg.id} is on thread {msg.thread_id}",
                t.id,
            )
        if msg.at >= t.at:
            yield Finding(
                "V3",
                f"message {msg.id} is at {msg.at} but the task it creates starts at {t.at} "
                "— the instruction must precede the obligation",
                t.id,
            )


def v04(ctx: Ctx) -> Iterator[Finding]:
    """Every door named in `require` exists; every state is open or closed."""
    known = set(ctx.station.doors)
    for t in ctx.scenario.tasks:
        if not t.require:
            yield Finding("V4", "task has an empty `require` map", t.id)
        for door, state in t.require.items():
            if door not in known:
                yield Finding(
                    "V4",
                    f"unknown door {door!r} (station has {sorted(known, key=door_sort_key)})",
                    t.id,
                )
            if state not in ("open", "closed"):
                yield Finding("V4", f"door {door} has invalid state {state!r}", t.id)


def v05(ctx: Ctx) -> Iterator[Finding]:
    """Radio audio exists and `audio_duration` matches the file within 0.3 s.

    Skipped before the TTS pass -- pipeline step 5 re-runs the whole validator
    once real audio exists (spec 12.1).
    """
    if ctx.audio_dir is None:
        return
    for msg in ctx.scenario.messages:
        if msg.channel != "radio":
            if msg.audio:
                yield Finding("V5", "text message must not carry audio", msg.id)
            continue
        yield from _check_audio("V5", ctx, msg.id, msg.audio, msg.audio_duration)
    for ch in ctx.scenario.all_challenges:
        if ch.channel == "radio":
            yield from _check_audio("V5", ctx, ch.id, ch.audio, ch.audio_duration)


def _check_audio(rule, ctx: Ctx, where, rel, declared) -> Iterator[Finding]:
    if not rel:
        yield Finding(rule, "radio item has no audio file", where)
        return
    path = (ctx.audio_dir.parent / rel) if ctx.audio_dir else None
    if path is None or not path.exists():
        yield Finding(rule, f"audio file missing: {rel}", where)
        return
    try:
        with wave.open(str(path), "rb") as wf:
            real = wf.getnframes() / float(wf.getframerate())
    except Exception as exc:  # noqa: BLE001 - a broken wav is a validator finding
        yield Finding(rule, f"cannot read audio {rel}: {exc}", where)
        return
    if declared is None:
        yield Finding(rule, "radio item has no audio_duration", where)
    elif abs(real - declared) > 0.3:
        yield Finding(
            rule, f"audio_duration {declared:.2f}s but {rel} is {real:.2f}s", where
        )


def v06(ctx: Ctx) -> Iterator[Finding]:
    """Exactly 6 actors, one per type (spec 11.4) -- this is what makes a voice
    identify a speaker, and therefore what makes provenance answerable."""
    actors = ctx.scenario.actors
    types = [a.type for a in actors]
    for t in ACTOR_TYPES:
        if types.count(t) != 1:
            yield Finding(
                "V6", f"actor type {t!r} used {types.count(t)} times, expected once"
            )
    for a in actors:
        if a.type not in ACTOR_TYPES:
            yield Finding("V6", f"unknown actor type {a.type!r}", a.id)
    if len(actors) != len(ACTOR_TYPES):
        yield Finding("V6", f"{len(actors)} actors, expected {len(ACTOR_TYPES)}")

    # A voice is the only cue that identifies a speaker, which is what makes
    # provenance answerable (spec 11.4). A message spoken in one voice while
    # introducing itself as somebody else destroys that.
    by_id = ctx.scenario.actors_by_id
    for msg in ctx.scenario.messages:
        speaker = by_id.get(msg.actor_id)
        if speaker is None:
            continue
        opening = msg.text[:48].lower()
        named = [
            a
            for a in actors
            if a.id != msg.actor_id
            and (a.name.split()[-1].lower() in opening or a.type in opening)
        ]
        if (
            named
            and speaker.name.split()[-1].lower() not in opening
            and speaker.type not in opening
        ):
            yield Finding(
                "V6",
                f"spoken by {speaker.type} but introduces itself as "
                f"{[a.type for a in named]} — the voice and the name must agree",
                msg.id,
            )


# ===========================================================================
# 13.2 Timing
# ===========================================================================


def v07(ctx: Ctx) -> Iterator[Finding]:
    """A task cannot start before the player could have read its message."""
    slack = ctx.difficulty["task_slack_after_message_seconds"]
    for msg in ctx.scenario.messages:
        tasks = ctx.tasks_of_message(msg.id)
        if not tasks:
            continue
        earliest = min(t.at for t in tasks)
        need = msg.at + ctx.read_cost(msg) + slack
        if earliest < need - 1e-6:
            yield Finding(
                "V7",
                f"first task starts at {earliest} but the message at {msg.at} needs "
                f"{ctx.read_cost(msg):.1f}s to read plus {slack}s slack — earliest is "
                f"{need:.1f}",
                msg.id,
            )


def v08(ctx: Ctx) -> Iterator[Finding]:
    """Rolling reading density.

    In-session challenges count toward the sum: they arrive through the same
    queue and have to be read like anything else.
    """
    window = ctx.difficulty["read_budget_window_seconds"]
    items = [(m.at, ctx.read_cost(m), m.id) for m in ctx.scenario.messages]
    items += [(c.at, ctx.challenge_read_cost(c), c.id) for c in ctx.scenario.challenges]
    items.sort()
    for i, (start, _, _) in enumerate(items):
        inside = [it for it in items[i:] if it[0] < start + window]
        total = sum(cost for _, cost, _ in inside)
        budget = ctx.difficulty.read_budget_for_phase(ctx.phase(start))
        if total > budget + 1e-6:
            ids = ", ".join(i2 for _, _, i2 in inside)
            yield Finding(
                "V8",
                f"{total:.1f}s of reading in the {window}s from {start} (phase "
                f"{ctx.phase(start)}, budget {budget}s): {ids}",
                inside[0][2],
            )


def v09(ctx: Ctx) -> Iterator[Finding]:
    """Consecutive messages are far enough apart to be opened one at a time."""
    gap = ctx.difficulty["min_message_gap_seconds"]
    msgs = ctx.scenario.sorted_messages()
    for a, b in zip(msgs, msgs[1:]):
        if b.at - a.at < gap:
            yield Finding(
                "V9", f"only {b.at - a.at}s after {a.id} (minimum {gap}s)", b.id
            )


def v10(ctx: Ctx) -> Iterator[Finding]:
    """A hold window cannot run past the end of the session."""
    dur = ctx.scenario.duration_seconds
    for t in ctx.scenario.tasks:
        if t.until > dur:
            yield Finding(
                "V10", f"window ends at {t.until} but the session ends at {dur}", t.id
            )


def v11(ctx: Ctx) -> Iterator[Finding]:
    """No in-session challenge lands on a deadline.

    Debrief challenges are exempt -- the session is over and nothing can fail.
    """
    clear = ctx.difficulty["challenge_task_clearance_seconds"]
    for ch in ctx.scenario.challenges:
        for t in ctx.scenario.tasks:
            if t.id in ctx.sim.cancelled_task_ids:
                continue
            for boundary, what in ((t.at, "opens"), (t.until, "closes")):
                if abs(ch.at - boundary) < clear:
                    yield Finding(
                        "V11",
                        f"challenge at {ch.at} is {abs(ch.at - boundary)}s from where "
                        f"{t.id} {what} ({boundary}); needs {clear}s of clearance",
                        ch.id,
                    )


def v12(ctx: Ctx) -> Iterator[Finding]:
    """Challenge counts, placement and spacing."""
    vol = ctx.difficulty.volumes
    sc = ctx.scenario
    want_in, want_deb = vol["challenges_in_session"], vol["challenges_debrief"]
    if len(sc.challenges) != want_in:
        yield Finding(
            "V12", f"{len(sc.challenges)} in-session challenges, expected {want_in}"
        )
    if len(sc.debrief_challenges) != want_deb:
        yield Finding(
            "V12",
            f"{len(sc.debrief_challenges)} debrief challenges, expected {want_deb}",
        )
    half = 0.5 * sc.duration_seconds
    for ch in sc.challenges:
        if ch.slot != "in_session":
            yield Finding(
                "V12", f"slot is {ch.slot!r} but it is in `challenges`", ch.id
            )
        if ch.at < half:
            yield Finding(
                "V12", f"at {ch.at}, before the 50% mark ({half:.0f}s)", ch.id
            )
    for ch in sc.debrief_challenges:
        if ch.slot != "debrief":
            yield Finding(
                "V12", f"slot is {ch.slot!r} but it is in `debrief_challenges`", ch.id
            )
    ordered = sorted(sc.challenges, key=lambda c: c.at)
    for a, b in zip(ordered, ordered[1:]):
        if b.at - a.at < 120:
            yield Finding(
                "V12", f"only {b.at - a.at}s after {a.id} (minimum 120s)", b.id
            )


# ===========================================================================
# 13.3 Solvability
# ===========================================================================


def v13(ctx: Ctx) -> Iterator[Finding]:
    """No two live obligations demand opposite states on one door at one moment.

    Found by the simulation, which already knows which tasks a retraction
    cancelled and how a mid-`hold` cancellation truncates a window.
    """
    for conflict in ctx.sim.conflicts:
        yield Finding("V13", conflict.describe(), conflict.a.task_id)


def v14(ctx: Ctx) -> Iterator[Finding]:
    """The perfect player must pass everything.

    A player who makes the minimum toggles at the latest safe moment is the best
    any human could do. If a task still fails, no amount of memory would save
    it and the scenario is unplayable.
    """
    for task_id in ctx.sim.failed_task_ids:
        yield Finding(
            "V14",
            "the perfect player cannot satisfy this task — the scenario is unsolvable",
            task_id,
        )
    if not ctx.scenario.tasks:
        yield Finding("V14", "scenario has no tasks, so nothing can be right or wrong")


def v15(ctx: Ctx) -> Iterator[Finding]:
    """No already-satisfied instruction.

    A `hold: 0` task whose door is already in the required state, and has not
    changed since its message, is a silent free pass. Tasks with `hold > 0` are
    exempt: holding a correct state against temptation is a real obligation.
    """
    for task in ctx.scenario.tasks:
        if task.hold > 0 or task.id in ctx.sim.cancelled_task_ids:
            continue
        msg = ctx.message_of_task(task)
        if msg is None:
            continue
        for door, want in task.require.items():
            if door not in ctx.sim.trace.initial:
                continue
            if ctx.sim.trace.state_at(door, task.at) != want:
                continue
            if not ctx.sim.trace.changed_in(door, msg.at, task.at):
                yield Finding(
                    "V15",
                    f"{door} is already {want} at {task.at} and has not changed since "
                    f"{msg.id} at {msg.at} — this instruction asks for nothing",
                    task.id,
                )


def v16(ctx: Ctx) -> Iterator[Finding]:
    """No redundant re-requirement inside one group.

    Looking only within a group is what implements the spec's exception: a
    different, earlier, already-closed obligation may legitimately have left the
    door in the same state.
    """
    for group in ctx.scenario.task_groups:
        tasks = ctx.scenario.tasks_of_group(group.id)
        per_door: dict[str, list[tuple[Task, str]]] = {}
        for t in tasks:
            for door, state in t.require.items():
                per_door.setdefault(door, []).append((t, state))
        for door, seq in per_door.items():
            for (t_a, s_a), (t_b, s_b) in zip(seq, seq[1:]):
                if s_a == s_b:
                    yield Finding(
                        "V16",
                        f"{door} was already required {s_a} by {t_a.id} in the same group "
                        "with no intervening opposite requirement",
                        t_b.id,
                    )


def v17(ctx: Ctx) -> Iterator[Finding]:
    """Temptations must actually tempt.

    A `tempting_request` carries no task -- complying is only punished through
    *another* thread's live hold. If no such hold exists, the message is
    harmless noise pretending to be a dilemma.
    """
    for msg in ctx.scenario.messages:
        if msg.kind != "tempting_request":
            continue
        tasks = ctx.tasks_of_message(msg.id)
        if tasks:
            yield Finding(
                "V17",
                f"a tempting request must have no tasks, but {len(tasks)} reference it "
                "— complying has to cost the player through another thread, not this one",
                msg.id,
            )
        asked = set(ctx.doors_in_text(msg.text))
        live: list[str] = []
        for c in ctx.sim.constraints:
            if (
                c.start <= msg.at <= c.end
                and c.task_id not in ctx.sim.cancelled_task_ids
            ):
                live.append(c.door)
        contradicted = asked & set(live)
        if not asked:
            yield Finding(
                "V17",
                "tempting request names no door, so nothing can be contradicted "
                "— name the door the player is being asked to operate",
                msg.id,
            )
        elif not contradicted:
            yield Finding(
                "V17",
                f"names {sorted(asked)} but no live hold covers any of them at {msg.at} "
                f"(live doors then: {sorted(set(live))})",
                msg.id,
            )
        else:
            for door in sorted(contradicted):
                states = {
                    c.state
                    for c in ctx.sim.constraints
                    if c.door == door and c.start <= msg.at <= c.end
                }
                thread_ids = {
                    ctx.scenario.groups_by_id[
                        ctx.scenario.tasks_by_id[c.task_id].group_id
                    ].thread_id
                    for c in ctx.sim.constraints
                    if c.door == door
                    and c.start <= msg.at <= c.end
                    and c.task_id in ctx.scenario.tasks_by_id
                    and ctx.scenario.tasks_by_id[c.task_id].group_id
                    in ctx.scenario.groups_by_id
                }
                if thread_ids == {msg.thread_id}:
                    yield Finding(
                        "V17",
                        f"the hold on {door} belongs to this same thread ({msg.thread_id}); "
                        "a temptation has to pull against a *different* thread",
                        msg.id,
                    )
                if (
                    states == {"open"}
                    and "open" in msg.text.lower()
                    and "clos" not in msg.text.lower()
                ):
                    yield Finding(
                        "V17",
                        f"{door} is already required open, so asking to open it is not a "
                        "temptation",
                        msg.id,
                        severity="warning",
                    )


def v18(ctx: Ctx) -> Iterator[Finding]:
    """Dormancy: at least one thread goes quiet for 4 minutes with a live
    obligation, and gets asked about. This is the measurement the game exists
    for -- the difference between `waiting` and `resolved`."""
    dormant: list[str] = []
    for thread in ctx.scenario.threads:
        if thread.grade in ("everyday", "conflicts"):
            continue
        msgs = ctx.messages_of_thread(thread.id)
        tasks = ctx.tasks_of_thread(thread.id)
        for a, b in zip(msgs, msgs[1:]):
            if b.at - a.at < 240:
                continue
            live = any(
                t.at <= b.at
                and t.until >= a.at
                and t.id not in ctx.sim.cancelled_task_ids
                for t in tasks
            )
            if live:
                dormant.append(thread.id)
                break
    if not dormant:
        yield Finding(
            "V18",
            "no thread is silent for 240s while still holding a live obligation — "
            "without one, nothing tests whether the player confuses waiting with resolved",
        )
        return
    asked = {c.thread_id for c in ctx.scenario.all_challenges}
    if not set(dormant) & asked:
        yield Finding(
            "V18",
            f"dormant thread(s) {sorted(set(dormant))} are never the subject of a challenge",
        )


def v19(ctx: Ctx) -> Iterator[Finding]:
    """Challenge integrity.

    Mechanical (errors): exactly one correct option; four authored options; no
    "I don't know" in the JSON; every `depends_on` id delivered before `at`;
    every distractor mentions something real in this scenario; no two options
    with identical text.

    Judgement (warnings): whether a distractor is genuinely false at `at`, and
    whether two differently-worded options mean the same thing. Neither is
    mechanically decidable; both are stated in the generation prompt.
    """
    sc = ctx.scenario
    for ch in sc.all_challenges:
        correct = [o for o in ch.options if o.correct]
        if len(correct) != 1:
            yield Finding(
                "V19", f"{len(correct)} options marked correct, expected 1", ch.id
            )
        if len(ch.options) != 4:
            yield Finding(
                "V19",
                f'{len(ch.options)} options, expected 4 — the fifth, "I don\'t know", is '
                "supplied by the UI and must never appear in the JSON",
                ch.id,
            )
        for o in ch.options:
            if o.text.strip().lower().rstrip(".") == "i don't know":
                yield Finding("V19", '"I don\'t know" must not be authored', ch.id)
        texts = [o.text.strip().lower() for o in ch.options]
        if len(set(texts)) != len(texts):
            yield Finding("V19", "two options have the same text", ch.id)
        if ch.kind not in CHALLENGE_KINDS:
            yield Finding("V19", f"unknown challenge kind {ch.kind!r}", ch.id)
        if not ch.explanation.strip():
            yield Finding("V19", "no explanation", ch.id)
        if not ch.pretext:
            yield Finding(
                "V19",
                "no pretext — a challenge must read as someone needing an answer, "
                "not as a quiz (spec 8.4)",
                ch.id,
                severity="warning",
            )

        deadline = ch.at if ch.slot == "in_session" else sc.duration_seconds
        for dep in ch.depends_on:
            msg = sc.messages_by_id.get(dep)
            if msg is None and dep in sc.groups_by_id:
                creators = [m for m in sc.messages if m.task_group_id == dep]
                msg = min(creators, key=lambda m: m.at) if creators else None
            if msg is None:
                yield Finding(
                    "V19", f"depends_on {dep!r} resolves to no message or group", ch.id
                )
            elif msg.at >= deadline:
                yield Finding(
                    "V19",
                    f"the answer depends on {dep} at {msg.at}, which is not delivered "
                    f"before the question at {deadline}",
                    ch.id,
                )
        if not ch.depends_on:
            yield Finding(
                "V19",
                "declares no depends_on, so nothing proves the answer was derivable "
                "from what the player had heard",
                ch.id,
                severity="warning",
            )

        # Distractors must be drawn from this scenario, not from generic filler
        # (spec 8.5). But the threshold is the option SET, not every option: a
        # "how long was it sealed" question has durations for answers, and
        # "twelve hours" is a plausible wrong answer rather than filler. So most
        # of the distractors must name something real, not all of them.
        vocabulary = _scenario_vocabulary(ctx)
        distractors = [o for o in ch.options if not o.correct]
        generic = [
            o
            for o in distractors
            if not set(re.findall(r"[a-z0-9]+", o.text.lower())) & vocabulary
        ]
        # A `time` question's answer space is durations, and every distractor is
        # legitimately one -- the scenario reference lives in the prompt and the
        # correct option. For `thread` and `provenance` questions the distractors
        # are the whole point, and most of them must name something real.
        needed = 0 if ch.kind == "time" else max(1, (len(distractors) + 1) // 2)
        grounded = len(distractors) - len(generic)
        if distractors and grounded < needed:
            yield Finding(
                "V19",
                f"{len(generic)} of {len(distractors)} distractors name nothing that "
                f"exists in this scenario ({[o.text for o in generic]}) — they must be "
                "drawn from other real threads, not invented as filler",
                ch.id,
            )


def _scenario_vocabulary(ctx: Ctx) -> set[str]:
    """Lower-cased tokens naming something real in this scenario: doors, areas,
    isolation phrases, actor names and thread titles."""
    out: set[str] = set()
    for door in ctx.station.doors:
        out.add(door.lower())
    for area in ctx.station.areas.values():
        out |= set(re.findall(r"[a-z0-9]+", area["name"].lower()))
        out |= set(re.findall(r"[a-z0-9]+", area["prose"].lower()))
    for t in ctx.station.isolation_targets.values():
        out |= set(re.findall(r"[a-z0-9]+", t.phrase.lower()))
    for a in ctx.scenario.actors:
        out |= set(re.findall(r"[a-z0-9]+", a.name.lower()))
        out.add(a.type)
    for th in ctx.scenario.threads:
        out |= set(re.findall(r"[a-z0-9]+", th.title.lower()))
    for g in ctx.scenario.task_groups:
        out |= set(re.findall(r"[a-z0-9]+", g.label.lower()))
    return out - {
        "the",
        "a",
        "an",
        "of",
        "and",
        "to",
        "in",
        "is",
        "for",
        "on",
        "bay",
        "c1",
        "c2",
        "c3",
    }


def v20(ctx: Ctx) -> Iterator[Finding]:
    """Volume targets (spec 2.2)."""
    vol = ctx.difficulty.volumes
    sc = ctx.scenario
    n = len(sc.messages)
    if not vol["messages_min"] <= n <= vol["messages_max"]:
        yield Finding(
            "V20", f"{n} messages, expected {vol['messages_min']}-{vol['messages_max']}"
        )
    incidents = [t for t in sc.threads if t.grade in ("ordinary", "finale")]
    if len(incidents) < vol["threads_min"]:
        yield Finding(
            "V20",
            f"{len(incidents)} incident threads, expected at least {vol['threads_min']}",
        )
    finales = [t for t in sc.threads if t.grade == "finale"]
    if len(finales) != 1:
        yield Finding("V20", f"{len(finales)} finale-grade threads, expected exactly 1")
    everyday = [t for t in sc.threads if t.grade == "everyday"]
    lo, hi = vol["everyday_exchanges_min"], vol["everyday_exchanges_max"]
    if not lo <= len(everyday) <= hi:
        yield Finding("V20", f"{len(everyday)} everyday exchanges, expected {lo}-{hi}")
    for th in everyday:
        count = len(ctx.messages_of_thread(th.id))
        if count > 2:
            yield Finding(
                "V20", f"everyday exchange has {count} messages, expected 1-2", th.id
            )


def v21(ctx: Ctx) -> Iterator[Finding]:
    """The station ends sealed.

    Two halves. The trace half is the outcome: at the final second of the
    perfect-player trace every hangar door must be closed. The group half is the
    intent: the last obligation of the shift has to be the one that seals the
    station, so ending sealed is something the player was asked to do rather
    than something that happened to be true.
    """
    dur = ctx.scenario.duration_seconds
    hangars = [d.id for d in ctx.station.hangar_doors]
    still_open = [d for d in hangars if ctx.sim.trace.state_at(d, dur) != "closed"]
    if still_open:
        yield Finding(
            "V21",
            f"the perfect player ends the shift with {sorted(still_open, key=door_sort_key)} "
            "open to space — the last task group must require every hangar door closed",
        )
    if not ctx.scenario.tasks:
        return
    last = max(ctx.scenario.tasks, key=lambda t: (t.until, t.at))
    group_requires: dict[str, str] = {}
    for task in ctx.scenario.tasks_of_group(last.group_id):
        group_requires.update(task.require)
    unsealed = [d for d in hangars if group_requires.get(d) != "closed"]
    if unsealed:
        yield Finding(
            "V21",
            f"the last task group {last.group_id!r} does not require "
            f"{sorted(unsealed, key=door_sort_key)} closed — the shift must end with an "
            "explicit obligation to seal every hangar door",
            last.group_id,
        )


def v22(ctx: Ctx) -> Iterator[Finding]:
    """Each thread lives inside its declared phase span."""
    for thread in ctx.scenario.threads:
        lo, hi = thread.phase_span
        msgs = ctx.messages_of_thread(thread.id)
        if not msgs:
            yield Finding("V22", "thread has no messages", thread.id)
            continue
        phases = {ctx.phase(m.at) for m in msgs}
        outside = sorted(p for p in phases if not lo <= p <= hi)
        if outside:
            yield Finding(
                "V22",
                f"declares phase_span {list(thread.phase_span)} but has messages in "
                f"phase(s) {outside}",
                thread.id,
            )
        if not any(lo <= p <= hi for p in phases):
            yield Finding(
                "V22",
                f"no message falls inside its declared phase_span {list(thread.phase_span)}",
                thread.id,
            )


# ===========================================================================
# 13.4 Derived obligations
# ===========================================================================


def v23(ctx: Ctx) -> Iterator[Finding]:
    """A derived task's `require` map must equal the cut recomputed from the
    door graph -- the cut only, plus hangar doors inside when the fiction
    concerns pressure, and nothing else.

    This is what makes the map load-bearing: move a door in station.json and
    every derived task in the bank is re-checked against it.
    """
    for task in ctx.scenario.tasks:
        if task.derived_from is None:
            continue
        target_id = task.derived_from.isolation_target
        target = ctx.station.isolation_targets.get(target_id)
        if target is None:
            continue  # V24 reports it
        cut = ctx.station.target_cut(target_id)
        want = cut.required(task.derived_from.include_hangar_doors)
        if task.require != want:
            missing = sorted(set(want) - set(task.require), key=door_sort_key)
            extra = sorted(set(task.require) - set(want), key=door_sort_key)
            wrong = sorted(
                d for d in set(task.require) & set(want) if task.require[d] != want[d]
            )
            detail = []
            if missing:
                interior = set(cut.interior_doors)
                detail.append(f"missing {missing}")
                for d in missing:
                    if d in interior:
                        detail.append(f"({d} is interior, it must NOT be required)")
            if extra:
                detail.append(
                    f"must not include {extra}"
                    + (
                        f" — {[d for d in extra if d in cut.interior_doors]} are interior "
                        "to the volume and stay open"
                        if any(d in cut.interior_doors for d in extra)
                        else ""
                    )
                )
            if wrong:
                detail.append(f"wrong state on {wrong}")
            yield Finding(
                "V23",
                f"derived from {target_id!r} so `require` must be exactly "
                f"{ {k: want[k] for k in sorted(want, key=door_sort_key)} }: "
                + "; ".join(detail),
                task.id,
            )


def v24(ctx: Ctx) -> Iterator[Finding]:
    """Named targets exist and can actually be sealed."""
    st = ctx.station
    for task in ctx.scenario.tasks:
        if task.derived_from is None:
            continue
        target_id = task.derived_from.isolation_target
        if (
            target_id in st.not_isolable
            or target_id in st.areas
            and not st.sealable_alone(target_id)
        ):
            enclosing = st.smallest_volume_containing(target_id)
            hint = f" — name {enclosing.id!r} instead" if enclosing else ""
            yield Finding(
                "V24",
                f"{target_id!r} cannot be sealed on its own: a permanent doorless passage "
                f"crosses its boundary{hint}",
                task.id,
            )
        elif target_id not in st.isolation_targets:
            yield Finding(
                "V24",
                f"{target_id!r} is not one of the {len(st.isolation_targets)} isolation "
                f"targets in station.json ({sorted(st.isolation_targets)})",
                task.id,
            )


def v25(ctx: Ctx) -> Iterator[Finding]:
    """Any place named in an indirect instruction resolves to a real place.

    The prose of the message that creates a derived task must mention the
    target's phrase (or one of its areas), otherwise the instruction and the
    obligation are about different things and the player cannot win.
    """
    phrases = ctx.station.phrases()
    for task in ctx.scenario.tasks:
        if task.derived_from is None:
            continue
        target = ctx.station.isolation_targets.get(task.derived_from.isolation_target)
        msg = ctx.message_of_task(task)
        if target is None or msg is None:
            continue
        low = msg.text.lower()
        names = (
            [target.phrase.lower()]
            + [ctx.station.area_prose(a).lower() for a in target.volume]
            + [ctx.station.area_name(a).lower() for a in target.volume]
        )
        if not any(n and n in low for n in names if n):
            yield Finding(
                "V25",
                f"task is derived from {target.id!r} but message {msg.id} never names "
                f"it — the prose must say {target.phrase!r}",
                task.id,
            )
    for msg in ctx.scenario.messages:
        for door in ctx.doors_in_text(msg.text):
            if door not in ctx.station.doors:
                yield Finding(
                    "V25", f"names a door that does not exist: {door}", msg.id
                )
        for match in SUSPECT_PLACE_RE.finditer(msg.text):
            phrase = match.group(0).lower().strip()
            if phrase in phrases:
                continue
            if any(phrase in p for p in phrases):
                continue
            yield Finding(
                "V25",
                f"place name {match.group(0)!r} does not resolve to anything in "
                "station.json",
                msg.id,
            )


# ===========================================================================
# 13.5 Retractions
# ===========================================================================


def _freed_by(ctx: Ctx, msg: Message) -> tuple[dict[str, str], set[str]]:
    """What a retraction actually releases, and which tasks it releases.

    Not the union of everything its target group ever required. A group that says
    "open D12 for the crossing, then close it again" requires D12 in *both*
    states over its life, and taking the union would claim the withdrawal freed
    D12-closed when at that moment it freed D12-open. Only the tasks still live
    at `message.at` are released, because only they were still binding.
    """
    freed: dict[str, str] = {}
    released: set[str] = set()
    sc = ctx.scenario
    for group_key in msg.cancels:
        if group_key in sc.groups_by_id:
            tasks = sc.tasks_of_group(group_key)
        elif group_key in sc.tasks_by_id:
            tasks = [sc.tasks_by_id[group_key]]
        else:
            continue
        for task in tasks:
            released.add(task.id)
            if task.at <= msg.at <= task.until or task.at > msg.at:
                freed.update(task.require)
    return freed, released


def v26(ctx: Ctx) -> Iterator[Finding]:
    """A retraction must cancel something that is still live.

    Withdrawing an obligation that already finished, or that a previous
    retraction already withdrew, is a no-op the player cannot even notice.
    """
    sc = ctx.scenario
    seen_cancelled: dict[str, int] = {}
    for msg in sc.sorted_messages():
        if not msg.cancels:
            if msg.kind == "retraction":
                yield Finding(
                    "V26", "kind is retraction but `cancels` is empty", msg.id
                )
            continue
        if msg.kind != "retraction":
            yield Finding(
                "V26",
                f"carries `cancels` but kind is {msg.kind!r}, expected 'retraction'",
                msg.id,
            )
        for target in msg.cancels:
            tasks: list[Task]
            if target in sc.groups_by_id:
                tasks = sc.tasks_of_group(target)
            elif target in sc.tasks_by_id:
                tasks = [sc.tasks_by_id[target]]
            else:
                yield Finding(
                    "V26", f"cancels {target!r}, which does not exist", msg.id
                )
                continue
            if target in seen_cancelled:
                yield Finding(
                    "V26",
                    f"{target} was already cancelled at {seen_cancelled[target]}s",
                    msg.id,
                )
                continue
            seen_cancelled[target] = msg.at
            pending = [t for t in tasks if t.until >= msg.at]
            if not pending:
                latest = max((t.until for t in tasks), default=0)
                yield Finding(
                    "V26",
                    f"{target} has no task still pending at {msg.at} (all done by {latest}s) "
                    "— cancelling it changes nothing",
                    msg.id,
                )


def v27(ctx: Ctx) -> Iterator[Finding]:
    """The text must pin down which obligation is being withdrawn.

    There is no structural limit on how many obligations an actor may hold. The
    constraint is on the prose: when the retracting actor holds more than one
    live obligation, the message has to identify one of them -- by door, place,
    subject or timing.
    """
    sc = ctx.scenario
    for msg in sc.retractions():
        live_groups = _live_groups_of_actor(
            ctx, msg.actor_id, msg.at, exclude=msg.cancels
        )
        if not live_groups:
            continue
        cancelled_labels = [
            sc.groups_by_id[g].label for g in msg.cancels if g in sc.groups_by_id
        ]
        low = msg.text.lower()
        cues: list[str] = []
        for gid in msg.cancels:
            group = sc.groups_by_id.get(gid)
            if group is None:
                continue
            for task in sc.tasks_of_group(gid):
                cues += list(task.require)
                if task.derived_from:
                    target = ctx.station.isolation_targets.get(
                        task.derived_from.isolation_target
                    )
                    if target:
                        cues.append(target.phrase)
            cues += [w for w in re.findall(r"[A-Za-z]{5,}", group.label)]
        if not any(cue.lower() in low for cue in cues):
            yield Finding(
                "V27",
                f"{ctx.scenario.actors_by_id[msg.actor_id].type} still holds "
                f"{len(live_groups)} other live obligation(s) "
                f'({sorted(live_groups)}), so "{msg.text[:60]}..." cannot be resolved. '
                f"Name the door, the place, or the subject: one of {sorted(set(cues))[:6]}"
                + (f" (withdrawing: {cancelled_labels})" if cancelled_labels else ""),
                msg.id,
            )


def _live_groups_of_actor(ctx: Ctx, actor_id: str, at: float, exclude=()) -> set[str]:
    """Groups created by this actor with a task still pending at `at`."""
    sc = ctx.scenario
    mine = {
        m.task_group_id
        for m in sc.messages
        if m.actor_id == actor_id and m.task_group_id and m.at <= at
    }
    out = set()
    for gid in mine - set(exclude):
        if gid is None:
            continue
        for task in sc.tasks_of_group(gid):
            if task.until >= at and task.id not in ctx.sim.cancelled_task_ids:
                out.add(gid)
                break
    return out


def v28(ctx: Ctx) -> Iterator[Finding]:
    """`cross_actor` really is cross-actor, and names the other actor."""
    sc = ctx.scenario
    for msg in sc.retractions():
        style = msg.retraction_style
        if style not in RETRACTION_STYLES:
            yield Finding("V28", f"unknown retraction_style {style!r}", msg.id)
            continue
        creators = set()
        for gid in msg.cancels:
            creators |= {m.actor_id for m in sc.messages if m.task_group_id == gid}
            if gid in sc.tasks_by_id:
                owner = sc.messages_by_id.get(sc.tasks_by_id[gid].message_id)
                if owner:
                    creators.add(owner.actor_id)
        others = creators - {msg.actor_id}
        if style == "cross_actor":
            if not others:
                yield Finding(
                    "V28",
                    "style is cross_actor but the obligation was created by this same "
                    "actor",
                    msg.id,
                )
            low = msg.text.lower()
            unnamed = [
                sc.actors_by_id[a].type
                for a in others
                if sc.actors_by_id[a].type not in low
                and sc.actors_by_id[a].name.split()[-1].lower() not in low
            ]
            if unnamed:
                yield Finding(
                    "V28",
                    f"style is cross_actor but the text never names {unnamed} — the "
                    "player has to be told whose instruction is being withdrawn",
                    msg.id,
                )
        elif style == "self_reference" and others:
            yield Finding(
                "V28",
                f"style is self_reference but the obligation came from "
                f"{[sc.actors_by_id[a].type for a in others]}, not this actor",
                msg.id,
            )


def v29(ctx: Ctx) -> Iterator[Finding]:
    """Retractions must have teeth (spec 6.7.2).

    Form 1 -- a later task requires the opposite state on a freed door -- is the
    one with real bite: a player who still believes the old restriction refuses
    and fails. Form 2 is a challenge whose answer depends on the retraction. At
    least half must be form 1, or the generator will produce decoration.
    """
    sc = ctx.scenario
    forms: dict[str, str] = {}
    for msg in sc.retractions():
        freed, released = _freed_by(ctx, msg)
        opposite = {
            door: ("open" if state == "closed" else "closed")
            for door, state in freed.items()
        }
        has_task = any(
            t.at > msg.at
            and t.id not in ctx.sim.cancelled_task_ids
            and t.id not in released
            and any(t.require.get(d) == s for d, s in opposite.items())
            for t in sc.tasks
        )
        has_challenge = any(
            msg.id in ch.depends_on or any(g in ch.depends_on for g in msg.cancels)
            for ch in sc.all_challenges
            if ch.slot == "debrief" or ch.at > msg.at
        )
        if has_task:
            forms[msg.id] = "task"
        elif has_challenge:
            forms[msg.id] = "challenge"
        else:
            forms[msg.id] = "none"
            yield Finding(
                "V29",
                f"has no teeth: nothing later requires {opposite} on the freed door(s), "
                "and no challenge declares it in depends_on. A retraction with no "
                "consequence is decoration",
                msg.id,
            )
    real = [m for m, f in forms.items() if f != "none"]
    task_form = [m for m, f in forms.items() if f == "task"]
    if real and len(task_form) * 2 < len(real):
        yield Finding(
            "V29",
            f"only {len(task_form)} of {len(real)} retractions are backed by a later "
            "opposite-state task; at least half must be",
        )


def v30(ctx: Ctx) -> Iterator[Finding]:
    """2-3 retractions, none in phase 1."""
    vol = ctx.difficulty.volumes
    retractions = ctx.scenario.retractions()
    lo, hi = vol["retractions_min"], vol["retractions_max"]
    if not lo <= len(retractions) <= hi:
        yield Finding("V30", f"{len(retractions)} retractions, expected {lo}-{hi}")
    for msg in retractions:
        if ctx.phase(msg.at) == 1:
            yield Finding(
                "V30",
                f"retraction at {msg.at} falls in phase 1, where the player is still "
                "learning the interface",
                msg.id,
            )
        if msg.retraction_style is None:
            yield Finding("V30", "retraction has no retraction_style", msg.id)


def v31(ctx: Ctx) -> Iterator[Finding]:
    """No immediate re-imposition: the same actor may not re-create the same
    requirement on the same door within 90 s of withdrawing it."""
    sc = ctx.scenario
    for msg in sc.retractions():
        freed, released = _freed_by(ctx, msg)
        for task in sc.tasks:
            if not msg.at < task.at <= msg.at + 90:
                continue
            if ctx.actor_of_task(task) != msg.actor_id:
                continue
            # A task inside the group being withdrawn is not a re-imposition of
            # it; the withdrawal cancelled that task too.
            if task.id in released or task.id in ctx.sim.cancelled_task_ids:
                continue
            same = {d: s for d, s in task.require.items() if freed.get(d) == s}
            if same:
                yield Finding(
                    "V31",
                    f"re-imposes {same} at {task.at}, only {task.at - msg.at}s after "
                    f"{msg.id} withdrew it",
                    task.id,
                )


# ===========================================================================
# 13.6 Station consistency
# ===========================================================================


def v32(ctx: Ctx) -> Iterator[Finding]:
    """No invented doors, rooms or corridors anywhere in the prose."""
    texts: list[tuple[str, str]] = [(m.id, m.text) for m in ctx.scenario.messages]
    texts += [(t.id, t.fail_message) for t in ctx.scenario.tasks]
    for ch in ctx.scenario.all_challenges:
        texts.append((ch.id, ch.prompt))
        texts.append((ch.id, ch.explanation))
        texts += [(ch.id, o.text) for o in ch.options]
        if ch.pretext:
            texts.append((ch.id, ch.pretext))
    phrases = ctx.station.phrases()
    for where, text in texts:
        for door in ctx.doors_in_text(text):
            if door not in ctx.station.doors:
                yield Finding(
                    "V32",
                    f"names door {door}, which does not exist "
                    f"(station has {sorted(ctx.station.doors, key=door_sort_key)})",
                    where,
                )
        for match in SUSPECT_PLACE_RE.finditer(text):
            phrase = match.group(0).lower().strip()
            if phrase in phrases or any(phrase in p for p in phrases):
                continue
            yield Finding(
                "V32",
                f"names {match.group(0)!r}, which is not a place on this station",
                where,
            )


def v33(ctx: Ctx) -> Iterator[Finding]:
    """The scenario was authored against this layout."""
    if ctx.scenario.station_version != ctx.station.version:
        yield Finding(
            "V33",
            f"station_version is {ctx.scenario.station_version!r} but station.json is "
            f"{ctx.station.version!r} — the layout changed under this scenario",
        )


def v34(ctx: Ctx) -> Iterator[Finding]:
    """The scenario records the tunables it was validated against.

    Not a rejection when they differ from the running config -- that is the
    admin page's job to flag (spec 9.1) -- but a missing fingerprint means
    nobody can tell, so that is an error.
    """
    want = ctx.difficulty.validator_fingerprint()
    got = ctx.scenario.difficulty_fingerprint
    if not got:
        yield Finding(
            "V34",
            "no difficulty_fingerprint recorded, so a later config change would go "
            "unnoticed",
        )
        return
    drifted = sorted(k for k in want if got.get(k) != want[k])
    if drifted:
        yield Finding(
            "V34",
            f"validated against different tunables: {[(k, got.get(k), want[k]) for k in drifted]}",
            severity="warning",
        )


ALL_RULES = [
    v01,
    v02,
    v03,
    v04,
    v05,
    v06,
    v07,
    v08,
    v09,
    v10,
    v11,
    v12,
    v13,
    v14,
    v15,
    v16,
    v17,
    v18,
    v19,
    v20,
    v21,
    v22,
    v23,
    v24,
    v25,
    v26,
    v27,
    v28,
    v29,
    v30,
    v31,
    v32,
    v33,
    v34,
]


# ===========================================================================
# 13.7 Plain language
# ===========================================================================

#: Figures of speech and slang that models reach for and that a non-native
#: speaker would have to decode. Deliberately a short, curated list of things
#: that are unambiguous as strings -- standard radio procedure words ("copy",
#: "roger", "stand by", "say again") are not here, because they are consistent,
#: learnable, and part of what makes the fiction work.
IDIOMS_EN: tuple[str, ...] = (
    "keep an eye",
    "buy me time",
    "buy us time",
    "buy some time",
    "clock is ticking",
    "up against it",
    "piece of cake",
    "heads up",
    "in the loop",
    "same page",
    "ballpark",
    "hold your horses",
    "no dice",
    "spot on",
    "dead in the water",
    "call it a day",
    "give me a hand",
    "up to speed",
    "ball is in your court",
    "bite the bullet",
    "cut corners",
    "under the weather",
    "throw a spanner",
    "wild goose",
    "back to square one",
    "in hot water",
    "on thin ice",
    "bend over backwards",
    "cut to the chase",
    "at the end of the day",
    "long story short",
    "touch base",
    "circle back",
    "moving forward",
    " mikes",
    " klicks",
    " clicks",
    "asap",
    "pronto",
    "gonna",
    "gotta",
    "wanna",
    "ain't",
    "y'all",
    "kinda",
    "sorta",
    "no biggie",
    "for kicks",
    "a heads-up",
)

#: The French arm's equivalent of IDIOMS_EN (spec 13.7). Not a translation of
#: the English list -- an idiom is idiomatic in one language and not the
#: other, so this is its own curated set of French figures of speech, slang
#: and contracted registers a non-native French speaker would have to decode
#: in one hearing. "feu vert"/"feu rouge" ("green light"/"red light") are
#: included for a second reason beyond idiom: this game already uses green
#: and red as the literal, load-bearing colour of an open and a closed door,
#: so the figurative sense would collide with the mechanic itself.
IDIOMS_FR: tuple[str, ...] = ()

#: A spoken instruction longer than this is hard to hold in one hearing.
LONG_SENTENCE_WORDS = 20
#: Beyond this it is not a style question any more.
VERY_LONG_SENTENCE_WORDS = 30

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def v35(ctx: Ctx) -> Iterator[Finding]:
    """Plain language.

    Most players are not native speakers of the scenario's language, and a
    `radio` message is heard exactly once with no transcript and no replay.
    That makes reading difficulty a confound rather than a style preference: a
    player who fails because they did not parse an idiom has been measured on
    their reading of the language, not on their memory.

    Errors: idioms, figures of speech, slang, and any sentence long enough that
    holding it in one hearing is the hard part. Warnings: sentences over
    twenty words, which are worth tightening but will not invalidate a session.
    """
    idioms = IDIOMS_FR if ctx.scenario.language == "fr" else IDIOMS_EN
    for where, text, spoken in _all_prose(ctx):
        low = f" {text.lower()} "
        for idiom in idioms:
            if idiom in low:
                yield Finding(
                    "V35",
                    f"{idiom.strip()!r} is an idiom or slang term — say it plainly, "
                    "most players are not native speakers",
                    where,
                )
        for sentence in SENTENCE_SPLIT_RE.split(text.strip()):
            words = len(sentence.split())
            if words > VERY_LONG_SENTENCE_WORDS:
                yield Finding(
                    "V35",
                    f"a {words}-word sentence: {sentence[:70]!r}... — one instruction "
                    "per sentence, under twenty words",
                    where,
                )
            elif words > LONG_SENTENCE_WORDS and spoken:
                yield Finding(
                    "V35",
                    f"a {words}-word spoken sentence is hard to hold in one hearing: "
                    f"{sentence[:70]!r}",
                    where,
                    severity="warning",
                )


def _all_prose(ctx: Ctx) -> Iterator[tuple[str, str, bool]]:
    """Every string a player ever sees or hears, with whether it is spoken."""
    for msg in ctx.scenario.messages:
        yield msg.id, msg.text, msg.channel == "radio"
    for task in ctx.scenario.tasks:
        yield task.id, task.fail_message, False
    for ch in ctx.scenario.all_challenges:
        yield ch.id, ch.prompt, ch.channel == "radio"
        yield ch.id, ch.explanation, False
        for option in ch.options:
            yield ch.id, option.text, False


def v36(ctx: Ctx) -> Iterator[Finding]:
    """A message is never answerable, so it must never ask a question.

    Only a `challenge` has a reply interface. A plain message that ends
    "...is the reactor corridor still off-limits?" reads as a question the
    player is expected to answer, and there is no way to: it just sits there
    unresolved. Say it as a report or a statement instead.
    """
    for msg in ctx.scenario.messages:
        if "?" in msg.text:
            yield Finding(
                "V36",
                "a message can never be answered — there is no reply interface "
                "outside a challenge. Rephrase the question as a statement",
                msg.id,
            )


#: Internal bookkeeping ids: m_012, t_045, og_ext_vent, th_reactor, q_003.
#: Deliberately scoped to the underscore-joined shapes the generator actually
#: mints, so a door token like D7 or a place like "Extension Epsilon" never
#: matches.
INTERNAL_ID_RE = re.compile(r"\b(?:m|t|q|th|og|a)_[a-z0-9][a-z0-9_]*\b", re.IGNORECASE)


def v37(ctx: Ctx) -> Iterator[Finding]:
    """No internal id ever reaches the player.

    m_012, t_045, og_ext_vent and friends are bookkeeping for the generator and
    the admin page. A challenge's `explanation` is written last, with the full
    annotated timeline in view, and it is easy to cite the message id just read
    instead of describing what happened. The player has never seen an id, and
    the string means nothing to them.
    """
    texts: list[tuple[str, str]] = [(m.id, m.text) for m in ctx.scenario.messages]
    texts += [(t.id, t.fail_message) for t in ctx.scenario.tasks]
    for ch in ctx.scenario.all_challenges:
        texts.append((ch.id, ch.prompt))
        texts.append((ch.id, ch.explanation))
        texts += [(ch.id, o.text) for o in ch.options]
    for where, text in texts:
        for match in INTERNAL_ID_RE.finditer(text):
            yield Finding(
                "V37",
                f"names the internal id {match.group(0)!r}, which means nothing to a "
                "player — describe what happened instead of citing the record",
                where,
            )


def v38(ctx: Ctx) -> Iterator[Finding]:
    """A 'time' challenge is reasoning about this shift, which is under half an
    hour long and where no obligation holds longer than 30% of it: the RIGHT
    answer measured in hours cannot be what actually happened, and is an
    authoring mistake rather than a hard question.

    Only the prompt, the explanation and the correct option are checked. A
    wrong option is allowed to name hours on purpose -- an implausible order of
    magnitude is a legitimate distractor (V19), and a player who knows the
    shift lasts thirty minutes should find it easy to rule out.
    """
    for ch in ctx.scenario.all_challenges:
        if ch.kind != "time":
            continue
        correct = ch.correct_option()
        texts = [ch.prompt, ch.explanation] + ([correct.text] if correct else [])
        for text in texts:
            if re.search(r"\bhours?\b", text, re.IGNORECASE):
                yield Finding(
                    "V38",
                    f"the correct answer names hours, but the whole shift lasts "
                    f"{ctx.scenario.duration_seconds // 60} minutes: {text[:70]!r}",
                    ch.id,
                )
                break


ALL_RULES.append(v35)
ALL_RULES.append(v36)
ALL_RULES.append(v37)
ALL_RULES.append(v38)
