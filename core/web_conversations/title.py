# =====================================
# Titan Conversation Title Generator
# =====================================

"""Cheap non-blocking title generation for new conversations (Phase 12.1)."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou", "a", "à",
    "en", "au", "aux", "ce", "cet", "cette", "mon", "ma", "mes", "ton", "ta",
    "tes", "son", "sa", "ses", "notre", "nos", "votre", "vos", "je", "tu", "il",
    "elle", "on", "nous", "vous", "ils", "elles", "est", "suis", "es", "sommes",
    "êtes", "etes", "sont", "avec", "pour", "sur", "dans", "par", "que", "qui",
    "quoi", "comment", "bonjour", "salut", "hello", "hi", "hey", "titan",
    "sappelle", "s'appelle", "appelle", "the", "a", "an", "my", "is", "are",
}


def fallback_title_from_message(message: str, *, max_len: int = 48) -> str:
    """Deterministic title from the first user message — never blocks LLM."""
    text = " ".join((message or "").strip().split())
    if not text:
        return "Nouvelle conversation"
    lower = text.lower()

    # Heuristic mappings for common openers.
    if re.match(r"^(bonjour|salut|hello|hi|hey)\b", lower):
        return "Accueil avec Titan"
    if "railway" in lower or "déploiement" in lower or "deploiement" in lower:
        return "Déploiement Railway"
    if "orb" in lower and ("stratég" in lower or "strateg" in lower or "optim"):
        return "Optimisation ORB"
    if "projet principal" in lower:
        return "Projet principal"

    # Keyword title: keep meaningful tokens.
    tokens = re.findall(r"[A-Za-zÀ-ÿ0-9']+", text)
    keep: list[str] = []
    for token in tokens:
        if token.lower().strip("'") in _STOPWORDS:
            continue
        keep.append(token)
        if len(keep) >= 5:
            break
    if not keep:
        title = text[:max_len]
    else:
        title = " ".join(keep)
        if len(title) > max_len:
            title = title[: max_len - 1].rstrip() + "…"
    return title[:max_len] or "Nouvelle conversation"


def schedule_title_update(
    *,
    conversation_id: str,
    user_id: str,
    first_message: str,
    rename: Callable[[str, str, str], Any],
    llm_ask: Callable[[str], str] | None = None,
) -> str:
    """Return immediate fallback title; optionally refine in a background thread.

    Never delays the main chat response. LLM refine is best-effort and bounded.
    """
    title = fallback_title_from_message(first_message)
    try:
        rename(conversation_id, user_id, title)
    except Exception:
        logger.debug("Immediate title rename failed", exc_info=True)

    if llm_ask is None:
        return title

    def _refine() -> None:
        try:
            prompt = (
                "Génère un titre court (3 à 6 mots) en français pour cette "
                "conversation. Réponds uniquement avec le titre, sans guillemets.\n\n"
                f"Premier message: {first_message[:300]}"
            )
            refined = (llm_ask(prompt) or "").strip().splitlines()[0].strip().strip("\"'")
            refined = refined[:80]
            if len(refined) >= 3 and not refined.lower().startswith("désolé"):
                rename(conversation_id, user_id, refined)
        except Exception:
            logger.debug("Background title refine failed", exc_info=True)

    thread = threading.Thread(target=_refine, daemon=True, name="titan-title-gen")
    thread.start()
    return title
