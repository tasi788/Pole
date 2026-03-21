from abc import ABC, abstractmethod
from typing import Any
from loguru import logger


class BaseTool(ABC):
    """Base class for all tools in the tool chain."""

    name: str = "base_tool"
    description: str = "Base tool description"

    def __init__(self):
        self._initialized = False

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the tool (e.g., authenticate, connect)."""
        pass

    @abstractmethod
    async def execute(self, action: str, **kwargs) -> Any:
        """Execute a tool action."""
        pass

    def is_initialized(self) -> bool:
        return self._initialized

    def _log_action(self, action: str, **kwargs):
        logger.debug(f"[{self.name}] Executing: {action} with {kwargs}")
