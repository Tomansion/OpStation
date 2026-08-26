"""The perfect-player simulation (spec 13.3, V14).

Simulate a player who, from the fixed station start state, performs the minimum
set of toggles that satisfies every task at the latest safe moment. If any task
still fails, the scenario is unsolvable and must be rejected -- no amount of
memory would save the player.

The resulting trace is not only a pass/fail signal. It is what V15 (no
already-satisfied instruction) and V16 (no redundant re-requirement) reason
about, and it is rendered on the admin page beside the player's actual door
timeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Scenario, Task
from ..station import Station, door_sort_key


@dataclass(frozen=True)
class Constraint:
    """One door held in one state over one closed interval, from one task."""

    door: str
    state: str
    start: float
    end: float  # inclusive
    task_id: str

    def overlaps(self, other: "Constraint") -> bool:
        return self.start <= other.end and other.start <= self.end


@dataclass(frozen=True)
class Toggle:
    at: float
    door: str
    to_state: str
    because: str  # task id that demanded it


@dataclass
class Trace:
    initial: dict[str, str]
    toggles: list[Toggle] = field(default_factory=list)

    def state_at(self, door: str, t: float) -> str:
        state = self.initial[door]
        for tog in self.toggles:
            if tog.door == door and tog.at <= t:
                state = tog.to_state
            elif tog.at > t:
                break
        return state

    def changed_in(self, door: str, lo: float, hi: float) -> list[Toggle]:
        """Toggles in (lo, hi] -- the window V15 asks about."""
        return [t for t in self.toggles if t.door == door and lo < t.at <= hi]

    def as_json(self) -> list[dict]:
        return [
            {"at": t.at, "door": t.door, "to": t.to_state, "because": t.because}
            for t in self.toggles
        ]


@dataclass
class Conflict:
    door: str
    a: Constraint
    b: Constraint

    def describe(self) -> str:
        return (
            f"{self.door}: {self.a.task_id} requires {self.a.state} over "
            f"[{self.a.start:g},{self.a.end:g}] while {self.b.task_id} requires "
            f"{self.b.state} over [{self.b.start:g},{self.b.end:g}]"
        )


@dataclass
class Simulation:
    trace: Trace
    constraints: list[Constraint]
    conflicts: list[Conflict]
    cancelled_task_ids: set[str]
    truncated_task_ids: dict[str, float]
    failed_task_ids: list[str]
    cancellation_times: dict[str, float]

    @property
    def solvable(self) -> bool:
        return not self.conflicts and not self.failed_task_ids

    def is_live(self, task_id: str) -> bool:
        return task_id not in self.cancelled_task_ids

    def report(self) -> dict:
        return {
            "solvable": self.solvable,
            "toggles": self.trace.as_json(),
            "initial": self.trace.initial,
            "cancelled_tasks": sorted(self.cancelled_task_ids),
            "truncated_tasks": self.truncated_task_ids,
            "conflicts": [c.describe() for c in self.conflicts],
            "failed_tasks": self.failed_task_ids,
        }


def cancellation_times(scenario: Scenario) -> dict[str, float]:
    """When each obligation id stops being monitored.

    A cancellation takes effect at `message.at` -- on delivery, not on
    acknowledgement (spec 6.7), so that the ground truth does not depend on how
    fast the player clicks.
    """
    out: dict[str, float] = {}
    for msg in scenario.sorted_messages():
        for target in msg.cancels:
            if target not in out or msg.at < out[target]:
                out[target] = float(msg.at)
    return out


def effective_window(
    task: Task, cancels: dict[str, float], tick: float
) -> tuple[float, float] | None:
    """The window a task is actually monitored over, given cancellations.

    Returns None if the task is cancelled before it ever starts. A cancellation
    that lands mid-`hold` truncates the window rather than erasing it: the
    obligation was real for the part of the window that already elapsed, and a
    failure that already fired cannot be taken back.
    """
    cancel_at = min(
        (t for t in (cancels.get(task.group_id), cancels.get(task.id)) if t is not None),
        default=None,
    )
    start, end = float(task.at), float(task.until)
    if cancel_at is None:
        return start, end
    if cancel_at <= start:
        return None
    return start, min(end, cancel_at - tick)


def simulate(scenario: Scenario, station: Station, tick: float = 0.25) -> Simulation:
    cancels = cancellation_times(scenario)
    cancelled: set[str] = set()
    truncated: dict[str, float] = {}
    constraints: list[Constraint] = []

    for task in sorted(scenario.tasks, key=lambda t: (t.at, t.id)):
        window = effective_window(task, cancels, tick)
        if window is None:
            cancelled.add(task.id)
            continue
        start, end = window
        if end < float(task.until):
            truncated[task.id] = end
        for door, state in sorted(task.require.items(), key=lambda kv: door_sort_key(kv[0])):
            # A door that does not exist is V4's finding to report. The
            # simulation has to survive it, because the validator owes the
            # generator a full report rather than a traceback.
            if door in station.doors:
                constraints.append(Constraint(door, state, start, end, task.id))

    # A contradiction between two live obligations on one door is not something
    # the player can play around, so it is found before any toggle is planned.
    conflicts: list[Conflict] = []
    by_door: dict[str, list[Constraint]] = {}
    for c in constraints:
        by_door.setdefault(c.door, []).append(c)
    for door, group in by_door.items():
        group.sort(key=lambda c: (c.start, c.end, c.task_id))
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if b.start > a.end:
                    break
                if a.state != b.state:
                    conflicts.append(Conflict(door, a, b))

    # Minimum toggles, each at the latest safe moment: exactly when the window
    # opens. Between windows a door is left wherever the last obligation put it.
    trace = Trace(initial=station.initial_states())
    for door, group in sorted(by_door.items(), key=lambda kv: door_sort_key(kv[0])):
        state = trace.initial[door]
        for c in group:
            if state != c.state:
                trace.toggles.append(Toggle(c.start, door, c.state, c.task_id))
                state = c.state
    trace.toggles.sort(key=lambda t: (t.at, door_sort_key(t.door)))

    # Replay the planned trace against every live task. With no conflicts this
    # should be vacuously true; it is checked anyway, because a silent bug here
    # would publish an unplayable scenario.
    failed: list[str] = []
    for task in scenario.tasks:
        if task.id in cancelled:
            continue
        window = effective_window(task, cancels, tick)
        if window is None:
            continue
        start, end = window
        if _violated(trace, task, start, end, tick):
            failed.append(task.id)

    return Simulation(
        trace=trace,
        constraints=constraints,
        conflicts=conflicts,
        cancelled_task_ids=cancelled,
        truncated_task_ids=truncated,
        failed_task_ids=failed,
        cancellation_times=cancels,
    )


def _violated(trace: Trace, task: Task, start: float, end: float, tick: float) -> bool:
    """Walk the window at tick resolution, exactly as the runtime does."""
    for door, want in task.require.items():
        if door not in trace.initial:
            continue
        t = start
        while t <= end + 1e-9:
            if trace.state_at(door, t) != want:
                return True
            t += tick
        if trace.state_at(door, end) != want:
            return True
    return False
