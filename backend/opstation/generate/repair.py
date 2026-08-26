"""Deterministic repairs.

Some validator errors have exactly one sensible fix and no judgement in them. It
is wasteful and unreliable to ask a language model to make an arithmetic
correction, so those are applied here before any LLM repair attempt, and the LLM
only ever sees what actually needs writing.

Every repair is logged. A silent fix would hide a generator bug.
"""
from __future__ import annotations

import math

from ..models import Scenario
from ..station import Station
from ..validator import Report


def repair(scenario: Scenario, report: Report, station: Station) -> list[str]:
    """Mutate `scenario` in place. Returns a log of what was changed."""
    log: list[str] = []
    by_rule: dict[str, list] = {}
    for finding in report.errors:
        by_rule.setdefault(finding.rule, []).append(finding)

    log += _drop_free_pass_tasks(scenario, by_rule.get("V15", []))
    log += _drop_redundant_tasks(scenario, by_rule.get("V16", []))
    log += _fix_derived_requires(scenario, station)
    log += _drop_toothless_temptations(scenario, by_rule.get("V17", []))
    log += _drop_dead_cancels(scenario, by_rule.get("V26", []))
    log += _fix_challenge_dependencies(scenario)
    log += _demote_toothless_retractions(scenario, by_rule.get("V29", []))
    log += _renumber(scenario)
    return log


def _fix_challenge_dependencies(scenario: Scenario) -> list[str]:
    """V19: a question's answer must be derivable from what the player has
    already heard.

    When a challenge declares evidence that arrives after it, moving the question
    later is the fix that keeps the author's intent -- the question is good, it
    was simply asked too early. Only if there is no legal slot left is the
    offending dependency dropped instead.
    """
    from ..config import difficulty as load_difficulty

    diff = load_difficulty()
    clearance = int(diff["challenge_task_clearance_seconds"])
    duration = scenario.duration_seconds
    by_id = scenario.messages_by_id
    log: list[str] = []

    boundaries = [b for t in scenario.tasks for b in (t.at, t.until)]

    def legal(at: int, others: list[int]) -> bool:
        if at < 0.5 * duration or at > duration - 30:
            return False
        if any(abs(at - b) < clearance for b in boundaries):
            return False
        return all(abs(at - other) >= 125 for other in others)

    for challenge in scenario.challenges:
        needed = [by_id[d].at for d in challenge.depends_on if d in by_id]
        latest = max(needed, default=None)
        if latest is None or latest < challenge.at:
            continue
        others = [c.at for c in scenario.challenges if c.id != challenge.id]
        moved = next(
            (at for at in range(latest + clearance, duration - 30) if legal(at, others)),
            None,
        )
        if moved is not None:
            log.append(
                f"V19: moved {challenge.id} from {challenge.at}s to {moved}s, after the "
                f"{len(needed)} message(s) its answer depends on"
            )
            challenge.at = moved
            continue
        late = [d for d in challenge.depends_on if d in by_id and by_id[d].at >= challenge.at]
        challenge.depends_on = [d for d in challenge.depends_on if d not in late]
        log.append(
            f"V19: {challenge.id} claimed to depend on {late}, which arrive after it, and "
            "there is no later slot — the claim was dropped"
        )
    return log


def _drop_free_pass_tasks(scenario: Scenario, findings) -> list[str]:
    """V15: an instantaneous task asking for a state that already holds is a
    silent free pass. There is nothing to rewrite -- the obligation does not
    exist -- so it is removed."""
    ids = {f.where for f in findings if f.where}
    if not ids:
        return []
    scenario.tasks = [t for t in scenario.tasks if t.id not in ids]
    return [f"V15: dropped {len(ids)} task(s) that asked for an already-true state: {sorted(ids)}"]


def _drop_redundant_tasks(scenario: Scenario, findings) -> list[str]:
    ids = {f.where for f in findings if f.where}
    if not ids:
        return []
    scenario.tasks = [t for t in scenario.tasks if t.id not in ids]
    return [f"V16: dropped {len(ids)} redundant re-requirement(s): {sorted(ids)}"]


def _fix_derived_requires(scenario: Scenario, station: Station) -> list[str]:
    """V23: the cut-set is computed from the graph, so a mismatch is always the
    scenario's error and the graph's answer is always right."""
    log: list[str] = []
    for task in scenario.tasks:
        if task.derived_from is None:
            continue
        target = task.derived_from.isolation_target
        if target not in station.isolation_targets:
            continue
        want = station.target_cut(target).required(task.derived_from.include_hangar_doors)
        if task.require != want:
            log.append(
                f"V23: {task.id} require {sorted(task.require)} -> {sorted(want)} "
                f"(recomputed from the door graph for {target!r})"
            )
            task.require = want
    return log


def _drop_toothless_temptations(scenario: Scenario, findings) -> list[str]:
    """A tempting request with nothing to pull against is noise pretending to be
    a dilemma. Demoting it to `chatter` keeps the reading load it contributes
    while removing the false claim about what it is."""
    ids = {f.where for f in findings if f.where}
    log: list[str] = []
    for msg in scenario.messages:
        if msg.id in ids and msg.kind == "tempting_request":
            msg.kind = "chatter"
            log.append(f"V17: {msg.id} had no live hold to pull against — demoted to chatter")
    return log


def _drop_dead_cancels(scenario: Scenario, findings) -> list[str]:
    """V26: cancelling something already finished is a no-op the player cannot
    notice. The retraction becomes a plain status message."""
    ids = {f.where for f in findings if f.where}
    log: list[str] = []
    for msg in scenario.messages:
        if msg.id in ids and msg.kind == "retraction":
            msg.kind = "status"
            msg.cancels = []
            msg.retraction_style = None
            log.append(f"V26: {msg.id} cancelled nothing live — demoted to status")
    return log


