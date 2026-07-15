# =====================================
# Titan Demo Fake Calculator Tool
# =====================================

"""Demo calculator tool discovered automatically by ToolLoader."""

from __future__ import annotations

from core.actions.action import Action
from core.actions.action_result import ActionResult
from core.tools.base_tool import BaseTool


class FakeCalculatorTool(BaseTool):
    """Placeholder calculator tool for automatic discovery validation."""

    def __init__(self) -> None:
        super().__init__()
        self._actions = (
            Action(
                id="add",
                name="Add",
                description="Add two numbers.",
                tool_id=self.id,
                permission_id="fake_calculator.add",
                parameters={
                    "left": {"type": "number", "required": False},
                    "right": {"type": "number", "required": False},
                },
            ),
            Action(
                id="subtract",
                name="Subtract",
                description="Subtract two numbers.",
                tool_id=self.id,
                permission_id="fake_calculator.subtract",
                parameters={
                    "left": {"type": "number", "required": False},
                    "right": {"type": "number", "required": False},
                },
            ),
        )

    @property
    def id(self) -> str:
        return "fake_calculator"

    @property
    def name(self) -> str:
        return "Fake Calculator"

    @property
    def description(self) -> str:
        return "Performs basic arithmetic for tool-loader discovery demos."

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def category(self) -> str:
        return "utility"

    @property
    def requires_confirmation(self) -> bool:
        return False

    @property
    def capabilities(self) -> list[str]:
        return ["math.add", "math.subtract"]

    def list_actions(self) -> list[Action]:
        return list(self._actions)

    def execute_action(self, action_id: str, **kwargs: object) -> ActionResult:
        left = float(kwargs.get("left", 0))
        right = float(kwargs.get("right", 0))
        if action_id == "subtract":
            return ActionResult(success=True, data={"result": left - right})
        if action_id == "add":
            return ActionResult(success=True, data={"result": left + right})
        return ActionResult(
            success=False,
            message=f"Unsupported action: {action_id}",
            errors=[f"Unsupported action: {action_id}"],
        )

    def execute(self, **kwargs: object) -> object:
        operation = kwargs.get("operation", "add")
        result = self.execute_action(str(operation), **kwargs)
        return result.data if result.success else {"error": result.message}
