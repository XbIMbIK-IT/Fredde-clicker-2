"""
Генеалогическое древо Фредиков — pygame edition (60 FPS)
==========================================================

Почему матплотлиб-версия лагала:
---------------------------------
Оригинал рисовал каждого фредика через `ax.imshow(...)` и на каждом кадре
двигал его через `set_extent`. Даже с blitting'ом и dirty-чекингом
matplotlib всё равно прогоняет каждое такое изменение через свой
Agg-рендерер и пересобирает composite — это тяжёлый путь, рассчитанный на
статичные графики, а не на десятки перемещающихся спрайтов 60 раз в
секунду. Больше оптимизаций внутри matplotlib для этого не выжать.

Что изменилось:
----------------
Вся отрисовка переехала на pygame (SDL2) — движок с настоящим
аппаратно-ускоренным blit'ом, тем же, на чём делают 2D-игры. При такой
модели отрисовка полусотни спрайтов на 60 fps — тривиальная задача.

Оптимизации:
- Спрайты рендерятся один раз и кешируются под конкретный размер в
  пикселях; пересчёт (smoothscale) происходит только когда реально
  меняется зум, а не каждый кадр.
- Текст (имя, поколение) рендерится один раз в текстуру, дальше только
  blit — рендер шрифта дорогой, blit почти бесплатный.
- Физика осталась векторизованной на numpy (O(n^2), но это никогда не
  было узким местом — для деревьев в сотни узлов это доли миллисекунды).
- Никакого полного redraw сцены на каждое событие мыши — только
  перерисовка кадра в общем цикле.

Зависимости:  pip install pygame numpy
Запуск:       python tree_view_pygame.py
"""

import math
import random

import numpy as np
import pygame

from fredde import freddies
from freddePhoto import generate_fredde


# ============================================================
#  ЦВЕТА / ТЕМА (в стиле Obsidian, тёмная)
# ============================================================
BG_COLOR       = (32, 34, 37)
PANEL_COLOR    = (43, 45, 49)
PANEL_HOVER    = (59, 61, 66)
EDGE_COLOR     = (90, 93, 99)
ARROW_COLOR    = (154, 160, 168)
TEXT_COLOR     = (220, 221, 222)
GEN_TEXT_COLOR = (200, 201, 202)
ACCENT_COLOR   = (114, 137, 218)
TOOLTIP_BG     = (43, 45, 49)
WHITE          = (255, 255, 255)

GENDER_LABELS = {
    "boy": "мальчик",
    "girl": "девочка",
    "is": "интерсекс",
    "cf": "чайлдфри",
}

# ============================================================
#  ФИЗИКА (те же формулы и параметры, что и в оригинале)
# ============================================================
DEFAULT_PARAMS = {
    "repulsion":   1.0,
    "spring_len":  1.5,
    "spring_k":    0.03,
    "gen_pull":    0.015,
    "center_pull": 0.02,
    "damping":     0.86,
    "jitter":      0.0,
    "dt":          0.7,
}

SLIDERS = [
    ("repulsion",   "Отталкивание узлов", 0.1, 3.0),
    ("spring_len",  "Длина связи",        0.5, 4.0),
    ("spring_k",    "Жёсткость связи",    0.0, 0.12),
    ("gen_pull",    "Тяга к поколению",   0.0, 0.15),
    ("center_pull", "Тяга к центру",      0.0, 0.02),
    ("damping",     "Затухание",          0.5, 0.98),
    ("jitter",      "Дрожание",           0.0, 0.05),
    ("dt",          "Скорость симуляции", 0.1, 1.5),
]

GEN_HEIGHT         = 2.6
NODE_RADIUS_WORLD  = 0.5
HIT_RADIUS         = NODE_RADIUS_WORLD * 1.45
EDGE_SHRINK        = NODE_RADIUS_WORLD * 0.95
ARROW_LEN          = 0.16
ARROW_WIDTH_DEG    = 22

SCREEN_W, SCREEN_H = 1300, 850
FPS = 60

REVEAL_FRAMES_PER_NODE = 3
REVEAL_FRAMES_PER_EDGE = 1

