import argparse
import json
import random
from datetime import datetime
from pathlib import Path

import pygame

from fredde import Fredde, STANDART_PADDOCK, freddies
from freddeBrain import BRAIN_SIZE, createBrain
from freddePhoto import generate_fredde
from simulation import move, occupied, requestSex, step as simulationStep
from terrain import (
    HEIGHT,
    MAP_HEIGHT,
    MAP_WIDTH,
    MAX_ZOOM,
    MIN_ZOOM,
    TILE_STEP_X,
    TILE_STEP_Y,
    WIDTH,
    TerrainApp,
)


BASE_DIR = Path(__file__).resolve().parent
SAVES_DIR = BASE_DIR / "saves"
SPEEDS = (0.25, 0.5, 1, 2, 5, 10, 20)
DIRECTION_KEYS = {
    pygame.K_q: "left_up",
    pygame.K_e: "right_up",
    pygame.K_z: "left_down",
    pygame.K_c: "right_down",
}

BACKGROUND = (7, 12, 20)
PANEL = (18, 27, 40)
PANEL_LIGHT = (38, 52, 70)
WHITE = (238, 243, 249)
MUTED = (151, 166, 184)
BLUE = (61, 153, 255)
GREEN = (71, 202, 139)
YELLOW = (244, 193, 79)
RED = (235, 91, 102)


