"""The prompts, one per generation stage.

Generation is staged rather than one giant call, for two reasons. A 60-message
scenario in a single response is where models start dropping fields, and each
stage can be given exactly the context it needs -- the challenge stage, for
instance, sees the finished timeline with real timestamps, which is the only way
it can write a question whose answer was actually derivable when it was asked.

No stage ever writes a timestamp. `schedule.py` does that.
"""
from __future__ import annotations

import json

from ..config import Difficulty
from ..station import Station
from .brief import LANGUAGE_NAMES, rules_brief, station_brief


def system_prompt(language: str = "en") -> str:
    return f"""You are the scenario author for OpStation, a door-control game used
as a research instrument for measuring memory. You write terse, credible station
radio traffic in {LANGUAGE_NAMES[language]} and you follow structural rules exactly.

You always reply with a single JSON object and nothing else. No prose outside the
JSON, no markdown fence, no commentary."""


def _context(st: Station, diff: Difficulty, duration: int, language: str = "en") -> str:
    return f"{station_brief(st)}\n\n{'=' * 78}\n\n{rules_brief(diff, duration, language)}"


# ---------------------------------------------------------------- stage 1: plan

CATALOGUE_ORDINARY = {
    "construction_extension": "Construction of Extension Epsilon — long hold on D13 and H5 while the extension is depressurised; two delays; release after a pressure test; possible reopening.",
    "damaged_vessel": "Damaged transport vessel — H2 opened for emergency docking then held closed pending inspection; the crew wants to leave before Security clears them; contradictory damage reports.",
    "pressure_leak": "Pressure leak — isolate a sector; a resident is trapped inside; a narrow authorised opening of one door only; the doors are released at different times.",
    "missing_technician": "Missing technician — D12 opened for a named technician, then the thread goes silent; radio contact lost; a search party; the technician resurfaces ten minutes later.",
    "medical_quarantine": "Medical quarantine — H1 then D3 held closed; an initial 'negative test, reopen in five minutes' that is then retracted; a second test clears it.",
    "reactor_maintenance": "Reactor maintenance — D10 closed with a stated duration but NO release message ever arrives; a third party asks to use it; the player must know Engineering never confirmed.",
    "contamination": "Contamination containment — isolate Storage and the service corridor; the scope escalates.",
    "vip_inspection": "VIP inspection — Command-imposed route restrictions that shift as the inspection party moves.",
}

CATALOGUE_FINALE = {
    "invasion": "Invaders attack — a patrol finds an abandoned ship, weapons damage, all teams recalled, a lockdown countdown while teams are still outside, hangars sealed, one hangar forced open, retreat routes opened and closed under time pressure, dormant threads reopen, a 'sector secure' that does NOT release every obligation, then lockdown lifted.",
    "hull_breach": "Catastrophic hull breach — progressive sector-by-sector isolation, evacuation corridors, revised isolation boundaries.",
    "reactor_emergency": "Reactor emergency — escalating engineering isolation, forced venting windows, personnel extraction.",
    "station_contamination": "Station-wide contamination — rolling quarantine boundaries that move room by room.",
}


