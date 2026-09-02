"""Scenario data model (spec 11.1).

These models parse and re-serialise a `scenario.json`. They deliberately do
almost no validating beyond shape and enums -- everything that makes a scenario
*playable* is a validator rule (spec 13), because the validator has to produce a
report the LLM can repair from, not an exception.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DoorState = Literal["open", "closed"]
Channel = Literal["text", "radio"]
Slot = Literal["in_session", "debrief"]


class Base(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Actor(Base):
    id: str
    type: str
    name: str
    portrait: str
    voice: str


class Thread(Base):
    id: str
    title: str
    catalogue_key: str
    grade: Literal["ordinary", "finale", "everyday", "conflicts"]
    phase_span: tuple[int, int]
    debrief_summary: str


class TaskGroup(Base):
    id: str
    thread_id: str
    label: str


class DerivedFrom(Base):
    """Records that a task's explicit `require` map came from a named isolation
    target, so V23 can recompute the cut-set and check them against each other."""

    isolation_target: str
    include_hangar_doors: bool = False


class Task(Base):
    id: str
    group_id: str
    message_id: str
    at: int
    hold: int = 0
    require: dict[str, DoorState]
    fail_message: str
    derived_from: DerivedFrom | None = None
    #: True for a task with no hold and no delay: an instruction that asked for
    #: something right now, checked right now. These are the only tasks worth
    #: confirming -- anything with a hold is judged much later, when its own
    #: pass is silent and unremarkable.
    confirm: bool = False

    @property
    def until(self) -> int:
        return self.at + self.hold

    def window(self) -> tuple[int, int]:
        return (self.at, self.until)


class Message(Base):
    id: str
    at: int
    thread_id: str
    actor_id: str
    channel: Channel
    kind: str
    text: str
    task_group_id: str | None = None
    audio: str | None = None
    audio_duration: float | None = None
    read_cost: float | None = None
    # retraction only (spec 6.7)
    cancels: list[str] = Field(default_factory=list)
    retraction_style: str | None = None


class Option(Base):
    id: str
    text: str
    correct: bool = False


class Challenge(Base):
    id: str
    at: int
    slot: Slot
    kind: str
    thread_id: str
    actor_id: str
    channel: Channel
    prompt: str
    options: list[Option]
    explanation: str
    pretext: str | None = None
    #: Message / task-group ids the correct answer depends on. Declared by the
    #: generator so V19 can check they were all delivered before `at`, and so a
    #: retraction can prove it has teeth through a challenge (V29 form 2).
    depends_on: list[str] = Field(default_factory=list)
    audio: str | None = None
    audio_duration: float | None = None

    def correct_option(self) -> Option | None:
        return next((o for o in self.options if o.correct), None)


class GeneratorInfo(Base):
    model: str = ""
    template_version: str = ""
    seed: int | None = None
    attempts: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class Scenario(Base):
    scenario_id: str
    name: str
    duration_seconds: int
    station_version: str
    actors: list[Actor]
    threads: list[Thread]
    task_groups: list[TaskGroup]
    messages: list[Message]
    tasks: list[Task]
    challenges: list[Challenge] = Field(default_factory=list)
    debrief_challenges: list[Challenge] = Field(default_factory=list)
    generated_at: str = ""
    generator: GeneratorInfo = Field(default_factory=GeneratorInfo)
    difficulty_fingerprint: dict[str, Any] = Field(default_factory=dict)
    status: Literal["valid", "invalid", "draft"] = "draft"
    retractions_note: str | None = None

    # ------------------------------------------------------------ conveniences

    def by_id(self, kind: str) -> dict[str, Any]:
        return {item.id: item for item in getattr(self, kind)}

    @property
    def actors_by_id(self) -> dict[str, Actor]:
        return {a.id: a for a in self.actors}

    @property
    def threads_by_id(self) -> dict[str, Thread]:
        return {t.id: t for t in self.threads}

    @property
    def groups_by_id(self) -> dict[str, TaskGroup]:
        return {g.id: g for g in self.task_groups}

    @property
    def messages_by_id(self) -> dict[str, Message]:
        return {m.id: m for m in self.messages}

    @property
    def tasks_by_id(self) -> dict[str, Task]:
        return {t.id: t for t in self.tasks}

    @property
    def all_challenges(self) -> list[Challenge]:
        return list(self.challenges) + list(self.debrief_challenges)

    def tasks_of_group(self, group_id: str) -> list[Task]:
        return sorted(
            (t for t in self.tasks if t.group_id == group_id), key=lambda t: (t.at, t.id)
        )

    def retractions(self) -> list[Message]:
        return [m for m in self.messages if m.kind == "retraction"]

    def sorted_messages(self) -> list[Message]:
        return sorted(self.messages, key=lambda m: (m.at, m.id))

    # -------------------------------------------------------------------- io

    @classmethod
    def load(cls, path: Path) -> "Scenario":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def dump(self, path: Path) -> None:
        payload = self.model_dump(mode="json", exclude_none=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
