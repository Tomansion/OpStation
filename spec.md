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

**6 rooms**, **3 corridors**, **5 hangar bays**, **10 internal doors (D1–D10)**, **5 hangar doors (H1–H5)**.

### 3.1 Schematic (v1)

Areas on the left, the three corridors on the right. `--Dn--` is an operable door; `..open..` is a permanent doorless passage.

```
              space --H1 > | HANGAR BAY 1   shuttle dock   |--D1  --|
              space --H2 > | HANGAR BAY 2   visiting berth |--D2  --|
                           | MEDICAL BAY                   |--D3  --+-- C1  NORTH CORRIDOR
                           | LIVING QUARTERS               |--D4  --|
                           |   '- OBSERVATION DECK              (no door -- reached through LIVING QUARTERS)
                                                                    |
                                                                    D5
                                                                    |
                           | SECURITY                      |--D6  --|
              space --H3 > | HANGAR BAY 3   security EVA   |--D7  --+-- C2  CENTRAL JUNCTION
                                                                    |
                                                                    D8
                                                                    |
                           | ENGINEERING / REACTOR         |--D9  --|
              space --H4 > | HANGAR BAY 4   cargo          |--D10 --|
                           | STORAGE                       |..open..+-- C3  SERVICE CORRIDOR
  Extension Epsilon --H5 > | HANGAR BAY 5   construction   |..open..|
```

### 3.1.1 Canvas layout grid

Coordinates for the renderer, on a 12 x 16 cell grid (cell = 64 px, canvas 768 x 1024, scaled to fit). Corridors are wide horizontal bars; rooms and hangar bays are boxes; doors are drawn as thick bars centred on the shared edge.

| Area | Cells (col, row) - (col, row) |
|---|---|
| Hangar Bay 1 | (2,1) - (4,2) |
| Hangar Bay 2 | (7,1) - (9,2) |
| Medical Bay | (0,4) - (2,5) |
| C1 North Corridor | (3,3) - (9,4) |
| Living Quarters | (10,4) - (11,5) |
| Observation Deck | (10,6) - (11,7) |
| Security | (0,8) - (2,9) |
| C2 Central Junction | (3,7) - (8,8) |
| Hangar Bay 3 | (9,7) - (11,8) |
| Engineering / Reactor | (0,12) - (2,13) |
| C3 Service Corridor | (3,11) - (8,12) |
| Storage | (9,11) - (11,12) |
| Hangar Bay 4 | (3,14) - (5,15) |
| Hangar Bay 5 | (6,14) - (8,15) |

Hangar doors H1-H5 are drawn on the outward-facing edge of their bay, with a hatched "space" margin beyond. H5's margin is labelled *Extension Epsilon*.

Door hit-boxes are the door bar inflated by 8 px on every side, so they remain clickable at small canvas scales.

### 3.2 Door table

| Door | Connects | Type | Normal state |
|---|---|---|---|
| D1 | Hangar Bay 1 ↔ C1 North Corridor | internal | open |
| D2 | Hangar Bay 2 ↔ C1 North Corridor | internal | open |
| D3 | Medical Bay ↔ C1 North Corridor | internal | open |
| D4 | Living Quarters ↔ C1 North Corridor | internal | open |
| D5 | C1 North Corridor ↔ C2 Central Junction | internal | open |
| D6 | Security ↔ C2 Central Junction | internal | open |
| D7 | Hangar Bay 3 ↔ C2 Central Junction | internal | open |
| D8 | C2 Central Junction ↔ C3 Service Corridor | internal | open |
| D9 | Engineering / Reactor ↔ C3 Service Corridor | internal | open |
| D10 | Hangar Bay 4 ↔ C3 Service Corridor | internal | open |
| H1 | Hangar Bay 1 ↔ space | hangar | closed |
| H2 | Hangar Bay 2 ↔ space | hangar | closed |
| H3 | Hangar Bay 3 ↔ space | hangar | closed |
| H4 | Hangar Bay 4 ↔ space | hangar | closed |
| H5 | Hangar Bay 5 ↔ space / Extension Epsilon | hangar | closed |

