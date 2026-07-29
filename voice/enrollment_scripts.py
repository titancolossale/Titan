# =====================================
# Titan Voice Enrollment Scripts
# =====================================

"""Guided enrollment phrases (multi-language — Phase 20.2 / 20.9).

Phrases intentionally avoid secrets, personal data, passwords, addresses,
and account details. They vary rhythm, phonetics, length, and intonation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EnrollmentScript:
    """Ordered enrollment phrases for one locale."""

    script_id: str
    locale: str
    language: str
    title: str
    instructions: str
    phrases: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "script_id": self.script_id,
            "locale": self.locale,
            "language": self.language,
            "title": self.title,
            "instructions": self.instructions,
            "phrases": list(self.phrases),
            "phrase_count": len(self.phrases),
        }

    def phrase_for_index(self, index: int) -> str:
        if not self.phrases:
            return ""
        return self.phrases[index % len(self.phrases)]


FRENCH_ENROLLMENT_SCRIPT = EnrollmentScript(
    script_id="fr_default",
    locale="fr-FR",
    language="fr",
    title="Enregistrement vocal Titan",
    instructions=(
        "Lis chaque phrase clairement, à voix normale. "
        "Varie légèrement le rythme entre les échantillons. "
        "Évite le bruit de fond et reste seul devant le micro."
    ),
    phrases=(
        "Bonjour Titan, je commence mon enregistrement vocal aujourd'hui.",
        "Les nuages passent vite au-dessus des collines verdoyantes.",
        "Peux-tu répéter cette phrase avec calme et précision ?",
        "Un deux trois quatre cinq — le rythme change maintenant.",
        "La bibliothèque contient des livres anciens et des cartes colorées.",
        "Quelle heure est-il sur l'horloge de la salle commune ?",
        "J'avance pas à pas, sans précipitation, vers la fin du script.",
        "Merci, l'enregistrement est presque terminé pour cette session.",
    ),
)

ENGLISH_ENROLLMENT_SCRIPT = EnrollmentScript(
    script_id="en_default",
    locale="en-US",
    language="en",
    title="Titan voice enrollment",
    instructions=(
        "Speak each phrase clearly at a natural volume. "
        "Vary rhythm slightly between samples. "
        "Avoid background noise and record alone."
    ),
    phrases=(
        "Hello Titan, I am starting my voice enrollment session now.",
        "Bright clouds drift quickly above the quiet green hills.",
        "Could you please repeat this sentence with calm clarity?",
        "One two three four five — the rhythm shifts right here.",
        "The library holds ancient books and brightly colored maps.",
        "What time does the clock in the common room display today?",
        "I move step by step, without rushing, toward the script end.",
        "Thank you — this enrollment recording is nearly complete.",
    ),
)

SPANISH_ENROLLMENT_SCRIPT = EnrollmentScript(
    script_id="es_default",
    locale="es-ES",
    language="es",
    title="Registro de voz Titan",
    instructions=(
        "Lee cada frase con claridad y volumen natural. "
        "Varía ligeramente el ritmo entre muestras. "
        "Evita el ruido de fondo y graba solo."
    ),
    phrases=(
        "Hola Titan, comienzo mi registro de voz ahora mismo.",
        "Las nubes brillantes cruzan rápido sobre las colinas verdes.",
        "¿Puedes repetir esta frase con calma y claridad?",
        "Uno dos tres cuatro cinco — el ritmo cambia aquí.",
        "La biblioteca guarda libros antiguos y mapas de colores.",
        "¿Qué hora marca el reloj de la sala común hoy?",
        "Avanzo paso a paso, sin prisa, hacia el final del guion.",
        "Gracias — esta grabación de registro está casi completa.",
    ),
)

BILINGUAL_ENROLLMENT_SCRIPT = EnrollmentScript(
    script_id="bilingual_fr_en",
    locale="fr-EN",
    language="bilingual",
    title="Enregistrement bilingue Titan / Bilingual enrollment",
    instructions=(
        "Alternate French and English phrases at a natural volume. "
        "Alterne français et anglais à voix normale."
    ),
    phrases=(
        "Bonjour Titan, je commence mon enregistrement vocal aujourd'hui.",
        "Hello Titan, this bilingual enrollment sample continues now.",
        "Les nuages passent vite au-dessus des collines verdoyantes.",
        "Bright clouds drift quickly above the quiet green hills.",
        "Un deux trois quatre cinq — le rythme change maintenant.",
        "One two three four five — the rhythm shifts right here.",
        "Merci, l'enregistrement est presque terminé pour cette session.",
        "Thank you — this enrollment recording is nearly complete.",
    ),
)

_SCRIPTS: dict[str, EnrollmentScript] = {
    FRENCH_ENROLLMENT_SCRIPT.script_id: FRENCH_ENROLLMENT_SCRIPT,
    ENGLISH_ENROLLMENT_SCRIPT.script_id: ENGLISH_ENROLLMENT_SCRIPT,
    SPANISH_ENROLLMENT_SCRIPT.script_id: SPANISH_ENROLLMENT_SCRIPT,
    BILINGUAL_ENROLLMENT_SCRIPT.script_id: BILINGUAL_ENROLLMENT_SCRIPT,
    "fr": FRENCH_ENROLLMENT_SCRIPT,
    "fr-FR": FRENCH_ENROLLMENT_SCRIPT,
    "en": ENGLISH_ENROLLMENT_SCRIPT,
    "en-US": ENGLISH_ENROLLMENT_SCRIPT,
    "en-GB": ENGLISH_ENROLLMENT_SCRIPT,
    "es": SPANISH_ENROLLMENT_SCRIPT,
    "es-ES": SPANISH_ENROLLMENT_SCRIPT,
    "bilingual": BILINGUAL_ENROLLMENT_SCRIPT,
    "fr-EN": BILINGUAL_ENROLLMENT_SCRIPT,
}


def get_enrollment_script(locale_or_id: str | None = None) -> EnrollmentScript:
    """Resolve an enrollment script by locale or script id (French default)."""
    key = (locale_or_id or "fr-FR").strip()
    if key in _SCRIPTS:
        return _SCRIPTS[key]
    lowered = key.lower()
    if lowered.startswith("en"):
        return ENGLISH_ENROLLMENT_SCRIPT
    if lowered.startswith("es"):
        return SPANISH_ENROLLMENT_SCRIPT
    if "bilingual" in lowered or lowered.startswith("fr-en"):
        return BILINGUAL_ENROLLMENT_SCRIPT
    return FRENCH_ENROLLMENT_SCRIPT


def list_enrollment_scripts() -> list[dict[str, Any]]:
    """Return canonical multi-language scripts (deduplicated)."""
    return [
        FRENCH_ENROLLMENT_SCRIPT.to_dict(),
        ENGLISH_ENROLLMENT_SCRIPT.to_dict(),
        SPANISH_ENROLLMENT_SCRIPT.to_dict(),
        BILINGUAL_ENROLLMENT_SCRIPT.to_dict(),
    ]
