"""The station door graph.

`station/station.json` is the single source of truth for the layout (spec 3.1).
This module turns it into a graph and recomputes every isolation cut-set from
that graph, so an instruction that names a place and the task that names doors
can never disagree (validator V23).

Nothing here is scenario-specific. The layout is fixed forever.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .paths import STATION_FILE

#: Areas outside the pressurised station. Hangar doors lead to one of these.
OUTSIDE = frozenset({"SPACE", "EPSILON"})


class StationError(ValueError):
    """The layout file is internally inconsistent."""


@dataclass(frozen=True)
class Door:
    id: str
    kind: str  # "internal" | "hangar"
    between: tuple[str, str]
    initial: str  # "open" | "closed"

    @property
    def is_hangar(self) -> bool:
        return self.kind == "hangar"

    def other_side(self, area: str) -> str:
        a, b = self.between
        return b if area == a else a

    def station_side(self) -> str:
        """For a hangar door, the area inside the station."""
        return next(a for a in self.between if a not in OUTSIDE)


@dataclass(frozen=True)
class Passage:
    """A permanent doorless opening. It can never be closed, which is what
    makes Storage and the Observation Deck impossible to seal alone."""

    id: str
    between: tuple[str, str]


@dataclass(frozen=True)
class Cut:
    """The doors that seal a volume, and the ones that must be left alone."""

    volume: frozenset[str]
    cut: tuple[str, ...]
    interior_doors: tuple[str, ...]
    hangar_doors_inside: tuple[str, ...]
    blocking_passages: tuple[str, ...] = ()

    @property
    def sealable(self) -> bool:
        return not self.blocking_passages

    def required(self, include_hangar_doors: bool) -> dict[str, str]:
        """The `require` map a derived task must carry (spec 6.8): the cut only,
        never the volume's interior doors, plus hangar doors when the fiction
        concerns pressure."""
        doors = list(self.cut)
        if include_hangar_doors:
            doors += list(self.hangar_doors_inside)
        return {d: "closed" for d in doors}


@dataclass
class IsolationTarget:
    id: str
    phrase: str
    volume: tuple[str, ...]
    cut: tuple[str, ...]
    hangar_doors_inside: tuple[str, ...]
    interior_doors: tuple[str, ...]
    cls: str  # "sector" | "room" | "bay" | "corridor"


@dataclass
class Station:
    version: str
    name: str
    areas: dict[str, dict]
    doors: dict[str, Door]
    passages: dict[str, Passage]
    isolation_targets: dict[str, IsolationTarget]
    not_isolable: frozenset[str]
    hangar_roles: dict[str, str]
    raw: dict = field(repr=False, default_factory=dict)

    # ---------------------------------------------------------------- loading

    @classmethod
    def load(cls, path: Path | None = None) -> "Station":
        raw = json.loads((path or STATION_FILE).read_text(encoding="utf-8"))
        doors = {
            d["id"]: Door(
                id=d["id"],
                kind=d["kind"],
                between=(d["between"][0], d["between"][1]),
                initial=d["initial"],
            )
            for d in raw["doors"]
        }
        passages = {
            p["id"]: Passage(id=p["id"], between=(p["between"][0], p["between"][1]))
            for p in raw.get("passages", [])
        }
        targets = {
            t["id"]: IsolationTarget(
                id=t["id"],
                phrase=t["phrase"],
                volume=tuple(t["volume"]),
                cut=tuple(t["cut"]),
                hangar_doors_inside=tuple(t.get("hangar_doors_inside", [])),
                interior_doors=tuple(t.get("interior_doors", [])),
                cls=t["class"],
            )
            for t in raw["isolation_targets"]
        }
        station = cls(
            version=raw["version"],
            name=raw["name"],
            areas={a["id"]: a for a in raw["areas"]},
            doors=doors,
            passages=passages,
            isolation_targets=targets,
            not_isolable=frozenset(raw["not_isolable"]["areas"]),
            hangar_roles=dict(raw.get("hangar_roles", {})),
            raw=raw,
        )
        station.self_check()
        return station

    # ------------------------------------------------------------ basic views

    @property
    def internal_doors(self) -> list[Door]:
        return [d for d in self.doors.values() if not d.is_hangar]

    @property
    def hangar_doors(self) -> list[Door]:
        return [d for d in self.doors.values() if d.is_hangar]

    @property
    def door_ids(self) -> list[str]:
        return list(self.doors)

    def initial_states(self) -> dict[str, str]:
        """Door states at session start (spec 3.4). Fixed by the station
        definition, identical in every scenario -- never a per-scenario field."""
        return {d.id: d.initial for d in self.doors.values()}

    def area_name(self, area_id: str) -> str:
        """The canvas label."""
        return self.areas[area_id]["name"] if area_id in self.areas else area_id

    def area_prose(self, area_id: str) -> str:
        """How an actor says the place out loud. This is what message text is
        matched against, so it is data rather than a guess at joining `name`
        and `sub` -- those two are canvas label lines."""
        area = self.areas.get(area_id)
        return area["prose"] if area else area_id

    def doors_of(self, area_id: str) -> list[Door]:
        return [d for d in self.doors.values() if area_id in d.between]

    # ------------------------------------------------------------- graph work

    def neighbours(self, area_id: str, *, closed: frozenset[str] = frozenset()) -> set[str]:
        """Areas reachable in one step, ignoring doors in `closed`. Passages are
        never closable so they are always traversable."""
        out: set[str] = set()
        for d in self.doors.values():
            if area_id in d.between and d.id not in closed:
                out.add(d.other_side(area_id))
        for p in self.passages.values():
            if area_id in p.between:
                out.add(p.between[1] if area_id == p.between[0] else p.between[0])
        return out - OUTSIDE

    def is_connected(self, volume: frozenset[str]) -> bool:
        """Is the volume one contiguous space? A named target that is two
        disjoint blobs would produce a cut-set that seals neither."""
        if not volume:
            return False
        seen = {next(iter(volume))}
        stack = [next(iter(volume))]
        while stack:
            for nxt in self.neighbours(stack.pop()):
                if nxt in volume and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return seen == set(volume)

    def compute_cut(self, volume: set[str] | frozenset[str]) -> Cut:
        """Derive from the door graph which doors bound a volume.

        The distinction that reads as a bug until it is drawn (spec 3.5):
        sealing a place closes its *boundary*, not everything inside it. A door
        with both ends in the volume is interior and stays open.
        """
        vol = frozenset(volume)
        unknown = vol - set(self.areas)
        if unknown:
            raise StationError(f"unknown areas in volume: {sorted(unknown)}")

        cut: list[str] = []
        interior: list[str] = []
        hangar_inside: list[str] = []
        for door in self.doors.values():
            if door.is_hangar:
                if door.station_side() in vol:
                    hangar_inside.append(door.id)
                continue
            inside = sum(1 for a in door.between if a in vol)
            if inside == 1:
                cut.append(door.id)
            elif inside == 2:
                interior.append(door.id)

        blocking = [
            p.id for p in self.passages.values()
            if sum(1 for a in p.between if a in vol) == 1
        ]
        return Cut(
            volume=vol,
            cut=tuple(sorted(cut, key=door_sort_key)),
            interior_doors=tuple(sorted(interior, key=door_sort_key)),
            hangar_doors_inside=tuple(sorted(hangar_inside, key=door_sort_key)),
            blocking_passages=tuple(sorted(blocking)),
        )

    def target_cut(self, target_id: str) -> Cut:
        """Recompute a named target's cut from the graph -- never read it back
        from the file. This is what makes the map load-bearing (V23)."""
        target = self.isolation_targets.get(target_id)
        if target is None:
            raise StationError(f"unknown isolation target: {target_id!r}")
        return self.compute_cut(set(target.volume))

    def sealable_alone(self, area_id: str) -> bool:
        return self.compute_cut({area_id}).sealable

    def smallest_volume_containing(self, area_id: str) -> IsolationTarget | None:
        """For an area that cannot be sealed alone, the target the generator
        must name instead."""
        candidates = [
            t for t in self.isolation_targets.values() if area_id in t.volume
        ]
        return min(candidates, key=lambda t: len(t.volume), default=None)

    # ---------------------------------------------------------- vocabulary

    def phrases(self) -> dict[str, str]:
        """Every place-name the fiction may use -> the id it resolves to (V25)."""
        out = {t.phrase.lower(): t.id for t in self.isolation_targets.values()}
        for area_id, area in self.areas.items():
            out[area["name"].lower()] = area_id
            out[area["prose"].lower()] = area_id
            if area.get("sub"):
                out[area["sub"].lower()] = area_id
        return out

    # ---------------------------------------------------------- consistency

    def self_check(self) -> None:
        """Assert the file agrees with its own graph. Runs on every load: a
        hand-edit that breaks a cut-set should fail loudly and immediately."""
        problems: list[str] = []

        for area_id, area in self.areas.items():
            if not area.get("prose"):
                problems.append(f"{area_id}: no `prose` name for the fiction to use")

        for door in self.doors.values():
            if door.initial not in ("open", "closed"):
                problems.append(f"{door.id}: bad initial state {door.initial!r}")
            for area in door.between:
                if area not in self.areas and area not in OUTSIDE:
                    problems.append(f"{door.id}: unknown area {area!r}")
            if door.is_hangar and not any(a in OUTSIDE for a in door.between):
                problems.append(f"{door.id}: hangar door with no exterior side")
            if not door.is_hangar and any(a in OUTSIDE for a in door.between):
                problems.append(f"{door.id}: internal door touching {OUTSIDE}")

        for target in self.isolation_targets.values():
            got = self.compute_cut(set(target.volume))
            if got.cut != tuple(sorted(target.cut, key=door_sort_key)):
                problems.append(
                    f"{target.id}: cut is {list(got.cut)}, file says {list(target.cut)}"
                )
            if got.interior_doors != tuple(sorted(target.interior_doors, key=door_sort_key)):
                problems.append(
                    f"{target.id}: interior is {list(got.interior_doors)}, "
                    f"file says {list(target.interior_doors)}"
                )
            if got.hangar_doors_inside != tuple(
                sorted(target.hangar_doors_inside, key=door_sort_key)
            ):
                problems.append(
                    f"{target.id}: hangar doors inside are {list(got.hangar_doors_inside)}, "
                    f"file says {list(target.hangar_doors_inside)}"
                )
            if not got.sealable:
                problems.append(
                    f"{target.id}: not sealable -- passages {list(got.blocking_passages)} "
                    "cross its boundary"
                )
            if not self.is_connected(frozenset(target.volume)):
                problems.append(f"{target.id}: volume is not contiguous")
            if target.cls not in ("sector", "room", "bay", "corridor"):
                problems.append(f"{target.id}: unknown class {target.cls!r}")
            expected_cls = "sector" if len(target.volume) > 1 else None
            if expected_cls and target.cls != "sector":
                problems.append(
                    f"{target.id}: spans {len(target.volume)} areas so it is a sector, "
                    f"not {target.cls!r}"
                )
            if len(target.volume) == 1 and target.cls == "sector":
                problems.append(f"{target.id}: single area cannot be a sector")

        declared = self.not_isolable
        actual = {a for a in self.areas if not self.sealable_alone(a)}
        if declared != actual:
            problems.append(
                f"not_isolable lists {sorted(declared)} but the graph says {sorted(actual)}"
            )

        if problems:
            raise StationError(
                "station.json is inconsistent with its own door graph:\n  - "
                + "\n  - ".join(problems)
            )


def door_sort_key(door_id: str) -> tuple[str, int]:
    """D2 before D10, and every D before every H."""
    return (door_id[0], int(door_id[1:]))


@lru_cache(maxsize=1)
def station() -> Station:
    """The process-wide station. Loaded once; the layout never changes."""
    return Station.load()
