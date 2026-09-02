"""Live sessions: the asyncio wrapper around the engine, plus persistence.

One task per session, ticking at `tick_ms`. The clock is server-authoritative
and derived from wall time, not from counting ticks, so a slow tick loses
resolution but never loses time -- the world does not wait for the browser.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import bank
from .config import difficulty as load_difficulty
from .engine import Engine, Event
from .models import Scenario
from . import paths
from .station import station as load_station

Listener = Callable[[dict], Awaitable[None]]


@dataclass
class Session:
    session_id: str
    participant_name: str
    scenario: Scenario
    engine: Engine
    started_at: float                     # monotonic, for the clock
    started_wall: str                     # ISO, for the record
    listeners: set[Listener] = field(default_factory=set)
    task: asyncio.Task | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # ------------------------------------------------------------------ clock

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    # -------------------------------------------------------------- broadcast

    async def broadcast(self, payload: dict) -> None:
        for listener in list(self.listeners):
            try:
                await listener(payload)
            except Exception:  # noqa: BLE001 - a dead socket must not stop the world
                self.listeners.discard(listener)

    async def push_state(self, extra: dict | None = None) -> None:
        await self.broadcast({"type": "state", **self.engine.public_state(), **(extra or {})})

    async def _emit(self, events: list[Event]) -> None:
        """Only tell the client that something arrived, never what it is: the
        player is not told who is calling or how urgent it is (spec 5.2)."""
        interesting = {
            "message_delivered", "challenge_delivered", "failure_notice_delivered",
            "debrief_challenge_delivered", "session_ended", "task_failed",
        }
        if any(e.kind in interesting for e in events):
            await self.push_state()
        # Confirmations bypass the queue entirely -- broadcast directly rather
        # than folding into public_state, which only ever describes the front
        # of the queue.
        for event in events:
            if event.kind == "task_confirmed":
                await self.broadcast({"type": "confirmed", "text": event.detail["text"]})

    # ------------------------------------------------------------------ loop

    async def run(self) -> None:
        tick = load_difficulty().tick_seconds
        try:
            while self.engine.phase == "running":
                async with self._lock:
                    events = self.engine.advance_to(self.elapsed)
                await self._emit(events)
                self.persist()
                await asyncio.sleep(tick)
            await self.push_state()
            self.persist()
        except asyncio.CancelledError:
            raise

    # --------------------------------------------------------- player actions

    async def toggle_door(self, door: str) -> dict:
        async with self._lock:
            self.engine.advance_to(self.elapsed)
            result = self.engine.toggle_door(door, now=self.elapsed)
        await self.push_state()
        self.persist()
        return result

    async def open_notification(self) -> dict | None:
        async with self._lock:
            self.engine.advance_to(self.elapsed)
            self.engine.open_notification(now=self.elapsed)
        await self.push_state()
        self.persist()
        return self.engine.public_state()["front"]

    async def acknowledge(self, uid: str) -> bool:
        async with self._lock:
            self.engine.advance_to(self.elapsed)
            ok = self.engine.acknowledge(uid, now=self.elapsed)
            if self.engine.phase == "debrief":
                self.engine.finish()
        await self.push_state()
        self.persist()
        return ok

    async def answer_challenge(self, uid: str, option_id: str) -> dict | None:
        async with self._lock:
            self.engine.advance_to(self.elapsed)
            result = self.engine.answer_challenge(uid, option_id, now=self.elapsed)
        await self.push_state()
        self.persist()
        return result

    async def reconnect(self) -> None:
        async with self._lock:
            self.engine.advance_to(self.elapsed)
            self.engine.on_reconnect(self.elapsed)
        await self.push_state()

    # ---------------------------------------------------------- persistence

    def as_json(self) -> dict:
        engine = self.engine
        return {
            "session_id": self.session_id,
            "participant_name": self.participant_name,
            "scenario_id": self.scenario.scenario_id,
            "scenario_name": self.scenario.name,
            "station_version": self.scenario.station_version,
            "started_at": self.started_wall,
            "phase": engine.phase,
            "elapsed": round(engine.elapsed, 2),
            "duration_seconds": self.scenario.duration_seconds,
            "penalties": engine.penalties,
            "doors": dict(engine.door_states),
            "queue": [
                {
                    "uid": i.uid, "kind": i.kind, "ref_id": i.ref_id,
                    "delivered_at": round(i.delivered_at, 2),
                    "opened_at": None if i.opened_at is None else round(i.opened_at, 2),
                    "acknowledged_at": (
                        None if i.acknowledged_at is None else round(i.acknowledged_at, 2)
                    ),
                    "withdrawn_at": (
                        None if i.withdrawn_at is None else round(i.withdrawn_at, 2)
                    ),
                    "answer_option_id": i.answer_option_id,
                    "answer_outcome": i.answer_outcome,
                    "audio_played": i.audio_played,
                }
                for i in engine.queue
            ],
            "tasks": [
                {
                    "task_id": o.task_id, "group_id": o.group_id, "thread_id": o.thread_id,
                    "state": o.state, "at": o.at, "resolved_at": o.resolved_at,
                    "failed_door": o.failed_door, "requested_by": o.requested_by,
                    "requested_at": o.requested_at,
                }
                for o in engine.task_outcomes()
            ],
            "events": [e.as_json() for e in engine.events],
        }

    def persist(self) -> None:
        """One JSON per session, written atomically. Sessions do not need to
        survive a backend restart -- an interrupted one is marked aborted."""
        paths.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        path = paths.session_file(self.session_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.as_json(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


class SessionManager:
    """Many sessions in one app instance, each with its own clock."""

    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def create(self, participant_name: str, scenario_id: str) -> Session:
        scenario = bank.load(scenario_id)
        station = load_station()
        if scenario.station_version != station.version:
            raise ValueError(
                f"scenario {scenario_id} was authored against station "
                f"{scenario.station_version}, but this station is {station.version}"
            )
        session_id = f"se_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:4]}"
        session = Session(
            session_id=session_id,
            participant_name=participant_name.strip() or "anonymous",
            scenario=scenario,
            engine=Engine(scenario, station=station),
            started_at=time.monotonic(),
            started_wall=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self.sessions[session_id] = session
        session.task = asyncio.create_task(session.run())
        session.persist()
        self._index()
        return session

    def get(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    async def abort_all(self, reason: str = "backend stopped") -> None:
        for session in list(self.sessions.values()):
            if session.task:
                session.task.cancel()
            if session.engine.phase in ("running", "debrief"):
                session.engine.abort(reason)
                session.persist()
        self._index()

    def _index(self) -> None:
        paths.SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        rows = []
        for path in sorted(paths.SESSIONS_DIR.glob("se_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            rows.append({
                k: data.get(k) for k in (
                    "session_id", "participant_name", "scenario_id", "scenario_name",
                    "started_at", "phase", "penalties", "elapsed",
                )
            })
        tmp = paths.SESSION_INDEX.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        tmp.replace(paths.SESSION_INDEX)

    def history(self) -> list[dict]:
        if not paths.SESSION_INDEX.exists():
            self._index()
        try:
            return json.loads(paths.SESSION_INDEX.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def detail(self, session_id: str) -> dict | None:
        live = self.sessions.get(session_id)
        if live is not None:
            return live.as_json()
        path = paths.session_file(session_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def delete(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session and session.task:
            session.task.cancel()
        path = paths.session_file(session_id)
        existed = path.exists()
        path.unlink(missing_ok=True)
        self._index()
        return existed