ZOOM_IN_FACTOR  = 1.0 / 0.9
ZOOM_OUT_FACTOR = 0.9
MIN_VIEW_SPAN_WORLD = 1.5
MAX_ZOOM_OUT_MULT   = 4.0

PANEL_W = 300
PANEL_MARGIN = 12
PANEL_EASE = 0.25


# ============================================================
#  СПРАЙТЫ
# ============================================================
def get_font(size, bold=False):
    for name in ("dejavusans", "arial", "segoeui", "notosans", "freesans"):
        try:
            f = pygame.font.SysFont(name, size, bold=bold)
            if f is not None:
                return f
        except Exception:
            continue
    return pygame.font.Font(None, size)


def to_pygame_surface(img):
    """PIL.Image или ndarray -> pygame.Surface с альфа-каналом."""
    if hasattr(img, "convert") and hasattr(img, "tobytes") and hasattr(img, "size"):
        pil_img = img.convert("RGBA")
        data = pil_img.tobytes()
        surf = pygame.image.fromstring(data, pil_img.size, "RGBA")
        return surf.convert_alpha()

    arr = np.asarray(img)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr, np.full_like(arr, 255)], axis=-1)
    elif arr.shape[-1] == 3:
        alpha = np.full(arr.shape[:2] + (1,), 255, dtype=arr.dtype)
        arr = np.concatenate([arr, alpha], axis=-1)
    arr = np.ascontiguousarray(arr.astype(np.uint8))
    h, w = arr.shape[:2]
    surf = pygame.image.frombuffer(arr.tobytes(), (w, h), "RGBA")
    return surf.convert_alpha()


