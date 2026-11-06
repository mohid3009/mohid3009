"""CATOPIA prototype: a night meadow with three cats and live GitHub stats.

The cats follow hand-planned routes here (walk, pause, sit, drink) to preview
the look. Phase 3 replaces the routes with simulated agents; the renderer
stays the same.

    python prototype.py             -> output/preview.png, output/catopia.gif
    python prototype.py --offline   -> use cached data/github.json only
"""
import math
import random
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

from catopia import github, models as M, palette as P, render as R, terrain as T
from catopia.palette import h32, shade

SEED = 7
LOGIN = "mohid3009"
FRAMES = 120               # 9.6 s loop at 80 ms
PANEL_H = 60                 # stats strip under the scene
SIZE = (268, 78 + PANEL_H)   # native px; x3 upscale -> 804x414 banner
ORIGIN = (SIZE[0] // 2, -105) # scene band centred on the x+y ~ 40 row
OUT = Path(__file__).parent / "output"


def dominant(dx, dy):
    return ((1 if dx > 0 else -1), 0) if abs(dx) >= abs(dy) else (0, (1 if dy > 0 else -1))


# --- cat routes ------------------------------------------------------------
def plan(legs, speed=0.17):
    """legs: ('walk', a, b) / ('sit', pos, facing). Walk time comes from the
    distance; sits share whatever is left so every route spans FRAMES."""
    walk = [max(1, round(math.dist(l[1], l[2]) / speed)) for l in legs if l[0] == "walk"]
    sits = sum(l[0] == "sit" for l in legs)
    spare = FRAMES - sum(walk)
    assert spare >= sits, "route too long for the loop"
    keys, wi, si = [], iter(walk), 0
    for l in legs:
        if l[0] == "walk":
            keys.append((*l, next(wi)))
        else:
            si += 1
            keys.append((*l, spare // sits + (spare % sits if si == sits else 0)))
    return keys


def at(keys, f):
    for kind, a, b, n in keys:
        if f < n:
            if kind == "walk":
                t = f / n
                return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), "walk", dominant(b[0] - a[0], b[1] - a[1])
            return a, "sit", b
        f -= n


def corridor(keys):
    tiles = set()
    for kind, a, b, _ in keys:
        b = b if kind == "walk" else a
        for k in range(21):
            x, y = a[0] + (b[0] - a[0]) * k / 20, a[1] + (b[1] - a[1]) * k / 20
            tiles |= {(int(x + dx), int(y + dy)) for dx in (-0.7, 0, 0.7) for dy in (-0.7, 0, 0.7)}
    return tiles


def on_screen(w, t, margin=22):
    """Tile centre lands inside the scene band, with room for a cat's height."""
    sx = ORIGIN[0] + (t[0] - t[1]) * R.A
    sy = ORIGIN[1] + (t[0] + t[1] + 1) * R.A / 2 - w.H[t] * R.A
    return margin <= sx <= SIZE[0] - margin and margin <= sy <= SIZE[1] - PANEL_H - 10


def find_loop(w, blocked, w_, h_, region):
    """A flat w_ x h_ rectangle of walkable meadow, searched near region."""
    for x, y in sorted(((x, y) for x in range(2, w.n - w_ - 2) for y in range(2, w.n - h_ - 2)),
                       key=lambda c: math.dist(c, region)):
        ring = [(x + i, y + j) for i in range(w_ + 1) for j in range(h_ + 1)]
        if all(w.land(*c) and w.H[c] == 2 and c not in blocked and on_screen(w, c) for c in ring):
            return x, y
    raise RuntimeError("no room for a cat loop")


def routes(w):
    hx, hy = w.house
    pad = {(i, j) for i in range(hx - 1, hx + 3) for j in range(hy - 1, hy + 3)}
    c = lambda t: (t[0] + 0.5, t[1] + 0.5)

    # Mochi, the explorer: a big lap around the meadow
    x, y = find_loop(w, pad, 6, 2, (hx + 6, hy - 8))
    a, b, cc, d = c((x, y)), c((x + 6, y)), c((x + 6, y + 2)), c((x, y + 2))
    mochi = plan([("walk", a, b), ("walk", b, cc), ("sit", cc, (0, 1)), ("walk", cc, d), ("walk", d, a)], speed=0.2)
    clearing = {(i, j) for i in range(hx - 2, hx + 5) for j in range(hy - 2, hy + 5)}
    used = pad | clearing | corridor(mochi)

    # Pixel, the homebody: door -> path -> drink at the pond -> home
    pts = [c(t) for t in w.path[-8:]]
    last = w.path[-1]
    to_water = next((dx, dy) for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)) if w.water[last[0] + dx, last[1] + dy])
    legs = [("walk", p, q) for p, q in zip(pts, pts[1:])]
    back = [("walk", q, p) for p, q in reversed(list(zip(pts, pts[1:])))]
    pixel = plan(legs + [("sit", pts[-1], to_water)] + back + [("sit", pts[0], (0, 1))], speed=0.2)
    used |= corridor(pixel)

    # Saffron, the wanderer: out to a lookout spot, a long sit, back again
    x, y = find_loop(w, pad, 5, 1, (hx + 2, hy - 3))   # paths may cross; only the cottage blocks
    p0, p1, p2 = c((x, y)), c((x + 5, y)), c((x + 5, y + 1))
    saffron = plan([("walk", p0, p1), ("walk", p1, p2), ("sit", p2, (0, 1)), ("walk", p2, p1), ("walk", p1, p0),
                    ("sit", p0, (1, 0))], speed=0.18)
    used |= corridor(saffron)

    cats = [(("ginger", "tabby", "green", 1), mochi), (("black", "tuxedo", "amber", 2), pixel),
            (("white", "calico", "amber", 5), saffron)]
    return cats, used