def plan_prompt(
    st: Station, diff: Difficulty, duration: int, *, finale: str | None = None,
    theme: str | None = None, threads: int = 5, language: str = "en",
) -> tuple[str, str]:
    vol = diff.volumes
    finale_choices = (
        {finale: CATALOGUE_FINALE[finale]} if finale in CATALOGUE_FINALE else CATALOGUE_FINALE
    )
    user = f"""{_context(st, diff, duration, language)}

{'=' * 78}

STAGE 1 of 5 — THE PLAN. Cast the actors and choose the threads. No prose yet.

Pick {threads} incident threads from this catalogue, of which EXACTLY ONE is the
finale:

ORDINARY
{json.dumps(CATALOGUE_ORDINARY, indent=2)}

FINALE (choose exactly one)
{json.dumps(finale_choices, indent=2)}
{f'THEME HINT: {theme}' if theme else ''}

Name one person per actor type. Names should sound like a working crew roster,
not like a cast list: rank or role plus surname is ideal, and names should sound
like {LANGUAGE_NAMES[language]}-speaking crew. The `system` actor is the
station's automated voice and is not a person, so give it a plain label such
as "Station Control" or "OpStation Automated" (translated, if the language is
not English).

Reply with JSON:
{{
  "name": "short evocative scenario name, 2-4 words",
  "actors": {{
    "security": "Officer Kade Ruiz", "construction": "...", "cargo": "...",
    "medical": "...", "civilian": "...", "system": "Station Control"
  }},
  "threads": [
    {{
      "key": "ext",                       // short slug, unique, lowercase
      "catalogue_key": "construction_extension",
      "grade": "ordinary",                // or "finale" for exactly one
      "title": "Extension Epsilon pressure isolation",
      "opens_in_phase": 1,                // 1..5, when the thread starts
      "runs_to_phase": 5,
      "premise": "two sentences on what happens in this thread, including which
                  doors or places it restricts and how it ends",
      "carries_retraction": false          // set true on EXACTLY TWO threads
    }}
  ]
}}

Rules for the plan:
- The finale thread must open in phase 4 or 5 and dominate phase 5.
- At least one ordinary thread must open in phase 1 so onboarding has content.
- At least one ordinary thread must be the reactor-maintenance shape or another
  thread that never receives a release message. That thread is what tests
  whether the player confuses "waiting" with "resolved".
- Spread the restricted doors around the station. Do not put every thread on the
  service corridor. Say in each premise which doors or place that thread
  restricts, and do not let two threads restrict the same door.
- Set `carries_retraction: true` on exactly two threads. Those are the ones
  where an actor will later withdraw an instruction they gave."""
    return system_prompt(language), user


# --------------------------------------------------------------- stage 2: beats

