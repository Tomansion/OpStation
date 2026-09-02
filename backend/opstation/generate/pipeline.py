"""The generation pipeline (spec 12.1).

    plan -> threads -> everyday traffic -> temptations -> challenges
         -> assemble -> validate -> repair (x5) -> TTS -> re-validate -> publish

Scenarios are generated offline into a bank and played deterministically. The
runtime never calls an LLM or a TTS engine.
"""
from __future__ import annotations

import json
import random
import re
import string
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..config import Difficulty, difficulty as load_difficulty, voices as load_voices
from ..models import Scenario
from .. import paths
from ..station import Station, station as load_station
from ..validator import Report, validate
from . import prompt as prompts
from .assemble import assemble
from .llm import LLM
from .plan import BeatSpec, ChallengeSpec, GroupSpec, Plan, TaskSpec, ThreadSpec
from .repair import repair
from .schedule import Scheduler

Progress = Callable[[str, str], None]

EVERYDAY_THREAD_KEY = "ev_pool"


def _noop(stage: str, message: str) -> None:
    pass


@dataclass
class GenerationResult:
    scenario: Scenario
    report: Report
    plan: Plan
    attempts: int
    log: list[str] = field(default_factory=list)
    scenario_dir: Path | None = None

    @property
    def ok(self) -> bool:
        return self.report.ok


