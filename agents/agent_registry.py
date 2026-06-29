# =====================================
# Titan Agent Registry
# =====================================

"""Unified routing registry — single source for AgentSelector and TaskManager (P5-010)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRoute:
    """One keyword route: primary agent for auto-select, pipeline for orchestration."""

    name: str
    keywords: tuple[str, ...]
    primary_agent: str
    pipeline: tuple[tuple[str, str], ...]
    priority: int = 0


def _fmt(template: str, message: str) -> str:
    return template.format(message=message)


# Higher priority wins when multiple routes match (P5-010).
# Order preserved from legacy AgentSelector / TaskManager behavior.
ROUTES: tuple[AgentRoute, ...] = (
    AgentRoute(
        name="web",
        keywords=(
            "web agent",
            "recherche web",
            "site web",
            "url",
            "navigateur",
        ),
        primary_agent="web",
        pipeline=(
            ("web", "Recherche web pour : {message}"),
            ("reasoning", "Vérifier et résumer les sources pour : {message}"),
        ),
        priority=32,
    ),
    AgentRoute(
        name="automation",
        keywords=(
            "automatise",
            "automatiser",
            "workflow",
            "automation",
            "pipeline automatisé",
        ),
        primary_agent="automation",
        pipeline=(
            ("automation", "Planifier workflow pour : {message}"),
            ("planning", "Structurer les étapes pour : {message}"),
        ),
        priority=34,
    ),
    AgentRoute(
        name="memory",
        keywords=(
            "résume la session",
            "compacte la mémoire",
            "memory agent",
            "résume mémoire session",
        ),
        primary_agent="memory",
        pipeline=(
            ("memory", "Résumer les notes de session pour : {message}"),
        ),
        priority=35,
    ),
    AgentRoute(
        name="coding",
        keywords=("code", "python", "fonction", "programmer", "script"),
        primary_agent="coding",
        pipeline=(
            ("planning", "Créer un plan pour : {message}"),
            ("coding", "Écrire une solution de code pour : {message}"),
            ("reasoning", "Vérifier la logique de la solution pour : {message}"),
        ),
        priority=40,
    ),
    AgentRoute(
        name="research",
        keywords=(
            "recherche",
            "chercher",
            "internet",
            "google",
            "information",
            "actualité",
        ),
        primary_agent="research",
        pipeline=(
            ("research", "Analyser la recherche demandée : {message}"),
            ("reasoning", "Résumer et vérifier les informations pour : {message}"),
        ),
        priority=30,
    ),
    AgentRoute(
        name="planning",
        keywords=(
            "plan",
            "planning",
            "organise",
            "organiser",
            "horaire",
            "programme",
            "journée",
        ),
        primary_agent="planning",
        pipeline=(
            ("planning", "Organiser la demande : {message}"),
            ("reasoning", "Vérifier si le plan est logique : {message}"),
        ),
        priority=20,
    ),
    AgentRoute(
        name="reasoning",
        keywords=(
            "pourquoi",
            "analyse",
            "raisonne",
            "réfléchis",
            "explique",
            "logique",
        ),
        primary_agent="reasoning",
        pipeline=(
            ("reasoning", "Comprendre et analyser la demande : {message}"),
            ("planning", "Proposer une prochaine étape pour : {message}"),
        ),
        priority=10,
    ),
)

DEFAULT_PRIMARY_AGENT = "base"
DEFAULT_PIPELINE: tuple[tuple[str, str], ...] = (
    ("reasoning", "Comprendre et analyser la demande : {message}"),
    ("planning", "Proposer une prochaine étape pour : {message}"),
)


class AgentRegistry:
    """Keyword routing registry shared by selector and task manager."""

    def __init__(self, routes: tuple[AgentRoute, ...] = ROUTES) -> None:
        self._routes = tuple(sorted(routes, key=lambda route: route.priority, reverse=True))

    @property
    def routes(self) -> tuple[AgentRoute, ...]:
        return self._routes

    def match_route(self, message: str) -> AgentRoute | None:
        """Return the highest-priority route whose keywords appear in message."""
        message_lower = message.lower()
        for route in self._routes:
            if any(keyword in message_lower for keyword in route.keywords):
                return route
        return None

    def select_agent(self, message: str) -> str:
        """Single-agent selection for auto_execute (legacy AgentSelector contract)."""
        route = self.match_route(message)
        if route is None:
            return DEFAULT_PRIMARY_AGENT
        return route.primary_agent

    def create_tasks(self, message: str) -> list[tuple[str, str]]:
        """Multi-agent task list for orchestrator (legacy TaskManager contract)."""
        route = self.match_route(message)
        pipeline = route.pipeline if route is not None else DEFAULT_PIPELINE
        return [(agent_name, _fmt(task_template, message)) for agent_name, task_template in pipeline]


# Module-level default registry instance.
default_registry = AgentRegistry()
