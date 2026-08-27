from __future__ import annotations

import argparse
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path

import pygame


# ============================================================
# PATHS AND WINDOW
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
TERRAIN_PATH = BASE_DIR / "sprites/terrain/default"
PROP_PATH = TERRAIN_PATH / "props"
EXPORT_PATH = BASE_DIR / "exports"

WIDTH = 1920
HEIGHT = 1080
FPS = 60

MAP_WIDTH = 88
MAP_HEIGHT = 88


# ============================================================
# ISOMETRIC GRID
# ============================================================

TILE_STEP_X = 489
TILE_STEP_Y = 218

# Small extra cosmetic nudge applied on top of each prop's measured foot
# point, so sprites sink very slightly into the tile instead of looking
# like they're balanced exactly on the seam. Purely aesthetic, not
# load-bearing for alignment (unlike the old global offset).
PROP_GROUND_NUDGE = 900


# ============================================================
# GENERATION
# ============================================================

# Larger values make terrain change more frequently.
HEIGHT_NOISE_SCALE = 0.085
MOISTURE_NOISE_SCALE = 0.105
PROP_NOISE_SCALE = 0.16

NOISE_OCTAVES = 5
NOISE_LACUNARITY = 2.0
NOISE_GAIN = 0.5

DEEP_WATER_LEVEL = 0.31
SEA_LEVEL = 0.40
BEACH_LEVEL = 0.46
HILL_LEVEL = 0.59
FOREST_MOISTURE = 0.61

# Makes the edges of the map sink into water.
ISLAND_START = 0.38
ISLAND_STRENGTH = 0.45

WATER_BIOMES = frozenset({"deep_water", "water"})

# Biomes that must never receive decorations, no matter what
# PROP_CHANCE_BY_BIOME says. This is the hard, unconditional guarantee;
# PROP_CHANCE_BY_BIOME is only a tunable density on top of this.
PROP_FORBIDDEN_BIOMES = WATER_BIOMES | frozenset({"hill"})


# ============================================================
# DECORATIONS
# ============================================================

PROP_CHANCE_BY_BIOME = {
    "beach": 0,
    "grass": 0.11,
    "forest": 0.24,
    "hill": 0,
}

# Keyword tags used to classify a prop sprite by its filename.
PROP_ROCK_KEYS = ("rock", "stone", "kamen", "skala")
PROP_TREE_KEYS = ("tree", "derevo", "elka", "pine", "oak")
PROP_BUSH_KEYS = ("bush", "kust", "shrub")
PROP_FLOWER_KEYS = ("flower", "cvet", "trava")

# Which prop categories are allowed to spawn on each biome. Only rocks may
# appear on beach tiles; everything else ("ground") is restricted to grass
# and forest tiles. Biomes not listed here (deep_water, water, hill) never
# get props at all — enforced by PROP_FORBIDDEN_BIOMES above.
BIOME_ALLOWED_PROP_CATEGORIES: dict[str, frozenset[str]] = {
    "beach": frozenset({"rock"}),
    "forest": frozenset({"tree", "bush", "flower", "other"}),
    "grass": frozenset({"tree", "bush", "flower", "other"}),
}

MAX_PROPS = MAP_WIDTH * MAP_HEIGHT

# 0 means that the prop anchor may stand on a coastal land tile.
# Set to 1 if large sprites must also stay one cell away from water.
PROP_WATER_CLEARANCE = 0


# ============================================================
# CAMERA AND EXPORT
# ============================================================

MIN_ZOOM = 0.04
MAX_ZOOM = 2.0
START_ZOOM = 0.18
ZOOM_SPEED = 1.15
CAMERA_SPEED = 900.0

