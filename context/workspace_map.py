# =====================================
# Titan Workspace Map
# =====================================

"""Lightweight project-area map for workspace intelligence (Phase 11 — P11-003)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceArea:
    """One logical area of the Titan codebase."""

    key: str
    label: str
    directories: tuple[str, ...]
    key_files: tuple[str, ...]
    description: str
    extension_points: tuple[str, ...] = ()


_WORKSPACE_AREAS: dict[str, WorkspaceArea] = {
    "brain": WorkspaceArea(
        key="brain",
        label="Brain / orchestration cognitive",
        directories=("brain/",),
        key_files=(
            "brain/brain.py",
            "brain/llm.py",
            "brain/reasoning.py",
            "brain/executor.py",
            "brain/prompt_builder.py",
        ),
        description=(
            "Orchestration cognitive : pipeline think(), assemblage de prompts, "
            "coordination agents/outils."
        ),
    ),
    "memory": WorkspaceArea(
        key="memory",
        label="Mémoire durable et session",
        directories=("memory/",),
        key_files=(
            "memory/memory_service.py",
            "memory/long_term_memory.py",
            "memory/memory_retriever.py",
            "memory/memory_decider.py",
            "memory/memory_classifier.py",
        ),
        description=(
            "Stockage, classification, récupération et écriture de la mémoire "
            "long terme isolée par utilisateur."
        ),
    ),
    "agents": WorkspaceArea(
        key="agents",
        label="Agents spécialisés",
        directories=("agents/",),
        key_files=(
            "agents/agent_manager.py",
            "agents/agent_selector.py",
            "agents/base_agent.py",
            "core/task_orchestrator.py",
        ),
        description="Spécialistes internes exécutés par l'orchestrateur, consommés par le Brain.",
    ),
    "tools": WorkspaceArea(
        key="tools",
        label="Outils et runtime",
        directories=("tools/",),
        key_files=(
            "tools/tool_manager.py",
            "tools/tool_runtime.py",
            "tools/capability_catalog.py",
            "tools/decision/tool_decision_engine.py",
        ),
        description="Capacités externes, politique, confirmation et exécution via Tool Runtime V2.",
        extension_points=(
            "tools/{name}_tool.py",
            "tools/tool_manager.py",
            "tools/decision/tool_ranker.py",
        ),
    ),
    "providers": WorkspaceArea(
        key="providers",
        label="Providers externes",
        directories=("tools/providers/",),
        key_files=(
            "tools/providers/provider_registry.py",
            "tools/providers/provider_executor.py",
            "tools/providers/defaults.py",
        ),
        description="Backends file_system, github, web_search et enregistrement des providers.",
    ),
    "config": WorkspaceArea(
        key="config",
        label="Configuration statique",
        directories=("config/",),
        key_files=("config/settings.py",),
        description="Version, chemins par défaut, feature flags non secrets.",
    ),
    "context": WorkspaceArea(
        key="context",
        label="Contexte opérationnel",
        directories=("context/", "core/"),
        key_files=(
            "context/context_manager.py",
            "core/state_manager.py",
            "core/mission_manager.py",
        ),
        description="Contexte utilisateur/projet synchronisé avec état et mission.",
    ),
    "tests": WorkspaceArea(
        key="tests",
        label="Tests automatisés",
        directories=("tests/",),
        key_files=("tests/",),
        description="Couverture pytest des managers, Brain, outils et décision.",
    ),
}

_AREA_ALIASES: dict[str, str] = {
    "brain": "brain",
    "cerveau": "brain",
    "orchestration": "brain",
    "orchestrateur": "brain",
    "memory": "memory",
    "memoire": "memory",
    "mémoire": "memory",
    "mem": "memory",
    "agents": "agents",
    "agent": "agents",
    "tools": "tools",
    "outil": "tools",
    "outils": "tools",
    "capability": "tools",
    "capacite": "tools",
    "capacité": "tools",
    "capacities": "tools",
    "providers": "providers",
    "provider": "providers",
    "config": "config",
    "configuration": "config",
    "settings": "config",
    "context": "context",
    "contexte": "context",
    "tests": "tests",
    "test": "tests",
}


def list_areas() -> tuple[str, ...]:
    """Return canonical workspace area keys."""
    return tuple(_WORKSPACE_AREAS.keys())


def get_area(key: str) -> WorkspaceArea | None:
    """Return a workspace area by canonical key or alias."""
    normalized = _AREA_ALIASES.get(key.lower().strip(), key.lower().strip())
    return _WORKSPACE_AREAS.get(normalized)


def find_area_in_message(message: str) -> str | None:
    """Detect the most likely workspace area referenced in natural language."""
    lowered = message.lower()
    best_key: str | None = None
    best_len = 0
    for alias, key in _AREA_ALIASES.items():
        if len(alias) < 3:
            continue
        if re.search(rf"\b{re.escape(alias)}\b", lowered):
            if len(alias) > best_len:
                best_key = key
                best_len = len(alias)
    if best_key:
        return best_key
    for key, area in _WORKSPACE_AREAS.items():
        for directory in area.directories:
            token = directory.rstrip("/").lower()
            if token and token in lowered:
                return key
    return None


def files_for_area(area_key: str, *, project_root: Path | None = None) -> tuple[str, ...]:
    """Return key files for an area, filtered to those that exist on disk."""
    area = get_area(area_key)
    if area is None:
        return ()
    if project_root is None:
        return area.key_files
    existing: list[str] = []
    for rel in area.key_files:
        if rel.endswith("/"):
            continue
        if (project_root / rel).is_file():
            existing.append(rel)
    if existing:
        return tuple(existing)
    return area.key_files


def controller_files_for_area(area_key: str, *, project_root: Path | None = None) -> tuple[str, ...]:
    """Return the primary control files for an area (for 'which files control X' queries)."""
    return files_for_area(area_key, project_root=project_root)[:3]


def extension_point_files(area_key: str = "tools") -> tuple[str, ...]:
    """Return documented extension points for adding capabilities."""
    area = get_area(area_key)
    if area is None:
        return ()
    return area.extension_points or area.key_files[:2]


def summarize_area(area_key: str) -> str:
    """Return a short human-readable summary of an area."""
    area = get_area(area_key)
    if area is None:
        return f"Aire inconnue : {area_key}"
    files = ", ".join(area.key_files[:4])
    return f"{area.label} — {area.description} Fichiers clés : {files}."
