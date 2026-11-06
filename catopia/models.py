"""Voxel models: {(i, j, k): rgb}. Cats and small props use 1/4-block voxels,
trees use 1/2-block voxels. Models face +x; the renderer rotates them.

Cat anatomy (walk pose, 1/4-block units; a cat is ~1.75 blocks long):

      ears  ..##..          k=5
      head  ..###           k=2..4   eyes on the front face, pink nose
      body  #####           k=1..2   pattern painted per part
      legs  ## ##           k=0      alternate each frame
      tail curls up behind
"""
import random

from . import palette as P
from .palette import shade, h32

PATTERNS = ("solid", "tabby", "tuxedo", "socks", "siamese", "calico", "spotted")


def _box(v, x0, x1, y0, y1, z0, z1, part):
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                v[(x, y, z)] = part


def cat(fur, pattern="solid", pose="walk", frame=0, eyes=P.EYES["green"], seed=0, kitten=False):
    parts = {}
    if pose == "walk":
        _box(parts, 0, 4, 0, 2, 1, 2, "body")
        _box(parts, 4, 6, 0, 2, 2, 4, "head")
        legs = [(0, 0), (1, 2), (4, 0), (3, 2)] if frame % 2 == 0 else [(1, 0), (0, 2), (3, 0), (4, 2)]
        for a, b in legs:
            parts[(a, b, 0)] = "leg"
        tail = [(-1, 1, 2), (-2, 1, 3), (-2, 1 - frame % 2, 4)]
        ears, eye, nose, chest, crown = [(5, 0, 5), (5, 2, 5)], [(6, 0, 3), (6, 2, 3)], (6, 1, 2), 3, 4
    elif pose == "sit":
        _box(parts, 0, 2, 0, 2, 0, 1, "body")
        _box(parts, 2, 3, 0, 2, 1, 3, "body")
        parts[(3, 0, 0)] = parts[(3, 2, 0)] = "leg"
        _box(parts, 3, 5, 0, 2, 3, 5, "head")
        tail = [(0, 3, 0), (1, 3, 0), (2, 3, frame % 2)]
        ears, eye, nose, chest, crown = [(4, 0, 6), (4, 2, 6)], [(5, 0, 4), (5, 2, 4)], (5, 1, 3), 3, 5
    else:  # sleep: curled loaf, breathing on odd frames
        _box(parts, 0, 4, 0, 2, 0, 1, "body")
        if frame % 2:
            _box(parts, 1, 3, 0, 2, 2, 2, "body")
        _box(parts, 4, 6, 0, 2, 0, 2, "head")
        tail = [(0, 3, 0), (1, 3, 0), (2, 3, 0), (3, 3, 0)]
        ears, eye, nose, chest, crown = [(5, 0, 3), (5, 2, 3)], [(6, 0, 1), (6, 2, 1)], (6, 1, 0), 9, 2
    for p in tail:
        parts[p] = "tail"
    for p in ears:
        parts[p] = "ear"
    for p in eye:
        parts[p] = "eye"
    parts[nose] = "nose"
    for y in (0, 2):
        parts[(nose[0], y, nose[2])] = "muzzle"

    if kitten:  # shorter body, same big head
        parts = {(x + 2 if x < 1 else x, y, z): p for (x, y, z), p in parts.items()
                 if not (x in (1, 2) and p in ("body", "leg"))}

    dark = shade(fur, 0.62)
    out = {}
    for (x, y, z), part in parts.items():
        c = fur
        if part == "eye":
            c = dark if pose == "sleep" else eyes
        elif part == "nose":
            c = P.NOSE
        elif pattern == "tabby" and (part in ("body", "tail") and x % 2 == 0 or part == "head" and y == 1 and z == crown):
            c = dark
        elif pattern in ("tuxedo", "socks") and (part in ("leg", "muzzle") or (pattern == "tuxedo" and part == "body" and x >= chest and z <= 1)):
            c = P.WHITE
        elif pattern == "siamese" and part in ("leg", "tail", "ear", "muzzle"):
            c = shade(P.FUR["brown"], 0.8)
        elif pattern == "calico" and part != "muzzle":
            c = (P.WHITE, P.FUR["ginger"], P.FUR["black"])[h32(seed, x // 2, y // 2, z // 2) % 3]
        elif pattern == "spotted" and part == "body" and h32(seed, x, y, z) % 4 == 0:
            c = dark
        out[(x - 3, y - 1, z)] = c
    return out


# --- trees (1/2-block voxels) ---------------------------------------------
def _blob(v, rng, leaves, rx, rz, cz, light=0.12):
    R = int(rx) + 1
    for x in range(-R, R + 1):
        for y in range(-R, R + 1):
            for z in range(int(cz - rz) - 1, int(cz + rz) + 2):
                d = (x * x + y * y) / rx ** 2 + ((z - cz) / rz) ** 2
                if d <= 1 + rng.uniform(-0.3, 0.08):
                    v[(x, y, z)] = shade(rng.choice(leaves), 1 + (z - cz) / rz * light + rng.uniform(-0.04, 0.04))


def oak(seed):
    rng = random.Random(seed)
    v = {(0, 0, z): P.OAK_TRUNK for z in range(5)}
    _blob(v, rng, P.OAK_LEAVES, 2.6, 2.0, 6.2)
    return v


def cherry(seed):
    rng = random.Random(seed)
    v = {(0, 0, z): P.CHERRY_TRUNK for z in range(5)}
    v[(1, 0, 3)] = P.CHERRY_TRUNK
    _blob(v, rng, P.CHERRY_LEAVES, 3.0, 1.9, 6.0)
    return v


def birch(seed):
    rng = random.Random(seed)
    v = {(0, 0, z): (P.BIRCH_MARK if z == 2 + seed % 3 else P.BIRCH_TRUNK) for z in range(6)}
    _blob(v, rng, P.BIRCH_LEAVES, 1.9, 1.9, 7.0)
    return v


def pine(seed):
    rng = random.Random(seed)
    v = {(0, 0, z): P.OAK_TRUNK for z in range(2)}
    for z in range(2, 12):
        rad = (12 - z) / 3.2 + (0.7 if z % 3 == 2 else 0)
        for x in range(-4, 5):
            for y in range(-4, 5):
                if x * x + y * y <= rad * rad + 0.3:
                    v[(x, y, z)] = shade(rng.choice(P.PINE_LEAVES), 0.92 + (z - 2) * 0.02)
    return v


TREES = {"oak": oak, "cherry": cherry, "birch": birch, "pine": pine}


# --- small props (1/4-block voxels) ----------------------------------------
def berry_bush(seed):
    rng = random.Random(seed)
    v = {}
    _blob(v, rng, P.OAK_LEAVES, 2.4, 1.8, 1.6, light=0.15)
    for k in v:
        if h32(seed, *k) % 6 == 0:
            v[k] = P.BERRY
    return v


def flowers(seed, palette=P.FLOWERS):
    rng = random.Random(seed)
    v = {}
    for _ in range(rng.randint(2, 4)):
        a, b = rng.randint(-2, 1), rng.randint(-2, 1)
        if rng.random() < 0.35:   # grass tuft
            v[(a, b, 0)] = shade(P.GRASS_SIDE, 0.9)
        else:
            v[(a, b, 0)] = P.STEM
            v[(a, b, 1)] = rng.choice(palette)
    return v


def mushrooms(seed):
    rng = random.Random(seed)
    v = {}
    a, b = rng.randint(-2, 0), rng.randint(-2, 0)
    v[(a + 1, b + 1, 0)] = P.MUSHROOM_STEM
    for dx in (0, 1, 2):
        for dy in (0, 1, 2):
            if dx in (0, 2) and dy in (0, 2):
                continue
            v[(a + dx, b + dy, 1)] = P.WHITE if (dx, dy) == (0, 1) else P.MUSHROOM_CAP
    v[(a + 1, b + 1, 2)] = P.MUSHROOM_CAP
    return v


def rock(seed):
    rng = random.Random(seed)
    v = {}
    for x in range(-2, 2):
        for y in range(-1, 2):
            for z in range(2):
                if rng.random() < (0.9 if z == 0 else 0.5) and not (abs(x + 0.5) > 1 and abs(y) == 1):
                    v[(x, y, z)] = shade(rng.choice(P.ROCK), 1.06 if z else 0.96)
    return v


def cat_house():
    """2x2-block cottage: door on the +y face, glowing window and gable on +x."""
    v = {}
    for x in range(8):
        for y in range(8):
            for z in range(6):
                v[(x, y, z)] = P.WOOD_DARK if x in (0, 7) and y in (0, 7) else P.WOOD[z % 2]
    for x in (3, 4):
        for z in range(4):
            v[(x, 7, z)] = P.DOOR
    for y in (3, 4):
        for z in (2, 3):
            v[(7, y, z)] = P.WINDOW
    for k in range(5):  # stepped roof, ridge along x
        for y in range(k - 1, 9 - k):
            for x in range(-1, 9):
                slope = y in (k - 1, 8 - k)
                v[(x, y, 6 + k)] = P.WOOD[k % 2] if x == 8 and not slope else P.ROOF[(y + k) % 2]
    for z in range(8, 12):
        v[(1, 5, z)] = P.CHIMNEY
    return v


def cardboard_box():
    v = {}
    for x in range(9):
        for y in range(6):
            for z in range(3):
                wall = x in (0, 8) or y in (0, 5)
                if wall or z == 0:
                    v[(x, y, z)] = P.CARDBOARD if wall else P.CARDBOARD_IN
    for x in range(9):
        v[(x, -1, 3)] = P.CARDBOARD_FLAP
    for y in range(6):
        v[(9, y, 3)] = P.CARDBOARD_FLAP
    return v


def cushion():
    return {(x, y, 0): (P.CUSHION_IN if -3 <= x <= 2 and abs(y) < 2 else P.CUSHION)
            for x in range(-4, 4) for y in range(-2, 3)}


def bowl(food=P.KIBBLE):
    v = {(x, y, 0): P.BOWL for x in range(-1, 2) for y in range(-1, 2)}
    v[(0, 0, 0)] = food
    return v


def lantern():
    """Wooden post with a warm lantern on top (the scene adds its light)."""
    v = {(0, 0, z): P.WOOD_DARK for z in range(5)}
    v[(0, 0, 5)] = P.LAMP
    v[(0, 0, 6)] = P.DOOR
    return v


def glow_shroom(seed):
    rng = random.Random(seed)
    v = {}
    for _ in range(rng.randint(2, 3)):
        a, b = rng.randint(-2, 1), rng.randint(-2, 1)
        v[(a, b, 0)] = P.MUSHROOM_STEM
        v[(a, b, 1)] = P.GLOW_CAP
    return v


def koi(seed, color=None):
    c = color or P.KOI[seed % 3]
    return {(0, 0, 0): c, (1, 0, 0): c, (-1, 0, 0): color or P.KOI[(seed + 1) % 3]}


def lily(seed):
    v = {(x, y, 0): P.LILY for x in range(-1, 2) for y in range(-1, 2) if (x, y) != (1, 1)}
    if seed % 2:
        v[(0, 0, 1)] = P.FLOWERS[3]
    return v
