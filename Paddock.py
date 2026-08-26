
paddocks = []

class Paddock:
    def __init__(self, max_freds=5):
        paddocks.append(self)
        self.max_freds = max_freds

    def add(self, fred):
    """добавляет Фреда если загон не        
       полный, иначе возвращает False"""

        if Len(self.freddies) == max_freds:
            return False
        self._freddies.append(fred)
        return True


    def step(self):
        for fred in self.freddies:
            feed.step()