# A 30x30 map is huge in native sprite resolution, so export is
# downscaled and additionally protected by a maximum side length.
EXPORT_SCALE = 0.25
EXPORT_MAX_SIDE = 8192
EXPORT_PADDING = 48


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return float(value >= edge1)
    t = clamp((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def natural_key(path: Path) -> list[object]:
    """Sorts tile2 before tile10."""
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", path.name)]


def coordinate_random(seed: int, x: int, y: int, salt: int = 0) -> float:
    """Stable coordinate hash in the [0, 1) range."""
    value = (
        seed * 0x9E3779B1
        + x * 0x85EBCA77
        + y * 0xC2B2AE3D
        + salt * 0x27D4EB2F
    ) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value / 2**32


def sprite_bottom_padding(image: pygame.Surface) -> int:
    """How many fully-transparent rows sit below a sprite's actual
    artwork, i.e. how far a naive get_rect() bottom edge overshoots the
    object's real visual base. Different prop sprites (trees, rocks,
    bushes...) carry different amounts of empty canvas below their
    artwork, so this must be measured per-sprite rather than assumed to
    be a single global constant.
    """
    width, height = image.get_size()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            if image.get_at((x, y)).a > 0:
                return height - 1 - y
    return 0


class PerlinNoise2D:
    """Small dependency-free implementation of seeded 2D Perlin noise."""

    _GRADIENTS = (
        (1.0, 0.0),
        (-1.0, 0.0),
        (0.0, 1.0),
        (0.0, -1.0),
        (0.70710678, 0.70710678),
        (-0.70710678, 0.70710678),
        (0.70710678, -0.70710678),
        (-0.70710678, -0.70710678),
    )

    def __init__(self, seed: int):
        permutation = list(range(256))
        random.Random(seed).shuffle(permutation)
        self.permutation = permutation * 2

    @staticmethod
    def _fade(value: float) -> float:
        return value * value * value * (
            value * (value * 6.0 - 15.0) + 10.0
        )

    @classmethod
    def _dot(cls, hashed: int, x: float, y: float) -> float:
        gx, gy = cls._GRADIENTS[hashed & 7]
        return gx * x + gy * y

    def noise(self, x: float, y: float) -> float:
        x0 = math.floor(x)
        y0 = math.floor(y)
        xf = x - x0
        yf = y - y0

        xi = x0 & 255
        yi = y0 & 255
        p = self.permutation

        aa = p[p[xi] + yi]
        ab = p[p[xi] + yi + 1]
        ba = p[p[xi + 1] + yi]
        bb = p[p[xi + 1] + yi + 1]

        u = self._fade(xf)
        v = self._fade(yf)

        bottom = lerp(
            self._dot(aa, xf, yf),
            self._dot(ba, xf - 1.0, yf),
            u,
        )
        top = lerp(
            self._dot(ab, xf, yf - 1.0),
            self._dot(bb, xf - 1.0, yf - 1.0),
            u,
        )
        return clamp(lerp(bottom, top, v) * 1.41421356, -1.0, 1.0)

    def fbm(
        self,
        x: float,
        y: float,
        octaves: int = NOISE_OCTAVES,
        lacunarity: float = NOISE_LACUNARITY,
        gain: float = NOISE_GAIN,
    ) -> float:
        """Fractal Brownian motion assembled from several Perlin octaves."""
        value = 0.0
        amplitude = 1.0
        frequency = 1.0
        amplitude_sum = 0.0

        for _ in range(octaves):
            value += self.noise(x * frequency, y * frequency) * amplitude
            amplitude_sum += amplitude
            amplitude *= gain
            frequency *= lacunarity

        normalized = value / amplitude_sum if amplitude_sum else 0.0
        return clamp(normalized * 0.5 + 0.5, 0.0, 1.0)


@dataclass(frozen=True)
class TerrainCell:
    biome: str
    height: float
    moisture: float
    variant: int


@dataclass(frozen=True)
class PropSprite:
    name: str
    image: pygame.Surface
    # Measured once at load time: how many transparent rows sit below
    # this sprite's actual artwork. Used instead of a single global
    # ground offset, since that overshoots for some sprites and
    # undershoots for others.
    foot_padding: int


@dataclass(frozen=True)
class PlacedProp:
    x: int
    y: int
    sprite: PropSprite


def tint_surface(
    image: pygame.Surface, color: tuple[int, int, int], strength: float,
) -> pygame.Surface:
    """Recolors a fallback tile while preserving its alpha channel."""
    strength = clamp(strength, 0.0, 1.0)
    multiplier = round(255 * (1.0 - strength))
    addition = tuple(round(channel * strength) for channel in color)

    result = image.copy()
    result.fill(
        (multiplier, multiplier, multiplier),
        special_flags=pygame.BLEND_RGB_MULT,
    )
    result.fill(addition, special_flags=pygame.BLEND_RGB_ADD)
    return result


class TerrainApp:
    def __init__(self, seed: int | None = None):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Fredde Perlin Terrain Generator")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("dejavusans", 22)

        self.camera_x = 0.0
        self.camera_y = 0.0
        self.zoom = START_ZOOM
        self.dragging = False
        self.last_mouse_pos: tuple[int, int] | None = None

        self.seed = seed if seed is not None else self.make_seed()
        self.terrain_sprites = self.load_terrain_sprites()
        self.props = self.load_props()
        self.prop_categories = {
            prop.name: self.classify_prop(prop) for prop in self.props
        }
        self.props_by_biome = self.build_props_by_biome()

        self.scaled_terrain: dict[str, list[pygame.Surface]] = {}
        self.scaled_props: dict[str, pygame.Surface] = {}
        self.scaled_assets_zoom: float | None = None

        self.terrain_map: list[list[TerrainCell]] = []
        self.map_props: list[PlacedProp] = []
        self.draw_items: list[tuple[int, int, int, int, str, object]] = []

        self.status_text = ""
        self.status_until = 0

        self.update_scaled_assets()
        self.regenerate(self.seed)
        self.center_camera()

    @staticmethod
    def make_seed() -> int:
        return random.SystemRandom().randrange(1, 2**31)

    @staticmethod
    def _load_image(path: Path) -> pygame.Surface | None:
        try:
            image = pygame.image.load(str(path)).convert_alpha()
            print(f"Loaded: {path}")
            return image
        except (pygame.error, OSError) as error:
            print(f"Cannot load {path}: {error}")
            return None

    def load_terrain_sprites(self) -> dict[str, list[pygame.Surface]]:
        if not TERRAIN_PATH.exists():
            raise FileNotFoundError(f"Terrain folder not found: {TERRAIN_PATH}")

        files = sorted(
            (
                path
                for path in TERRAIN_PATH.iterdir()
                if path.is_file() and path.suffix.casefold() == ".png"
            ),
            key=natural_key,
        )
        if not files:
            raise FileNotFoundError(f"No PNG terrain sprites found in {TERRAIN_PATH}")

        groups: dict[str, list[Path]] = {
            "deep_water": [],
            "water": [],
            "beach": [],
            "grass": [],
            "forest": [],
            "hill": [],
        }
        unclassified: list[Path] = []

        for path in files:
            name = path.stem.casefold()
            if any(key in name for key in ("deep_water", "deepwater", "glubok")):
                groups["deep_water"].append(path)
            elif any(key in name for key in ("water", "voda", "ocean", "sea")):
                groups["water"].append(path)
            elif any(key in name for key in ("sand", "pesok", "beach", "shore")):
                groups["beach"].append(path)
            elif any(key in name for key in ("forest", "les", "woodland")):
                groups["forest"].append(path)
            elif any(key in name for key in ("rock", "stone", "kamen", "hill", "skala")):
                groups["hill"].append(path)
            elif any(key in name for key in ("lujaika", "luzhaika", "grass", "lawn", "meadow")):
                groups["grass"].append(path)
            else:
                unclassified.append(path)

        if not groups["grass"]:
            groups["grass"] = unclassified or files

        loaded_by_path: dict[Path, pygame.Surface] = {}

        def load_group(paths: list[Path]) -> list[pygame.Surface]:
            result: list[pygame.Surface] = []
            for path in paths:
                if path not in loaded_by_path:
                    image = self._load_image(path)
                    if image is not None:
                        loaded_by_path[path] = image
                if path in loaded_by_path:
                    result.append(loaded_by_path[path])
            return result

        sprites = {name: load_group(paths) for name, paths in groups.items()}
        grass = sprites["grass"]
        if not grass:
            raise RuntimeError("Terrain sprites exist, but none could be loaded")

        # Use at most three source variants for generated fallbacks to keep
        # memory usage reasonable with 1000x1000 source sprites.
        fallback_sources = grass[:3]

        if not sprites["water"]:
            sprites["water"] = [
                tint_surface(image, (47, 132, 190), 0.78)
                for image in fallback_sources
            ]
            print("No water*.png found: generated water fallback tiles")

        if not sprites["deep_water"]:
            sprites["deep_water"] = [
                tint_surface(image, (25, 76, 128), 0.48)
                for image in sprites["water"][:3]
            ]

        if not sprites["beach"]:
            sprites["beach"] = [
                tint_surface(image, (210, 181, 112), 0.70)
                for image in fallback_sources
            ]

        if not sprites["forest"]:
            sprites["forest"] = [
                tint_surface(image, (36, 105, 55), 0.34)
                for image in fallback_sources
            ]

        if not sprites["hill"]:
            sprites["hill"] = [
                tint_surface(image, (116, 111, 98), 0.60)
                for image in fallback_sources
            ]

        return sprites

    def load_props(self) -> list[PropSprite]:
        if not PROP_PATH.exists():
            print(f"Props folder not found: {PROP_PATH}")
            return []

        result: list[PropSprite] = []
        paths = sorted(
            (
                path
                for path in PROP_PATH.iterdir()
                if path.is_file() and path.suffix.casefold() == ".png"
            ),
            key=natural_key,
        )
        for path in paths:
            image = self._load_image(path)
            if image is not None:
                result.append(
                    PropSprite(
                        name=path.stem,
                        image=image,
                        foot_padding=sprite_bottom_padding(image),
                    )
                )
        return result

    @staticmethod
    def classify_prop(prop: PropSprite) -> str:
        """Buckets a prop sprite into rock / tree / bush / flower / other
        based on its filename, so biome placement can be locked down."""
        name = prop.name.casefold()
        if any(key in name for key in PROP_ROCK_KEYS):
            return "rock"
        if any(key in name for key in PROP_TREE_KEYS):
            return "tree"
        if any(key in name for key in PROP_BUSH_KEYS):
            return "bush"
        if any(key in name for key in PROP_FLOWER_KEYS):
            return "flower"
        return "other"

    def build_props_by_biome(self) -> dict[str, list[PropSprite]]:
        """Precomputes, per biome, the list of props actually allowed to
        spawn there. Rocks are the only thing allowed on beach; everything
        else ("ground") is restricted to grass and forest. Biomes not
        present in BIOME_ALLOWED_PROP_CATEGORIES (water, deep_water, hill)
        never get anything — see PROP_FORBIDDEN_BIOMES."""
        by_biome: dict[str, list[PropSprite]] = {}
        for biome, allowed_categories in BIOME_ALLOWED_PROP_CATEGORIES.items():
            by_biome[biome] = [
                prop
                for prop in self.props
                if self.prop_categories[prop.name] in allowed_categories
            ]
        return by_biome

    def regenerate(self, seed: int | None = None) -> None:
        if seed is not None:
            self.seed = seed
        self.generate_map()
        self.generate_props()
        self.rebuild_draw_order()
        self.show_status(
            f"Seed {self.seed}: {len(self.map_props)} decorations",
            seconds=3.0,
        )

    def generate_map(self) -> None:
        height_noise = PerlinNoise2D(self.seed)
        moisture_noise = PerlinNoise2D(self.seed ^ 0x5F356495)
        detail_noise = PerlinNoise2D(self.seed ^ 0xA24BAED4)
        result: list[list[TerrainCell]] = []

        for y in range(MAP_HEIGHT):
            row: list[TerrainCell] = []
            for x in range(MAP_WIDTH):
                height = height_noise.fbm(
                    (x + 0.37) * HEIGHT_NOISE_SCALE,
                    (y - 0.61) * HEIGHT_NOISE_SCALE,
                )
                detail = detail_noise.fbm(
                    (x + 17.0) * HEIGHT_NOISE_SCALE * 2.1,
                    (y - 23.0) * HEIGHT_NOISE_SCALE * 2.1,
                    octaves=3,
                )
                height = height * 0.84 + detail * 0.16

                nx = (x / max(1, MAP_WIDTH - 1)) * 2.0 - 1.0
                ny = (y / max(1, MAP_HEIGHT - 1)) * 2.0 - 1.0
                radial_distance = math.hypot(nx, ny) / math.sqrt(2.0)
                island_falloff = smoothstep(ISLAND_START, 1.0, radial_distance)
                height = clamp(height - island_falloff * ISLAND_STRENGTH, 0.0, 1.0)

                moisture = moisture_noise.fbm(
                    (x + 101.0) * MOISTURE_NOISE_SCALE,
                    (y - 79.0) * MOISTURE_NOISE_SCALE,
                    octaves=4,
                )

                if height < DEEP_WATER_LEVEL:
                    biome = "deep_water"
                elif height < SEA_LEVEL:
                    biome = "water"
                elif height < BEACH_LEVEL:
                    biome = "beach"
                elif height >= HILL_LEVEL:
                    biome = "hill"
                elif moisture >= FOREST_MOISTURE:
                    biome = "forest"
                else:
                    biome = "grass"

                variant_count = len(self.terrain_sprites[biome])
                variant = min(
                    variant_count - 1,
                    int(coordinate_random(self.seed, x, y, 7) * variant_count),
                )
                row.append(TerrainCell(biome, height, moisture, variant))
            result.append(row)

        self.terrain_map = result

    def cell_is_near_water(self, x: int, y: int, clearance: int) -> bool:
        for offset_y in range(-clearance, clearance + 1):
            for offset_x in range(-clearance, clearance + 1):
                check_x = x + offset_x
                check_y = y + offset_y
                if not (0 <= check_x < MAP_WIDTH and 0 <= check_y < MAP_HEIGHT):
                    continue
                if self.terrain_map[check_y][check_x].biome in WATER_BIOMES:
                    return True
        return False

    @staticmethod
    def prop_weight(prop: PropSprite, biome: str) -> float:
        name = prop.name.casefold()
        tree = any(key in name for key in PROP_TREE_KEYS)
        bush = any(key in name for key in PROP_BUSH_KEYS)
        rock = any(key in name for key in PROP_ROCK_KEYS)
        flower = any(key in name for key in PROP_FLOWER_KEYS)

        weight = 1.0
        if biome == "forest":
            weight *= 4.0 if tree or bush else 0.75
        elif biome == "hill":
            weight *= 4.0 if rock else 0.65
        elif biome == "beach":
            weight *= 1.5 if rock else 0.7
        elif biome == "grass":
            weight *= 2.0 if flower or bush else 0.75 if rock else 1.0
        return weight

    def choose_prop(self, biome: str, rng: random.Random) -> PropSprite | None:
        # Only ever pick from the pre-filtered, biome-eligible pool; if a
        # biome has no eligible props (e.g. no rock sprites exist), simply
        # place nothing rather than falling back to an unrelated prop.
        candidates = self.props_by_biome.get(biome, [])
        if not candidates:
            return None
        weights = [self.prop_weight(prop, biome) for prop in candidates]
        return rng.choices(candidates, weights=weights, k=1)[0]

    def generate_props(self) -> None:
        self.map_props = []
        if not self.props:
            return

        rng = random.Random(self.seed ^ 0xD1B54A32)
        prop_noise = PerlinNoise2D(self.seed ^ 0x94D049BB)
        cells = [(x, y) for y in range(MAP_HEIGHT) for x in range(MAP_WIDTH)]
        rng.shuffle(cells)

        for x, y in cells:
            cell = self.terrain_map[y][x]

            # Hard, unconditional guarantee: decorations never spawn on
            # water, deep water, or hill tiles — regardless of what
            # PROP_CHANCE_BY_BIOME says.
            if cell.biome in PROP_FORBIDDEN_BIOMES:
                continue
            if self.cell_is_near_water(x, y, PROP_WATER_CLEARANCE):
                continue

            base_chance = PROP_CHANCE_BY_BIOME.get(cell.biome, 0.0)
            density = prop_noise.fbm(
                (x + 41.0) * PROP_NOISE_SCALE,
                (y - 57.0) * PROP_NOISE_SCALE,
                octaves=3,
            )
            chance = clamp(base_chance * lerp(0.35, 1.75, density), 0.0, 0.85)
            if rng.random() > chance:
                continue

            chosen_prop = self.choose_prop(cell.biome, rng)
            if chosen_prop is None:
                continue

            self.map_props.append(PlacedProp(x=x, y=y, sprite=chosen_prop))
            if len(self.map_props) >= MAX_PROPS:
                break

        assert all(
            self.terrain_map[prop.y][prop.x].biome not in PROP_FORBIDDEN_BIOMES
            for prop in self.map_props
        )
        assert all(
            self.prop_categories[prop.sprite.name]
            in BIOME_ALLOWED_PROP_CATEGORIES.get(
                self.terrain_map[prop.y][prop.x].biome, frozenset()
            )
            for prop in self.map_props
        )

    def rebuild_draw_order(self) -> None:
        items: list[tuple[int, int, int, int, str, object]] = []
        for y, row in enumerate(self.terrain_map):
            for x, cell in enumerate(row):
                items.append((x + y, 0, y, x, "tile", cell))
        for prop in self.map_props:
            items.append((prop.x + prop.y, 1, prop.y, prop.x, "prop", prop))
        items.sort(key=lambda item: item[:4])
        self.draw_items = items

    @staticmethod
    def scale_image(image: pygame.Surface, scale: float) -> pygame.Surface:
        size = (
            max(1, round(image.get_width() * scale)),
            max(1, round(image.get_height() * scale)),
        )
        return pygame.transform.smoothscale(image, size)

    def update_scaled_assets(self) -> None:
        if self.scaled_assets_zoom is not None and math.isclose(
            self.scaled_assets_zoom, self.zoom, abs_tol=1e-9
        ):
            return

        self.scaled_terrain = {
            biome: [self.scale_image(image, self.zoom) for image in images]
            for biome, images in self.terrain_sprites.items()
        }
        self.scaled_props = {
            prop.name: self.scale_image(prop.image, self.zoom)
            for prop in self.props
        }
        self.scaled_assets_zoom = self.zoom

    @staticmethod
    def cell_to_world(x: int, y: int) -> tuple[float, float]:
        return (x - y) * TILE_STEP_X, (x + y) * TILE_STEP_Y

    def world_to_screen(self, x: int, y: int) -> tuple[float, float]:
        world_x, world_y = self.cell_to_world(x, y)
        return (
            WIDTH / 2 + (world_x - self.camera_x) * self.zoom,
            HEIGHT / 2 + (world_y - self.camera_y) * self.zoom,
        )

    def center_camera(self) -> None:
        self.camera_x = ((MAP_WIDTH - 1) - (MAP_HEIGHT - 1)) * TILE_STEP_X / 2
        self.camera_y = ((MAP_WIDTH - 1) + (MAP_HEIGHT - 1)) * TILE_STEP_Y / 2

    def draw_map(self) -> None:
        screen_rect = self.screen.get_rect()

        for _, _, y, x, kind, payload in self.draw_items:
            screen_x, screen_y = self.world_to_screen(x, y)

            if kind == "tile":
                cell = payload
                assert isinstance(cell, TerrainCell)
                image = self.scaled_terrain[cell.biome][cell.variant]
                rect = image.get_rect(center=(round(screen_x), round(screen_y)))
            else:
                placed = payload
                assert isinstance(placed, PlacedProp)
                image = self.scaled_props[placed.sprite.name]
                # Anchor using this specific sprite's measured foot
                # padding rather than a single global constant, since
                # different props have different amounts of transparent
                # canvas below their artwork.
                foot_offset = (
                    placed.sprite.foot_padding - PROP_GROUND_NUDGE
                ) * self.zoom
                rect = image.get_rect(
                    midbottom=(
                        round(screen_x),
                        round(screen_y - foot_offset),
                    )
                )

            if screen_rect.colliderect(rect):
                self.screen.blit(image, rect)

    def change_zoom(self, mouse_pos: tuple[int, int], wheel: int) -> None:
        if wheel == 0:
            return

        mouse_x, mouse_y = mouse_pos
        world_mouse_x = self.camera_x + (mouse_x - WIDTH / 2) / self.zoom
        world_mouse_y = self.camera_y + (mouse_y - HEIGHT / 2) / self.zoom
        old_zoom = self.zoom
        self.zoom = clamp(
            self.zoom * (ZOOM_SPEED ** wheel),
            MIN_ZOOM,
            MAX_ZOOM,
        )

        if not math.isclose(old_zoom, self.zoom, abs_tol=1e-9):
            self.camera_x = world_mouse_x - (mouse_x - WIDTH / 2) / self.zoom
            self.camera_y = world_mouse_y - (mouse_y - HEIGHT / 2) / self.zoom
            self.update_scaled_assets()

    def drag_camera(self, pos: tuple[int, int]) -> None:
        if not self.dragging:
            return
        if self.last_mouse_pos is None:
            self.last_mouse_pos = pos
            return

        dx = pos[0] - self.last_mouse_pos[0]
        dy = pos[1] - self.last_mouse_pos[1]
        self.camera_x -= dx / self.zoom
        self.camera_y -= dy / self.zoom
        self.last_mouse_pos = pos

    def keyboard_camera(self, delta_seconds: float) -> None:
        keys = pygame.key.get_pressed()
        speed = CAMERA_SPEED * delta_seconds / self.zoom
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            self.camera_x -= speed
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            self.camera_x += speed
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            self.camera_y -= speed
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            self.camera_y += speed

    def show_status(self, text: str, seconds: float = 4.0) -> None:
        self.status_text = text
        self.status_until = pygame.time.get_ticks() + round(seconds * 1000)

    def draw_ui(self) -> None:
        lines = [
            f"Seed: {self.seed} Zoom: {self.zoom:.2f} Props: {len(self.map_props)}",
            "MMB drag | Wheel zoom | WASD | SPACE new seed | R regenerate | C center | E export PNG",
        ]
        if self.status_text and pygame.time.get_ticks() < self.status_until:
            lines.append(self.status_text)

        rendered = [self.font.render(line, True, (255, 255, 255)) for line in lines]
        box_width = max(surface.get_width() for surface in rendered) + 24
        box_height = sum(surface.get_height() for surface in rendered) + 16
        background = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
        background.fill((0, 0, 0, 185))
        self.screen.blit(background, (6, 6))

        y = 12
        for surface in rendered:
            self.screen.blit(surface, (18, y))
            y += surface.get_height()

    def export_bounds(self) -> tuple[float, float, float, float]:
        min_x = math.inf
        min_y = math.inf
        max_x = -math.inf
        max_y = -math.inf

        for y, row in enumerate(self.terrain_map):
            for x, cell in enumerate(row):
                world_x, world_y = self.cell_to_world(x, y)
                image = self.terrain_sprites[cell.biome][cell.variant]
                half_width = image.get_width() / 2
                half_height = image.get_height() / 2
                min_x = min(min_x, world_x - half_width)
                max_x = max(max_x, world_x + half_width)
                min_y = min(min_y, world_y - half_height)
                max_y = max(max_y, world_y + half_height)

        for prop in self.map_props:
            world_x, world_y = self.cell_to_world(prop.x, prop.y)
            foot_offset = prop.sprite.foot_padding - PROP_GROUND_NUDGE
            bottom = world_y - foot_offset
            image = prop.sprite.image
            min_x = min(min_x, world_x - image.get_width() / 2)
            max_x = max(max_x, world_x + image.get_width() / 2)
            min_y = min(min_y, bottom - image.get_height())
            max_y = max(max_y, bottom)

        return (
            math.floor(min_x - EXPORT_PADDING),
            math.floor(min_y - EXPORT_PADDING),
            math.ceil(max_x + EXPORT_PADDING),
            math.ceil(max_y + EXPORT_PADDING),
        )

    @staticmethod
    def export_geometry(
        bounds: tuple[float, float, float, float], requested_scale: float,
    ) -> tuple[float, tuple[int, int]]:
        left, top, right, bottom = bounds
        world_width = max(1.0, right - left)
        world_height = max(1.0, bottom - top)
        scale = min(
            requested_scale,
            EXPORT_MAX_SIDE / world_width,
            EXPORT_MAX_SIDE / world_height,
        )
        size = (
            max(1, math.ceil(world_width * scale)),
            max(1, math.ceil(world_height * scale)),
        )
        return scale, size

    def export_terrain_png(
        self,
        path: Path,
        bounds: tuple[float, float, float, float],
        scale: float,
        size: tuple[int, int],
    ) -> None:
        layer = pygame.Surface(size, pygame.SRCALPHA, 32)
        layer.fill((0, 0, 0, 0))
        left, top, _, _ = bounds
        cache: dict[tuple[str, int], pygame.Surface] = {}

        cells = sorted(
            (
                (x + y, y, x, cell)
                for y, row in enumerate(self.terrain_map)
                for x, cell in enumerate(row)
            ),
            key=lambda item: item[:3],
        )
        for _, y, x, cell in cells:
            key = (cell.biome, cell.variant)
            if key not in cache:
                cache[key] = self.scale_image(
                    self.terrain_sprites[cell.biome][cell.variant], scale
                )
            image = cache[key]
            world_x, world_y = self.cell_to_world(x, y)
            rect = image.get_rect(
                center=(
                    round((world_x - left) * scale),
                    round((world_y - top) * scale),
                )
            )
            layer.blit(image, rect)

        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(layer, str(path))

    def export_decorations_png(
        self,
        path: Path,
        bounds: tuple[float, float, float, float],
        scale: float,
        size: tuple[int, int],
    ) -> None:
        layer = pygame.Surface(size, pygame.SRCALPHA, 32)
        layer.fill((0, 0, 0, 0))
        left, top, _, _ = bounds
        cache: dict[str, pygame.Surface] = {}

        for prop in sorted(self.map_props, key=lambda item: (item.x + item.y, item.y, item.x)):
            if prop.sprite.name not in cache:
                cache[prop.sprite.name] = self.scale_image(prop.sprite.image, scale)
            image = cache[prop.sprite.name]
            world_x, world_y = self.cell_to_world(prop.x, prop.y)
            foot_offset = prop.sprite.foot_padding - PROP_GROUND_NUDGE
            rect = image.get_rect(
                midbottom=(
                    round((world_x - left) * scale),
                    round((world_y - foot_offset - top) * scale),
                )
            )
            layer.blit(image, rect)

        path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(layer, str(path))

    def export_map_layers(self, output_root: Path = EXPORT_PATH) -> tuple[Path, Path]:
        """Exports aligned transparent terrain and decoration PNG layers."""
        output_dir = output_root / f"map_{self.seed}"
        terrain_path = output_dir / "terrain.png"
        decorations_path = output_dir / "decorations.png"

        bounds = self.export_bounds()
        scale, size = self.export_geometry(bounds, EXPORT_SCALE)
        self.export_terrain_png(terrain_path, bounds, scale, size)
        self.export_decorations_png(decorations_path, bounds, scale, size)

        print(f"Exported {size[0]}x{size[1]} PNG layers to {output_dir}")
        return terrain_path, decorations_path

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_SPACE:
                self.regenerate(self.make_seed())
            elif event.key == pygame.K_r:
                self.regenerate(self.seed)
            elif event.key == pygame.K_c:
                self.center_camera()
            elif event.key == pygame.K_e:
                try:
                    terrain_path, _ = self.export_map_layers()
                    self.show_status(f"Exported: {terrain_path.parent}", seconds=6.0)
                except (pygame.error, OSError, MemoryError) as error:
                    self.show_status(f"Export failed: {error}", seconds=8.0)
                    print(f"Export failed: {error}")

        elif event.type == pygame.MOUSEWHEEL:
            self.change_zoom(pygame.mouse.get_pos(), event.y)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 2:
            self.dragging = True
            self.last_mouse_pos = event.pos
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 2:
            self.dragging = False
            self.last_mouse_pos = None
        elif event.type == pygame.MOUSEMOTION:
            self.drag_camera(event.pos)
        return True

    def run(self) -> None:
        running = True
        while running:
            delta_seconds = self.clock.tick(FPS) / 1000.0
            for event in pygame.event.get():
                if not self.handle_event(event):
                    running = False
                    break

            self.keyboard_camera(delta_seconds)
            self.screen.fill((8, 15, 24))
            self.draw_map()
            self.draw_ui()
            pygame.display.flip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seeded Perlin isometric terrain generator")
    parser.add_argument("--seed", type=int, help="Generate a reproducible map")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        TerrainApp(seed=args.seed).run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