**Doorless passages** (always traversable, cannot be operated): Observation Deck ↔ Living Quarters; Storage ↔ C3; Hangar Bay 5 ↔ C3.

Hangar Bay 5 having no internal door is deliberate: **H5 is the only barrier between the construction extension and the interior**, which makes it a natural focus for isolation obligations.

### 3.3 Hangar roles

Fixed roles give the generator a consistent vocabulary:

| Hangar | Role |
|---|---|
| H1 | Passenger and medical shuttle dock |
| H2 | Visiting-vessel berth (inspections, damaged ships) |
| H3 | Security EVA airlock |
| H4 | Cargo hangar (adjacent to Storage via C3) |
| H5 | Construction hangar → Extension Epsilon |

### 3.4 Initial door states

Default: all internal doors **open**, all hangar doors **closed**. A scenario may override this via `initial_door_states`, but the validator requires the override to be reachable and sensible.

All 15 doors are always visible to the player, whether or not the current scenario uses them. A scenario may use any subset. Two different scenarios may use the same door for entirely different obligations.

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
| `text` | Written text in the modal. No audio. |
| `radio` | **Audio only** — pre-rendered TTS in the sender's voice, with a simple waveform animation. No transcript is shown. |

Radio messages carry more memory load than text, which is the point. Transcripts of radio messages exist in the scenario JSON and are visible on the admin page only.

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
  "require": { "D8": "closed", "H5": "closed" },
  "fail_message": "WARNING — pressure loss near Extension Epsilon. D8 was opened during depressurisation."
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

**Hole 1 — sampling is blind between checkpoints.** A player who opens D3 at t=119, closes it at t=121, and reopens at t=149 passes both open-checks while the crew was locked out for 28 of the 30 seconds. Worse case: an obligation like *"keep D8 closed for 12 minutes"* can only be expressed as instantaneous samples, so the player can open D8 freely between samples with no consequence — which destroys exactly the gameplay the game exists to test (the tempting request the player must refuse).

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

---

## 7. Failure notices

A failed task produces a **failure notice**: a short, in-fiction consequence message from the affected actor or from `system`.

- Failure notices enter the same notification queue as messages, but at **lower priority**: they are only presented when no unopened message is waiting.
- They are `text` channel, no audio — they must be readable instantly.
- They are visually distinct (alert styling).
- They require acknowledgement like any other modal.
- At most **one failure notice per task group per 30 seconds** is presented; further ones are dropped from the queue (the penalty is still recorded).

The lower priority and the cap exist to prevent a failure cascade from burying the messages the player needs to recover.

---

## 8. Keeper challenges

Challenges test whether the player still holds the thread history. They are disguised as ordinary station traffic — a person asking a question, not a quiz.

> **Security:** Door Control, why is D8 still closed?

### 8.1 Format

