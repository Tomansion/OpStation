# OpStation

A door-control game used as a memory instrument.

The player is the **Door Control Operator** of a space station. Their only actions are opening and closing doors, reading or hearing messages, and answering questions. The difficulty is not manual — it is remembering _why_ each door is in its current state, _who_ asked for it, _since when_, _what must happen before it can change_, and _whether the instruction they remember has since been withdrawn_.

There is no message history, no log, no replay. A message arrives once and is gone.

A session runs **20–30 minutes** in real time and never pauses.

## Run it

```sh
make venv        # create .venv and install everything
make test        # run the suite
make serve       # play on http://localhost:3000
```

Generating a scenario needs an LLM key in a gitignored `.env` beside this file:

```sh
echo 'MISTRAL_API_KEY=...' > .env
make voices                              # download the six pinned Piper voices (~500 MB, once)
make generate ARGS="--finale invasion"   # writes into data/scenarios/
```

Or in Docker:

```sh
docker compose up app
docker compose run --rm generator --finale hull_breach
```

## What is here

|                                                        |                                                                                                |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| **[`spec.md`](spec.md)**                               | The specification. Start here.                                                                 |
| **[`backend/opstation/`](backend/opstation/)**         | Station graph, runtime engine, validator, generator, FastAPI app.                              |
| **[`frontend/`](frontend/)**                           | Four pages of plain ES modules. No build step.                                                 |
| **[`station/`](station/)**                             | The layout: authoritative JSON, canvas renderer, browsable preview, printable sector handbook. |
| **[`config/difficulty.json`](config/difficulty.json)** | Every value that shapes difficulty, in one place.                                              |
| **[`config/voices.json`](config/voices.json)**         | The pinned Piper voice per actor type. Append-only.                                            |
| **[`archive/`](archive/)**                             | Superseded drafts and the review rounds that produced the current spec.                        |

```
backend/opstation/
  station.py       the door graph; recomputes every isolation cut-set from it
  engine.py        the session runtime — tasks, holds, cascade, queue, scoring
  session.py       the asyncio clock and per-session persistence
  validator/       the 35 rules, and the perfect-player simulation
  generate/        five LLM stages, a deterministic scheduler, Piper TTS
  app.py           FastAPI: REST, WebSocket, admin
```

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

## How it is built

- **Backend** — Python 3.12 + FastAPI. Server-authoritative clock, one asyncio loop per session, WebSocket push. The engine itself is pure and clock-injected, so a 27-minute session replays in a millisecond in a test.
- **Frontend** — plain ES modules on an HTML `<canvas>`, no framework and no build step. A deliberate change from the Angular plan; the reasoning is in [`spec.md` §14.7](spec.md).
- **Scenarios** — generated offline into a validated bank, with Piper audio pre-rendered into each scenario folder. **The runtime never calls an LLM or a TTS engine.**
- **Storage** — flat JSON files, written atomically. One file per session.
- **Packaging** — one Dockerfile for playing, one for generating. They share nothing but the bank.

See [`spec.md` §14](spec.md) for the architecture, §11–13 for the scenario format, generation pipeline and validator.

## The three ideas worth knowing before reading the spec

**Tasks are the sole ground truth.** There is no priority hierarchy and no inferred intent. A task is a required set of door states, a start time, and a duration it must hold for. If no task covers a door at a given moment, no state is right or wrong. A "conflicting request" is therefore a message with _no task_ — a sympathetic plea to open a door that another thread's live obligation requires stay closed.

**Every scenario must be provably solvable.** The validator replays each generated scenario with a perfect operator — one who makes the minimum toggles at the latest safe moment. If any task still fails, the scenario is unplayable and is rejected. The same pass produces the expected-state trace the admin page renders beside what the player actually did.

**The model writes fiction; Python does the arithmetic.** Every timestamp in a scenario is computed, not written. The generator asks for beats, phases and prose across five small calls, and a scheduler assigns the times — which is what makes the reading budget, the minimum gaps, the challenge clearances and, most of all, solvability hold by construction rather than by luck. The first version that asked the model to do its own arithmetic failed 63 validator checks. See [`spec.md` §12.1.1](spec.md).
