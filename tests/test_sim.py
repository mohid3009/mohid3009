"""Simulation checks. Run: python tests/test_sim.py  (or pytest)."""
import copy
import json
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run  # noqa: E402
from catopia import sim, terrain as T  # noqa: E402

W = T.generate(run.SEED)
_, HAB = run.build_world(W, random.Random(run.SEED))


def fresh():
    return sim.new_state(run.SEED, HAB)


def nights(state, n, energy=0.5):
    s = sim.Sim(state, HAB)
    for _ in range(n):
        s.new_day(energy, 10)
        s.run(sim.DAY_TICKS)
    return state


def test_deterministic():
    assert nights(fresh(), 2) == nights(fresh(), 2)


def test_save_load_continuity():
    straight = nights(fresh(), 2)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "state.json"
        sim.save(nights(fresh(), 1), p)
        resumed = nights(sim.load(p), 1)
    assert json.dumps(straight, sort_keys=True) == json.dumps(resumed, sort_keys=True)


def test_population_drifts_within_bounds_and_evolves():
    s = sim.Sim(fresh(), HAB)
    sizes = []
    for _ in range(160):
        s.new_day(0.5, 10)
        s.run(sim.DAY_TICKS)
        sizes.append(len(s.cats))
    assert min(sizes) >= sim.MIN_CATS and max(sizes) <= sim.MAX_CATS, sizes
    assert max(c["gen"] for c in s.cats) >= 2, "no kittens in 160 nights"
    assert any(v["died"] for v in s.s["lineage"].values()), "nobody ever died of age"


def test_genes_drive_behaviour():
    """Same cat, only curiosity/efficiency differ: the explorer roams, the sleeper naps."""
    state = fresh()
    base = state["cats"][0]
    explorer, sleeper = copy.deepcopy(base), copy.deepcopy(base)
    explorer["genes"].update(curiosity=0.95, efficiency=0.9)
    sleeper["genes"].update(curiosity=0.05, efficiency=0.05)
    explorer["id"], sleeper["id"] = 100, 101
    state["cats"] = [explorer, sleeper]
    s = sim.Sim(state, HAB)
    s.new_day(0.5, 10)
    walked, slept = {100: 0, 101: 0}, {100: 0, 101: 0}
    for _ in range(sim.DAY_TICKS):
        s.step()
        for c in s.cats:
            walked[c["id"]] += c["pose"] == "walk"
            slept[c["id"]] += c["pose"] == "sleep"
    assert walked[100] > walked[101] and slept[101] > slept[100], (walked, slept)


def test_rain_keeps_cats_in():
    def walking(weather):
        s = sim.Sim(fresh(), HAB)
        s.new_day(0.5, 10)
        s.s["weather"] = weather
        n = 0
        for _ in range(sim.DAY_TICKS):
            s.step()
            n += sum(c["pose"] == "walk" for c in s.cats)
        return n
    assert walking("rain") < walking("clear") * 0.85


def test_activity_grows_new_bushes_up_to_four():
    s = sim.Sim(fresh(), HAB)
    for _ in range(14 * sim.NIGHTS_PER_DAY):   # two real weeks of max activity
        s.new_day(1.0, 10)           # bushes only change per night, no ticks needed
    assert s.s["bushes"] == 4 and any("berry bush" in e for e in s.s["events"])


def test_stars_and_repos_trigger_events():
    s = sim.Sim(fresh(), HAB)
    s.new_day(0.5, 10)
    s.github_events(stars=1, repos=15)          # first sighting = baseline, no events
    assert not s.s["starfall"] and s.s["dens"] == 0
    s.new_day(0.5, 10)
    s.github_events(stars=3, repos=17)
    assert s.s["starfall"] and s.s["dens"] == 2
    s.new_day(0.5, 10)
    s.github_events(stars=3, repos=30)          # dens cap at 3; no new stars, no starfall
    assert not s.s["starfall"] and s.s["dens"] == 3


def test_tired_cats_use_beds():
    _, hab = run.build_world(W, random.Random(run.SEED), 2, None, 2)
    s = sim.Sim(sim.new_state(run.SEED, hab), hab)
    s.new_day(0.5, 10)
    for c in s.cats:
        c["energy"] = 0.05
    snap = s.run(200, record=1)[0]
    assert sum(c["lift"] > 0 for c in snap["cats"]) >= 2, snap["cats"]   # on the cushion / in a box den


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
