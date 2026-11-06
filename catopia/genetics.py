"""Heritable traits.

Behavioural genes are not cosmetic: the utility AI in sim.py reads them every
tick (curiosity -> exploring/fishing/play, sociability -> seeking company,
speed -> walking pace, efficiency -> how fast hunger and tiredness build,
territory -> staying near a home spot, longevity -> lifespan).
"""
from . import palette as P
from .models import PATTERNS

TRAITS = ("curiosity", "sociability", "speed", "efficiency", "territory", "longevity")
FURS = tuple(P.FUR)
EYES = tuple(P.EYES)
NAMES = ("Mochi", "Pixel", "Saffron", "Biscuit", "Nimbus", "Tofu", "Juniper", "Pepper", "Miso", "Clover",
         "Pumpkin", "Sesame", "Waffle", "Luna", "Poppy", "Maple", "Noodle", "Olive", "Bean", "Ziggy",
         "Hazel", "Marble", "Sprout", "Taro", "Wren", "Yuzu", "Basil", "Cocoa", "Fig", "Kiwi")
MUTATION = 0.06   # std-dev of the nudge each numeric trait gets at birth
RECOLOR = 0.08    # chance a looks gene ignores both parents


def clip(v):
    return min(1.0, max(0.0, v))


def inherit(a, b, rng):
    """Child genome: each trait lands between the parents (biased randomly
    toward one), plus a small gaussian mutation. Looks come from either
    parent, with a rare fresh mutation."""
    g = {}
    for t in TRAITS:
        mid = (a[t] + b[t]) / 2 + (a[t] - b[t]) * rng.uniform(-0.5, 0.5)
        g[t] = round(clip(mid + rng.gauss(0, MUTATION)), 3)
    for key, pool in (("fur", FURS), ("pattern", PATTERNS), ("eyes", EYES)):
        g[key] = rng.choice(pool) if rng.random() < RECOLOR else rng.choice((a[key], b[key]))
    return g


def speed(g):
    """Blocks per tick."""
    return 0.11 + 0.13 * g["speed"]


def lifespan(g):
    """Nights."""
    return int(50 + 70 * g["longevity"])


def personality(g):
    traits = {"explorer": g["curiosity"], "social": g["sociability"],
              "territorial": g["territory"], "sleepy": 1 - g["efficiency"]}
    return max(traits, key=traits.get)


if __name__ == "__main__":
    import random
    rng = random.Random(1)
    a = {t: 0.9 for t in TRAITS} | {"fur": "ginger", "pattern": "tabby", "eyes": "green"}
    b = {t: 0.1 for t in TRAITS} | {"fur": "black", "pattern": "solid", "eyes": "amber"}
    kids = [inherit(a, b, rng) for _ in range(500)]
    mean = sum(k["curiosity"] for k in kids) / len(kids)
    assert 0.4 < mean < 0.6 and all(0 <= k["speed"] <= 1 for k in kids), mean
    assert sum(k["fur"] in ("ginger", "black") for k in kids) > 420
    print("ok")
