"""Validator findings and report.

The validator's output is not an exception. It is a report the generator feeds
back to the LLM for repair (spec 12.1), so every finding has to name the rule,
point at the offending object, and say what would fix it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str
    where: str | None = None
    severity: str = "error"  # "error" blocks publication; "warning" does not

    def __str__(self) -> str:
        at = f" [{self.where}]" if self.where else ""
        return f"{self.rule}{at}: {self.message}"


@dataclass
class Report:
    scenario_id: str
    findings: list[Finding] = field(default_factory=list)
    simulation: dict = field(default_factory=dict)
    difficulty_fingerprint: dict = field(default_factory=dict)
    station_version: str = ""
    rules_run: list[str] = field(default_factory=list)
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def failed_rules(self) -> list[str]:
        seen: list[str] = []
        for f in self.errors:
            if f.rule not in seen:
                seen.append(f.rule)
        return sorted(seen, key=lambda r: int(r[1:]))

    def add(self, findings: Iterable[Finding]) -> None:
        self.findings.extend(findings)

    def as_json(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "ok": self.ok,
            "checked_at": self.checked_at,
            "station_version": self.station_version,
            "rules_run": self.rules_run,
            "failed_rules": self.failed_rules(),
            "errors": [
                {"rule": f.rule, "where": f.where, "message": f.message} for f in self.errors
            ],
            "warnings": [
                {"rule": f.rule, "where": f.where, "message": f.message} for f in self.warnings
            ],
            "stats": self.stats,
            "difficulty_fingerprint": self.difficulty_fingerprint,
            "simulation": self.simulation,
        }

    def dump(self, path: Path) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.as_json(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def for_llm(self) -> str:
        """The repair prompt's payload: every error at once, so one attempt can
        fix them all (spec 12.1)."""
        if self.ok:
            return "No errors."
        lines = [f"{len(self.errors)} validator errors must be fixed:"]
        lines += [f"- {f}" for f in self.errors]
        if self.warnings:
            lines.append("")
            lines.append("Warnings (fix if easy, they do not block publication):")
            lines += [f"- {f}" for f in self.warnings]
        return "\n".join(lines)

    def summary(self) -> str:
        if self.ok:
            return f"PASS ({len(self.warnings)} warnings)"
        return f"FAIL — {len(self.errors)} errors in {', '.join(self.failed_rules())}"
