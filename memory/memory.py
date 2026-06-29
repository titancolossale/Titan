# ==========================================
# Titan Memory
# ==========================================

class Memory:

    def __init__(self):
        self.short_term = []
        self.long_term = []

    def remember(self, information):
        self.short_term.append(information)

    def show_memory(self):
        print("Mémoire actuelle :")
        for item in self.short_term:
            print("-", item)