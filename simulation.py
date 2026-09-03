from paddock import paddocks
from sex import try_sex
from freddeBrain import think


SEX_REWARD = 3


def step():
    babies = []

    for paddock in paddocks:
        if not paddock.time or not hasattr(paddock, "terrain"):
            continue

        living = [fred for fred in paddock.freddies if fred.alive]
        active = [fred for fred in living if not fred.hibernation]
        decisions = {fred: think(fred, living) for fred in active}

        requests = {
            fred: decision["target"]
            for fred, decision in decisions.items()
            if decision["action"] == "sex"
        }

        finished = set()

        for fred, target in requests.items():
            if fred in finished or requests.get(target) is not fred:
                continue

            baby, message = requestSex(fred, target)
            finished.add(fred)
            finished.add(target)

            if baby is not None:
                babies.append(baby)

        for fred, decision in decisions.items():
            if decision["action"] == "move":
                move(fred, decision["direction"])

        # Спящие не думают, не двигаются, не размножаются и не стареют.
        for fred in active:
            fred.step()

    return babies


def move(fred, direction):
    if fred.hibernation:
        return False

    paddock = fred._paddock
    destination = paddock.terrain.destination(fred.position, direction)

    if destination is None or occupied(paddock, destination):
        return False

    fred.position = list(destination)
    return True


def changePaddock(fred, newPaddock, position):
    if not newPaddock.terrain.is_walkable(*position):
        return False

    if occupied(newPaddock, position):
        return False

    oldPaddock = fred._paddock

    if oldPaddock is not newPaddock:
        if not oldPaddock.move(fred, newPaddock):
            return False

    fred.position = list(position)
    return True


def requestSex(first, second, forced=False):
    if first is second:
        return None, "Нужно выбрать двух разных Фредди"

    if not first.alive or not second.alive:
        return None, "Мёртвый Фредди не может размножаться"

    if first.hibernation or second.hibernation:
        return None, "Один из Фредди спит"

    if first._paddock is not second._paddock:
        return None, "Фредди находятся в разных мирах"

    distance = (
        abs(first.position[0] - second.position[0])
        + abs(first.position[1] - second.position[1])
    )

    if not forced and distance > 1:
        return None, "Фредди находятся слишком далеко"

    paddock = first._paddock

    if len(paddock.freddies) >= paddock.max_freds:
        return None, "В мире достигнут лимит Фредди"

    babyPosition = findBirthPosition(first, second)

    if babyPosition is None:
        return None, "Нет места для ребёнка"

    try:
        # Даже команда игрока проходит обычные проверки пола, возраста
        # и родства внутри try_sex. forced отменяет только проверку расстояния.
        baby, message = try_sex(first, second)
    except Exception as error:
        return None, f"Ошибка размножения: {error}"

    if baby is None:
        return None, message

    if not hasattr(baby, "position"):
        baby.position = None

    try:
        if not changePaddock(baby, paddock, babyPosition):
            baby.alive = False
            return None, "Не удалось разместить ребёнка"
    except Exception as error:
        baby.alive = False
        return None, f"Ошибка размещения ребёнка: {error}"

    first.reward = getattr(first, "reward", 0) + SEX_REWARD
    second.reward = getattr(second, "reward", 0) + SEX_REWARD
    first.successful_sex = getattr(first, "successful_sex", 0) + 1
    second.successful_sex = getattr(second, "successful_sex", 0) + 1

    if forced:
        message = "Принудительное размножение успешно"

    return baby, message


def findBirthPosition(first, second):
    paddock = first._paddock
    positions = []

    for fred in (first, second):
        x, y = fred.position
        positions += [(x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y)]

    for position in positions:
        if paddock.terrain.is_walkable(*position) and not occupied(paddock, position):
            return position

    return None


def occupied(paddock, position):
    for fred in paddock.freddies:
        fredPosition = getattr(fred, "position", None)

        if fred.alive and fredPosition is not None:
            if tuple(fredPosition) == tuple(position):
                return True

    return False
