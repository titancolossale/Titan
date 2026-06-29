# =====================================
# Titan Decision System
# =====================================

class Decision:

    def decide(self, message):
        if "bonjour" in message.lower():
            return "salutation"

        return "conversation"