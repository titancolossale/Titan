# =====================================
# Titan Demo Fake Search Tool
# =====================================

"""Demo search tool discovered automatically by ToolLoader."""

from __future__ import annotations

from core.actions.action import Action
from core.actions.action_result import ActionResult
from core.tools.base_tool import BaseTool


class FakeSearchTool(BaseTool):
    """Placeholder search tool for automatic discovery validation."""

    def __init__(self) -> None:
        super().__init__()
        self._actions = (
            Action(
                id="query",
                name="Query",
                description="Simulate a web search query.",
                tool_id=self.id,
                permission_id="fake_search.query",
                parameters={
                    "query": {"type": "string", "required": False},
                },
            ),
        )

    @property
    def id(self) -> str:
        return "fake_search"

    @property
    def name(self) -> str:
        return "Fake Search"

    @property
    def description(self) -> str:
        return "Simulates a web search for tool-loader discovery demos."

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def category(self) -> str:
        return "web"

    @property
    def requires_confirmation(self) -> bool:
        return False

    @property
    def capabilities(self) -> list[str]:
        return ["search.query"]

    def list_actions(self) -> list[Action]:
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        if action_id != "query":
            return ActionResult(
                success=False,
                message=f"Unsupported action: {action_id}",
                errors=[f"Unsupported action: {action_id}"],
            )
        query = kwargs.get("query", "")
        return ActionResult(success=True, data={"query": query, "results": []})

    def execute(self, **kwargs: object) -> object:
        result = self.execute_action("query", **kwargs)
        return result.data if result.success else {"error": result.message}
