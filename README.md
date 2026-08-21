# OpStation

A door-control game used as a memory instrument.

The player is the **Door Control Operator** of a space station. Their only actions are opening and closing doors, reading or hearing messages, and answering questions. The difficulty is not manual — it is remembering *why* each door is in its current state, *who* asked for it, *since when*, *what must happen before it can change*, and *whether the instruction they remember has since been withdrawn*.

There is no message history, no log, no replay. A message arrives once and is gone.

A session runs **20–30 minutes** in real time and never pauses.

## Status

Specification and station layout only. No application code yet.

| | |
|---|---|
| **[`spec.md`](spec.md)** | The specification. Start here. |
| **[`station/`](station/)** | The station layout: authoritative JSON, canvas renderer, browsable preview, printable sector handbook. |
| **[`config/difficulty.json`](config/difficulty.json)** | Every value that shapes difficulty, in one place. |
| **[`archive/`](archive/)** | Superseded drafts and the review rounds that produced the current spec. |

## Look at the station

Open [`station/preview.html`](station/preview.html) in a browser. It is self-contained — no server needed. Click any door on the map, or in the side panel, to toggle it.

```
station/
  station.json            authoritative layout: areas, doors, fixed start states, sectors
  render.js               canvas renderer + door hit-testing, shared by everything below
  preview.template.html   template for the preview
  preview.html            generated, self-contained
  build_preview.py        regenerate preview.html after editing station.json
  build_sector_sheets.py  build the printable sector handbook
  sector-sheets.html      generated, print-ready
  format_station.py       keep station.json compact and hand-editable
```

After editing `station.json`:

```sh
python3 station/format_station.py        # tidy it
python3 station/build_preview.py         # refresh the preview
python3 station/build_sector_sheets.py   # refresh the handbook
```

## Print the sector handbook

Sectors are the one thing a newcomer cannot read off the map, and figuring them out
is not what a session is meant to measure — so they get printed and handed over first.

```sh
python3 station/build_sector_sheets.py          # -> station/sector-sheets.html
python3 station/build_sector_sheets.py --png    # also -> station/sectors/*.png
```

Open [`station/sector-sheets.html`](station/sector-sheets.html) and print it, or print to
PDF. Page 1 is the labelled map plus the five things worth knowing; page 2 is seven cards,
one per sector, each showing which doors seal it and which doors inside it stay open.
The cards are drawn by the game's own renderer, so they can never drift from the map.

The layout is **fixed forever** — identical in every scenario and every session. 6 rooms,
3 corridors, 5 hangar bays, 13 internal doors (D1–D13), 5 hangar doors (H1–H5), and 2
permanent doorless passages. Doors are numbered top to bottom, then left to right, so C1
owns exactly D1–D5 and every two-door area has consecutive numbers.

The home page shows this same canvas, fully operable with no clock running, so a player can
learn the controls and the layout before a session starts.

## How it will be built

- **Backend** — Python 3.12 + FastAPI. Server-authoritative clock, one asyncio game loop per session, WebSocket push.
- **Frontend** — Angular. The station drawn on a `<canvas>`.
- **Scenarios** — generated offline by an LLM (via LiteLLM) into a validated bank, with TTS audio pre-rendered into each scenario folder. **The runtime never calls an LLM or a TTS engine.**
- **Storage** — flat JSON files. One file per session.
- **Packaging** — Dockerfile per service plus `docker-compose.yml`.

See [`spec.md` §14](spec.md) for the architecture, and §11–13 for the scenario format, generation pipeline and validator.

## The two ideas worth knowing before reading the spec

**Tasks are the sole ground truth.** There is no priority hierarchy and no inferred intent. A task is a required set of door states, a start time, and a duration it must hold for. If no task covers a door at a given moment, no state is right or wrong. A "conflicting request" is therefore a message with *no task* — a sympathetic plea to open a door that another thread's live obligation requires stay closed.

**Every scenario must be provably solvable.** The validator replays each generated scenario with a perfect operator; if any task fails, the scenario is rejected and sent back to the generator for repair. The same pass produces the expected-state trace the admin page renders against what the player actually did.
