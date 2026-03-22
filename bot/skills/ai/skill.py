import json
from datetime import datetime
from typing import Any, Optional

from loguru import logger

from bot.core.base_skill import BaseSkill
from bot.core.permissions import Permission, PermissionLevel, PermissionManager
from bot.skills.ai.tools import OpenAITool
from bot.skills.calendar import CalendarSkill


SYSTEM_PROMPT = """你是一個智能助手，可以幫助用戶管理行事曆和回答問題。

當用戶詢問行事曆相關問題時，請使用提供的工具來操作。
- 查看行程：使用 calendar_list_events
- 新增行程：使用 calendar_create_event
- 刪除行程：使用 calendar_delete_event

**重要：新增行程時必須確認以下資訊都已提供：**
1. 標題 (summary) - 必填
2. 時間 (start_time) - 必填
3. 地點 (location) - 必填
4. 參與人員 (attendees) - 必填，人員名稱或 email 皆可

如果用戶要新增行程但缺少上述任何必填資訊，請先詢問用戶補充缺少的資訊，不要直接呼叫 calendar_create_event。
只有當所有必填資訊都齊全時，才能呼叫 calendar_create_event 建立行程。

回應時請使用繁體中文，保持簡潔友善。
當前時間：{current_time}
"""

CALENDAR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": "列出即將到來的行程",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "最多返回幾筆行程",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": "建立新的行事曆行程。必須提供標題、時間、地點和參與人員才能建立。",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "行程標題（必填）",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "開始時間，ISO 8601 格式，例如 2026-03-21T14:00:00（必填）",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "結束時間，ISO 8601 格式，如果不提供則預設為開始時間後一小時",
                    },
                    "description": {
                        "type": "string",
                        "description": "行程描述",
                    },
                    "location": {
                        "type": "string",
                        "description": "行程地點（必填）",
                    },
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "參與人員列表，可以是名稱或 email（必填）",
                    },
                },
                "required": ["summary", "start_time", "location", "attendees"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_delete_event",
            "description": "刪除行事曆行程",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "要刪除的行程 ID",
                    },
                },
                "required": ["event_id"],
            },
        },
    },
]


