# =====================================
# Titan Tool Decision — Intent Classifier
# =====================================

"""Heuristic intent classification with confidence scoring (Phase 10B — P10B-001/002)."""

from __future__ import annotations

import re

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
            "latest ",
            " news",
            "nouvelles",
            "actualités",
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
            "positions",
            "position ",
            "mes positions",
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
            "reunion",
            "meeting",
            "agenda",
            "rendez-vous",
            "rendez vous",
            "appointment",
            "schedule",
            "planifier",
            "événement",
            "evenement",
            "événements",
            "evenements",
            "créneau",
            "creneau",
            "créneau libre",
            "creneau libre",
            "qu'est-ce que j'ai",
            "quest ce que j ai",
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
        Intent.WORKSPACE_EXPLAIN,
        (
            "explique-moi ce fichier",
            "explique ce fichier",
            "explique-moi le fichier",
            "explique le fichier",
            "explain this file",
            "explain the file",
            "explique-moi ",
            "explique ",
            "explain ",
            "explique-moi comment",
            "explique comment",
            "explain how",
            "comment fonctionne",
            "how does the",
            "how does ",
            "résume",
            "resume ",
            "summarize",
            "summarise",
            "quels fichiers contrôlent",
            "quels fichiers controlent",
            "which files control",
            "what files control",
            "où dois-je modifier",
            "ou dois-je modifier",
            "where should i modify",
            "où modifier",
            "ajouter une nouvelle capacité",
            "add a new capability",
            "nouvelle capacité",
            "new capability",
            "nouvel outil",
            "new tool",
            "trouve le fichier",
            "find the file",
            "cherche le fichier",
            "search for the file",
            "locate the file",
            "explique-le",
            "fichier qui parle",
            "fichier qui contrôle",
            "fichier qui control",
            "file that talks",
            "file that controls",
            "le fichier qui",
            "the file that",
        ),
        weight=0.96,
        reason="Workspace explanation or project navigation request detected",
    ),
    IntentRule(
        Intent.WORKSPACE_MODIFY,
        (
            "ajoute ",
            "ajouter ",
            "ajoutez ",
            "add a new",
            "add new",
            "add an ",
            "create ",
            "crée ",
            "cree ",
            "créer ",
            "implement ",
            "implémente ",
            "implemente ",
            "corrige ",
            "corriger ",
            "fix this bug",
            "fix the bug",
            "fix ",
            "patch ",
            "modifie ",
            "modifier ",
            "modify ",
            "ajoute une commande",
            "add a command",
            "add command",
            "ajoute un provider",
            "add a provider",
            "add provider",
            "ajoute une capacité",
            "ajoute une capacite",
            "add a capability",
            "ajoute une mémoire",
            "ajoute une memoire",
            "add a memory",
        ),
        weight=0.97,
        reason="Workspace modification planning request detected",
    ),
    IntentRule(
        Intent.FILE_LIST,
        (
            "liste les fichiers",
            "liste les ",
            "list files",
            "list the files",
            "list all files",
            "montre les fichiers",
            "show files in",
            "show the files",
            "affiche les fichiers",
            "fichiers du projet",
            "files in the project",
        ),
        weight=0.94,
        reason="File listing operation detected",
    ),
    IntentRule(
        Intent.FILE_SEARCH,
        (
            "trouve les fichiers",
            "trouve le fichier",
            "trouve des fichiers",
            "trouve les ",
            "find file",
            "find ",
            "locate ",
            "cherche ",
            "chercher ",
            "search for ",
            "look for ",
            "recherche de fichiers",
            "recherche fichier",
            "qui parlent de",
            "contenant ",
            "containing ",
        ),
        weight=0.94,
        reason="File search operation detected",
    ),
    IntentRule(
        Intent.FILE_READ,
        (
            "lire le fichier",
            "lire fichier",
            "read file",
            "contenu du fichier",
            "affiche le fichier",
            "ouvre le fichier",
            "show file",
            "open file",
        ),
        weight=0.95,
        reason="File read operation detected",
    ),
    IntentRule(
        Intent.FILE_METADATA,
        (
            "métadonnées",
            "metadonnees",
            "metadata",
            "info du fichier",
            "file info",
            "informations sur le fichier",
            "taille du fichier",
        ),
        weight=0.91,
        reason="File metadata query detected",
    ),
    IntentRule(
        Intent.FILE,
        (
            "écris dans",
            "ecrire dans",
            "write file",
            "crée le fichier",
            "cree le fichier",
            "create file",
            "écrire le fichier",
        ),
        weight=0.93,
        reason="File write operation detected",
    ),
    IntentRule(
        Intent.GITHUB,
        (
            "commit",
            "commits",
            "latest commits",
            "show latest commits",
            "pull request",
            "pull requests",
            "github",
            "repository",
            "repo ",
            "issue",
            "issues",
            "branch",
            "branches",
            "merge request",
        ),
        weight=0.94,
        reason="GitHub repository operation detected",
    ),
    IntentRule(
        Intent.OBSIDIAN,
        (
            "obsidian",
            "vault",
            "titan ai",
            "mes notes",
            "note obsidian",
            "dans le vault",
            "dans obsidian",
            "dans mon vault",
            "search vault",
            "search notes",
            "cherche les notes",
            "notes liées",
            "notes liees",
            "santé du vault",
            "sante du vault",
            "analyse la santé",
            "analyse la sante",
        ),
        weight=0.95,
        reason="Obsidian vault operation detected",
    ),
    IntentRule(
        Intent.BROWSER,
        (
            "navigateur",
            "browser",
            "page web",
            "webpage",
            "site web",
            "website",
            "ouvre la page",
            "open page",
            "open webpage",
            "navigate to",
            "navigue vers",
            "va sur",
            "go to",
            "lis la page",
            "lis cette page",
            "read page",
            "contenu de la page",
            "extrait le texte",
            "extract text",
            "défiler",
            "defiler",
            "scroll",
            "capture d'écran",
            "capture ecran",
            "prends une capture",
            "prend une capture",
            "screenshot",
            "titre de la page",
            "http://",
            "https://",
        ),
        weight=0.94,
        reason="Browser page interaction detected",
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

        if _has_calendar_scheduling_context(lowered):
            return IntentClassification(
                intent=Intent.CALENDAR,
                confidence=0.93,
                reason="Calendar scheduling context detected",
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


_CALENDAR_SCHEDULING_SIGNALS: tuple[str, ...] = (
    "événement",
    "evenement",
    "événements",
    "evenements",
    "créneau",
    "creneau",
    "agenda",
    "calendrier",
    "calendar",
    "réunion",
    "reunion",
    "rendez-vous",
    "rendez vous",
    "qu'est-ce que j'ai",
    "quest ce que j ai",
    "emploi du temps",
    "my schedule",
)


def _has_calendar_scheduling_context(lowered: str) -> bool:
    """Return True when the message targets calendar scheduling, not general chat."""
    if any(signal in lowered for signal in _CALENDAR_SCHEDULING_SIGNALS):
        return True
    scheduling_time = ("demain", "tomorrow", "aujourd'hui", "aujourdhui", "today")
    return any(
        time_word in lowered and phrase in lowered
        for time_word in scheduling_time
        for phrase in ("qu'est-ce que j'ai", "quest ce que j ai", "créneau", "creneau")
    )


def _matches_no_tool_chat(lowered: str) -> bool:
    """Detect messages that should stay in direct LLM response path."""
    if _has_calendar_scheduling_context(lowered):
        return False
    workspace_signals = (
        "explique",
        "explain",
        "résume",
        "resume",
        "summarize",
        "fichier",
        "file",
        "brain",
        "mémoire",
        "memoire",
        "capacité",
        "capacite",
        "capability",
        "modifier le code",
        "contrôlent",
        "control",
    )
    if any(signal in lowered for signal in workspace_signals):
        return False
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
    if _has_calendar_scheduling_context(lowered) and Intent.CALENDAR in scores:
        for competing in (
            Intent.FILE_SEARCH,
            Intent.WORKSPACE_MODIFY,
            Intent.FILE,
            Intent.FILE_LIST,
        ):
            if competing in scores:
                reduced = scores[competing][0] * 0.35
                scores[competing] = (reduced, scores[competing][1])
        calendar_score = scores[Intent.CALENDAR][0]
        scores[Intent.CALENDAR] = (
            max(calendar_score, 0.95),
            scores[Intent.CALENDAR][1],
        )
    search_signals = ("search", "recherche", "latest news", "news", "google ")
    if Intent.WEB_SEARCH in scores and Intent.TRADING in scores:
        if any(signal in lowered for signal in search_signals):
            del scores[Intent.TRADING]
    file_intents = {
        Intent.FILE,
        Intent.FILE_LIST,
        Intent.FILE_SEARCH,
        Intent.FILE_READ,
        Intent.FILE_METADATA,
    }
    if file_intents.intersection(scores) and Intent.CODING in scores:
        file_ops = ("lire", "read", "write", "écris", "ecri", "fichier", "file", "find", "liste", "cherche")
        if any(op in lowered for op in file_ops):
            coding_score = scores[Intent.CODING][0]
            scores[Intent.CODING] = (coding_score * 0.6, scores[Intent.CODING][1])
    if file_intents.intersection(scores) and Intent.GITHUB in scores:
        if _PATH_PATTERN.search(lowered) or any(
            kw in lowered for kw in ("find", "fichier", "file", ".md", ".py", ".txt", "liste", "cherche")
        ):
            github_score = scores[Intent.GITHUB][0]
            scores[Intent.GITHUB] = (github_score * 0.55, scores[Intent.GITHUB][1])
    obsidian_signals = (
        "obsidian",
        "vault",
        "titan ai",
        "dans obsidian",
        "dans le vault",
        "mes notes",
    )
    if Intent.OBSIDIAN in scores:
        if any(signal in lowered for signal in obsidian_signals):
            for file_intent in file_intents:
                if file_intent in scores:
                    reduced = scores[file_intent][0] * 0.45
                    scores[file_intent] = (reduced, scores[file_intent][1])
        if Intent.DOCUMENT in scores:
            doc_score = scores[Intent.DOCUMENT][0] * 0.5
            scores[Intent.DOCUMENT] = (doc_score, scores[Intent.DOCUMENT][1])
    if Intent.FILE_SEARCH in scores and Intent.WEB_SEARCH in scores:
        if not any(signal in lowered for signal in ("internet", "web", "google", "news", "actualités")):
            del scores[Intent.WEB_SEARCH]
    if Intent.BROWSER in scores and Intent.WEB_SEARCH in scores:
        browser_signals = (
            "http://",
            "https://",
            "ouvre la page",
            "open page",
            "navigate to",
            "lis la page",
            "read page",
            "page web",
            "webpage",
        )
        if any(signal in lowered for signal in browser_signals):
            web_score = scores[Intent.WEB_SEARCH][0] * 0.45
            scores[Intent.WEB_SEARCH] = (web_score, scores[Intent.WEB_SEARCH][1])
    if Intent.FILE_LIST in scores and Intent.FILE_SEARCH in scores:
        if any(kw in lowered for kw in ("liste", "list ", "montre les fichiers", "show files")):
            search_score = scores[Intent.FILE_SEARCH][0]
            scores[Intent.FILE_SEARCH] = (search_score * 0.55, scores[Intent.FILE_SEARCH][1])
    explain_signals = ("explique", "explain", "résume", "resume", "summarize", "summarise")
    if any(signal in lowered for signal in explain_signals):
        has_path = _PATH_PATTERN.search(lowered) is not None
        has_search = any(
            signal in lowered
            for signal in ("trouve", "find ", "cherche", "locate", "search for")
        )
        has_referential = any(
            signal in lowered
            for signal in ("fichier qui", "file that", "le fichier qui", "the file that")
        )
        if has_path or has_search or has_referential:
            if Intent.WORKSPACE_EXPLAIN not in scores:
                scores[Intent.WORKSPACE_EXPLAIN] = (
                    0.97,
                    "Search-then-explain workspace flow",
                )
            for file_intent in file_intents:
                if file_intent in scores:
                    reduced = scores[file_intent][0] * 0.45
                    scores[file_intent] = (reduced, scores[file_intent][1])
    workspace_intents = {Intent.WORKSPACE_EXPLAIN}
    if Intent.WORKSPACE_EXPLAIN in scores:
        for file_intent in file_intents:
            if file_intent in scores and file_intent != Intent.WORKSPACE_EXPLAIN:
                reduced = scores[file_intent][0] * 0.55
                scores[file_intent] = (reduced, scores[file_intent][1])
        if Intent.CODING in scores:
            coding_score = scores[Intent.CODING][0] * 0.5
            scores[Intent.CODING] = (coding_score, scores[Intent.CODING][1])
        project_signals = (
            "brain",
            "mémoire",
            "memoire",
            "memory",
            "titan",
            "agent",
            "fichier",
            "file",
            "workspace",
            "projet",
            "project",
            "outil",
            "tool",
            "capacité",
            "capability",
            "provider",
            "config/",
            "settings.py",
        )
        if not any(signal in lowered for signal in project_signals):
            has_search_then_explain = any(
                signal in lowered for signal in explain_signals
            ) and (
                _PATH_PATTERN.search(lowered) is not None
                or any(
                    signal in lowered
                    for signal in ("trouve", "find ", "cherche", "locate", "search for")
                )
                or any(
                    signal in lowered
                    for signal in (
                        "fichier qui",
                        "file that",
                        "le fichier qui",
                        "the file that",
                    )
                )
            )
            if not has_search_then_explain:
                del scores[Intent.WORKSPACE_EXPLAIN]
    if Intent.WORKSPACE_MODIFY in scores:
        where_explain_signals = (
            "où dois-je",
            "ou dois-je",
            "where should i",
            "where to modify",
            "où modifier",
            "where modify",
        )
        if any(signal in lowered for signal in where_explain_signals):
            explain_score = scores.get(Intent.WORKSPACE_EXPLAIN, (0.0, ""))[0]
            scores[Intent.WORKSPACE_EXPLAIN] = (
                max(explain_score, 0.98),
                "Extension point or where-to-modify question",
            )
            modify_score = scores[Intent.WORKSPACE_MODIFY][0] * 0.35
            scores[Intent.WORKSPACE_MODIFY] = (
                modify_score,
                scores[Intent.WORKSPACE_MODIFY][1],
            )
    if Intent.WORKSPACE_MODIFY in scores and Intent.WORKSPACE_EXPLAIN in scores:
        explain_only = any(
            signal in lowered
            for signal in (
                "explique",
                "explain",
                "où dois-je",
                "ou dois-je",
                "where should i",
                "where to modify",
                "où modifier",
                "where modify",
            )
        )
        modify_verbs = (
            "ajoute",
            "ajouter",
            "add ",
            "create",
            "crée",
            "cree",
            "implement",
            "implémente",
            "corrige",
            "corriger",
            "fix ",
            "patch",
            "modifie",
            "modifier",
        )
        has_modify = any(verb in lowered for verb in modify_verbs)
        if explain_only and not has_modify:
            del scores[Intent.WORKSPACE_MODIFY]
        elif has_modify:
            explain_score = scores[Intent.WORKSPACE_EXPLAIN][0] * 0.45
            scores[Intent.WORKSPACE_EXPLAIN] = (
                explain_score,
                scores[Intent.WORKSPACE_EXPLAIN][1],
            )
    if Intent.WORKSPACE_MODIFY in scores and Intent.CODING in scores:
        coding_score = scores[Intent.CODING][0] * 0.5
        scores[Intent.CODING] = (coding_score, scores[Intent.CODING][1])
    return scores


_PATH_PATTERN = re.compile(
    r"(?:[\w./\\-]+[/\\])?[\w.-]+\.(?:py|txt|md|json|yaml|yml|toml|cfg|ini|pdf|docx?)",
    re.IGNORECASE,
)