# --- static scenery --------------------------------------------------------
def place_static(w, occ, rng):
    scene, shadow, trees = R.Scene(), {}, []
    hx, hy = w.house
    near_water = lambda x, y: any(w.water[min(max(x + i, 0), w.n - 1), min(max(y + j, 0), w.n - 1)]
                                  for i in (-1, 0, 1) for j in (-1, 0, 1))
    cells = [(x, y) for x in range(w.n) for y in range(w.n)]
    rng.shuffle(cells)
    for x, y in cells:   # forest on the back ridge and both sides, meadow kept open
        if (x, y) in occ or near_water(x, y) or w.top[x, y] not in ("grass", "stone"):
            continue
        front = x + y >= 44   # anything here would stand in front of the cats
        p = 0.6 if x + y < 32 else 0.45 if abs(x - y) >= 14 else 0 if front else 0.1 if abs(x - y) >= 11 else 0.01
        if rng.random() > p or any(abs(x - a) <= 1 and abs(y - b) <= 1 for a, b, _ in trees):
            continue
        trees.append((x, y, "pine" if w.H[x, y] >= 5 else rng.choice(["oak", "oak", "birch"])))
    if (hx + 3, hy - 2) not in occ:
        trees.append((hx + 3, hy - 2, "cherry"))
    for x, y, kind in trees:
        occ.add((x, y))
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

    for i in (0, len(w.path) // 2, len(w.path) - 1):   # lanterns along the path
        px, py = w.path[i]
        for dx, dy in ((0, -1), (1, 0), (-1, 0), (0, 1)):
            t = (px + dx, py + dy)
            if w.land(*t) and t not in occ and w.top[t] != "path":
                occ.add(t)
                scene.model(M.lantern(), t[0] + 0.5, t[1] + 0.5, w.H[t], 0.25)
                scene.light(t[0] + 0.5, t[1] + 0.5, w.H[t] + 1.5, 2.2, P.LAMP, 0.9)
                break

    for x, y in [(x, y) for x in range(w.n) for y in range(w.n) if w.water[x, y]][::5]:
        scene.model(M.lily(h32(x, y)), x + 0.5, y + 0.5, w.wl - 0.2, 0.25)

    shrooms = 0
    for x, y in cells:  # small props on tiles nobody uses
        if (x, y) in occ or not w.land(x, y) or w.top[x, y] not in ("grass", "stone"):
            continue
        r = rng.random()
        z = w.H[x, y]
        near_tree = any((x + i, y + j) in occ for i in (-1, 0, 1) for j in (-1, 0, 1))
        if near_tree and r < 0.06 and shrooms < 5:
            shrooms += 1
            scene.model(M.glow_shroom(h32(x, y)), x + 0.5, y + 0.5, z, 0.25)
            scene.light(x + 0.5, y + 0.5, z + 0.3, 0.9, P.GLOW_CAP, 0.5)
        elif r < 0.16:
            scene.model(M.flowers(h32(x, y, 1)), x + 0.5, y + 0.5, z, 0.25)
        elif r < 0.18:
            scene.model(M.rock(h32(x, y)), x + 0.5, y + 0.5, z, 0.25)
    return scene


# --- per-frame -------------------------------------------------------------
def dynamic(w, cats, flies, f):
    s = R.Scene()
    for (fur, pattern, eyes, seed), keys in cats:
        (x, y), pose, facing = at(keys, f)
        z = w.H[int(x), int(y)]
        s.light(x, y, z + 0.5, 1.1, (190, 200, 255), 0.45, dynamic=True)   # moonlit fur
        s.flat(x, y, z, 0.42, shade(T.top_color(w, int(x), int(y)), 0.7))
        s.model(M.cat(P.FUR[fur], pattern, pose, f // 2 if pose == "walk" else f // 9, P.EYES[eyes], seed),
                x, y, z, 0.25, facing)

    pond = [(x, y) for x in range(w.n) for y in range(w.n) if w.water[x, y] and y < w.n // 2 + 4]
    mx = sum(p[0] for p in pond) / len(pond) + 0.5
    my = sum(p[1] for p in pond) / len(pond) + 0.5
    a = f / FRAMES * 2 * math.pi
    for i, sgn in enumerate((1, -1)):
        b = sgn * a + i * math.pi
        kx, ky = mx + 1.3 * math.cos(b), my + 1.3 * math.sin(b)
        if w.water[int(kx), int(ky)]:
            s.model(M.koi(i), kx, ky, w.wl - 0.2, 0.25, dominant(-sgn * math.sin(b), sgn * math.cos(b)))

    def fireflies(d, proj, frame):
        for i, (x, y, z, ph) in enumerate(flies):
            if (frame + ph) % 14 >= 9:   # blink off
                continue
            t = frame / FRAMES * 2 * math.pi
            sx, sy = proj(x + 0.4 * math.sin(t + ph), y + 0.4 * math.cos(2 * t + ph), z + 0.25 * math.sin(3 * t + i))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                d.point((sx + dx, sy + dy), fill=shade(P.FIREFLY, 0.45))
            d.point((sx, sy), fill=P.FIREFLY)

    s.overlays.append(fireflies)
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


def make_hud(stats):
    def hud(d, size):
        W, H = size
        top = H - PANEL_H
        d.rectangle([0, top, W - 1, H - 1], fill=P.PANEL)
        d.line([(0, top), (W - 1, top)], fill=P.PANEL_EDGE)
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
    """255-colour palette (MAXCOVERAGE keeps small saturated details); every
    frame after the first stores only changed pixels, the rest transparent."""
    pal = frames[0].quantize(colors=255, method=Image.Quantize.MAXCOVERAGE)
    idx = [np.asarray(fr.quantize(palette=pal, dither=Image.Dither.NONE)) for fr in frames]
    out = []
    for i, a in enumerate(idx):
        im = Image.fromarray(a if i == 0 else np.where(a == idx[i - 1], 255, a).astype(np.uint8), "P")
        im.putpalette(pal.getpalette())
        out.append(im)
    out[0].save(path, save_all=True, append_images=out[1:], duration=80, loop=0,
                transparency=255, disposal=1, optimize=False)


def main():
    t0 = time.time()
    stats = github.load(LOGIN, refresh="--offline" not in sys.argv)
    w = T.generate(SEED)
    rng = random.Random(SEED)
    cats, occ = routes(w)
    static = place_static(w, occ, rng)

    # fireflies: 8 always, plus one per contribution this week (capped)
    n_flies = 8 + min(32, stats["last7"] if stats else 0)
    meadow = [(x, y) for x in range(w.n) for y in range(w.n) if w.land(x, y) and 32 <= x + y <= 50 and abs(x - y) <= 16]
    flies = [(x + rng.random(), y + rng.random(), w.H[x, y] + rng.uniform(0.8, 2.2), rng.randrange(14))
             for x, y in rng.sample(meadow, n_flies)]

    hud = make_hud(stats)
    frames = [R.render(static.merged(dynamic(w, cats, flies, f)), SIZE, ORIGIN, f, hud) for f in range(FRAMES)]
    OUT.mkdir(exist_ok=True)
    frames[0].save(OUT / "preview.png", optimize=True)
    save_gif(frames, OUT / "catopia.gif")
    print(f"{SIZE[0] * R.UPSCALE}x{SIZE[1] * R.UPSCALE}, {FRAMES} frames, {time.time() - t0:.1f}s, "
          f"gif {(OUT / 'catopia.gif').stat().st_size // 1024} KB, fireflies {n_flies}")


if __name__ == "__main__":
    main()
