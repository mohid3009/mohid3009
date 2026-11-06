# CATOPIA — Design

![preview](../output/preview.png)

## 1. Visual direction
- **Night only.** A moonlit meadow under a starry sky. The world layer is multiplied
  by a light field: blue moonlight sets the base level, warm light pools around the
  cottage window and lanterns, cyan glow comes from bioluminescent mushrooms, and
  each cat carries a faint moonlit halo so it reads against the dark.
  Fireflies and stars are emissive overlays drawn after lighting.
- **Ordinary ground, not a floating island.** A 40×40 map is cropped so the ground
  runs off the left, right and bottom edges of the frame. A low forested ridge
  forms the skyline at the back.
- **Pixel-art isometric**: 2:1 dimetric projection, flat-shaded faces,
  nearest-neighbour 3x upscale, grass bands, rim highlights and ambient occlusion.
- **Composition**: forest on the ridge and the frame edges, with a wide open
  meadow in the middle where the three cats roam.
- **Git stats**: a footer panel shows your real GitHub data, fetched through the
  GraphQL API (`catopia/github.py`): a contribution heatmap, total contributions,
  current and best streak, repos and stars, and this week's count. Your top
  language appears under the wordmark. This week's contributions also set the
  number of fireflies (8 + one per contribution, capped at 32 extra). No token and
  no cache means a "stats unavailable" notice, never invented numbers.

## 2. Cats
Cats are built from 1/4-block voxels and are about 1.75 blocks long.

| part | detail |
|---|---|
| poses | `walk` (2-frame leg cycle, tail sway), `sit`, `sleep` (curled loaf that breathes) |
| face  | two coloured eye voxels, pink nose, muzzle; closed eyes when asleep |
| fur   | ginger, black, white, grey, cream, brown |
| pattern | solid, tabby, tuxedo, socks, siamese points, calico, spotted |
| eyes  | green, amber, blue |

Fur, pattern and eye colour are plain parameters, so Phase 4 genetics can map
genes directly to looks.

## 3. Layout (40×40 map, procedural from a seed; about a 34×46-tile window is visible)
- **Back ridge**: low hills and forest form the skyline.
- **Left**: the cottage with its lit window, food and water bowls, and a cherry tree.
- **Centre**: an open meadow with flowers. A lantern-lit path runs to the pond.
- **Right**: a pond with lily pads and koi, and a river running out of frame.
- **Cats' territory**: the visible, walkable part of the meadow. The cats never
  leave the frame.

## 4. Rendering approach
A custom painter's-algorithm voxel renderer in **Pillow**:
- Everything is an axis-aligned cube (size 1, 1/2 or 1/4), sorted by centre `x+y+z`.
- Faces are culled inside each model, so only visible faces become polygons.
- Cubes that fall outside the frame are skipped.
- The world is drawn on a transparent layer and multiplied by the light field.
  Static lights are cached; each cat's moving glow is added per frame, only in a
  small window around it.
- **Performance**: 120 frames (a 9.6 s loop) at 804×870 render in about 17 s.
- **GIF size**: about 0.9 MB. It uses a 255-colour MAXCOVERAGE palette (MEDIANCUT
  lost small saturated details). Every frame after the first stores only the pixels
  that changed; everything else is transparent.

## 5. Libraries
| need | choice | why |
|---|---|---|
| drawing, GIF/PNG | **Pillow** | already ubiquitous, fast polygon fill, GIF writer |
| noise, arrays, lighting | **numpy** | value-noise terrain, sky gradient, light field |
| GitHub API | stdlib `urllib` | one GraphQL POST; no extra dependency |

Rejected options:
- **pyrender / moderngl / Blender**: GPU or headless-GL setup on Actions, too heavy for 16 px blocks.
- **matplotlib 3D**: slow, and its look doesn't fit.

## 6. Simulation (`catopia/sim.py`, `catopia/genetics.py`)
- **One workflow run = one night** of 1,440 ticks, and the workflow runs hourly.
  A cat's 50–120-night lifespan is therefore about 2–5 real days. The GIF shows the last 120.
  State is saved in `state.json` on the `output` branch, so the world continues
  across runs. The RNG is seeded from (seed, tick), so the same state always
  gives the same future (tested).
- **Needs** drift every tick: hunger, thirst, energy, loneliness and boredom.
  Genes set the rates.
- **Utility AI**: an idle cat scores every action from its needs × genes
  (eat, drink, sleep, socialise, explore, chase fireflies, idle), picks the
  best, walks there along a BFS path and performs it. Urgent hunger or thirst
  interrupts everything except deep sleep.
- **Food is finite**: the bowl, two berry bushes and the pond's fish stock.
  Curious cats prefer fishing and catch more.
- **Genes**: curiosity, sociability, speed, efficiency, territory, longevity,
  plus fur, pattern and eye colour. A kitten's traits land between its
  parents' with a gaussian mutation, and its looks come from either parent
  (8% chance of a new mutation). Genes change behaviour, which is tested: an
  explorer walks more, and a low-efficiency cat sleeps more.
- **Population drifts between 2 and 4.** Bonded, content adults (8+ nights
  old) may have a kitten; the chance rises with room left and food. Cats die
  of old age (50–120 nights, from the longevity gene) only while more than 2
  remain, so an elder outlives its lifespan rather than dropping the colony
  below the floor. Over 240 test nights the colony spent 35 nights at 2 cats,
  65 at 3 and 140 at 4, and reached generation 8.
- **GitHub only feeds the world.** It never kills or spawns a cat directly.
  - **This week's contributions** raise the nightly refill of food, fish and
    berries, the firefly count, and slightly the birth chance.
  - **Sustained activity** builds up as growth: every 6 points (1 point = a
    real day at 70+ contributions this week) a new berry bush sprouts, up to 4. That's new habitat.
  - **Streaks**: 3+ days brings a firefly swarm (1.6× fireflies); 7+ days a
    lantern festival with paper lanterns rising, where cats seek each other's
    company.
  - **Top language** colours the meadow's flowers (Python: yellow and blue).
  - **New stars**: each one adds a golden koi to the pond for good (up to 5),
    and the night it arrives has a starfall of gold sparkles.
  - **New repos**: each one adds a cardboard-box den (up to 3). Dens are new
    beds; a tired cat picks the nearest free one (cushion or den) and is drawn
    asleep inside it. The first run records your current stars and repos as a
    baseline, so nothing fires for what already existed.
- **Family tree**: every run publishes `lineage.md` on the `output` branch
  with living cats and their traits, the full lineage tree from the founders,
  and recent events.
- **Weather** is rolled each night: about 70% clear, 15% fog and 15% rain.
  - **Fog** mists the back of the scene, and cats stay near home.
  - **Rain** dims the light and adds falling streaks. Cats explore less and nap
    or hunker down more (tested), and most fireflies hide.
- **Tests** (`tests/`), run by the Action before every render:
  - same seed gives the same result
  - save/reload continuity
  - population stays between 2 and 4, with births and deaths
  - genes change behaviour
  - rain keeps cats in
  - stars and repos trigger events
  - tired cats use beds
  - activity grows bushes
  - banner size and deterministic rendering
  - cats actually drawn
  - weather changes the picture
  - GIF round-trip accuracy
