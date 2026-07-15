# =====================================
# Titan Workspace Guidance
# =====================================

"""User-facing guidance for workspace explanation mode (Phase 11 — P11-006)."""

from __future__ import annotations

WORKSPACE_EXPLANATION_GUIDANCE = (
    "[Mode explication workspace]\n"
    "Pour chaque fichier lu ci-dessous :\n"
    "- Résume le rôle du fichier\n"
    "- Explique les fonctions/classes importantes\n"
    "- Explique comment le fichier se connecte au reste de Titan\n"
    "- Mentionne l'incertitude si le contenu est incomplet\n"
    "- Suggère un prochain fichier à inspecter si utile"
)


def format_workspace_tool_results(
    tool_results_text: str,
    *,
    explanation_mode: str | None,
    area_summary: str = "",
) -> str:
    """Prefix tool output with workspace explanation instructions when active."""
    if not explanation_mode or not tool_results_text.strip():
        return tool_results_text
    blocks = [WORKSPACE_EXPLANATION_GUIDANCE]
    if area_summary:
        blocks.append(f"[Contexte zone]\n{area_summary}")
    blocks.append(tool_results_text)
    return "\n\n".join(blocks)


def collect_files_read(tool_results: list) -> tuple[str, ...]:
    """Extract successfully read file paths from tool result metadata."""
    paths: list[str] = []
    for result in tool_results:
        if not getattr(result, "success", False):
            continue
        metadata = getattr(result, "metadata", None) or {}
        operation = metadata.get("file_operation")
        target = metadata.get("target_path")
        if operation in {"read_file", "get_metadata"} and target:
            normalized = str(target).replace("\\", "/")
            if normalized not in paths:
                paths.append(normalized)
    return tuple(paths)
