"""The station graph is load-bearing: the generator, the validator, the renderer
and the printed handbook all derive from it."""
from opstation.station import Station, StationError


def test_self_check_passes_on_the_real_layout(station):
    station.self_check()  # would raise


def test_all_seventeen_targets_recompute_from_the_graph(station):
    assert len(station.isolation_targets) == 17
    for target in station.isolation_targets.values():
        cut = station.target_cut(target.id)
        assert cut.cut == tuple(target.cut)
        assert cut.interior_doors == tuple(target.interior_doors)
        assert cut.hangar_doors_inside == tuple(target.hangar_doors_inside)


def test_hangar_bay_3_bypass_forces_a_second_door(station):
    """The layout's most valuable trap: sealing the service sector takes D7 AND
    D9, because Hangar Bay 3 bridges C2 and C3. The plausible answer is one door
    short."""
    cut = station.target_cut("service_sector")
    assert cut.cut == ("D7", "D9")
    assert "D9" in cut.cut


def test_interior_doors_stay_open(station):
    """Sealing a place closes its boundary, not everything inside it."""
    cut = station.target_cut("service_sector")
    assert set(cut.interior_doors) == {"D10", "D11", "D12", "D13"}
    assert not set(cut.cut) & set(cut.interior_doors)
    assert cut.required(include_hangar_doors=False) == {"D7": "closed", "D9": "closed"}


def test_nested_sector_needs_more_doors(station):
    """construction_sector is inside service_sector yet needs more doors, because
    excluding Engineering and Hangar Bay 4 turns their corridor doors into
    boundary doors."""
    inner = station.target_cut("construction_sector")
    outer = station.target_cut("service_sector")
    assert set(inner.volume) < set(outer.volume)
    assert len(inner.cut) > len(outer.cut)
    assert set(inner.cut) == {"D7", "D9", "D10", "D12"}


def test_doorless_places_cannot_be_sealed_alone(station):
    for area in ("STO", "C3", "OBS", "LQ"):
        assert not station.sealable_alone(area)
    assert station.smallest_volume_containing("OBS").id == "residential_sector"
    assert station.smallest_volume_containing("STO").id == "storage_sector"


def test_observation_deck_resolves_to_D5(station):
    """"Isolate the observation deck" means D5, which seals Living Quarters too.
    A player looking for a door on the Observation Deck will not find one."""
    assert station.target_cut("residential_sector").cut == ("D5",)


def test_start_state_matches_the_spec(station):
    states = station.initial_states()
    assert {d for d, s in states.items() if s == "open"} == {"D4", "D5", "D7", "D9", "D12"}
    assert all(states[h] == "closed" for h in ("H1", "H2", "H3", "H4", "H5"))


def test_a_broken_cut_set_is_rejected(station, tmp_path):
    import json
    raw = json.loads(json.dumps(station.raw))
    target = next(t for t in raw["isolation_targets"] if t["id"] == "service_sector")
    target["cut"] = ["D7"]  # the plausible, wrong answer
    path = tmp_path / "station.json"
    path.write_text(json.dumps(raw))
    try:
        Station.load(path)
    except StationError as exc:
        assert "service_sector" in str(exc)
    else:
        raise AssertionError("a wrong cut-set must not load")
