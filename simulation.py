from paddock import paddocks


def step():
    for p in paddocks:
        p.step()

def move(fred, paddock):
    old_paddock = fred._paddock
    return old_paddock.move(fred, paddock)
