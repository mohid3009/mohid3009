"""Agent-based cat ecosystem.

One workflow run (hourly) = one simulated night of DAY_TICKS ticks. Everything lives in
a JSON-ready dict so a night can be saved, reloaded and continued; the RNG is
re-seeded from (seed, tick) every tick, so the same state always produces the
same future.

Each tick a cat's needs drift (hunger, thirst, tiredness, loneliness,
boredom - rates set by its genes). When it has nothing to do, it scores every
action with a utility function of needs x genes, picks the best, walks there
(BFS over the meadow) and performs it. Nothing is scripted: who fishes, who
naps, who seeks company all falls out of the numbers.

Population drifts between MIN_CATS and MAX_CATS: bonded, content adults may
have a kitten while there is room; old cats die of age only while the
population stays above the floor (an elder outlives its lifespan otherwise).
GitHub activity only feeds the world (food refill, fireflies, slow growth
of new berry bushes, streak events); it never kills or spawns cats.

Each night also rolls weather. Rain sends cats to nap and huddle instead of
roaming; fog keeps them near home. Streak events: a 3+ day contribution
streak brings a firefly swarm, 7+ days a lantern festival that draws cats
together.
"""
import json
import math
import random
from collections import deque
from pathlib import Path

from . import genetics as G

DAY_TICKS = 1440
NIGHTS_PER_DAY = 24       # the workflow runs hourly: one night per real hour
MIN_CATS, MAX_CATS = 2, 4
ADULT_AGE = 8
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))

FOUNDERS = [  # an explorer, a sleepy homebody and a social butterfly
    ("Mochi", 20, {"fur": "ginger", "pattern": "tabby", "eyes": "green", "curiosity": 0.85, "sociability": 0.4,
                   "speed": 0.75, "efficiency": 0.65, "territory": 0.2, "longevity": 0.5}),
    ("Pixel", 34, {"fur": "black", "pattern": "tuxedo", "eyes": "amber", "curiosity": 0.3, "sociability": 0.45,
                   "speed": 0.35, "efficiency": 0.2, "territory": 0.7, "longevity": 0.6}),
    ("Saffron", 12, {"fur": "white", "pattern": "calico", "eyes": "amber", "curiosity": 0.5, "sociability": 0.9,
                     "speed": 0.5, "efficiency": 0.55, "territory": 0.3, "longevity": 0.55}),
]


def clip(v):
    return min(1.0, max(0.0, v))


def dominant(dx, dy):
    return [(1 if dx > 0 else -1), 0] if abs(dx) >= abs(dy) else [0, (1 if dy > 0 else -1)]


class Habitat:
    """Static facts the agents rely on. Points of interest are
    (stand_tile, facing) pairs."""

    def __init__(self, walkable, shore, bowl, beds, bushes):
        self.walkable = set(walkable)
        self.tiles = sorted(self.walkable)
        self.shore = shore
        self.bowl = bowl
        self.beds = beds              # [(stand_tile, facing, display_xy, lift)]: cushion, box dens
        self.bushes = bushes          # {tile_key: (stand_tile, facing)}

    def path(self, a, b):
        """Shortest 4-connected path of tiles from a to b (excluding a)."""
        if a == b:
            return []
        prev, q = {a: None}, deque([a])
        while q:
            t = q.popleft()
            if t == b:
                break
            for dx, dy in DIRS:
                n = (t[0] + dx, t[1] + dy)
                if n in self.walkable and n not in prev:
                    prev[n] = t
                    q.append(n)
        if b not in prev:
            return None
        out = []
        while b != a:
            out.append(list(b))
            b = prev[b]
        return out[::-1]

    def nearest(self, x, y):
        return min(self.tiles, key=lambda t: (t[0] + 0.5 - x) ** 2 + (t[1] + 0.5 - y) ** 2)


# --- state -----------------------------------------------------------------
def new_cat(state, name, genes, gen, parents, age, x, y):
    cid = state["next_id"]
    state["next_id"] += 1
    c = {"id": cid, "name": name, "gen": gen, "parents": parents, "genes": genes, "age": age,
         "lifespan": G.lifespan(genes), "x": x, "y": y, "facing": [1, 0], "pose": "sit",
         "hunger": 0.3, "thirst": 0.3, "energy": 0.8, "social": 0.3, "boredom": 0.3,
         "health": 1.0, "happiness": 0.7, "bonds": {}, "home": [int(x), int(y)], "act": None}
    state["cats"].append(c)
    state["lineage"][str(cid)] = {"name": name, "gen": gen, "parents": parents, "born": state["day"] - age,
                                  "died": None, "genes": genes}
    return c


