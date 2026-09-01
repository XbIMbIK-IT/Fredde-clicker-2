paddocks = []


class Paddock:
    def __init__(self, time=True, max_freds=5):
        paddocks.append(self)

        self.time = time
        self.max_freds = max_freds
        self.freddies = []

    def add(self, fred):
        if len(self.freddies) >= self.max_freds:
            return False

        self.freddies.append(fred)
        return True

    def move(self, fred, new_paddock):
        is_added = new_paddock.add(fred)

        if not is_added:
            return False

        self.freddies.remove(fred)
        fred._paddock = new_paddock
        return True

    def step(self):
        if not self.time:
            return

        for fred in self.freddies:
            fred.step()
