"""Filesystem layout. Everything is resolved from the repository root so the
backend, the generator and the build scripts cannot disagree about where the
station definition or the scenario bank lives."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = ROOT / "config"
DIFFICULTY_FILE = CONFIG_DIR / "difficulty.json"
VOICES_FILE = CONFIG_DIR / "voices.json"

STATION_DIR = ROOT / "station"
STATION_FILE = STATION_DIR / "station.json"
RENDER_JS = STATION_DIR / "render.js"

ASSETS_DIR = ROOT / "assets"
PORTRAITS_DIR = ASSETS_DIR / "portraits"

#: Overridable so a container can mount the bank elsewhere, and so tests can
#: run against a throwaway bank without touching the real one.
DATA_DIR = Path(os.environ.get("OPSTATION_DATA_DIR") or (ROOT / "data"))
SCENARIOS_DIR = DATA_DIR / "scenarios"
SCENARIO_INDEX = SCENARIOS_DIR / "index.json"
SESSIONS_DIR = DATA_DIR / "sessions"
SESSION_INDEX = SESSIONS_DIR / "index.json"

FRONTEND_DIR = ROOT / "frontend"


def use_data_dir(path: Path) -> None:
    """Point every data path at `path`. Called by tests and by the CLI."""
    global DATA_DIR, SCENARIOS_DIR, SCENARIO_INDEX, SESSIONS_DIR, SESSION_INDEX
    DATA_DIR = Path(path)
    SCENARIOS_DIR = DATA_DIR / "scenarios"
    SCENARIO_INDEX = SCENARIOS_DIR / "index.json"
    SESSIONS_DIR = DATA_DIR / "sessions"
    SESSION_INDEX = SESSIONS_DIR / "index.json"


def scenario_dir(scenario_id: str) -> Path:
    return SCENARIOS_DIR / scenario_id


def session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def load_dotenv(path: Path | None = None) -> None:
    """Read the gitignored .env into os.environ without overwriting anything
    already set. Generation-time only -- the runtime never needs a key."""
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