def new_state(seed, hab):
    rng = random.Random(f"{seed}:genesis")
    state = {"version": 1, "seed": seed, "day": 0, "tick": 0, "next_id": 1, "cats": [], "lineage": {},
             "events": [], "res": {"bowl": 3, "fish": 8, "berries": {k: 3 for k in hab.bushes}}, "flies": [],
             "weather": "clear", "event": None, "growth": 0.0, "bushes": 2}
    for name, age, genes in FOUNDERS:
        t = rng.choice(hab.tiles)
        new_cat(state, name, dict(genes), 1, [], age, t[0] + 0.5, t[1] + 0.5)
    return state


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def save(state, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(state, separators=(",", ":")))


# --- simulation --------------------------------------------------------------
class Sim:
    def __init__(self, state, hab):
        self.s = state
        self.hab = hab
        for k, v in (("weather", "clear"), ("event", None), ("growth", 0.0), ("bushes", 2), ("dens", 0),
                     ("starfall", False)):
            state.setdefault(k, v)    # saves from older versions
        for k in hab.bushes:      # bushes that sprouted since the last run
            state["res"]["berries"].setdefault(k, 2)
        for c in state["cats"]:   # layout may have changed since the save
            if (int(c["x"]), int(c["y"])) not in hab.walkable:
                t = hab.nearest(c["x"], c["y"])
                c["x"], c["y"] = t[0] + 0.5, t[1] + 0.5

    @property
    def cats(self):
        return self.s["cats"]

    def log(self, text):
        self.s["events"] = (self.s["events"] + [f"night {self.s['day']}: {text}"])[-30:]

    # --- once per night ------------------------------------------------------
    def new_day(self, energy=0.3, flies=8, streak=0):
        """energy in [0, 1] and streak (days) come from GitHub activity; they
        only feed the world (food, fish, berries, fireflies, events)."""
        s = self.s
        rng = random.Random(f"{s['seed']}:day:{s['day']}")
        s["day"] += 1
        r = rng.random()
        s["weather"] = "rain" if r < 0.15 else "fog" if r < 0.30 else "clear"
        event = "festival" if streak >= 7 else "swarm" if streak >= 3 else None
        if event and event != s.get("event"):
            self.log({"festival": "a lantern festival", "swarm": "a firefly swarm"}[event] + f" for a {streak}-day streak")
        s["event"] = event
        flies = int(flies * (1.6 if event == "swarm" else 1) * (0.25 if s["weather"] == "rain" else 1))
        s["growth"] = round(s.get("growth", 0) + energy / NIGHTS_PER_DAY, 4)   # paced in real days
        bushes = min(4, 2 + int(s["growth"] // 6))   # sustained activity grows new habitat
        if bushes > s.get("bushes", 2):
            s["bushes"] = bushes
            self.log("a new berry bush sprouted")
        for c in self.cats:
            c["age"] += 1
            c["act"] = None

        res = s["res"]
        res["bowl"] = min(6, res["bowl"] + 2 + round(4 * energy))
        res["fish"] = min(12, res["fish"] + 2 + round(3 * energy))
        for k in res["berries"]:
            res["berries"][k] = min(5, res["berries"][k] + 1 + round(2 * energy * rng.random()))

        for c in sorted(self.cats, key=lambda c: c["age"] - c["lifespan"], reverse=True):
            old = c["age"] > c["lifespan"]
            if (old or c["health"] <= 0) and len(self.cats) > MIN_CATS:
                self.cats.remove(c)
                s["lineage"][str(c["id"])]["died"] = s["day"]
                self.log(f"{c['name']} passed away at {c['age']} nights" + ("" if old else " (starved)"))
        self._breed(rng, energy)

        s["flies"] = [[t[0] + rng.random(), t[1] + rng.random(), rng.uniform(0.8, 2.2), rng.randrange(14)]
                      for t in rng.sample(self.hab.tiles, min(flies, len(self.hab.tiles)))]

    def github_events(self, stars, repos):
        """Call after new_day. New stars -> a starfall night (golden koi are drawn
        from the star count); new repos -> a cardboard-box den, up to 3.
        The first sighting only records a baseline: no retroactive events."""
        s = self.s
        seen = s.setdefault("seen", {"stars": stars, "repos": repos})
        new_stars, new_repos = max(0, stars - seen["stars"]), max(0, repos - seen["repos"])
        seen.update(stars=max(seen["stars"], stars), repos=max(seen["repos"], repos))
        s["starfall"] = new_stars > 0
        if new_stars:
            self.log(f"a starfall for {new_stars} new GitHub star" + ("s" if new_stars > 1 else ""))
        if new_repos and s["dens"] < 3:
            s["dens"] = min(3, s["dens"] + new_repos)
            self.log("a new box den appeared for a new repo")

    def _breed(self, rng, energy):
        if len(self.cats) >= MAX_CATS:
            return
        adults = [c for c in self.cats if c["age"] >= ADULT_AGE]
        pairs = []
        for i, a in enumerate(adults):
            for b in adults[i + 1:]:
                bond = (a["bonds"].get(str(b["id"]), 0) + b["bonds"].get(str(a["id"]), 0)) / 2
                mood = (a["happiness"] + b["happiness"]) / 2
                if bond >= 0.45 and mood >= 0.4:
                    pairs.append((bond + mood, a, b))
        # room left x how well fed the meadow is: a crowded or hungry colony rarely breeds
        room = MAX_CATS - len(self.cats)
        if not pairs or rng.random() > 0.06 * room * (0.6 + 0.8 * energy):
            return
        _, a, b = max(pairs, key=lambda p: p[0])
        used = {v["name"] for v in self.s["lineage"].values()}
        living = {c["name"] for c in self.cats}
        name = rng.choice([n for n in G.NAMES if n not in used] or [n for n in G.NAMES if n not in living])
        kid = new_cat(self.s, name, G.inherit(a["genes"], b["genes"], rng), max(a["gen"], b["gen"]) + 1,
                      [a["id"], b["id"]], 0, a["x"], a["y"])
        for p in (a, b):
            kid["bonds"][str(p["id"])] = p["bonds"][str(kid["id"])] = 0.6
        self.log(f"{name} was born to {a['name']} and {b['name']} (gen {kid['gen']})")

    # --- every tick ----------------------------------------------------------
    def run(self, ticks, record=0):
        snaps = []
        for i in range(ticks):
            self.step()
            if i >= ticks - record:
                snaps.append(self.snapshot())
        return snaps

    def step(self):
        rng = random.Random(f"{self.s['seed']}:{self.s['tick']}")
        self.s["tick"] += 1
        bx = [t[0] for t in self.hab.tiles]
        by = [t[1] for t in self.hab.tiles]
        for f in self.s["flies"]:
            f[0] = min(max(f[0] + rng.uniform(-0.06, 0.06), min(bx)), max(bx) + 1)
            f[1] = min(max(f[1] + rng.uniform(-0.06, 0.06), min(by)), max(by) + 1)
        for c in self.cats:
            self._needs(c)
        for c in self.cats:
            self._act(c, rng)

    def _needs(self, c):
        g = c["genes"]
        burn = 1.3 - 0.6 * g["efficiency"]
        asleep = c["pose"] == "sleep"
        c["hunger"] = clip(c["hunger"] + 0.0011 * burn)
        c["thirst"] = clip(c["thirst"] + 0.0013)
        c["energy"] = clip(c["energy"] + 0.004) if asleep else clip(
            c["energy"] - 0.0009 * burn * (1.6 if c["pose"] == "walk" else 1))
        c["social"] = clip(c["social"] + 0.0008 * (0.4 + g["sociability"]))
        c["boredom"] = clip(c["boredom"] + (0 if asleep else 0.001 * (0.4 + g["curiosity"])))
        starving = c["hunger"] > 0.97 or c["thirst"] > 0.97
        c["health"] = clip(c["health"] + (-0.003 if starving else 0.0006))
        strain = (c["hunger"] + c["thirst"] + (1 - c["energy"]) + c["social"] * g["sociability"]
                  + c["boredom"] * g["curiosity"])
        c["happiness"] = clip(1 - strain / 3.2)

    # utility AI ------------------------------------------------------------
    def _choose(self, c, rng):
        g = c["genes"]
        awake = [o for o in self.cats if o is not c and o["pose"] != "sleep"]
        food = self._food(c)
        u = {
            "eat": c["hunger"] ** 2 * 1.6 if food else 0,
            "drink": c["thirst"] ** 2 * 1.6,
            "sleep": (1 - c["energy"]) ** 2 * 1.7 + 0.08 * (1 - g["efficiency"]),
            "social": c["social"] * g["sociability"] * 0.9 if awake else 0,
            "explore": c["boredom"] * (0.3 + g["curiosity"]) * 0.7,
            "play": c["boredom"] * g["curiosity"] * 0.6 if self.s["flies"] else 0,
            "idle": 0.12,
        }
        weather = self.s.get("weather")
        if weather == "rain":      # nap and huddle instead of roaming
            u["explore"] *= 0.3
            u["idle"] += 0.12   # hunker down where they are
            u["play"] *= 0.3
            u["sleep"] += 0.15 if c["energy"] < 0.9 else 0
            u["social"] *= 1.3
        elif weather == "fog":
            u["explore"] *= 0.7
        if self.s.get("event") == "festival":
            u["social"] += 0.15 * g["sociability"]
        for k in u:
            u[k] += rng.uniform(0, 0.04)
        kind = max(u, key=u.get)
        here = (int(c["x"]), int(c["y"]))

        if kind == "eat":
            src, (stand, face) = food[0]
            return self._go(c, "eat", stand, face, 30, src=src)
        if kind == "drink":
            stand, face = min(self.hab.shore + [self.hab.bowl], key=lambda p: self._dist(c, p[0]))
            return self._go(c, "drink", stand, face, 30)
        if kind == "sleep":   # nearest free bed (cushion or a box den), else curl up right here
            taken = {tuple(o["act"]["stand"]) for o in self.cats
                     if o is not c and o["act"] and o["act"]["kind"] == "sleep"}
            beds = [i for i, b in enumerate(self.hab.beds) if tuple(b[0]) not in taken and self._dist(c, b[0]) < 14]
            if beds:
                i = min(beds, key=lambda i: self._dist(c, self.hab.beds[i][0]))
                return self._go(c, "sleep", self.hab.beds[i][0], self.hab.beds[i][1], 2000, bed=i)
            return self._go(c, "sleep", here, c["facing"], 2000)
        if kind == "social":
            o = min(awake, key=lambda o: (o["x"] - c["x"]) ** 2 + (o["y"] - c["y"]) ** 2)
            ot = (int(o["x"]), int(o["y"]))
            spots = [(ot[0] + dx, ot[1] + dy) for dx, dy in DIRS if (ot[0] + dx, ot[1] + dy) in self.hab.walkable]
            if spots:
                stand = min(spots, key=lambda t: self._dist(c, t))
                return self._go(c, "social", stand, dominant(ot[0] - stand[0], ot[1] - stand[1]), 60, other=o["id"])
        if kind == "explore":
            if rng.random() < max(g["territory"], 0.7 if weather == "fog" else 0):
                near = [t for t in self.hab.tiles if abs(t[0] - c["home"][0]) + abs(t[1] - c["home"][1]) <= 3]
                stand = rng.choice(near or self.hab.tiles)
            else:
                stand = rng.choice(self.hab.tiles)
            return self._go(c, "explore", stand, None, rng.randint(15, 40))
        if kind == "play":
            f = min(self.s["flies"], key=lambda f: (f[0] - c["x"]) ** 2 + (f[1] - c["y"]) ** 2)
            return self._go(c, "play", self.hab.nearest(f[0], f[1]), None, 12)
        return self._go(c, "idle", here, None, rng.randint(20, 60))

    def _food(self, c):
        """Food sources with stock, best first (curious cats like fishing)."""
        res, opts = self.s["res"], []
        if res["bowl"] > 0:
            opts.append(("bowl", self.hab.bowl))
        for k, poi in self.hab.bushes.items():
            if res["berries"][k] > 0:
                opts.append((k, poi))
        if res["fish"] > 0:
            opts.append(("fish", min(self.hab.shore, key=lambda p: self._dist(c, p[0]))))
        bias = lambda src: 4 * c["genes"]["curiosity"] if src == "fish" else 0
        return sorted(opts, key=lambda o: self._dist(c, o[1][0]) - bias(o[0]))

    def _dist(self, c, t):
        return abs(t[0] + 0.5 - c["x"]) + abs(t[1] + 0.5 - c["y"])

    def _go(self, c, kind, stand, face, dur, **extra):
        stand = tuple(stand)
        path = self.hab.path((int(c["x"]), int(c["y"])), stand)
        if path is None:
            stand, path, kind = (int(c["x"]), int(c["y"])), [], "idle"
        return {"kind": kind, "stand": list(stand), "face": face, "dur": dur, "path": path, "started": False, **extra}

    def _act(self, c, rng):
        a = c["act"]
        urgent = (c["hunger"] > 0.9 or c["thirst"] > 0.9) and (not a or a["kind"] not in ("eat", "drink"))
        if a is None or (urgent and not (a["kind"] == "sleep" and c["energy"] < 0.3)):
            a = c["act"] = self._choose(c, rng)

        if a["path"]:  # walking
            tx, ty = a["path"][0]
            dx, dy = tx + 0.5 - c["x"], ty + 0.5 - c["y"]
            d = math.hypot(dx, dy)
            sp = G.speed(c["genes"]) * (0.8 if c["age"] < ADULT_AGE or c["age"] > c["lifespan"] else 1)
            if d <= sp:
                c["x"], c["y"] = tx + 0.5, ty + 0.5
                a["path"].pop(0)
            else:
                c["x"] += dx / d * sp
                c["y"] += dy / d * sp
            c["facing"] = dominant(dx, dy)
            c["pose"] = "walk"
            return

        if not a["started"]:
            a["started"] = True
            if not self._arrive(c, a, rng):
                c["act"] = None
                return
        if a["face"]:
            c["facing"] = list(a["face"])
        c["pose"] = "sleep" if a["kind"] == "sleep" else "sit"
        self._effect(c, a)
        a["dur"] -= 1
        if a["kind"] == "sleep":
            a["slept"] = a.get("slept", 0) + 1
        if a["dur"] <= 0 or (a["kind"] == "sleep" and c["energy"] >= 0.97 and a["slept"] >= 60):
            c["act"] = None

    def _arrive(self, c, a, rng):
        res = self.s["res"]
        if a["kind"] == "eat":
            src = a["src"]
            if src == "bowl":
                if res["bowl"] <= 0:
                    return False
                res["bowl"] -= 1
            elif src == "fish":
                a["dur"] = 50
                a["catch"] = res["fish"] > 0 and rng.random() < 0.35 + 0.4 * c["genes"]["curiosity"]
                if a["catch"]:
                    res["fish"] -= 1
            else:
                if res["berries"][src] <= 0:
                    return False
                res["berries"][src] -= 1
        return True

    def _effect(self, c, a):
        k = a["kind"]
        if k == "eat" and (a["src"] != "fish" or a.get("catch")):
            c["hunger"] = clip(c["hunger"] - 0.025)
        elif k == "drink":
            c["thirst"] = clip(c["thirst"] - 0.03)
        elif k == "social":
            o = next((o for o in self.cats if o["id"] == a["other"]), None)
            c["social"] = clip(c["social"] - 0.012)
            if o:
                o["social"] = clip(o["social"] - 0.006)
                for p, q in ((c, o), (o, c)):
                    p["bonds"][str(q["id"])] = round(clip(p["bonds"].get(str(q["id"]), 0) + 0.004), 4)
        elif k in ("explore", "play"):
            c["boredom"] = clip(c["boredom"] - (0.02 if k == "play" else 0.01))

    # --- for the renderer ----------------------------------------------------
    def snapshot(self):
        cats = []
        for c in self.cats:
            a = c["act"] or {}
            arrived = bool(a) and not a.get("path")
            overlay = None
            if c["pose"] == "sleep":
                overlay = "zzz"
            elif arrived and a.get("kind") == "social" and c["bonds"].get(str(a.get("other")), 0) > 0.3:
                overlay = "heart"
            elif arrived and a.get("kind") == "eat" and a.get("catch"):
                overlay = "fish"
            x, y, lift = c["x"], c["y"], 0
            if c["pose"] == "sleep" and a.get("bed") is not None and a["bed"] < len(self.hab.beds):
                (x, y), lift = self.hab.beds[a["bed"]][2:]   # drawn on the cushion / inside the box
            cats.append({"id": c["id"], "x": x, "y": y, "pose": c["pose"], "facing": tuple(c["facing"]),
                         "genes": c["genes"], "kitten": c["age"] < ADULT_AGE, "overlay": overlay, "lift": lift})
        return {"tick": self.s["tick"], "cats": cats, "flies": [list(f) for f in self.s["flies"]]}

    def summary(self):
        return {"day": self.s["day"], "cats": len(self.cats), "gen": max((c["gen"] for c in self.cats), default=0),
                "weather": self.s.get("weather", "clear"), "event": self.s.get("event"),
                "starfall": self.s.get("starfall", False)}