def make_halo_surface(color, diameter=128, alpha=38):
    surf = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    pygame.draw.circle(surf, (*color, alpha), (diameter // 2, diameter // 2), diameter // 2)
    return surf


class ScaledCache:
    """Кеширует смасштабированную версию картинки, пересчитывая её
    только когда целевой размер в пикселях реально изменился (т.е.
    практически только при зуме, а не каждый кадр)."""

    __slots__ = ("raw", "world_w", "world_h", "cached_px", "cached_surf")

    def __init__(self, raw_surface, world_w, world_h):
        self.raw = raw_surface
        self.world_w = world_w
        self.world_h = world_h
        self.cached_px = None
        self.cached_surf = None

    def get(self, scale):
        w_px = max(1, int(round(self.world_w * scale)))
        h_px = max(1, int(round(self.world_h * scale)))
        if self.cached_px != (w_px, h_px):
            self.cached_surf = pygame.transform.smoothscale(self.raw, (w_px, h_px))
            self.cached_px = (w_px, h_px)
        return self.cached_surf


# ============================================================
#  ГРАФ
# ============================================================
def build_graph():
    nodes = list(freddies)
    node_index = {node: i for i, node in enumerate(nodes)}
    edges = []
    for child in nodes:
        for parent in getattr(child, "parents", []):
            if parent in node_index:
                edges.append((node_index[parent], node_index[child]))
    return nodes, node_index, edges


def tooltip_lines(node):
    gender = GENDER_LABELS.get(node.gender, node.gender)
    status = "жив" if node.alive else "мёртв"
    return [
        node.name,
        f"Статус: {status}",
        f"Поколение: {node.generation}",
        f"Возраст: {node.age}",
        f"Пол: {gender}",
        f"Редкость: {node.rarity}",
        f"Отпечаток: {node.genid}",
        f"Доминантность: {node.gendom}",
        f"Мутация: {node.mutrate}%",
    ]


# ============================================================
#  ПРОСТЫЕ UI-ВИДЖЕТЫ
# ============================================================
class Button:
    def __init__(self, rect, label, font, on_click):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.font = font
        self.on_click = on_click

    def draw(self, surface, offset=(0, 0)):
        r = self.rect.move(offset)
        hovered = r.collidepoint(pygame.mouse.get_pos())
        color = PANEL_HOVER if hovered else PANEL_COLOR
        pygame.draw.rect(surface, color, r, border_radius=8)
        txt = self.font.render(self.label, True, TEXT_COLOR)
        surface.blit(txt, txt.get_rect(center=r.center))

    def handle_click(self, pos, offset=(0, 0)):
        if self.rect.move(offset).collidepoint(pos):
            self.on_click()
            return True
        return False


class SliderWidget:
    def __init__(self, key, label, vmin, vmax, value, rect, font_label, font_value):
        self.key = key
        self.label = label
        self.vmin = vmin
        self.vmax = vmax
        self.value = value
        self.rect = pygame.Rect(rect)  # позиция track при полностью открытой панели
        self.font_label = font_label
        self.font_value = font_value
        self.dragging = False

    def _track_rect(self, offset):
        return self.rect.move(offset)

    def value_from_x(self, x, offset):
        r = self._track_rect(offset)
        t = (x - r.x) / max(1, r.w)
        t = min(1.0, max(0.0, t))
        return self.vmin + t * (self.vmax - self.vmin)

    def draw(self, surface, offset):
        r = self._track_rect(offset)
        label_y = r.y - 20
        lbl = self.font_label.render(self.label, True, TEXT_COLOR)
        surface.blit(lbl, (r.x, label_y))

        pygame.draw.rect(surface, PANEL_HOVER, r, border_radius=4)
        t = (self.value - self.vmin) / (self.vmax - self.vmin) if self.vmax > self.vmin else 0
        handle_x = r.x + t * r.w
        pygame.draw.circle(surface, ACCENT_COLOR, (int(handle_x), r.centery), r.h // 2 + 4)

        val_txt = self.font_value.render(f"{self.value:.3f}", True, TEXT_COLOR)
        surface.blit(val_txt, (r.right + 10, r.centery - val_txt.get_height() // 2))

    def try_grab(self, pos, offset):
        r = self._track_rect(offset).inflate(0, 16)
        if r.collidepoint(pos):
            self.dragging = True
            self.value = self.value_from_x(pos[0], offset)
            return True
        return False

    def drag_to(self, pos, offset):
        if self.dragging:
            self.value = self.value_from_x(pos[0], offset)

    def release(self):
        self.dragging = False


# ============================================================
#  ОСНОВНАЯ ПРОГРАММА
# ============================================================
def main():
    pygame.init()
    pygame.display.set_caption("Генеалогическое древо")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    font_name = get_font(14, bold=True)
    font_gen = get_font(11)
    font_ui = get_font(14)
    font_ui_small = get_font(11)
    font_tooltip = get_font(15)
    font_tooltip_bold = get_font(16, bold=True)
    font_title = get_font(20, bold=True)
    font_gear = get_font(18)

    nodes, node_index, edges = build_graph()
    n = len(nodes)
    if n == 0:
        print("Генеалогическое дерево пустое.")
        return

    parent_idx = np.array([e[0] for e in edges], dtype=int)
    child_idx = np.array([e[1] for e in edges], dtype=int)

    generations = {}
    for node in nodes:
        generations.setdefault(node.generation, []).append(node)
    gens_present = sorted(generations.keys())

    def gen_y(gen):
        return -gen * GEN_HEIGHT

    gen_target_y = np.array([gen_y(node.generation) for node in nodes], dtype=float)

    params = dict(DEFAULT_PARAMS)

    pos = np.zeros((n, 2))
    prev_pos = np.zeros((n, 2))
    vel = np.zeros((n, 2))
    dragged_mask = np.zeros(n, dtype=bool)

    def layout_by_generation(spring_len, spread_x, spread_y):
        for gen, gnodes in generations.items():
            width = max(len(gnodes), 1)
            for i, node in enumerate(gnodes):
                idx = node_index[node]
                pos[idx, 0] = (i - (width - 1) / 2) * spring_len * 1.3 + random.uniform(-spread_x, spread_x)
                pos[idx, 1] = gen_y(gen) + random.uniform(-spread_y, spread_y)
                vel[idx] = 0.0

    layout_by_generation(DEFAULT_PARAMS["spring_len"], 0.4, 0.3)
    prev_pos[:] = pos

    max_width = max((len(v) for v in generations.values()), default=1)
    home_span_x = max(max_width * DEFAULT_PARAMS["spring_len"], 3.5) * 2 + 6.0
    home_span_y = (gen_y(gens_present[0]) - gen_y(gens_present[-1])) + 2.5 + 3.3
    home_cx = 0.0
    home_cy = (gen_y(gens_present[0]) + gen_y(gens_present[-1])) / 2.0
    home_scale = min(SCREEN_W / home_span_x, SCREEN_H / home_span_y)

    MIN_SCALE = min(SCREEN_W, SCREEN_H) / (max(home_span_x, home_span_y) * MAX_ZOOM_OUT_MULT)
    MAX_SCALE = min(SCREEN_W, SCREEN_H) / MIN_VIEW_SPAN_WORLD

    camera = {"cx": home_cx, "cy": home_cy, "scale": home_scale}

    # ---------- спрайты, halo, текст (рендерятся один раз) ----------
    sprite_cache = []
    halo_cache = []
    node_colors = []
    for i, node in enumerate(nodes):
        color = tuple(max(0, min(255, int(c))) for c in node.color[:3])
        node_colors.append(color)
        try:
            surf = to_pygame_surface(generate_fredde(node))
        except Exception as e:
            print(f"Не удалось сгенерировать спрайт для {node.name}: {e}")
            surf = None

        if surf is not None:
            w, h = surf.get_size()
            ratio = (w / h) if h else 1.0
            hw = NODE_RADIUS_WORLD * (ratio if ratio >= 1 else 1.0)
            hh = NODE_RADIUS_WORLD * (1.0 if ratio >= 1 else 1.0 / ratio)
            sprite_cache.append((ScaledCache(surf, 2 * hw, 2 * hh), hw, hh))
        else:
            sprite_cache.append((None, NODE_RADIUS_WORLD, NODE_RADIUS_WORLD))

        halo_d = NODE_RADIUS_WORLD * 1.35 * 2
        halo_cache.append(ScaledCache(make_halo_surface(color), halo_d, halo_d))

    name_surfs = [font_name.render(node.name, True, TEXT_COLOR) for node in nodes]
    gen_surfs = [font_gen.render(f"Поколение {node.generation}", True, GEN_TEXT_COLOR) for node in nodes]

    # ---------- появление узлов/связей по очереди ----------
    visible = np.zeros(n, dtype=bool)
    reveal = {"active": False, "frame": 0, "node_order": [], "node_i": 0, "edge_order": [], "edge_i": 0}
    revealed_parent = np.array([], dtype=int)
    revealed_child = np.array([], dtype=int)

    def start_reveal():
        order = list(range(n))
        random.shuffle(order)
        eorder = list(range(len(edges)))
        random.shuffle(eorder)
        reveal.update(active=True, frame=0, node_order=order, node_i=0, edge_order=eorder, edge_i=0)
        visible[:] = False
        nonlocal revealed_parent, revealed_child
        revealed_parent = np.array([], dtype=int)
        revealed_child = np.array([], dtype=int)

    def advance_reveal():
        nonlocal revealed_parent, revealed_child
        if not reveal["active"]:
            return
        reveal["frame"] += 1
        if reveal["node_i"] < n:
            if reveal["frame"] % REVEAL_FRAMES_PER_NODE == 0:
                idx = reveal["node_order"][reveal["node_i"]]
                visible[idx] = True
                reveal["node_i"] += 1
        elif reveal["edge_i"] < len(edges):
            if reveal["frame"] % REVEAL_FRAMES_PER_EDGE == 0:
                reveal["edge_i"] += 1
                shown = reveal["edge_order"][:reveal["edge_i"]]
                revealed_parent = parent_idx[shown]
                revealed_child = child_idx[shown]
        else:
            reveal["active"] = False

    def reveal_all_immediately():
        nonlocal revealed_parent, revealed_child
        reveal["active"] = False
        visible[:] = True
        revealed_parent = parent_idx
        revealed_child = child_idx

    # ---------- физика (векторизовано, как в оригинале) ----------
    def compute_forces():
        diff = pos[:, None, :] - pos[None, :, :]
        dist_sq = np.sum(diff * diff, axis=-1)
        np.fill_diagonal(dist_sq, np.inf)
        dist = np.sqrt(dist_sq)
        dist_safe = np.where(dist < 1e-3, 1e-3, dist)

        repel = params["repulsion"] / np.where(dist_sq < 1e-6, 1e-6, dist_sq)
        forces = np.stack([
            np.sum(diff[..., 0] / dist_safe * repel, axis=1),
            np.sum(diff[..., 1] / dist_safe * repel, axis=1),
        ], axis=-1)

        if len(edges):
            pdiff = pos[child_idx] - pos[parent_idx]
            edist = np.sqrt(np.sum(pdiff * pdiff, axis=1))
            edist_safe = np.where(edist < 1e-3, 1e-3, edist)
            stretch = edist_safe - params["spring_len"]
            fmag = params["spring_k"] * stretch
            efx = pdiff[:, 0] / edist_safe * fmag
            efy = pdiff[:, 1] / edist_safe * fmag
            np.add.at(forces[:, 0], parent_idx, efx)
            np.add.at(forces[:, 1], parent_idx, efy)
            np.add.at(forces[:, 0], child_idx, -efx)
            np.add.at(forces[:, 1], child_idx, -efy)

        forces[:, 1] += (gen_target_y - pos[:, 1]) * params["gen_pull"]
        forces[:, 0] += -pos[:, 0] * params["center_pull"]
        if params["jitter"] > 0:
            forces += np.random.uniform(-params["jitter"], params["jitter"], size=(n, 2))
        return forces

    def step_physics():
        forces = compute_forces()
        free = ~dragged_mask
        dt = params["dt"]
        vel[free] = (vel[free] + forces[free] * dt) * params["damping"]
        pos[free] += vel[free] * dt

    # ---------- камера ----------
    def world_to_screen(x, y):
        sx = SCREEN_W / 2 + (x - camera["cx"]) * camera["scale"]
        sy = SCREEN_H / 2 - (y - camera["cy"]) * camera["scale"]
        return sx, sy

    def screen_to_world(sx, sy):
        x = (sx - SCREEN_W / 2) / camera["scale"] + camera["cx"]
        y = -(sy - SCREEN_H / 2) / camera["scale"] + camera["cy"]
        return x, y

    def zoom_at(screen_pos, factor):
        old_scale = camera["scale"]
        new_scale = min(MAX_SCALE, max(MIN_SCALE, old_scale * factor))
        if new_scale == old_scale:
            return
        wx, wy = screen_to_world(*screen_pos)
        camera["scale"] = new_scale
        sx, sy = screen_pos
        camera["cx"] = wx - (sx - SCREEN_W / 2) / new_scale
        camera["cy"] = wy + (sy - SCREEN_H / 2) / new_scale

    def go_home():
        camera["cx"], camera["cy"], camera["scale"] = home_cx, home_cy, home_scale

    def find_node_at(wx, wy):
        dx = pos[:, 0] - wx
        dy = pos[:, 1] - wy
        dist = np.hypot(dx, dy)
        dist = np.where(visible, dist, np.inf)
        i = int(np.argmin(dist))
        return i if dist[i] < HIT_RADIUS else None

    # ---------- кнопки ----------
    def regenerate():
        layout_by_generation(params["spring_len"], 0.5, 0.4)
        prev_pos[:] = pos
        vel[:] = np.random.uniform(-0.6, 0.6, size=(n, 2))
        go_home()
        start_reveal()

    def do_reset_sliders():
        for s in sliders:
            s.value = DEFAULT_PARAMS[s.key]
            params[s.key] = s.value

    regen_button = Button((SCREEN_W - 190, SCREEN_H - 60, 170, 42), "⟳ Пересобрать", font_ui, regenerate)
    home_button = Button((20, SCREEN_H - 60, 100, 42), "⌂ Вид", font_ui, go_home)
    gear_button = Button((SCREEN_W - 54, 16, 38, 38), "⚙", font_gear, lambda: None)

    # ---------- панель настроек ----------
    panel_open_x = SCREEN_W - PANEL_W - PANEL_MARGIN
    panel_closed_x = SCREEN_W + 20
    panel_state = {"x": panel_closed_x, "target_x": panel_closed_x, "open": False}

    sliders = []
    row_top = 70
    row_gap = 62
    for i, (key, label, vmin, vmax) in enumerate(SLIDERS):
        y = row_top + i * row_gap
        sliders.append(SliderWidget(key, label, vmin, vmax, params[key],
                                     (panel_open_x + 20, y, PANEL_W - 90, 12),
                                     font_ui_small, font_ui_small))

    reset_button = Button((panel_open_x + 20, row_top + len(SLIDERS) * row_gap + 10, PANEL_W - 40, 38),
                           "Сбросить настройки", font_ui_small, do_reset_sliders)

    def toggle_panel():
        panel_state["open"] = not panel_state["open"]
        panel_state["target_x"] = panel_open_x if panel_state["open"] else panel_closed_x

    gear_button.on_click = toggle_panel

    # ---------- отрисовка ----------
    def draw_edges():
        if len(revealed_parent) == 0:
            return
        p = pos[revealed_parent]
        c = pos[revealed_child]
        vec = c - p
        dist = np.hypot(vec[:, 0], vec[:, 1])
        dist_safe = np.where(dist < 1e-6, 1e-6, dist)
        unit = vec / dist_safe[:, None]
        start = p + unit * EDGE_SHRINK
        end = c - unit * EDGE_SHRINK

        angle = np.arctan2(unit[:, 1], unit[:, 0])
        spread = math.radians(ARROW_WIDTH_DEG)
        left = end - ARROW_LEN * np.stack([np.cos(angle - spread), np.sin(angle - spread)], axis=1)
        right = end - ARROW_LEN * np.stack([np.cos(angle + spread), np.sin(angle + spread)], axis=1)

        for i in range(len(revealed_parent)):
            sx1, sy1 = world_to_screen(*start[i])
            sx2, sy2 = world_to_screen(*end[i])
            pygame.draw.line(screen, EDGE_COLOR, (sx1, sy1), (sx2, sy2), 2)

            lx, ly = world_to_screen(*left[i])
            rx, ry = world_to_screen(*right[i])
            pygame.draw.lines(screen, ARROW_COLOR, False, [(lx, ly), (sx2, sy2), (rx, ry)], 2)

    def draw_nodes(hovered_idx, dragging_idx):
        scale = camera["scale"]
        for i in range(n):
            if not visible[i]:
                continue
            wx, wy = pos[i]
            sx, sy = world_to_screen(wx, wy)
            if sx < -100 or sx > SCREEN_W + 100 or sy < -100 or sy > SCREEN_H + 100:
                continue  # вне экрана - не тратим blit

            is_active = (i == hovered_idx) or (i == dragging_idx)

            halo_surf = halo_cache[i].get(scale)
            screen.blit(halo_surf, halo_surf.get_rect(center=(sx, sy)))

            sc, hw, hh = sprite_cache[i]
            if sc is not None:
                img = sc.get(scale)
                screen.blit(img, img.get_rect(center=(sx, sy)))
                if is_active:
                    pygame.draw.circle(screen, ACCENT_COLOR, (int(sx), int(sy)),
                                        int(max(hw, hh) * scale), width=2)
            else:
                r = int(NODE_RADIUS_WORLD * scale)
                pygame.draw.circle(screen, node_colors[i], (int(sx), int(sy)), r)
                border = ACCENT_COLOR if is_active else WHITE
                pygame.draw.circle(screen, border, (int(sx), int(sy)), r, width=2)

            name_s = name_surfs[i]
            screen.blit(name_s, name_s.get_rect(midbottom=(sx, sy - (hh if sc else NODE_RADIUS_WORLD) * scale - 6)))
            gen_s = gen_surfs[i]
            screen.blit(gen_s, gen_s.get_rect(midtop=(sx, sy + (hh if sc else NODE_RADIUS_WORLD) * scale + 6)))

    def draw_tooltip(idx, mouse_pos):
        lines = tooltip_lines(nodes[idx])
        surfs = [font_tooltip_bold.render(lines[0], True, TEXT_COLOR)]
        surfs += [font_tooltip.render(l, True, TEXT_COLOR) for l in lines[1:]]
        w = max(s.get_width() for s in surfs) + 24
        line_h = font_tooltip.get_height() + 6
        h = line_h * len(surfs) + 20

        x = mouse_pos[0] + 18
        y = mouse_pos[1] + 18
        if x + w > SCREEN_W:
            x = mouse_pos[0] - w - 18
        if y + h > SCREEN_H:
            y = mouse_pos[1] - h - 18

        box = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(box, (*TOOLTIP_BG, 245), box.get_rect(), border_radius=10)
        pygame.draw.rect(box, ACCENT_COLOR, box.get_rect(), width=2, border_radius=10)
        for i, s in enumerate(surfs):
            box.blit(s, (12, 10 + i * line_h))
        screen.blit(box, (x, y))

    def draw_panel(offset_x):
        if offset_x >= SCREEN_W:
            return
        panel_rect = pygame.Rect(panel_open_x, 0, PANEL_W, SCREEN_H)
        panel_rect.x = offset_x
        pygame.draw.rect(screen, PANEL_COLOR, panel_rect)

        title = font_title.render("Параметры симуляции", True, TEXT_COLOR)
        screen.blit(title, (offset_x + 20, 20))

        dx = offset_x - panel_open_x
        for s in sliders:
            s.draw(screen, (dx, 0))
        reset_button.rect.x = panel_open_x + 20
        reset_button.draw(screen, (dx, 0))

    # ---------- главный цикл ----------
    dragging_node = None
    panning = False
    pan_start_screen = (0, 0)
    pan_start_cam = (0.0, 0.0)
    active_slider = None

    reveal_all_immediately()
    regenerate()

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = event.pos
                handled = (regen_button.handle_click((mx, my))
                           or home_button.handle_click((mx, my))
                           or gear_button.handle_click((mx, my)))

                if not handled and panel_state["x"] < SCREEN_W - 5:
                    dx = panel_state["x"] - panel_open_x
                    if reset_button.rect.move(dx, 0).collidepoint(mx, my):
                        reset_button.on_click()
                        handled = True
                    else:
                        for s in sliders:
                            if s.try_grab((mx, my), (dx, 0)):
                                params[s.key] = s.value
                                active_slider = s
                                handled = True
                                break

                if not handled:
                    wx, wy = screen_to_world(mx, my)
                    idx = find_node_at(wx, wy)
                    if idx is not None:
                        dragging_node = idx
                        dragged_mask[idx] = True
                        vel[idx] = 0.0
                    else:
                        panning = True
                        pan_start_screen = (mx, my)
                        pan_start_cam = (camera["cx"], camera["cy"])

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                if dragging_node is not None:
                    dragged_mask[dragging_node] = False
                    dragging_node = None
                panning = False
                if active_slider is not None:
                    active_slider.release()
                    active_slider = None

            elif event.type == pygame.MOUSEMOTION:
                if dragging_node is not None:
                    wx, wy = screen_to_world(*event.pos)
                    pos[dragging_node] = (wx, wy)
                elif panning:
                    dxp = event.pos[0] - pan_start_screen[0]
                    dyp = event.pos[1] - pan_start_screen[1]
                    camera["cx"] = pan_start_cam[0] - dxp / camera["scale"]
                    camera["cy"] = pan_start_cam[1] + dyp / camera["scale"]
                elif active_slider is not None:
                    dx = panel_state["x"] - panel_open_x
                    active_slider.drag_to(event.pos, (dx, 0))
                    params[active_slider.key] = active_slider.value

            elif event.type == pygame.MOUSEWHEEL:
                factor = ZOOM_IN_FACTOR if event.y > 0 else ZOOM_OUT_FACTOR
                zoom_at(mouse_pos, factor)

        # ---- физика и анимация появления ----
        prev_pos[:] = pos
        step_physics()
        advance_reveal()

        if panel_state["x"] != panel_state["target_x"]:
            panel_state["x"] += (panel_state["target_x"] - panel_state["x"]) * PANEL_EASE
            if abs(panel_state["target_x"] - panel_state["x"]) < 0.5:
                panel_state["x"] = panel_state["target_x"]

        hovered = None
        if dragging_node is None and not panning and active_slider is None:
            wx, wy = screen_to_world(*mouse_pos)
            hovered = find_node_at(wx, wy)

        # ---- отрисовка ----
        screen.fill(BG_COLOR)
        draw_edges()
        draw_nodes(hovered, dragging_node)

        title = font_title.render("Генеалогическое древо", True, TEXT_COLOR)
        screen.blit(title, title.get_rect(midtop=(SCREEN_W // 2, 14)))

        regen_button.draw(screen)
        home_button.draw(screen)
        gear_button.draw(screen)
        draw_panel(panel_state["x"])

        if hovered is not None:
            draw_tooltip(hovered, mouse_pos)

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


