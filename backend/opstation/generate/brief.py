"""The station and rules brief handed to the LLM.

Generated from station.json and difficulty.json, never transcribed. Change a
door and the prompt changes with it, so the generator cannot be told about a
station that no longer exists.
"""
from __future__ import annotations

from ..config import Difficulty
from ..station import Station, door_sort_key


def station_brief(st: Station) -> str:
    lines: list[str] = [
        f"STATION LAYOUT ({st.version}) — fixed forever, identical in every scenario.",
        "",
        "AREAS",
    ]
    for area in st.areas.values():
        role = f"   — {area['sub']}" if area.get("sub") and area["kind"] == "hangar_bay" else ""
        lines.append(f"  {area['id']:<4} {area['prose']}{role}")

    lines += ["", "INTERNAL DOORS  (state at session start in brackets)"]
    for door in sorted(st.internal_doors, key=lambda d: door_sort_key(d.id)):
        a, b = door.between
        lines.append(
            f"  {door.id:<4} {st.area_prose(a)} <-> {st.area_prose(b)}   [{door.initial}]"
        )
    lines += ["", "HANGAR DOORS  (bay to the outside; all closed at session start)"]
    for door in sorted(st.hangar_doors, key=lambda d: door_sort_key(d.id)):
        bay = door.station_side()
        outside = next(x for x in door.between if x != bay)
        role = st.hangar_roles.get(door.id, "")
        lines.append(f"  {door.id:<4} {st.area_prose(bay)} -> {outside}   {role}")

    lines += [
        "",
        "PERMANENT DOORLESS OPENINGS — can never be closed:",
    ]
    for p in st.passages.values():
        a, b = p.between
        lines.append(f"  {st.area_prose(a)} <-> {st.area_prose(b)}")

    lines += [
        "",
        "ISOLATION TARGETS — the only place-names an indirect instruction may use.",
        "Give the isolation_target id; the doors are computed for you from the map.",
        "",
        f"  {'id':<22}{'phrase to say in the prose':<32}{'closes':<26}{'+pressure':<12}stays open",
    ]
    for t in sorted(st.isolation_targets.values(), key=lambda t: (t.cls != "sector", t.id)):
        lines.append(
            f"  {t.id:<22}{t.phrase:<32}{', '.join(t.cut):<26}"
            f"{', '.join(t.hangar_doors_inside) or '—':<12}"
            f"{', '.join(t.interior_doors) or '—'}"
        )

    lines += [
        "",
        "CANNOT BE SEALED ALONE — never name these as an isolation target:",
    ]
    for area in sorted(st.not_isolable):
        enclosing = st.smallest_volume_containing(area)
        lines.append(
            f"  {st.area_prose(area)} — a doorless opening crosses its boundary. "
            f"Use {enclosing.id!r} instead."
        )

    lines += [
        "",
        "TWO TOPOLOGY FACTS THAT MATTER",
        "  * Hangar Bay 3 touches BOTH C2 (D8) and C3 (D9). Sealing anything that",
        "    involves the service corridor therefore needs D9 as well as D7. A player",
        "    who forgets the back route leaves the sector open. Mention the Hangar Bay 3",
        "    shortcut once, in an early thread, so it becomes a memory test rather than",
        "    a knowledge gap.",
        "  * Sealing a place closes its BOUNDARY, not everything inside it. Interior",
        "    doors stay open. Never ask for an interior door to be closed as part of an",
        "    isolation.",
    ]
    return "\n".join(lines)


def rules_brief(diff: Difficulty, duration: int) -> str:
    vol = diff.volumes
    return f"""
HOW THE GAME WORKS — read this before writing anything.

The player is the Door Control Operator. Their only actions are opening and
closing doors, reading or hearing messages, and answering questions. The
difficulty is MEMORY: there is no message history, no log, no replay, no pause.
A message is delivered once and is gone. A radio message is audio only and has
no transcript.

TASKS ARE THE SOLE GROUND TRUTH. There is no priority system, no authority
ranking, no inferred intent. If you do not write a task, no door state is right
or wrong. A sympathetic plea with no task behind it costs the player nothing to
refuse -- that is how a conflicting request is authored.

A task is a door state that must hold over a window:
  require: {{"D7": "closed"}}   hold: 300     -> D7 must be closed for 300 s
  hold: 0                                     -> one instantaneous check
The moment a door in `require` is wrong, the task FAILS, the player is told, and
one penalty is applied. Tasks that express one obligation share a group; when
one fails the rest of the group is cancelled, so one mistake costs exactly one
penalty.

NEVER write an instruction that asks for something already true. D4, D5, D7, D9
and D12 start OPEN; every other door starts CLOSED. "Close D3 now" is invalid,
because D3 is already closed. Asking to HOLD an already-correct state is fine
and good -- that is the tempting-request pattern.

A RETRACTION withdraws an obligation: a message with `cancels`. It takes effect
on delivery. It must have teeth -- something later must depend on the player
knowing the obligation is gone, normally a task requiring the OPPOSITE state on
the freed door. {vol['retractions_min']}-{vol['retractions_max']} per scenario, never in phase 1.

Session length: {duration} s. Phases, as fractions of that:
  1 Onboarding    0-15%    one obligation at a time, long windows, DIRECT
                           instructions only (name the door)
  2 Multiple      15-38%   2-3 concurrent threads, first conflicting request
  3 Memory        38-60%   3-4 threads, one goes silent 4+ min while unresolved
  4 High load     60-80%   4 threads, messages queue behind one another
  5 Finale        80-100%  a major event dominates, dormant threads reopen

Volumes: {vol['messages_min']}-{vol['messages_max']} messages, at least {vol['threads_min']} incident threads of which
EXACTLY ONE is finale-grade, plus {vol['everyday_exchanges_min']}-{vol['everyday_exchanges_max']} short everyday exchanges.

Six actors, one person per type, the same person all session:
  security      patrols, EVA, inspections, lockdowns
  construction  extension work, exterior operations
  cargo         transfers, storage, low-priority traffic
  medical       patient transport, quarantine
  civilian      residents, researchers, routine requests
  system        automated alerts and alarms (never a person)

WRITING. Radio-terse, in character, English. Nobody explains the rules. An actor
says what they need and why it matters to them. Prose names doors as D7 / H5 and
places by the exact phrases in the layout brief. Do not invent rooms, decks,
sectors or door numbers.

PLAIN ENGLISH, AND THIS MATTERS MORE THAN STYLE. Most players will not be native
speakers, and a spoken message is heard once with no transcript. So:

  * Short sentences. One instruction per sentence. Under twenty words.
  * Common words. "Leaving" not "vacating". "Now" not "at this juncture".
  * NO idioms and NO figures of speech. Not "keep an eye on it", not "we are up
    against it", not "buy me some time", not "the clock is ticking".
  * NO slang and no invented jargon. Say "minutes", never "mikes". Say
    "immediately", never "yesterday".
  * NO jokes, no wordplay, no sarcasm, no irony. An actor can be curt, worried or
    impatient -- that is character. Nothing needs to be funny.
  * Say the door name early in the sentence, and say it once.

Terse and plain are not in tension. "Door Control, Cargo. Open D12 for two
minutes, then close it." is both.
""".strip()