def _demote_toothless_retractions(scenario: Scenario, findings) -> list[str]:
    """V29: a retraction with no consequence is decoration, so it stops being a
    retraction.

    Only while the quota allows it (V30). If demoting one would drop the
    scenario below the minimum, the finding stands and the generator has to be
    asked again -- silently keeping a decorative withdrawal would be worse than
    an honest rejection.
    """
    from ..config import difficulty as load_difficulty

    minimum = load_difficulty().volumes["retractions_min"]
    flagged = [f.where for f in findings if f.where]
    log: list[str] = []
    for message_id in flagged:
        current = scenario.retractions()
        if len(current) <= minimum:
            log.append(
                f"V29: {message_id} has no teeth, but demoting it would leave only "
                f"{len(current) - 1} retractions and the minimum is {minimum}"
            )
            break
        message = scenario.messages_by_id.get(message_id)
        if message is None or message.kind != "retraction":
            continue
        message.kind = "status"
        message.cancels = []
        message.retraction_style = None
        log.append(
            f"V29: {message_id} withdrew something nothing later depended on — "
            "demoted to an ordinary status message"
        )
    return log


def _renumber(scenario: Scenario) -> list[str]:
    """Keep messages sorted and ids in timeline order after any edit (V2)."""
    ordered = sorted(scenario.messages, key=lambda m: (m.at, m.id))
    if [m.id for m in scenario.messages] == [m.id for m in ordered]:
        return []
    scenario.messages = ordered
    return ["V2: re-sorted messages by delivery time"]


def reflow_for_audio(scenario: Scenario) -> list[str]:
    """Settle the schedule against the real audio: density first, then slack."""
    log = _relieve_density(scenario)
    log += _restore_read_slack(scenario)
    return log


def _relieve_density(scenario: Scenario) -> list[str]:
    """Thin out any window where the real audio pushed reading over budget (V8).

    Only ever moves a message later, and only the last one in the offending
    window, so the order the player hears things in is preserved.
    """
    from ..config import difficulty as load_difficulty, phase_at

    diff = load_difficulty()
    window = float(diff["read_budget_window_seconds"])
    gap = int(diff["min_message_gap_seconds"])
    ceiling = scenario.duration_seconds - 40
    log: list[str] = []

    def cost_of(item) -> float:
        if hasattr(item, "prompt"):
            return diff.read_cost(item.prompt, getattr(item, "audio_duration", None))
        return item.read_cost if item.read_cost is not None else diff.read_cost(
            item.text, item.audio_duration
        )

    items = list(scenario.messages) + list(scenario.challenges)
    for _ in range(400):
        items.sort(key=lambda i: i.at)
        offender = None
        for index, start in enumerate(i.at for i in items):
            inside = [i for i in items[index:] if i.at < start + window]
            total = sum(cost_of(i) for i in inside)
            budget = diff.read_budget_for_phase(phase_at(start, scenario.duration_seconds))
            if total > budget + 1e-6 and len(inside) > 1:
                offender = (start, inside, total, budget)
                break
        if offender is None:
            break
        start, inside, total, budget = offender
        # Move the last arrival out of the window rather than the first: the
        # earlier messages are the ones later obligations were timed against.
        last = max(inside, key=lambda i: i.at)
        target = int(start + window)
        others = [i.at for i in items if i is not last]
        while any(abs(target - other) < gap for other in others) and target < ceiling:
            target += 1
        if target > ceiling or target <= last.at:
            log.append(
                f"V8: {total:.1f}s of reading in the window from {start}s exceeds "
                f"{budget}s and there is no room left to spread it"
            )
            break
        log.append(
            f"V8: moved {last.id} {last.at}s -> {target}s; the window from {start}s held "
            f"{total:.1f}s of reading against a budget of {budget}s"
        )
        last.at = target
    return log


def _restore_read_slack(scenario: Scenario) -> list[str]:
    """Re-settle obligation times against the real audio durations.

    `read_cost` for a spoken message is its true length plus the acknowledgement
    overhead, and that is only known after rendering. The pre-TTS estimate is
    deliberately generous, but a message that comes back a second longer than
    predicted leaves its own obligation starting too early (V7). Pushing the
    obligation later by exactly the shortfall is precise, and cheaper than
    padding every schedule to cover the worst case.
    """
    from ..config import difficulty as load_difficulty

    diff = load_difficulty()
    slack = int(diff["task_slack_after_message_seconds"])
    tail = 5
    log: list[str] = []
    by_message: dict[str, list] = {}
    for task in scenario.tasks:
        by_message.setdefault(task.message_id, []).append(task)

    for message in scenario.messages:
        tasks = by_message.get(message.id)
        if not tasks:
            continue
        cost = message.read_cost
        if cost is None:
            cost = diff.read_cost(message.text, message.audio_duration)
        earliest = math.ceil(message.at + cost + slack)
        shortfall = earliest - min(t.at for t in tasks)
        if shortfall <= 0:
            continue
        for task in tasks:
            new_at = task.at + shortfall
            if new_at + task.hold > scenario.duration_seconds - tail:
                new_at = max(earliest, scenario.duration_seconds - tail - task.hold)
            if new_at + task.hold > scenario.duration_seconds - tail:
                log.append(
                    f"V7: {task.id} cannot fit after {message.id}'s real audio "
                    f"({cost:.1f}s) — dropped"
                )
                scenario.tasks = [t for t in scenario.tasks if t.id != task.id]
                continue
            log.append(
                f"V7: {task.id} moved {task.at}s -> {new_at}s; {message.id} turned out "
                f"{cost:.1f}s long"
            )
            task.at = new_at
    return log
