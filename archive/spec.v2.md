# OpStation — Game Specification

**Version:** 2.0 — 2026-08-21
**Status:** design locked on the questions answered in `archive/spec.v1.md` review. Open questions are collected in [Open questions](#open-questions).

---

## 1. Overview

OpStation is a single-player web game in which the player is the **Door Control Operator** of a space station. The player's only actions are opening and closing doors, reading/hearing messages, and answering questions.

The difficulty is deliberately not manual. It is **memory**. The player must hold in their head:

- **which** doors are currently under an obligation;
- **why** each one is in its current state;
- **who** asked for it;
- **since when**;
- **what has to happen before it can change**;
- and **whether the instruction they remember has since been superseded**.

The game is an instrument for measuring how well a person maintains an accurate mental model of many concurrent, interleaved, partially dormant threads. It is deliberately hostile to memory: **there is no message history, no log, no replay.** A message is delivered once and is gone.

A session lasts **20–30 minutes**, runs in **real time (1:1)**, and never pauses.

### 1.1 Non-goals

The game does **not** simulate:

- atmosphere or pressure physics (pressure is narrative only);
- people or vehicles moving through the station;
- pathfinding, blocking or trapping;
- door hardware failures.

Doors have exactly two states: **OPEN** and **CLOSED**. Nothing can prevent the player from operating any door at any time.

---

## 2. Session shape

| | |
|---|---|
| Duration | declared per scenario, 20–30 min (`duration_seconds`) |
| Clock | real time, 1:1, never paused |
| Time base | all scenario times are **relative to session start**, in seconds |
| Station clock | displayed as the machine's wall-clock time, plus an elapsed-time counter |
| Fail state | none — the session always runs to completion |
| End | when the scenario's last task/message resolves, then 3 debrief questions, then the summary page |

### 2.1 Difficulty phases

Phases are a property of the scenario template, expressed as fractions of `duration_seconds`. They constrain the generator, not the runtime.

| Phase | Span | Concurrent threads | Character |
|---|---|---|---|
| 1 — Onboarding | 0 – 15 % | 1 | One obligation at a time. Long windows. Player learns the interface. |
| 2 — Multiple threads | 15 – 38 % | 2–3 | Delayed instructions appear. First conflicting request. |
| 3 — Memory pressure | 38 – 60 % | 3–4 | At least one thread goes silent ≥ 4 min while remaining unresolved. Superseding instructions appear. First Keeper challenge (≥ 50 % mark). |
| 4 — High load | 60 – 80 % | 4 | Civilian traffic thickens. Messages queue behind one another. |
| 5 — Finale | 80 – 100 % | 4+ | A major event dominates. Dormant threads reopen. Fastest message cadence. |

### 2.2 Volume targets per session

- **55–75** messages total.
- **≥ 4** threads, of which **exactly 1** is finale-grade.
- **12–18** everyday one-off exchanges (short, self-contained, 1–2 messages).
- **3** in-session Keeper challenges, all placed at or after the 50 % mark.
- **3** debrief Keeper challenges.

---

## 3. The station

The station layout is **fixed forever** — identical in every scenario and every session. It is authored once, here.

**6 rooms**, **3 corridors**, **5 hangar bays**, **13 internal doors (D1–D13)**, **5 hangar doors (H1–H5)**. Every hangar bay has two doors: an internal one onto the station and an outer one to space.

### 3.1 Authoritative definition

The layout lives in **[`station/station.json`](station/station.json)** (v4) — the single source of truth for areas, door positions, initial door states, hangar roles and the isolation vocabulary of §3.5. The tables below are generated from it; if they disagree, the JSON wins.

To look at it: open **[`station/preview.html`](station/preview.html)** in a browser. It is self-contained (no server needed) and lets you click doors to toggle them. After editing `station.json`, regenerate it:

```
python3 station/build_preview.py
```

[`station/render.js`](station/render.js) is the canvas renderer used by the preview, the printed sector handbook and the game itself. It draws areas, doors and labels, and hit-tests door clicks with an 8 px inflated hit-box so doors stay clickable at small scales.

Orientation listing, generated from `station.json`. `Dn` is an operable door; `..open..` is a permanent doorless passage:

```
C1 NORTH CORRIDOR
     D1       -- HANGAR BAY 1  (shuttle dock)     H1 -> space
     D2       -- HANGAR BAY 2  (visiting berth)   H2 -> space
     D3       -- MEDICAL BAY
     D4       -- C2 CENTRAL JUNCTION
     D5       -- LIVING QUARTERS

C2 CENTRAL JUNCTION
     D4       -- C1 NORTH CORRIDOR
     D6       -- SECURITY
     D7       -- C3 SERVICE CORRIDOR
     D8       -- HANGAR BAY 3  (security EVA)   H3 -> space

C3 SERVICE CORRIDOR
     D7       -- C2 CENTRAL JUNCTION
     D9       -- HANGAR BAY 3  (security EVA)   back route: this bay also opens onto C2
     D10      -- ENGINEERING / REACTOR
     D12      -- HANGAR BAY 4  (cargo)          H4 -> space
     D13      -- HANGAR BAY 5  (construction)   H5 -> Extension Epsilon
     ..open.. -- STORAGE                        no door, can never be closed

links that do not touch a corridor
     D11      -- ENGINEERING / REACTOR <-> HANGAR BAY 4
     ..open.. -- LIVING QUARTERS <-> OBSERVATION DECK     no door, can never be closed
```

**Door numbering.** Internal doors run **top to bottom in horizontal bands, then left to right within a band**. Two useful consequences: every area with two doors gets consecutive numbers (Hangar Bay 3 → D8/D9, Engineering → D10/D11, Hangar Bay 4 → D11/D12), and C1 owns exactly D1–D5. Hangar doors H1–H5 match their bay number.

Two topology details do real work:

- **Hangar Bay 3 touches both C2 (D8) and C3 (D9).** The door graph therefore contains a cycle, and the service sector cannot be sealed with one door — see §3.5.
- **Engineering shares a wall with Hangar Bay 4 (D11).** Isolating Engineering alone takes D10 *and* D11; isolating the pair as one block takes D10 and D12 instead.

### 3.2 Door table

| Door | Connects | Type | State at session start |
|---|---|---|---|
| D1 | Hangar Bay 1 ↔ C1 North Corridor | internal | closed |
| D2 | Hangar Bay 2 ↔ C1 North Corridor | internal | closed |
| D3 | Medical Bay ↔ C1 North Corridor | internal | closed |
| D4 | C1 North Corridor ↔ C2 Central Junction | internal | **open** |
| D5 | Living Quarters ↔ C1 North Corridor | internal | **open** |
| D6 | Security ↔ C2 Central Junction | internal | closed |
| D7 | C2 Central Junction ↔ C3 Service Corridor | internal | **open** |
| D8 | Hangar Bay 3 ↔ C2 Central Junction | internal | closed |
| D9 | Hangar Bay 3 ↔ C3 Service Corridor | internal | **open** |
| D10 | Engineering / Reactor ↔ C3 Service Corridor | internal | closed |
| D11 | Engineering / Reactor ↔ Hangar Bay 4 | internal | closed |
| D12 | Hangar Bay 4 ↔ C3 Service Corridor | internal | **open** |
| D13 | Hangar Bay 5 ↔ C3 Service Corridor | internal | closed |
| H1 | Hangar Bay 1 ↔ space | hangar | closed |
| H2 | Hangar Bay 2 ↔ space | hangar | closed |
| H3 | Hangar Bay 3 ↔ space | hangar | closed |
| H4 | Hangar Bay 4 ↔ space | hangar | closed |
| H5 | Hangar Bay 5 ↔ Extension Epsilon | hangar | closed |

**Doorless passages** (always traversable, can never be closed): Observation Deck ↔ Living Quarters; Storage ↔ C3. Only these two.

### 3.3 Hangar roles

Fixed roles give the generator a consistent vocabulary:

| Hangar | Role |
|---|---|
| H1 | Passenger and medical shuttle dock |
| H2 | Visiting-vessel berth (inspections, damaged ships) |
| H3 | Security EVA airlock |
| H4 | Cargo hangar, sharing a wall with Engineering (D11) and reaching Storage via C3 |
| H5 | Construction hangar → Extension Epsilon |
| H3 | Also the station's only interior shortcut: Hangar Bay 3 links C2 and C3 |

### 3.4 Door states at session start

**Fixed by the station definition, identical in every scenario.** Not a per-scenario field. The generator must reason from this state, and the validator's perfect-player simulation starts from it.

| | Doors |
|---|---|
| **Open** at start | D4, D5, D7, D9, D12 |
| **Closed** at start | D1, D2, D3, D6, D8, D10, D11, D13, H1, H2, H3, H4, H5 |

The rationale, so the fiction stays consistent: the main thoroughfare is open (D4 C1↔C2, D7 C2↔C3), residents move freely (D5), the cargo bay boundary stands open through the shift (D12), and the Hangar Bay 3 shortcut is in normal use (D9). Restricted rooms are closed by default (D3 Medical, D6 Security, D10 Engineering, D11 Engineering↔Hangar Bay 4), the remaining hangar-bay boundaries are closed (D1, D2, D8, D13), and every hangar door to space is closed.

This mix matters for authoring. Obligations naturally fall into two shapes:

- **isolation** — a door that starts open must be held closed (D5, D4, D7, D12, D9);
- **access** — a door that starts closed must be opened for a crossing and closed again (D1, D2, D3, D6, D8, D10, D13, D11, and all hangar doors).

A `hold` obligation on a door that is *already* in the required state is still a real obligation — it is the "resist the tempting request" pattern, and it is not a no-op. Only a `hold: 0` task on an already-satisfied state is a no-op (validator V15).

All 15 doors are always visible to the player, whether or not the current scenario uses them. A scenario may use any subset. Two different scenarios may use the same door for entirely different obligations.

### 3.5 Isolation vocabulary

Instructions often name a *place* rather than a door list — "seal the service sector", "isolate Medical". `station.json` carries **17 named isolation targets**, each with the exact set of doors that seals it, and each tagged with a **class**. These are computed from the door graph and verified against it, so an instruction and its task can never disagree.

| Class | Target | Phrase used in fiction | Close to seal it | Hangar doors inside | Left open (interior) |
|---|---|---|---|---|---|
| **sector** | `central_sector` | the central sector | D4, D7, D9 | H3 | D6, D8 |
| **sector** | `construction_sector` | the construction sector | D7, D9, D10, D12 | H5 | D13 |
| **sector** | `engineering_sector` | the engineering sector | D10, D12 | H4 | D11 |
| **sector** | `north_sector` | the north sector | D4 | H1, H2 | D1, D2, D3, D5 |
| **sector** | `residential_sector` | the residential sector | D5 | — | — |
| **sector** | `service_sector` | the service sector | D7, D9 | H4, H5 | D10, D11, D12, D13 |
| **sector** | `storage_sector` | the storage sector | D7, D9, D10, D12, D13 | — | — |
| **room** | `engineering` | Engineering / the reactor | D10, D11 | — | — |
| **room** | `medical_bay` | the Medical Bay | D3 | — | — |
| **room** | `security` | Security | D6 | — | — |
| **bay** | `hangar_bay_1` | Hangar Bay 1 | D1 | H1 | — |
| **bay** | `hangar_bay_2` | Hangar Bay 2 | D2 | H2 | — |
| **bay** | `hangar_bay_3` | Hangar Bay 3 | D8, D9 | H3 | — |
| **bay** | `hangar_bay_4` | Hangar Bay 4 | D11, D12 | H4 | — |
| **bay** | `hangar_bay_5` | Hangar Bay 5 | D13 | H5 | — |
| **corridor** | `central_junction` | the central junction | D4, D6, D7, D8 | — | — |
| **corridor** | `north_corridor` | the north corridor | D1, D2, D3, D4, D5 | — | — |

The class matters because the four kinds are not equally hard:

| Class | | Difficulty |
|---|---|---|
| `room`, `bay`, `corridor` | A single area — Medical, Security, Hangar Bay 2, C1 | **Easy.** The place has its own visible wall, and the door on that wall is the door that seals it. Nothing to learn. |
| `sector` | A volume spanning more than one area — the north sector, the service sector | **Hard.** Which doors bound it is not visible on the map, and the answer is often not the one door you would guess. |

Seven of the seventeen are sectors, and they are the only ones worth teaching in advance (§3.6). The word **sector** is reserved for them: single rooms, bays and corridors keep their own names, and "section" is never used in the fiction.

One pair is worth knowing about, because it looks like a contradiction. `construction_sector` is **nested inside** `service_sector` and yet needs **more** doors — D7, D9, D10, D12 against D7, D9. Leaving Engineering and Hangar Bay 4 *outside* the sealed volume turns their corridor doors into boundary doors. Sealing a smaller place is not always cheaper.

**Hangar doors inside** are added only when the fiction concerns vacuum or pressure — sealing a volume against space also means closing the hangar doors within it.

**Doors interior to the volume stay open**, and this is the part that reads as a bug until you see it drawn. Sealing a place means closing its *boundary*, not everything within it. Sealing the service sector closes **D7 and D9** and leaves **D10–D13** alone, because Engineering, Hangar Bay 4 and Hangar Bay 5 are all *inside* the sealed volume — shutting their doors would isolate them from each other, not from the rest of the station. `interior_doors` is recorded per target so the generator, the validator and the debrief all agree on which doors are legitimately still open. In [`station/preview.html`](station/preview.html), clicking a target opens every door, closes only the cut, and tints the sealed volume amber, which makes this immediately obvious.

Note also what the Hangar Bay 3 bypass does to this table. Sealing **the service sector** takes **D7 and D9**, not D7 alone: a player who remembers only the obvious junction door leaves the back route through Hangar Bay 3 wide open and fails the obligation. The same applies to the central sector and to the construction end. This is the single most valuable thing the layout contributes to the game — a plausible-looking answer that is one door short.

#### Places that cannot be isolated

A doorless passage crosses the boundary of these, so none can be sealed on its own. An instruction to isolate one of them is rejected by the validator; the generator must name the enclosing volume instead.

| Area | Permanently open to | Smallest sealable volume containing it |
|---|---|---|
| Storage | C3 Service Corridor | `storage_sector` (Storage + C3) |
| C3 Service Corridor | Storage | `storage_sector` (Storage + C3) |
| Observation Deck | Living Quarters | `residential_sector` (Living Quarters + Observation Deck) |
| Living Quarters | Observation Deck | `residential_sector` (Living Quarters + Observation Deck) |

Both pairs are deliberate hooks:

- **The Observation Deck has no door of its own.** "Isolate the observation deck" means closing **D5**, which seals Living Quarters along with it. A player looking for a door on the Observation Deck will not find one.
- **Storage is the mirror case.** It hangs off C3 with no door, so "seal Storage" means sealing the entire service corridor — the `storage_sector` target, five doors: D7, D9, D10, D12, D13. This is the largest cut in the game and a good finale obligation.

### 3.6 Printed sector reference

The sectors are the one part of the station a newcomer cannot read off the map, and working them out from scratch is not what a session is meant to measure. So they are printed and handed over beforehand, like the reference card that comes with a board game.

```
python3 station/build_sector_sheets.py           # -> station/sector-sheets.html
python3 station/build_sector_sheets.py --png     # also -> station/sectors/*.png
```

`sector-sheets.html` is self-contained and print-ready — A4 portrait, `@page` rules, no page break inside a card. Open it and print, or print to PDF. `--png` additionally writes one image per sector for slides or a wiki; it needs Chrome or Chromium on PATH.

**Page 1** is one large labelled map, with the five things a newcomer needs, in prose: how doors are numbered, how to read a card, that sealing means closing the boundary and not everything inside, that two places have no door of their own, and that Hangar Bay 3 is a shortcut.

**Page 2** is seven cards, one per `sector` — and *only* the sectors. Each card carries an unlabelled silhouette of the station with the sealed volume tinted amber and every door open except the cut, plus three door lists: **CLOSE**, **+ PRESSURE** (hangar doors inside the volume), and **INSIDE** (doors left open because they are interior to it). Rooms, bays and corridors get no card — each has its own visible wall, and the door on that wall is the door that seals it, so printing them would bury the seven that actually need learning.

The cards are drawn by [`station/render.js`](station/render.js), the same renderer the game uses, so a change to the map or to the drawing shows up in the handbook with no second implementation to keep in step. Every value on them comes from `station.json`; nothing is transcribed by hand.

---

## 4. Player controls

The player can:

- **toggle any door** (open ↔ closed) at any time, by clicking it on the station canvas;
- **open the pending notification** (the front of the queue);
- **acknowledge** the open notification, which dismisses it permanently;
- **answer** a Keeper challenge.

There is nothing else. No inspect, no notes panel, no history, no replay, no pause. Pen and paper are permitted outside the software.

---

## 5. Messages and the notification queue

### 5.1 Channels

Every message has a `channel`:

| Channel | Presentation |
|---|---|
| `text` | Written text in the modal, revealed character by character rather than all at once. No audio underneath other than a soft typing cue. |
| `radio` | **Audio only** — pre-rendered TTS in the sender's voice, bookended by a channel-open and channel-close cue with quiet static underneath, and a CSS "speaking" bar animation. No transcript, ever, and **no fallback**: if the audio cannot be played the session is void, not degraded. |

Radio messages carry more memory load than text, which is the point. Transcripts exist in the scenario JSON and are visible on the admin page only — never to the player, in any circumstance.

**Audio unlock.** Browsers block audio until the page has received a user gesture, so a session that opened silently would be unplayable and unrecoverable. The **Start shift** button is that gesture: it must both create the session and prime the audio context, and the client must verify playback works before the clock starts. If priming fails, refuse to start the session rather than beginning one that will have to be thrown away.

#### 5.1.1 Sound design

Every cue is a short fixed asset in `assets/sfx/`, played through a plain `HTMLAudioElement` (no Web Audio graph — that machinery buys nothing for a handful of one-shots and loops, and connecting an `AnalyserNode` is a well-known way to end up with audio that silently never reaches the speakers). Assets:

| Asset | Used for |
|---|---|
| `door_open.wav` / `door_close.wav` | Played once per door whose state actually changed between two server pushes — diffed against the previous snapshot, never against the click, so it reflects what happened rather than what was attempted. |
| `notification.wav` | Played once whenever `pending_count` increases. |
| `radio_start.wav` / `radio_end.wav` | Bookend a radio message's voice audio: the start cue plays, *then* the voice, then the end cue on `ended`. Sequential, not layered, so the words never compete with the effects. `radio_end.wav` also plays at the end of a text message's character reveal (§5.1, `text` row) — the same "transmission closed" cue serves both channels. |
| `radio_noise.wav` | Quiet (≈6% volume) station static, looped under the start cue and the voice, seeded at a **random offset** into the file on every play so it never sounds identically looped twice. Faded in over 0.6 s rather than starting abruptly. |
| `writing.wav` | Looped, faded in over 0.3 s, under a `text` message's character-by-character reveal; stopped and faded out the moment the last character lands. |

**The radio waveform is pure CSS**, not a frequency-domain reading of the audio: a row of bars with a `@keyframes` pulse, toggled by a `.playing` class the instant the voice begins. This is a deliberate simplification over an `AnalyserNode`-driven visualisation — the earlier version could silently fail to hook up (leaving the panel looking dead while the audio played perfectly well) or, worse, redirect the element's output through a graph that was never connected back to the destination. A CSS animation cannot fail that way: if the class is toggled, it animates, on every browser, independent of whether the analyser API exists or behaves.

**Cleanup.** Every sound and timer started while a modal is open is tracked, and stopped unconditionally when the modal closes — whether by Acknowledge or by the next queued item replacing it. Radio is audio-only and heard once; a background loop or a voice clip left playing after its modal has gone would quietly reopen the "no replay" guarantee (§1) from underneath it.

### 5.2 The queue

- The player is **not told who is calling, or how urgent it is**, before opening a notification. Only that one is waiting.
- Messages are delivered by the server at their scheduled `at`. A delivered, unopened message sits in a **FIFO queue**.
- Only the **oldest** queued message is presented. The rest are invisible except as a **pending count** on the notification button.
- Opening a message shows the sender portrait and name, and plays audio if it is a radio message.
- The modal can only be dismissed with **Acknowledge**. Attempting to close it otherwise shakes the modal.
- Once acknowledged, the message is **gone forever**. There is no way back to it.
- If a message's task fails while the message is still unopened, the message is **removed from the queue unread** and the corresponding failure notice is delivered instead.

### 5.3 Reading budget

Because the clock never stops, the generator must leave the player time to actually consume messages. Define:

```
read_cost(text  message) = clamp(2.0 + words / 3.0, 4.0, 25.0)     # ≈180 wpm + 2 s to acknowledge
read_cost(radio message) = audio_duration + 2.0
```

Enforced by the validator (see §11): earliest task per message, rolling density cap, minimum inter-message gap.

---

## 6. Tasks — the correctness model

**Tasks are the sole ground truth.** There is no priority hierarchy, no authority ranking, no inferred intent. If the scenario does not contain a task, no door state is right or wrong.

### 6.1 Task shape

```json
{
  "id": "t_020",
  "group_id": "og_ext_isolation",
  "message_id": "m_012",
  "at": 300,
  "hold": 540,
  "require": { "D13": "closed", "H5": "closed" },
  "fail_message": "WARNING — pressure loss near Extension Epsilon. D13 was opened during depressurisation."
}
```

- `at` — seconds from session start when evaluation begins.
- `hold` — seconds the condition must hold **continuously**. `0` means a single instantaneous check at `at`.
- `require` — a map of door → required state. All entries must hold simultaneously.
- `fail_message` — delivered to the player the moment the task fails.

### 6.2 Evaluation

At every tick (250 ms) within `[at, at + hold]`, the runtime compares each door in `require` against its actual state.

- **First mismatch → task FAILED.** The `fail_message` is delivered immediately, one penalty is applied, and monitoring of that task stops (no repeated penalties for one broken obligation).
- **No mismatch through the whole window → task PASSED.**

### 6.3 Task groups and cascade cancellation

Tasks that together express one obligation share a `group_id`. **When a task fails, every later task in the same group is cancelled** — not evaluated, not scored, no message.

This exists to fix two problems (see §6.4). One broken obligation costs exactly one penalty.

### 6.4 Why `hold` and cascade cancellation were added — two holes in the checkpoint-only model

Your proposal was: a task is *a condition plus an instant*; check the condition at that instant. The three-checkpoint encoding of *"in 2 min, have the door open at least 30 s, then close it"* becomes, at t₀ = 0:

```
{ at: 120, require: {D3: open}   }
{ at: 150, require: {D3: open}   }
{ at: 160, require: {D3: closed} }
```

**Hole 1 — sampling is blind between checkpoints.** A player who opens D3 at t=119, closes it at t=121, and reopens at t=149 passes both open-checks while the crew was locked out for 28 of the 30 seconds. Worse case: an obligation like *"keep D7 closed for 12 minutes"* can only be expressed as instantaneous samples, so the player can open D7 freely between samples with no consequence — which destroys exactly the gameplay the game exists to test (the tempting request the player must refuse).

`hold` closes it: the condition is checked continuously, and the failure fires *at the moment of violation*, which is also better feedback than a delayed verdict.

With `hold`, your example collapses to two tasks, and says precisely what you meant:

```
{ at: 120, hold: 30, require: {D3: open},   fail: "You didn't have D3 open for the crossing." }
{ at: 160, hold: 0,  require: {D3: closed}, fail: "You didn't close D3 afterwards." }
```

**Hole 2 — false passes.** If the player never opens D3 at all, checkpoint 1 fails (correct), but checkpoint 3 (`D3: closed`) **passes**, because the door happens to be closed for the wrong reason. The player is credited for an obligation nobody fulfilled, and is simultaneously penalised twice for one mistake (checkpoints 1 and 2). Cascade cancellation fixes both: checkpoint 1 fails, checkpoint 2 and 3 are cancelled, one penalty.

### 6.5 Conflicting requests

With no priority system, a genuine contradiction would be unfair. So a "conflicting request" is authored as a **message with no task at all** — a plausible, sympathetic plea to open a door that a *different* thread's live `hold` obligation requires to stay closed.

- Player refuses → nothing happens, no penalty. Correct.
- Player complies → the other thread's `hold` window is violated → that task fails, its `fail_message` fires.

The validator (rule V17) requires every message marked `kind: "tempting_request"` to actually be tempting: it must target a door that is under a contradictory active `hold` at that moment. Otherwise it is harmless noise.

### 6.6 Immediate tasks

An "act now" instruction is a task with `hold: 0` and a small offset from the message. The generator must not produce an instruction to open a door that is already open (or close one already closed) in the perfect-player trace — validator rule V15. Such a task would be a silent free pass.

**Confirmation.** A task with `hold: 0` *and* `delay: 0` — nothing to hold, no offset, an instruction complied with immediately — sets `Task.confirm: true` at assembly time. When such a task passes, the engine logs `task_confirmed` with a text composed mechanically from `require` (`"D3 open"`, never authored prose) and the session broadcasts it directly over the websocket as `{"type": "confirmed", "text": ...}`. This bypasses the FIFO queue entirely: it needs no opening and no acknowledging, and must never compete with a real message for the player's attention. The client renders it as a small toast that dismisses itself after a few seconds. A task with any `hold` is never confirmed — it is judged much later, when a ping would be noise rather than reassurance.

---

### 6.7 Retractions — cancelling an obligation

An actor can withdraw an instruction. This is the cheapest way to create real memory difficulty, because the player must work out **which** obligation is being withdrawn.

A retraction is a message carrying `cancels`:

```json
{
  "id": "m_040",
  "at": 902,
  "thread_id": "th_med",
  "actor_id": "a_med",
  "channel": "radio",
  "kind": "retraction",
  "retraction_style": "self_reference",
  "cancels": ["og_med_isolation"],
  "text": "Door Control, Medical. Forget what I asked you earlier — it no longer applies."
}
```

- `cancels` holds ids. `og_…` cancels a whole obligation group; `t_…` cancels individual tasks.
- **A cancellation takes effect at `message.at` — on delivery, not on acknowledgement.** Acknowledgement time is player-controlled, so making it the trigger would put the ground truth at the mercy of how fast the player clicks, and would make the perfect-player simulation non-deterministic. On delivery it is exact and checkable.
- Cancelled tasks are never evaluated and never scored. A player who has not yet read the retraction simply keeps doing the old thing, which now costs nothing.

### 6.7.1 Difficulty tiers

`retraction_style` records how much the player has to reconstruct. The generator picks the tier; the validator enforces that each one is actually answerable.

| Style | Message says | The player must recall |
|---|---|---|
| `explicit` | the door **and** the action | nothing — it is spelled out. *"Ignore my earlier instruction about keeping D3 closed."* |
| `self_reference` | neither door nor action | which obligation **this actor** created. *"Cargo here — forget what I told you earlier."* |
| `cross_actor` | names a **different** actor | who created which obligation, plus that this actor may speak for them. *"Security: Medical's isolation on D3 is no longer needed, the patient was moved."* |
| `partial` | keeps part, drops part | the internal structure of one obligation. *"You still need D10 closed. Forget the reopen I asked for."* |

### 6.7.2 Retractions need teeth

A retraction on its own has no mechanical consequence — there is no task, so there is nothing to fail. Its value only materialises later, in one of two ways:

1. **A later task requires the opposite state** on the freed door. A player who still believes the old restriction refuses to open it, and fails that task. This is the form with real bite.
2. **A challenge** whose correct answer depends on knowing the obligation was withdrawn.

The validator requires every retraction to have at least one of these, and at least half of them to have form 1 (V29). Without that rule the generator will happily produce retractions that are pure decoration.

### 6.8 Indirect obligations — "isolate the service sector"

The most interesting instructions do not name doors. They name a **place**, and the player has to work out which doors that implies.

> **Engineering:** Pressure is dropping somewhere past the junction. Seal the service sector until we find it.

The task's `require` map stays fully explicit — the ground truth is never inferred at runtime — but it is *derived* from a named isolation target (§3.5), and the derivation is recorded so the validator can check the message and the task agree:

```json
{
  "id": "t_051",
  "group_id": "og_leak_isolation",
  "message_id": "m_061",
  "at": 655,
  "hold": 300,
  "derived_from": { "isolation_target": "service_sector", "include_hangar_doors": true },
  "require": { "D7": "closed", "D9": "closed", "H4": "closed", "H5": "closed" },
  "fail_message": "PRESSURE ALARM — the service sector is still open to the rest of the station."
}
```

The validator (V23) recomputes the cut-set from the door graph and rejects the task if `require` does not match exactly. That makes the map load-bearing: change a door in `station.json` and every derived task is re-checked automatically.

The example above is a live demonstration. **D9 is in that `require` map only because Hangar Bay 3 bridges C2 and C3.** Omit it and the sector is not actually sealed; remove the bypass from the map and V23 rejects the task for carrying a door that is no longer on the boundary.

`require` lists the **cut only** — never the volume's interior doors. D10–D13 sit inside the service sector and stay open; requiring them closed would be a different, larger obligation, and V23 rejects it.

Difficulty comes free with this. Three levels, all expressible with the same field:

| | Instruction | What the player must know |
|---|---|---|
| easy | "Close D7." | nothing |
| harder | "Seal the service sector." | which doors bound that sector |
| hardest | "Isolate the observation deck." | that it has **no door of its own**, so the answer is D5 — which also seals Living Quarters |

An indirect instruction must name a target that exists in `station.json` and is actually isolable; "seal Storage" is rejected, because a permanent opening to C3 makes it impossible.

**Mix per phase.** Directness is a difficulty dial, so it follows the phase progression:

| Phase | Instructions |
|---|---|
| 1 — Onboarding | **direct only** — the player is still learning what the doors are |
| 2–3 | roughly **half** indirect |
| 4–5 | **mostly** indirect |

The observation-deck trick is used **at most once per session**: it only surprises the player the first time, and repeating it turns a realisation into a chore.

Isolation obligations are also the natural home for long `hold` windows, and therefore for tempting requests: a sealed sector is exactly what people keep asking you to let them through.

---

## 7. Failure notices

A failed task produces a **failure notice**: a short, in-fiction consequence message from the affected actor or from `system`.

- Failure notices enter the **same FIFO queue as messages, at the same priority**. There is no priority system anywhere in the game.
- They are `text` channel, no audio — they must be readable instantly.
- They are visually distinct (alert styling).
- They require acknowledgement like any other modal.
- At most **one failure notice per task group per `failure_notice_cooldown_seconds`** (default 30) is queued; further ones are dropped, though the penalty is still recorded.

The cooldown is the only guard against a failure cascade burying the messages the player needs in order to recover. It is a difficulty tunable (§9.2) — lowering it makes a bad run spiral, raising it is more forgiving.

---

## 8. Keeper challenges

Challenges test whether the player still holds the thread history. They are disguised as ordinary station traffic — a person asking a question, not a quiz.

> **Security:** Door Control, why is D7 still closed?

### 8.1 Format

- **4 authored options + a fixed 5th option, "I don't know."** The 5th is supplied by the UI and never appears in the scenario JSON.
- Exactly one authored option is correct.
- Delivered through the normal notification queue, as `text` or `radio`.
- **Answering is mandatory:** the modal cannot be dismissed until an option is chosen. But **the station canvas stays live** — doors can still be operated behind the modal, and the clock never stops. Nothing in this game freezes time.
- **No time limit.** The world keeps running and tasks keep being evaluated, so a long deliberation costs elapsed time — but never an obligation the player could not reach, because the doors are never locked.
- After answering, the correct answer and a one-line explanation are shown, then acknowledged away.
- A wrong answer costs one penalty. **"I don't know" costs the same penalty**, but is recorded as its own outcome so the debrief can distinguish it from a confident wrong answer.

### 8.2 Placement

- **3 in-session**, the first no earlier than the 50 % mark, biased toward threads that have been **dormant ≥ 3 minutes**.
- **3 in the debrief**, after the session ends, covering the whole shift including threads that have not been heard from in 10+ minutes. The debrief is **untimed** — nothing can fail by then, so it measures retained knowledge rather than reaction speed.
- Times are written into the scenario; the generator chooses them.
- Validator rule V11 still keeps every **in-session** challenge clear of any task boundary by `challenge_task_clearance_seconds`, so a question never lands exactly on a deadline. Debrief challenges are exempt — the session is over.

### 8.3 Challenge kinds

Each challenge declares a `kind`. Aim for one of each per group of three.

| Kind | Tests | Examples |
|---|---|---|
| `thread` | Connecting information belonging to one event | *Why is D7 currently closed? / Is the construction incident finished? / Which door is associated with Technician Ruiz?* |
| `time` | Chronology and pending intentions | *Which restriction expires first? / How long has D10 been closed? / What were you asked to do after the coolant test?* |
| `provenance` | Source and evolution of information | *Who authorised D6 to reopen? / Who contradicted the asteroid report? / Medical said D3 could reopen — is that still valid?* |

### 8.4 Pretexts — why an actor is asking

A challenge must never read as a quiz. Someone asks because **they need the answer for their own reasons**, and those reasons are worth authoring properly: they carry the fiction, and they make the question memorable.

| Pretext | Example | Kind |
|---|---|---|
| Building a case | *Security: someone let a man into the service corridor an hour ago. Who authorised that door?* — they intend to arrest whoever went through | `provenance` |
| Assigning blame | *Works: something got broken on the way out through Hangar Bay 4. Who was the last crew you let through H4?* | `provenance` / `time` |
| Tracing a contact chain | *Medical: I need the first patient. Which hangar did the sick passenger come in through, and who else moved through Medical after that?* | `thread` / `time` |
| Reconstructing a timeline | *Command: I am writing the incident report. How long was the north sector sealed?* | `time` |
| Disputing a lockout | *Civilian: I was stuck in the observation deck for ten minutes. Who told you to keep that shut?* | `provenance` |
| Reconciling a manifest | *Works: the transfer log says two crossings at D12. I count one. Which is it?* | `time` |
| Checking before acting | *Security: we need D10. Is there anything live on it right now?* | `thread` |
| Auditing a supposedly closed incident | *Command: is the extension incident actually finished, or just quiet?* | `thread` |

Two rules make these carry weight:

- **A pretext may span threads and actors.** The actor asking need not own the thread being asked about — Security asking about a door Medical restricted is better than Medical asking about their own. Cross-actor questions are where provenance memory actually gets tested.
- **The pretext should imply a consequence.** "So I can arrest him" or "so I can file the report" gives the player a reason to care about being right, and makes a wrong answer feel like a wrong answer rather than a lost point.

### 8.5 Distractor rules

Distractors must be drawn from **other real threads in this same scenario** — real reasons, real actors, real doors — and must be false at the moment the question is asked. Generic filler ("routine maintenance") is not acceptable. See validator V21.

---

## 9. Scoring

One single scale: **penalty points**, all of equal weight. No weighting, no tolerance windows, no partial credit.

| Event | Cost |
|---|---|
| Task failed | 1 penalty |
| Challenge answered wrongly | 1 penalty |
| Challenge answered "I don't know" | see [Open questions](#open-questions) Q-A |

During play the player sees only the **running total**. Nothing else — no breakdown, no list, no indication of which thread a penalty came from.

### 9.1 Difficulty tunables

Everything that shapes pressure lives in **`config/difficulty.json`**, loaded at startup and shown on the admin page. Scenario generation reads the same file, so a scenario is generated against the tunables it will be played with.

| Key | Default | Effect |
|---|---|---|
| `tts_engine` | `piper` | Which TTS backend the generator uses |
| `tts_sentence_gap_seconds` | 1.0 | Silence between sentences of a spoken message. Changing it changes every `audio_duration`, so the bank must be re-rendered and re-validated |
| `tick_ms` | 250 | Task-evaluation resolution |
| `failure_notice_cooldown_seconds` | 30 | Min gap between failure notices from one task group |
| `penalty_per_failed_task` | 1 | |
| `penalty_per_wrong_answer` | 1 | |
| `penalty_per_dont_know` | 1 | Same as a wrong answer, but logged distinctly so the debrief can separate aware-of-not-knowing from confidently-wrong |
| `read_cost_base_seconds` | 2.0 | Acknowledgement overhead per message |
| `read_cost_words_per_second` | 3.0 | ≈180 wpm |
| `read_cost_min_seconds` / `_max_seconds` | 4.0 / 25.0 | Clamp |
| `task_slack_after_message_seconds` | 10 | Extra room before a message's first task (V7) |
| `min_message_gap_seconds` | 6 | Floor on message spacing (V9) |
| `read_budget_window_seconds` | 60 | Rolling density window (V8) |
| `read_budget_phase1` / `_mid` / `_finale` | 20 / 35 / 45 | Seconds of reading allowed per window |
| `challenge_task_clearance_seconds` | 20 | Dead zone around an in-session challenge (V11) |
| `challenge_blocks_doors` | **false** | The challenge modal never locks the station canvas — time is never frozen and doors stay operable |
| `show_pending_count` | true | Whether the notification button shows how many are queued |
| `radio_transcript_fallback` | **false** | Never true in practice — audio failure voids the session (§5.1) |
| `generator_repair_attempts` | 5 | Validator → LLM repair loop limit |

Changing a tunable that the validator depends on (`read_*`, `task_slack_*`, `min_message_gap_*`, `challenge_task_clearance_*`) invalidates existing scenarios. The admin page flags bank entries validated against different tunables.

### 9.2 Debrief and summary page

After the 3 debrief challenges, the summary page reveals the breakdown the player could not see during play:

- total penalties;
- every failed task: the thread it belonged to, the obligation, the door(s), the requesting actor, when it was requested, when it failed;
- every challenge: the question, the player's answer, the correct answer, the thread;
- per-thread roll-up — how many penalties each thread cost;
- elapsed time and number of messages left unread when their task expired.

---

## 10. Threads and event catalogue

A **thread** is one incident: a sequence of linked messages spanning phases, with dormant gaps, updates that supersede earlier instructions, an apparent resolution, and optionally a reopening.

Every thread carries an internal state used for authoring and for the admin view:

```
not_started → active → waiting → active → resolved → reopened → resolved
```

The distinction between **waiting** (nothing is happening in the thread, but it is not finished) and **resolved** is the single most important thing the game tests. A thread in `waiting` still has live `hold` obligations and no releasing message yet.

### 10.1 Catalogue

The generator selects **≥ 4** threads: exactly one finale-grade, the rest ordinary.

**Ordinary threads**

| Thread | Core obligation shape |
|---|---|
| Construction of Extension Epsilon | Long `hold` on D13 and H5 while the extension is depressurised; two delays; tempting civilian requests; release after pressure test; possible reopening. |
| Damaged transport vessel | H2 opened for emergency docking, then held closed pending inspection; the crew requests departure before Security clears them; contradictory damage reports (provenance). |
| Pressure leak | D7 and D10 closed to isolate; a resident is trapped inside; a narrow authorised opening of one door only; the two doors are released at different times. |
| Missing technician | D12 opened for a named technician; thread goes silent; radio contact lost; search party; technician resurfaces 10 min later. Pure delayed recall. |
| Medical quarantine | H1 then D3 held closed; an initial "negative test, reopen in 5 min" that is then **retracted**; second test clears it. Pure superseding-information test. |
| Reactor maintenance | D10 closed with a stated duration but **no automatic release message**; a third party asks to use it; the player must know Engineering never confirmed. |
| Contamination containment | Storage/C3 isolation via D7 and D12; escalating scope. |
| VIP inspection | Command-imposed route restrictions that shift as the inspection party moves. |

**Finale-grade threads** (exactly one per scenario, occupying phase 5)

| Thread | Shape |
|---|---|
| Invaders attack the station | Patrol finds an abandoned ship → weapons damage → recall all teams → lockdown countdown while teams are still outside → seal hangars → a hangar forced open → retreat routes opened and closed under time pressure → dormant threads reopen → "sector secure" that does **not** release all obligations → lockdown lifted. |
| Catastrophic hull breach | Progressive sector-by-sector isolation, evacuation corridors, revised isolation boundaries. |
| Reactor emergency | Escalating engineering isolation, forced venting windows, personnel extraction. |
| Station-wide contamination | Rolling quarantine boundaries that move room by room. |

The invasion must **not** always be the finale.

### 10.2 Everyday exchanges

12–18 short self-contained exchanges provide background load: a resident wanting D5, a cargo transfer through D12, a maintenance inspection, a shuttle docking at H1, a brief environmental hold. They are 1–2 messages with 1–3 tasks and no dormancy.

---

## 11. Scenario format

A scenario is a directory in the bank:

```
data/scenarios/<scenario_id>/
  scenario.json
  audio/
    m_012.wav
    q_001.wav
    ...
  validation.json      # validator report, written at generation time
```

### 11.1 `scenario.json`

```json
{
  "scenario_id": "sc_20260821_epsilon_a1",
  "name": "Epsilon Extension",
  "generated_at": "2026-08-21T10:32:00Z",
  "generator": { "model": "...", "template_version": "3", "seed": 4711 },
  "station_version": "v1",
  "duration_seconds": 1620,

  "actors": [
    {
      "id": "a_sec",
      "type": "security",
      "name": "Officer Kade Ruiz",
      "portrait": "security.png",
      "voice": "security"
    }
  ],

  "threads": [
    {
      "id": "th_ext",
      "title": "Extension Epsilon pressure isolation",
      "catalogue_key": "construction_extension",
      "grade": "ordinary",
      "phase_span": [1, 5],
      "debrief_summary": "Construction depressurised Extension Epsilon at 05:00; H5 held closed; released after the pressure test at 19:40; reopened at 24:10 after a pressure drop."
    }
  ],

  "task_groups": [
    {
      "id": "og_ext_isolation",
      "thread_id": "th_ext",
      "label": "Keep H5 closed while Extension Epsilon is depressurised"
    }
  ],

  "messages": [
    {
      "id": "m_012",
      "at": 245,
      "thread_id": "th_ext",
      "actor_id": "a_con",
      "channel": "radio",
      "kind": "instruction",
      "text": "Door Control, Construction. We're venting Extension Epsilon in one minute. H5 stays closed until I clear it — no exceptions.",
      "audio": "audio/m_012.wav",
      "audio_duration": 7.4,
      "read_cost": 9.4,
      "task_group_id": "og_ext_isolation"
    },
    {
      "id": "m_040",
      "at": 902,
      "thread_id": "th_ext",
      "actor_id": "a_con",
      "channel": "radio",
      "kind": "retraction",
      "retraction_style": "self_reference",
      "cancels": ["og_ext_isolation"],
      "text": "Door Control, Construction. Stand down on what I asked you earlier — we finished the vent cycle early.",
      "audio": "audio/m_040.wav",
      "audio_duration": 8.1,
      "read_cost": 10.1
    }
  ],

  "retractions_note": "a retraction is just a message with a `cancels` array — see the second message below",

  "tasks": [
    {
      "id": "t_020",
      "group_id": "og_ext_isolation",
      "message_id": "m_012",
      "at": 305,
      "hold": 540,
      "require": { "H5": "closed" },
      "fail_message": "PRESSURE ALARM — Extension Epsilon vented to the service corridor. H5 was opened during depressurisation."
    }
  ],

  "challenges": [
    {
      "id": "q_001",
      "at": 880,
      "slot": "in_session",
      "kind": "thread",
      "thread_id": "th_ext",
      "actor_id": "a_sec",
      "channel": "text",
      "prompt": "Door Control, Security here. Why is H5 still locked out? I have a team that wants to stage equipment.",
      "options": [
        { "id": "o1", "text": "Extension Epsilon is depressurised for construction.", "correct": true },
        { "id": "o2", "text": "Medical quarantine of the north corridor.", "correct": false },
        { "id": "o3", "text": "Cargo transfer in progress from Hangar 4.", "correct": false },
        { "id": "o4", "text": "Engineering is flushing reactor coolant.", "correct": false }
      ],
      "explanation": "Construction requested H5 held closed at 04:05 while venting the extension, and has not cleared it."
    }
  ],

  "debrief_challenges": [ "...same shape, slot: \"debrief\", at is ignored..." ]
}
```

Notes:

- `"I don't know"` is a constant supplied by the UI, never present in the JSON.
- `message.kind` ∈ `instruction | update | supersede | retraction | status | tempting_request | resolution | reopen | chatter`. The set is closed and V1 enforces it: `kind` is what the admin page reads to tell a release from a withdrawal, and what V17 reads to find a tempting request. Generation maps the synonyms a model reaches for — `confirmation`, `alert`, `correction` — onto the enum rather than widening it.
- `cancels` and `retraction_style` appear only on `kind: "retraction"` messages (§6.7).
- Door states at session start come from `station/station.json`, never from the scenario.
- `at` is always **seconds from session start**, integer.
- Every message with a `task_group_id` is the message that *creates or updates* that obligation.
- A challenge carries **`depends_on`**: the message ids its correct answer rests on. Added during implementation, because two rules are otherwise unverifiable — V19 has to check that everything the answer depends on was delivered *before* the question, and V29 has to recognise a retraction whose teeth are a challenge rather than a later task. Without it both rules can only be guessed at.

### 11.2 Actors

Exactly **6 actor types**, fixed forever, each with one portrait and one pinned TTS voice. The assignment lives in **[`config/voices.json`](config/voices.json)**, with the reasoning for every pick recorded there.

| Type | Piper voice | Portrait | Role |
|---|---|---|---|
| `security` | `en_GB-northern_english_male-medium` | `assets/portraits/security.png` | Patrols, EVA, inspections, lockdowns |
| `construction` | `en_US-joe-medium` | `assets/portraits/construction.png` | Extension work, exterior operations |
| `cargo` | `en_US-kusal-medium` | `assets/portraits/cargo.png` | Transfers, storage, low-priority traffic |
| `medical` | `en_GB-cori-high` | `assets/portraits/medical.png` | Patient transport, quarantine |
| `civilian` | `en_GB-alba-medium` | `assets/portraits/civilian.png` | Residents, researchers, routine requests |
| `system` | `en_US-lessac-high` + `pa_intercom` | `assets/portraits/system.png` | Automated alerts, alarms, failure notices |

The six were chosen for **pairwise distinctness**, not for individual quality: three male, three female, across six accents (Northern English, American, Sri Lankan English, British RP, Scottish, American-neutral). The weakest pair is Medical against Civilian — both British female, separated by RP versus Scottish. Multi-speaker models (`libritts`, `arctic`, `vctk`) were rejected because speaker selection inside them is not stable enough to pin; the three `low`-quality models were rejected because radio messages carry no transcript, so intelligibility is not optional.

The `system` voice additionally runs through a **band-limiting intercom filter** at generation time (`highpass 400 Hz`, `lowpass 3400 Hz`, hard compression). Without it the station's automated voice is simply a seventh person and provenance gets muddier; with it, "the station said it" is audibly different from "somebody said it".

**Changing a pinned voice after scenarios exist silently invalidates every provenance question in the bank.** Treat `config/voices.json` as append-only.

### 11.3 Portraits

Head-and-shoulders, one per actor type: `assets/portraits/<type>.png`, **512×512 PNG**, displayed at roughly 160 px to the left of the message body.

Placeholders exist now — flat silhouettes, role-tinted, with an accent collar so the six are told apart at a glance; the `system` portrait is a speaker grille rather than a person. Regenerate with:

```
python3 assets/make_placeholder_portraits.py
```

Replace with real artwork later, keeping the filenames and the size.

### 11.4 Actor rules

- Each scenario instantiates **one named individual per type**, and that individual is the same person for the entire scenario. Names and personalities change between scenarios.
- A voice is never shared between two people. Since there is one person per type, the voice unambiguously identifies the speaker — which is what makes provenance questions answerable.
- Messages may be *about* a group ("two workers are still outside near H5"), and an actor may reference a group, but a group never speaks.

---

## 12. Scenario generation

Scenarios are **generated offline into a bank** and played deterministically at runtime. **The runtime never calls an LLM or a TTS engine.**

### 12.1 Pipeline

1. **Template selection** — a hand-authored JSON template fixes the structure: `duration_seconds`, phase boundaries, thread count and grades, how many tempting requests, how many superseding updates, dormancy requirements, challenge slots and kinds, volume targets.
2. **LLM fill** — the LLM receives the station map, the actor roster, the task/`hold` semantics, the template, and the timing rules. It produces `scenario.json`: actor names, thread instantiations, message prose, timings, tasks, `fail_message` texts, challenges with distractors and explanations.
3. **Validation** — the validator (§13) runs. On failure the report is fed back to the LLM for up to **5** repair attempts (`generator_repair_attempts`), each attempt receiving the full validator report so it can fix every rule at once. A scenario that still fails is stored as `invalid` and never offered for play.
4. **TTS rendering** — every `radio` message and every `radio` challenge prompt is rendered to WAV in the sender's pinned voice ([`config/voices.json`](config/voices.json)), written to `audio/`, and its real `audio_duration` written back into the JSON. `system` output passes through the `pa_intercom` filter before being written.

   **A pause of `tts_sentence_gap_seconds` (default 1 s) is inserted between sentences.** Piper yields one audio chunk per sentence, so the gap uses its own segmentation rather than a guess at where sentences end. This is not cosmetic. A radio message has no transcript and is heard exactly once, so two instructions running into each other are not merely harder to follow — they are unintelligible, and the pause is what lets a listener separate *"H5 stays closed"* from *"until I clear it"*. It also gives the important clause somewhere to land.

   The gap lengthens every file, so the pre-TTS estimate of `read_cost` has to include it (§5.3): a radio message is costed as its text cost × 1.35 plus one gap per sentence break. An estimate that is too low passes validation and then fails step 5, after the audio has been rendered.
5. **Re-validation** — timing rules are re-checked with the real audio durations, since `read_cost` depends on them. This pass may not call the LLM; if it fails, the scenario is marked `invalid`.

   Before re-checking, a **reflow** settles the difference the estimate could not know. The pre-TTS cost of a spoken message is a prediction; when a file comes back a second longer than predicted, its own obligation now starts too early (V7). The reflow pushes that obligation later by exactly the shortfall. Padding every estimate to cover the worst case would cost real gameplay time on every message in the bank; correcting the handful that actually drift costs nothing.
6. **Publish** — the scenario appears in the bank and is selectable on the home page.

### 12.1.1 The model writes fiction; Python does the arithmetic

The single "LLM fill" of step 2 is, in the build, five smaller calls and a scheduler. This is the most consequential implementation decision in the generator and it exists because the first working version failed 63 validator rules, almost all of them arithmetic.

**Five stages instead of one call.** A 60-message scenario in one response is where models start dropping fields, and each stage needs different context:

| Stage | Produces | Why separate |
|---|---|---|
| 1 Plan | scenario name, six actor names, threads with grades, premises and door claims | Cheap, and everything downstream needs it |
| 2 Threads | the beats of one thread | Written in parallel, one call each. Each is told which doors the other threads claimed |
| 3 Everyday | the short one-off exchanges | Needs no thread detail, only what not to contradict |
| 4 Temptations | the conflicting requests | Cannot be written until every obligation exists, since it must pull against one from a *different* thread |
| 5 Challenges | six questions | Needs the finished timeline with real timestamps, because the answer must be derivable from what arrived *before* the question |

**No stage ever writes a timestamp.** Beats declare a phase and an order; the scheduler assigns every `at`. That is what makes the timing rules hold rather than be hoped for: V7's reading slack, V8's rolling density, V9's minimum gap, V10's window fit, V11's clearance around deadlines and V12's challenge spacing are all arithmetic, and arithmetic is not what a language model is for.

The scheduler also **guarantees solvability**. Threads are written in parallel and cannot know which doors the others took, so two threads demanding opposite states on one door at one moment is expected, not exceptional. Rather than reject the scenario, the scheduler settles each collision in a fixed order of preference: truncate the earlier obligation (the later instruction supersedes it, which is what the fiction implies anyway), else push the later one clear, else drop whichever carries less content. V13 and V14 are therefore structural rather than aspirational.

Three more things are structural for the same reason:

- **The end-of-shift seal** (V21) is appended and pinned so its window closes last. Asking for it politely produced a scenario that ended with a hangar door open to space.
- **A hold is capped** at 30 % of the session. Models write 60-minute holds into 27-minute shifts.
- **Retraction shape** is normalised: a `resolution` carrying `cancels` is relabelled a retraction, a missing `retraction_style` is inferred, an unresolvable withdrawal has the door named in it, and anything over the quota is demoted. Every one of those is a labelling question with one right answer, so none of them is worth a call.

**What is left for the model to fix.** After the deterministic pass, the repair loop sends back only prose: an invented place, a withdrawal that cannot be resolved, a distractor drawn from nowhere. One item at a time, with the validator's own words attached. That is a far smaller and more reliable request than "here are 60 errors, try again".

### 12.2 Generation is triggered manually

A **Generate scenario** button on the admin page starts a generation job with a small form (duration, thread count, finale thread choice or "random", optional theme hint, optional seed). Progress is streamed. Nothing about generation happens during a play session.

### 12.3 Requirements to state explicitly in the generation prompt

- All times are **integer seconds from session start**.
- **The player needs time to consume messages.** Every task's `at` must leave room for its message's `read_cost` plus 10 s of slack, and the rolling density caps in §13 must hold. Messages the player has not had time to read cannot carry obligations.
- Prefer **one `hold` window** over a chain of instantaneous samples whenever the obligation is "keep it like this for a while".
- Never instruct an action that is already satisfied.
- Every isolation obligation must have a **releasing message** in its thread — or must deliberately have none (the reactor-maintenance pattern), in which case the thread must be the subject of a challenge.
- At least one thread must be **silent for ≥ 4 minutes while still holding a live obligation**, and must be the subject of a challenge.
- Distractors must be **true-sounding and false**, drawn from other threads in this scenario.
- **Door states at session start are fixed** (§3.4) and must be reasoned from: open D5, D4, D7, D12; everything else closed. An "open it" instruction for a door that is already open is invalid.
- Include **2–3 retractions** (§6.7), none in phase 1. They may fall on any actors or threads. Each must have teeth: a later opposite-state task on the freed door, or a challenge that depends on it.
- A retraction's text must be resolvable. If the retracting actor holds more than one live obligation, the text has to pin down which one — by door, place, subject, or timing.
- Use **indirect obligations** (§6.8) for isolation instructions: name the place, not the doors, and set `derived_from`. Only the 17 targets listed in `station.json` may be named, never one of the four areas that cannot be sealed alone, and `require` must carry the cut only — never the volume's interior doors.
- Every challenge needs a **pretext** (§8.4): a reason the asker needs the answer. Prefer an asker from a *different* thread than the one being asked about.
- The station map is fixed; only rooms, corridors, hangars and door ids present in `station/station.json` may be named.
- English only.

---

## 13. Scenario validator

Every scenario must pass all 38 rules before it can be played. The report is written to `validation.json` and shown on the admin page.

### 13.1 Structural

| # | Rule |
|---|---|
| V1 | All ids unique; every `thread_id`, `actor_id`, `group_id`, `message_id` reference resolves. |
| V2 | Every `at` is an integer in `[0, duration_seconds]`. Messages sorted ascending by `at`. |
| V3 | Every task has a `group_id` and a `message_id`; the group's thread matches the message's thread; `message.at < task.at`. |
| V4 | Every door named in `require` ∈ {D1…D13, H1…H5}; every state ∈ {open, closed}. |
| V5 | Every `radio` message has an existing audio file, and `audio_duration` matches the file within ±0.3 s. |
| V6 | Exactly 6 actors, one per type; each type used at most once. |

### 13.2 Timing

| # | Rule |
|---|---|
| V7 | For each message, `min(task.at) ≥ message.at + read_cost(message) + task_slack_after_message_seconds`. |
| V8 | Rolling `read_budget_window_seconds` sum of `read_cost` ≤ `read_budget_phase1` in phase 1, `_mid` in phases 2–4, `_finale` in phase 5. |
| V9 | Consecutive messages are ≥ `min_message_gap_seconds` apart. |
| V10 | `task.at + task.hold ≤ duration_seconds`. |
| V11 | No **in-session** challenge is within `challenge_task_clearance_seconds` of any task boundary (`at` or `at + hold`), so a question never lands on a deadline. Debrief challenges are exempt — the session is over and no task can fail. |
| V12 | Exactly 3 in-session challenges, all with `at ≥ 0.5 × duration_seconds`, spaced ≥ 120 s apart. Exactly 3 debrief challenges. |

### 13.3 Solvability — the perfect-player simulation

| # | Rule |
|---|---|
| V13 | **No contradictory overlap.** For every pair of tasks whose windows `[at, at+hold]` intersect and that name the same door, the required states must be identical. |
| V14 | **Perfect-player trace.** Simulate a player who, from the fixed station start state (§3.4), performs the minimum set of toggles that satisfies every task at the latest safe moment. Tasks cancelled by a retraction (§6.7) are excluded from the simulation entirely. Every task must PASS. A scenario that the perfect player cannot complete is unsolvable and rejected. The resulting expected-state trace is stored in `validation.json` and rendered on the admin page. |
| V15 | **No already-satisfied instruction.** If, in the perfect-player trace, the door state required by a `hold: 0` task already holds at `task.at` and has not changed since the task's message was emitted, the task is a silent free pass → reject. Tasks with `hold > 0` are exempt: holding an already-correct state against temptation is a genuine obligation. |
| V16 | **No redundant re-requirement.** If a task requires door X to be `s`, and an earlier task in the same group already established X = `s` with no intervening task requiring the opposite, the later task is redundant → reject. *Exception:* a task scheduled in the future may legitimately restate a state that a *different, earlier and already-closed* obligation happened to leave in place — e.g. "open D3 now, close it afterwards" alongside "have D3 open again in 5 minutes" is valid, because an intervening close occurred. |
| V17 | **Temptations must tempt.** Every message with `kind: "tempting_request"` must have no tasks, and must name a door that is under a contradictory active `hold` at the message's `at`. |
| V18 | **Dormancy.** At least one thread has a gap ≥ 240 s between consecutive messages while holding a live obligation, and is the subject of at least one challenge. |
| V19 | **Challenge integrity.** Exactly one option is `correct: true`. The correct option is derivable solely from messages delivered before `challenge.at`. Every distractor references a real thread, actor or door in this scenario, and is false at `challenge.at`. No two options are semantically equivalent. |
| V20 | **Volumes.** 55 ≤ messages ≤ 75; threads ≥ 4; exactly one thread with `grade: "finale"`; 12 ≤ everyday exchanges ≤ 18. |
| V21 | **Safe final configuration.** The last task group requires all five hangar doors closed, so the session ends with the station sealed. |
| V22 | **Reachability.** Every thread has ≥ 1 message in its declared `phase_span`, and no thread's messages fall outside it. |

### 13.4 Derived obligations

| # | Rule |
|---|---|
| V23 | **Derived tasks match the graph.** For any task with `derived_from`, recompute the cut-set of the named isolation target from `station.json`'s door graph. `require` must equal that cut-set exactly, plus the target's `hangar_doors_inside` when `include_hangar_doors` is true, and nothing else. |
| V24 | **Isolation targets exist and are possible.** The named target is present in `station.json.isolation_targets`. Instructions to isolate any area in `station.json.not_isolable` are rejected. |
| V25 | **Place names are real.** Any place named in the prose of an indirect instruction resolves to an area or isolation-target phrase in `station.json`. |

### 13.5 Retractions

| # | Rule |
|---|---|
| V26 | **Target exists and is live.** Every id in `cancels` resolves, and names an obligation with at least one task still pending at `message.at`. Cancelling something already finished or already cancelled is a no-op → reject. |
| V27 | **The text must be resolvable.** No structural constraint on how many obligations an actor holds — but when the retracting actor has more than one live obligation, the message text must pin down *which* one, by naming the door, the place, the thread's subject, or when it was given. "Forget what I told you" is legal only when it can actually be resolved from the text plus what the player has heard. |
| V28 | **`cross_actor` must name the other actor.** The cancelled obligation was created by a *different* actor, and that actor is named in the message text. |
| V29 | **Retractions must have teeth (§6.7.2).** Each one is followed either by a later task requiring the opposite state on a door it freed, or by a challenge whose correct answer depends on it. At least half of a scenario's retractions use the task form. |
| V30 | **Quotas.** 2–3 retractions per scenario. None in phase 1. No constraint on how they distribute across actors or threads. |
| V31 | **No immediate re-imposition.** The same obligation is not re-created on the same door by the same actor within 90 s of being retracted. |

### 13.6 Station consistency

| # | Rule |
|---|---|
| V32 | Every door and area named in any message text exists in `station/station.json`. No invented rooms, corridors or door ids. |
| V33 | The scenario's `station_version` matches `station.json`'s `version`. |
| V34 | The scenario records the `config/difficulty.json` values it was validated against; the admin page flags a mismatch with the running config. |

### 13.7 Plain English

| # | Rule |
|---|---|
| V35 | **No idioms, no slang, no jokes, and no sentence long enough that holding it is the hard part.** Errors on a curated list of figures of speech and slang, and on any sentence over 30 words. Warns on spoken sentences over 20 words. |

Most players will not be native English speakers, and a `radio` message is heard exactly once with no transcript and no replay. That makes reading difficulty a **confound, not a style preference**: a player who fails because they could not decode *"buy me some time"* in one hearing has been measured on their English, not on their memory — which is the one thing the instrument exists to measure.

### 13.8 Player-facing integrity

| # | Rule |
|---|---|
| V36 | **A message is never a question.** No `Message.text` may contain `?`. Only a `challenge` has a reply interface; a plain message that poses a question dead-ends, since there is no way for the player to answer it. |
| V37 | **No internal id reaches the player.** `m_012`, `t_045`, `og_ext_vent` and similar bookkeeping ids must never appear in a message, a `fail_message`, or a challenge's `prompt`, `explanation` or option text. The player has never seen an id; a challenge's `explanation` in particular is written last, with the annotated timeline in view, and it is easy to cite a record instead of describing what happened. |
| V38 | **Time answers are in minutes, never hours.** For a `kind: "time"` challenge, the prompt, the explanation, and the *correct* option may not name hours: the whole shift is under half an hour and no single hold may exceed 30% of it (§12.1.1), so an hour-scale correct answer cannot be what actually happened. A wrong option may name hours on purpose, as an implausible order-of-magnitude distractor (V19) — only the right answer is checked. |

Each of these was found by playtesting rather than by design review: a chatter message phrased as a question the player had no way to answer, a challenge explanation that cited `m_032` as its justification, and a "how long was it sealed" question whose correct answer was given in hours despite the shift lasting well under thirty minutes.

The rule is enforced rather than merely requested because models drift toward colour. The first passing scenario contained *"vent starts in two mikes"* — military slang for minutes, invisible to a native speaker and opaque to everyone else. V35 is in the set of rules the repair loop sends back for rewriting, so the fix costs one call.

Standard radio procedure words are **not** slang and are deliberately not on the list. *"Copy"*, *"stand by"*, *"say again"* are consistent, learnable and part of what makes the fiction work. What is banned is figurative language, invented jargon, and humour.

Speech rendering serves the same goal from the other side (§12.1 step 4): a pause between sentences, and door names spoken separately and slower, because the door name is at once the most important word in the instruction and the shortest.

---

## 14. Application architecture

### 14.1 Stack

- **Backend:** Python 3.12 + FastAPI. WebSockets for the live session. Server-authoritative clock and game loop.
- **LLM:** LiteLLM, provider-agnostic, generation-time only.
- **TTS:** **Piper**, local and offline, generation-time only. Six pinned voice models, one per actor type — see [`config/voices.json`](config/voices.json) and §11.2. Rendered at generation time into the scenario folder, with the `system` voice passed through an intercom filter. Wrapped behind a small `TextToSpeech` interface so a cloud provider can be swapped in later without touching the pipeline.
- **Frontend:** plain ES modules, no framework and no build step. Station rendered on an HTML `<canvas>` with hit-testing for door clicks, by the same [`station/render.js`](station/render.js) the dev preview and the printed handbook use. **This is a deliberate change from the Angular plan** — see §14.7.
- **Storage:** flat files, no database server.
- **Packaging:** one Dockerfile plus a `docker-compose.yml`; README with local and Docker instructions.

### 14.2 Storage layout

```
.env                    gitignored: the LLM key. Generation-time only.
Makefile                venv, test, serve, generate, station, sheets, voices
docker-compose.yml      one service: `app` plays and generates
docker/
  Dockerfile.app        LiteLLM, Piper, ffmpeg, the six pinned voices
config/
  difficulty.json       every value that shapes pressure
  voices.json           pinned Piper voice per actor type — append-only
assets/
  portraits/*.png       512x512, one per actor type
  make_placeholder_portraits.py
  download_voices.py    fetches the six pinned voice models
  voices/*.onnx         gitignored: ~500 MB of Piper models
station/
  station.json          authoritative layout, read by backend and frontend
  render.js             canvas renderer, shared by preview, handbook and game
  preview.template.html
  preview.html          generated by build_preview.py
  build_preview.py
  format_station.py     keeps station.json compact and hand-editable
  build_sector_sheets.py
  sector-sheets.html    generated: printable sector handbook
  sectors/*.png         generated with --png: one image per sector
backend/
  requirements.txt      runtime only — no LiteLLM, no Piper
  requirements-generate.txt
  opstation/
    paths.py            one place that knows the layout; OPSTATION_DATA_DIR
    station.py          the door graph and every isolation cut-set
    config.py           difficulty tunables and pinned voices
    models.py           the scenario schema
    engine.py           the session runtime — pure, clock-injected
    session.py          asyncio clock, WebSocket fan-out, persistence
    bank.py             the scenario bank and what makes an entry playable
    app.py              FastAPI: REST, WebSocket, admin
    validator/
      __init__.py       runs all 38 rules, builds the report
      rules.py          one function per rule, v01 .. v38
      simulate.py       the perfect-player simulation
      findings.py       the report, including the form the LLM repairs from
    generate/
      brief.py          the station and rules brief, generated from the JSON
      prompt.py         the five stage prompts and the repair prompt
      plan.py           the intermediate form between the LLM and a scenario
      schedule.py       every timestamp, and the solvability guarantee
      assemble.py       plan + schedule -> scenario.json
      repair.py         deterministic fixes
      pipeline.py       the whole run, including the repair loop
      tts.py            Piper, the intercom filter, and the TextToSpeech seam
  tests/                station, engine, validator, scheduler, API
frontend/
  index.html            the shell; loads render.js as a classic script
  style.css
  app.js                router, and the audio priming that Start shift performs
  lib/{api,station,modal}.js
  pages/{home,game,summary,admin}.js
data/                   OPSTATION_DATA_DIR; gitignored
  scenarios/
    index.json
    <scenario_id>/
      scenario.json
      validation.json
      generation.log
      audio/*.wav
  sessions/
    index.json
    <session_id>.json
```

`station/station.json` is served to the frontend and loaded by the backend, so both sides agree on the layout and on the fixed start state without duplicating it.

One JSON per session, written atomically (temp file + rename). Persisted on every state-changing event. **Sessions do not need to survive a backend restart** — an interrupted session is simply marked `aborted`.

### 14.3 Session runtime

- One `asyncio` task per session, ticking at **250 ms**.
- Each tick: deliver due messages/challenges, evaluate live task windows, emit failures, push state to the client.
- Multiple sessions run concurrently in one app instance, each with its own `session_id`.
- **Browser refresh resumes** the session: the client reconnects to the WebSocket and receives a full state snapshot. Elapsed time keeps running while the browser is away — the world does not wait.
- On reconnect, the queue is restored as it was. An open-but-unacknowledged modal returns as unopened, at the front of the queue.

### 14.4 API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/station` | The layout, served from the same `station.json` the backend loads |
| GET | `/api/config` | The tunables the client's own behaviour depends on, plus the UI-supplied "I don't know" option |
| GET | `/api/scenarios` | Bank listing: id, name, duration, thread count, validity, whether its audio exists |
| GET | `/api/scenarios/{id}/audio/{file}` | A pre-rendered radio message |
| POST | `/api/sessions` | `{participant_name, scenario_id}` → `{session_id}` |
| GET | `/api/sessions/{id}` | State snapshot |
| GET | `/api/sessions/{id}/summary` | The debrief breakdown of §9.2 |
| WS | `/ws/sessions/{id}` | Live session |
| GET | `/api/admin/status` | App health, bank inventory, validator summary, active sessions |
| GET | `/api/admin/sessions` | Session history |
| GET | `/api/admin/sessions/{id}` | Full session detail |
| DELETE | `/api/admin/sessions/{id}` | Remove a session |
| GET | `/api/admin/scenarios/{id}` | Full scenario + validation report + perfect-player trace |
| POST | `/api/admin/scenarios/generate` | Start a generation job |
| GET | `/api/admin/jobs/{id}` | Generation job progress |

No authentication anywhere.

**WebSocket — server → client:** `snapshot` on connect, then `state` on every change — clock, score, door states, pending count, and the front of the queue. Plus `opened`, `answered` and `shake` in reply to a client action.

The `state` payload is deliberately one shape rather than a family of typed events. The player is not told who is calling or how urgent it is before opening a notification (§5.2), so a queued item must reveal nothing but its existence — and the simplest way to guarantee that is for one function to decide what is publishable and for the socket to carry only its output. A `message` event carrying a sender would be a leak waiting to happen.

**WebSocket — client → server:** `toggle_door {door}`, `open_notification`, `acknowledge {id}`, `answer_challenge {challenge_id, option_id}`.

### 14.5 Pages

| Page | Contents |
|---|---|
| **Home** `/` | Participant name field, scenario picker from the bank, **Start shift** — and the **live station canvas**, fully operable with no clock running. See §14.6. |
| **Game** `/game/:id` | Station canvas, notification button with pending count, penalty total, station clock, elapsed timer. Nothing else. |
| **Summary** `/summary/:id` | The debrief breakdown from §9.1. |
| **Admin** `/admin` | App status, bank inventory with validity, session history, **Generate scenario**. |
| **Admin — session** `/admin/sessions/:id` | Full replay data: actors, threads, every message with delivery/open/ack timestamps, task results, door-state timeline vs. expected trace, challenges and answers, penalties, elapsed time. Delete button. |
| **Admin — scenario** `/admin/scenarios/:id` | Scenario JSON, validation report, perfect-player trace, radio transcripts, audio playback, a per-thread panel (story summary plus every message belonging to it), a thread-coloured message timeline, a message-density chart in 4-minute buckets, and a per-door chart of every window a real obligation requires it open or closed — which makes a genuine scheduler contradiction (two live obligations disagreeing on one door) visible at a glance, and distinguishes it from a conflicting request (§6.5), which shows no obligation bar at all because it has no task behind it. |

The admin pages exist to debug and tune generation; they are the only place ground truth is visible.

### 14.6 The home page shows the station

The home page carries the same station canvas the game uses, in the same component, **fully operable**. The player can click doors open and closed as much as they like. Nothing is being timed and nothing is being scored.

This exists because the first minutes of a session are the worst possible place to learn an interface. Once **Start shift** is pressed the clock runs and never stops again, so any fumbling with the controls contaminates the very thing being measured. Phase 1 already ramps the workload gently, but it cannot teach where D9 is.

What the home canvas is for:

- learning that a door is toggled by clicking it, and what open and closed look like;
- learning the layout — where the corridors run, which bay is which, where each `Dn` sits;
- finding the two permanent openings and discovering that the Observation Deck and Storage have no door of their own;
- working through the printed sector cards (§3.6) against the live map.

Rules for it:

- **No clock, no score, no messages.** Nothing here is recorded against the participant.
- **Door states reset** to the fixed start state (§3.4) when **Start shift** is pressed, whatever the player left them in. The session always begins from the same configuration.
- **No sector highlighting and no isolation-target list.** Those belong to the printed handbook and to the admin preview. Putting an interactive sector lookup here would hand the player a tool during the session's own setup and blur what the printed reference is for.
- It doubles as a **liveness check**: if the canvas renders and doors respond, the station component and the WebSocket are working before a participant is committed to a session.

Pressing **Start shift** also primes the audio context (§5.1), so the home page is the natural place for the audio check too — it is the last moment at which a failure is free.

### 14.7 Why the frontend has no framework

The plan said Angular. The build is plain ES modules instead, and the reasoning is worth recording because it is a reversible decision that someone will want to revisit.

Three things pushed it:

- **The renderer was already framework-free.** [`station/render.js`](station/render.js) is the load-bearing part of the UI, and it is shared with the dev preview and the printed sector handbook (§3.6). Under Angular it would have been wrapped in a component that adds nothing; the wrapper would be the only Angular-shaped thing about it.
- **The app is four pages and one socket.** Home, game, summary, admin. There is no form validation, no client-side state machine, no data layer worth the name — the server is authoritative about time, delivery, failure and score, and the client renders what it is told.
- **A research instrument has to be runnable.** `make serve` starts it. Adding a Node toolchain, a package lock and a build step between a researcher and a session is a real cost against no benefit at this size.

What this costs: no component tests, no typed templates, and if the UI grows a genuine client-side model — an operator's notepad, a live thread view, anything with state of its own — this decision should be revisited rather than worked around. The API and the WebSocket protocol are unchanged either way, so a rewrite of the frontend is a rewrite of the frontend and nothing else.

---

## 15. Visual design

Not a game. A **plain, unglamorous industrial control console**.

- Dark theme, near-black background, muted panel greys, thin 1 px rules.
- Monospace throughout (e.g. IBM Plex Mono / JetBrains Mono), small sizes, uppercase labels.
- Minimal colour, used only as state: **open = green**, **closed = red**, **alert = amber**. Nothing decorative.
- **No animations** in this version — not even door transitions. A door changes state instantly on the canvas.
- No people, no ships, no movement anywhere.
- Station drawn as flat rectangles and lines: rooms as outlined boxes with a label, corridors as connecting boxes, doors as short thick bars on the wall between two areas, hangar doors as bars on the station's outer edge. Door labels (D1…D12, H1…H5) always visible.
- Clicking a door bar toggles it. Hover shows the door label and its current state, nothing more.
- Message modal: sender portrait left, sender name and channel above, body right, single **ACKNOWLEDGE** button. Radio messages show a waveform in place of the body text. Shakes if dismissed any other way.

---

## 16. Deliberately out of scope

Recorded so they are not re-litigated:

- The Keeper application itself, and the with/without-Keeper experimental conditions.
- Paired-scenario cognitive-equivalence machinery.
- Message history, replay, "repeat that" — permanently excluded, this is the core manipulation.
- Priority hierarchies and authority ranking between actors — including any priority between failure notices and messages. The queue is strict FIFO.
- Locked or unavailable doors; scenario-driven door disabling.
- Any door state other than open and closed.
- Animation, movement simulation, pathfinding, pressure physics.
- Research data export (CSV/JSON); the admin page is the only view.
- Any transcript or fallback for radio messages — audio failure voids the session.
- Surviving a backend restart mid-session.
- Authentication.
- Any language other than English.
- Any LLM or TTS call at runtime.

---

## Open questions

Nothing is blocking. Two things to look at, and one flagged risk.

**Q-A — Station map v4.** [`station/preview.html`](station/preview.html) — open it and click through the **isolation targets** list at the bottom of the panel; each row applies that target's cut-set to the map, which is the fastest way to sanity-check all 17. What changed this round: every hangar bay now has an internal door as well as an outer one (D13 added for Hangar Bay 5), Hangar Bay 3 links C2 and C3 (D9), Engineering shares a wall with Hangar Bay 4 (D11), and Security overhangs the corridor line to the left.

Doors were renumbered spatially in v4: top to bottom in horizontal bands, then left to right within a band (§3.1).

**Q-B — Portrait placeholders.** Six exist at `assets/portraits/*.png`, 512×512: silhouettes with a role-tinted background and an accent collar, `system` drawn as a speaker grille rather than a person. Good enough to build against — worth confirming the framing and size before real artwork.

**Q-C — Risk worth naming: the Hangar Bay 3 bypass may be too punishing.** Sealing the service sector now needs D7 **and** D9. That is a genuinely good trap — the plausible answer is one door short — but it fires on *every* service-sector isolation, so a player who never spots it fails all of them for the same reason. That measures one missed fact repeatedly rather than measuring memory. Options: leave it and let the debrief expose it, teach it explicitly in an early thread, or cap how many derived tasks per session depend on D9. I lean toward **teaching it once in phase 2** — an actor mentions taking the Hangar Bay 3 shortcut — so that afterwards it is a memory test rather than a knowledge gap.
