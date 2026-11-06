"""Rendering checks. Run: python tests/test_render.py  (or pytest)."""
import random
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run  # noqa: E402
from catopia import render as R, sim, terrain as T  # noqa: E402

W = T.generate(run.SEED)
STATIC, HAB = run.build_world(W, random.Random(run.SEED))
STATS = {"login": "test", "total": 1234, "current_streak": 3, "longest_streak": 9, "repos": 5, "stars": 2,
         "last7": 12, "top_language": "Python", "days": [("2026-01-04", i % 5) for i in range(364)]}


def frames(n=3, weather="clear", event=None):
    s = sim.Sim(sim.new_state(run.SEED, HAB), HAB)
    s.new_day(0.5, 10)
    snaps = s.run(200, record=n)
    hud = run.make_hud(STATS, s.summary() | {"weather": weather, "event": event})
    return [R.render(STATIC.merged(run.dynamic(W, sn, f, weather, event)), run.SIZE, run.ORIGIN, f, hud)
            for f, sn in enumerate(snaps)]


def test_banner_size_and_determinism():
    a, b = frames(1)[0], frames(1)[0]
    assert a.size == (run.SIZE[0] * R.UPSCALE, run.SIZE[1] * R.UPSCALE) == (804, 414)
    assert a.tobytes() == b.tobytes()


def test_cats_are_drawn():
    """Removing the cats from a frame must change the pixels where they stand."""
    s = sim.Sim(sim.new_state(run.SEED, HAB), HAB)
    s.new_day(0.5, 0)
    snap = s.run(50, record=1)[0]
    with_cats = R.render(STATIC.merged(run.dynamic(W, snap, 0)), run.SIZE, run.ORIGIN)
    without = R.render(STATIC.merged(run.dynamic(W, snap | {"cats": []}, 0)), run.SIZE, run.ORIGIN)
    diff = (np.asarray(with_cats) != np.asarray(without)).any(axis=2).sum()
    assert diff > 300 * len(snap["cats"]), diff


def test_weather_changes_the_picture():
    clear, rain, festival = frames(1)[0], frames(1, "rain")[0], frames(1, "clear", "festival")[0]
    assert clear.tobytes() != rain.tobytes() and clear.tobytes() != festival.tobytes()


def test_gif_roundtrip():
    fr = frames(6)
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.gif"
        run.save_gif(fr, p)
        decoded = [np.asarray(f.convert("RGB")).astype(int) for f in ImageSequence.Iterator(Image.open(p))]
    assert len(decoded) == len(fr)
    for got, want in zip(decoded, fr):
        assert np.abs(got - np.asarray(want).astype(int)).max() <= 24   # palette rounding only


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
