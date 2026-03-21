import json
from typing import Any, Optional

from openai import AsyncOpenAI
from loguru import logger

from bot.core.base_tool import BaseTool


class OpenAITool(BaseTool):
    """Tool for OpenAI-compatible API operations."""

    name = "openai"
    description = "OpenAI-compatible API operations with function calling"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client: Optional[AsyncOpenAI] = None

    def initialize(self) -> None:
        """Initialize the OpenAI client."""
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        self._initialized = True
        logger.info(f"OpenAI Tool initialized with model: {self.model}")

    async def execute(self, action: str, **kwargs) -> Any:
        """Execute an OpenAI action."""
        if not self._initialized:
            raise RuntimeError("Tool not initialized. Call initialize() first.")

        self._log_action(action, **kwargs)

        actions = {
            "chat": self._chat,
            "chat_with_tools": self._chat_with_tools,
        }

        if action not in actions:
            raise ValueError(f"Unknown action: {action}")

        return await actions[action](**kwargs)

    async def _chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Simple chat completion."""
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        return response.choices[0].message.content

    async def _chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system_prompt: Optional[str] = None,
    ) -> dict:
        """Chat completion with function calling."""
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        message = response.choices[0].message

        result = {
            "content": message.content,
            "tool_calls": [],
        }

        if message.tool_calls:
            for tool_call in message.tool_calls:
                result["tool_calls"].append({
                    "id": tool_call.id,
                    "name": tool_call.function.name,
                    "arguments": json.loads(tool_call.function.arguments),
                })

        return result
