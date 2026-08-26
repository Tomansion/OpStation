"""The intermediate form between the LLM and a scenario.

The LLM writes fiction and structure: who says what, in which phase, which
obligation it creates, how long the hold is. It never writes a timestamp.
Every `at` in the finished scenario is computed here and in `schedule.py`,
because most of the validator's timing rules are arithmetic and a language model
is the wrong tool for arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def as_text(value: Any, default: str = "") -> str:
    """Coerce whatever the model returned into a string.

    Models are inconsistent about singular-or-list for fields like `creates`,
    and a generation run that crashes on the shape of one field wastes every
    call that came before it.
    """
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        return as_text(value[0], default) if value else default
    if isinstance(value, dict):
        for key in ("key", "id", "name"):
            if key in value:
                return as_text(value[key], default)
        return default
    return str(value).strip()


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [t for t in (as_text(v) for v in value) if t]
    text = as_text(value)
    return [text] if text else []


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


@dataclass
class TaskSpec:
    hold: int
    fail_message: str
    require: dict[str, str] = field(default_factory=dict)
    isolation_target: str | None = None
    include_hangar_doors: bool = False
    #: extra seconds after the message's reading time before the window opens
    delay: int = 0
    seal_station: bool = False

    @classmethod
    def parse(cls, raw: dict) -> "TaskSpec":
        require = raw.get("require") or {}
        if not isinstance(require, dict):
            require = {}
        return cls(
            hold=max(0, as_int(raw.get("hold"), 0)),
            fail_message=as_text(raw.get("fail_message")),
            require={
                as_text(k).upper(): as_text(v).lower()
                for k, v in require.items()
                if as_text(v).lower() in ("open", "closed")
            },
            isolation_target=as_text(raw.get("isolation_target")) or None,
            include_hangar_doors=bool(raw.get("include_hangar_doors", False)),
            delay=max(0, as_int(raw.get("delay"), 0)),
            seal_station=bool(raw.get("seal_station", False)),
        )


@dataclass
class BeatSpec:
    """One message, with whatever obligation it carries."""

    key: str
    thread_key: str
    phase: int
    actor_type: str
    channel: str
    kind: str
    text: str
    creates_group: str | None = None
    cancels: list[str] = field(default_factory=list)
    retraction_style: str | None = None
    targets_group: str | None = None  # tempting_request: whose hold it pulls against
    tasks: list[TaskSpec] = field(default_factory=list)
    at: int | None = None  # filled by the scheduler
    #: Set only for structurally-required beats (the end-of-shift seal), which
    #: must land at an exact second rather than wherever the density rule allows.
    pin_at: int | None = None

    @classmethod
    def parse(cls, raw: dict, thread_key: str) -> "BeatSpec":
        tasks = raw.get("tasks")
        if isinstance(tasks, dict):
            tasks = [tasks]
        return cls(
            key=as_text(raw.get("key")) or "b",
            thread_key=thread_key,
            phase=min(5, max(1, as_int(raw.get("phase"), 1))),
            actor_type=as_text(raw.get("actor"), "system"),
            channel=as_text(raw.get("channel"), "text"),
            kind=as_text(raw.get("kind"), "status"),
            text=as_text(raw.get("text")),
            creates_group=as_text(raw.get("creates")) or None,
            cancels=as_list(raw.get("cancels")),
            retraction_style=as_text(raw.get("retraction_style")) or None,
            targets_group=as_text(raw.get("targets")) or None,
            tasks=[TaskSpec.parse(t) for t in (tasks or []) if isinstance(t, dict)],
        )


@dataclass
class GroupSpec:
    key: str
    thread_key: str
    label: str


@dataclass
class ThreadSpec:
    key: str
    title: str
    catalogue_key: str
    grade: str  # ordinary | finale | everyday
    debrief_summary: str
    beats: list[BeatSpec] = field(default_factory=list)
    groups: list[GroupSpec] = field(default_factory=list)
    dormant_after: str | None = None  # beat key after which the thread goes quiet
    #: Derived from where the beats actually landed, never declared by the LLM.
    phase_span: tuple[int, int] = (1, 1)


@dataclass
class ChallengeSpec:
    key: str
    slot: str
    kind: str
    thread_key: str
    actor_type: str
    channel: str
    pretext: str
    prompt: str
    explanation: str
    options: list[dict[str, Any]]
    depends_on: list[str] = field(default_factory=list)
    at: int | None = None


@dataclass
class Plan:
    name: str
    duration_seconds: int
    actor_names: dict[str, str]
    threads: list[ThreadSpec] = field(default_factory=list)
    challenges: list[ChallengeSpec] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------ lookups

    @property
    def beats(self) -> list[BeatSpec]:
        return [b for t in self.threads for b in t.beats]

    @property
    def groups(self) -> list[GroupSpec]:
        return [g for t in self.threads for g in t.groups]

    def thread_of(self, key: str) -> ThreadSpec | None:
        return next((t for t in self.threads if t.key == key), None)

    def group(self, key: str) -> GroupSpec | None:
        return next((g for g in self.groups if g.key == key), None)

    def resolve_group(self, raw: str | None) -> str | None:
        """Match an obligation key the LLM wrote against the namespaced key.

        Later stages see obligation keys that were namespaced per thread, but the
        model tends to answer with the name it invented in its own stage. Rather
        than lose the reference (a dropped temptation or a dead retraction), the
        name is matched by suffix.
        """
        if not raw:
            return None
        if self.group(raw):
            return raw
        bare = raw[3:] if raw.startswith("og_") else raw
        for group in self.groups:
            tail = group.key.split("__", 1)[-1]
            if tail == bare or group.key == bare or group.key.endswith(f"_{bare}"):
                return group.key
        for group in self.groups:
            if bare and bare in group.key:
                return group.key
        return None

    def beats_creating(self, group_key: str) -> list[BeatSpec]:
        return [b for b in self.beats if b.creates_group == group_key]

    def tasks_of_group(self, group_key: str) -> list[tuple[BeatSpec, TaskSpec]]:
        return [
            (b, t) for b in self.beats if b.creates_group == group_key for t in b.tasks
        ]
