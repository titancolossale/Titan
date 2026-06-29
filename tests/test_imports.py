# =====================================
# Titan Import Smoke Tests
# =====================================

"""Verify all production modules import without circular dependency errors."""

from __future__ import annotations

import importlib

import pytest

# Every importable production module (excludes main.py — it starts the REPL on import).
PRODUCTION_MODULES = [
    "config.settings",
    "core.logging_config",
    "core.titan",
    "core.state_manager",
    "core.mission_manager",
    "core.task_manager",
    "core.task_orchestrator",
    "core.conversation",
    "core.conversation_engine",
    "core.conversation_models",
    "brain.brain",
    "brain.decision",
    "brain.reasoning",
    "brain.planning",
    "brain.knowledge",
    "brain.executor",
    "brain.llm",
    "brain.llm_provider",
    "brain.prompt_builder",
    "brain.pipeline.context_bundle",
    "brain.pipeline.stages",
    "brain.internal_monologue",
    "brain.executive_brain",
    "brain.task_evaluator",
    "brain.identity",
    "agents.agent_registry",
    "agents.agent_result",
    "agents.agent_context",
    "agents.agent_manager",
    "agents.agent_response_parser",
    "agents.agent_llm",
    "agents.llm_agent_mixin",
    "agents.memory_agent",
    "agents.general_agent",
    "agents.agent_selector",
    "agents.base_agent",
    "agents.coding_agent",
    "agents.research_agent",
    "agents.planning_agent",
    "agents.reasoning_agent",
    "memory.memory_manager",
    "memory.memory",
    "memory.long_term_memory",
    "memory.memory_service",
    "memory.memory_migrator",
    "memory.models",
    "memory.memory_decider",
    "memory.memory_classifier",
    "memory.memory_retriever",
    "context.context_manager",
    "context.context_engine",
    "context.context_formatter",
    "context.models",
    "context.session_manager",
    "tools.tool_manager",
    "tools.time_tool",
    "tools.base_tool",
    "tools.tool_registry",
    "tools.tool_result",
    "tools.tool_policy",
    "tools.path_guard",
    "tools.file_read_tool",
    "tools.file_write_tool",
    "tools.python_exec_tool",
    "tools.web_search_tool",
    "tools.calendar_tool",
    "tools.decision",
    "tools.decision.tool_decision_engine",
    "brain.tool_dispatcher",
]


@pytest.mark.parametrize("module_name", PRODUCTION_MODULES)
def test_production_module_imports(module_name: str) -> None:
    """Each production module must import cleanly (no circular dependency)."""
    importlib.import_module(module_name)
