# =====================================
# Titan Tool Decision — Workspace Modification Planner
# =====================================

"""Inspect workspace and plan safe code modifications — read-only (Phase 11 — P11-301)."""

from __future__ import annotations

import re
from pathlib import Path

from context.workspace_map import extension_point_files, files_for_area, get_area
from tools.decision.modification_models import (
    FileChangeSpec,
    ModificationPlan,
    PatchPreview,
    estimate_modification_risk,
)
from tools.decision.modification_param_parser import ModificationParams, parse_modification_params
from tools.decision.patch_preview import (
    append_registration_snippet,
    generate_create_file_preview,
    generate_unified_diff,
    propose_capability_tool_file,
    propose_provider_file,
    propose_test_file,
    read_file_safe,
)
from tools.tool_enums import RiskLevel


class WorkspaceModificationPlanner:
    """Analyze coding requests and produce modification plans without writing."""

    def __init__(self, *, project_root: Path) -> None:
        self._project_root = project_root.resolve()

    def plan(self, message: str, *, confidence: float = 0.85) -> ModificationPlan:
        """Build a modification plan for a natural-language coding request."""
        params = parse_modification_params(message)
        if params.ambiguous:
            return ModificationPlan(
                objective=message.strip(),
                modification_type=params.modification_type,
                files_to_modify=(),
                files_to_create=(),
                files_to_delete=(),
                dependency_graph={},
                implementation_steps=(
                    "Clarifier la demande avec l'utilisateur.",
                ),
                estimated_risk=estimate_modification_risk(
                    files_to_modify=(),
                    files_to_create=(),
                    modification_type=params.modification_type,
                ),
                confidence=min(confidence, 0.45),
                ambiguous=True,
                ambiguity_reason=params.ambiguity_reason,
            )

        builders = {
            "add_capability": self._plan_add_capability,
            "add_provider": self._plan_add_provider,
            "add_memory": self._plan_add_memory,
            "fix_bug": self._plan_fix_bug,
            "add_command": self._plan_add_command,
        }
        builder = builders.get(params.modification_type, self._plan_fix_bug)
        plan = builder(message, params, confidence=confidence)
        previews = self._generate_patch_previews(plan)
        dependency_graph = self._build_dependency_graph(plan)
        risk = estimate_modification_risk(
            files_to_modify=plan.files_to_modify,
            files_to_create=plan.files_to_create,
            modification_type=plan.modification_type,
        )
        return ModificationPlan(
            objective=plan.objective,
            modification_type=plan.modification_type,
            files_to_modify=plan.files_to_modify,
            files_to_create=plan.files_to_create,
            files_to_delete=plan.files_to_delete,
            dependency_graph=dependency_graph,
            implementation_steps=plan.implementation_steps,
            estimated_risk=risk,
            confidence=plan.confidence,
            patch_previews=previews,
            side_effects=plan.side_effects,
            ambiguous=plan.ambiguous,
            ambiguity_reason=plan.ambiguity_reason,
        )

    def _plan_add_capability(
        self,
        message: str,
        params: ModificationParams,
        *,
        confidence: float,
    ) -> ModificationPlan:
        entity = params.entity_name or "example"
        tool_path = f"tools/{entity}_tool.py"
        manager_path = "tools/tool_manager.py"
        test_path = f"tests/test_{entity}_tool.py"
        class_name = "".join(part.capitalize() for part in entity.split("_")) + "Tool"

        files_create = (
            FileChangeSpec(
                path=tool_path,
                reason="Nouvelle capacité outil suivant le pattern BaseTool.",
                change_summary=f"Créer {class_name} avec schema et run().",
            ),
            FileChangeSpec(
                path=test_path,
                reason="Couverture pytest requise pour les nouveaux modules.",
                change_summary=f"Test smoke d'import pour {entity}.",
            ),
        )
        files_modify = (
            FileChangeSpec(
                path=manager_path,
                reason="Enregistrer l'outil dans le composition root des outils.",
                change_summary=f"Importer {class_name} et l'ajouter à _register_defaults().",
            ),
        )
        steps = (
            f"Créer {tool_path} en étendant BaseTool.",
            f"Enregistrer {class_name} dans {manager_path}._register_defaults().",
            f"Ajouter {test_path} avec un test d'import.",
            "Vérifier que Tool Runtime V2 expose la capacité via refresh_catalog().",
            "Exécuter pytest sur le nouveau test avant application manuelle.",
        )
        side_effects = (
            "Nouvelle capacité visible dans ToolManager.list_tools().",
            "Peut nécessiter une entrée capability_catalog après refresh_catalog().",
        )
        return ModificationPlan(
            objective=f"Ajouter la capacité '{entity}' au runtime Titan.",
            modification_type="add_capability",
            files_to_modify=files_modify,
            files_to_create=files_create,
            files_to_delete=(),
            dependency_graph={},
            implementation_steps=steps,
            estimated_risk=estimate_modification_risk(
                files_to_modify=files_modify,
                files_to_create=files_create,
                modification_type="add_capability",
            ),
            confidence=confidence if params.entity_name else confidence * 0.75,
            side_effects=side_effects,
        )

    def _plan_add_provider(
        self,
        message: str,
        params: ModificationParams,
        *,
        confidence: float,
    ) -> ModificationPlan:
        entity = params.entity_name or "example"
        provider_path = f"tools/providers/{entity}_provider.py"
        defaults_path = "tools/providers/defaults.py"
        test_path = f"tests/test_{entity}_provider.py"
        class_name = "".join(part.capitalize() for part in entity.split("_")) + "Provider"

        files_create = (
            FileChangeSpec(
                path=provider_path,
                reason="Nouveau backend provider suivant BaseProvider.",
                change_summary=f"Créer {class_name} avec provider_id='{entity}'.",
            ),
            FileChangeSpec(
                path=test_path,
                reason="Tests requis pour les nouveaux providers.",
                change_summary=f"Test smoke pour {entity}_provider.",
            ),
        )
        files_modify = (
            FileChangeSpec(
                path=defaults_path,
                reason="Bootstrap du provider au démarrage via register_default_providers().",
                change_summary=f"Importer et enregistrer {class_name} dans defaults.",
            ),
        )
        steps = (
            f"Créer {provider_path} avec provider_id stable.",
            f"Ajouter {class_name} à {defaults_path}.",
            f"Couvrir avec {test_path}.",
            "Vérifier compatibilité runtime via ProviderRegistry.register().",
            "Documenter les credentials requis si provider externe.",
        )
        side_effects = (
            "Provider visible dans ProviderRegistry.list_ids().",
            "Peut impacter le ranking provider pour les capacités liées.",
        )
        return ModificationPlan(
            objective=f"Ajouter le provider '{entity}' au registry Titan.",
            modification_type="add_provider",
            files_to_modify=files_modify,
            files_to_create=files_create,
            files_to_delete=(),
            dependency_graph={},
            implementation_steps=steps,
            estimated_risk=estimate_modification_risk(
                files_to_modify=files_modify,
                files_to_create=files_create,
                modification_type="add_provider",
            ),
            confidence=confidence if params.entity_name else confidence * 0.75,
            side_effects=side_effects,
        )

    def _plan_add_memory(
        self,
        message: str,
        params: ModificationParams,
        *,
        confidence: float,
    ) -> ModificationPlan:
        entity = params.entity_name or "note_category"
        classifier_path = "memory/memory_classifier.py"
        retriever_path = "memory/memory_retriever.py"
        test_path = "tests/test_memory_classifier.py"
        area_files = files_for_area("memory", project_root=self._project_root)

        files_modify = (
            FileChangeSpec(
                path=classifier_path,
                reason="Assigner la nouvelle catégorie mémoire lors de l'écriture.",
                change_summary=f"Ajouter la catégorie '{entity}' au classificateur.",
            ),
            FileChangeSpec(
                path=retriever_path,
                reason="Permettre la récupération ciblée de la nouvelle catégorie.",
                change_summary=f"Inclure '{entity}' dans les filtres de retrieval pertinents.",
            ),
            FileChangeSpec(
                path=test_path,
                reason="Régression sur la classification mémoire.",
                change_summary=f"Test de classification pour '{entity}'.",
            ),
        )
        steps = (
            f"Définir la catégorie '{entity}' dans {classifier_path}.",
            f"Adapter {retriever_path} pour filtrer/récupérer la catégorie.",
            "Mettre à jour les tests memory_classifier / memory_retriever.",
            "Vérifier l'isolation utilisateur Nolan/Ibrahim inchangée.",
            "Ne pas écrire directement dans long_term_memory.json sans decider.",
        )
        side_effects = (
            "Nouvelles notes classées sous une catégorie additionnelle.",
            "Prompt MÉMOIRE PERMANENTE peut inclure la nouvelle catégorie si retrieval adapté.",
        )
        return ModificationPlan(
            objective=f"Ajouter une extension mémoire '{entity}' au pipeline Titan.",
            modification_type="add_memory",
            files_to_modify=files_modify,
            files_to_create=(),
            files_to_delete=(),
            dependency_graph={},
            implementation_steps=steps,
            estimated_risk=estimate_modification_risk(
                files_to_modify=files_modify,
                files_to_create=(),
                modification_type="add_memory",
            ),
            confidence=confidence,
            side_effects=side_effects,
        )

    def _plan_fix_bug(
        self,
        message: str,
        params: ModificationParams,
        *,
        confidence: float,
    ) -> ModificationPlan:
        target = params.target_path
        area = params.target_area
        if target is None and area is not None:
            candidates = files_for_area(area, project_root=self._project_root)
            target = candidates[0] if candidates else None

        if target is None:
            return ModificationPlan(
                objective=message.strip(),
                modification_type="fix_bug",
                files_to_modify=(),
                files_to_create=(),
                files_to_delete=(),
                dependency_graph={},
                implementation_steps=("Identifier le fichier ou la zone concernée.",),
                estimated_risk=RiskLevel.LOW,
                confidence=0.4,
                ambiguous=True,
                ambiguity_reason=(
                    "Correction de bug ambiguë — précise le fichier, la zone "
                    "(Brain, mémoire, tools…) ou le message d'erreur."
                ),
            )

        files_modify = (
            FileChangeSpec(
                path=target,
                reason="Fichier cible identifié pour la correction.",
                change_summary=params.topic or "Appliquer le correctif minimal nécessaire.",
            ),
        )
        related = self._related_test_path(target)
        if related and (self._project_root / related).is_file():
            files_modify = files_modify + (
                FileChangeSpec(
                    path=related,
                    reason="Test de régression associé au module modifié.",
                    change_summary="Ajouter ou ajuster un test reproduisant le bug.",
                ),
            )

        steps = (
            f"Reproduire le bug dans {target}.",
            "Appliquer le correctif minimal sans refactor opportuniste.",
            f"Exécuter pytest ciblant {related or 'tests/'} si disponible.",
            "Vérifier python main.py démarre sans régression.",
        )
        return ModificationPlan(
            objective=f"Corriger le bug dans {target}.",
            modification_type="fix_bug",
            files_to_modify=files_modify,
            files_to_create=(),
            files_to_delete=(),
            dependency_graph={},
            implementation_steps=steps,
            estimated_risk=estimate_modification_risk(
                files_to_modify=files_modify,
                files_to_create=(),
                modification_type="fix_bug",
            ),
            confidence=confidence if params.target_path else confidence * 0.7,
            side_effects=("Comportement runtime du module modifié peut changer.",),
        )

    def _plan_add_command(
        self,
        message: str,
        params: ModificationParams,
        *,
        confidence: float,
    ) -> ModificationPlan:
        entity = params.entity_name or "help"
        titan_path = "core/titan.py"
        test_path = "tests/test_titan_repl.py"

        files_modify = (
            FileChangeSpec(
                path=titan_path,
                reason="Boucle REPL — point d'entrée des commandes utilisateur.",
                change_summary=f"Ajouter la commande '{entity}' dans Titan.start().",
            ),
        )
        if (self._project_root / test_path).is_file():
            files_modify = files_modify + (
                FileChangeSpec(
                    path=test_path,
                    reason="Régression REPL/commandes.",
                    change_summary=f"Test de la commande '{entity}'.",
                ),
            )

        steps = (
            f"Définir le handler de commande '{entity}' dans {titan_path}.",
            "Conserver les commandes exit/quit/stop/bye intactes.",
            "Documenter la commande dans Titan_Context ou README si user-facing.",
            "Ajouter test REPL si applicable.",
        )
        side_effects = (
            "Nouvelle commande disponible dans la session CLI.",
            "Touche le composition root — revue manuelle recommandée.",
        )
        return ModificationPlan(
            objective=f"Ajouter la commande REPL '{entity}'.",
            modification_type="add_command",
            files_to_modify=files_modify,
            files_to_create=(),
            files_to_delete=(),
            dependency_graph={},
            implementation_steps=steps,
            estimated_risk=estimate_modification_risk(
                files_to_modify=files_modify,
                files_to_create=(),
                modification_type="add_command",
            ),
            confidence=confidence if params.entity_name else confidence * 0.7,
            side_effects=side_effects,
        )

    def _generate_patch_previews(self, plan: ModificationPlan) -> tuple[PatchPreview, ...]:
        """Generate unified diff previews for planned changes (read-only)."""
        previews: list[PatchPreview] = []

        for item in plan.files_to_create:
            content = self._proposed_new_file_content(plan.modification_type, item.path)
            previews.append(generate_create_file_preview(item.path, content))

        entity = _entity_from_plan(plan)
        for item in plan.files_to_modify:
            original = read_file_safe(self._project_root, item.path)
            proposed = self._proposed_modified_content(
                plan.modification_type,
                item.path,
                original,
                entity=entity,
            )
            previews.append(
                generate_unified_diff(
                    item.path,
                    original=original,
                    proposed=proposed,
                    change_type="modify" if original else "create",
                ),
            )
        return tuple(previews)

    def _proposed_new_file_content(self, modification_type: str, path: str) -> str:
        stem = Path(path).stem.replace("_tool", "").replace("_provider", "")
        if path.endswith("_tool.py"):
            return propose_capability_tool_file(stem)
        if path.endswith("_provider.py"):
            return propose_provider_file(stem)
        if path.startswith("tests/test_"):
            module = path.replace("tests/test_", "").replace(".py", "")
            source = f"tools/{module}.py"
            if not (self._project_root / source).is_file():
                source = f"tools/providers/{module}.py"
            return propose_test_file(source, stem)
        return f"# Proposed new file: {path}\n"

    def _proposed_modified_content(
        self,
        modification_type: str,
        path: str,
        original: str,
        *,
        entity: str,
    ) -> str:
        if not original:
            return f"# Proposed changes for missing file: {path}\n"

        if modification_type == "add_capability" and path == "tools/tool_manager.py":
            class_name = "".join(part.capitalize() for part in entity.split("_")) + "Tool"
            return append_registration_snippet(
                original,
                import_line=f"from tools.{entity}_tool import {class_name}",
                register_line=f"            {class_name}(),",
                anchor="for tool in defaults:",
            )

        if modification_type == "add_provider" and path == "tools/providers/defaults.py":
            class_name = "".join(part.capitalize() for part in entity.split("_")) + "Provider"
            return append_registration_snippet(
                original,
                import_line=f"from tools.providers.{entity}_provider import {class_name}",
                register_line=f"        {class_name}(",
                anchor="defaults = (",
            )

        if modification_type == "add_memory" and path == "memory/memory_classifier.py":
            return original + "\n# TODO(titan): register proposed memory category in classifier rules\n"

        if modification_type == "add_command" and path == "core/titan.py":
            marker = f"# TODO(titan): handle repl command '{entity}'\n"
            if marker in original:
                return original
            return original + f"\n{marker}"

        if modification_type == "fix_bug":
            marker = "# TODO(titan): proposed minimal bug fix\n"
            if marker in original:
                return original
            return original + marker

        return original + f"\n# Proposed modification for {path}\n"

    def _build_dependency_graph(self, plan: ModificationPlan) -> dict[str, tuple[str, ...]]:
        """Map each affected file to related dependencies via lightweight import scan."""
        graph: dict[str, tuple[str, ...]] = {}
        all_paths = [item.path for item in plan.files_to_modify] + [
            item.path for item in plan.files_to_create
        ]
        for rel_path in all_paths:
            deps = self._scan_import_dependencies(rel_path)
            graph[rel_path] = deps
        extension_refs = extension_point_files("tools")
        for rel_path in all_paths:
            if rel_path in extension_refs:
                existing = graph.get(rel_path, ())
                graph[rel_path] = tuple(dict.fromkeys(existing + ("tools/tool_manager.py",)))
        return graph

    def _scan_import_dependencies(self, rel_path: str) -> tuple[str, ...]:
        content = read_file_safe(self._project_root, rel_path)
        if not content:
            return ()
        deps: list[str] = []
        for line in content.splitlines():
            match = re.match(r"^\s*from\s+([\w.]+)\s+import", line)
            if match:
                module = match.group(1).replace(".", "/") + ".py"
                if (self._project_root / module).is_file():
                    deps.append(module)
                continue
            match = re.match(r"^\s*import\s+([\w.]+)", line)
            if match:
                module = match.group(1).split(".")[0]
                candidate = f"{module}.py"
                if (self._project_root / candidate).is_file():
                    deps.append(candidate)
        return tuple(dict.fromkeys(deps))

    @staticmethod
    def _related_test_path(source_path: str) -> str | None:
        stem = Path(source_path).stem
        if source_path.startswith("tools/providers/"):
            return f"tests/test_{stem}.py"
        if source_path.startswith("tools/"):
            return f"tests/test_{stem}.py"
        if source_path.startswith("memory/"):
            return f"tests/test_{stem}.py"
        if source_path.startswith("core/"):
            return "tests/test_titan_repl.py"
        return None


def _entity_from_plan(plan: ModificationPlan) -> str:
    """Extract entity slug from planned create paths or fall back to defaults."""
    for item in plan.files_to_create:
        stem = Path(item.path).stem
        if stem.endswith("_tool"):
            return stem[: -len("_tool")]
        if stem.endswith("_provider"):
            return stem[: -len("_provider")]
    if plan.modification_type == "add_command":
        return "help"
    return "example"
