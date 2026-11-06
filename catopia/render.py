"""Isometric voxel renderer with night lighting.

Everything is an axis-aligned cube (terrain blocks at size 1, props at 1/2,
cats and flowers at 1/4). Cubes are depth-sorted (painter's algorithm on
x+y+z of the centre) and drawn as three flat-shaded Pillow polygons onto a
transparent world layer. That layer is multiplied by a light field (blue
moonlight + warm/cool point lights), composited over a starry sky, and the
frame is upscaled with nearest-neighbour for crisp pixels.

Projection (2:1 dimetric, the classic pixel-art isometric):
    screen_x = (x - y) * A
    screen_y = (x + y) * A/2 - z * A
The camera looks from +x,+y,+z, so only the top, +y (left) and +x (right)
faces of a cube are ever visible.
"""
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from . import palette as P
from .palette import shade, h32

A = 8                 # px per block half-width (a block is 16 px wide)
UPSCALE = 3
TOP, LEFT, RIGHT = 1, 2, 4
LIGHT_LEFT, LIGHT_RIGHT = 0.84, 0.66   # moon from screen upper-left

# pixel offsets inside a block's top diamond, used for grass/sand speckles
TOP_PIX = [(dx, dy) for dy in range(-3, 4) for dx in range(-6, 7)
           if abs(dx) / 7 + abs(dy) / 3.5 < 0.8]
ROT = {(1, 0): lambda a, b: (a, b), (0, 1): lambda a, b: (-b, a),
       (-1, 0): lambda a, b: (-a, -b), (0, -1): lambda a, b: (b, -a)}


class Scene:
    """Depth-sortable primitives, point lights and screen-space overlays."""

    def __init__(self):
        self.prims = []      # (depth, kind, data)
        self.lights = []     # (x, y, z, radius_blocks, rgb, strength)
        self.dyn_lights = []
        self.overlays = []   # fn(draw, proj, frame), drawn after lighting (emissive)

    def cube(self, x, y, z, s, top, side=None, faces=7, ao=1.0, tex=None):
        self.prims.append((x + y + z + 1.5 * s, 0,
                           (x, y, z, s, top, side or top, faces, ao, tex)))

    def flat(self, x, y, z, r, color):
        """Flat diamond on a surface (soft contact shadow under a cat)."""
        self.prims.append((x + y + z + 0.05, 1, (x, y, z, r, color)))

    def light(self, x, y, z, radius, color, strength=1.0, dynamic=False):
        """Point light. Static lights are baked into a cached field; dynamic
        ones (following a cat) are added per frame in a small window."""
        (self.dyn_lights if dynamic else self.lights).append((x, y, z, radius, color, strength))

    def model(self, vox, x, y, z, s, facing=(1, 0), centered=True):
        """Place a voxel model {(i,j,k): rgb}. Interior faces are culled."""
        rot = ROT[facing]
        v = {(*rot(a, b), c): col for (a, b, c), col in vox.items()}
        off = s / 2 if centered else 0
        for (a, b, c), col in v.items():
            f = ((a, b, c + 1) not in v) | ((a, b + 1, c) not in v) << 1 | ((a + 1, b, c) not in v) << 2
            if f:
                self.cube(x + a * s - off, y + b * s - off, z + c * s, s, col, faces=f)

    def merged(self, other):
        s = Scene()
        s.prims = self.prims + other.prims
        s.lights = self.lights + other.lights
        s.dyn_lights = self.dyn_lights + other.dyn_lights
        s.overlays = self.overlays + other.overlays
        return s


def _px(x, y, z, ox, oy):
    return round(ox + (x - y) * A), round(oy + (x + y) * A / 2 - z * A)


