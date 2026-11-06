"""CATOPIA colour palette and tiny colour/hash helpers.

Every colour in the world comes from here so the whole island reads as one
cohesive, cozy palette (warm greens, honey dirt, turquoise water, pastel sky).
"""

# --- sky -------------------------------------------------------------------
SKY_TOP = (96, 168, 224)
SKY_BOTTOM = (206, 236, 244)
CLOUD = (250, 252, 255)
CLOUD_SHADE = (214, 230, 242)
SUN = (255, 236, 160)

# --- night -----------------------------------------------------------------
NIGHT_TOP = (10, 14, 36)
NIGHT_BOTTOM = (40, 50, 98)
STAR = (232, 238, 255)
MOON = (248, 242, 214)
MOON_SHADE = (214, 206, 182)
AMBIENT = (0.34, 0.40, 0.68)      # moonlight multiplier for the whole world
LAMP = (255, 186, 104)
FIREFLY = (226, 255, 150)
GLOW_CAP = (120, 224, 255)
HEAT = [(34, 42, 70), (40, 92, 74), (58, 146, 92), (104, 206, 118), (196, 255, 170)]
FOG = (104, 116, 156)
RAIN = (140, 160, 214)
PANEL = (16, 20, 42)
PANEL_EDGE = (70, 82, 140)
DIM = (150, 164, 214)

# --- terrain ---------------------------------------------------------------
GRASS = [(110, 192, 74), (100, 182, 66), (122, 200, 82)]
GRASS_SIDE = (90, 166, 60)
DIRT = (140, 100, 66)
STONE = (128, 128, 138)
SAND = (234, 214, 158)
PATH = (206, 174, 120)
WATER = (60, 146, 214)
WATER_SHALLOW = (96, 186, 228)
WATER_FOAM = (206, 240, 252)

# --- vegetation ------------------------------------------------------------
# meadow flowers bloom in the colours of your top GitHub language
LANG_FLOWERS = {
    "Python": [(255, 212, 59), (74, 132, 200)], "JavaScript": [(247, 223, 30)], "TypeScript": [(49, 120, 198)],
    "Rust": [(222, 165, 132)], "Go": [(0, 173, 216)], "Java": [(237, 139, 0)], "C++": [(243, 75, 125)],
    "C": [(170, 170, 190)], "C#": [(104, 33, 122)], "HTML": [(227, 76, 38)], "CSS": [(86, 61, 124)],
    "Ruby": [(204, 52, 45)], "Kotlin": [(169, 123, 255)], "Swift": [(240, 81, 56)], "PHP": [(119, 123, 180)],
}
OAK_LEAVES = [(74, 156, 60), (62, 140, 52), (88, 170, 68)]
OAK_TRUNK = (112, 80, 52)
BIRCH_LEAVES = [(150, 196, 74), (132, 182, 64), (168, 206, 88)]
BIRCH_TRUNK = (236, 232, 220)
BIRCH_MARK = (58, 56, 60)
PINE_LEAVES = [(42, 112, 74), (34, 98, 66), (52, 124, 82)]
CHERRY_LEAVES = [(246, 172, 202), (234, 150, 188), (252, 198, 218)]
CHERRY_TRUNK = (96, 64, 52)
STEM = (70, 140, 56)
FLOWERS = [(234, 72, 72), (252, 214, 72), (172, 112, 222), (246, 246, 246), (104, 152, 240)]
BERRY = (214, 44, 70)
MUSHROOM_CAP = (216, 62, 54)
MUSHROOM_STEM = (238, 228, 208)
ROCK = [(150, 150, 158), (132, 132, 142), (166, 166, 172)]

# --- structures ------------------------------------------------------------
WOOD = [(196, 140, 88), (180, 126, 78)]
WOOD_DARK = (140, 96, 62)
ROOF = [(206, 84, 64), (186, 70, 56)]
DOOR = (64, 42, 38)
WINDOW = (255, 214, 120)
CHIMNEY = (150, 140, 136)
CARDBOARD = (204, 160, 104)
CARDBOARD_FLAP = (222, 182, 126)
CARDBOARD_IN = (150, 110, 70)
CUSHION = (122, 104, 196)
CUSHION_IN = (158, 142, 222)
BOWL = (90, 150, 196)
KIBBLE = (170, 110, 60)
KOI = [(250, 140, 50), (250, 250, 246), (232, 76, 50)]
LILY = (74, 160, 80)
GOLD = (255, 206, 72)

# --- cats ------------------------------------------------------------------
FUR = {
    "ginger": (238, 150, 64),
    "black": (52, 48, 56),
    "white": (242, 240, 234),
    "grey": (146, 146, 158),
    "cream": (242, 218, 172),
    "brown": (134, 92, 62),
}
EYES = {"green": (120, 210, 90), "amber": (246, 192, 60), "blue": (110, 180, 250)}
NOSE = (244, 146, 166)
WHITE = FUR["white"]

# --- ui --------------------------------------------------------------------
INK = (54, 38, 44)
CREAM = (255, 246, 220)
HEART = (240, 86, 120)


def shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def lerp(a, b, t):
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def h32(*k):
    """Deterministic integer hash (Python's hash() is salted per process)."""
    h = 2166136261
    for v in k:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
        h ^= h >> 15
    return h