class AISkill(BaseSkill):
    """Skill for AI-powered conversations with function calling."""

    name = "ai"
    description = "AI 對話與技能調用"
    keywords = []  # AI skill handles all messages when enabled
    required_permissions = [
        Permission(
            skill="ai",
            action="chat",
            description="AI 對話",
            min_level=PermissionLevel.USER,
            default_allowed=True,
        ),
        Permission(
            skill="ai",
            action="function_call",
            description="AI 調用技能",
            min_level=PermissionLevel.USER,
            default_allowed=True,
        ),
    ]

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        calendar_skill: Optional[CalendarSkill] = None,
        permission_manager: Optional[PermissionManager] = None,
    ):
        super().__init__(permission_manager)
        self.openai_tool = OpenAITool(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self.register_tool(self.openai_tool)
        self.calendar_skill = calendar_skill
        self.conversation_history: dict[int, list[dict]] = {}

    def initialize(self):
        """Initialize the AI skill."""
        self.openai_tool.initialize()
        logger.info("AISkill initialized")

    def set_calendar_skill(self, calendar_skill: CalendarSkill):
        """Set the calendar skill for function calling."""
        self.calendar_skill = calendar_skill

    async def handle(self, user_id: int, text: str, **context) -> str:
        """Handle AI conversation with function calling."""
        if not await self.check_permission(user_id, "chat"):
            return "❌ 你沒有權限使用 AI 對話"

        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []

        self.conversation_history[user_id].append({
            "role": "user",
            "content": text,
        })

        if len(self.conversation_history[user_id]) > 20:
            self.conversation_history[user_id] = self.conversation_history[user_id][-20:]

        system_prompt = SYSTEM_PROMPT.format(
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        tools = []
        if self.calendar_skill:
            tools.extend(CALENDAR_TOOLS)

        try:
            if tools:
                result = await self.openai_tool.execute(
                    "chat_with_tools",
                    messages=self.conversation_history[user_id],
                    tools=tools,
                    system_prompt=system_prompt,
                )

                if result["tool_calls"]:
                    chat_id = context.get("chat_id", user_id)
                    tool_results = await self._execute_tool_calls(user_id, result["tool_calls"], chat_id=chat_id)

                    self.conversation_history[user_id].append({
                        "role": "assistant",
                        "content": result["content"],
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc["arguments"]),
                                },
                            }
                            for tc in result["tool_calls"]
                        ],
                    })

                    for tool_result in tool_results:
                        self.conversation_history[user_id].append({
                            "role": "tool",
                            "tool_call_id": tool_result["id"],
                            "content": tool_result["result"],
                        })

                    final_result = await self.openai_tool.execute(
                        "chat_with_tools",
                        messages=self.conversation_history[user_id],
                        tools=tools,
                        system_prompt=system_prompt,
                    )

                    response = final_result["content"] or "操作完成"
                else:
                    response = result["content"] or "我不太理解你的意思"
            else:
                response = await self.openai_tool.execute(
                    "chat",
                    messages=self.conversation_history[user_id],
                    system_prompt=system_prompt,
                )

            self.conversation_history[user_id].append({
                "role": "assistant",
                "content": response,
            })

            return response

        except Exception as e:
            logger.error(f"AI chat error: {e}")
            return f"❌ AI 處理錯誤：{e}"

    async def _execute_tool_calls(self, user_id: int, tool_calls: list[dict], chat_id: int = None) -> list[dict]:
        """Execute function calls and return results."""
        results = []
        if chat_id is None:
            chat_id = user_id

        calendar_id = self.calendar_skill.get_calendar_id_for_chat(chat_id) if self.calendar_skill else "primary"

        for tc in tool_calls:
            name = tc["name"]
            args = tc["arguments"]
            tool_id = tc["id"]

            logger.info(f"Executing tool: {name} with args: {args}")

            try:
                if name == "calendar_list_events":
                    if not self.calendar_skill.check_group_permission(chat_id, "read"):
                        result = "❌ 此群組沒有權限查看行事曆"
                    elif not await self.check_permission(user_id, "function_call"):
                        result = "❌ 沒有權限執行此操作"
                    else:
                        result = await self.calendar_skill.get_upcoming_events(
                            max_results=args.get("max_results", 10),
                            calendar_id=calendar_id,
                        )

                elif name == "calendar_create_event":
                    if not self.calendar_skill.check_group_permission(chat_id, "write"):
                        result = "❌ 此群組沒有權限新增行程"
                    elif not await self.check_permission(user_id, "function_call"):
                        result = "❌ 沒有權限執行此操作"
                    else:
                        start_time = datetime.fromisoformat(args["start_time"])
                        end_time = None
                        if args.get("end_time"):
                            end_time = datetime.fromisoformat(args["end_time"])

                        result = await self.calendar_skill.create_event(
                            summary=args["summary"],
                            start_time=start_time,
                            end_time=end_time,
                            description=args.get("description", ""),
                            location=args.get("location", ""),
                            attendees=args.get("attendees", []),
                            calendar_id=calendar_id,
                        )

                elif name == "calendar_delete_event":
                    if not self.calendar_skill.check_group_permission(chat_id, "delete"):
                        result = "❌ 此群組沒有權限刪除行程"
                    elif not await self.calendar_skill.check_permission(user_id, "delete"):
                        result = "❌ 沒有權限刪除行程（需要管理員權限）"
                    else:
                        result = await self.calendar_skill.delete_event(args["event_id"])

                else:
                    result = f"未知的工具：{name}"

            except Exception as e:
                logger.error(f"Tool execution error: {e}")
                result = f"執行錯誤：{e}"

            results.append({"id": tool_id, "result": result})

        return results

    def clear_history(self, user_id: int):
        """Clear conversation history for a user."""
        if user_id in self.conversation_history:
            del self.conversation_history[user_id]

    async def get_help(self) -> str:
        """Return help text for AI skill."""
        return """🤖 **AI 助手**

直接 @我 並說出你的需求，我可以：

**行事曆操作：**
• 查看行程：「幫我看看今天有什麼行程」
• 新增行程：「新增一個明天下午3點的會議」
• 刪除行程：「取消那個會議」（需要管理員權限）

**一般對話：**
• 直接問我任何問題
"""
