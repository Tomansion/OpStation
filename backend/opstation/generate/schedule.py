"""Deterministic timeline assignment.

Every timing rule in spec 13.2 is arithmetic, so it is settled here rather than
asked of the LLM: minimum gaps (V9), the rolling reading budget (V8), the slack
between a message and the obligation it creates (V7), windows that fit inside
the session (V10), and challenge placement clear of every deadline (V11, V12).

The LLM only says which phase a beat belongs to and in what order. This decides
when.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..config import Difficulty, PHASE_BOUNDS, phase_at
from ..station import Station
from .plan import BeatSpec, ChallengeSpec, Plan, TaskSpec

#: A dormant thread has to be quiet for longer than V18's 240 s to survive
#: later nudges to the timeline.
DORMANCY_SECONDS = 275

#: Ordinary obligations end this far before the session does. The end-of-shift
#: seal ends later still (`SEAL_TAIL`), so V21's "last task group" is
#: unambiguous rather than a tie.
ORDINARY_TAIL = 10
SEAL_TAIL = 3

#: The longest single obligation, as a fraction of the session. Models
#: cheerfully write a 60-minute hold into a 27-minute shift; an eight-minute
#: hold is already more memory load than anything else in the game.
MAX_HOLD_FRACTION = 0.30

#: Breathing room left between two obligations on the same door, and the
#: shortest hold worth keeping after a truncation.
CONFLICT_GAP = 8
MIN_USEFUL_HOLD = 20

#: An obligation that somebody later withdraws has to have been standing long
#: enough for the withdrawal to land inside it and to be worth making. Models
#: cheerfully attach a retraction to a thirty-second hold, which leaves nowhere
#: legal to put it (V26) and no reason to care.
RETRACTED_MIN_HOLD = 240

#: Challenges are placed before they are written, so their slot has to be
#: reserved against a cost nobody knows yet. The reservation uses the WORST
#: case -- `read_cost` is clamped at `read_cost_max_seconds`, so no prompt can
#: ever cost more than this. A slot that turns out cheaper is harmless; one that
#: turns out dearer breaks V8 after the audio has been rendered.
_CHALLENGE_PLACEHOLDER = " ".join(["word"] * 200)

#: A representative withdrawal, for `_reserve_retraction_slots`. Unlike the
#: challenge placeholder this is not a worst case -- a retraction's own
#: placement is bounded to its real target window regardless (see
#: `_place_retractions`), so overstating its cost here would only starve
#: ordinary content for no reason. This is sized like an actual one-line
#: "stand down" message.
_RETRACTION_PLACEHOLDER = (
    "Door Control, stand down on the earlier hold — that instruction is "
    "lifted now, the situation has changed."
)

#: Sentence ends, for estimating how much inter-sentence silence the renderer
#: will add. Piper does its own segmentation; this only has to agree closely.
SENTENCE_END = re.compile(r"[.!?](?:\s|$)")

#: Door names are spoken separately and slower, so they cost more than the words
#: around them. About how long "D 7" takes at normal speed, used to price the
#: slow-down.
DOOR_TOKEN_SECONDS = 0.9
DOOR_IN_PROSE = re.compile(r"\b[DH]\d{1,2}\b")


@dataclass
class Placed:
    at: int
    cost: float
    beat: BeatSpec


@dataclass
class Schedule:
    duration: int
    placed: list[Placed] = field(default_factory=list)
    task_times: dict[int, tuple[int, int]] = field(default_factory=dict)  # id(task) -> (at, hold)
    dropped_tasks: set[int] = field(default_factory=set)
    #: Beat keys whose withdrawal could not be kept -- either its target no
    #: longer stands or it is over the quota. Recorded rather than applied to the
    #: plan, because the scheduler runs more than once over the same plan and a
    #: mutation would compound across runs.
    demoted_retractions: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def times(self) -> list[int]:
        return [p.at for p in self.placed]


class Scheduler:
    def __init__(self, plan: Plan, diff: Difficulty, station: Station) -> None:
        self.plan = plan
        self.diff = diff
        self.station = station
        self.duration = plan.duration_seconds
        self.gap = int(diff["min_message_gap_seconds"])
        self.window = float(diff["read_budget_window_seconds"])
        self.slack = int(diff["task_slack_after_message_seconds"])
        self.sched = Schedule(duration=self.duration)
        #: Counters for the end-of-run summary note only -- diagnostics, not
        #: anything a rule depends on. `run()` is called more than once over
        #: the same plan (a provisional pass, then the real one in `assemble`),
        #: so these reflect only the most recent `run()`.
        self._stat_ordinary_total = 0
        self._stat_ordinary_dropped = 0
        self._stat_retraction_requested = 0
        self._stat_retraction_kept = 0
        self._stat_retraction_no_live_window = 0
        self._stat_retraction_over_quota = 0
        self._stat_retraction_no_room_in_window = 0
        self._stat_retraction_stranded = 0
        self._stat_temptation_requested = 0
        self._stat_temptation_kept = 0

    # ------------------------------------------------------------- helpers

    def phase_window(self, phase: int) -> tuple[int, int]:
        lo, hi = next((l, h) for p, l, h in PHASE_BOUNDS if p == phase)
        return int(lo * self.duration), int(hi * self.duration)

    def read_cost(self, beat: BeatSpec) -> float:
        """Estimate what a message will cost the player to consume.

        Audio does not exist yet -- it is rendered after validation -- so a radio
        message is costed from its text, marked up because speech runs slower
        than the eye, plus the silence the renderer will insert between
        sentences. Under-estimating here is not a rounding error: the real
        durations are written back and the timing rules re-checked against them
        (spec 12.1 step 5), and an estimate that was too low fails V7 at that
        point, after the audio has been paid for.
        """
        base = self.diff.read_cost(beat.text)
        if beat.channel != "radio":
            return base
        gap = float(self.diff.get("tts_sentence_gap_seconds", 1.0))
        sentences = max(1, len(SENTENCE_END.findall(beat.text)))
        # Each door name is rendered on its own, slower, with a pause either
        # side, so it costs more than the words around it.
        pause = float(self.diff.get("tts_door_pause_seconds", 0.25))
        scale = float(self.diff.get("tts_door_length_scale", 1.3))
        per_door = 2 * pause + DOOR_TOKEN_SECONDS * (scale - 1.0) + 0.25
        doors = len(DOOR_IN_PROSE.findall(beat.text))
        return round(base * 1.35 + gap * (sentences - 1) + per_door * doors, 2)

    def _fits(self, at: int, cost: float) -> bool:
        """Would placing `cost` at `at` break the rolling budget in any window?"""
        items = [(p.at, p.cost) for p in self.sched.placed] + [(at, cost)]
        starts = {t for t, _ in items if at - self.window < t <= at}
        starts.add(at)
        for start in starts:
            total = sum(c for t, c in items if start <= t < start + self.window)
            if total > self.diff.read_budget_for_phase(phase_at(start, self.duration)):
                return False
        return True

    def _seal_ceiling(self) -> int:
        """The end-of-shift seal is pinned to be the last real message (V21).
        No ordinary, unpinned beat may be walked forward onto or past it, or
        the seal stops being last -- `_place`'s generic ceiling alone is not
        tight enough to guarantee that, since it is normally much later than
        the seal's own pin."""
        seal_pins = [
            b.pin_at for b in self.plan.beats
            if b.pin_at is not None and any(t.seal_station for t in b.tasks)
        ]
        if not seal_pins:
            return self.duration - 40
        return min(self.duration - 40, min(seal_pins) - self.gap)

    def _place(self, beat: BeatSpec, earliest: int, ceiling: int | None = None) -> int:
        """`ceiling` overrides the normal end-of-session limit for this one
        placement -- used by `_place_retractions` so a withdrawal can never be
        walked past the end of the window it is meant to land inside (see its
        docstring). Defaults to `_seal_ceiling()`, the ordinary limit."""
        lo, hi = self.phase_window(beat.phase)
        cost = self.read_cost(beat)
        if beat.pin_at is not None:
            beat.at = beat.pin_at
            self.sched.placed.append(Placed(at=beat.at, cost=cost, beat=beat))
            return beat.at
        at = max(earliest, lo)
        capped = ceiling is not None
        ceiling = self._seal_ceiling() if ceiling is None else min(ceiling, self._seal_ceiling())
        # Walk forward until the density rule is satisfied. Steps of `gap` keep
        # this cheap; the budget is the binding constraint, not the gap.
        guard = 0
        while not self._fits(at, cost) and at <= ceiling:
            at += self.gap
            guard += 1
            if guard > 4000:
                break
        if at > ceiling:
            # There is no room left in the session (or, if `ceiling` was capped
            # by the caller, no room before the caller's own limit -- e.g. a
            # retraction's target window closing). Dropping the beat is the
            # only honest option: placing it past the end would fail V2, and
            # squeezing it in would fail the reading budget the player
            # actually needs.
            reason = "no room left before its target window closes" if capped \
                else "no room left in the session"
            self.sched.notes.append(
                f"{beat.key}: {reason} — dropped"
            )
            beat.at = None
            return -1
        if at > hi:
            self.sched.notes.append(
                f"{beat.key}: phase {beat.phase} was full, spilled to {at}s"
            )
        beat.at = at
        self.sched.placed.append(Placed(at=at, cost=cost, beat=beat))
        return at

    def _last_of_thread(self, thread_key: str) -> int:
        times = [p.at for p in self.sched.placed if p.beat.thread_key == thread_key]
        return max(times) if times else -10_000

    # -------------------------------------------------------------- passes

    def run(self) -> Schedule:
        """Place every message, then every obligation, then the questions.

        The order matters and was arrived at the hard way. Messages must all be
        settled before task times are derived from them, because a message that
        moves afterwards breaks the reading slack its own obligation depends on
        (V7) and can carry a withdrawal past the thing it withdraws (V26).
        """
        # The three in-session questions are appointments, so their slots are
        # reserved before anything competes for the reading budget. Placing them
        # last -- after 70-odd messages have filled every 60 s window -- leaves
        # nowhere legal to put them. Retractions get the same treatment, for the
        # same reason: they too are placed in a later pass, and without a
        # reservation the ordinary pass below has already spent the budget they
        # needed.
        self._reserve_challenge_slots()
        self._reserve_retraction_slots()
        self._place_pinned()
        self._place_ordinary_beats()
        self._enforce_message_spacing()

        # A first pass, so retractions and temptations can see real windows.
        self._assign_task_times()
        self._resolve_conflicts()
        self._place_retractions()
        self._place_temptations()
        self._separate_reimposition()
        self._enforce_message_spacing()

        # Messages are final from here. Everything below derives from them.
        self._assign_task_times()
        self._resolve_conflicts()
        # A challenge is a fixed appointment and an obligation is not, so the
        # obligations move out of its way rather than the other way round. With
        # forty-odd tasks in a 27-minute shift, every deadline carries a 40 s
        # dead zone (V11) and searching for a gap between them finds none.
        self._clear_challenge_zones()
        self._resolve_conflicts()
        self._drop_stranded_retractions()
        self._place_challenges()
        self._recompute_phase_spans()
        self._log_summary()
        return self.sched

    def _log_summary(self) -> None:
        """One line that answers 'did this run have enough room', without
        having to count 'no room left' notes by hand. This is what the
        generator's volume and retraction validator failures (V20, V30) come
        from far more often than a writing mistake, so it belongs beside the
        per-beat notes above it, not only in the final validator report."""
        self.sched.notes.append(
            f"placed {self._stat_ordinary_total - self._stat_ordinary_dropped}/"
            f"{self._stat_ordinary_total} ordinary beats "
            f"({self._stat_ordinary_dropped} dropped for room); "
            f"retractions {self._stat_retraction_kept}/{self._stat_retraction_requested} kept "
            f"({self._stat_retraction_no_live_window} had no live window, "
            f"{self._stat_retraction_no_room_in_window} had a window but no room in it, "
            f"{self._stat_retraction_over_quota} were genuinely over the quota, "
            f"{self._stat_retraction_stranded} landed outside their own window); "
            f"temptations {self._stat_temptation_kept}/{self._stat_temptation_requested} kept"
        )

    def _drop_stranded_retractions(self) -> None:
        """Last word on withdrawals: after every adjustment, is each one still
        inside something it can actually cancel?"""
        self._stat_retraction_stranded = 0
        for beat in self.plan.beats:
            if beat.kind != "retraction" or beat.at is None:
                continue
            if beat.key in self.sched.demoted_retractions:
                continue
            if not any(start <= beat.at <= end for start, end in self._live_windows(beat)):
                self.sched.notes.append(
                    f"{beat.key}: ended up outside every window it cancels — "
                    "kept as a status message"
                )
                self.sched.demoted_retractions.add(beat.key)
                self._stat_retraction_stranded += 1
                self._stat_retraction_kept = max(0, self._stat_retraction_kept - 1)

    def _reserve_challenge_slots(self) -> None:
        """Hold the nominal slots open in the reading budget."""
        cost = self.diff.read_cost(_CHALLENGE_PLACEHOLDER)
        for index, at in enumerate(self._nominal_challenge_times(), start=1):
            marker = BeatSpec(
                key=f"__challenge_slot_{index}", thread_key="__slots", phase=5,
                actor_type="system", channel="text", kind="chatter", text="",
                pin_at=at, at=at,
            )
            self.sched.placed.append(Placed(at=at, cost=cost, beat=marker))

    def _reserve_retraction_slots(self) -> None:
        """Hold a little reading budget open across the middle of the session
        for the withdrawals that have not been placed yet.

        Retractions are placed by `_place_retractions`, well after
        `_place_ordinary_beats` has already packed the budget densely -- so a
        retraction was only ever as likely to fit as whatever that first pass
        happened to leave behind, which is why they are so often the first
        thing lost to "no room". Reserving a little room ahead of time, the
        same way `_reserve_challenge_slots` already does for questions, gives
        the later, precisely-targeted retraction pass somewhere to actually
        land.

        This cannot reserve the RIGHT second -- a retraction's real target
        window is only known once its own obligation has been placed and
        timed, which happens after this runs -- so it is deliberately coarse:
        one slot per retraction candidate (capped the same way
        `_place_retractions` caps itself), spread evenly across the span
        retractions are actually allowed to land in (after phase 1, per V30,
        and clear of the very end).
        """
        candidates = [b for b in self.plan.beats if b.kind == "retraction"]
        if not candidates:
            return
        quota = int(self.diff.volumes["retractions_max"])
        count = min(len(candidates), quota + 1)
        marker_cost = self.read_cost(BeatSpec(
            key="__retraction_slot", thread_key="__slots", phase=1,
            actor_type="system", channel="radio", kind="chatter",
            text=_RETRACTION_PLACEHOLDER,
        ))
        span = (0.20, 0.78)
        for index in range(count):
            frac = span[0] + (index + 0.5) * (span[1] - span[0]) / count
            at = int(frac * self.duration)
            marker = BeatSpec(
                key=f"__retraction_slot_{index + 1}", thread_key="__slots",
                phase=phase_at(at, self.duration), actor_type="system", channel="radio",
                kind="chatter", text="", pin_at=at, at=at,
            )
            self.sched.placed.append(Placed(at=at, cost=marker_cost, beat=marker))

    def _nominal_challenge_times(self) -> list[int]:
        """Where the in-session questions want to be: starting as soon as phase
        3 ("Memory") has had a little room to establish something worth being
        asked about, spread on to clear of the very end. The first question
        used to land around the 56% mark -- fifteen minutes into a 27-minute
        shift -- which is a long time to go without one."""
        count = int(self.diff.volumes["challenges_in_session"])
        span = (0.40, 0.90)
        if count == 1:
            return [int(0.7 * self.duration)]
        step = (span[1] - span[0]) / (count - 1)
        return [int((span[0] + i * step) * self.duration) for i in range(count)]

    def _clear_challenge_zones(self) -> None:
        clear = int(self.diff["challenge_task_clearance_seconds"])
        slots = self._nominal_challenge_times()

        def conflicts(at: int, hold: int) -> bool:
            return any(
                abs(boundary - slot) < clear
                for boundary in (at, at + hold)
                for slot in slots
            )

        for beat in self.plan.beats:
            if beat.at is None:
                continue
            for task in beat.tasks:
                key = id(task)
                if key in self.sched.dropped_tasks or key not in self.sched.task_times:
                    continue
                at, hold = self.sched.task_times[key]
                if not conflicts(at, hold):
                    continue
                earliest = self._task_start(beat, task)
                tail = SEAL_TAIL if task.seal_station else ORDINARY_TAIL
                moved = None
                for offset in range(1, 3 * clear + 2):
                    for candidate in (at + offset, at - offset):
                        if candidate < earliest or candidate + hold > self.duration - tail:
                            continue
                        if not conflicts(candidate, hold):
                            moved = candidate
                            break
                    if moved is not None:
                        break
                if moved is None:
                    self.sched.notes.append(
                        f"{beat.key}: could not move its obligation clear of a question slot"
                    )
                    continue
                self.sched.task_times[key] = (moved, hold)

    # ------------------------------------------------- solvability guarantee

    def require_of(self, task: TaskSpec) -> dict[str, str]:
        """The doors a task really constrains, with a derived isolation resolved
        through the door graph."""
        if task.seal_station:
            return {d.id: "closed" for d in self.station.hangar_doors}
        if task.isolation_target in self.station.isolation_targets:
            cut = self.station.target_cut(task.isolation_target)
            return cut.required(task.include_hangar_doors)
        return {k.upper(): v for k, v in task.require.items()}

    def _retraction_protected_task_ids(self) -> set[int]:
        """Tasks a retraction means to withdraw. `_floor_retracted_holds`
        floors these to `RETRACTED_MIN_HOLD` so the withdrawal has somewhere
        to land inside their window; conflict resolution must not immediately
        undo that by truncating one back below the floor; the retraction is
        placed later; and by then it would have no live window left to attach
        to (V30). Computed from the plan alone, so it is known before any
        scheduling pass runs."""
        protected: set[int] = set()
        for beat in self.plan.beats:
            if beat.kind != "retraction":
                continue
            for group_key in (self.plan.resolve_group(c) for c in beat.cancels):
                if not group_key:
                    continue
                for _owner, task in self.plan.tasks_of_group(group_key):
                    protected.add(id(task))
        return protected

    def _resolve_conflicts(self) -> None:
        """Guarantee that no two live obligations demand opposite states on one
        door at one moment (V13), which is also what makes the perfect-player
        simulation pass (V14).

        Threads are written in parallel and cannot know which doors the others
        claimed, so collisions are expected. Rather than reject the scenario and
        ask the model to redo its arithmetic, they are settled here, in this
        order of preference:

          1. truncate the earlier obligation -- the later instruction supersedes
             it, which is what the fiction implies anyway;
          2. push the later obligation past the earlier one;
          3. drop whichever carries less content.

        A task a retraction depends on is protected from (1) below the floor
        that made it withdrawable, and is not preferred as the loser in (3).
        """
        protected = self._retraction_protected_task_ids()
        entries = self._entries()
        for _ in range(400):
            pair = self._first_conflict(entries)
            if pair is None:
                break
            a, b = pair
            a_end, b_end = a["at"] + a["hold"], b["at"] + b["hold"]
            truncated = b["at"] - CONFLICT_GAP - a["at"]
            tail = SEAL_TAIL if b["task"].seal_station else ORDINARY_TAIL
            a_would_break_floor = a["key"] in protected and truncated < RETRACTED_MIN_HOLD
            if a["hold"] > 0 and truncated >= MIN_USEFUL_HOLD and not a_would_break_floor:
                self.sched.notes.append(
                    f"conflict on {a['door']}: {a['beat'].key} hold "
                    f"{a['hold']}->{truncated}s, superseded by {b['beat'].key}"
                )
                a["hold"] = truncated
            elif a_end + CONFLICT_GAP + b["hold"] <= self.duration - tail:
                new_at = a_end + CONFLICT_GAP
                self.sched.notes.append(
                    f"conflict on {a['door']}: {b['beat'].key} pushed "
                    f"{b['at']}->{new_at}s, clear of {a['beat'].key}"
                )
                b["at"] = new_at
            else:
                a_protected, b_protected = a["key"] in protected, b["key"] in protected
                if a_protected and not b_protected:
                    loser = b
                elif b_protected and not a_protected:
                    loser = a
                else:
                    loser = a if a["hold"] <= b["hold"] else b
                self.sched.notes.append(
                    f"conflict on {a['door']}: dropped {loser['beat'].key}'s task "
                    f"(no room to separate it from the other obligation)"
                )
                self.sched.dropped_tasks.add(loser["key"])
                entries = [e for e in entries if e["key"] != loser["key"]]
                continue
            entries = [e for e in entries if e["key"] not in self.sched.dropped_tasks]
        else:
            self.sched.notes.append("conflict resolution hit its iteration limit")
        for entry in entries:
            self.sched.task_times[entry["key"]] = (entry["at"], entry["hold"])

    def _entries(self) -> list[dict]:
        out: list[dict] = []
        for beat in self.plan.beats:
            if beat.at is None:
                continue
            for task in beat.tasks:
                key = id(task)
                if key not in self.sched.task_times:
                    continue
                at, hold = self.sched.task_times[key]
                out.append({
                    "key": key, "at": at, "hold": hold, "beat": beat, "task": task,
                    "require": self.require_of(task),
                })
        out.sort(key=lambda e: (e["at"], e["hold"]))
        return out

    def _first_conflict(self, entries: list[dict]):
        ordered = sorted(entries, key=lambda e: (e["at"], e["hold"]))
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                if b["at"] > a["at"] + a["hold"]:
                    continue
                shared = set(a["require"]) & set(b["require"])
                for door in sorted(shared):
                    if a["require"][door] != b["require"][door]:
                        a["door"] = b["door"] = door
                        return a, b
        return None

    def _ordering(self) -> list[BeatSpec]:
        """Interleave threads inside each phase so concurrent obligations really
        do arrive interleaved, rather than one thread at a time."""
        out: list[BeatSpec] = []
        for phase in (1, 2, 3, 4, 5):
            lanes: dict[str, list[BeatSpec]] = {}
            for thread in self.plan.threads:
                lane = [
                    b for b in thread.beats
                    if b.phase == phase and b.pin_at is None
                    and b.kind not in ("retraction", "tempting_request")
                ]
                if lane:
                    lanes[thread.key] = lane
            while lanes:
                for key in list(lanes):
                    out.append(lanes[key].pop(0))
                    if not lanes[key]:
                        del lanes[key]
        return out

    def _place_pinned(self) -> None:
        for beat in self.plan.beats:
            if beat.pin_at is not None:
                self._place(beat, beat.pin_at)

    def _place_ordinary_beats(self) -> None:
        cursor = 0
        self._stat_ordinary_total = 0
        self._stat_ordinary_dropped = 0
        for beat in self._ordering():
            self._stat_ordinary_total += 1
            earliest = cursor
            thread = self.plan.thread_of(beat.thread_key)
            previous = self._last_of_thread(beat.thread_key)
            # Enforce the dormant gap by construction: V18 is the measurement the
            # game exists for, so it is not left to chance.
            if thread and thread.dormant_after and previous > -10_000:
                already = [
                    p for p in self.sched.placed if p.beat.thread_key == beat.thread_key
                ]
                if already and already[-1].beat.key == thread.dormant_after:
                    earliest = max(earliest, previous + DORMANCY_SECONDS)
            at = self._place(beat, earliest)
            if at >= 0:
                cursor = at + self.gap
            else:
                self._stat_ordinary_dropped += 1

    def _place_retractions(self) -> None:
        """Place the withdrawals, keeping at most the quota.

        Runs after the windows are final, so "still live" is measured against the
        obligations that actually survived conflict resolution rather than an
        estimate of them. A candidate whose target no longer stands becomes a
        plain status message: the prose is still usable station traffic, and a
        message that cancels nothing is rejected by V26 and unnoticeable to the
        player anyway.

        Candidates are considered in order of bite, so if there are more than the
        quota the ones that survive are the ones something later depends on.
        """
        phase2_start = self.phase_window(2)[0]
        quota = int(self.diff.volumes["retractions_max"])
        candidates = [b for b in self.plan.beats if b.kind == "retraction"]
        self._stat_retraction_requested = len(candidates)
        self._stat_retraction_kept = 0
        self._stat_retraction_no_live_window = 0
        self._stat_retraction_over_quota = 0
        self._stat_retraction_no_room_in_window = 0
        for beat in candidates:
            beat.cancels = [
                c for c in (self.plan.resolve_group(c) for c in beat.cancels) if c
            ]
        ranked = sorted(
            candidates,
            key=lambda b: (self._has_bite(b), len(b.cancels), b.key),
            reverse=True,
        )

        kept = 0
        for beat in ranked:
            # A window is only usable if there is room inside it for the
            # withdrawal to land: after phase 1, after the obligation has been
            # standing a moment, and before it expires on its own. A short or
            # instantaneous obligation offers no such room, and withdrawing it
            # would cancel nothing (V26).
            usable = []
            for start, end in self._live_windows(beat):
                lower = max(phase2_start, start + 10)
                upper = end - 10
                if upper >= lower:
                    usable.append((start, end, lower, upper))
            # A little slack above the quota: `_drop_stranded_retractions` runs
            # much later, after everything else has finished moving, and can
            # still lose one of these to a target window that shifted out from
            # under it. Attempting one extra costs nothing when it is not needed.
            attempted = bool(usable) and kept < quota + 1
            if attempted:
                start, end, lower, upper = max(usable, key=lambda w: w[1] - w[0])
                # Comfortably inside: late enough that the player has held the
                # obligation for a while, early enough that dropping it matters.
                target = min(max(start + max(15, int(0.4 * (end - start))), lower), upper)
                beat.phase = phase_at(target, self.duration)
                # `ceiling=upper` is load-bearing, not a style choice: `_place`'s
                # own forward search only stops at the *session's* ceiling, which
                # is normally far later than `upper`. Without capping it here, a
                # crowded window lets the search walk straight past the end of
                # the obligation the withdrawal is meant to land inside -- it
                # still "succeeds" and increments `kept`, consuming a quota slot,
                # and only `_drop_stranded_retractions` notices afterward that it
                # landed outside every window it cancels. By then a lower-ranked
                # candidate that *did* fit inside its own window has already been
                # skipped for nothing. Capping the search here means a retraction
                # that cannot fit its own window fails immediately and honestly,
                # leaving the next candidate its chance.
                placed_at = self._place(beat, target, ceiling=upper)
                if placed_at >= 0:
                    kept += 1
                    self._stat_retraction_kept += 1
                    continue
                # `_place` found no room and dropped it -- this attempt did not
                # actually succeed, so it must not consume a quota slot that a
                # lower-ranked, placeable candidate could have used instead.
                # Fall through and give it the demoted placement below, which
                # tries an earlier, less contested target.
            live = usable
            if not live:
                reason = "nothing it cancels is still live"
                self._stat_retraction_no_live_window += 1
            elif attempted:
                # A window existed and was tried, but even the capped search
                # inside it found nowhere that fit -- this is the room problem,
                # not a genuine surplus (see the ceiling=upper comment above).
                reason = "no room within its own window, even though one exists"
                self._stat_retraction_no_room_in_window += 1
            else:
                reason = f"over the quota of {quota}"
                self._stat_retraction_over_quota += 1
            self.sched.notes.append(f"{beat.key}: {reason} — kept as a status message")
            self.sched.demoted_retractions.add(beat.key)
            self._place(beat, self.phase_window(max(2, beat.phase))[0])

    def _live_windows(self, beat: BeatSpec) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for owner, task in (
            pair for c in beat.cancels for pair in self.plan.tasks_of_group(c)
        ):
            key = id(task)
            if owner.at is None or key in self.sched.dropped_tasks:
                continue
            if key not in self.sched.task_times:
                continue
            at, hold = self.sched.task_times[key]
            out.append((at, at + hold))
        return out

    def _has_bite(self, beat: BeatSpec) -> bool:
        """Does anything later demand the opposite of what this frees (V29)?"""
        freed: dict[str, str] = {}
        released: set[int] = set()
        for group_key in beat.cancels:
            for _owner, task in self.plan.tasks_of_group(group_key):
                released.add(id(task))
                freed.update(self.require_of(task))
        if not freed:
            return False
        opposite = {d: ("open" if v == "closed" else "closed") for d, v in freed.items()}
        for other in self.plan.beats:
            for task in other.tasks:
                if id(task) in released or id(task) in self.sched.dropped_tasks:
                    continue
                require = self.require_of(task)
                if any(require.get(d) == v for d, v in opposite.items()):
                    return True
        return False

    def _place_temptations(self) -> None:
        """A tempting request is only tempting if a *different* thread's hold is
        live when it arrives (V17)."""
        self._stat_temptation_requested = 0
        self._stat_temptation_kept = 0
        for beat in self.plan.beats:
            if beat.kind != "tempting_request":
                continue
            self._stat_temptation_requested += 1
            target = self.plan.resolve_group(beat.targets_group)
            windows = []
            for owner, task in self.plan.tasks_of_group(target or ""):
                key = id(task)
                if owner.at is None or key in self.sched.dropped_tasks:
                    continue
                if key not in self.sched.task_times:
                    continue
                start, hold = self.sched.task_times[key]
                if hold <= 0:
                    continue
                windows.append((start, start + hold, owner.thread_key))
            windows = [w for w in windows if w[2] != beat.thread_key]
            if not windows:
                self.sched.notes.append(
                    f"{beat.key}: no live hold from another thread to tempt against "
                    f"(targets {target!r}) — dropped"
                )
                beat.at = None
                continue
            start, end, _ = max(windows, key=lambda w: w[1] - w[0])
            middle = start + (end - start) // 2
            beat.phase = phase_at(middle, self.duration)
            if self._place(beat, middle) >= 0:
                self._stat_temptation_kept += 1

    @staticmethod
    def _is_slot(beat: BeatSpec) -> bool:
        return beat.thread_key == "__slots"

    def _enforce_message_spacing(self) -> None:
        """No two messages closer than the minimum gap (V9).

        A pinned beat never moves -- it is pinned because something structural
        depends on the exact second -- so a crowded neighbour is pushed instead.
        """
        placed = sorted(
            (p for p in self.sched.placed if p.beat.at is not None),
            key=lambda p: (p.at, p.beat.key),
        )
        # The same ceiling `_place` uses: pushing an unpinned beat forward to
        # resolve a spacing clash must not walk it onto or past the pinned
        # end-of-shift seal either, or V21 breaks the same way it did before
        # `_seal_ceiling` existed -- this is the other place `_place`'s old
        # bare `duration - 40` ceiling used to leak through.
        ceiling = self._seal_ceiling()
        for _ in range(200):
            moved = False
            for earlier, later in zip(placed, placed[1:]):
                if later.beat.at - earlier.beat.at >= self.gap:
                    continue
                if self._is_slot(earlier.beat) and self._is_slot(later.beat):
                    continue
                if later.beat.pin_at is None:
                    later.beat.at = min(earlier.beat.at + self.gap, ceiling)
                    later.at = later.beat.at
                elif earlier.beat.pin_at is None:
                    earlier.beat.at = max(0, later.beat.at - self.gap)
                    earlier.at = earlier.beat.at
                else:
                    self.sched.notes.append(
                        f"{later.beat.key}: two pinned beats are {later.beat.at - earlier.beat.at}s "
                        "apart and neither can move"
                    )
                    continue
                moved = True
            if not moved:
                break
            placed.sort(key=lambda p: (p.beat.at, p.beat.key))

    def _separate_reimposition(self) -> None:
        """A withdrawal followed straight away by the same demand from the same
        actor reads as a mistake, and V31 rejects it. The retraction is moved
        earlier rather than the obligation later: the obligation has a reason to
        be where it is, and the retraction only has to land while its target is
        still live.
        """
        phase2 = self.phase_window(2)[0]
        for beat in self.plan.beats:
            if beat.kind != "retraction" or beat.at is None:
                continue
            freed: dict[str, str] = {}
            released: set[int] = set()
            first_start = None
            for group_key in beat.cancels:
                for owner, task in self.plan.tasks_of_group(group_key):
                    if id(task) not in self.sched.task_times:
                        continue
                    at, hold = self.sched.task_times[id(task)]
                    released.add(id(task))
                    first_start = at if first_start is None else min(first_start, at)
                    # Only what was still binding when the withdrawal landed.
                    if at <= beat.at <= at + hold or at > beat.at:
                        freed.update(self.require_of(task))
            if not freed:
                continue
            clashes = []
            for other in self.plan.beats:
                if other.at is None or other.actor_type != beat.actor_type:
                    continue
                for task in other.tasks:
                    if id(task) in self.sched.dropped_tasks or id(task) in released:
                        continue
                    if id(task) not in self.sched.task_times:
                        continue
                    at, _hold = self.sched.task_times[id(task)]
                    if not beat.at < at <= beat.at + 90:
                        continue
                    if any(self.require_of(task).get(d) == s for d, s in freed.items()):
                        clashes.append(at)
            if not clashes:
                continue
            floor = max(phase2, (first_start or 0) + 30)
            target = min(clashes) - 91
            if target >= floor:
                self.sched.notes.append(
                    f"{beat.key}: moved {beat.at}->{target}s so it is not undone 90s later "
                    "by the same actor"
                )
                beat.at = target
                for entry in self.sched.placed:
                    if entry.beat is beat:
                        entry.at = target
            else:
                self.sched.notes.append(
                    f"{beat.key}: cannot be separated from the obligation that re-imposes it"
                )

    def _task_start(self, beat: BeatSpec, task: TaskSpec) -> int:
        """V7: the obligation cannot open before the player could have read the
        instruction, plus slack."""
        assert beat.at is not None
        return int(math.ceil(beat.at + self.read_cost(beat) + self.slack + task.delay))

    def _cap_holds(self) -> None:
        cap = int(MAX_HOLD_FRACTION * self.duration)
        for beat in self.plan.beats:
            for task in beat.tasks:
                if task.hold > cap:
                    self.sched.notes.append(
                        f"{beat.key}: hold {task.hold}->{cap}s (a single obligation may "
                        f"not exceed {int(MAX_HOLD_FRACTION * 100)}% of the session)"
                    )
                    task.hold = cap

    def _floor_retracted_holds(self) -> None:
        """Give every withdrawn obligation room to be withdrawn."""
        for beat in self.plan.beats:
            if beat.kind != "retraction":
                continue
            for group_key in (self.plan.resolve_group(c) for c in beat.cancels):
                if not group_key:
                    continue
                pairs = self.plan.tasks_of_group(group_key)
                held = [t for _o, t in pairs if t.hold > 0]
                if not held or max(t.hold for t in held) >= RETRACTED_MIN_HOLD:
                    continue
                longest = max(held, key=lambda t: t.hold)
                self.sched.notes.append(
                    f"{beat.key}: lengthened the obligation it withdraws from "
                    f"{longest.hold}s to {RETRACTED_MIN_HOLD}s so the withdrawal has "
                    "somewhere to land"
                )
                longest.hold = RETRACTED_MIN_HOLD

    def _assign_task_times(self) -> None:
        self._floor_retracted_holds()
        self._cap_holds()
        for beat in self.plan.beats:
            if beat.at is None:
                continue
            for task in beat.tasks:
                if id(task) in self.sched.dropped_tasks:
                    continue
                at = self._task_start(beat, task)
                hold = task.hold
                tail = SEAL_TAIL if task.seal_station else ORDINARY_TAIL
                if at > self.duration - tail:
                    # The instruction lands too late for its own obligation to
                    # fit. Shortening it is not an option; there is no room.
                    self.sched.notes.append(
                        f"{beat.key}: obligation would start at {at}s, past the end of the "
                        "session — dropped"
                    )
                    self.sched.dropped_tasks.add(id(task))
                    continue
                if at + hold > self.duration - tail:
                    hold = max(0, self.duration - tail - at)
                    if task.hold > 0 and hold < 30:
                        hold = min(task.hold, max(30, self.duration - tail - at))
                    self.sched.notes.append(
                        f"{beat.key}: hold shortened {task.hold}->{hold}s to fit the session"
                    )
                self.sched.task_times[id(task)] = (at, hold)

    def _forbidden(self) -> list[tuple[int, int]]:
        clear = int(self.diff["challenge_task_clearance_seconds"])
        zones: list[tuple[int, int]] = []
        for at, hold in self.sched.task_times.values():
            zones.append((at - clear, at + clear))
            zones.append((at + hold - clear, at + hold + clear))
        return sorted(zones)

    def _place_challenges(self) -> None:
        """Three in-session challenges after the halfway mark, 120 s apart, none
        within the clearance of a deadline (V11, V12)."""
        in_session = [c for c in self.plan.challenges if c.slot == "in_session"]
        zones = self._forbidden()
        nominal = self._nominal_challenge_times()
        chosen: list[int] = []
        # The slot was reserved at the nominal second and the obligations were
        # moved clear of it, so the common case is that it stays exactly there.
        # The search below only runs when something still overlaps.
        for index, challenge in enumerate(in_session):
            cursor = nominal[index] if index < len(nominal) else (
                (chosen[-1] + 130) if chosen else int(0.6 * self.duration)
            )
            at = max(cursor, int(0.5 * self.duration) + 5)
            guard = 0
            # Density is not re-checked here: `_reserve_challenge_slots` already
            # booked this second's reading cost, so checking again would count it
            # twice and walk the question to the end of the shift.
            while at < self.duration - 30 and guard < 5000:
                if any(lo < at < hi for lo, hi in zones):
                    at += 1
                elif chosen and at - chosen[-1] < 125:
                    at = chosen[-1] + 125
                else:
                    break
                guard += 1
            if at >= self.duration - 30:
                self.sched.notes.append(
                    f"{challenge.key}: no clear slot found before the end of the session"
                )
                at = min(at, self.duration - 30)
            challenge.at = at
            chosen.append(at)
        for i, challenge in enumerate(
            [c for c in self.plan.challenges if c.slot == "debrief"]
        ):
            challenge.at = self.duration  # untimed; the debrief runs after the clock
        self.sched.notes.append(f"in-session challenges at {chosen}")

    def _recompute_phase_spans(self) -> None:
        """Derive each thread's declared span from where its messages actually
        landed, so V22 can never fail on a rounding difference."""
        for thread in self.plan.threads:
            phases = [
                phase_at(b.at, self.duration) for b in thread.beats if b.at is not None
            ]
            thread.phase_span = (min(phases), max(phases)) if phases else (1, 1)