def _draw_cube(d, ox, oy, data, frame, W, H):
    x, y, z, s, top, side, faces, ao, tex = data
    hx, hy, hz = round(A * s), round(A * s / 2), round(A * s)
    px, py = _px(x, y, z, ox, oy)
    if px + hx < 0 or px - hx > W or py + 2 * hy < 0 or py - hz > H:
        return
    t0, t1, t2, t3 = (px, py - hz), (px + hx, py + hy - hz), (px, py + 2 * hy - hz), (px - hx, py + hy - hz)
    b1, b2, b3 = (px + hx, py + hy), (px, py + 2 * hy), (px - hx, py + hy)
    r = h32(x * 4, y * 4, z * 4)

    if faces & TOP:
        c = shade(top, ao)
        d.polygon([t0, t1, t2, t3], fill=c, outline=c)
    if faces & LEFT:
        c = shade(side, LIGHT_LEFT)
        d.polygon([t3, t2, b2, b3], fill=c, outline=c)
    if faces & RIGHT:
        c = shade(side, LIGHT_RIGHT)
        d.polygon([t1, t2, b2, b1], fill=c, outline=c)
    if s != 1 or tex is None:
        return

    cx, cy = px, py + hy - hz
    if faces & TOP and tex in ("grass", "sand", "path", "stone"):
        for i in range(3):
            dx, dy = TOP_PIX[(r >> (i * 7)) % len(TOP_PIX)]
            d.point((cx + dx, cy + dy), fill=shade(top, ao * (1.12 if i else 0.88)))
    if faces & TOP and tex == "water":   # moon glints drift with the frame
        for i in range(2):
            dx, dy = TOP_PIX[((r >> (i * 9)) + frame * 5) % len(TOP_PIX)]
            d.line([(cx + dx - 1, cy + dy), (cx + dx + 1, cy + dy)], fill=P.WATER_FOAM)
    # side texture: a few darker pixels; grass gets the Minecraft green band
    for face, base, du, light in ((LEFT, b3, (hx, hy), LIGHT_LEFT), (RIGHT, b2, (hx, -hy), LIGHT_RIGHT)):
        if not faces & face:
            continue
        for i in range(2):
            u, v = ((r >> (i * 5 + face)) % 7 + 1) / 8, ((r >> (i * 3 + 11)) % 5 + 3) / 8
            d.point((base[0] + u * du[0], base[1] + u * du[1] - v * hz), fill=shade(side, light * 0.82))
        if tex == "grass":
            g = shade(P.GRASS_SIDE, light)
            for k in range(2):
                d.line([(base[0], base[1] - hz + k), (base[0] + du[0], base[1] + du[1] - hz + k)], fill=g)
            u = ((r >> face) % 6 + 1) / 8
            d.point((base[0] + u * du[0], base[1] + u * du[1] - hz + 2), fill=g)
    # bright rim on exposed front edges of the top face: crisp voxel silhouette
    if faces & TOP and tex != "water":
        rim = shade(top, ao * 1.1)
        if faces & LEFT:
            d.line([t3, t2], fill=rim)
        if faces & RIGHT:
            d.line([t2, t1], fill=rim)


def _draw_flat(d, ox, oy, data):
    x, y, z, r, color = data
    pts = [_px(x - r, y, z, ox, oy), _px(x, y - r, z, ox, oy), _px(x + r, y, z, ox, oy), _px(x, y + r, z, ox, oy)]
    d.polygon(pts, fill=color, outline=color)


@lru_cache(maxsize=4)
def light_field(size, origin, lights):
    """Per-pixel RGB multiplier: moonlight ambient + gaussian point lights.
    Light pools are squashed 2:1 so they lie flat on the isometric ground."""
    W, H = size
    field = np.empty((H, W, 3), np.float32)
    field[:] = P.AMBIENT
    for light in lights:
        add_light(field, origin, light)
    return field