def beats_prompt(
    st: Station, diff: Difficulty, duration: int, *, thread: dict, actors: dict[str, str],
    other_threads: list[dict], teach_bypass: bool, claimed: list[str] | None = None,
    carries_retraction: bool = False, max_hold: int = 480, language: str = "en",
) -> tuple[str, str]:
    others = json.dumps(
        [{k: t.get(k) for k in ("key", "title", "premise")} for t in other_threads], indent=2
    )
    claimed_line = ", ".join(claimed) if claimed else "(none reserved)"

    bypass_note = """
SPECIAL INSTRUCTION FOR THIS THREAD: somewhere in phase 1 or 2, have an actor
mention in passing that they are taking the Hangar Bay 3 shortcut between the
central junction and the service corridor. One line, in character, no
explanation. This is the only time the station teaches that D9 exists, so that
later isolation obligations test memory rather than knowledge.
""" if teach_bypass else ""

    retraction_note = """
THIS THREAD CARRIES A RETRACTION. After phase 1, the actor who gave one of this
thread's instructions withdraws it: a beat with kind "retraction", a "cancels"
naming that obligation, and a "retraction_style".

It must have TEETH. Later in this thread, something must require the OPPOSITE
state on a door the retraction freed, so that a player who still believes the old
restriction refuses and gets it wrong. A retraction with no consequence is
decoration.

Whichever style, restate enough of the original instruction that the player does
not have to guess what is being lifted -- the door, and ideally the reason it
was closed in the first place. "Forget what I said about D3" is weaker than
"Forget what I said about holding D3 closed for the leak inspection -- that is
over now." A bare "forget what I told you" with nothing else is not answerable.

Choose the style by how much work the player has to do:
  explicit        names the door and the action outright
  self_reference  "forget what I told you earlier" — the player must recall
                  which obligation THIS actor created. Only legal if this actor
                  holds one live obligation, or the text pins down which.
  partial         keeps part and drops part: "you still need D10 closed, forget
                  the reopen I asked for"
""" if carries_retraction else ""

    user = f"""{_context(st, diff, duration, language)}

{'=' * 78}

STAGE 2 of 5 — WRITE ONE THREAD. Write the messages for this thread only.

THREAD
{json.dumps(thread, indent=2)}

THE CAST (use these names in the prose)
{json.dumps(actors, indent=2)}

THE OTHER THREADS running in the same session, for cross-references and for
challenge distractors later — do not write their messages here:
{others}

DOORS THE OTHER THREADS HAVE CLAIMED. Two threads holding one door in opposite
states at the same moment is a contradiction the player cannot play around, so
stay off these unless your instruction is a brief crossing:
  {claimed_line}
{bypass_note}{retraction_note}
Reply with JSON:
{{
  "obligations": [
    {{"key": "og_ext_vent", "label": "Keep H5 closed while Epsilon is vented"}}
  ],
  "dormant_after": "b3",          // beat key after which this thread goes silent
                                  // for 4+ minutes while still holding an
                                  // obligation. null if it is not the dormant one.
  "beats": [
    {{
      "key": "b1",
      "phase": 1,                 // must lie inside the thread's phase range
      "actor": "construction",    // one of the six types
      "channel": "radio",         // "radio" is audio-only and carries more
                                  // memory load; use it for instructions that
                                  // matter. "text" for detail-heavy messages.
      "kind": "instruction",      // instruction | update | supersede | status |
                                  // resolution | reopen | chatter | retraction
      "text": "Door Control, Construction. We are venting Extension Epsilon in
               two minutes. H5 stays closed until I clear it — no exceptions.",
      "creates": "og_ext_vent",   // the obligation this message creates, or null
      "tasks": [
        {{
          "require": {{"H5": "closed"}},   // explicit doors, OR use
                                           // isolation_target below instead
          "hold": 300,                     // seconds the state must hold.
                                           // 0 = one instantaneous check.
                                           // NEVER more than {max_hold}.
          "delay": 0,                      // extra seconds before the window
                                           // opens, on top of reading time
          "fail_message": "Foreman Voss ordered H5 held closed while Epsilon
                           was vented, to keep the corridor sealed. It was
                           opened before he cleared it."
                                           // the full report: who asked, for
                                           // what door and state, why, and
                                           // what went wrong -- delivered to
                                           // the player exactly as written,
                                           // word for word, if this fails
        }}
      ]
    }}
  ]
}}

HOW TO WRITE A TASK
- Direct: `"require": {{"D10": "closed"}}`. Use this in phase 1 always, and
  wherever the instruction genuinely names a door.
- Indirect: `"isolation_target": "service_sector", "include_hangar_doors": true`
  and NO `require`. The doors are computed from the map for you. The prose MUST
  contain that target's exact phrase from the layout brief. Roughly half of
  phase 2-3 obligations and most of phase 4-5 obligations should be indirect.
- `include_hangar_doors` is true only when the fiction is about vacuum or
  pressure.
- Never require a door the layout brief lists as interior to your target.
- Never instruct an action that is already true of the starting state.
- A crossing is two tasks in one obligation: open with a `hold` for the crossing,
  then a second task with `hold: 0` and a larger `delay` to close it again.

WHAT MAKES THIS THREAD WORTH PLAYING
- One obligation that lasts several minutes, so there is something to remember.
- A stretch where nothing is said but the obligation is still live.
- An ending that either releases the obligation explicitly (`kind: resolution`)
  or deliberately never does — the reactor-maintenance shape, where the player
  has to know that nobody ever confirmed.
- 4 to 9 beats. Terse. Nobody explains the game."""
    return system_prompt(language), user


# ----------------------------------------------------------- stage 3: everyday

