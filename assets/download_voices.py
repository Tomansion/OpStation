#!/usr/bin/env python3
"""Download the six pinned Piper voice models into assets/voices/.

The voices are pinned in config/voices.json and that file is append-only: a
voice is the only cue that tells one actor from another, so swapping one
silently invalidates every provenance question in the bank.

    python3 assets/download_voices.py
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "voices"
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


def url_for(voice: str) -> str:
    """en_GB-alba-medium -> en/en_GB/alba/medium/en_GB-alba-medium"""
    locale, name, quality = voice.split("-")
    lang = locale.split("_")[0]
    return f"{BASE}/{lang}/{locale}/{name}/{quality}/{voice}"


def fetch(url: str, dest: Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  have {dest.name}")
        return
    print(f"  get  {dest.name} ...", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as response, tmp.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    tmp.replace(dest)
    print(f"       {dest.stat().st_size / 1e6:.1f} MB")


def main() -> int:
    voices = json.loads((ROOT / "config" / "voices.json").read_text())["assignment"]
    OUT.mkdir(parents=True, exist_ok=True)
    for actor_type, spec in voices.items():
        voice = spec["voice"]
        print(f"{actor_type}: {voice}")
        base = url_for(voice)
        try:
            fetch(f"{base}.onnx", OUT / f"{voice}.onnx")
            fetch(f"{base}.onnx.json", OUT / f"{voice}.onnx.json")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAILED: {exc}", file=sys.stderr)
            return 1
    print(f"\n{len(voices)} voices in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
