#!/usr/bin/env python3
"""Build a print-ready sector reference handbook from station.json.

One card per isolation target: the station map with the sealed volume tinted and
only the cut doors closed, plus the door lists. Intended to be printed and handed
to a player before a session, so learning the sectors is not part of the test.

The cards are drawn by station/render.js — the same renderer the game uses — so a
change to the map or to the drawing shows up here with no separate code to keep
in step.

    python3 station/build_sector_sheets.py           # -> station/sector-sheets.html
    python3 station/build_sector_sheets.py --png     # also -> station/sectors/*.png

--png needs Chrome or Chromium on PATH.
"""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
CHROME_CANDIDATES = ("google-chrome", "chromium", "chromium-browser", "chrome")

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>OpStation — sector reference</title>
<style>
  @page { size: A4 portrait; margin: 11mm; }
  * { box-sizing: border-box; }
  body { margin: 0; background: #fff; color: #000;
         font: 11px "Courier New", Courier, monospace; }

  header { border-bottom: 3px solid #000; padding-bottom: 6px; margin-bottom: 12px; }
  h1 { font-size: 18px; margin: 0 0 3px; letter-spacing: .06em; }
  header p { margin: 0; font-size: 10px; }

  h2.band { font-size: 12px; letter-spacing: .09em; background: #000; color: #fff;
            padding: 4px 7px; margin: 16px 0 10px; }

  /* page 1: the reference map */
  .reference { display: flex; gap: 14px; page-break-after: always; align-items: flex-start; }
  .refmap { width: 470px; height: 514px; flex-shrink: 0; border: 2px solid #000; }
  .refnotes { flex: 1; min-width: 0; font-size: 10px; line-height: 1.65; }
  .refnotes p { margin: 0 0 9px; }
  .refnotes b { letter-spacing: .04em; }
  .sw { display: inline-block; width: 20px; height: 8px; border: 1px solid #333;
        vertical-align: middle; margin-right: 4px; }

  /* sector cards */
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }
  .card { border: 2px solid #000; padding: 7px; page-break-inside: avoid; }
  .card h3 { font-size: 11px; margin: 0 0 1px; letter-spacing: .03em; line-height: 1.25; }
  .card .id { font-size: 8px; color: #666; margin: 0 0 5px; }
  .cardmap { width: 100%; height: 215px; border: 1px solid #999; background: #000;
             margin-bottom: 5px; }
  .card canvas { display: block; margin: 0 auto; }
  .row { display: flex; gap: 4px; font-size: 10px; border-top: 1px solid #ccc; padding: 2px 0; }
  .row span:first-child { color: #555; flex-shrink: 0; width: 52px; font-size: 8px;
                          letter-spacing: .04em; padding-top: 1px; }
  .row b { letter-spacing: .04em; }
  .none { color: #999; font-weight: normal; }
  .why { font-size: 9px; line-height: 1.4; margin: 5px 0 0; padding: 4px;
         background: #eee; border-left: 3px solid #666; }
  footer { margin-top: 12px; font-size: 9px; color: #666; text-align: right; }
</style>

<header>
  <h1>OPSTATION &mdash; SECTOR REFERENCE</h1>
  <p>Which doors seal which place. Station layout __VERSION__ &mdash; fixed, identical in every shift.</p>
</header>

<div class="reference">
  <div class="refmap"><canvas id="c_reference"></canvas></div>
  <div class="refnotes">
    <p><b>THE STATION.</b> Three corridors stacked north to south, with rooms and
    hangar bays hanging off them. Doors are numbered top to bottom, then left to
    right, so C1 owns D1&ndash;D5. Every hangar bay has an inner door onto the station
    and an outer door <span class="sw" style="background:#ff1a1a"></span>H1&ndash;H5 to space.</p>

    <p><b>HOW TO READ THE CARDS.</b> Each card shows every door
    <span class="sw" style="background:#00ff40"></span>open except the ones that
    <b>seal that place</b>, shown <span class="sw" style="background:#ff1a1a"></span>closed.
    The sealed place is tinted <span class="sw" style="background:#d9a520"></span>amber.
    The card maps carry no names &mdash; use this one to place them.</p>

    <p><b>SEALING MEANS CLOSING THE BOUNDARY, NOT EVERYTHING INSIDE.</b> A door that
    sits <i>inside</i> a sealed place stays open. Closing it would cut the inside off
    from itself, not from the station. Each card lists these as <b>INSIDE</b>.</p>

    <p><b>TWO PLACES HAVE NO DOOR OF THEIR OWN.</b> The Observation Deck opens onto
    Living Quarters through a permanent gap, and Storage opens onto C3 the same way.
    Neither can be sealed alone &mdash; sealing either one seals its neighbour with it.
    On the map these gaps are drawn as a break in the wall with two pale jamb ticks.</p>

    <p><b>HANGAR BAY 3 IS A SHORTCUT.</b> It touches both C2 and C3, so there are two
    ways between the central and service sectors. Sealing either sector takes both
    doors &mdash; the junction door alone is not enough. This is the easiest mistake
    to make on the whole station.</p>

    <p><b>IF IT IS ABOUT PRESSURE OR VACUUM</b>, also close the hangar doors inside the
    sealed place. If it is only about keeping people out, do not.</p>
  </div>
</div>

<h2 class="band">SECTORS &mdash; ONE CARD EACH</h2>

<p style="font-size:10px;margin:0 0 10px">A <b>sector</b> spans more than one area, so which
doors bound it is not obvious from the map &mdash; that is what these cards are for. Single
rooms, hangar bays and corridors are not shown: each has its own visible wall, and the
door on it is the door that seals it.</p>

<div class="grid">
__CARDS__
</div>

<footer>station layout __VERSION__ &middot; generated from station.json by build_sector_sheets.py</footer>

<script>__RENDER_JS__</script>
<script>
const station    = __STATION_JSON__;
const stationBig = __STATION_BIG__;
const targets    = __TARGETS__;

// page 1: the labelled reference map, no sector selected
new StationView(document.getElementById('c_reference'), stationBig, { interactive: false, subLabels: false });

// one silhouette card per sector
for (const t of targets) {
  const view = new StationView(document.getElementById('c_' + t.id), station,
                               { interactive: false, showLabels: false });
  const closed = t.cut.concat(t.hangar_doors_inside);
  const m = {};
  for (const d of station.doors) m[d.id] = closed.includes(d.id) ? 'closed' : 'open';
  view.setDoorStates(m);
  view.setHighlight(t.volume);
}
</script>
"""

CARD = """<div class="card">
  <h3>{phrase_uc}</h3>
  <p class="id">{id}</p>
  <div class="cardmap"><canvas id="c_{id}"></canvas></div>
  <div class="row"><span>CLOSE</span><b>{cut}</b></div>
  <div class="row"><span>+ PRESSURE</span><b>{hangars}</b></div>
  <div class="row"><span>INSIDE</span><b>{interior}</b></div>
  <div class="row"><span>SEALS</span><span>{areas}</span></div>
  {why}
</div>
"""


def find_chrome():
    for name in CHROME_CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    return None


def card_html(target, area_names, notes):
    def doors(ids):
        return ", ".join(ids) if ids else '<span class="none">&mdash;</span>'

    why = notes.get(target["id"])
    return CARD.format(
        id=target["id"],
        phrase_uc=target["phrase"].upper(),
        cut=doors(target["cut"]),
        hangars=doors(target["hangar_doors_inside"]),
        interior=doors(target["interior_doors"]),
        areas=", ".join(area_names[a] for a in target["volume"]),
        why=f'<p class="why">{why}</p>' if why else "",
    )


def sizing(station, cards_wide_px):
    """Shrink the grid cell so a card map fits the page, keeping the aspect ratio."""
    grid = dict(station["grid"])
    grid["cell"] = round(cards_wide_px / grid["cols"], 3)
    out = dict(station)
    out["grid"] = grid
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", action="store_true", help="also write one PNG per sector")
    ap.add_argument("--card-width", type=int, default=196, help="map width in px per sector card")
    args = ap.parse_args(argv)

    station = json.loads((HERE / "station.json").read_text())
    render_js = (HERE / "render.js").read_text()

    area_names = {a["id"]: a["name"].replace("  ", " ").title() for a in station["areas"]}
    area_names.update({"C1": "C1 North Corridor", "C2": "C2 Central Junction",
                       "C3": "C3 Service Corridor"})

    notes = {
        "residential_sector": "The Observation Deck has no door of its own — it opens onto Living "
                       "Quarters through a permanent gap. Sealing one seals both.",
        "storage_sector": "Storage has no door of its own, so sealing it means sealing the "
                          "whole service corridor with it. The largest cut on the station.",
        "service_sector": "Two doors, not one. Hangar Bay 3 is a back route between C2 and "
                          "C3, so closing the junction door alone leaves the sector open.",
        "central_sector": "Includes both Hangar Bay 3 doors' side of the loop — the bay "
                          "bridges C2 and C3.",
        "construction_sector": "Nested inside the service sector, but it needs MORE doors. "
                               "Leaving Engineering and Hangar Bay 4 outside the sealed volume "
                               "turns their corridor doors into boundary doors.",
        "engineering": "Engineering has two doors: one onto the service corridor and one "
                       "straight into Hangar Bay 4.",
        "engineering_sector": "Engineering and Hangar Bay 4 treated as one place, so the door "
                             "between them stays open.",
        "hangar_bay_3": "The only bay with two internal doors, because it links two corridors.",
    }

    # Only sectors get a card. Single rooms, bays and corridors are obvious from the
    # map, so printing them would bury the seven that actually need learning.
    sectors = [t for t in station["isolation_targets"] if t["class"] == "sector"]
    cards = "\n".join(card_html(t, area_names, notes) for t in sectors)

    html = (PAGE
            .replace("__CARDS__", cards)
            .replace("__RENDER_JS__", render_js)
            .replace("__STATION_JSON__", json.dumps(sizing(station, args.card_width)))
            .replace("__STATION_BIG__", json.dumps(sizing(station, 470)))
            .replace("__TARGETS__", json.dumps(sectors))
            .replace("__VERSION__", station["version"]))

    out = HERE / "sector-sheets.html"
    out.write_text(html)
    print(f"wrote {out.relative_to(HERE.parent)}  "
          f"({len(sectors)} sector cards, {len(html) // 1024} KB)")
    print("open it and print, or Print to PDF — one card per sector, A4 portrait")

    if args.png:
        chrome = find_chrome()
        if not chrome:
            print("error: --png needs Chrome or Chromium on PATH", file=sys.stderr)
            return 1
        png_dir = HERE / "sectors"
        png_dir.mkdir(exist_ok=True)
        big = sizing(station, 760)
        for t in sectors:
            single = PAGE.replace("__CARDS__", card_html(t, area_names, notes)) \
                         .replace("__RENDER_JS__", render_js) \
                         .replace("__STATION_JSON__", json.dumps(big)) \
                         .replace("__STATION_BIG__", json.dumps(sizing(station, 470))) \
                         .replace("__TARGETS__", json.dumps([t])) \
                         .replace("__VERSION__", station["version"])
            with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
                fh.write(single)
                tmp = fh.name
            dest = png_dir / f"{t['id']}.png"
            subprocess.run([chrome, "--headless", "--disable-gpu", "--no-sandbox",
                            "--hide-scrollbars", "--window-size=1000,1500",
                            "--virtual-time-budget=3000",
                            f"--screenshot={dest}", f"file://{tmp}"],
                           check=True, capture_output=True)
            pathlib.Path(tmp).unlink()
            print(f"  {dest.relative_to(HERE.parent)}")
        print(f"{len(sectors)} PNGs in {png_dir.relative_to(HERE.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
