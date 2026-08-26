import pygame
import random
import sys
from pathlib import Path


# ============================================================
# НАСТРОЙКИ
# ============================================================

WIDTH = 1920
HEIGHT = 1080

FPS = 60

MAP_WIDTH = 30
MAP_HEIGHT = 30

TERRAIN_PATH = Path("sprites/terrain/default")
PROP_PATH = Path("sprites/terrain/default/props")


# ============================================================
# РАЗМЕРЫ ИЗОМЕТРИЧЕСКОЙ СЕТКИ
# ============================================================

TILE_IMAGE_WIDTH = 1000
TILE_IMAGE_HEIGHT = 1000

TILE_STEP_X = 489
TILE_STEP_Y = 218


# ============================================================
# ПРОПЫ
# ============================================================

# Шанс появления пропа на каждой клетке
PROP_CHANCE = 0.12

# Максимальное количество пропов
MAX_PROPS = (MAP_HEIGHT * MAP_WIDTH)


# ============================================================
# КАМЕРА
# ============================================================

MIN_ZOOM = 0.15
MAX_ZOOM = 2.0

ZOOM_SPEED = 1.15

# Камера хранится в мировых координатах
camera_x = 0.0
camera_y = 0.0

zoom = 0.7

CAMERA_SPEED = 15


# ============================================================
# PYGAME
# ============================================================

pygame.init()

screen = pygame.display.set_mode(
    (WIDTH, HEIGHT)
)

pygame.display.set_caption(
    "Fredde Terrain Generator"
)

clock = pygame.time.Clock()


# ============================================================
# ЗАГРУЗКА ЛУЖАЕК
# ============================================================

tiles = []

for i in range(1, 10):

    path = TERRAIN_PATH / f"lujaika{i}.png"

    try:

        image = pygame.image.load(
            path
        ).convert_alpha()

        tiles.append(image)

        print(
            f"Загружена лужайка: {path}"
        )

    except Exception as e:

        print(
            f"Ошибка загрузки {path}: {e}"
        )


if not tiles:

    print(
        "ОШИБКА: не найдено ни одной лужайки!"
    )

    pygame.quit()
    sys.exit()


# ============================================================
# ЗАГРУЗКА ПРОПОВ
# ============================================================

props = []


if PROP_PATH.exists():

    for path in PROP_PATH.iterdir():

        if not path.is_file():
            continue

        if path.suffix.lower() != ".png":
            continue

        try:

            image = pygame.image.load(
                path
            ).convert_alpha()

            props.append({
                "name": path.stem,
                "image": image
            })

            print(
                f"Загружен проп: {path}"
            )

        except Exception as e:

            print(
                f"Ошибка загрузки пропа {path}: {e}"
            )

else:

    print(
        f"Папка пропов не найдена: {PROP_PATH}"
    )


# ============================================================
# КЭШ ЛУЖАЕК
# ============================================================

scaled_tiles = []

scaled_tiles_zoom = None


def update_scaled_tiles():

    global scaled_tiles
    global scaled_tiles_zoom

    # Если zoom не изменился,
    # масштабировать заново не нужно
    if scaled_tiles_zoom == zoom:

        return

    scaled_tiles = []

    for tile in tiles:

        width = max(
            1,
            round(
                tile.get_width() * zoom
            )
        )

        height = max(
            1,
            round(
                tile.get_height() * zoom
            )
        )

        scaled = pygame.transform.scale(
            tile,
            (width, height)
        )

        scaled_tiles.append(
            scaled
        )

    scaled_tiles_zoom = zoom


# ============================================================
# КЭШ ПРОПОВ
# ============================================================

scaled_props = []

scaled_props_zoom = None


def update_scaled_props():

    global scaled_props
    global scaled_props_zoom

    if scaled_props_zoom == zoom:

        return

    scaled_props = []

    for prop in props:

        image = prop["image"]

        width = max(
            1,
            round(
                image.get_width() * zoom
            )
        )

        height = max(
            1,
            round(
                image.get_height() * zoom
            )
        )

        scaled = pygame.transform.scale(
            image,
            (width, height)
        )

        scaled_props.append({
            "name": prop["name"],
            "image": scaled
        })

    scaled_props_zoom = zoom


# ============================================================
# ПЕРВОНАЧАЛЬНЫЙ КЭШ
# ============================================================

update_scaled_tiles()
update_scaled_props()


# ============================================================
# КАРТА
# ============================================================

terrain_map = []


def generate_map():

    global terrain_map

    terrain_map = []

    for y in range(MAP_HEIGHT):

        row = []

        for x in range(MAP_WIDTH):

            tile_id = random.randrange(
                len(tiles)
            )

            row.append(
                tile_id
            )

        terrain_map.append(
            row
        )


# ============================================================
# ПРОПЫ НА КАРТЕ
# ============================================================

map_props = []


