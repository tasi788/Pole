from abc import ABC, abstractmethod
from typing import Any, Optional
from pathlib import Path
from loguru import logger

from bot.core.base_tool import BaseTool
from bot.core.permissions import Permission, PermissionManager


class BaseSkill(ABC):
    """Base class for all skills in the skill chain."""

    name: str = "base_skill"
    description: str = "Base skill description"
    keywords: list[str] = []
    required_permissions: list[Permission] = []

    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        self.tools: dict[str, BaseTool] = {}
        self.permission_manager = permission_manager
        self._load_skill_doc()

    def _load_skill_doc(self):
        """Load SKILL.md documentation if exists."""
        skill_dir = Path(__file__).parent.parent / "skills" / self.name
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists():
            self.skill_doc = skill_md.read_text(encoding="utf-8")
            logger.debug(f"Loaded SKILL.md for {self.name}")
        else:
            self.skill_doc = None

    def register_tool(self, tool: BaseTool):
        """Register a tool for this skill to use."""
        self.tools[tool.name] = tool
        logger.debug(f"[{self.name}] Registered tool: {tool.name}")

    def has_keyword(self, text: str) -> bool:
        """Check if text contains any of the skill's keywords."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.keywords)

    async def check_permission(self, user_id: int, action: str) -> bool:
        """Check if user has permission to perform action."""
        if self.permission_manager is None:
            return True

        for perm in self.required_permissions:
            if perm.action == action:
                return await self.permission_manager.check(user_id, perm)

        return True

    @abstractmethod
    async def handle(self, user_id: int, text: str, **context) -> str:
        """Handle a user request and return response."""
        pass

    @abstractmethod
    async def get_help(self) -> str:
        """Return help text for this skill."""
        pass
