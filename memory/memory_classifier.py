# =====================================
# Titan Memory Classifier
# =====================================

class MemoryClassifier:

    def classify(self, message):
        message_lower = message.lower()

        if "objectif" in message_lower or "goal" in message_lower:
            return "goals"

        if "je préfère" in message_lower or "j'aime" in message_lower or "préférence" in message_lower:
            return "preferences"

        if "projet" in message_lower or "titan" in message_lower or "trading" in message_lower:
            return "projects"

        return "notes"