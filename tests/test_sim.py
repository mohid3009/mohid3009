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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
