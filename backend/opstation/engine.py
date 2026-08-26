"""The session runtime.

Deterministic and driven by an explicit clock: `advance_to(elapsed)` and
`toggle_door(door, at)`. Nothing here knows about asyncio, WebSockets or
persistence, so a whole 27-minute session can be replayed in a millisecond in a
test. `session.py` wraps this in the real clock.

Two evaluation triggers, which together make failure exact:

* every tick, to open and close task windows and deliver traffic;
* every door toggle, because "the failure fires at the moment of violation"
  (spec 6.2) and a 250 ms tick would otherwise let a player open and reclose a
  door between samples.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from .config import DONT_KNOW_OPTION_ID, Difficulty, difficulty as load_difficulty
from .models import Challenge, Message, Scenario, Task
from .station import Station, station as load_station

TaskState = Literal["pending", "active", "passed", "failed", "cancelled"]
Phase = Literal["running", "debrief", "complete", "aborted"]


@dataclass
class QueueItem:
    """One thing waiting in the FIFO queue (spec 5.2).

    The player is never told who is calling or how urgent it is before opening
    it -- only that one is waiting.
    """

    uid: str
    kind: Literal["message", "failure_notice", "challenge"]
    ref_id: str
    delivered_at: float
    opened_at: float | None = None
    acknowledged_at: float | None = None
    answered_at: float | None = None
    answer_option_id: str | None = None
    answer_outcome: str | None = None  # correct | wrong | dont_know
    audio_played: bool = False
    text: str = ""
    actor_id: str | None = None
    channel: str = "text"
    withdrawn_at: float | None = None  # removed unread because its task failed

    @property
    def is_open(self) -> bool:
        return self.opened_at is not None and self.acknowledged_at is None

    @property
    def is_done(self) -> bool:
        return self.acknowledged_at is not None or self.withdrawn_at is not None

    @property
    def needs_answer(self) -> bool:
        return self.kind == "challenge" and self.answered_at is None


@dataclass
class Event:
    """Append-only session log. The player never sees it; the admin page is
    built entirely from it (spec 14.5)."""

    at: float
    kind: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict:
        return {"at": round(self.at, 3), "kind": self.kind, **self.detail}


@dataclass
class TaskOutcome:
    task_id: str
    group_id: str
    thread_id: str
    state: TaskState
    at: float
    resolved_at: float | None = None
    failed_door: str | None = None
    requested_by: str | None = None
    requested_at: float | None = None


class Engine:
    """One session. Not thread-safe; the runner owns it."""

    def __init__(
        self,
        scenario: Scenario,
        *,
        station: Station | None = None,
        difficulty: Difficulty | None = None,
    ) -> None:
        self.scenario = scenario
        self.station = station or load_station()
        self.difficulty = difficulty or load_difficulty()

        self.elapsed: float = 0.0
        self.phase: Phase = "running"
        self.penalties: int = 0
        #: Door states at session start are fixed by the station definition and
        #: are never a per-scenario field (spec 3.4).
        self.door_states: dict[str, str] = self.station.initial_states()

        self.queue: list[QueueItem] = []
        self.events: list[Event] = []

        self._uids = itertools.count(1)
        self._delivered_messages: set[str] = set()
        self._delivered_challenges: set[str] = set()
        self._task_state: dict[str, TaskState] = {t.id: "pending" for t in scenario.tasks}
        self._task_resolved_at: dict[str, float] = {}
        self._task_failed_door: dict[str, str] = {}
        self._cancelled_by: dict[str, str] = {}
        self._last_notice: dict[str, float] = {}
        self._tasks_by_door: dict[str, list[Task]] = {}
        for task in scenario.tasks:
            for door in task.require:
                self._tasks_by_door.setdefault(door, []).append(task)
        self._groups = scenario.groups_by_id
        self._messages = scenario.messages_by_id
        self._challenges = {c.id: c for c in scenario.all_challenges}
        self._debrief_queued = False

    # ------------------------------------------------------------------ clock

    def advance_to(self, t: float) -> list[Event]:
        """Run the world forward to `t` seconds after session start.

        Events between `self.elapsed` and `t` are processed in chronological
        order, not in a single lump, so a long stall (a slow tick, a paused
        laptop) produces exactly the same outcome as a smooth run.
        """
        before = len(self.events)
        if self.phase not in ("running",):
            self.elapsed = max(self.elapsed, t)
            return self.events[before:]
        limit = min(t, float(self.scenario.duration_seconds))
        while True:
            nxt = self._next_event_time(limit)
            if nxt is None:
                break
            self.elapsed = nxt
            self._process_at(nxt)
        self.elapsed = max(self.elapsed, min(t, float(self.scenario.duration_seconds)))
        if t >= self.scenario.duration_seconds:
            self.elapsed = float(self.scenario.duration_seconds)
            self._end_session()
        return self.events[before:]

    def _next_event_time(self, limit: float) -> float | None:
        candidates: list[float] = []
        for msg in self.scenario.messages:
            if msg.id not in self._delivered_messages and self.elapsed <= msg.at <= limit:
                candidates.append(float(msg.at))
        for ch in self.scenario.challenges:
            if ch.id not in self._delivered_challenges and self.elapsed <= ch.at <= limit:
                candidates.append(float(ch.at))
        for task in self.scenario.tasks:
            state = self._task_state[task.id]
            if state == "pending" and self.elapsed <= task.at <= limit:
                candidates.append(float(task.at))
            elif state == "active" and self.elapsed <= task.until <= limit:
                candidates.append(float(task.until))
        return min(candidates) if candidates else None

    def _process_at(self, now: float) -> None:
        # Deliveries first: a retraction landing on the same second as the task
        # it withdraws must cancel it rather than let it start.
        for msg in sorted(self.scenario.messages, key=lambda m: m.id):
            if msg.id not in self._delivered_messages and msg.at <= now:
                self._deliver_message(msg, now)
        for ch in sorted(self.scenario.challenges, key=lambda c: c.id):
            if ch.id not in self._delivered_challenges and ch.at <= now:
                self._deliver_challenge(ch, now)
        for task in self.scenario.tasks:
            if self._task_state[task.id] == "pending" and task.at <= now:
                self._activate(task, now)
        for task in self.scenario.tasks:
            if self._task_state[task.id] == "active" and task.until <= now:
                if self._check(task, now):
                    self._pass_task(task, now)

    # -------------------------------------------------------------- delivery

    def _deliver_message(self, msg: Message, now: float) -> None:
        self._delivered_messages.add(msg.id)
        # A cancellation takes effect on delivery, not on acknowledgement, so
        # the ground truth never depends on how fast the player clicks.
        for target in msg.cancels:
            self._cancel_obligation(target, now, by=msg.id)
        item = QueueItem(
            uid=f"q{next(self._uids)}",
            kind="message",
            ref_id=msg.id,
            delivered_at=now,
            text=msg.text,
            actor_id=msg.actor_id,
            channel=msg.channel,
        )
        self.queue.append(item)
        self._log(now, "message_delivered", message_id=msg.id, uid=item.uid,
                  message_kind=msg.kind)

    def _deliver_challenge(self, ch: Challenge, now: float) -> None:
        self._delivered_challenges.add(ch.id)
        item = QueueItem(
            uid=f"q{next(self._uids)}",
            kind="challenge",
            ref_id=ch.id,
            delivered_at=now,
            text=ch.prompt,
            actor_id=ch.actor_id,
            channel=ch.channel,
        )
        self.queue.append(item)
        self._log(now, "challenge_delivered", challenge_id=ch.id, uid=item.uid, slot=ch.slot)

    def _deliver_failure_notice(self, task: Task, now: float) -> None:
        """At most one notice per task group per cooldown. The cooldown is the
        only guard against a failure cascade burying the messages the player
        needs in order to recover (spec 7) -- the penalty is recorded either
        way."""
        cooldown = self.difficulty["failure_notice_cooldown_seconds"]
        last = self._last_notice.get(task.group_id)
        if last is not None and now - last < cooldown:
            self._log(
                now, "failure_notice_suppressed", task_id=task.id, group_id=task.group_id,
                since_last=round(now - last, 2),
            )
            return
        self._last_notice[task.group_id] = now
        item = QueueItem(
            uid=f"q{next(self._uids)}",
            kind="failure_notice",
            ref_id=task.id,
            delivered_at=now,
            text=task.fail_message,
            channel="text",
        )
        self.queue.append(item)
        self._log(now, "failure_notice_delivered", task_id=task.id, uid=item.uid)

    # ----------------------------------------------------------------- tasks

    def _activate(self, task: Task, now: float) -> None:
        self._task_state[task.id] = "active"
        self._log(now, "task_window_open", task_id=task.id, group_id=task.group_id,
                  hold=task.hold, require=dict(task.require))
        if not self._check(task, now):
            return
        if task.hold == 0:
            self._pass_task(task, now)

    def _check(self, task: Task, now: float) -> bool:
        """True if the task still holds. On the first mismatch the task fails
        here and now, and monitoring stops -- one broken obligation, one
        penalty."""
        for door, want in task.require.items():
            if self.door_states.get(door) != want:
                self._fail_task(task, now, door)
                return False
        return True

    def _pass_task(self, task: Task, now: float) -> None:
        self._task_state[task.id] = "passed"
        self._task_resolved_at[task.id] = now
        self._log(now, "task_passed", task_id=task.id, group_id=task.group_id)

    def _fail_task(self, task: Task, now: float, door: str) -> None:
        self._task_state[task.id] = "failed"
        self._task_resolved_at[task.id] = now
        self._task_failed_door[task.id] = door
        self.penalties += self.difficulty["penalty_per_failed_task"]
        self._log(
            now, "task_failed", task_id=task.id, group_id=task.group_id, door=door,
            was=self.door_states.get(door), wanted=task.require[door],
        )
        # Cascade: the group is one obligation, so the rest of it is cancelled
        # rather than failed. No false credit, no double penalty (spec 6.3).
        for sibling in self.scenario.tasks_of_group(task.group_id):
            if sibling.id != task.id and self._task_state[sibling.id] in ("pending", "active"):
                self._task_state[sibling.id] = "cancelled"
                self._cancelled_by[sibling.id] = f"cascade:{task.id}"
                self._log(now, "task_cancelled", task_id=sibling.id, reason="cascade",
                          because=task.id)
        # If the instruction is still sitting unread, it is pulled from the
        # queue and the consequence arrives instead (spec 5.2).
        for item in self.queue:
            if (
                item.kind == "message"
                and item.ref_id == task.message_id
                and not item.is_done
                and item.opened_at is None
            ):
                item.withdrawn_at = now
                self._log(now, "message_withdrawn_unread", message_id=item.ref_id,
                          uid=item.uid, because=task.id)
        self._deliver_failure_notice(task, now)

    def _cancel_obligation(self, target: str, now: float, by: str) -> None:
        if target in self._groups:
            tasks = self.scenario.tasks_of_group(target)
        elif target in self.scenario.tasks_by_id:
            tasks = [self.scenario.tasks_by_id[target]]
        else:
            self._log(now, "cancel_unresolved", target=target, by=by)
            return
        for task in tasks:
            if self._task_state[task.id] in ("pending", "active"):
                self._task_state[task.id] = "cancelled"
                self._cancelled_by[task.id] = by
                self._log(now, "task_cancelled", task_id=task.id, reason="retraction", by=by)

    # --------------------------------------------------------- player actions

    def toggle_door(self, door: str, now: float | None = None) -> dict:
        """The player's only physical action. Never blocked: no door is ever
        locked, and the challenge modal does not lock the canvas either."""
        now = self.elapsed if now is None else now
        if door not in self.door_states:
            raise KeyError(f"unknown door {door!r}")
        if self.phase not in ("running", "debrief"):
            return {"door": door, "state": self.door_states[door], "ignored": True}
        new = "closed" if self.door_states[door] == "open" else "open"
        self.door_states[door] = new
        self._log(now, "door_toggled", door=door, state=new)
        # Evaluate immediately: failure fires at the moment of violation.
        if self.phase == "running":
            for task in self._tasks_by_door.get(door, []):
                if self._task_state[task.id] == "active":
                    self._check(task, now)
        return {"door": door, "state": new}

    def set_door(self, door: str, state: str, now: float | None = None) -> dict:
        if self.door_states.get(door) == state:
            return {"door": door, "state": state}
        return self.toggle_door(door, now)

    def open_notification(self, now: float | None = None) -> QueueItem | None:
        """Open the front of the queue. Only the oldest is ever presented."""
        now = self.elapsed if now is None else now
        item = self.front()
        if item is None:
            return None
        if item.opened_at is None:
            item.opened_at = now
            self._log(now, "item_opened", uid=item.uid, item_kind=item.kind, ref=item.ref_id)
        return item

    def acknowledge(self, uid: str, now: float | None = None) -> bool:
        """Dismiss the open modal. Once acknowledged it is gone forever -- there
        is no way back to it."""
        now = self.elapsed if now is None else now
        item = self.front()
        if item is None or item.uid != uid or item.opened_at is None:
            return False
        if item.needs_answer:
            return False  # a challenge must be answered before it can be dismissed
        item.acknowledged_at = now
        self._log(now, "item_acknowledged", uid=uid, item_kind=item.kind, ref=item.ref_id)
        return True

    def answer_challenge(self, uid: str, option_id: str, now: float | None = None) -> dict | None:
        """Answering is mandatory, untimed, and does not stop the clock."""
        now = self.elapsed if now is None else now
        item = self.front()
        if item is None or item.uid != uid or item.kind != "challenge":
            return None
        if item.answered_at is not None:
            return None
        ch = self._challenges[item.ref_id]
        if option_id == DONT_KNOW_OPTION_ID:
            outcome = "dont_know"
            cost = self.difficulty["penalty_per_dont_know"]
        else:
            option = next((o for o in ch.options if o.id == option_id), None)
            if option is None:
                return None
            outcome = "correct" if option.correct else "wrong"
            cost = 0 if option.correct else self.difficulty["penalty_per_wrong_answer"]
        item.answered_at = now
        item.answer_option_id = option_id
        item.answer_outcome = outcome
        self.penalties += cost
        self._log(now, "challenge_answered", challenge_id=ch.id, option_id=option_id,
                  outcome=outcome, cost=cost, slot=ch.slot)
        correct = ch.correct_option()
        return {
            "challenge_id": ch.id,
            "outcome": outcome,
            "penalty": cost,
            "correct_option_id": correct.id if correct else None,
            "explanation": ch.explanation,
        }

    def mark_audio_played(self, uid: str) -> None:
        for item in self.queue:
            if item.uid == uid:
                item.audio_played = True

    def on_reconnect(self, now: float) -> None:
        """An open-but-unacknowledged modal returns as unopened, at the front of
        the queue (spec 14.3), so a refresh never strands the player.

        A radio message is marked heard on the way back, because the only route
        from an open modal to the queue is a reconnect -- and replay is the one
        thing the game exists to remove. The mark happens here rather than when
        the message is opened: doing it at open time would make the very first
        listen count as already spent.
        """
        item = self.front()
        if item is not None and item.opened_at is not None and item.acknowledged_at is None:
            item.opened_at = None
            if item.channel == "radio":
                item.audio_played = True
            self._log(now, "item_returned_to_queue", uid=item.uid,
                      audio_already_played=item.audio_played)

    # ------------------------------------------------------------------- end

    def _end_session(self) -> None:
        if self.phase != "running":
            return
        live = [
            t for t in self.scenario.tasks if self._task_state[t.id] in ("pending", "active")
        ]
        for task in live:
            # The session always runs to completion, so an obligation still open
            # at the final second is judged on the state it is in.
            if self._task_state[task.id] == "active" and self._check(task, self.elapsed):
                self._pass_task(task, self.elapsed)
            elif self._task_state[task.id] == "pending":
                self._task_state[task.id] = "cancelled"
                self._cancelled_by[task.id] = "session_ended"
        self.phase = "debrief"
        self._log(self.elapsed, "session_ended", penalties=self.penalties)
        self._queue_debrief()

    def _queue_debrief(self) -> None:
        """The debrief is untimed: nothing can fail by then, so it measures
        retained knowledge rather than reaction speed."""
        if self._debrief_queued:
            return
        self._debrief_queued = True
        for ch in self.scenario.debrief_challenges:
            item = QueueItem(
                uid=f"q{next(self._uids)}",
                kind="challenge",
                ref_id=ch.id,
                delivered_at=self.elapsed,
                text=ch.prompt,
                actor_id=ch.actor_id,
                channel=ch.channel,
            )
            self.queue.append(item)
            self._log(self.elapsed, "debrief_challenge_delivered", challenge_id=ch.id,
                      uid=item.uid)

    def finish(self) -> None:
        if self.phase == "debrief" and not self.pending:
            self.phase = "complete"
            self._log(self.elapsed, "debrief_complete", penalties=self.penalties)

    def abort(self, reason: str = "aborted") -> None:
        self.phase = "aborted"
        self._log(self.elapsed, "session_aborted", reason=reason)

    # ------------------------------------------------------------------ views

    @property
    def pending(self) -> list[QueueItem]:
        return [i for i in self.queue if not i.is_done]

    def front(self) -> QueueItem | None:
        return self.pending[0] if self.pending else None

    def task_outcomes(self) -> list[TaskOutcome]:
        out: list[TaskOutcome] = []
        for task in sorted(self.scenario.tasks, key=lambda t: (t.at, t.id)):
            group = self._groups.get(task.group_id)
            msg = self._messages.get(task.message_id)
            out.append(
                TaskOutcome(
                    task_id=task.id,
                    group_id=task.group_id,
                    thread_id=group.thread_id if group else "",
                    state=self._task_state[task.id],
                    at=float(task.at),
                    resolved_at=self._task_resolved_at.get(task.id),
                    failed_door=self._task_failed_door.get(task.id),
                    requested_by=msg.actor_id if msg else None,
                    requested_at=float(msg.at) if msg else None,
                )
            )
        return out

    def task_state(self, task_id: str) -> TaskState:
        return self._task_state[task_id]

    def public_state(self) -> dict:
        """Everything the player is allowed to see (spec 14.4).

        Deliberately thin: the running penalty total and nothing else -- no
        breakdown, no list, no hint which thread a penalty came from.
        """
        item = self.front()
        return {
            "phase": self.phase,
            "elapsed": round(self.elapsed, 2),
            "duration": self.scenario.duration_seconds,
            "penalties": self.penalties,
            "doors": dict(self.door_states),
            "pending_count": len(self.pending),
            "front": self._public_item(item) if item else None,
        }

    def _public_item(self, item: QueueItem) -> dict:
        """What the client gets. A queued item reveals nothing until opened --
        not the sender, not the channel, not how urgent it is."""
        base = {"uid": item.uid, "kind": item.kind, "opened": item.opened_at is not None}
        if item.opened_at is None:
            return base
        actor = self.scenario.actors_by_id.get(item.actor_id or "")
        base |= {
            "channel": item.channel,
            "actor": None if actor is None else {
                "id": actor.id, "name": actor.name, "type": actor.type,
                "portrait": actor.portrait,
            },
            "audio_played": item.audio_played,
        }
        if item.kind == "challenge":
            ch = self._challenges[item.ref_id]
            base |= {
                "prompt": ch.prompt,
                "options": [{"id": o.id, "text": o.text} for o in ch.options],
                "answered": item.answered_at is not None,
                "must_answer": True,
            }
            if item.answered_at is not None:
                correct = ch.correct_option()
                base |= {
                    "outcome": item.answer_outcome,
                    "chosen": item.answer_option_id,
                    "correct_option_id": correct.id if correct else None,
                    "explanation": ch.explanation,
                }
            if ch.channel == "radio":
                base |= {"audio": ch.audio, "audio_duration": ch.audio_duration}
        elif item.kind == "message":
            msg = self._messages[item.ref_id]
            # Radio is audio only. There is no transcript, ever, in any
            # circumstance -- it exists in the JSON for the admin page alone.
            base |= {"text": "" if msg.channel == "radio" else msg.text}
            if msg.channel == "radio":
                base |= {"audio": msg.audio, "audio_duration": msg.audio_duration}
        else:
            base |= {"text": item.text, "alert": True}
        return base

    def _log(self, at: float, kind: str, **detail: Any) -> None:
        self.events.append(Event(at=at, kind=kind, detail=detail))
