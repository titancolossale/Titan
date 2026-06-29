# =====================================
# Titan Knowledge System
# =====================================

from config.settings import VERSION


class Knowledge:

    def __init__(self):
        self.facts = {
            "creator": "Nolan Hassing",
            "name": "Titan",
            "version": VERSION,
        }

    def search(self, question):
        question = question.lower()

        if "créateur" in question or "createur" in question:
            return self.facts["creator"]

        if "nom" in question:
            return self.facts["name"]

        if "version" in question:
            return self.facts["version"]

        return None
