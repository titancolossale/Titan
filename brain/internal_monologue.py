# =====================================
# Titan Internal Monologue
# =====================================

class InternalMonologue:

    def think(self, message, context=None):
        thoughts = f"""
============================
TITAN INTERNAL MONOLOGUE
============================

Message reçu :
{message}

Analyse interne :
- Comprendre la demande de l'utilisateur.
- Identifier l'objectif réel.
- Vérifier le contexte disponible.
- Réfléchir à la meilleure prochaine étape.
- Répondre de manière utile, claire et concrète.

Contexte disponible :
{context}

============================
"""

        return thoughts