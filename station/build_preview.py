#!/usr/bin/env python3
"""Inline station.json and render.js into a self-contained preview.html.

station.json is the single source of truth. Regenerate the preview after editing it:

    python3 station/build_preview.py
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).parent

def main() -> int:
    station_path = HERE / "station.json"
    render_path = HERE / "render.js"
    template_path = HERE / "preview.template.html"
    out_path = HERE / "preview.html"

    station = json.loads(station_path.read_text())
    render_js = render_path.read_text()
    template = template_path.read_text()

    for marker in ("/*__RENDER_JS__*/", "/*__STATION_JSON__*/"):
        if marker not in template:
            print(f"error: {template_path.name} is missing {marker}", file=sys.stderr)
            return 1

    html = (
        template
        .replace("/*__RENDER_JS__*/", render_js)
        .replace("/*__STATION_JSON__*/", json.dumps(station, indent=2))
    )
    out_path.write_text(html)

    doors = station["doors"]
    open_at_start = [d["id"] for d in doors if d["initial"] == "open"]
    print(f"wrote {out_path.relative_to(HERE.parent)}  "
          f"({len(html) // 1024} KB, {len(station['areas'])} areas, {len(doors)} doors)")
    print(f"open at start: {', '.join(open_at_start)}")
    print("open it directly in a browser — no server needed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
