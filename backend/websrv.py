"""FastAPI application (spec 14.4).

Server-authoritative: the client renders and reports clicks, and every decision
about time, delivery, failure and scoring is taken here. No authentication
anywhere, by design.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from opstation import bank
from opstation.config import (
    DONT_KNOW_OPTION_ID,
    DONT_KNOW_OPTION_TEXT,
    difficulty,
    voices,
)
from opstation import paths
from opstation.paths import FRONTEND_DIR, PORTRAITS_DIR, RENDER_JS, STATION_FILE
from opstation.session import SessionManager
from opstation.station import station as load_station

manager = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_station()  # fail fast if the layout is inconsistent with its own graph
    yield
    await manager.abort_all()


app = FastAPI(title="OpStation", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def no_stale_client(request, call_next):
    """Never let a browser cache the client.

    The frontend is served straight from disk, and a participant running a
    cached copy of a page that has since been fixed is a silently corrupted
    session. Audio is content-addressed by scenario and message id, so it stays
    cacheable.
    """
    response = await call_next(request)
    path = request.url.path
    if (
        path.startswith(("/app/", "/station/"))
        or path == "/"
        or path.startswith(("/game/", "/summary/", "/admin"))
    ):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


# ------------------------------------------------------------------- the station


@app.get("/api/station")
def get_station() -> JSONResponse:
    """Served to the frontend and loaded by the backend, so both sides agree on
    the layout and on the fixed start state without duplicating it."""
    return JSONResponse(json.loads(STATION_FILE.read_text(encoding="utf-8")))


@app.get("/station/render.js")
def get_render_js() -> FileResponse:
    return FileResponse(RENDER_JS, media_type="text/javascript")


@app.get("/api/config")
def get_config() -> dict:
    """What the client legitimately needs: the tunables that change its own
    behaviour, and the fifth challenge option it supplies itself."""
    diff = difficulty()
    return {
        "tick_ms": diff["tick_ms"],
        "show_pending_count": diff["show_pending_count"],
        "challenge_blocks_doors": diff["challenge_blocks_doors"],
        "dont_know": {"id": DONT_KNOW_OPTION_ID, "text": DONT_KNOW_OPTION_TEXT},
        "station_version": load_station().version,
    }


# --------------------------------------------------------------------- the bank


@app.get("/api/scenarios")
def list_scenarios() -> list[dict]:
    return [e.as_json() for e in bank.listing()]


@app.get("/api/scenarios/{scenario_id}/audio/{filename}")
def get_audio(scenario_id: str, filename: str) -> FileResponse:
    path = paths.scenario_dir(scenario_id) / "audio" / filename
    if not path.exists() or path.suffix != ".wav":
        raise HTTPException(404, "no such audio")
    return FileResponse(path, media_type="audio/wav")


# ------------------------------------------------------------------- sessions


@app.post("/api/sessions")
async def create_session(payload: dict) -> dict:
    scenario_id = payload.get("scenario_id")
    if not scenario_id:
        raise HTTPException(400, "scenario_id is required")
    entry = next((e for e in bank.listing() if e.scenario_id == scenario_id), None)
    if entry is None:
        raise HTTPException(404, "no such scenario")
    if not entry.playable:
        # A scenario that failed validation, or whose audio is missing, is never
        # offered: audio failure voids a session rather than degrading it.
        raise HTTPException(
            409,
            f"scenario {scenario_id} is not playable "
            f"(valid={entry.valid}, audio={entry.has_audio})",
        )
    try:
        session = manager.create(payload.get("participant_name", ""), scenario_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"session_id": session.session_id, "scenario_id": scenario_id}


@app.get("/api/sessions/{session_id}")
async def session_state(session_id: str) -> dict:
    session = manager.get(session_id)
    if session is None:
        raise HTTPException(404, "no such live session")
    session.engine.advance_to(session.elapsed)
    return _snapshot(session)


def _snapshot(session) -> dict:
    return {
        "type": "snapshot",
        "session_id": session.session_id,
        "participant_name": session.participant_name,
        "scenario_id": session.scenario.scenario_id,
        "scenario_name": session.scenario.name,
        **session.engine.public_state(),
    }


@app.get("/api/sessions/{session_id}/summary")
async def session_summary(session_id: str) -> dict:
    """The debrief breakdown (spec 9.2) -- everything the player could not see
    during play."""
    detail = manager.detail(session_id)
    if detail is None:
        raise HTTPException(404, "no such session")
    scenario = bank.load(detail["scenario_id"])
    groups = scenario.groups_by_id
    threads = scenario.threads_by_id
    actors = scenario.actors_by_id
    messages = scenario.messages_by_id
    challenges = {c.id: c for c in scenario.all_challenges}

    failures = []
    for row in detail["tasks"]:
        if row["state"] != "failed":
            continue
        group = groups.get(row["group_id"])
        thread = threads.get(row["thread_id"])
        failures.append(
            {
                "task_id": row["task_id"],
                "thread": thread.title if thread else row["thread_id"],
                "obligation": group.label if group else row["group_id"],
                "door": row["failed_door"],
                "requested_by": (
                    actors[row["requested_by"]].name
                    if row["requested_by"] in actors
                    else None
                ),
                "requested_at": row["requested_at"],
                "failed_at": row["resolved_at"],
            }
        )

    answered = []
    for item in detail["queue"]:
        if item["kind"] != "challenge" or item["answer_outcome"] is None:
            continue
        challenge = challenges.get(item["ref_id"])
        if challenge is None:
            continue
        chosen = next(
            (o for o in challenge.options if o.id == item["answer_option_id"]), None
        )
        correct = challenge.correct_option()
        answered.append(
            {
                "challenge_id": challenge.id,
                "slot": challenge.slot,
                "kind": challenge.kind,
                "thread": (
                    threads[challenge.thread_id].title
                    if challenge.thread_id in threads
                    else challenge.thread_id
                ),
                "prompt": challenge.prompt,
                "outcome": item["answer_outcome"],
                "your_answer": (
                    DONT_KNOW_OPTION_TEXT
                    if item["answer_option_id"] == DONT_KNOW_OPTION_ID
                    else (chosen.text if chosen else item["answer_option_id"])
                ),
                "correct_answer": correct.text if correct else None,
                "explanation": challenge.explanation,
            }
        )

    per_thread: dict[str, int] = {}
    for failure in failures:
        per_thread[failure["thread"]] = per_thread.get(failure["thread"], 0) + 1
    for answer in answered:
        if answer["outcome"] != "correct":
            per_thread[answer["thread"]] = per_thread.get(answer["thread"], 0) + 1

    unread_at_expiry = sum(
        1 for item in detail["queue"] if item.get("withdrawn_at") is not None
    )
    return {
        "session_id": session_id,
        "participant_name": detail["participant_name"],
        "scenario_name": detail["scenario_name"],
        "penalties": detail["penalties"],
        "elapsed": detail["elapsed"],
        "duration_seconds": detail["duration_seconds"],
        "phase": detail["phase"],
        "failed_tasks": failures,
        "challenges": answered,
        "per_thread": [
            {"thread": k, "penalties": v}
            for k, v in sorted(per_thread.items(), key=lambda kv: -kv[1])
        ],
        "messages_unread_at_expiry": unread_at_expiry,
        "threads": [
            {"title": t.title, "summary": t.debrief_summary}
            for t in scenario.threads
            if t.grade in ("ordinary", "finale")
        ],
    }


# ------------------------------------------------------------------ websocket


@app.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    session = manager.get(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "message": "no such live session"})
        await websocket.close()
        return

    async def send(payload: dict) -> None:
        await websocket.send_json(payload)

    session.listeners.add(send)
    try:
        await websocket.send_json(_snapshot(session))
        # A refresh resumes the session; elapsed time kept running while the
        # browser was away, and an unacknowledged modal goes back to the front
        # of the queue.
        await session.reconnect()
        while True:
            data = await websocket.receive_json()
            await _handle(session, data, send)
    except WebSocketDisconnect:
        pass
    finally:
        session.listeners.discard(send)


async def _handle(session, data: dict, send) -> None:
    action = data.get("type")
    if action == "toggle_door":
        await session.toggle_door(data["door"])
    elif action == "open_notification":
        item = await session.open_notification()
        await send({"type": "opened", "item": item})
    elif action == "acknowledge":
        ok = await session.acknowledge(data["uid"])
        if not ok:
            # The modal can only be dismissed with Acknowledge, and a challenge
            # not until it is answered.
            await send({"type": "shake", "uid": data.get("uid")})
    elif action == "answer_challenge":
        result = await session.answer_challenge(data["uid"], data["option_id"])
        await send({"type": "answered", "result": result})
    elif action == "ping":
        await send({"type": "pong", "elapsed": round(session.elapsed, 2)})


# ---------------------------------------------------------------------- admin


@app.get("/api/admin/status")
def admin_status() -> dict:
    entries = bank.listing()
    diff = difficulty()
    return {
        "station_version": load_station().version,
        "difficulty": diff.raw,
        "tunables_fingerprint": diff.validator_fingerprint(),
        "voices": voices().raw["assignment"],
        "bank": {
            "total": len(entries),
            "playable": sum(1 for e in entries if e.playable),
            "invalid": sum(1 for e in entries if not e.valid),
            "stale_tunables": sum(1 for e in entries if not e.tunables_match),
        },
        "active_sessions": [
            {
                "session_id": s.session_id,
                "participant_name": s.participant_name,
                "scenario_id": s.scenario.scenario_id,
                "phase": s.engine.phase,
                "elapsed": round(s.engine.elapsed, 1),
                "penalties": s.engine.penalties,
            }
            for s in manager.sessions.values()
        ],
    }


@app.get("/api/admin/sessions")
def admin_sessions() -> list[dict]:
    return manager.history()


@app.get("/api/admin/sessions/{session_id}")
def admin_session(session_id: str) -> dict:
    detail = manager.detail(session_id)
    if detail is None:
        raise HTTPException(404, "no such session")
    scenario = bank.load(detail["scenario_id"])
    report = bank.validation_report(detail["scenario_id"])
    return {
        "session": detail,
        "scenario": scenario.model_dump(mode="json", exclude_none=True),
        "expected_trace": report.get("simulation", {}).get("toggles", []),
    }


@app.delete("/api/admin/sessions/{session_id}")
def admin_delete_session(session_id: str) -> dict:
    if not manager.delete(session_id):
        raise HTTPException(404, "no such session")
    return {"deleted": session_id}


@app.get("/api/admin/scenarios/{scenario_id}")
def admin_scenario(scenario_id: str) -> dict:
    try:
        scenario = bank.load(scenario_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    directory = paths.scenario_dir(scenario_id)
    log = directory / "generation.log"
    return {
        "scenario": scenario.model_dump(mode="json", exclude_none=True),
        "validation": bank.validation_report(scenario_id),
        "generation_log": log.read_text(encoding="utf-8") if log.exists() else "",
    }


# ------------------------------------------------------------------ generation

_jobs: dict[str, dict] = {}


@app.post("/api/admin/scenarios/generate")
async def admin_generate(payload: dict) -> dict:
    """Start a generation job. Nothing about generation happens during a play
    session, so this is a separate background task with its own progress."""
    import asyncio
    import uuid

    job_id = f"job_{uuid.uuid4().hex[:8]}"
    _jobs[job_id] = {
        "job_id": job_id,
        "state": "running",
        "progress": [],
        "result": None,
    }

    async def work() -> None:
        from .opstation.generate.pipeline import Generator, publish
        from .opstation.generate.tts import render_scenario

        def progress(stage: str, message: str) -> None:
            _jobs[job_id]["progress"].append({"stage": stage, "message": message})

        try:
            generator = Generator(progress=progress)
            result = await asyncio.to_thread(
                generator.generate,
                duration=int(payload.get("duration_seconds", 1620)),
                finale=payload.get("finale") or None,
                theme=payload.get("theme") or None,
                threads=int(payload.get("threads", 5)),
                seed=payload.get("seed"),
            )
            directory = publish(result)
            if result.ok and payload.get("render_audio", True):
                progress("tts", "rendering audio")
                await asyncio.to_thread(render_scenario, result.scenario, directory)
                from .opstation.generate.repair import reflow_for_audio
                from .opstation.validator import validate as _validate

                for line in reflow_for_audio(result.scenario):
                    progress("reflow", line)
                result.scenario.dump(directory / "scenario.json")
                report = _validate(result.scenario, audio_dir=directory / "audio")
                report.dump(directory / "validation.json")
                progress("revalidate", report.summary())
                if not report.ok:
                    result.scenario.status = "invalid"
                    result.scenario.dump(directory / "scenario.json")
            _jobs[job_id] |= {
                "state": "done" if result.ok else "invalid",
                "result": {
                    "scenario_id": result.scenario.scenario_id,
                    "summary": result.report.summary(),
                    "failed_rules": result.report.failed_rules(),
                },
            }
        except Exception as exc:  # noqa: BLE001 - surfaced to the admin page
            _jobs[job_id] |= {
                "state": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }

    asyncio.create_task(work())
    return {"job_id": job_id}


@app.get("/api/admin/jobs/{job_id}")
def admin_job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return job


# ----------------------------------------------------------------- static files

if PORTRAITS_DIR.exists():
    app.mount(
        "/assets/portraits", StaticFiles(directory=PORTRAITS_DIR), name="portraits"
    )


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return "ok"


def _index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html", media_type="text/html")


if FRONTEND_DIR.exists():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR), name="frontend")

    # Client-side routes all serve the same shell.
    for route in (
        "/",
        "/game/{rest:path}",
        "/summary/{rest:path}",
        "/admin/{rest:path}",
    ):
        app.get(route, include_in_schema=False)(lambda rest="": _index())

    @app.get("/admin", include_in_schema=False)
    def admin_page() -> FileResponse:
        return _index()
