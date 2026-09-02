"""The station and rules brief handed to the LLM.

Generated from station.json and difficulty.json, never transcribed. Change a
door and the prompt changes with it, so the generator cannot be told about a
station that no longer exists.
"""
from __future__ import annotations

from ..config import Difficulty
from ..station import Station, door_sort_key

#: Generation is monolingual per scenario (spec 16): text and audio never mix
#: languages within one session. Used to name the target language in the brief
#: and to pick which plain-language block below applies.
LANGUAGE_NAMES = {"en": "English", "fr": "French"}


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


def rules_brief(diff: Difficulty, duration: int, language: str = "en") -> str:
    vol = diff.volumes
    language_line = (
        "" if language == "en" else
        f"\nWrite every piece of player-facing text -- messages, fail_message, "
        f"challenge prompts, options and explanations, actor names -- in "
        f"{LANGUAGE_NAMES[language]}. These instructions stay in English; only the "
        f"game's own content changes language.\n"
    )
    return f"""
HOW THE GAME WORKS — read this before writing anything.
{language_line}
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

`fail_message` IS that notice, delivered to the player verbatim -- nothing is
generated at the moment of failure, so write it as the full reason a report
would give: who asked, for which door and state, why, and what went wrong. Not
an alarm code. "Foreman Voss asked for H5 held closed while Epsilon was vented.
It was opened before he cleared it." -- not "PRESSURE ALARM: H5 open."

NEVER write an instruction that asks for something already true. D4, D5, D7, D9
and D12 start OPEN; every other door starts CLOSED. "Close D3 now" is invalid,
because D3 is already closed. Asking to HOLD an already-correct state is fine
and good -- that is the tempting-request pattern.

DOOR-STATE PHRASING must match what the player already sees on the map. If the
door has to CHANGE state: "Open D3." / "Close D10." If it has to STAY as it
already is: "Keep D12 open for two minutes." / "Do not close D5 yet." / "Hold
D7 open while the crew crosses." Never phrase an already-true state as an
instruction to change it: D12 starts open, so "Open D12" reads as a
contradiction the moment the player checks the door -- "Keep D12 open" is what
you mean.

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

Six actors, one person per type, the same person all session. Give each a
distinct, consistent voice -- the same person should sound like themselves in
their fifth message as in their first:
  security      clipped and procedural. States facts, gives orders, expects
                compliance. Patrols, EVA, inspections, lockdowns.
  construction  blunt and impatient. Focused on the job in front of them,
                short on courtesy when the work is waiting. Extension work,
                exterior operations.
  cargo         casual and transactional. Treats a door like a tool, not an
                event; mentions schedules and loads. Transfers, storage,
                low-priority traffic.
  medical       careful and exact, especially about time -- states durations
                and conditions precisely because a patient's safety depends on
                it. Patient transport, quarantine.
  civilian      informal, sometimes anxious or apologetic. Explains their own
                situation because they have no authority to just ask.
                Residents, researchers, routine requests.
  system        flat and automated. No opinions, no courtesy words, states the
                alarm and the required state and nothing else. Never a person.

WRITING. Most instructions are one or two short sentences: what you need, and,
if the first sentence was dense, the door and the duration said again in
different words -- not copy-pasted, a second phrasing, as insurance against
being heard only once. A reason is welcome when it is cheap: "Close D10, we're
venting the corridor" already carries one in four words and needs nothing more
added to it. The session has a fixed length and a real reading budget, so add
words only where they earn their place -- a third sentence is the exception,
not the rule. A short status update or a plain acknowledgement is one sentence,
plainly. Nobody explains the game's rules, but everybody explains their own
actions when it costs nothing to. Prose names doors as D7 / H5 and places by
the exact phrases in the layout brief. Do not invent rooms, decks, sectors or
door numbers.

A MESSAGE IS NEVER A QUESTION. Nothing in a message can be answered -- only a
Keeper challenge has a reply. "Is the reactor corridor still off-limits?" sent
as ordinary chatter dead-ends: the player cannot respond and nothing resolves
it. Say it as a report instead: "Reactor corridor is still off-limits, last I
heard." If something truly needs an answer, that is what a challenge is for.

{_PLAIN_LANGUAGE[language]}
""".strip()


#: The plain-language block (spec 13.7) is the one part of the brief that has
#: to change words, not just switch a header: its examples are idioms in the
#: target language, and an idiom in English is invisible noise to a model
#: asked to avoid idioms in French. Everything else in this file is an
#: instruction *to* the model, so it stays in English regardless of language.
_PLAIN_LANGUAGE = {
    "en": """PLAIN ENGLISH, AND THIS MATTERS MORE THAN STYLE. Most players will not be native
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

Terse, plain and a little explained are not in tension. "Door Control, Cargo.
Pallet run through D10, two minutes. Need it open for the crossing, then
closed straight after so the corridor stays sealed." is all three.""",
    "fr": """FRANÇAIS SIMPLE, ET CECI COMPTE PLUS QUE LE STYLE. La plupart des joueurs ne
sont pas francophones natifs, et un message parlé n'est entendu qu'une seule
fois, sans transcription. Donc :

  * Phrases courtes. Une instruction par phrase. Moins de vingt mots.
  * Mots courants. « Partir » plutôt que « quitter les lieux ». « Maintenant »
    plutôt que « à l'heure actuelle ».
  * AUCUNE expression idiomatique, AUCUNE figure de style. Pas « garder un œil
    dessus », pas « on est dans le rouge », pas « le temps presse », pas « à
    la dernière minute », pas « il était moins une ».
  * AUCUN argot, aucun jargon inventé. Dis « minutes », jamais « mikes ». Dis
    « immédiatement », jamais « dans la foulée ».
  * AUCUNE blague, aucun jeu de mots, aucune ironie. Un acteur peut être sec,
    inquiet ou impatient -- c'est du caractère. Rien n'a besoin d'être drôle.
  * Nomme la porte tôt dans la phrase, et une seule fois.

Concis, simple et un peu expliqué ne s'opposent pas. « Contrôle des portes,
Fret. Passage par D10, deux minutes. Il me la faut ouverte pour la traversée,
puis refermée aussitôt pour que le couloir reste isolé. » a les trois qualités
à la fois.""",
}