def add_light(field, origin, light):
    x, y, z, radius, color, strength = light
    H, W = field.shape[:2]
    sx, sy = _px(x, y, z, *origin)
    sig = radius * A
    x0, x1 = max(0, int(sx - 3 * sig)), min(W, int(sx + 3 * sig) + 1)
    y0, y1 = max(0, int(sy - 1.5 * sig)), min(H, int(sy + 1.5 * sig) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    g = np.exp(-((xx - sx) ** 2 + ((yy - sy) * 2) ** 2) / (2 * sig * sig))
    field[y0:y1, x0:x1] += g[..., None] * (np.array(color, np.float32) / 255 * strength)


def night_sky(w, h, frame):
    t = np.linspace(0, 1, h)[:, None, None]
    grad = np.array(P.NIGHT_TOP) * (1 - t) + np.array(P.NIGHT_BOTTOM) * t
    img = Image.fromarray(np.repeat(grad, w, axis=1).astype(np.uint8))
    d = ImageDraw.Draw(img)
    rng = random.Random(1)
    for i in range(w * h // 260):
        x, y = rng.randrange(w), rng.randrange(h)
        twinkle = (i + frame // 3) % 9 == 0
        d.point((x, y), fill=P.STAR if twinkle or i % 4 == 0 else shade(P.STAR, 0.55))
        if twinkle and i % 3 == 0:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                d.point((x + dx, y + dy), fill=shade(P.STAR, 0.5))
    mx, my = int(w * 0.86), int(h * 0.09)
    for rad, col in ((16, shade(P.NIGHT_BOTTOM, 1.0)), (12, shade(P.NIGHT_BOTTOM, 1.25))):
        d.ellipse([mx - rad, my - rad, mx + rad, my + rad], fill=col)
    d.ellipse([mx - 9, my - 9, mx + 9, my + 9], fill=P.MOON)
    for cx, cy, cr in ((-3, -2, 2), (3, 3, 1), (2, -4, 1), (-4, 4, 1)):
        d.ellipse([mx + cx - cr, my + cy - cr, mx + cx + cr, my + cy + cr], fill=P.MOON_SHADE)
    return img


def render(scene, size, origin, frame=0, hud=None, fog=0.0, dim=1.0):
    """Draw one frame at native resolution, light it, upscale for crisp pixels.
    fog: 0..1 mist strength (thickest at the back); dim: light multiplier (rain)."""
    W, H = size
    world = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(world)
    ox, oy = origin
    for _, kind, data in sorted(scene.prims, key=lambda p: p[0]):
        if kind == 0:
            _draw_cube(d, ox, oy, data, frame, W, H)
        else:
            _draw_flat(d, ox, oy, data)
    arr = np.asarray(world).astype(np.float32)
    field = light_field(size, origin, tuple(scene.lights))
    if scene.dyn_lights:
        field = field.copy()
        for light in scene.dyn_lights:
            add_light(field, origin, light)
    arr[..., :3] *= np.minimum(field, 1.25) * dim
    if fog:
        k = fog * (1 - 0.6 * np.linspace(0, 1, H))[:, None, None]
        arr[..., :3] = arr[..., :3] * (1 - k) + np.array(P.FOG, np.float32) * k
    world = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
    img = night_sky(W, H, frame)
    img.paste(world, (0, 0), world)
    d = ImageDraw.Draw(img)
    proj = lambda x, y, z: _px(x, y, z, ox, oy)
    for fn in scene.overlays:
        fn(d, proj, frame)
    if hud:
        hud(d, img.size)
    return img.resize((W * UPSCALE, H * UPSCALE), Image.NEAREST)


# --- 3x5 pixel font --------------------------------------------------------
_GLYPHS = dict(zip(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 :.-/·@,+#",
    """010101111101101 110101110101110 011100100100011 110101101101110 111100110100111
111100110100100 011100101101011 101101111101101 111010010010111 001001001101010
101101110101101 100100100100111 101111111101101 110101101101101 010101101101010
110101110100100 010101101110011 110101110101101 011100010001110 111010010010010
101101101101111 101101101101010 101101111111101 101101010101101 101101010010010
111001010100111 111101101101111 010110010010111 110001010100111 110001010001110
101101111001001 111100110001110 011100111101111 111001010010010 111101111101111
111101111001110 000000000000000 000010000010000 000000000000010 000000111000000
001001010100100 000000010000000 010101111100011 000000000010100 000010111010000
101111101111101""".split()))


def text(d, x, y, s, color, scale=1, shadow=None):
    if shadow:
        text(d, x + max(1, scale // 2), y + max(1, scale // 2), s, shadow, scale)
    for i, ch in enumerate(s.upper()):
        for j, bit in enumerate(_GLYPHS.get(ch, _GLYPHS[" "])):
            if bit == "1":
                gx, gy = x + (i * 4 + j % 3) * scale, y + (j // 3) * scale
                d.rectangle([gx, gy, gx + scale - 1, gy + scale - 1], fill=color)


def text_width(s, scale=1):
    return (len(s) * 4 - 1) * scale


def sprite(d, x, y, rows, color):
    """Tiny screen-space pixel sprite (hearts, zzz, butterflies)."""
    for j, row in enumerate(rows):
        for i, bit in enumerate(row):
            if bit == "1":
                d.point((x + i, y + j), fill=color)