- **4 authored options + a fixed 5th option, "I don't know."**
- Exactly one authored option is correct.
- Delivered through the normal notification queue, as `text` or `radio`.
- **Answering is mandatory and blocking:** the modal cannot be dismissed until an option is chosen, and **door controls are inoperable while it is open**.
- **No time limit** — but the world keeps running, and tasks keep being evaluated. Stalling costs.
- After answering, the correct answer and a one-line explanation are shown, then acknowledged away.
- A wrong answer costs one penalty. "I don't know" is logged separately (see [Open questions](#open-questions) Q-A).

### 8.2 Placement

- **3 in-session**, the first no earlier than the 50 % mark, biased toward threads that have been **dormant ≥ 3 minutes**.
- **3 in the debrief**, after the session ends, covering the whole shift including threads that have not been heard from in 10+ minutes.
- Times are written into the scenario; the generator chooses them.
- Validator rule V10 keeps every challenge at least 20 s clear of any task boundary, since the modal blocks door operation.

### 8.3 Challenge kinds

Each challenge declares a `kind`. Aim for one of each per group of three.

| Kind | Tests | Examples |
|---|---|---|
| `thread` | Connecting information belonging to one event | *Why is D8 currently closed? / Is the construction incident finished? / Which door is associated with Technician Ruiz?* |
| `time` | Chronology and pending intentions | *Which restriction expires first? / How long has D9 been closed? / What were you asked to do after the coolant test?* |
| `provenance` | Source and evolution of information | *Who authorised D6 to reopen? / Who contradicted the asteroid report? / Medical said D3 could reopen — is that still valid?* |

### 8.4 Distractor rules

Distractors must be drawn from **other real threads in this same scenario** — real reasons, real actors, real doors — and must be false at the moment the question is asked. Generic filler ("routine maintenance") is not acceptable. See validator V19.

---

## 9. Scoring

One single scale: **penalty points**, all of equal weight. No weighting, no tolerance windows, no partial credit.

| Event | Cost |
|---|---|
| Task failed | 1 penalty |
| Challenge answered wrongly | 1 penalty |
| Challenge answered "I don't know" | see [Open questions](#open-questions) Q-A |

During play the player sees only the **running total**. Nothing else — no breakdown, no list, no indication of which thread a penalty came from.

### 9.1 Debrief and summary page

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
| Construction of Extension Epsilon | Long `hold` on H5 (and D8) while the extension is depressurised; two delays; tempting civilian requests; release after pressure test; possible reopening. |
| Damaged transport vessel | H2 opened for emergency docking, then held closed pending inspection; the crew requests departure before Security clears them; contradictory damage reports (provenance). |
| Pressure leak | D8 and D9 closed to isolate; a resident is trapped inside; a narrow authorised opening of one door only; the two doors are released at different times. |
| Missing technician | D10 opened for a named technician; thread goes silent; radio contact lost; search party; technician resurfaces 10 min later. Pure delayed recall. |
| Medical quarantine | H1 then D3 held closed; an initial "negative test, reopen in 5 min" that is then **retracted**; second test clears it. Pure superseding-information test. |
| Reactor maintenance | D9 closed with a stated duration but **no automatic release message**; a third party asks to use it; the player must know Engineering never confirmed. |
| Contamination containment | Storage/C3 isolation via D8 and D10; escalating scope. |
| VIP inspection | Command-imposed route restrictions that shift as the inspection party moves. |

**Finale-grade threads** (exactly one per scenario, occupying phase 5)

| Thread | Shape |
|---|---|
| Invaders attack the station | Patrol finds an abandoned ship → weapons damage → recall all teams → lockdown countdown while teams are still outside → seal hangars → a hangar forced open → retreat routes opened and closed under time pressure → dormant threads reopen → "sector secure" that does **not** release all obligations → lockdown lifted. |
| Catastrophic hull breach | Progressive sectional isolation, evacuation corridors, revised isolation boundaries. |
| Reactor emergency | Escalating engineering isolation, forced venting windows, personnel extraction. |
| Station-wide contamination | Rolling quarantine boundaries that move room by room. |

The invasion must **not** always be the finale.

### 10.2 Everyday exchanges

12–18 short self-contained exchanges provide background load: a resident wanting D4, a cargo transfer through D10, a maintenance inspection, a shuttle docking at H1, a brief environmental hold. They are 1–2 messages with 1–3 tasks and no dormancy.

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

  "initial_door_states": {
    "D1": "open",  "D2": "open",  "D3": "open",  "D4": "open",  "D5": "open",
    "D6": "open",  "D7": "open",  "D8": "open",  "D9": "open",  "D10": "open",
    "H1": "closed","H2": "closed","H3": "closed","H4": "closed","H5": "closed"
  },

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
    }
  ],

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
- `message.kind` ∈ `instruction | update | supersede | status | tempting_request | resolution | reopen | chatter`.
- `at` is always **seconds from session start**, integer.
- Every message with a `task_group_id` is the message that *creates or updates* that obligation.

### 11.2 Actors

Exactly **6 actor types**, fixed forever, each with one portrait and one TTS voice:

| Type | Voice | Portrait | Role |
|---|---|---|---|
| `security` | voice_security | assets/portraits/security.png | Patrols, EVA, inspections, lockdowns |
| `construction` | voice_construction | assets/portraits/construction.png | Extension work, exterior operations |
| `cargo` | voice_cargo | assets/portraits/cargo.png | Transfers, storage, low-priority traffic |
| `medical` | voice_medical | assets/portraits/medical.png | Patient transport, quarantine |
| `civilian` | voice_civilian | assets/portraits/civilian.png | Residents, researchers, routine requests |
| `system` | voice_system | assets/portraits/system.png | Automated alerts, alarms, failure notices |

Rules:

- Each scenario instantiates **one named individual per type**, and that individual is the same person for the entire scenario. Names and personalities change between scenarios.
- A voice is never shared between two people. Since there is one person per type, the voice unambiguously identifies the speaker — which is what makes provenance questions answerable.
- Messages may be *about* a group ("two workers are still outside near H5"), and an actor may reference a group, but a group never speaks.

---

## 12. Scenario generation

Scenarios are **generated offline into a bank** and played deterministically at runtime. **The runtime never calls an LLM or a TTS engine.**

### 12.1 Pipeline

1. **Template selection** — a hand-authored JSON template fixes the structure: `duration_seconds`, phase boundaries, thread count and grades, how many tempting requests, how many superseding updates, dormancy requirements, challenge slots and kinds, volume targets.
2. **LLM fill** — the LLM receives the station map, the actor roster, the task/`hold` semantics, the template, and the timing rules. It produces `scenario.json`: actor names, thread instantiations, message prose, timings, tasks, `fail_message` texts, challenges with distractors and explanations.
3. **Validation** — the validator (§13) runs. On failure the report is fed back to the LLM for up to **3** repair attempts. A scenario that still fails is stored as `invalid` and never offered for play.
4. **TTS rendering** — every `radio` message and every `radio` challenge prompt is rendered to WAV in the sender's voice, written to `audio/`, and its real `audio_duration` written back into the JSON.
5. **Re-validation** — timing rules are re-checked with the real audio durations, since `read_cost` depends on them. This pass may not call the LLM; if it fails, the scenario is marked `invalid`.
6. **Publish** — the scenario appears in the bank and is selectable on the home page.

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
- The station map is fixed; only real rooms, corridors, hangars and doors may be named.
- English only.

---

## 13. Scenario validator

Every scenario must pass all rules before it can be played. The report is written to `validation.json` and shown on the admin page.

### 13.1 Structural

| # | Rule |
|---|---|
| V1 | All ids unique; every `thread_id`, `actor_id`, `group_id`, `message_id` reference resolves. |
| V2 | Every `at` is an integer in `[0, duration_seconds]`. Messages sorted ascending by `at`. |
| V3 | Every task has a `group_id` and a `message_id`; the group's thread matches the message's thread; `message.at < task.at`. |
| V4 | Every door named in `require` ∈ {D1…D10, H1…H5}; every state ∈ {open, closed}. |
| V5 | Every `radio` message has an existing audio file, and `audio_duration` matches the file within ±0.3 s. |
| V6 | Exactly 6 actors, one per type; each type used at most once. |

### 13.2 Timing

| # | Rule |
|---|---|
| V7 | For each message, `min(task.at) ≥ message.at + read_cost(message) + 10`. |
| V8 | Rolling 60 s window sum of `read_cost` ≤ 20 s in phase 1, ≤ 35 s in phases 2–4, ≤ 45 s in phase 5. |
| V9 | Consecutive messages are ≥ 6 s apart. |
| V10 | `task.at + task.hold ≤ duration_seconds`. |
| V11 | No challenge is within 20 s of any task boundary (`at` or `at + hold`), since the challenge modal blocks door operation. |
| V12 | Exactly 3 in-session challenges, all with `at ≥ 0.5 × duration_seconds`, spaced ≥ 120 s apart. Exactly 3 debrief challenges. |

### 13.3 Solvability — the perfect-player simulation

| # | Rule |
|---|---|
| V13 | **No contradictory overlap.** For every pair of tasks whose windows `[at, at+hold]` intersect and that name the same door, the required states must be identical. |
| V14 | **Perfect-player trace.** Simulate a player who, from `initial_door_states`, performs the minimum set of toggles that satisfies every task at the latest safe moment. Every task must PASS. A scenario that the perfect player cannot complete is unsolvable and rejected. The resulting expected-state trace is stored in `validation.json` and rendered on the admin page. |
| V15 | **No already-satisfied instruction.** If, in the perfect-player trace, the door state required by a `hold: 0` task already holds at `task.at` and has not changed since the task's message was emitted, the task is a silent free pass → reject. |
| V16 | **No redundant re-requirement.** If a task requires door X to be `s`, and an earlier task in the same group already established X = `s` with no intervening task requiring the opposite, the later task is redundant → reject. *Exception:* a task scheduled in the future may legitimately restate a state that a *different, earlier and already-closed* obligation happened to leave in place — e.g. "open D3 now, close it afterwards" alongside "have D3 open again in 5 minutes" is valid, because an intervening close occurred. |
| V17 | **Temptations must tempt.** Every message with `kind: "tempting_request"` must have no tasks, and must name a door that is under a contradictory active `hold` at the message's `at`. |
| V18 | **Dormancy.** At least one thread has a gap ≥ 240 s between consecutive messages while holding a live obligation, and is the subject of at least one challenge. |
| V19 | **Challenge integrity.** Exactly one option is `correct: true`. The correct option is derivable solely from messages delivered before `challenge.at`. Every distractor references a real thread, actor or door in this scenario, and is false at `challenge.at`. No two options are semantically equivalent. |
| V20 | **Volumes.** 55 ≤ messages ≤ 75; threads ≥ 4; exactly one thread with `grade: "finale"`; 12 ≤ everyday exchanges ≤ 18. |
| V21 | **Safe final configuration.** The last task group requires all five hangar doors closed, so the session ends with the station sealed. |
| V22 | **Reachability.** Every thread has ≥ 1 message in its declared `phase_span`, and no thread's messages fall outside it. |

---

## 14. Application architecture

### 14.1 Stack

- **Backend:** Python 3.12 + FastAPI. WebSockets for the live session. Server-authoritative clock and game loop.
- **LLM:** LiteLLM, provider-agnostic, generation-time only.
- **TTS:** pre-rendered at generation time, written into the scenario folder. Engine choice — see [Open questions](#open-questions) Q-C.
- **Frontend:** Angular. Station rendered on an HTML `<canvas>` with hit-testing for door clicks.
- **Storage:** flat files, no database server.
- **Packaging:** Dockerfile per service plus a `docker-compose.yml`; README with local and Docker instructions.

### 14.2 Storage layout

```
data/
  scenarios/
    index.json
    <scenario_id>/
      scenario.json
      validation.json
      audio/*.wav
  sessions/
    index.json
    <session_id>.json
```

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
| GET | `/api/scenarios` | Bank listing: id, name, duration, thread count, validity |
| POST | `/api/sessions` | `{participant_name, scenario_id}` → `{session_id}` |
| GET | `/api/sessions/{id}` | State snapshot |
| WS | `/ws/sessions/{id}` | Live session |
| GET | `/api/admin/status` | App health, bank inventory, validator summary, active sessions |
| GET | `/api/admin/sessions` | Session history |
| GET | `/api/admin/sessions/{id}` | Full session detail |
| DELETE | `/api/admin/sessions/{id}` | Remove a session |
| GET | `/api/admin/scenarios/{id}` | Full scenario + validation report + perfect-player trace |
| POST | `/api/admin/scenarios/generate` | Start a generation job |
| GET | `/api/admin/jobs/{id}` | Generation job progress |

No authentication anywhere.

**WebSocket — server → client:** `snapshot`, `tick` (clock, score, pending count), `notification_available`, `message` (on open), `challenge`, `failure_notice`, `door_state`, `session_end`.

**WebSocket — client → server:** `toggle_door {door}`, `open_notification`, `acknowledge {id}`, `answer_challenge {challenge_id, option_id}`.

### 14.5 Pages

| Page | Contents |
|---|---|
| **Home** `/` | Participant name field, scenario picker from the bank, **Start shift**. No other configuration. |
| **Game** `/game/:id` | Station canvas, notification button with pending count, penalty total, station clock, elapsed timer. Nothing else. |
| **Summary** `/summary/:id` | The debrief breakdown from §9.1. |
| **Admin** `/admin` | App status, bank inventory with validity, session history, **Generate scenario**. |
| **Admin — session** `/admin/sessions/:id` | Full replay data: actors, threads, every message with delivery/open/ack timestamps, task results, door-state timeline vs. expected trace, challenges and answers, penalties, elapsed time. Delete button. |
| **Admin — scenario** `/admin/scenarios/:id` | Scenario JSON, validation report, perfect-player trace, radio transcripts, audio playback. |

The admin pages exist to debug and tune generation; they are the only place ground truth is visible.

---

## 15. Visual design

Not a game. A **plain, unglamorous industrial control console**.

- Dark theme, near-black background, muted panel greys, thin 1 px rules.
- Monospace throughout (e.g. IBM Plex Mono / JetBrains Mono), small sizes, uppercase labels.
- Minimal colour, used only as state: **open = green**, **closed = red**, **alert = amber**. Nothing decorative.
- **No animations** in this version — not even door transitions. A door changes state instantly on the canvas.
- No people, no ships, no movement anywhere.
- Station drawn as flat rectangles and lines: rooms as outlined boxes with a label, corridors as connecting boxes, doors as short thick bars on the wall between two areas, hangar doors as bars on the station's outer edge. Door labels (D1…D10, H1…H5) always visible.
- Clicking a door bar toggles it. Hover shows the door label and its current state, nothing more.
- Message modal: sender portrait left, sender name and channel above, body right, single **ACKNOWLEDGE** button. Radio messages show a waveform in place of the body text. Shakes if dismissed any other way.

---

## 16. Deliberately out of scope

Recorded so they are not re-litigated:

- The Keeper application itself, and the with/without-Keeper experimental conditions.
- Paired-scenario cognitive-equivalence machinery.
- Message history, replay, "repeat that" — permanently excluded, this is the core manipulation.
- Priority hierarchies and authority ranking between actors.
- Locked or unavailable doors; scenario-driven door disabling.
- Animation, movement simulation, pathfinding, pressure physics.
- Research data export (CSV/JSON); the admin page is the only view.
- Surviving a backend restart mid-session.
- Authentication.
- Any language other than English.
- Any LLM or TTS call at runtime.

---

## Open questions

Remaining decisions, smallest set I could reduce to.

**Q-A — "I don't know" penalty.** Same cost as a wrong answer, half, or zero? A free "I don't know" gives you a clean *calibration* signal (aware-of-not-knowing vs. confidently-wrong) but invites spamming it. Recommendation: **same penalty, logged distinctly**, so the two are separable in the debrief without creating an escape hatch.

**Q-B — Radio messages carry no transcript.** Confirmed above as audio-only. This is a large difficulty increase and makes the game unplayable without working audio. Do you want a fallback (transcript shown if audio fails to load), or should a broken audio session simply be void?

**Q-C — TTS engine.** Local (**Piper** — free, offline, fast, six clearly distinct voices, runs in the Docker image, deterministic) vs. cloud (**OpenAI TTS / ElevenLabs** — better quality, needs a key, non-deterministic). Recommendation: **Piper**, because reproducibility matters more than timbre and the audio ships inside the bank.

**Q-D — Failure notices at lower queue priority (§7).** I chose this so a cascade of failures cannot bury the messages needed to recover. The alternative is strict FIFO with everything mixed. Confirm?

**Q-E — Cascade cancellation (§6.3).** When a task fails, later tasks in its group are cancelled. Alternative: keep evaluating them, so a player who breaks an obligation and then recovers still gets credit for the rest. Recommendation: cancel — one mistake, one penalty, and no false passes.

**Q-F — Pending-message count.** The notification button shows how many messages are waiting. That is workload information, not content, so I judged it fair. Hide it instead?

**Q-G — Challenges block door operation (§8.1).** With no answer time limit, a slow answerer will watch obligations fail without being able to act. V11's 20 s clearance mitigates it but does not eliminate it. Accept, or make challenges non-blocking for door controls?

**Q-H — Station map v1.** §3 is my draft: 6 rooms, 3 corridors, 5 hangar bays, three doorless passages. Hangar Bay 5 deliberately has no internal door. Review the door assignments and hangar roles before scenario generation starts, as agreed.

**Q-I — Redundant `game.md` / `game2.md`.** `game2.md` is fully superseded by this document and `game.md` by both. Move them into `archive/` alongside `spec.v1.md`?
