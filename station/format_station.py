#!/usr/bin/env python3
"""Re-emit station.json compactly: rects, bars and short string lists stay on one line.

station.json is hand-edited, so `json.dump(indent=2)` (one number per line) is not
acceptable. Run this after any programmatic edit.

    python3 station/format_station.py
"""
import json
import pathlib

HERE = pathlib.Path(__file__).parent
INLINE_KEYS = {"grid", "bar", "rects", "between", "cut", "hangar_doors_inside", "volume"}


def dumps(value, indent=0, inline=False):
    pad = "  " * indent
    if inline:
        return json.dumps(value, ensure_ascii=False)

    if isinstance(value, dict):
        if not value:
            return "{}"
        parts = []
        for k, v in value.items():
            sub = dumps(v, indent + 1, inline=k in INLINE_KEYS)
            parts.append(f'{pad}  {json.dumps(k, ensure_ascii=False)}: {sub}')
        return "{\n" + ",\n".join(parts) + "\n" + pad + "}"

    if isinstance(value, list):
        if not value:
            return "[]"
        # a list of scalars, or of short lists (rects), goes on one line
        if all(not isinstance(x, (dict, list)) for x in value):
            return json.dumps(value, ensure_ascii=False)
        if all(isinstance(x, list) for x in value):
            inner = ", ".join(json.dumps(x, ensure_ascii=False) for x in value)
            return f"[{inner}]"
        parts = [f'{pad}  {dumps(x, indent + 1)}' for x in value]
        return "[\n" + ",\n".join(parts) + "\n" + pad + "]"

    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    path = HERE / "station.json"
    data = json.loads(path.read_text())
    path.write_text(dumps(data) + "\n")
    before = data
    assert json.loads(path.read_text()) == before, "reformat changed the data"
    print(f"formatted {path.name}: {len(path.read_text().splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