@dataclass
class Generator:
    llm: LLM = field(default_factory=LLM)
    station: Station = field(default_factory=load_station)
    difficulty: Difficulty = field(default_factory=load_difficulty)
    progress: Progress = _noop
    log: list[str] = field(default_factory=list)

    def _say(self, stage: str, message: str) -> None:
        self.log.append(f"[{stage}] {message}")
        self.progress(stage, message)

    # ------------------------------------------------------------------ stages

    def build_plan(
        self, duration: int, *, finale: str | None, theme: str | None, threads: int, seed: int
    ) -> Plan:
        self._say("plan", "casting actors and choosing threads")
        system, user = prompts.plan_prompt(
            self.station, self.difficulty, duration, finale=finale, theme=theme, threads=threads
        )
        raw = self.llm.json(system, user)
        plan = Plan(
            name=str(raw.get("name") or "Unnamed shift"),
            duration_seconds=duration,
            actor_names={k: str(v) for k, v in (raw.get("actors") or {}).items()},
        )
        incidents = raw.get("threads") or []
        finales = [t for t in incidents if t.get("grade") == "finale"]
        if len(finales) != 1 and incidents:
            # Exactly one finale is structural (V20), so it is decided here rather
            # than hoped for.
            for t in incidents:
                t["grade"] = "ordinary"
            incidents[-1]["grade"] = "finale"
            self._say("plan", "forced exactly one finale-grade thread")
        # Ask for the maximum, not the minimum: a retraction whose target does
        # not survive conflict resolution is dropped, so asking for exactly two
        # and losing one puts the scenario under quota.
        want = self.difficulty.volumes["retractions_max"]
        marked = [t for t in incidents if t.get("carries_retraction")]
        if len(marked) != want and incidents:
            ordinary = [t for t in incidents if t.get("grade") != "finale"] or incidents
            for t in incidents:
                t["carries_retraction"] = False
            for t in ordinary[:want]:
                t["carries_retraction"] = True
            self._say("plan", f"assigned the retractions to "
                              f"{[t['key'] for t in incidents if t['carries_retraction']]}")
        self._raw_threads = incidents
        for t in incidents:
            plan.threads.append(
                ThreadSpec(
                    key=str(t["key"]),
                    title=str(t.get("title") or t["key"]),
                    catalogue_key=str(t.get("catalogue_key") or "unknown"),
                    grade=str(t.get("grade") or "ordinary"),
                    debrief_summary=str(t.get("premise") or ""),
                )
            )
        self._say("plan", f"{plan.name}: {', '.join(t.key for t in plan.threads)}")
        return plan

    def write_threads(self, plan: Plan, duration: int) -> None:
        raws = {t["key"]: t for t in self._raw_threads}
        # The bypass is taught exactly once, in the earliest thread, so that later
        # isolation obligations measure memory rather than a knowledge gap.
        teach = min(
            plan.threads,
            key=lambda t: raws.get(t.key, {}).get("opens_in_phase", 9),
            default=None,
        )
        self._say("threads", f"writing {len(plan.threads)} threads in parallel")

        # Threads are written in parallel and so cannot see each other's doors.
        # The premises from stage 1 name them, which is enough to keep two
        # threads off the same door in opposite states.
        claims = {t.key: _doors_in(raws.get(t.key, {}).get("premise", "")) for t in plan.threads}

        def one(thread: ThreadSpec):
            claimed = sorted({d for k, v in claims.items() if k != thread.key for d in v})
            system, user = prompts.beats_prompt(
                self.station, self.difficulty, duration,
                thread=raws.get(thread.key, {"key": thread.key, "title": thread.title}),
                actors=plan.actor_names,
                other_threads=[r for k, r in raws.items() if k != thread.key],
                teach_bypass=(teach is not None and thread.key == teach.key),
                claimed=claimed,
                carries_retraction=bool(raws.get(thread.key, {}).get("carries_retraction")),
                max_hold=int(0.30 * duration),
            )
            return thread, self.llm.json(system, user)

        with ThreadPoolExecutor(max_workers=4) as pool:
            for thread, raw in pool.map(one, plan.threads):
                self._absorb_beats(plan, thread, raw)
                self._say("threads", f"{thread.key}: {len(thread.beats)} beats")

        # Exactly one thread carries the dormancy the game is built to measure.
        dormant = [t for t in plan.threads if t.dormant_after]
        for extra in dormant[1:]:
            extra.dormant_after = None
        if not dormant:
            candidate = next(
                (t for t in plan.threads if t.grade == "ordinary" and len(t.beats) >= 3), None
            )
            if candidate:
                candidate.dormant_after = candidate.beats[len(candidate.beats) // 2 - 1].key
                self._say("threads", f"assigned dormancy to {candidate.key} (none declared)")

    def _absorb_beats(self, plan: Plan, thread: ThreadSpec, raw: dict) -> None:
        for g in raw.get("obligations") or []:
            thread.groups.append(
                GroupSpec(key=str(g["key"]), thread_key=thread.key,
                          label=str(g.get("label") or g["key"]))
            )
        for b in raw.get("beats") or []:
            try:
                thread.beats.append(BeatSpec.parse(b, thread.key))
            except Exception as exc:  # noqa: BLE001
                self._say("threads", f"{thread.key}: dropped malformed beat: {exc}")
        thread.dormant_after = raw.get("dormant_after") or None
        # Keep the thread's own order but make keys unique across the scenario.
        for beat in thread.beats:
            beat.key = f"{thread.key}:{beat.key}"
        for beat in thread.beats:
            beat.creates_group = _qualify(beat.creates_group, thread.key)
            beat.cancels = [_qualify(c, thread.key) for c in beat.cancels]
        for group in thread.groups:
            group.key = _qualify(group.key, thread.key)

    def write_missing_retractions(self, plan: Plan, duration: int) -> None:
        """Fill in the withdrawals the thread stage was asked for and skipped.

        Two to three retractions per scenario is a validator rule (V30), and the
        thread stage forgets one more often than not -- it is a single beat among
        eight, and the instruction competes with everything else in that prompt.
        Asking for it on its own, together with the obligation that gives it
        teeth, is both more reliable and cheaper than re-rolling a whole thread.
        """
        raws = {t["key"]: t for t in self._raw_threads}
        wanted = [
            t for t in plan.threads
            if raws.get(t.key, {}).get("carries_retraction")
            and not any(b.kind == "retraction" for b in t.beats)
        ]
        have = sum(1 for b in plan.beats if b.kind == "retraction")
        # Chased up to the MAXIMUM, not the minimum, for the same reason
        # build_plan marks retractions_max threads in the first place: more of
        # them are lost later, to a window with no room left or a target that
        # does not survive scheduling, than are lost here. Stopping at the
        # minimum leaves no margin against that second round of attrition, and
        # the scenario routinely lands under quota (V30) as a result.
        need = max(0, self.difficulty.volumes["retractions_max"] - have)
        if not wanted:
            self._say("retractions", f"{have} written by the thread stage; every marked "
                                      "thread already has one — nothing to chase")
            return
        if not need:
            self._say("retractions", f"{have} written by the thread stage already meets "
                                      "the quota — nothing to chase")
            return
        self._say("retractions", f"{have} written by the thread stage; asking for {need} more")

        for thread in wanted[:need + 1]:
            groups = [g for g in thread.groups]
            best = None
            for group in groups:
                pairs = plan.tasks_of_group(group.key)
                held = [t for _o, t in pairs if t.hold > 0]
                if not held:
                    continue
                longest = max(held, key=lambda t: t.hold)
                if best is None or longest.hold > best[1].hold:
                    best = (group, longest)
            if best is None:
                self._say("retractions", f"{thread.key}: no held obligation to withdraw")
                continue
            group, task = best
            creator = next(
                (b.actor_type for b in thread.beats if b.creates_group == group.key),
                "system",
            )
            doors = self._require_of(task)
            system, user = prompts.retraction_prompt(
                self.station, self.difficulty, duration,
                thread=raws.get(thread.key, {"key": thread.key, "title": thread.title}),
                actor=creator,
                obligation={
                    "key": group.key, "label": group.label,
                    "requires": doors, "hold_seconds": task.hold,
                    "imposed_by": creator,
                },
                beats=[
                    {"actor": b.actor_type, "kind": b.kind, "text": b.text}
                    for b in thread.beats
                ],
            )
            try:
                raw = self.llm.json(system, user)
            except Exception as exc:  # noqa: BLE001
                self._say("retractions", f"{thread.key}: could not be written ({exc})")
                continue

            withdrawal = raw.get("withdrawal") or {}
            consequence = raw.get("consequence") or {}
            if not withdrawal.get("text"):
                self._say("retractions", f"{thread.key}: no withdrawal text came back")
                continue
            thread.beats.append(BeatSpec(
                key=f"{thread.key}:withdraw",
                thread_key=thread.key,
                phase=3,
                actor_type=str(withdrawal.get("actor") or creator),
                channel=str(withdrawal.get("channel") or "radio"),
                kind="retraction",
                text=str(withdrawal["text"]).strip(),
                cancels=[group.key],
                retraction_style=str(withdrawal.get("retraction_style") or "explicit"),
            ))
            require = {
                str(k).upper(): str(v).lower()
                for k, v in (consequence.get("require") or {}).items()
                if str(v).lower() in ("open", "closed")
            }
            opposite = {d: ("open" if v == "closed" else "closed") for d, v in doors.items()}
            require = {d: v for d, v in require.items() if opposite.get(d) == v}
            if not require:
                # The model's consequence did not actually reverse anything, so
                # the reversal is taken from the graph instead. Without it the
                # withdrawal has no teeth and V29 rejects it.
                door = sorted(opposite)[0]
                require = {door: opposite[door]}
                self._say("retractions",
                          f"{thread.key}: the consequence did not reverse the door — "
                          f"using {require}")
            group_key = f"{thread.key}_after_withdrawal"
            thread.groups.append(GroupSpec(
                key=group_key, thread_key=thread.key,
                label=str(consequence.get("label") or f"Reopen {sorted(require)[0]}"),
            ))
            thread.beats.append(BeatSpec(
                key=f"{thread.key}:consequence",
                thread_key=thread.key,
                phase=4,
                actor_type=str(consequence.get("actor") or "cargo"),
                channel=str(consequence.get("channel") or "text"),
                kind="instruction",
                text=str(consequence.get("text") or
                         f"Door Control. We need {sorted(require)[0]} "
                         f"{require[sorted(require)[0]]} for a crossing."),
                creates_group=group_key,
                tasks=[TaskSpec(
                    hold=max(30, int(consequence.get("hold") or 120)),
                    fail_message=str(consequence.get("fail_message") or
                                     f"{sorted(require)[0]} was not "
                                     f"{require[sorted(require)[0]]} when it was needed."),
                    require=require,
                )],
            ))
            self._say("retractions",
                      f"{thread.key}: withdrawal of {group.label!r} plus a later {require}")

    def _require_of(self, task: TaskSpec) -> dict[str, str]:
        if task.seal_station:
            return {d.id: "closed" for d in self.station.hangar_doors}
        if task.isolation_target in self.station.isolation_targets:
            return self.station.target_cut(task.isolation_target).required(
                task.include_hangar_doors
            )
        return {k.upper(): v for k, v in task.require.items()}

    def write_everyday(self, plan: Plan, duration: int, count: int) -> None:
        # Each call is its own round. Without a round tag the model reuses ev1,
        # ev2 ... on a top-up, which collides thread ids, obligation ids and beat
        # keys -- and a collided beat key silently attaches one beat's tasks to
        # another beat's message.
        self._everyday_round = getattr(self, "_everyday_round", 0) + 1
        round_tag = "" if self._everyday_round == 1 else f"r{self._everyday_round}"
        self._say("everyday", f"writing {count} everyday exchanges")
        system, user = prompts.everyday_prompt(
            self.station, self.difficulty, duration,
            actors=plan.actor_names, threads=self._raw_threads, count=count,
        )
        raw = self.llm.json(system, user)
        taken = {t.key for t in plan.threads}
        for ex in (raw.get("exchanges") or [])[:count]:
            key = f"{ex.get('key') or f'ev{len(plan.threads)}'}{round_tag}"
            while key in taken:
                key = f"{key}x"
            taken.add(key)
            thread = ThreadSpec(
                key=key,
                title=str(ex.get("title") or key),
                catalogue_key="everyday",
                grade="everyday",
                debrief_summary=str(ex.get("title") or ""),
            )
            ob = ex.get("obligation")
            if isinstance(ob, dict) and ob.get("key"):
                thread.groups.append(
                    GroupSpec(key=_qualify(str(ob["key"]), key), thread_key=key,
                              label=str(ob.get("label") or ob["key"]))
                )
            # An everyday exchange is 1-2 messages by definition (V20); anything
            # past that is a thread wearing an exchange's clothes.
            for b in (ex.get("beats") or [])[:2]:
                try:
                    beat = BeatSpec.parse(b, key)
                except Exception as exc:  # noqa: BLE001
                    self._say("everyday", f"dropped malformed beat: {exc}")
                    continue
                beat.key = f"{key}:{beat.key}"
                beat.creates_group = _qualify(beat.creates_group, key)
                beat.cancels = [_qualify(c, key) for c in beat.cancels]
                thread.beats.append(beat)
            if thread.beats:
                plan.threads.append(thread)
        self._say("everyday", f"{sum(1 for t in plan.threads if t.grade == 'everyday')} exchanges")

    def write_temptations(self, plan: Plan, duration: int, count: int) -> None:
        """Needs a provisional schedule first: a request is only tempting if a
        hold is live when it lands, so the obligations must already have times."""
        Scheduler(plan, self.difficulty, self.station).run()
        obligations = []
        for group in plan.groups:
            windows = plan.tasks_of_group(group.key)
            doors: set[str] = set()
            longest = 0
            for beat, task in windows:
                if task.hold <= 0:
                    continue
                longest = max(longest, task.hold)
                if task.isolation_target and task.isolation_target in self.station.isolation_targets:
                    cut = self.station.target_cut(task.isolation_target)
                    doors |= set(cut.required(task.include_hangar_doors))
                else:
                    doors |= set(task.require)
            if doors and longest >= 60:
                obligations.append({
                    "key": group.key, "label": group.label, "thread": group.thread_key,
                    "doors": sorted(doors), "longest_hold_seconds": longest,
                })
        if not obligations:
            self._say("temptations", "no long holds to tempt against — skipped")
            return
        self._say("temptations", f"{count} requests against {len(obligations)} obligations")
        system, user = prompts.temptation_prompt(
            self.station, self.difficulty, duration,
            actors=plan.actor_names, obligations=obligations, count=count,
        )
        raw = self.llm.json(system, user)
        pool = ThreadSpec(
            key=EVERYDAY_THREAD_KEY, title="Requests that cannot be granted",
            catalogue_key="conflicting_requests", grade="conflicts",
            debrief_summary="Plausible requests that collided with a live obligation.",
        )
        for r in raw.get("requests") or []:
            pool.beats.append(
                BeatSpec(
                    key=f"{EVERYDAY_THREAD_KEY}:{r.get('key') or len(pool.beats)}",
                    thread_key=EVERYDAY_THREAD_KEY,
                    phase=3,
                    actor_type=str(r.get("actor") or "civilian"),
                    channel=str(r.get("channel") or "text"),
                    kind="tempting_request",
                    text=str(r.get("text") or "").strip(),
                    targets_group=str(r.get("targets") or ""),
                )
            )
        if pool.beats:
            plan.threads.append(pool)
        # Times are stale now that beats were added; the real schedule is run
        # again during assembly.
        for beat in plan.beats:
            beat.at = None if beat.pin_at is None else beat.pin_at

    def write_challenges(self, plan: Plan, duration: int) -> None:
        """Place the six questions, then write them.

        Placement happens on the real plan and before the prose, so the second a
        question is asked is a fact by the time the model writes it. That matters:
        a challenge's answer has to be derivable from what the player had already
        heard (V19), and the model can only judge that against real timestamps.
        """
        vol = self.difficulty.volumes
        plan.challenges = [
            ChallengeSpec(key=f"c{i}", slot="in_session", kind="thread", thread_key="",
                          actor_type="security", channel="text", pretext="", prompt="",
                          explanation="", options=[])
            for i in range(1, vol["challenges_in_session"] + 1)
        ] + [
            ChallengeSpec(key=f"d{i}", slot="debrief", kind="thread", thread_key="",
                          actor_type="security", channel="text", pretext="", prompt="",
                          explanation="", options=[])
            for i in range(1, vol["challenges_debrief"] + 1)
        ]
        Scheduler(plan, self.difficulty, self.station).run()

        slots = [
            {
                "slot_id": c.key,
                "slot": c.slot,
                "asked_at_seconds": c.at if c.slot == "in_session" else "after the shift, untimed",
            }
            for c in plan.challenges
        ]
        timeline = _timeline_text(plan)
        # V29 lets a retraction earn its teeth through a challenge instead of a
        # later task. That only works if the challenge stage knows the
        # retractions exist, and knows the message id to declare.
        ordered = sorted(
            (b for b in plan.beats if b.at is not None),
            key=lambda b: (b.at, b.thread_key, b.key),
        )
        numbering = {b.key: f"m_{i:03d}" for i, b in enumerate(ordered, start=1)}
        retractions = [
            {
                "message_id": numbering[b.key],
                "at_seconds": b.at,
                "actor": b.actor_type,
                "text": b.text,
                "withdrew": [
                    (plan.group(c).label if plan.group(c) else c) for c in b.cancels
                ],
            }
            for b in ordered if b.kind == "retraction"
        ]
        self._say("challenges", "writing 6 challenges; in-session slots at "
                                f"{[s['asked_at_seconds'] for s in slots if s['slot'] == 'in_session']}")
        system, user = prompts.challenge_prompt(
            self.station, self.difficulty, duration, timeline=timeline,
            actors=plan.actor_names, threads=self._raw_threads, slots=slots,
            retractions=retractions,
        )
        raw = self.llm.json(system, user)

        by_slot = {c.key: c for c in plan.challenges}
        filled = 0
        for c in raw.get("challenges") or []:
            spec = by_slot.get(str(c.get("slot_id")))
            if spec is None:
                continue
            spec.kind = str(c.get("kind") or "thread")
            spec.thread_key = str(c.get("thread") or "")
            spec.actor_type = str(c.get("actor") or "security")
            spec.channel = str(c.get("channel") or "text")
            spec.pretext = str(c.get("pretext") or "")
            spec.prompt = str(c.get("prompt") or "")
            spec.explanation = str(c.get("explanation") or "")
            spec.options = list(c.get("options") or [])
            spec.depends_on = [str(d) for d in (c.get("depends_on") or [])]
            filled += 1
        plan.challenges = [c for c in plan.challenges if c.prompt]
        self._say("challenges", f"{filled} written")
        for beat in plan.beats:
            beat.at = None if beat.pin_at is None else beat.pin_at

    # ------------------------------------------------------- normalisation

    def align_speakers(self, plan: Plan) -> None:
        """Make the speaker match the prose.

        A message that opens "Officer Ruiz here" while its `actor_id` says
        Construction is not a cosmetic mismatch. The voice is the only cue that
        identifies a speaker, and that is precisely what makes provenance
        questions answerable -- so a message spoken in one voice while naming
        another person makes "who authorised that door" unanswerable.

        The prose wins, because the prose is what the player hears.
        """
        by_name: list[tuple[str, str]] = []
        for actor_type, name in plan.actor_names.items():
            for token in (name, name.split()[-1] if name.split() else name):
                if len(token) > 3:
                    by_name.append((token.lower(), actor_type))
            by_name.append((actor_type.lower(), actor_type))

        moved = 0
        for beat in plan.beats:
            opening = beat.text[:48].lower()
            hit = min(
                ((opening.index(token), actor) for token, actor in by_name
                 if token in opening),
                default=None,
            )
            if hit is None:
                continue
            _position, actor = hit
            if actor != beat.actor_type:
                beat.actor_type = actor
                moved += 1
        if moved:
            self._say("speakers", f"aligned {moved} message(s) to the person their own "
                                  "text identifies")

    def normalise_retractions(self, plan: Plan) -> None:
        """Make every withdrawal structurally legal before the validator sees it.

        Models express "this no longer applies" as `resolution` or `supersede`
        with a `cancels` array. The intent is right and the label is wrong, and
        `cancels` only belongs on a retraction (spec 11.1), so the label is
        corrected here. Style, actor and quota are settled the same way, because
        none of it is a writing decision.
        """
        creators: dict[str, str] = {}
        for beat in plan.beats:
            if beat.creates_group:
                creators.setdefault(beat.creates_group, beat.actor_type)

        carrying = []
        for beat in plan.beats:
            beat.cancels = [c for c in (plan.resolve_group(c) for c in beat.cancels) if c]
            if beat.cancels:
                carrying.append(beat)

        for beat in carrying:
            if beat.kind != "retraction":
                self._say("retractions",
                          f"{beat.key}: kind {beat.kind!r} carried `cancels` — it is a retraction")
                beat.kind = "retraction"
            creator = next((creators.get(c) for c in beat.cancels if creators.get(c)), None)
            cues = self._cues(plan, beat)
            names_cue = any(cue.lower() in beat.text.lower() for cue in cues)
            names_someone = any(
                a.lower() in beat.text[:48].lower() for a in plan.actor_names.values()
            ) or any(t in beat.text[:48].lower() for t in plan.actor_names)
            if (creator and creator != beat.actor_type
                    and creator not in beat.text.lower() and not names_someone):
                # Nobody is named at all, so a cross-actor withdrawal would be
                # unanswerable (V28). The person who imposed it withdraws it --
                # safe only because the prose identifies no one to contradict.
                self._say("retractions",
                          f"{beat.key}: reassigned to {creator} — the text names nobody")
                beat.actor_type = creator
                creator = beat.actor_type
            if creator and creator != beat.actor_type:
                # Somebody is withdrawing another person's instruction, so
                # first-person references to it are wrong and, worse,
                # unanswerable: V28 requires the other actor to be named,
                # because provenance is the thing being tested.
                fixed = _attribute_to(beat.text, creator)
                if fixed != beat.text:
                    self._say("retractions",
                              f"{beat.key}: attributed the withdrawn instruction to "
                              f"{creator}, who gave it")
                    beat.text = fixed
                beat.retraction_style = "cross_actor"
            if beat.retraction_style not in ("explicit", "self_reference", "cross_actor", "partial"):
                if creator and creator != beat.actor_type:
                    beat.retraction_style = "cross_actor"
                elif names_cue:
                    beat.retraction_style = "explicit"
                else:
                    beat.retraction_style = "self_reference"
            if beat.retraction_style in ("self_reference", "partial") and not names_cue and cues:
                # V27: the text has to pin down WHICH obligation, and the only
                # deterministic way to do that is to say the door out loud.
                beat.text = beat.text.rstrip(". ") + f" — the hold on {cues[0]}."
                beat.retraction_style = "explicit"
                self._say("retractions", f"{beat.key}: named {cues[0]} so the withdrawal resolves")

        # The quota is NOT enforced here. A candidate whose target does not
        # survive conflict resolution is demoted during scheduling, so trimming
        # to the quota before that runs throws away the replacements and lands
        # the scenario under quota instead of over it.

    def _cues(self, plan: Plan, beat: BeatSpec) -> list[str]:
        """Doors and places that identify what a retraction is withdrawing."""
        cues: list[str] = []
        for group_key in beat.cancels:
            for _owner, task in plan.tasks_of_group(group_key):
                if task.isolation_target in self.station.isolation_targets:
                    cues.append(self.station.isolation_targets[task.isolation_target].phrase)
                cues += sorted(task.require)
        return cues

    def top_up_volume(self, plan: Plan, duration: int, target: int) -> None:
        """Ask for more everyday traffic if the session is thin.

        Beats get dropped -- by conflict resolution, by a full phase -- so the
        message target (V20) is met by asking for more rather than by relaxing
        it. The number of *exchanges* is itself capped by V20, so the top-up can
        only fill the space between the current count and that ceiling.
        """
        ceiling = self.difficulty.volumes["everyday_exchanges_max"]
        try:
            self._ask_for_more(plan, duration, target, ceiling)
        finally:
            # The exchange count is a validator rule (V20), not a preference, so
            # the ceiling is enforced on the way out no matter which path the
            # asking took.
            everyday = [t for t in plan.threads if t.grade == "everyday"]
            if len(everyday) > ceiling:
                drop = {t.key for t in everyday[ceiling:]}
                plan.threads = [t for t in plan.threads if t.key not in drop]
                self._say("volume",
                          f"trimmed {len(drop)} exchange(s) over the quota of {ceiling}")
            self._trim_to_ceiling(plan)

    def _trim_to_ceiling(self, plan: Plan) -> None:
        """Both ends of the volume rule matter (V20). Over the maximum, the
        cheapest thing to lose is the second half of an everyday exchange: it
        carries no obligation, and the exchange still reads as an exchange
        without it."""
        ceiling = self.difficulty.volumes["messages_max"]
        # The assembler adds the end-of-shift seal, so leave room for it.
        over = sum(1 for b in plan.beats if b.text) + 1 - ceiling
        if over <= 0:
            return
        spare: list[tuple[ThreadSpec, BeatSpec]] = []
        for thread in plan.threads:
            if thread.grade != "everyday":
                continue
            for beat in thread.beats[1:]:
                if not beat.tasks and not beat.cancels:
                    spare.append((thread, beat))
        for thread, beat in spare[:over]:
            thread.beats = [b for b in thread.beats if b is not beat]
        removed = min(over, len(spare))
        self._say("volume",
                  f"{over} message(s) over the maximum — dropped {removed} follow-up(s) "
                  "from everyday exchanges")
        if removed < over:
            self._say("volume", f"still {over - removed} over; nothing cheap left to cut")

    def _ask_for_more(self, plan: Plan, duration: int, target: int, ceiling: int) -> None:
        for _attempt in (1, 2):
            have = sum(1 for b in plan.beats if b.text)
            exchanges = sum(1 for t in plan.threads if t.grade == "everyday")
            if have >= target:
                return
            room = ceiling - exchanges
            if room <= 0:
                self._say("volume",
                          f"{have} messages, want {target}, but the everyday quota of "
                          f"{ceiling} exchanges is full — leaving it to the validator")
                return
            ask = min(room, max(2, (target - have + 1) // 2))
            self._say("volume", f"{have} messages, want {target} — asking for {ask} "
                                f"more exchange(s), {room} of the quota still free")
            before = len(plan.threads)
            self.write_everyday(plan, duration, ask)
            if len(plan.threads) == before:
                self._say("volume", "no further exchanges came back")
                return

    # ------------------------------------------------------------ llm repair

    def rewrite_bad_prose(self, scenario: Scenario, report: Report, duration: int) -> int:
        """Send back only what needs writing.

        Most validator errors are arithmetic and are already settled. What is
        left is prose: an invented place, an unresolvable withdrawal, a
        distractor drawn from nowhere. Those go back one item at a time with the
        errors attached, which is a far smaller and more reliable request than
        regenerating a scenario.
        """
        from .prompt import TEXT_RULES

        by_item: dict[str, list[str]] = {}
        for finding in report.errors:
            if finding.rule in TEXT_RULES and finding.where:
                by_item.setdefault(finding.where, []).append(f"{finding.rule}: {finding.message}")
        # A task-level finding is really about the message that created it.
        tasks = scenario.tasks_by_id
        remapped: dict[str, list[str]] = {}
        for where, errors in by_item.items():
            target = tasks[where].message_id if where in tasks else where
            remapped.setdefault(target, []).extend(errors)

        messages = scenario.messages_by_id
        challenges = {c.id: c for c in scenario.all_challenges}
        items = []
        for item_id, errors in sorted(remapped.items()):
            if item_id in messages:
                msg = messages[item_id]
                items.append({
                    "id": item_id, "kind": "message",
                    "speaker": scenario.actors_by_id[msg.actor_id].type,
                    "text": msg.text, "errors": errors,
                })
            elif item_id in challenges:
                ch = challenges[item_id]
                items.append({
                    "id": item_id, "kind": "challenge",
                    "asker": scenario.actors_by_id[ch.actor_id].type,
                    "prompt": ch.prompt, "explanation": ch.explanation,
                    "options": [{"text": o.text, "correct": o.correct} for o in ch.options],
                    "errors": errors,
                })
        if not items:
            return 0

        self._say("rewrite", f"asking for {len(items)} item(s) to be rewritten")
        system, user = prompts.rewrite_prompt(
            self.station, self.difficulty, duration, items=items
        )
        try:
            raw = self.llm.json(system, user)
        except Exception as exc:  # noqa: BLE001 - a failed rewrite is not fatal
            self._say("rewrite", f"failed: {exc}")
            return 0

        changed = 0
        for entry in raw.get("items") or []:
            item_id = str(entry.get("id"))
            if item_id in messages and entry.get("text"):
                messages[item_id].text = str(entry["text"]).strip()
                messages[item_id].read_cost = (
                    self.difficulty.read_cost(messages[item_id].text)
                    if messages[item_id].channel == "text" else messages[item_id].read_cost
                )
                changed += 1
            elif item_id in challenges:
                ch = challenges[item_id]
                if entry.get("prompt"):
                    ch.prompt = str(entry["prompt"]).strip()
                if entry.get("explanation"):
                    ch.explanation = str(entry["explanation"]).strip()
                options = entry.get("options")
                if isinstance(options, list) and len(options) == 4:
                    from ..models import Option

                    ch.options = [
                        Option(id=f"o{i}", text=str(o.get("text", "")).strip(),
                               correct=bool(o.get("correct")))
                        for i, o in enumerate(options, start=1)
                    ]
                changed += 1
        self._say("rewrite", f"{changed} item(s) rewritten")
        return changed

    # ---------------------------------------------------------------- assembly

    def generate(
        self,
        *,
        duration: int = 1620,
        finale: str | None = None,
        theme: str | None = None,
        threads: int = 5,
        seed: int | None = None,
        everyday: int | None = None,
        temptations: int = 4,
        scenario_id: str | None = None,
    ) -> GenerationResult:
        seed = seed if seed is not None else random.randrange(1, 10_000)
        rng = random.Random(seed)
        scenario_id = scenario_id or _new_id(rng)
        vol = self.difficulty.volumes
        everyday = everyday or vol["everyday_exchanges_max"]

        plan = self.build_plan(duration, finale=finale, theme=theme, threads=threads, seed=seed)
        self.write_threads(plan, duration)
        self.write_missing_retractions(plan, duration)
        self.write_everyday(plan, duration, everyday)
        self.write_temptations(plan, duration, temptations)
        self.align_speakers(plan)
        self.normalise_retractions(plan)
        # Targeted a bit above the minimum, not just past it: scheduling has
        # not run yet, and V15 drops, "no room" drops and conflict resolution
        # all still lie ahead. A target that only clears the minimum leaves no
        # margin against that attrition, and the scenario routinely lands
        # under quota (V20) as a result -- the same reasoning as the
        # retraction top-up above. `top_up_volume` still trims back down to
        # `messages_max` on the way out, so overshooting here is harmless on
        # its own -- but pushed too far it crowds the session enough that
        # retraction targets lose their live window before `_place_retractions`
        # ever runs, trading a V20 shortfall for a V30 one. +10 is a
        # deliberately smaller margin than the first attempt at this (+15).
        self.top_up_volume(plan, duration, vol["messages_min"] + 10)
        self.write_challenges(plan, duration)

        scenario, schedule = assemble(
            plan, station=self.station, difficulty=self.difficulty,
            scenario_id=scenario_id, model=self.llm.model, seed=seed,
        )
        for note in schedule.notes:
            self.log.append(f"[schedule] {note}")

        report = validate(scenario, station=self.station, difficulty=self.difficulty)
        self._say("validate", report.summary())

        attempts = 0
        limit = int(self.difficulty["generator_repair_attempts"])
        while not report.ok and attempts < limit:
            attempts += 1
            fixed = repair(scenario, report, self.station)
            for line in fixed:
                self._say("repair", line)
            rewritten = self.rewrite_bad_prose(scenario, report, duration)
            if not fixed and not rewritten:
                self._say("repair", f"attempt {attempts}: nothing a repair pass can reach")
                break
            report = validate(scenario, station=self.station, difficulty=self.difficulty)
            self._say("repair", f"attempt {attempts}: {report.summary()}")

        scenario.generator.attempts = attempts
        scenario.generator.prompt_tokens = self.llm.usage.prompt_tokens
        scenario.generator.completion_tokens = self.llm.usage.completion_tokens
        scenario.status = "valid" if report.ok else "invalid"
        return GenerationResult(
            scenario=scenario, report=report, plan=plan, attempts=attempts, log=list(self.log)
        )


DOOR_IN_TEXT = re.compile(r"\b([DH])\s?-?(\d{1,2})\b")

#: First-person references to an instruction, for the case where the speaker is
#: withdrawing somebody else's.
_FIRST_PERSON = (
    ("what i said", "what {who} said"),
    ("what i told you", "what {who} told you"),
    ("what i asked", "what {who} asked"),
    ("what i asked for", "what {who} asked for"),
    ("my earlier instruction", "{who}'s earlier instruction"),
    ("my instruction", "{who}'s instruction"),
    ("my earlier request", "{who}'s earlier request"),
    ("my request", "{who}'s request"),
    ("my hold", "{who}'s hold"),
    ("i asked you earlier", "{who} asked you earlier"),
)


def _attribute_to(text: str, creator: str) -> str:
    """Rewrite a first-person reference so it names whoever gave the order."""
    who = creator.title()
    low = text.lower()
    for pattern, replacement in _FIRST_PERSON:
        index = low.find(pattern)
        if index == -1:
            continue
        return text[:index] + replacement.format(who=who) + text[index + len(pattern):]
    return text


def _doors_in(text: str) -> set[str]:
    return {f"{m.group(1).upper()}{int(m.group(2))}" for m in DOOR_IN_TEXT.finditer(text or "")}


def _qualify(key: str | None, thread_key: str) -> str | None:
    """Namespace an obligation key to its thread.

    Group keys are only unique inside a thread. The model's own `og_` prefix is
    stripped first and re-added at assembly, so an id reads `og_ext_vent` rather
    than `og_ext__og_ext_vent`.
    """
    if not key:
        return None
    bare = key[3:] if key.startswith("og_") else key
    if bare == thread_key or bare.startswith(f"{thread_key}_"):
        return bare
    return f"{thread_key}_{bare}"


def _timeline_text(plan: Plan) -> str:
    """The timeline the challenge stage reasons over. Message numbers here are
    the same ones assembly will assign, because both sort by delivery time."""
    rows = []
    ordered = sorted(
        (b for b in plan.beats if b.at is not None), key=lambda b: (b.at, b.thread_key, b.key)
    )
    for index, beat in enumerate(ordered, start=1):
        mm, ss = divmod(int(beat.at), 60)
        thread = plan.thread_of(beat.thread_key)
        obligations = ""
        if beat.creates_group:
            group = plan.group(beat.creates_group)
            obligations = f"  [creates: {group.label if group else beat.creates_group}]"
        if beat.cancels:
            obligations += f"  [cancels: {', '.join(beat.cancels)}]"
        rows.append(
            f"m_{index:03d}  {mm:02d}:{ss:02d}  {beat.actor_type:<13}"
            f"{(thread.title if thread else beat.thread_key)[:28]:<30}"
            f"{beat.kind:<17}{beat.text}{obligations}"
        )
    return "\n".join(rows)


def _new_id(rng: random.Random) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    tag = "".join(rng.choice(string.ascii_lowercase) for _ in range(4))
    return f"sc_{stamp}_{tag}"


def publish(result: GenerationResult, root: Path | None = None) -> Path:
    """Write the scenario and its validator report into the bank."""
    root = root or paths.SCENARIOS_DIR
    directory = root / result.scenario.scenario_id
    (directory / "audio").mkdir(parents=True, exist_ok=True)
    result.scenario.dump(directory / "scenario.json")
    result.report.dump(directory / "validation.json")
    (directory / "generation.log").write_text("\n".join(result.log) + "\n", encoding="utf-8")
    result.scenario_dir = directory
    return directory
