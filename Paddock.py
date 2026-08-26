
paddocks = []

class Paddock:
    def __init__(self, max_freds=5):
        paddocks.append(self)
        self.max_freds = max_freds

    def add(self, fred):
    """добавляет Фреда если загон не        
       полный, иначе возвращает False"""

        if len(self.freddies) == max_freds:
            return False
        self._freddies.append(fred)
        return True


    def move(self, fred, new_paddock):
        is_added = new_paddock.add(fred)
        if not is_added:
            return False

        self._freddies.remove(fred)
        fred._paddock = new_paddock
        return True
            

    def step(self):
        for fred in self.freddies:
            feed.step()