def everyday_prompt(
    st: Station, diff: Difficulty, duration: int, *, actors: dict[str, str],
    threads: list[dict], count: int, language: str = "en",
) -> tuple[str, str]:
    user = f"""{_context(st, diff, duration, language)}

{'=' * 78}

STAGE 3 of 5 — EVERYDAY TRAFFIC. Write {count} short, self-contained exchanges
that have nothing to do with the incident threads. They exist to fill the
player's attention so the real threads have to compete for it.

THE CAST
{json.dumps(actors, indent=2)}

THE INCIDENT THREADS (do not touch these; just avoid contradicting them)
{json.dumps([{k: t[k] for k in ('key', 'title', 'premise')} for t in threads], indent=2)}

Each exchange is 2 messages and 1 or 2 tasks — a request and its follow-up, or
a request and an unrelated aside from the same person. A resident wanting D5 open, a
cargo transfer through D12, a maintenance inspection, a shuttle docking at H1, a
brief environmental hold. Ordinary station life.

Reply with JSON:
{{
  "exchanges": [
    {{
      "key": "ev1",
      "title": "Cargo transfer to Storage",
      "obligation": {{"key": "og_ev1", "label": "Open D12 for the pallet run"}},
      "beats": [
        {{
          "key": "ev1b1", "phase": 2, "actor": "cargo", "channel": "text",
          "kind": "instruction", "creates": "og_ev1",
          "text": "Door Control, Cargo. Pallet run to Storage, two minutes.
                   Keep D12 open for the crossing, then close it behind us
                   once we're through.",
          "tasks": [
            {{"require": {{"D12": "open"}}, "hold": 90, "delay": 30,
             "fail_message": "The pallet run was blocked at D12."}},
            {{"require": {{"D12": "closed"}}, "hold": 0, "delay": 150,
             "fail_message": "D12 was left open after the transfer."}}
          ]
        }}
      ]
    }}
  ]
}}

At least HALF of these exchanges must be tagged phase 4 or 5. The second half of
the shift needs traffic as much as the first does -- the pressure is supposed to
build, not taper off once the incident threads have said their piece. A few
should carry NO obligation and NO `cancels` at all: a single beat of pure
chatter or a status remark with nothing riding on it -- a passing comment about
a place, a bit of station gossip, someone noting a door reads correctly on
their own panel. That is what makes the quiet stretches between real
obligations feel inhabited rather than empty. Do NOT write a "stand down" or
"closing this out" message here -- that is a retraction, and retractions are
handled in a separate stage. An everyday exchange's second beat, if it has one,
is a plain follow-up with its own task (see the `D10` example above), never a
message that cancels the first beat's obligation.

Use every actor type at least twice across the set. Vary the doors: touch D1,
D2, D3, D5, D6, D8, D11, D13 and the hangar doors, not only the service
corridor.

Watch the starting state: D4, D5, D7, D9 and D12 start OPEN, everything else
CLOSED. "Open D5 for me" is invalid — D5 is already open. "Hold D5 closed while
we clean" is valid and good."""
    return system_prompt(language), user


# --------------------------------------------------------- stage 4: temptations

def temptation_prompt(
    st: Station, diff: Difficulty, duration: int, *, actors: dict[str, str],
    obligations: list[dict], count: int, language: str = "en",
) -> tuple[str, str]:
    user = f"""{_context(st, diff, duration, language)}

{'=' * 78}

STAGE 4 of 5 — CONFLICTING REQUESTS. Write {count} of them.

A conflicting request is a message with NO TASK. Somebody asks, plausibly and
sympathetically, for a door that another thread's live obligation requires to
stay as it is. Refusing costs nothing. Complying breaks the other obligation and
the player is penalised — through that thread, never through this message.

This is the only way the game creates a dilemma, because there is no priority
system: no actor outranks another, and nothing infers what the player "should"
have done.

THE CAST
{json.dumps(actors, indent=2)}

LIVE OBLIGATIONS you may pull against. Pick one per request, and pick one owned
by a DIFFERENT thread than the actor you choose would naturally belong to:
{json.dumps(obligations, indent=2)}

Reply with JSON:
{{
  "requests": [
    {{
      "key": "tr1",
      "targets": "og_ext_vent",     // the obligation this pulls against
      "thread": "ev_pool",          // leave as "ev_pool" — these belong to no
                                    // incident thread
      "actor": "civilian",
      "channel": "radio",
      "text": "Door Control? I have been waiting at H5 for twenty minutes. My
               tools are on the other side and my shift ended an hour ago. Can
               you just open it for thirty seconds?"
    }}
  ]
}}

Each request MUST name, in the prose, at least one door id that the targeted
obligation requires ({', '.join(sorted({d for o in obligations for d in o.get('doors', [])}))}).
Make it sympathetic and specific — a person with a reason, not a test."""
    return system_prompt(language), user


# --------------------------------------------------------- stage 5: challenges

