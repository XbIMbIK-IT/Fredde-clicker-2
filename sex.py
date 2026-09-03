from fredde import Fredde as fredde
import random
import os
from freddeBrain import breedBrain

# Подгрузка визуала и случайный визуал
def load_visuals():
    visual_params = [
        "bodyPattern",
        "eye",
        "eyeAcs",
        "faceAcs",
        "hatAcs"
    ]

    visuals = {}

    for param in visual_params:
        path = f"sprites/{param}"

        try:
            visuals[param] = [
                filename.rsplit(".", 1)[0]
                for filename in os.listdir(path)
                if os.path.isfile(os.path.join(path, filename))
            ]
        except FileNotFoundError:
            visuals[param] = []

    return visuals


Visuals = load_visuals()


def random_visual(visuals, param):
    return random.choice(visuals[param])


with open("NameList.txt", "r", encoding="utf-8") as f:
    NameList = f.read().splitlines()
RarityList = ['common', 'uncommon', 'rare', 'epic', 'mythic', 'legendary']
SEX_AGE = 3


def try_sex(parent1, parent2):
    try:
        if not parent1.alive or not parent2.alive:
            return None, "Один из родителей мёртв"

        if parent1.gender == 'cf' or parent2.gender == 'cf':
            return None, "CF не может размножаться"

        if parent1.gender == 'is' or parent2.gender == 'is':
            pass
        elif parent1.gender == parent2.gender:
            return None, "Одинаковый пол"

        if parent1.age < SEX_AGE or parent2.age < SEX_AGE:
            return None, "Один из родителей слишком молод"

        if parent1.hibernation or parent2.hibernation:
            return None, "Один из родителей в гибернации"

        return sex(parent1, parent2), "Успешно"


    except Exception as e:
        return None, f"Ошибка при размножении: {e}"


def is_inbreeding(parent1, parent2):
    family1 = parent1.family
    family2 = parent2.family

    return parent1 in family2 or parent2 in family1 or bool(family1 & family2)


def sex(parent1, parent2):
    if parent1.generation <= parent2.generation:
        babygeneration = parent2.generation + 1
    else:
        babygeneration = parent1.generation + 1

    # Общая доминантность
    total_dom = parent1.gendom + parent2.gendom

    # Шанс мутации
    MutRate = mut_chance(parent1, parent2, total_dom)

    # GenID
    babygenid = (
                        parent1.genid * parent1.gendom +
                        parent2.genid * parent2.gendom
                ) / total_dom

    # Цвет
    babycolor = []

    for i in range(3):
        color = (
                        parent1.color[i] * parent1.gendom +
                        parent2.color[i] * parent2.gendom
                ) / total_dom

        babycolor.append(round(color))

    # Наследование gendom
    parent1_chance = parent1.gendom / total_dom

    if random.random() <= parent1_chance:
        babygendom = parent1.gendom
    else:
        babygendom = parent2.gendom

    # Редкость
    if random.random() <= parent1_chance:
        babyrarity = parent1.rarity
    else:
        babyrarity = parent2.rarity

    # Словарь с визуалом
    baby_visuals = {
        "bodyPattern": parent1.bodyPattern if random.random() <= parent1_chance else parent2.bodyPattern,
        "eye": parent1.eye if random.random() <= parent1_chance else parent2.eye,
        "eyeAcs": parent1.eyeAcs if random.random() <= parent1_chance else parent2.eyeAcs,
        "faceAcs": parent1.faceAcs if random.random() <= parent1_chance else parent2.faceAcs,
        "hatAcs": parent1.hatAcs if random.random() <= parent1_chance else parent2.hatAcs
    }

    # Мутация
    if random.uniform(0, 100) <= MutRate:

        # GenID
        babygenid *= random.uniform(0.6, 1.4)

        # Цвет
        for i in range(3):
            babycolor[i] *= random.uniform(0.5, 2)
            babycolor[i] = max(
                0,
                min(255, round(babycolor[i]))
            )

        # Доминантность
        babygendom *= random.uniform(0.6, 1.3)
        babygendom = max(0, min(1, babygendom))

        # Редкость
        rarity_index = RarityList.index(babyrarity)

        if random.random() < 0.25:
            rarity_index += 1
        else:
            rarity_index -= 1

        rarity_index = max(
            0,
            min(len(RarityList) - 1, rarity_index)
        )

        babyrarity = RarityList[rarity_index]

        # Мутация словоря с визуалом
        if random.random() <= 0.5:
            baby_visuals["bodyPattern"] = random_visual(Visuals, "bodyPattern")

        if random.random() <= 0.5:
            baby_visuals["eye"] = random_visual(Visuals, "eye")

        if random.random() <= 0.5:
            baby_visuals["eyeAcs"] = random_visual(Visuals, "eyeAcs")

        if random.random() <= 0.5:
            baby_visuals["faceAcs"] = random_visual(Visuals, "faceAcs")

        if random.random() <= 0.5:
            baby_visuals["hatAcs"] = random_visual(Visuals, "hatAcs")

    # Пол ребенка
    gender_roll = random.uniform(0, 100)
    if gender_roll < 45:
        babygender = 'boy'
    elif gender_roll < 90:
        babygender = 'girl'
    elif gender_roll < 95:
        babygender = 'cf'
    else:
        babygender = 'is'

    # Реснички
    if babygender == 'boy':
        eyelash = False
    elif babygender == 'girl':
        eyelash = True
    elif random.random() <= 0.5:
        eyelash = False
    else:
        eyelash = True

    babybrain = breedBrain(
        parent1.brain,
        parent2.brain,
        parent1.gendom,
        parent2.gendom,
        MutRate,
    )

    babygenid = round(babygenid)
    babygendom = round(babygendom, 3)
    MutRate = round(MutRate, 1)
    return fredde(
        name=random.choice(NameList),
        color=babycolor,
        genid=babygenid,
        gendom=babygendom,
        mutrate=MutRate,
        rarity=babyrarity,
        parents=[parent1, parent2],
        generation=babygeneration,
        gender=babygender,
        age=1,
        eyelash=eyelash,
        brain=babybrain,

        bodyPattern=baby_visuals["bodyPattern"],
        eye=baby_visuals["eye"],
        eyeAcs=baby_visuals["eyeAcs"],
        faceAcs=baby_visuals["faceAcs"],
        hatAcs=baby_visuals["hatAcs"],
    )


def mut_chance(parent1, parent2, total_dom):
    MutRate = (parent1.mutrate + parent2.mutrate) / 2

    # Инбридинг
    if is_inbreeding(parent1, parent2):
        if MutRate <= 0:
            MutRate = 13
        else:
            MutRate *= 1.3
    elif random.random() <= 0.4 and parent1.generation == parent2.generation:
        MutRate -= 4

    # Разница поколений
    if parent1.generation != parent2.generation:
        gendif = abs(parent2.generation - parent1.generation)
        MutRate += (gendif * 2)

    return MutRate
