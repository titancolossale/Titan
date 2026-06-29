# =====================================
# Titan LLM System Instructions Tests
# =====================================

"""Tests for Phase 2 LLM gateway: identity, constitution, model config (P2-004–P2-005)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from brain.identity import IDENTITY
from brain.llm import LLM, build_system_instructions, load_prompt_file
from brain.llm_provider import LLMProvider


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Minimal prompts directory for isolated instruction assembly."""
    (tmp_path / "system_instructions.md").write_text(
        "Base system rules.",
        encoding="utf-8",
    )
    (tmp_path / "constitution_summary.md").write_text(
        "Résumé constitution test.",
        encoding="utf-8",
    )
    return tmp_path


def test_load_prompt_file_returns_content(prompts_dir: Path) -> None:
    """P2-004: prompt files load from configured directory."""
    content = load_prompt_file("system_instructions.md", prompts_dir)
    assert content == "Base system rules."


def test_load_prompt_file_missing_returns_empty(tmp_path: Path) -> None:
    """P2-004: missing prompt file returns empty string without raising."""
    assert load_prompt_file("missing.md", tmp_path) == ""


def test_build_system_instructions_includes_identity_and_constitution(
    prompts_dir: Path,
) -> None:
    """P2-004/P2-005: system instructions contain identity and constitution summary."""
    instructions = build_system_instructions(prompts_dir)

    assert "Base system rules." in instructions
    assert "Nolan Hassing" in instructions
    assert IDENTITY.strip()[:40] in instructions
    assert "Résumé constitution test." in instructions
    assert "CONSTITUTION (résumé)" in instructions


def test_llm_uses_configured_model(prompts_dir: Path) -> None:
    """P2-002/P2-004: LLM passes model name from constructor to API call."""
    with patch("brain.llm.OpenAI"):
        llm = LLM(model="test-model-42", prompts_dir=prompts_dir)
    llm.client = MagicMock()
    response = MagicMock()
    response.output_text = "ok"
    llm.client.responses.create.return_value = response

    llm.ask("hello")

    call_kwargs = llm.client.responses.create.call_args.kwargs
    assert call_kwargs["model"] == "test-model-42"
    assert "Nolan Hassing" in call_kwargs["instructions"]


def test_llm_system_instructions_property(prompts_dir: Path) -> None:
    """P2-005: system_instructions property exposes assembled prompt."""
    with patch("brain.llm.OpenAI"):
        llm = LLM(prompts_dir=prompts_dir)

    assert "Résumé constitution test." in llm.system_instructions


def test_llm_implements_provider_interface(prompts_dir: Path) -> None:
    """P2-003: LLM satisfies LLMProvider abstract contract."""
    with patch("brain.llm.OpenAI"):
        llm = LLM(prompts_dir=prompts_dir)

    assert isinstance(llm, LLMProvider)
    assert callable(llm.ask)
    assert isinstance(llm.system_instructions, str)


def test_production_prompts_load_constitution_summary() -> None:
    """P2-001/P2-004: repo prompts/ constitution summary loads in default LLM path."""
    from pathlib import Path

    project_root = Path(__file__).resolve().parent.parent
    prompts_dir = project_root / "prompts"
    instructions = build_system_instructions(prompts_dir)

    assert "Constitution Titan" in instructions or "CONSTITUTION" in instructions
    assert "Nolan Hassing" in instructions