class Game:
    def __init__(self, arguments):
        self.terrain = TerrainApp(seed=arguments.seed)
        self.screen = self.terrain.screen
        self.clock = pygame.time.Clock()
        pygame.display.set_caption("Fredde World")

        self.world = STANDART_PADDOCK
        self.world.terrain = self.terrain
        self.world.max_freds = 100000
        self.world.time = True

        self.fontBig = pygame.font.SysFont("dejavusans", 28, bold=True)
        self.font = pygame.font.SysFont("dejavusans", 20)
        self.fontSmall = pygame.font.SysFont("dejavusans", 16)
        self.fontTiny = pygame.font.SysFont("dejavusans", 13)

        self.running = True
        self.paused = arguments.paused
        self.speedIndex = min(
            range(len(SPEEDS)),
            key=lambda number: abs(SPEEDS[number] - arguments.speed),
        )
        self.accumulator = 0.0
        self.turn = 0

        self.parent1 = None
        self.parent2 = None
        self.selectedFred = None
        self.popup = None
        self.popupFred = None
        self.popupCell = None
        self.popupButtons = {}
        self.popupRect = pygame.Rect(0, 0, 0, 0)
        self.menuButton = pygame.Rect(WIDTH - 154, 18, 132, 44)

        self.message = ""
        self.messageColor = WHITE
        self.messageUntil = 0
        self.fredCache = {}
        self.fredOriginalCache = {}

        loaded = False
        if arguments.loadPath:
            loaded = self.loadGame(Path(arguments.loadPath))
        elif arguments.latest:
            loaded = self.loadLatest()

        if not loaded:
            self.spawnRandom(arguments.spawn)

        self.showMessage("ПКМ — действия")

    def run(self):
        while self.running:
            delta = min(self.clock.tick(60) / 1000, 0.1)
            self.handleEvents()

            if not self.paused:
                self.accumulator += delta * SPEEDS[self.speedIndex]
                steps = 0
                while self.accumulator >= 1 and steps < 20:
                    self.nextTurn()
                    self.accumulator -= 1
                    steps += 1

            self.draw()

        pygame.quit()

    def nextTurn(self):
        babies = simulationStep()
        self.turn += 1
        if babies:
            self.showMessage(f"Родилось Фредди: {len(babies)}", GREEN)

    def handleEvents(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self.paused = not self.paused
                elif event.key == pygame.K_ESCAPE:
                    if self.popup == "world":
                        self.closePopup()
                    else:
                        self.openWorldPopup(None)
                elif event.key in DIRECTION_KEYS and self.popup != "world":
                    self.manualMove(DIRECTION_KEYS[event.key])

            elif event.type == pygame.MOUSEWHEEL and self.popup is None:
                self.terrain.change_zoom(pygame.mouse.get_pos(), event.y)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.leftClick(event.pos)
                elif event.button == 2 and self.popup is None:
                    self.terrain.dragging = True
                    self.terrain.last_mouse_pos = event.pos
                elif event.button == 3:
                    self.rightClick(event.pos)

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 2:
                self.terrain.dragging = False
                self.terrain.last_mouse_pos = None

            elif event.type == pygame.MOUSEMOTION and self.popup is None:
                self.terrain.drag_camera(event.pos)

    def leftClick(self, position):
        if self.menuButton.collidepoint(position):
            self.openWorldPopup(None)
            return

        if self.popup is None:
            return

        for action, rectangle in self.popupButtons.items():
            if rectangle.collidepoint(position):
                self.press(action)
                return

        if not self.popupRect.collidepoint(position):
            self.closePopup()

    def rightClick(self, position):
        fred = self.fredAt(position)
        if fred is not None:
            self.selectedFred = fred
            self.popup = "fred"
            self.popupFred = fred
            self.popupCell = tuple(fred.position)
            return

        cell = self.screenToCell(position)
        if cell is not None:
            self.openWorldPopup(cell)

    def openWorldPopup(self, cell):
        self.popup = "world"
        self.popupFred = None
        self.popupCell = cell

    def closePopup(self):
        self.popup = None
        self.popupFred = None
        self.popupCell = None
        self.popupButtons.clear()

    def press(self, action):
        if action == "close":
            self.closePopup()
        elif action == "spawn":
            fred = self.spawnFredde(self.popupCell)
            if fred is not None:
                self.selectedFred = fred
                self.popup = "fred"
                self.popupFred = fred
        elif action == "pause":
            self.paused = not self.paused
        elif action == "step":
            self.nextTurn()
        elif action == "slower":
            self.speedIndex = max(0, self.speedIndex - 1)
        elif action == "faster":
            self.speedIndex = min(len(SPEEDS) - 1, self.speedIndex + 1)
        elif action == "save":
            self.saveGame()
        elif action == "load":
            self.loadLatest()
        elif action == "center":
            self.terrain.center_camera()
            self.closePopup()
        elif action == "clearParents":
            self.parent1 = None
            self.parent2 = None
        elif action == "exit":
            self.popup = "exit"
        elif action == "exitYes":
            self.running = False
        elif action == "exitNo":
            self.openWorldPopup(None)
        elif action == "parent1":
            self.selectParent(1)
        elif action == "parent2":
            self.selectParent(2)
        elif action == "breed":
            self.forceBreed()
        elif action in ("left_up", "right_up", "left_down", "right_down"):
            self.manualMove(action)

    def selectParent(self, number):
        fred = self.popupFred
        if fred is None or not fred.alive:
            self.showMessage("Нужен живой Фредди", RED)
            return

        if number == 1:
            self.parent1 = fred
        else:
            self.parent2 = fred
        self.showMessage(f"Родитель {number}: {fred.name}", YELLOW)

    def forceBreed(self):
        if self.parent1 is None or self.parent2 is None:
            self.showMessage("Сначала выбери двух родителей", RED)
            return

        try:
            baby, message = requestSex(self.parent1, self.parent2, forced=True)
        except Exception as error:
            self.showMessage(f"Ошибка: {error}", RED)
            return

        self.showMessage(message, GREEN if baby else RED)

        if baby is not None:
            self.parent1 = None
            self.parent2 = None
            self.selectedFred = baby
            self.popupFred = baby
            self.popupCell = tuple(baby.position)

    def manualMove(self, direction):
        fred = self.popupFred or self.selectedFred
        if fred is None or not fred.alive:
            self.showMessage("Нужен живой Фредди", RED)
            return

        if move(fred, direction):
            self.popupCell = tuple(fred.position)
        else:
            self.showMessage("Туда пройти нельзя", RED)

    def spawnRandom(self, amount):
        positions = list(self.terrain.walkable_cells())
        random.shuffle(positions)
        made = 0
        for position in positions:
            if made >= amount:
                break
            if self.spawnFredde(position, False) is not None:
                made += 1

    def spawnFredde(self, position, announce=True):
        if position is None or not self.terrain.is_walkable(*position):
            if announce:
                self.showMessage("Эта клетка непроходима", RED)
            return None
        if occupied(self.world, position):
            if announce:
                self.showMessage("Клетка занята", RED)
            return None

        fred = Fredde(paddock=self.world)
        fred.position = list(position)
        if len(getattr(fred, "brain", [])) != BRAIN_SIZE:
            fred.brain = createBrain()
        fred.hibernation = getattr(fred, "hibernation", False)
        fred.reward = getattr(fred, "reward", 0)
        fred.successful_sex = getattr(fred, "successful_sex", 0)

        if announce:
            self.showMessage(f"Создан {fred.name}", GREEN)
        return fred

    def screenToCell(self, position):
        screenX, screenY = position
        worldX = self.terrain.camera_x + (screenX - WIDTH / 2) / self.terrain.zoom
        worldY = self.terrain.camera_y + (screenY - HEIGHT / 2) / self.terrain.zoom
        x = round((worldX / TILE_STEP_X + worldY / TILE_STEP_Y) / 2)
        y = round((worldY / TILE_STEP_Y - worldX / TILE_STEP_X) / 2)
        return (x, y) if 0 <= x < MAP_WIDTH and 0 <= y < MAP_HEIGHT else None

    def fredAt(self, position):
        visible = sorted(
            (fred for fred in self.world.freddies if fred.position is not None),
            key=lambda fred: sum(fred.position),
            reverse=True,
        )
        for fred in visible:
            screenX, screenY = self.terrain.world_to_screen(*fred.position)
            size = max(36, min(180, round(360 * self.terrain.zoom)))
            rectangle = pygame.Rect(0, 0, size, size)
            rectangle.midbottom = (round(screenX), round(screenY + 10))
            if rectangle.inflate(10, 10).collidepoint(position):
                return fred
        return None

    def draw(self):
        self.screen.fill(BACKGROUND)
        self.terrain.draw_map()
        self.drawSelection()
        self.drawFreddies()
        self.drawHud()
        if self.popup is not None:
            self.drawPopup()
        self.drawMessage()
        pygame.display.flip()

    def drawSelection(self):
        cell = self.popupCell
        if cell is None and self.selectedFred is not None:
            cell = getattr(self.selectedFred, "position", None)
        if cell is not None:
            self.drawDiamond(cell, YELLOW, 3)

    def drawDiamond(self, cell, color, width):
        centerX, centerY = self.terrain.world_to_screen(*cell)
        radiusX = TILE_STEP_X * self.terrain.zoom
        radiusY = TILE_STEP_Y * self.terrain.zoom
        points = [
            (centerX, centerY - radiusY),
            (centerX + radiusX, centerY),
            (centerX, centerY + radiusY),
            (centerX - radiusX, centerY),
        ]
        pygame.draw.polygon(self.screen, color, points, width)

    def drawFreddies(self):
        ordered = sorted(
            (fred for fred in self.world.freddies if fred.position is not None),
            key=lambda fred: sum(fred.position),
        )

        for fred in ordered:
            screenX, screenY = self.terrain.world_to_screen(*fred.position)
            if not self.screen.get_rect().inflate(200, 200).collidepoint(screenX, screenY):
                continue

            size = max(36, min(180, round(360 * self.terrain.zoom)))
            image = self.fredSurface(fred, size)

            if fred is self.selectedFred:
                pygame.draw.circle(self.screen, YELLOW, (round(screenX), round(screenY)), size // 2 + 4, 3)
            if fred is self.parent1:
                pygame.draw.circle(self.screen, BLUE, (round(screenX), round(screenY)), size // 2, 3)
            if fred is self.parent2:
                pygame.draw.circle(self.screen, GREEN, (round(screenX), round(screenY)), size // 2 - 4, 3)

            picture = image if fred.alive else image.copy()
            if not fred.alive:
                picture.set_alpha(90)
            rectangle = picture.get_rect(midbottom=(round(screenX), round(screenY + 10)))
            self.screen.blit(picture, rectangle)

            if getattr(fred, "hibernation", False) and fred.alive:
                self.drawText("Zz", screenX + size * 0.2, screenY - size * 0.65, self.fontSmall, BLUE)

            if self.terrain.zoom >= 0.14:
                label = self.fontTiny.render(fred.name, True, WHITE)
                labelRect = label.get_rect(midtop=(screenX, screenY + 12))
                pygame.draw.rect(self.screen, BACKGROUND, labelRect.inflate(8, 4), border_radius=4)
                self.screen.blit(label, labelRect)

    def fredSurface(self, fred, size):
        visual = (
            tuple(fred.color), fred.eye, fred.hatAcs, fred.faceAcs,
            fred.eyeAcs, fred.bodyPattern, fred.eyelash,
        )
        originalKey = (id(fred), visual)
        key = (originalKey, size)
        if key not in self.fredCache:
            if originalKey not in self.fredOriginalCache:
                try:
                    image = generate_fredde(fred).convert("RGBA")
                    original = pygame.image.fromstring(
                        image.tobytes(), image.size, "RGBA"
                    ).convert_alpha()
                except Exception:
                    original = pygame.Surface((256, 256), pygame.SRCALPHA)
                    pygame.draw.circle(original, tuple(fred.color), (128, 128), 124)
                self.fredOriginalCache[originalKey] = original

            original = self.fredOriginalCache[originalKey]
            self.fredCache[key] = pygame.transform.scale(original, (size, size))
        return self.fredCache[key]

    def drawHud(self):
        alive = sum(fred.alive for fred in self.world.freddies)
        status = "ПАУЗА" if self.paused else "ИДЁТ"

        panel = pygame.Surface((460, 48), pygame.SRCALPHA)
        panel.fill((12, 19, 29, 220))
        self.screen.blit(panel, (18, 16))
        self.drawText(
            f"Ход {self.turn}   Живых {alive}   {SPEEDS[self.speedIndex]}x   {status}",
            34, 31, self.fontSmall, GREEN if not self.paused else YELLOW,
        )

        hovered = self.menuButton.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.screen, BLUE if hovered else PANEL_LIGHT, self.menuButton, border_radius=10)
        self.drawCentered("МЕНЮ", self.menuButton, self.font, WHITE)

        hint = "Q E Z C — ход   Space — пауза   Esc — меню"
        hintImage = self.fontTiny.render(hint, True, WHITE)
        hintRect = hintImage.get_rect(bottomleft=(18, HEIGHT - 16)).inflate(18, 10)
        shade = pygame.Surface(hintRect.size, pygame.SRCALPHA)
        shade.fill((12, 19, 29, 190))
        self.screen.blit(shade, hintRect)
        self.screen.blit(hintImage, hintImage.get_rect(center=hintRect.center))

    def drawPopup(self):
        self.popupButtons.clear()

        if self.popup == "fred":
            self.drawFredPopup()
        elif self.popup == "exit":
            self.drawExitPopup()
        else:
            self.drawWorldPopup()

    def beginPopup(self, width, height, title):
        self.popupRect = pygame.Rect(0, 0, width, height)
        self.popupRect.bottomright = (WIDTH - 18, HEIGHT - 18)
        pygame.draw.rect(self.screen, PANEL, self.popupRect, border_radius=16)
        pygame.draw.rect(self.screen, (77, 96, 118), self.popupRect, 2, border_radius=16)
        self.drawText(title, self.popupRect.x + 24, self.popupRect.y + 20, self.fontBig, WHITE)
        self.drawPopupButton("close", "×", self.popupRect.right - 54, self.popupRect.y + 14, 38, 38)

    def drawWorldPopup(self):
        self.beginPopup(470, 625, "Мир")
        x = self.popupRect.x + 24
        y = self.popupRect.y + 70

        alive = sum(fred.alive for fred in self.world.freddies)
        self.drawText(f"Ход: {self.turn}     Живых: {alive}", x, y, self.font, WHITE)
        y += 34

        canSpawn = False
        if self.popupCell is None:
            self.drawText("ПКМ по клетке", x, y, self.fontSmall, MUTED)
        else:
            canSpawn = self.terrain.is_walkable(*self.popupCell) and not occupied(self.world, self.popupCell)
            color = GREEN if canSpawn else RED
            cell = self.terrain.cell_at(*self.popupCell)
            biome = cell.biome if cell else "край"

            if self.popupCell in self.terrain.blocked_cells:
                state = "препятствие"
            elif occupied(self.world, self.popupCell):
                state = "занято"
            else:
                state = "можно" if canSpawn else "нельзя"

            self.drawText(
                f"{self.popupCell}   {biome}   {state}",
                x, y, self.fontSmall, color,
            )
        y += 40

        self.drawPopupButton("spawn", "Создать Фредди", x, y, 422, 44, disabled=not canSpawn)
        y += 58
        self.drawPopupButton("pause", "Продолжить" if self.paused else "Пауза", x, y, 202, 44)
        self.drawPopupButton("step", "Один ход", x + 220, y, 202, 44)
        y += 66

        self.drawText(f"Скорость: {SPEEDS[self.speedIndex]} хода/с", x, y + 10, self.font, WHITE)
        self.drawPopupButton("slower", "−", x + 300, y, 54, 44)
        self.drawPopupButton("faster", "+", x + 368, y, 54, 44)
        y += 66

        self.drawPopupButton("save", "Сохранить", x, y, 202, 44)
        self.drawPopupButton("load", "Загрузить последний", x + 220, y, 202, 44)
        y += 58
        self.drawPopupButton("center", "К центру карты", x, y, 202, 44)
        self.drawPopupButton("clearParents", "Сбросить родителей", x + 220, y, 202, 44)
        y += 58
        self.drawPopupButton("exit", "Выйти", x, y, 422, 44, danger=True)

    def drawExitPopup(self):
        self.beginPopup(390, 190, "Выйти из игры?")
        x = self.popupRect.x + 24
        y = self.popupRect.bottom - 68
        self.drawPopupButton("exitNo", "Нет", x, y, 162, 44)
        self.drawPopupButton("exitYes", "Да", x + 180, y, 162, 44, danger=True)

    def drawFredPopup(self):
        fred = self.popupFred
        if fred is None:
            self.closePopup()
            return

        self.beginPopup(520, 655, "Фредди")
        x = self.popupRect.x + 24
        y = self.popupRect.y + 68

        image = self.fredSurface(fred, 105)
        self.screen.blit(image, image.get_rect(topleft=(x, y)))
        self.drawText(fred.name, x + 125, y + 4, self.fontBig, YELLOW)
        self.drawText("Жив" if fred.alive else "Мёртв", x + 125, y + 42, self.font, GREEN if fred.alive else RED)
        self.drawText(f"Позиция: {fred.position}", x + 125, y + 72, self.fontSmall, WHITE)
        y += 125

        parents = ", ".join(parent.name for parent in fred.parents) or "нет"
        left = [
            f"Возраст: {fred.age:.1f}",
            f"Пол: {fred.gender}",
            f"Поколение: {fred.generation}",
            f"GenID: {fred.genid}",
        ]
        right = [
            f"GenDom: {fred.gendom}",
            f"Мутация: {fred.mutrate}%",
            f"Награда: {getattr(fred, 'reward', 0)}",
            f"Секс: {getattr(fred, 'successful_sex', 0)}",
        ]
        for number, text in enumerate(left):
            self.drawText(text, x, y + number * 27, self.fontSmall, WHITE)
        for number, text in enumerate(right):
            self.drawText(text, x + 245, y + number * 27, self.fontSmall, WHITE)
        y += 116
        sleep = "да" if getattr(fred, "hibernation", False) else "нет"
        self.drawText(f"Сон: {sleep}", x, y, self.fontSmall, BLUE if sleep == "да" else MUTED)
        self.drawText(f"Родители: {parents}", x, y + 27, self.fontSmall, MUTED)
        y += 68

        self.drawText("Передвинуть", x, y, self.font, WHITE)
        y += 34
        self.drawPopupButton("left_up", "Q   ↖", x, y, 227, 42, disabled=not fred.alive)
        self.drawPopupButton("right_up", "E   ↗", x + 245, y, 227, 42, disabled=not fred.alive)
        y += 52
        self.drawPopupButton("left_down", "Z   ↙", x, y, 227, 42, disabled=not fred.alive)
        self.drawPopupButton("right_down", "C   ↘", x + 245, y, 227, 42, disabled=not fred.alive)
        y += 66

        self.drawPopupButton("parent1", "Родитель 1", x, y, 227, 42, disabled=not fred.alive)
        self.drawPopupButton("parent2", "Родитель 2", x + 245, y, 227, 42, disabled=not fred.alive)
        y += 52
        ready = self.parent1 is not None and self.parent2 is not None
        self.drawPopupButton("breed", "Размножить", x, y, 472, 46, danger=True, disabled=not ready)

    def drawPopupButton(self, action, text, x, y, width, height, danger=False, disabled=False):
        rectangle = pygame.Rect(x, y, width, height)
        if not disabled:
            self.popupButtons[action] = rectangle
        hovered = rectangle.collidepoint(pygame.mouse.get_pos()) and not disabled
        if disabled:
            color = (42, 48, 57)
            textColor = (102, 111, 123)
        elif danger:
            color = RED if hovered else (130, 51, 62)
            textColor = WHITE
        else:
            color = BLUE if hovered else PANEL_LIGHT
            textColor = WHITE
        pygame.draw.rect(self.screen, color, rectangle, border_radius=9)
        self.drawCentered(text, rectangle, self.fontSmall, textColor)

    def drawCentered(self, text, rectangle, font, color):
        image = font.render(str(text), True, color)
        self.screen.blit(image, image.get_rect(center=rectangle.center))

    def drawText(self, text, x, y, font, color):
        self.screen.blit(font.render(str(text), True, color), (round(x), round(y)))

    def showMessage(self, text, color=WHITE):
        self.message = str(text)
        self.messageColor = color
        self.messageUntil = pygame.time.get_ticks() + 3500

    def drawMessage(self):
        if not self.message or pygame.time.get_ticks() > self.messageUntil:
            return
        image = self.font.render(self.message, True, self.messageColor)
        rectangle = image.get_rect(midbottom=(WIDTH // 2, HEIGHT - 35)).inflate(30, 18)
        pygame.draw.rect(self.screen, PANEL, rectangle, border_radius=10)
        pygame.draw.rect(self.screen, self.messageColor, rectangle, 1, border_radius=10)
        self.screen.blit(image, image.get_rect(center=rectangle.center))

    def saveGame(self):
        try:
            SAVES_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = SAVES_DIR / f"save_{stamp}.json"
            number = 2
            while path.exists():
                path = SAVES_DIR / f"save_{stamp}_{number}.json"
                number += 1

            fredList = list(self.world.freddies)
            indexes = {fred: number for number, fred in enumerate(fredList)}
            data = {
                "version": 1,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "terrain_seed": self.terrain.seed,
                "turn": self.turn,
                "speed": SPEEDS[self.speedIndex],
                "paused": self.paused,
                "camera": {
                    "x": self.terrain.camera_x,
                    "y": self.terrain.camera_y,
                    "zoom": self.terrain.zoom,
                },
                "parent1": indexes.get(self.parent1),
                "parent2": indexes.get(self.parent2),
                "selected": indexes.get(self.selectedFred),
                "freddies": [self.fredData(fred, indexes) for fred in fredList],
            }

            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
            self.showMessage(f"Сохранено: {path.name}", GREEN)
            return path
        except Exception as error:
            self.showMessage(f"Ошибка сохранения: {error}", RED)
            return None

    def fredData(self, fred, indexes):
        return {
            "name": fred.name,
            "alive": fred.alive,
            "age": fred.age,
            "gender": fred.gender,
            "genid": fred.genid,
            "gendom": fred.gendom,
            "mutrate": fred.mutrate,
            "rarity": fred.rarity,
            "generation": fred.generation,
            "color": list(fred.color),
            "eye": fred.eye,
            "hatAcs": fred.hatAcs,
            "faceAcs": fred.faceAcs,
            "eyeAcs": fred.eyeAcs,
            "bodyPattern": fred.bodyPattern,
            "eyelash": fred.eyelash,
            "position": list(fred.position) if fred.position is not None else None,
            "brain": list(fred.brain),
            "hibernation": fred.hibernation,
            "reward": getattr(fred, "reward", 0),
            "successful_sex": getattr(fred, "successful_sex", 0),
            "parents": [indexes[parent] for parent in fred.parents if parent in indexes],
        }

    def loadLatest(self):
        saves = sorted(SAVES_DIR.glob("save_*.json")) if SAVES_DIR.exists() else []
        if not saves:
            self.showMessage("Сохранений пока нет", RED)
            return False
        return self.loadGame(saves[-1])

    def loadGame(self, path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            records = data["freddies"]
            self.world.freddies.clear()
            freddies.clear()
            self.terrain.regenerate(int(data["terrain_seed"]))
            self.world.terrain = self.terrain
            created = []

            for record in records:
                fred = Fredde(
                    name=record["name"], paddock=self.world, age=record["age"],
                    gender=record["gender"], genid=record["genid"],
                    gendom=record["gendom"], mutrate=record["mutrate"],
                    rarity=record["rarity"], parents=[], generation=record["generation"],
                    color=record["color"], eye=record["eye"], hatAcs=record["hatAcs"],
                    faceAcs=record["faceAcs"], eyeAcs=record["eyeAcs"],
                    bodyPattern=record["bodyPattern"], eyelash=record["eyelash"],
                )
                fred.alive = record["alive"]
                fred.position = record["position"]
                brain = record.get("brain", [])
                fred.brain = brain if len(brain) == BRAIN_SIZE else createBrain()
                fred.hibernation = record.get("hibernation", False)
                fred.reward = record.get("reward", 0)
                fred.successful_sex = record.get("successful_sex", 0)
                created.append(fred)

            for fred, record in zip(created, records):
                fred.parents = [created[number] for number in record.get("parents", [])]

            def savedFred(name):
                number = data.get(name)
                return created[number] if isinstance(number, int) and number < len(created) else None

            self.parent1 = savedFred("parent1")
            self.parent2 = savedFred("parent2")
            self.selectedFred = savedFred("selected")
            self.turn = int(data.get("turn", 0))
            savedSpeed = float(data.get("speed", 1))
            self.speedIndex = min(
                range(len(SPEEDS)),
                key=lambda number: abs(SPEEDS[number] - savedSpeed),
            )
            self.paused = bool(data.get("paused", True))

            camera = data.get("camera", {})
            self.terrain.camera_x = float(camera.get("x", self.terrain.camera_x))
            self.terrain.camera_y = float(camera.get("y", self.terrain.camera_y))
            self.terrain.zoom = max(MIN_ZOOM, min(MAX_ZOOM, float(camera.get("zoom", self.terrain.zoom))))
            self.terrain.scaled_assets_zoom = None
            self.terrain.update_scaled_assets()

            self.accumulator = 0
            self.fredCache.clear()
            self.fredOriginalCache.clear()
            self.closePopup()
            self.showMessage(f"Загружено: {path.name}", GREEN)
            return True
        except Exception as error:
            self.showMessage(f"Ошибка загрузки: {error}", RED)
            return False


def parseArguments():
    parser = argparse.ArgumentParser(description="Fredde World")
    parser.add_argument("--seed", type=int, help="Seed новой карты")
    parser.add_argument("--spawn", type=int, default=20, help="Сколько Фредди создать")
    parser.add_argument("--speed", type=float, default=1, help="Ходов в секунду")
    parser.add_argument("--paused", action="store_true", help="Начать с паузы")
    parser.add_argument("--load", dest="loadPath", help="Загрузить JSON-сейв")
    parser.add_argument("--latest", action="store_true", help="Загрузить последний сейв")
    return parser.parse_args()


def main():
    Game(parseArguments()).run()


if __name__ == "__main__":
    main()