def challenge_prompt(
    st: Station, diff: Difficulty, duration: int, *, timeline: str, actors: dict[str, str],
    threads: list[dict], slots: list[dict], retractions: list[dict] | None = None,
    language: str = "en",
) -> tuple[str, str]:
    retraction_note = ""
    if retractions:
        retraction_note = f"""
WITHDRAWN INSTRUCTIONS. During this shift someone took back something they had
asked for:

{json.dumps(retractions, indent=2)}

At least one of your six questions must be about one of these, and must be
answerable only by somebody who knows the instruction was withdrawn. Put that
message id in its `depends_on`. This is the sharpest thing the shift tests: a
player who remembers the original instruction but not the withdrawal will pick a
distractor that used to be true.
"""

    user = f"""{_context(st, diff, duration, language)}

{'=' * 78}

STAGE 5 of 5 — KEEPER CHALLENGES. Six questions: three during the shift and
three in the untimed debrief afterwards.

THE FULL TIMELINE as the player experiences it. Every line is one message with
the second it arrives. This is your only source of truth — a question's answer
must be derivable from lines that arrive BEFORE the question does:

{timeline}

THE CAST
{json.dumps(actors, indent=2)}

THE THREADS
{json.dumps([{k: t[k] for k in ('key', 'title', 'premise')} for t in threads], indent=2)}

THE SLOTS, with the exact second each question is asked:
{json.dumps(slots, indent=2)}
{retraction_note}

A challenge is disguised as ordinary station traffic. Somebody asks because THEY
NEED THE ANSWER, and the reason matters as much as the question:
  * Building a case — Security intends to arrest whoever went through.
  * Assigning blame — Works broke something on the way out of a hangar.
  * Tracing a contact chain — Medical needs patient zero.
  * Reconstructing a timeline — Command is writing the incident report.
  * Disputing a lockout — a civilian was stuck somewhere for ten minutes.
  * Checking before acting — Security wants a door and asks what is live on it.
  * Auditing a closed incident — is it actually finished, or just quiet?

Prefer an asker from a DIFFERENT thread than the one being asked about. That is
where provenance memory actually gets tested.

Reply with JSON:
{{
  "challenges": [
    {{
      "slot_id": "c1",              // from the slots list above
      "kind": "provenance",         // thread | time | provenance, one of each
                                    // per group of three
      "thread": "ext",              // the thread being asked ABOUT
      "actor": "security",          // who is asking
      "channel": "text",
      "pretext": "Security is building a case against whoever entered the
                  service corridor and needs to know who authorised the door.",
      "prompt": "Door Control, Security. Someone was let through into the
                 service corridor about an hour ago and I need a name for the
                 report. Who authorised that door?",
      "options": [
        {{"text": "Construction, for the Epsilon vent crew.", "correct": true}},
        {{"text": "Medical, for the patient transfer.", "correct": false}},
        {{"text": "Cargo, for the pallet run to Storage.", "correct": false}},
        {{"text": "Engineering, for the coolant flush.", "correct": false}}
      ],
      "explanation": "Construction asked for it at 04:05 and Security was never
                      involved.",
      "depends_on": ["m_012", "m_031"]   // message ids from the timeline whose
                                         // content the answer relies on
    }}
  ]
}}

HARD RULES
- Exactly 4 options. Exactly one correct. Never author "I don't know" — the game
  adds it as a fifth option itself.
- Every distractor must be drawn from ANOTHER REAL THREAD in this timeline: a
  real actor, a real door, a real reason. And it must be FALSE at the moment the
  question is asked. Generic filler like "routine maintenance" is not acceptable.
- `depends_on` must list the message ids the answer rests on, and every one of
  them must arrive before the question. Message ids are for `depends_on` ONLY —
  never write one into `prompt`, `explanation` or an option's `text`. The player
  has never seen an id; say what happened in prose ("Construction asked for it
  at 04:05", not "see m_012").
- The whole shift lasts under half an hour, and no obligation holds for more
  than a few minutes. A "time" question's answer is always in MINUTES or
  SECONDS — never hours. An option measured in hours is wrong on its face and
  will be rejected.
- One question must be about a thread that has been silent for several minutes
  while still holding an obligation. The debrief questions should reach back
  furthest, including threads not heard from in ten minutes or more."""
    return system_prompt(language), user


# ------------------------------------------------------------------- repairs

#: Rules whose only possible fix is rewriting prose. Everything else the
#: validator can complain about is arithmetic or structure, and is repaired
#: deterministically without spending a call.
TEXT_RULES = frozenset({"V19", "V25", "V27", "V28", "V32", "V35", "V36", "V37", "V38"})


