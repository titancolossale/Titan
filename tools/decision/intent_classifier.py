# =====================================
# Titan Tool Decision — Intent Classifier
# =====================================

"""Heuristic intent classification with confidence scoring (Phase 10B — P10B-001/002)."""

from __future__ import annotations

from tools.decision.intent import Intent
from tools.decision.models import IntentClassification, IntentRule


_INTENT_RULES: tuple[IntentRule, ...] = (
    IntentRule(
        Intent.WEB_SEARCH,
        (
            "recherche web",
            "web search",
            "cherche sur internet",
            "search the",
            "search for",
            "latest news",
            "google ",
            "trouve sur le web",
        ),
        weight=0.95,
        reason="Explicit web search phrasing detected",
    ),
    IntentRule(
        Intent.TRADING,
        (
            "trading",
            "trade ",
            "buy stock",
            "buy order",
            "buy ",
            "sell stock",
            "sell order",
            "sell ",
            "nq ",
            "nasdaq",
            "forex",
            "backtest",
            "position size",
            "achète",
            "vends",
            "bourse",
            "futures",
            "contracts",
        ),
        weight=0.92,
        reason="Trading or market automation keywords detected",
    ),
    IntentRule(
        Intent.CALENDAR,
        (
            "calendrier",
            "calendar",
            "réunion",
            "meeting",
            "agenda",
            "rendez-vous",
            "appointment",
            "schedule",
            "planifier",
        ),
        weight=0.9,
        reason="Calendar or scheduling keywords detected",
    ),
    IntentRule(
        Intent.EMAIL,
        (
            "email",
            "e-mail",
            "courriel",
            "envoie un mail",
            "send mail",
            "send email",
            "boîte mail",
            "inbox",
        ),
        weight=0.9,
        reason="Email-related keywords detected",
    ),
    IntentRule(
        Intent.MEMORY,
        (
            "souviens-toi",
            "souviens toi",
            "remember that",
            "rappelle-toi",
            "rappelle toi",
            "recall my",
            "oublie pas",
            "mémorise",
            "memorize",
            "what do you know about me",
            "que sais-tu de moi",
        ),
        weight=0.88,
        reason="Memory recall or store phrasing detected",
    ),
    IntentRule(
        Intent.FILE,
        (
            "lire le fichier",
            "lire fichier",
            "read file",
            "contenu du fichier",
            "affiche le fichier",
            "ouvre le fichier",
            "show file",
            "open file",
            "écris dans",
            "ecrire dans",
            "write file",
            "crée le fichier",
            "cree le fichier",
            "create file",
            "écrire le fichier",
        ),
        weight=0.93,
        reason="File read or write operation detected",
    ),
    IntentRule(
        Intent.DOCUMENT,
        (
            "document",
            "pdf",
            "docx",
            "markdown doc",
            "rapport",
            "report file",
        ),
        weight=0.82,
        reason="Document handling keywords detected",
    ),
    IntentRule(
        Intent.CODING,
        (
            "python",
            "code",
            "fonction",
            "function",
            "bug",
            "debug",
            "exécute python",
            "execute python",
            "run python",
            "exec python",
            "lance ce code",
            "script",
            "refactor",
            "implémente",
            "implement",
        ),
        weight=0.85,
        reason="Coding or execution keywords detected",
    ),
    IntentRule(
        Intent.SYSTEM,
        (
            "heure",
            "quelle heure",
            "what time",
            "current time",
            "datetime",
            "date et heure",
            "quelle date",
            "system status",
            "état du système",
        ),
        weight=0.9,
        reason="System or datetime query detected",
    ),
    IntentRule(
        Intent.GENERAL_CHAT,
        (
            "bonjour",
            "salut",
            "hello",
            "hi ",
            "merci",
            "thanks",
            "comment ça va",
            "how are you",
        ),
        weight=0.75,
        reason="Greeting or casual conversation detected",
    ),
)

_NO_TOOL_CHAT_PATTERNS: tuple[str, ...] = (
    "what is ",
    "qu'est-ce que ",
    "combien font",
    "2+2",
    "2 + 2",
    "translate",
    "traduis",
    "traduction",
    "explain what",
    "explique ce que",
)


class IntentClassifier:
    """Classify user messages into intents with confidence and rationale."""

    def classify(self, message: str) -> IntentClassification:
        """Return the best-matching intent with confidence in [0, 1]."""
        lowered = message.lower().strip()
        if not lowered:
            return IntentClassification(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                reason="Empty message",
            )

        if _matches_no_tool_chat(lowered):
            return IntentClassification(
                intent=Intent.GENERAL_CHAT,
                confidence=0.92,
                reason="Conversational or knowledge question — no external tool implied",
            )

        scores: dict[Intent, tuple[float, str]] = {}
        for rule in _INTENT_RULES:
            rule_score = rule.score(lowered)
            if rule_score <= 0:
                continue
            current = scores.get(rule.intent)
            if current is None or rule_score > current[0]:
                scores[rule.intent] = (rule_score, rule.reason)

        if not scores:
            return IntentClassification(
                intent=Intent.UNKNOWN,
                confidence=0.35,
                reason="No intent keywords matched",
            )

        scores = _apply_intent_precedence(lowered, scores)

        best_intent = max(scores, key=lambda intent: scores[intent][0])
        best_score, best_reason = scores[best_intent]
        confidence = min(best_score, 1.0)

        if len(scores) > 1:
            sorted_scores = sorted(scores.values(), key=lambda item: item[0], reverse=True)
            margin = sorted_scores[0][0] - sorted_scores[1][0]
            if margin < 0.08:
                confidence = max(confidence * 0.75, 0.45)
                best_reason = (
                    f"{best_reason}; ambiguous overlap with other intents "
                    f"(margin={margin:.2f})"
                )

        return IntentClassification(
            intent=best_intent,
            confidence=round(confidence, 3),
            reason=best_reason,
        )


def _matches_no_tool_chat(lowered: str) -> bool:
    """Detect messages that should stay in direct LLM response path."""
    if any(pattern in lowered for pattern in _NO_TOOL_CHAT_PATTERNS):
        return True
    if lowered.endswith("?") and not any(
        kw in lowered
        for kw in (
            "heure",
            "time",
            "fichier",
            "file",
            "search",
            "recherche",
            "calendar",
            "email",
            "python",
        )
    ):
        if len(lowered.split()) <= 12:
            return True
    return False


def _apply_intent_precedence(
    lowered: str,
    scores: dict[Intent, tuple[float, str]],
) -> dict[Intent, tuple[float, str]]:
    """Resolve known cross-intent collisions (e.g. market news search vs trading)."""
    search_signals = ("search", "recherche", "latest news", "news", "google ")
    if Intent.WEB_SEARCH in scores and Intent.TRADING in scores:
        if any(signal in lowered for signal in search_signals):
            del scores[Intent.TRADING]
    if Intent.FILE in scores and Intent.CODING in scores:
        file_ops = ("lire", "read", "write", "écris", "ecri", "fichier", "file")
        if any(op in lowered for op in file_ops):
            coding_score = scores[Intent.CODING][0]
            scores[Intent.CODING] = (coding_score * 0.6, scores[Intent.CODING][1])
    return scores