def generate_props():

    global map_props

    map_props = []

    if not props:

        return

    # Все клетки карты
    cells = []

    for y in range(MAP_HEIGHT):

        for x in range(MAP_WIDTH):

            cells.append(
                (x+1, y+1)
            )

    # Перемешиваем клетки
    random.shuffle(cells)

    for x, y in cells:

        # Проверяем шанс появления
        if random.random() > PROP_CHANCE:

            continue

        # Выбираем случайный проп
        prop = random.choice(
            props
        )

        map_props.append({

            "x": x,
            "y": y,

            "prop": prop

        })

        # Максимальное количество
        if len(map_props) >= MAX_PROPS:

            break


# ============================================================
# СОЗДАЁМ ПЕРВУЮ КАРТУ
# ============================================================

generate_map()
generate_props()


# ============================================================
# WORLD -> SCREEN
# ============================================================

def world_to_screen(x, y):

    # --------------------------------------------------------
    # Положение клетки в мире
    # --------------------------------------------------------

    world_x = (
        (x - y) * TILE_STEP_X
    )

    world_y = (
        (x + y) * TILE_STEP_Y
    )

    # --------------------------------------------------------
    # Переводим мировые координаты
    # в экранные
    # --------------------------------------------------------

    screen_x = (
        WIDTH / 2
        + (world_x - camera_x) * zoom
    )

    screen_y = (
        HEIGHT / 2
        + (world_y - camera_y) * zoom
    )

    return (
        screen_x,
        screen_y
    )


# ============================================================
# ПОИСК ПРОПА В КЭШЕ
# ============================================================

def get_scaled_prop(name):

    for prop in scaled_props:

        if prop["name"] == name:

            return prop["image"]

    return None


# ============================================================
# ОТРИСОВКА
# ============================================================

def draw_map():

    if not terrain_map:

        return

    screen_rect = pygame.Rect(
        0,
        0,
        WIDTH,
        HEIGHT
    )

    # ========================================================
    # СОЗДАЁМ ВСЕ ОБЪЕКТЫ
    #
    # Чтобы лужайки и пропы имели
    # общий изометрический порядок.
    # ========================================================

    objects = []

    # --------------------------------------------------------
    # ЛУЖАЙКИ
    # --------------------------------------------------------

    for y in range(MAP_HEIGHT):

        for x in range(MAP_WIDTH):

            objects.append({

                "depth": x + y,

                "type": "tile",

                "x": x,
                "y": y,

                "tile_id":
                    terrain_map[y][x]

            })

    # --------------------------------------------------------
    # ПРОПЫ
    # --------------------------------------------------------

    for prop_data in map_props:

        x = prop_data["x"]
        y = prop_data["y"]

        objects.append({

            "depth": x + y,

            "type": "prop",

            "x": x,
            "y": y,

            "prop_name":
                prop_data["prop"]["name"]

        })

    # ========================================================
    # СОРТИРОВКА ПО ГЛУБИНЕ
    # ========================================================

    objects.sort(
        key=lambda obj: (
            obj["depth"],
            obj["y"],
            obj["x"]
        )
    )

    # ========================================================
    # ОТРИСОВКА
    # ========================================================

    for obj in objects:

        x = obj["x"]
        y = obj["y"]

        screen_x, screen_y = world_to_screen(
            x,
            y
        )

        # ----------------------------------------------------
        # ЛУЖАЙКА
        # ----------------------------------------------------

        if obj["type"] == "tile":

            tile_id = obj["tile_id"]

            tile = scaled_tiles[
                tile_id
            ]

            rect = tile.get_rect(
                center=(
                    round(screen_x),
                    round(screen_y)
                )
            )

            # Не рисуем то,
            # что полностью за экраном
            if not screen_rect.colliderect(
                rect
            ):

                continue

            screen.blit(
                tile,
                rect
            )

        # ----------------------------------------------------
        # ПРОП
        # ----------------------------------------------------

        elif obj["type"] == "prop":

            prop_image = get_scaled_prop(
                obj["prop_name"]
            )

            if prop_image is None:

                continue

            # ------------------------------------------------
            # Проп стоит "на земле".
            #
            # Поэтому его нижняя часть находится
            # примерно в центре клетки.
            # ------------------------------------------------

            prop_y = (
                screen_y
                - 30 * zoom
            )

            rect = prop_image.get_rect(
                midbottom=(
                    round(screen_x),
                    round(prop_y)
                )
            )

            if not screen_rect.colliderect(
                rect
            ):

                continue

            screen.blit(
                prop_image,
                rect
            )


# ============================================================
# ZOOM
# ============================================================