def rewrite_prompt(
    st: Station, diff: Difficulty, duration: int, *, items: list[dict], language: str = "en",
) -> tuple[str, str]:
    """Ask for a rewrite of specific messages or challenges, and nothing else."""
    language_line = (
        "" if language == "en" else f"\nWrite the rewrite in {LANGUAGE_NAMES[language]}.\n"
    )
    user = f"""{station_brief(st)}
{language_line}

{'=' * 78}

REPAIR PASS. The validator rejected some of your prose. Rewrite ONLY the items
below, keeping the same meaning, the same speaker and the same length, and
fixing what the errors say.

{json.dumps(items, indent=2, ensure_ascii=False)}

Reply with JSON, one entry per item, using the same `id`:
{{
  "items": [
    {{"id": "m_012", "text": "the corrected message text"}},
    {{"id": "q_002",
      "prompt": "the corrected question",
      "explanation": "the corrected explanation",
      "options": [
        {{"text": "...", "correct": true}}, {{"text": "..."}},
        {{"text": "..."}}, {{"text": "..."}}
      ]}}
  ]
}}

Reminders that cover most of these errors:
- Only doors D1-D13 and H1-H5 exist. Only the places in the layout brief exist.
  No invented decks, sectors, bays or door numbers.
- A message that withdraws an instruction must make clear WHICH instruction, by
  naming the door, the place, or the subject, and should remind the player why
  it was asked for in the first place.
- A retraction that names another actor's instruction must name that actor.
- Every distractor must come from another real thread in this session, name a
  real actor, door or place, and be false at the moment the question is asked.
- Exactly four options, exactly one correct, and never author "I don't know".
- A "time" answer is in minutes or seconds — the whole shift is under half an
  hour, so an hour-scale answer is always wrong.
- Never write an internal id (m_012, t_045, og_ext_vent) into anything a player
  reads — describe what happened in prose instead.
- A message is never a question — nothing outside a challenge can be answered.
  Say it as a statement or a report.
- Plain {LANGUAGE_NAMES[language]}. Short sentences, common words, no idioms, no
  slang, no jokes. Most players are not native speakers and a spoken message is
  heard once."""
    return system_prompt(language), user


def retraction_prompt(
    st: Station, diff: Difficulty, duration: int, *, thread: dict, actor: str,
    obligation: dict, beats: list[dict], language: str = "en",
) -> tuple[str, str]:
    """Ask for one withdrawal and the obligation that gives it teeth.

    A separate, tiny call because it is the one beat the thread stage most often
    forgets, and because a withdrawal is only worth anything if something later
    depends on the player knowing about it -- which means writing the pair
    together or not at all.
    """
    language_line = (
        "" if language == "en" else f"\nWrite both messages in {LANGUAGE_NAMES[language]}.\n"
    )
    user = f"""{station_brief(st)}
{language_line}

{'=' * 78}

ONE WITHDRAWAL, PLUS ITS CONSEQUENCE.

This thread already exists:
{json.dumps(thread, indent=2)}

Its messages so far:
{json.dumps(beats, indent=2)}

The obligation to withdraw:
{json.dumps(obligation, indent=2)}

Write TWO messages.

1. **The withdrawal.** {actor.title()} takes back the instruction that created
   that obligation. It must be clear WHICH instruction is being withdrawn — name
   the door, the place, or the subject — because the player has heard a great
   deal by now and "forget what I said" is not answerable on its own. Restate
   enough of the original obligation as a reminder, ideally including why it was
   asked for in the first place: "the hold you were keeping on D3 for the leak
   inspection is over" reminds the player what they are being released from,
   rather than assuming they still remember the name of it.

2. **The consequence.** Later, somebody needs that same door in the OPPOSITE
   state. This is what makes the withdrawal matter: a player who still believes
   the old restriction refuses, and is wrong. Give it a plain reason of its own —
   a crossing, a transfer, a patient, an inspection — not a reference back.

Reply with JSON:
{{
  "withdrawal": {{
    "actor": "{actor}",
    "channel": "radio",
    "retraction_style": "explicit",
    "text": "Door Control, {actor.title()}. Stand down on ... — that hold is lifted."
  }},
  "consequence": {{
    "actor": "cargo",
    "channel": "text",
    "label": "short name for this new obligation",
    "text": "the instruction that needs the door the other way",
    "require": {{ "D7": "open" }},
    "hold": 120,
    "fail_message": "what goes wrong if the player leaves it as it was"
  }}
}}

`require` must name at least one door from the withdrawn obligation, in the
opposite state. `retraction_style` is `explicit` when you name the door outright,
`partial` when you keep part of the instruction and drop the rest."""
    return system_prompt(language), user
