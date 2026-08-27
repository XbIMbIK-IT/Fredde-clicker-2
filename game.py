import pygame
import sys
import time

from fredde import freddies, Fredde
from sex import try_sex
from simulation import step
from freddePhoto import generate_fredde


# ============================================================
# НАСТРОЙКИ ИГРЫ
# ============================================================

WIDTH = 1300
HEIGHT = 800
FPS = 60

# Экономика
CLICK_POINTS = 1

FOOD_START = 20
POINTS_START = 0
DOLLARS_START = 0

FOOD_PRICE = 5
FOOD_BUY_AMOUNT = 10

FREDDE_FOOD_COST = 10
FREDDE_SELL_PRICE = 25

# Сколько еды появляется пассивно
# за каждого МЁРТВОГО Fredde
FOOD_PER_DEAD_PER_SECOND = 0.2

# Сколько времени занимает один игровой год
YEAR_LENGTH = 30


# ============================================================
# ЦВЕТА
# ============================================================

BG = (25, 27, 30)
PANEL = (38, 40, 45)
PANEL_HOVER = (55, 58, 65)

WHITE = (240, 240, 240)
GRAY = (150, 150, 150)

YELLOW = (240, 190, 50)
GREEN = (70, 200, 100)
RED = (220, 70, 70)
BLUE = (80, 140, 230)
ORANGE = (230, 140, 50)


# ============================================================
# PYGAME
# ============================================================

pygame.init()

fullscreen = False
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Fredde")

clock = pygame.time.Clock()


# Шрифты
font_big = pygame.font.Font(None, 42)
font_medium = pygame.font.Font(None, 30)
font_small = pygame.font.Font(None, 23)
font_tiny = pygame.font.Font(None, 19)


# ============================================================
# РЕСУРСЫ
# ============================================================

points = POINTS_START
dollars = DOLLARS_START
food = FOOD_START

selected_fredde = None
selected_parent1 = None
selected_parent2 = None

# Состояние интерфейса
current_tab = "alive"       # "alive" или "dead"
list_scroll = 0
list_rect = pygame.Rect(310, 145, 430, HEIGHT - 215)
TAB_HEIGHT = 42

message = "Добро пожаловать в Fredde!"

game_year = 1
last_year_time = time.time()


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

def draw_text(text, font, color, x, y, center=False):
    surface = font.render(str(text), True, color)

    if center:
        rect = surface.get_rect(center=(x, y))
    else:
        rect = surface.get_rect(topleft=(x, y))

    screen.blit(surface, rect)


def button(rect, text, color, font=font_small):
    mouse = pygame.mouse.get_pos()

    if rect.collidepoint(mouse):
        draw_color = tuple(min(255, c + 20) for c in color)
    else:
        draw_color = color

    pygame.draw.rect(
        screen,
        draw_color,
        rect,
        border_radius=8
    )

    pygame.draw.rect(
        screen,
        WHITE,
        rect,
        2,
        border_radius=8
    )

    draw_text(
        text,
        font,
        WHITE,
        rect.centerx,
        rect.centery,
        center=True
    )


def alive_freddies():
    return [f for f in freddies if f.alive]


def dead_freddies():
    return [f for f in freddies if not f.alive]


def visible_freddies():
    """Fredde для текущей вкладки."""
    if current_tab == "alive":
        return alive_freddies()
    return dead_freddies()


def toggle_fullscreen():
    global screen, fullscreen
    fullscreen = not fullscreen

    if fullscreen:
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)


