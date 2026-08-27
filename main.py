from fredde import freddies
from fredde import Fredde as fredde
from sex import try_sex,sex
import tree
from freddePhoto import show_fredde
from freddePhoto import save_fredde

Ded1 = fredde(
    name='Сало',
    eyelash= True,
    eye= 'blue',
    hatAcs= 'usa',
    eyeAcs= 'coolshades',
    bodyPattern= 'afghanistan',
    color=[192, 185, 159],
    genid=10,
    gendom=0.3,
    mutrate=50,
    rarity='rare',
    age=11
)

Babka1 = fredde(
    name='Агафья',
    eyelash= False,
    eye= 'hearts',
    hatAcs= 'wings',
    faceAcs= 'tail',
    bodyPattern= 'hearts',
    color=[255, 0, 0],
    genid=20,
    gendom=0.8,
    mutrate=50,
    rarity='common',
    age=11
)

Ded2 = fredde(
    name='Касеки',
    eyelash=False,
    eye='ghoul',
    hatAcs='casque',
    faceAcs='drop',
    bodyPattern='xeno',
    color=[131, 71, 201],
    genid=20,
    gendom=0.8,
    mutrate=50,
    rarity='common',
    age=11
)

Babka2 = fredde(
    name='Бабка гренни',
    eyelash=False,
    eye='smoker',
    hatAcs='ushanka',
    faceAcs='cigar',
    bodyPattern='brain',
    color=[14, 12, 224],
    genid=20,
    gendom=0.8,
    mutrate=50,
    rarity='common',
    age=11
)

Ded3 = fredde(
    name='Хрящ',
    eyelash=False,
    eye='ghoul',
    hatAcs='horns2',
    faceAcs='drop',
    bodyPattern='xeno',
    color=[12, 71, 44],
    genid=20,
    gendom=0.8,
    mutrate=50,
    rarity='common',
    age=11
)

Babka3 = fredde(
    name='Баба капа',
    eyelash=False,
    eye='herobrine',
    hatAcs='nimbus',
    faceAcs='tears',
    bodyPattern='flower',
    color=[131, 12, 12],
    genid=20,
    gendom=0.8,
    mutrate=50,
    rarity='common',
    age=11
)

Gurin = fredde(
    name='Гурин',
    eyelash=False,
    eye='gurin',
    hatAcs='gurin',
    eyeAcs='gurin',
    faceAcs='gurin',
    bodyPattern='afghanistan',
    color=[255, 255, 255],
    genid=20,
    gendom=0.8,
    mutrate=0,
    rarity='common',
    age=11
)





baby = sex(Ded1, Babka1)
baby1 = sex(Ded3, Babka3)
baby2 = sex(Ded2, Babka2)
baby3 = sex(baby, baby2)
baby4 = sex(baby3, baby2)
baby5 = sex(Ded2, Babka2)
baby6 = sex(baby5, baby2)
baby7 = sex(Gurin, Babka3)
baby8 = sex(Ded1, Babka1)

baby9 = sex(baby1, baby3)
baby10 = sex(baby4, baby6)
baby11 = sex(baby7, baby8)
baby12 = sex(baby9, baby10)
baby13 = sex(baby11, baby12)
baby14 = sex(baby2, baby8)
baby15 = sex(baby5, baby7)
baby16 = sex(baby3, baby9)
baby17 = sex(baby6, baby10)
baby18 = sex(baby4, baby11)
baby19 = sex(baby12, baby14)
baby20 = sex(baby13, baby15)
baby21 = sex(baby16, baby17)
baby22 = sex(baby18, baby19)
baby23 = sex(baby20, baby21)
baby24 = sex(baby22, baby23)
baby25 = sex(baby9, baby14)

#if baby:
#    values = [
#        ("name", baby.name),
#        ("gender", baby.gender),
#        ("eyelashes", baby.eyelash),
#        ("age", baby.age),
#        ("generation", baby.generation),
#        ("genid", baby.genid),
#        ("gendom", baby.gendom),
#        ("mutrate", baby.mutrate),
#        ("color", baby.color)
#    ]
#
#    for name, value in values:
#        print(f"{name}: {value}")
#



# print(baby.age)

tree.main()
