# =====================================
# Titan Tool Decision — Patch Preview
# =====================================

"""Generate read-only unified diff previews — never writes (Phase 11 — P11-303)."""

from __future__ import annotations

import difflib
from pathlib import Path

from tools.decision.modification_models import PatchPreview


def generate_unified_diff(
    path: str,
    *,
    original: str,
    proposed: str,
    change_type: str = "modify",
) -> PatchPreview:
    """Build a unified diff preview without touching the filesystem."""
    original_lines = original.splitlines(keepends=True)
    proposed_lines = proposed.splitlines(keepends=True)
    diff_lines = difflib.unified_diff(
        original_lines,
        proposed_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    unified = "\n".join(diff_lines)
    if not unified.strip():
        unified = f"--- a/{path}\n+++ b/{path}\n@@ No textual changes proposed @@"
    return PatchPreview(
        path=path,
        change_type=change_type,
        unified_diff=unified,
    )


def generate_create_file_preview(path: str, proposed_content: str) -> PatchPreview:
    """Preview a new file as a unified diff against empty content."""
    return generate_unified_diff(
        path,
        original="",
        proposed=proposed_content,
        change_type="create",
    )


def read_file_safe(project_root: Path, rel_path: str) -> str:
    """Read a project file for diff baseline; returns empty string if missing."""
    target = project_root / rel_path
    if not target.is_file():
        return ""
    try:
        return target.read_text(encoding="utf-8")
    except OSError:
        return ""


def append_registration_snippet(
    existing: str,
    *,
    import_line: str,
    register_line: str,
    anchor: str,
) -> str:
    """Propose registration changes by inserting after a known anchor."""
    lines = existing.splitlines()
    if import_line and import_line not in existing:
        insert_at = 0
        for index, line in enumerate(lines):
            if line.startswith("from tools.") or line.startswith("import "):
                insert_at = index + 1
        lines.insert(insert_at, import_line)

    if register_line in existing:
        return "\n".join(lines) + ("\n" if existing.endswith("\n") else "")

    anchor_index = next(
        (index for index, line in enumerate(lines) if anchor in line),
        len(lines) - 1,
    )
    lines.insert(anchor_index + 1, register_line)
    body = "\n".join(lines)
    if existing.endswith("\n") and not body.endswith("\n"):
        body += "\n"
    return body


def propose_capability_tool_file(entity: str) -> str:
    """Return a stub tool module following Titan conventions."""
    class_name = "".join(part.capitalize() for part in entity.split("_")) + "Tool"
    return f'''# =====================================
# Titan {class_name}
# =====================================

"""{entity} tool capability (proposed — not applied)."""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolSchema
from tools.tool_result import ToolResult


class {class_name}(BaseTool):
    """Proposed {entity} capability."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="{entity}",
            description="Proposed {entity} capability.",
            parameters=[],
        )

    def run(self, **params: object) -> ToolResult:
        del params
        return self._result(success=True, data="Proposed {entity} tool stub.")
'''


def propose_provider_file(entity: str) -> str:
    """Return a stub provider module following Titan conventions."""
    class_name = "".join(part.capitalize() for part in entity.split("_")) + "Provider"
    return f'''# =====================================
# Titan {class_name}
# =====================================

"""{entity} provider (proposed — not applied)."""

from __future__ import annotations

from tools.providers.base_provider import BaseProvider


class {class_name}(BaseProvider):
    """Proposed {entity} provider stub."""

    @property
    def provider_id(self) -> str:
        return "{entity}"
'''


def propose_test_file(module_path: str, entity: str) -> str:
    """Return a minimal pytest stub for a new module."""
    module_import = module_path.replace("/", ".").replace(".py", "")
    return f'''# =====================================
# Titan {entity.title()} Tests
# =====================================

"""Regression tests for proposed {entity} module."""

from __future__ import annotations


def test_{entity}_module_importable() -> None:
    """Smoke import for proposed {entity} module."""
    __import__("{module_import}")
'''