def clamp_scroll(items_count):
    global list_scroll
    visible_rows = max(1, (list_rect.height - TAB_HEIGHT) // 85)
    max_scroll = max(0, items_count - visible_rows)
    list_scroll = max(0, min(list_scroll, max_scroll))


def get_fredde_image(fred, size=110):
    """
    Генерирует Pygame-картинку Fredde.
    """

    try:
        image = generate_fredde(fred)

        data = image.tobytes()

        surface = pygame.image.fromstring(
            data,
            image.size,
            "RGBA"
        ).convert_alpha()

        surface = pygame.transform.smoothscale(
            surface,
            (size, size)
        )

        return surface

    except Exception as e:
        print("Ошибка генерации Fredde:", e)
        return None


def click():
    global points

    points += CLICK_POINTS


def buy_food():
    global points
    global food

    if points < FOOD_PRICE:
        set_message("Недостаточно поинтов!")

        return

    points -= FOOD_PRICE
    food += FOOD_BUY_AMOUNT

    set_message(
        f"Куплено {FOOD_BUY_AMOUNT} еды!"
    )


def buy_fredde():
    global food

    if food < FREDDE_FOOD_COST:
        set_message(
            "Недостаточно еды для создания Fredde!"
        )

        return

    food -= FREDDE_FOOD_COST

    new_fredde = Fredde(
        name=f"Fredde #{len(freddies) + 1}",
        age=1
    )

    set_message(
        f"Создан новый Fredde: {new_fredde.name}"
    )


def sell_fredde(fred):
    global dollars

    if fred is None:
        return

    if not fred.alive:
        set_message(
            "Мёртвого Fredde продавать нельзя!"
        )

        return

    dollars += FREDDE_SELL_PRICE

    fred.alive = False

    set_message(
        f"{fred.name} продан за ${FREDDE_SELL_PRICE}"
    )


def reproduce(parent1, parent2):
    global food

    if parent1 is None or parent2 is None:
        set_message(
            "Выбери двух родителей!"
        )

        return

    if food < FREDDE_FOOD_COST:
        set_message(
            "Недостаточно еды!"
        )

        return

    baby, result = try_sex(
        parent1,
        parent2
    )

    if baby is not None:
        food -= FREDDE_FOOD_COST

        set_message(
            f"Рождение: {baby.name}"
        )

    else:
        set_message(result)


def set_message(text):
    global message

    message = text


# ============================================================
# ПАССИВНАЯ ЕДА
# ============================================================

last_food_time = time.time()


def passive_food():
    global food
    global last_food_time

    current = time.time()

    if current - last_food_time >= 1:

        dead_count = len(dead_freddies())

        food += dead_count * FOOD_PER_DEAD_PER_SECOND

        last_food_time = current


# ============================================================
# ИГРОВОЙ ГОД
# ============================================================

def next_year():
    global game_year

    old_dead = len(dead_freddies())

    step(freddies)

    new_dead = len(dead_freddies())

    game_year += 1

    if new_dead > old_dead:
        set_message(
            f"Прошёл год. Умерло Fredde: {new_dead - old_dead}"
        )
    else:
        set_message(
            "Прошёл ещё один год."
        )


# ============================================================
# КНОПКИ
# ============================================================

click_button = pygame.Rect(
    30,
    130,
    240,
    70
)

buy_food_button = pygame.Rect(
    30,
    220,
    240,
    55
)

buy_fredde_button = pygame.Rect(
    30,
    290,
    240,
    55
)

year_button = pygame.Rect(
    30,
    360,
    240,
    55
)

reproduce_button = pygame.Rect(
    30,
    430,
    240,
    55
)

sell_button = pygame.Rect(
    30,
    500,
    240,
    55
)

# Кнопки вкладок и полноэкранного режима.
# Их положение обновляется каждый кадр, поэтому работают и после resize.
alive_tab_button = pygame.Rect(310, 145, 140, TAB_HEIGHT)
dead_tab_button = pygame.Rect(450, 145, 140, TAB_HEIGHT)
fullscreen_button = pygame.Rect(690, 145, 50, TAB_HEIGHT)


# ============================================================
# ОСНОВНОЙ ЦИКЛ
# ============================================================

running = True

while running:

    clock.tick(FPS)

    passive_food()

    # --------------------------------------------------------
    # СОБЫТИЯ
    # --------------------------------------------------------

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

        # Изменение размера окна
        elif event.type == pygame.VIDEORESIZE and not fullscreen:
            # Pygame при resize отдаёт новое окно; интерфейс ниже
            # использует актуальные screen.get_width()/get_height().
            pass

        # Клавиши
        elif event.type == pygame.KEYDOWN:

            # F11 — полноэкранный / оконный режим
            if event.key == pygame.K_F11:
                toggle_fullscreen()

            # ESC — выйти из fullscreen
            elif event.key == pygame.K_ESCAPE and fullscreen:
                toggle_fullscreen()

            # Стрелки — прокрутка списка
            elif event.key == pygame.K_DOWN:
                list_scroll += 1
                clamp_scroll(len(visible_freddies()))

            elif event.key == pygame.K_UP:
                list_scroll -= 1
                clamp_scroll(len(visible_freddies()))

        # Колесо мыши — прокрутка списка
        elif event.type == pygame.MOUSEWHEEL:
            mouse_pos = pygame.mouse.get_pos()

            if list_rect.collidepoint(mouse_pos):
                list_scroll -= event.y
                clamp_scroll(len(visible_freddies()))

        # ЛКМ
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:

            pos = event.pos

            # Клик — поинты
            if click_button.collidepoint(pos):
                click()

            # Купить еду
            elif buy_food_button.collidepoint(pos):
                buy_food()

            # Создать Fredde
            elif buy_fredde_button.collidepoint(pos):
                buy_fredde()

            # Следующий год
            elif year_button.collidepoint(pos):
                next_year()

            # Размножение
            elif reproduce_button.collidepoint(pos):
                reproduce(
                    selected_parent1,
                    selected_parent2
                )

            # Продажа
            elif sell_button.collidepoint(pos):
                sell_fredde(selected_fredde)

            # Вкладка ЖИВЫЕ
            elif alive_tab_button.collidepoint(pos):
                current_tab = "alive"
                list_scroll = 0

            # Вкладка МЁРТВЫЕ
            elif dead_tab_button.collidepoint(pos):
                current_tab = "dead"
                list_scroll = 0

            # Кнопка fullscreen
            elif fullscreen_button.collidepoint(pos):
                toggle_fullscreen()

            # Выбор Fredde из текущего списка
            elif list_rect.collidepoint(pos):

                items = visible_freddies()

                # Область карточек начинается ниже вкладок
                cards_y = list_rect.y + TAB_HEIGHT

                for visible_i, fred in enumerate(
                    items[list_scroll:]
                ):

                    y = cards_y + visible_i * item_h

                    if y > list_rect.bottom:
                        break

                    rect = pygame.Rect(
                        list_rect.x,
                        y,
                        list_rect.width,
                        70
                    )

                    if rect.collidepoint(pos):

                        selected_fredde = fred

                        # Родителями можно выбирать только живых
                        if fred.alive:

                            if selected_parent1 is None:
                                selected_parent1 = fred
                                set_message(
                                    f"Родитель 1: {fred.name}"
                                )

                            elif selected_parent2 is None:
                                selected_parent2 = fred
                                set_message(
                                    f"Родитель 2: {fred.name}"
                                )

                            else:
                                selected_parent1 = fred
                                selected_parent2 = None
                                set_message(
                                    f"Родитель 1: {fred.name}"
                                )
                        else:
                            set_message(
                                f"Выбран мёртвый Fredde: {fred.name}"
                            )

                        break


    # --------------------------------------------------------
    # ФОН
    # --------------------------------------------------------

    screen.fill(BG)


    # ========================================================
    # ВЕРХНЯЯ ПАНЕЛЬ РЕСУРСОВ
    # ========================================================

    pygame.draw.rect(
        screen,
        PANEL,
        (0, 0, WIDTH, 90)
    )

    draw_text(
        f"🟡 Поинты: {int(points)}",
        font_medium,
        YELLOW,
        30,
        25
    )

    draw_text(
        f"💵 Доллары: ${int(dollars)}",
        font_medium,
        GREEN,
        300,
        25
    )

    draw_text(
        f"🍖 Еда: {int(food)}",
        font_medium,
        ORANGE,
        570,
        25
    )

    draw_text(
        f"🧬 Fredde: {len(alive_freddies())}/{len(freddies)}",
        font_medium,
        BLUE,
        max(760, - 10),
        25
    )

    draw_text(
        f"Год: {game_year}",
        font_medium,
        WHITE,
        max(1050, - 250),
        25
    )


    # ========================================================
    # ЛЕВАЯ ПАНЕЛЬ
    # ========================================================

    pygame.draw.rect(
        screen,
        PANEL,
        (0, 90, 290, HEIGHT - 90)
    )

    draw_text(
        "УПРАВЛЕНИЕ",
        font_big,
        WHITE,
        30,
        105
    )

    button(
        click_button,
        f"КЛИК +{CLICK_POINTS}",
        YELLOW,
        font_medium
    )

    button(
        buy_food_button,
        f"Купить еду (${FOOD_PRICE})",
        ORANGE
    )

    button(
        buy_fredde_button,
        f"Создать Fredde ({FREDDE_FOOD_COST} 🍖)",
        BLUE
    )

    button(
        year_button,
        "Следующий год",
        GREEN
    )

    button(
        reproduce_button,
        "Размножить",
        (140, 90, 200)
    )

    button(
        sell_button,
        f"Продать (+${FREDDE_SELL_PRICE})",
        RED
    )


    # ========================================================
    # СПИСОК FREDDE
    # ========================================================

    screen_w = screen.get_width()
    screen_h = screen.get_height()

    # Левая панель остаётся фиксированной, список расширяется.
    list_x = 310
    info_x = max(770, int(screen_w * 0.60))
    list_width = max(430, info_x - list_x - 25)

    # Правая панель
    pygame.draw.rect(
        screen,
        PANEL,
        (
            info_x,
            90,
            screen_w - info_x,
            screen_h - 90
        )
    )

    # Заголовок
    draw_text(
        "FREDDIES",
        font_big,
        WHITE,
        list_x,
        105
    )

    # Область списка
    list_rect = pygame.Rect(
        list_x,
        145,
        list_width,
        screen_h - 215
    )

    alive_tab_button = pygame.Rect(
        list_x,
        145,
        140,
        TAB_HEIGHT
    )

    dead_tab_button = pygame.Rect(
        list_x + 140,
        145,
        140,
        TAB_HEIGHT
    )

    fullscreen_button = pygame.Rect(
        list_x + list_width - 50,
        145,
        50,
        TAB_HEIGHT
    )

    # Вкладки
    button(
        alive_tab_button,
        f"ЖИВЫЕ ({len(alive_freddies())})",
        GREEN if current_tab == "alive" else PANEL,
        font_tiny
    )

    button(
        dead_tab_button,
        f"МЁРТВЫЕ ({len(dead_freddies())})",
        RED if current_tab == "dead" else PANEL,
        font_tiny
    )

    button(
        fullscreen_button,
        "⛶",
        BLUE,
        font_medium
    )

    # Список текущей вкладки
    items = visible_freddies()
    clamp_scroll(len(items))

    cards_y = list_rect.y + TAB_HEIGHT
    item_h = 85

    # Скрываем карточки за пределами списка
    old_clip = screen.get_clip()
    screen.set_clip(
        pygame.Rect(
            list_rect.x,
            cards_y,
            list_rect.width,
            list_rect.bottom - cards_y
        )
    )

    for visible_i, fred in enumerate(items[list_scroll:]):

        y = cards_y + visible_i * item_h

        if y > list_rect.bottom:
            break

        rect = pygame.Rect(
            list_rect.x,
            y,
            list_rect.width,
            70
        )

        # Цвет карточки
        if fred == selected_fredde:
            color = (65, 70, 85)
        else:
            color = PANEL

        pygame.draw.rect(
            screen,
            color,
            rect,
            border_radius=8
        )

        # Рамка родителя
        if fred == selected_parent1:
            pygame.draw.rect(
                screen,
                YELLOW,
                rect,
                3,
                border_radius=8
            )

        elif fred == selected_parent2:
            pygame.draw.rect(
                screen,
                GREEN,
                rect,
                3,
                border_radius=8
            )

        # Спрайт
        image = get_fredde_image(fred, 60)

        if image:
            screen.blit(
                image,
                (rect.x + 5, rect.y + 5)
            )

        # Имя
        draw_text(
            fred.name,
            font_medium,
            WHITE,
            rect.x + 75,
            rect.y + 8
        )

        # Информация
        status = "ЖИВ" if fred.alive else "МЁРТВ"

        draw_text(
            f"{status} | Возраст: {fred.age} | "
            f"Gen: {fred.generation}",
            font_tiny,
            GRAY,
            rect.x + 75,
            rect.y + 38
        )

    screen.set_clip(old_clip)

    # Подсказка о прокрутке
    if len(items) > 1:
        draw_text(
            "Колесо мыши / ↑ ↓ — прокрутка",
            font_tiny,
            GRAY,
            list_x,
            screen_h - 42
        )


    # ========================================================
    # ИНФОРМАЦИЯ СПРАВА
    # ========================================================

    draw_text(
        "ИНФОРМАЦИЯ",
        font_big,
        WHITE,
        info_x + 25,
        110
    )

    if selected_fredde is not None:

        fred = selected_fredde

        y = 165

        draw_text(
            fred.name,
            font_big,
            YELLOW,
            info_x + 25,
            y
        )

        y += 55

        information = [
            f"Статус: {'жив' if fred.alive else 'мёртв'}",
            f"Возраст: {fred.age}",
            f"Пол: {fred.gender}",
            f"Поколение: {fred.generation}",
            f"GenID: {fred.genid}",
            f"GenDom: {fred.gendom}",
            f"Мутация: {fred.mutrate}%",
            f"Редкость: {fred.rarity}",
            f"Цвет: {fred.color}",
        ]

        for line in information:

            draw_text(
                line,
                font_small,
                WHITE,
                info_x + 25,
                y
            )

            y += 30

        # Родители
        y += 15

        draw_text(
            "Родители:",
            font_medium,
            BLUE,
            info_x + 25,
            y
        )

        y += 35

        if fred.parents:

            for parent in fred.parents:

                draw_text(
                    parent.name,
                    font_small,
                    WHITE,
                    info_x + 35,
                    y
                )

                y += 25

        else:

            draw_text(
                "Нет данных",
                font_small,
                GRAY,
                info_x + 35,
                y
            )

    else:

        draw_text(
            "Выбери Fredde",
            font_medium,
            GRAY,
            info_x + 25,
            170
        )


    # ========================================================
    # РОДИТЕЛИ
    # ========================================================

    draw_text(
        "РОДИТЕЛИ",
        font_medium,
        WHITE,
        info_x + 25,
        min(500, screen_h - 190)
    )

    draw_text(
        f"1: {selected_parent1.name if selected_parent1 else '-'}",
        font_small,
        YELLOW,
        info_x + 25,
        min(535, screen_h - 155)
    )

    draw_text(
        f"2: {selected_parent2.name if selected_parent2 else '-'}",
        font_small,
        GREEN,
        info_x + 25,
        min(565, screen_h - 125)
    )


    # ========================================================
    # СООБЩЕНИЕ
    # ========================================================

    message_rect = pygame.Rect(
        300,
        screen_h - 60,
        max(400, info_x - 320),
        40
    )

    pygame.draw.rect(
        screen,
        (30, 32, 36),
        message_rect,
        border_radius=5
    )

    draw_text(
        message,
        font_small,
        WHITE,
        message_rect.x + 15,
        message_rect.y + 10
    )


    pygame.display.flip()


pygame.quit()
sys.exit()
