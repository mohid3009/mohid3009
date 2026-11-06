"""CATOPIA: advance the cat ecosystem one night and render the banner.

    python run.py                 # fetch GitHub stats, simulate one night, render
    python run.py --offline       # use cached data/github.json, no network
    python run.py --nights 30     # fast-forward 30 nights (renders the last)
    python run.py --fresh         # ignore saved state, start from the founders

State persists in data/state.json; the workflow keeps it on the output branch.
"""
import argparse
import math
import random
import time
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

from catopia import github, models as M, palette as P, render as R, sim, terrain as T
from catopia.palette import h32, shade

SEED = 7
LOGIN = "mohid3009"
FRAMES = 120                 # ticks shown in the GIF (9.6 s at 80 ms)
PANEL_H = 60                 # stats strip under the scene
SIZE = (268, 78 + PANEL_H)   # native px; x3 upscale -> 804x414 banner
ORIGIN = (SIZE[0] // 2, -105)  # scene band centred on the x+y ~ 40 row
OUT = Path(__file__).parent / "output"
STATE = Path(__file__).parent / "data" / "state.json"

ZZZ = ["1111", "0010", "0100", "1111"]
HEART = ["01010", "11111", "01110", "00100"]
FISH = ["0110", "1111", "0110"]


def on_screen(w, t, margin=20):
    """Tile centre lands inside the scene band, with room for a cat's height."""
    sx = ORIGIN[0] + (t[0] - t[1]) * R.A
    sy = ORIGIN[1] + (t[0] + t[1] + 1) * R.A / 2 - w.H[t] * R.A
    return margin <= sx <= SIZE[0] - margin and margin <= sy <= SIZE[1] - PANEL_H - 10


def dominant(dx, dy):
    return ((1 if dx > 0 else -1), 0) if abs(dx) >= abs(dy) else (0, (1 if dy > 0 else -1))


# --- static scenery + the habitat the agents live in ------------------------
def build_world(w, rng, n_bushes=2, lang=None, n_dens=0):
    scene, shadow, trees, blocked = R.Scene(), {}, [], set()
    hx, hy = w.house
    pad = {(i, j) for i in range(hx - 1, hx + 3) for j in range(hy - 1, hy + 3)}
    clearing = {(i, j) for i in range(hx - 2, hx + 5) for j in range(hy - 2, hy + 5)}
    blocked |= pad
    near_water = lambda x, y: any(w.water[min(max(x + i, 0), w.n - 1), min(max(y + j, 0), w.n - 1)]
                                  for i in (-1, 0, 1) for j in (-1, 0, 1))
    cells = [(x, y) for x in range(w.n) for y in range(w.n)]
    rng.shuffle(cells)
    for x, y in cells:   # forest on the back ridge and both sides, meadow kept open
        if (x, y) in clearing or near_water(x, y) or w.top[x, y] not in ("grass", "stone"):
            continue
        front = x + y >= 44   # anything here would stand in front of the cats
        p = 0.6 if x + y < 32 else 0.45 if abs(x - y) >= 14 else 0 if front else 0.1 if abs(x - y) >= 11 else 0.01
        if rng.random() > p or any(abs(x - a) <= 1 and abs(y - b) <= 1 for a, b, _ in trees):
            continue
        trees.append((x, y, "pine" if w.H[x, y] >= 5 else rng.choice(["oak", "oak", "birch"])))
    trees.append((hx + 3, hy - 2, "cherry"))
    for x, y, kind in trees:
        blocked.add((x, y))
        for (dx, dy), f in {(0, 0): 0.72, (1, 0): 0.8, (0, 1): 0.9, (1, 1): 0.88}.items():
            shadow[(x + dx, y + dy)] = shadow.get((x + dx, y + dy), 1.0) * f
        scene.model(M.TREES[kind](h32(x, y)), x + 0.5, y + 0.5, w.H[x, y], 0.5)

    T.build(scene, w, shadow)
    scene.light(w.n / 2 - 1, w.n / 2 + 3, 2, 11, (150, 172, 255), 0.45)   # moonlit clearing
    z0 = w.H[hx, hy]
    scene.model(M.cat_house(), hx, hy, z0, 0.25, centered=False)
    scene.light(hx + 2.3, hy + 1, z0 + 0.7, 2.4, P.LAMP, 1.2)       # window glow
    scene.model(M.bowl(), hx + 2.4, hy + 1.3, z0, 0.25)
    scene.model(M.bowl(P.WATER_SHALLOW), hx + 2.4, hy + 1.9, z0, 0.25)
    cushion = (hx + 3, hy - 1)
    scene.model(M.cushion(), cushion[0] + 0.5, cushion[1] + 0.5, w.H[cushion], 0.25)

    for i in (0, len(w.path) // 2, len(w.path) - 1):   # lanterns along the path
        px, py = w.path[i]
        for dx, dy in ((0, -1), (1, 0), (-1, 0), (0, 1)):
            t = (px + dx, py + dy)
            if w.land(*t) and t not in blocked and t != cushion and w.top[t] != "path":
                blocked.add(t)
                scene.model(M.lantern(), t[0] + 0.5, t[1] + 0.5, w.H[t], 0.25)
                scene.light(t[0] + 0.5, t[1] + 0.5, w.H[t] + 1.5, 2.2, P.LAMP, 0.9)
                break

    for x, y in [(x, y) for x in range(w.n) for y in range(w.n) if w.water[x, y]][::5]:
        scene.model(M.lily(h32(x, y)), x + 0.5, y + 0.5, w.wl - 0.2, 0.25)

    bushes = []  # berry bushes: a food source inside the meadow
    for x, y in cells:
        if len(bushes) < n_bushes and on_screen(w, (x, y), 30) and w.land(x, y) and w.top[x, y] == "grass" \
                and (x, y) not in clearing | blocked and all(abs(x - a) + abs(y - b) > 6 for a, b in bushes):
            bushes.append((x, y))
            blocked.add((x, y))
            scene.model(M.berry_bush(h32(x, y)), x + 0.5, y + 0.5, w.H[x, y], 0.25)

    dens, keep = [], set()  # cardboard-box dens, one per new repo (sleep spots)
    for x, y in cells:
        if len(dens) >= n_dens:
            break
        foot = [(x + i, y + j) for i in range(3) for j in range(2)]
        front = (x + 1, y + 2)
        # the box may sit at the band's back edge; only its entrance must be in the cats' territory
        ok = x + 3 < w.n and y + 3 < w.n and on_screen(w, front) and on_screen(w, (x + 1, y), 13) and all(
            w.land(*t) and t not in blocked | clearing and w.H[t] == w.H[x, y] and w.top[t] == "grass"
            for t in foot + [front])
        if ok and all(abs(x - a) + abs(y - b) > 4 for a, b in dens + bushes):
            dens.append((x, y))
            blocked |= set(foot)
            keep.add(front)
            scene.model(M.cardboard_box(), x, y, w.H[x, y], 0.25, centered=False)

    flower_colors = P.LANG_FLOWERS[lang] + [P.FLOWERS[3]] if lang in P.LANG_FLOWERS else P.FLOWERS
    shrooms = 0
    for x, y in cells:  # small props on tiles nobody uses
        if (x, y) in blocked | keep or (x, y) == cushion or not w.land(x, y) or w.top[x, y] not in ("grass", "stone"):
            continue
        r = rng.random()
        z = w.H[x, y]
        near_tree = any((x + i, y + j) in blocked for i in (-1, 0, 1) for j in (-1, 0, 1))
        if near_tree and r < 0.06 and shrooms < 5:
            shrooms += 1
            scene.model(M.glow_shroom(h32(x, y)), x + 0.5, y + 0.5, z, 0.25)
            scene.light(x + 0.5, y + 0.5, z + 0.3, 0.9, P.GLOW_CAP, 0.5)
        elif r < 0.16:
            scene.model(M.flowers(h32(x, y, 1), flower_colors), x + 0.5, y + 0.5, z, 0.25)
        elif r < 0.18:
            blocked.add((x, y))
            scene.model(M.rock(h32(x, y)), x + 0.5, y + 0.5, z, 0.25)

    # the cats' territory: visible, walkable meadow, largest connected patch
    walk = {(x, y) for x in range(w.n) for y in range(w.n)
            if w.land(x, y) and (x, y) not in blocked and on_screen(w, (x, y))}
    start = max(walk, key=lambda t: sum((t[0] + d[0], t[1] + d[1]) in walk for d in sim.DIRS))
    seen, todo = {start}, [start]
    while todo:
        t = todo.pop()
        for d in sim.DIRS:
            n = (t[0] + d[0], t[1] + d[1])
            if n in walk and n not in seen:
                seen.add(n)
                todo.append(n)
    walk = seen
    stand_by = lambda t: next(((t[0] + dx, t[1] + dy), (-dx, -dy)) for dx, dy in sim.DIRS
                              if (t[0] + dx, t[1] + dy) in walk)
    shore = [(t, d) for t in sorted(walk) for d in sim.DIRS if w.water[t[0] + d[0], t[1] + d[1]]]
    beds = [(cushion, (0, 1), (cushion[0] + 0.5, cushion[1] + 0.5), 0.25)]
    beds += [((x + 1, y + 2), (1, 0), (x + 1.125, y + 0.75), 0.25) for x, y in dens if (x + 1, y + 2) in walk]
    hab = sim.Habitat(walk, shore, ((hx + 3, hy + 1), (-1, 0)), beds,
                      {f"{x},{y}": stand_by((x, y)) for x, y in bushes})
    assert cushion in walk and (hx + 3, hy + 1) in walk and shore, "layout lost a point of interest"
    return scene, hab


# --- per frame ---------------------------------------------------------------
def dynamic(w, snap, f, weather="clear", event=None, golden=0, starfall=False):
    s = R.Scene()
    marks = []
    for c in snap["cats"]:
        g, x, y = c["genes"], c["x"], c["y"]
        z = w.H[int(x), int(y)] + c["lift"]
        s.light(x, y, z + 0.5, 1.1, (190, 200, 255), 0.45, dynamic=True)   # moonlit fur
        if not c["lift"]:
            s.flat(x, y, z, 0.42 if not c["kitten"] else 0.3, shade(T.top_color(w, int(x), int(y)), 0.7))
        anim = snap["tick"] // 2 if c["pose"] == "walk" else snap["tick"] // 9
        s.model(M.cat(P.FUR[g["fur"]], g["pattern"], c["pose"], anim, P.EYES[g["eyes"]], c["id"], c["kitten"]),
                x, y, z, 0.25, c["facing"])
        if c["overlay"]:
            marks.append((c["overlay"], x, y, z))

    pond = [(x, y) for x in range(w.n) for y in range(w.n) if w.water[x, y]]
    pond = [p for p in pond if abs(p[1] - w.n // 2 + 3) < 4 and abs(p[0] - w.n // 2 - 5) < 4]
    mx = sum(p[0] for p in pond) / len(pond) + 0.5
    my = sum(p[1] for p in pond) / len(pond) + 0.5
    a = f / FRAMES * 2 * math.pi
    fish = [(1, 1.3, 0, None), (-1, 1.3, math.pi, None)]       # two koi, plus one golden koi per star
    fish += [((-1) ** i, 0.7 + 0.35 * (i % 3), 1 + i * 1.3, P.GOLD) for i in range(golden)]
    for i, (sgn, r, ph, color) in enumerate(fish):
        b = sgn * a + ph
        kx, ky = mx + r * math.cos(b), my + r * math.sin(b)
        if w.water[int(kx), int(ky)]:
            s.model(M.koi(i, color), kx, ky, w.wl - 0.2, 0.25, dominant(-sgn * math.sin(b), sgn * math.cos(b)))

    flies = snap["flies"]

    def overlay(d, proj, frame):
        for i, (x, y, z, ph) in enumerate(flies):
            if (frame + ph) % 14 >= 9:   # blink off
                continue
            sx, sy = proj(x, y, w.H[min(int(x), w.n - 1), min(int(y), w.n - 1)] + z)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                d.point((sx + dx, sy + dy), fill=shade(P.FIREFLY, 0.45))
            d.point((sx, sy), fill=P.FIREFLY)
        for kind, x, y, z in marks:
            sx, sy = proj(x, y, z + 1.7)
            if kind == "zzz":
                rise = frame % 12
                R.sprite(d, sx + 3 + rise // 4, sy - rise // 2, ZZZ, P.CREAM)
            elif kind == "heart":
                R.sprite(d, sx - 2, sy - (frame // 3) % 3, HEART, P.HEART)
            else:
                R.sprite(d, sx - 2, sy, FISH, P.KOI[0])
        band = SIZE[1] - PANEL_H
        if event == "festival":   # paper lanterns drifting up for a 7+ day streak
            for i in range(7):
                ph = i * 37
                lx = 20 + (i * 41 + 13) % 228 + round(3 * math.sin((frame + ph) / 9))
                ly = band - int((frame * 0.6 + ph) % (band + 20))
                for gx, gy in ((-2, 1), (3, 1), (0, -2), (1, -2), (0, 4), (1, 4)):
                    d.point((lx + gx, ly + gy), fill=shade(P.LAMP, 0.6))   # soft glow
                d.rectangle([lx - 1, ly - 1, lx + 2, ly + 3], fill=P.LAMP)
                d.rectangle([lx, ly, lx + 1, ly + 1], fill=P.CREAM)
        if starfall:   # sparkles drifting down on a night that brought new stars
            rng = random.Random(frame // 2)
            for i in range(9):
                sx0 = (i * 53 + 17) % SIZE[0]
                sy0 = int((frame * 0.9 + i * 23) % (band + 10)) - 5
                d.point((sx0, sy0), fill=P.GOLD)
                d.point((sx0 + 1, sy0 - 1), fill=shade(P.GOLD, 0.6))
                if rng.random() < 0.5:
                    for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        d.point((sx0 + ddx, sy0 + ddy), fill=shade(P.GOLD, 0.45))
        if weather == "rain":
            rng = random.Random(frame)
            for _ in range(70):
                rx, ry = rng.randrange(SIZE[0]), rng.randrange(band)
                d.line([(rx, ry), (rx - 1, min(ry + 4, band - 1))], fill=P.RAIN)

    s.overlays.append(overlay)
    return s


# --- HUD -------------------------------------------------------------------
def heatmap(d, y0, W, days, pitch=4):
    """GitHub-style calendar, centred; levels are quartiles of active days."""
    first = date.fromisoformat(days[0][0])
    nz = sorted(c for _, c in days if c)
    qs = [nz[len(nz) * k // 4] for k in (1, 2, 3)] if nz else []
    off = (first.weekday() + 1) % 7      # GitHub rows start on Sunday
    x0 = (W - (len(days) + off + 6) // 7 * pitch + 1) // 2
    for i, (_, c) in enumerate(days):
        col, row = divmod(i + off, 7)
        lvl = 0 if not c else 1 + sum(c > q for q in qs)
        x, y = x0 + col * pitch, y0 + row * pitch
        d.rectangle([x, y, x + pitch - 2, y + pitch - 2], fill=P.HEAT[lvl])


def make_hud(stats, world):
    def hud(d, size):
        W, H = size
        top = H - PANEL_H
        d.rectangle([0, top, W - 1, H - 1], fill=P.PANEL)
        d.line([(0, top), (W - 1, top)], fill=P.PANEL_EDGE)
        extra = [world["weather"].upper()] if world["weather"] != "clear" else []
        extra += [{"festival": "LANTERN FESTIVAL", "swarm": "FIREFLY SWARM"}[world["event"]]] if world["event"] else []
        extra += ["STARFALL"] if world.get("starfall") else []
        info = " · ".join([f"NIGHT {world['day']}", f"GEN {world['gen']}", f"{world['cats']} CATS"] + extra)
        R.text(d, W - 8 - R.text_width(info), top + 3, info, P.DIM)
        if not stats:
            R.text(d, 8, top + 30, "GITHUB STATS UNAVAILABLE - SET GITHUB_TOKEN", P.DIM)
            return
        R.text(d, 8, top + 3, f"@{stats['login']}", P.CREAM)
        heatmap(d, top + 11, W, stats["days"])
        blocks = [(f"{stats['total']:,}", "CONTRIBS"), (f"{stats['current_streak']}D", "STREAK"),
                  (f"{stats['longest_streak']}D", "BEST"), (str(stats["repos"]), "REPOS"),
                  (str(stats["stars"]), "STAR" if stats["stars"] == 1 else "STARS"), (str(stats["last7"]), "THIS WEEK")]
        bw = (W - 16) // len(blocks)
        for i, (value, label) in enumerate(blocks):
            cx = 8 + i * bw + bw // 2
            R.text(d, cx - R.text_width(value, 2) // 2, top + 42, value, P.FIREFLY if label == "THIS WEEK" else P.CREAM, 2)
            R.text(d, cx - R.text_width(label) // 2, top + 54, label, P.DIM)
    return hud


def save_gif(frames, path):
    """One 255-colour palette for the whole loop (MAXCOVERAGE keeps small
    saturated details); every frame after the first stores only changed
    pixels, the rest transparent."""
    picks = frames[:: max(1, len(frames) // 8)][:8]      # palette must cover colours from the whole loop
    montage = Image.new("RGB", (frames[0].width, frames[0].height * len(picks)))
    for i, fr in enumerate(picks):
        montage.paste(fr, (0, i * fr.height))
    pal = montage.quantize(colors=255, method=Image.Quantize.MAXCOVERAGE)
    idx = [np.asarray(fr.quantize(palette=pal, dither=Image.Dither.NONE)) for fr in frames]
    out = []
    for i, a in enumerate(idx):
        im = Image.fromarray(a if i == 0 else np.where(a == idx[i - 1], 255, a).astype(np.uint8), "P")
        im.putpalette(pal.getpalette())
        out.append(im)
    out[0].save(path, save_all=True, append_images=out[1:], duration=80, loop=0,
                transparency=255, disposal=1, optimize=False)


def lineage_md(state):
    """Family tree + living roster + recent events, published next to the GIF."""
    lin, alive = state["lineage"], {str(c["id"]) for c in state["cats"]}
    kids = {}
    for cid, v in lin.items():
        if v["parents"]:
            kids.setdefault(str(v["parents"][0]), []).append(cid)

    def tag(cid):
        v = lin[cid]
        life = f"nights {v['born']}-{v['died']}" if v["died"] else ("alive" if cid in alive else "?")
        other = [lin[str(p)]["name"] for p in v["parents"][1:] if str(p) in lin]
        g = v["genes"]
        return (f"**{v['name']}** · gen {v['gen']} · {sim.G.personality(g)} · {g['fur']} {g['pattern']} · {life}"
                + (f" · with {other[0]}" if other else ""))

    def tree(cid, depth):
        yield "  " * depth + "- " + tag(cid)
        for k in sorted(kids.get(cid, []), key=int):
            yield from tree(k, depth + 1)

    gen = max((c["gen"] for c in state["cats"]), default=0)
    out = ["# CATOPIA family tree", "",
           f"Night {state['day']} · generation {gen} · {len(state['cats'])} cats alive", "",
           "## Living cats", "",
           "| cat | gen | age | personality | curiosity | sociability | speed | efficiency |",
           "|---|---|---|---|---|---|---|---|"]
    for c in state["cats"]:
        g = c["genes"]
        out.append(f"| {c['name']} | {c['gen']} | {c['age']} nights | {sim.G.personality(g)} | "
                   f"{g['curiosity']:.2f} | {g['sociability']:.2f} | {g['speed']:.2f} | {g['efficiency']:.2f} |")
    out += ["", "## Lineage", ""]
    for cid, v in lin.items():
        if not v["parents"]:
            out += list(tree(cid, 0))
    out += ["", "## Recent events", ""] + [f"- {e}" for e in reversed(state["events"][-15:])]
    return "\n".join(out) + "\n"


def environment(stats):
    """Recent GitHub activity -> food/fish/berry refill and firefly count.
    Without stats the world still runs on its baseline."""
    last7 = stats["last7"] if stats else 0
    return min(1.0, last7 / 70), 8 + min(32, last7)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--nights", type=int, default=1)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    stats = github.load(LOGIN, refresh=not args.offline)
    w = T.generate(SEED)
    lang = stats["top_language"] if stats else None
    streak = stats["current_streak"] if stats else 0
    energy, flies = environment(stats)
    state = None if args.fresh else sim.load(STATE)
    for night in range(args.nights):
        # rebuild the meadow each night: activity can sprout bushes, new repos add dens
        grown = lambda st: (st.get("bushes", 2), st.get("dens", 0)) if st else (2, 0)
        static, hab = build_world(w, random.Random(SEED), grown(state)[0], lang, grown(state)[1])
        state = state or sim.new_state(SEED, hab)
        world = sim.Sim(state, hab)
        before = grown(state)
        world.new_day(energy, flies, streak)
        if stats:
            world.github_events(stats["stars"], stats["repos"])
        if grown(state) != before:
            static, hab = build_world(w, random.Random(SEED), grown(state)[0], lang, grown(state)[1])
            world = sim.Sim(state, hab)
        last = night == args.nights - 1
        snaps = world.run(sim.DAY_TICKS, record=FRAMES if last else 0)
    sim.save(state, STATE)

    info = world.summary()
    hud = make_hud(stats, info)
    fog, dim = {"fog": (0.35, 0.95), "rain": (0.08, 0.8)}.get(info["weather"], (0.0, 1.0))
    golden = min(5, stats["stars"]) if stats else 0
    frames = [R.render(static.merged(dynamic(w, snap, f, info["weather"], info["event"], golden, info["starfall"])),
                       SIZE, ORIGIN, f, hud, fog, dim) for f, snap in enumerate(snaps)]
    OUT.mkdir(exist_ok=True)
    frames[0].save(OUT / "preview.png", optimize=True)
    save_gif(frames, OUT / "catopia.gif")
    (OUT / "lineage.md").write_text(lineage_md(state), encoding="utf-8")

    print(f"night {state['day']}: " + ", ".join(
        f"{c['name']} (gen {c['gen']}, {c['age']}n, {sim.G.personality(c['genes'])})" for c in state["cats"]))
    for e in state["events"][-5:]:
        print("  " + e)
    print(f"{SIZE[0] * R.UPSCALE}x{SIZE[1] * R.UPSCALE}, {len(frames)} frames, {time.time() - t0:.1f}s, "
          f"gif {(OUT / 'catopia.gif').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
