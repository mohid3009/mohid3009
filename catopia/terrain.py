"""Procedural ground: a wide meadow that runs past the frame edges.

Banner layout, everything along one screen row (x+y ~ 40): the cottage on
the left, open meadow for the cats in the middle, a pond on the right whose
river drains off toward the right edge. Forest frames the back and sides.
"""
from dataclasses import dataclass

import numpy as np

from . import palette as P
from .palette import shade, h32


def value_noise(rng, n, cell):
    k = n // cell + 2
    g = rng.random((k, k))
    t = np.arange(n) / cell
    i = t.astype(int)
    f = t - i
    f = f * f * (3 - 2 * f)
    fx, fy = f[:, None], f[None, :]
    return (g[np.ix_(i, i)] * (1 - fx) * (1 - fy) + g[np.ix_(i + 1, i)] * fx * (1 - fy)
            + g[np.ix_(i, i + 1)] * (1 - fx) * fy + g[np.ix_(i + 1, i + 1)] * fx * fy)


@dataclass
class World:
    n: int
    H: np.ndarray         # surface height (top of the column)
    water: np.ndarray     # bool, cell is water
    wl: int               # water surface level
    top: np.ndarray       # surface material name
    house: tuple          # (x, y) min corner of the 2x2 cat house
    path: list            # path tiles from the house door to the pond shore

    def land(self, x, y):
        return 0 <= x < self.n and 0 <= y < self.n and not self.water[x, y]


def generate(seed=7, n=40):
    rng = np.random.default_rng(seed)
    X, Y = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    c = n // 2
    back = np.clip(1 - (X + Y) / n, 0, 1)   # 1 at the back corner, 0 from mid-map on
    mounds = np.clip(np.floor(value_noise(rng, n, 5) * 1.6 - 0.3), 0, None)
    H = (2 + mounds + np.floor(back ** 1.8 * 4 * (0.6 + 0.6 * value_noise(rng, n, 4)))).astype(int)

    wl = 2
    px, py = c + 5, c - 3
    water = np.hypot(X - px, Y - py) + (value_noise(rng, n, 3) - 0.5) * 1.6 < 2.8
    x, y = px, py   # river meanders toward the +x edge (screen right)
    while x < n:
        water[x, y] = True
        if x % 3 == 0 and x > px + 2:
            y2 = int(np.clip(y + rng.choice([-1, 1]), 1, n - 2))
            water[x, y2] = True
            y = y2
        x += 1
    H[water] = wl

    hx, hy = c - 5, c + 6
    H[hx - 1:hx + 3, hy - 1:hy + 3] = 2

    top = np.full((n, n), "grass", dtype=object)
    for i in range(n):
        for j in range(n):
            near = water[max(i - 1, 0):i + 2, max(j - 1, 0):j + 2].any()
            if near and not water[i, j] and H[i, j] <= wl + 1:
                top[i, j] = "sand"
            elif H[i, j] >= 8:
                top[i, j] = "stone"

    path, i, j = [], hx + 1, hy + 2
    while not water[i, j]:
        path.append((i, j))
        if top[i, j] == "grass":
            top[i, j] = "path"
        if abs(px - i) > abs(py - j):
            i += 1 if px > i else -1
        else:
            j += 1 if py > j else -1
    return World(n, H, water, wl, top, (hx, hy), path)


def top_color(w, x, y):
    """Colour of the walkable surface (used for contact shadows)."""
    mat = "water" if w.water[x, y] else w.top[x, y]
    return {"grass": P.GRASS[0], "sand": P.SAND, "path": P.PATH, "stone": P.STONE, "water": P.WATER}[mat]


def build(scene, w, shadow):
    """Emit terrain cubes with face culling, ambient occlusion and textures."""
    solid = {}
    for x in range(w.n):
        for y in range(w.n):
            h = w.H[x, y]
            for z in range(h):
                if w.water[x, y]:
                    mat = "water" if z == h - 1 else "sand"
                else:
                    mat = w.top[x, y] if z == h - 1 else "dirt" if z >= h - 4 else "stone"
                solid[(x, y, z)] = mat

    for (x, y, z), mat in solid.items():
        f = ((x, y, z + 1) not in solid) | ((x, y + 1, z) not in solid) << 1 | ((x + 1, y, z) not in solid) << 2
        if not f or (z == 0 and f == 6):   # map-edge walls are never on screen
            continue
        j = 0.95 + (h32(x, y, z) % 100) / 1000
        side = P.DIRT
        if mat == "grass":
            top = shade(P.GRASS[h32(x, y) % 3], j)
        elif mat == "path":
            top = shade(P.PATH, j)
        elif mat == "sand":
            top = side = shade(P.SAND, j)
        elif mat == "water":
            shore = any(w.land(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            top = side = P.WATER_SHALLOW if shore else P.WATER
        elif mat == "stone":
            top = side = shade(P.STONE, j)
        else:
            top = side = shade(P.DIRT, j)
        ao = 1.0
        if f & 1:
            occ = ((x - 1, y, z + 1) in solid) + ((x, y - 1, z + 1) in solid)
            ao = (1.0, 0.86, 0.76)[occ] * shadow.get((x, y), 1.0)
        scene.cube(x, y, z, 1, top, side, f, ao, mat)
    return solid