def change_zoom(
    mouse_pos,
    wheel
):

    global zoom
    global camera_x
    global camera_y

    mouse_x, mouse_y = mouse_pos

    # --------------------------------------------------------
    # Точка мира под курсором ДО zoom
    # --------------------------------------------------------

    world_mouse_x = (
        camera_x
        + (
            mouse_x - WIDTH / 2
        ) / zoom
    )

    world_mouse_y = (
        camera_y
        + (
            mouse_y - HEIGHT / 2
        ) / zoom
    )

    old_zoom = zoom

    # --------------------------------------------------------
    # Меняем масштаб
    # --------------------------------------------------------

    if wheel > 0:

        zoom *= ZOOM_SPEED

    else:

        zoom /= ZOOM_SPEED

    zoom = max(
        MIN_ZOOM,
        min(
            MAX_ZOOM,
            zoom
        )
    )

    # --------------------------------------------------------
    # Сохраняем точку под мышью
    # --------------------------------------------------------

    if zoom != old_zoom:

        camera_x = (
            world_mouse_x
            - (
                mouse_x - WIDTH / 2
            ) / zoom
        )

        camera_y = (
            world_mouse_y
            - (
                mouse_y - HEIGHT / 2
            ) / zoom
        )

        # Пересоздаём кэш
        update_scaled_tiles()
        update_scaled_props()


# ============================================================
# ПЕРЕМЕЩЕНИЕ КАМЕРЫ МЫШЬЮ
# ============================================================

dragging = False

last_mouse_pos = None


def start_drag(pos):

    global dragging
    global last_mouse_pos

    dragging = True

    last_mouse_pos = pos


def stop_drag():

    global dragging
    global last_mouse_pos

    dragging = False

    last_mouse_pos = None


def drag_camera(pos):

    global camera_x
    global camera_y
    global last_mouse_pos

    if not dragging:

        return

    if last_mouse_pos is None:

        last_mouse_pos = pos

        return

    old_x, old_y = last_mouse_pos

    new_x, new_y = pos

    dx = new_x - old_x
    dy = new_y - old_y

    # Переводим движение мыши
    # из экранных координат
    # в мировые

    camera_x -= dx / zoom
    camera_y -= dy / zoom

    last_mouse_pos = pos


# ============================================================
# ДВИЖЕНИЕ КАМЕРЫ КЛАВИАТУРОЙ
# ============================================================

def keyboard_camera():

    global camera_x
    global camera_y

    keys = pygame.key.get_pressed()

    speed = CAMERA_SPEED / zoom

    if (
        keys[pygame.K_a]
        or keys[pygame.K_LEFT]
    ):

        camera_x -= speed

    if (
        keys[pygame.K_d]
        or keys[pygame.K_RIGHT]
    ):

        camera_x += speed

    if (
        keys[pygame.K_w]
        or keys[pygame.K_UP]
    ):

        camera_y -= speed

    if (
        keys[pygame.K_s]
        or keys[pygame.K_DOWN]
    ):

        camera_y += speed


# ============================================================
# UI
# ============================================================

font = pygame.font.Font(
    None,
    24
)


def draw_ui():

    text = (
        f"Zoom: {zoom:.2f}    "
        f"СКМ — камера    "
        f"Колесо — zoom    "
        f"WASD — движение    "
        f"SPACE — новая карта    "
        f"Пропов: {len(map_props)}"
    )

    surface = font.render(
        text,
        True,
        (255, 255, 255)
    )

    background = pygame.Surface(
        (
            surface.get_width() + 20,
            surface.get_height() + 10
        ),
        pygame.SRCALPHA
    )

    background.fill(
        (0, 0, 0, 180)
    )

    screen.blit(
        background,
        (5, 5)
    )

    screen.blit(
        surface,
        (15, 10)
    )


# ============================================================
# ОСНОВНОЙ ЦИКЛ
# ============================================================

running = True


while running:

    clock.tick(FPS)

    # ========================================================
    # EVENTS
    # ========================================================

    for event in pygame.event.get():

        # ----------------------------------------------------
        # Выход
        # ----------------------------------------------------

        if event.type == pygame.QUIT:

            running = False

        # ----------------------------------------------------
        # Клавиатура
        # ----------------------------------------------------

        elif event.type == pygame.KEYDOWN:

            # Новая карта
            if event.key == pygame.K_SPACE:

                generate_map()
                generate_props()

            # Выход
            elif event.key == pygame.K_ESCAPE:

                running = False

        # ----------------------------------------------------
        # Zoom
        # ----------------------------------------------------

        elif event.type == pygame.MOUSEWHEEL:

            change_zoom(
                pygame.mouse.get_pos(),
                event.y
            )

        # ----------------------------------------------------
        # Нажатие мыши
        # ----------------------------------------------------

        elif event.type == pygame.MOUSEBUTTONDOWN:

            # Средняя кнопка
            if event.button == 2:

                start_drag(
                    event.pos
                )

        # ----------------------------------------------------
        # Отпускание мыши
        # ----------------------------------------------------

        elif event.type == pygame.MOUSEBUTTONUP:

            if event.button == 2:

                stop_drag()

        # ----------------------------------------------------
        # Движение мыши
        # ----------------------------------------------------

        elif event.type == pygame.MOUSEMOTION:

            drag_camera(
                event.pos
            )

    # ========================================================
    # КАМЕРА
    # ========================================================

    keyboard_camera()

    # ========================================================
    # ОТРИСОВКА
    # ========================================================

    screen.fill(
        (0, 0, 0)
    )

    draw_map()

    draw_ui()

    pygame.display.flip()


# ============================================================
# ВЫХОД
# ============================================================

pygame.quit()
sys.exit()