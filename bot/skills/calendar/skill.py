from datetime import datetime, timedelta
from typing import Optional

from loguru import logger

from bot.core.base_skill import BaseSkill
from bot.core.permissions import Permission, PermissionLevel, PermissionManager
from bot.skills.calendar.attendee_store import AttendeeStore
from bot.skills.calendar.group_calendar_store import GroupCalendarStore
from bot.skills.calendar.tools import GoogleCalendarTool
from bot.types import GroupCalendarAccess


class CalendarSkill(BaseSkill):
    """Skill for managing Google Calendar."""

    name = "calendar"
    description = "Google Calendar 行事曆管理"
    keywords = [
        "行事曆",
        "日曆",
        "calendar",
        "行程",
        "schedule",
        "會議",
        "meeting",
        "活動",
        "event",
        "提醒",
        "remind",
    ]
    required_permissions = [
        Permission(
            skill="calendar",
            action="read",
            description="讀取行事曆",
            min_level=PermissionLevel.USER,
            default_allowed=True,
        ),
        Permission(
            skill="calendar",
            action="write",
            description="新增/修改行程",
            min_level=PermissionLevel.USER,
            default_allowed=True,
        ),
        Permission(
            skill="calendar",
            action="delete",
            description="刪除行程",
            min_level=PermissionLevel.ADMIN,
            default_allowed=False,
        ),
    ]

    def __init__(
        self,
        credentials_path: str,
        timezone: str = "Asia/Taipei",
        default_calendar_id: str = "primary",
        group_access: Optional[list[GroupCalendarAccess]] = None,
        permission_manager: Optional[PermissionManager] = None,
    ):
        super().__init__(permission_manager)
        self.timezone = timezone
        self.default_calendar_id = default_calendar_id
        self.group_access: dict[int, GroupCalendarAccess] = {}
        if group_access:
            for access in group_access:
                self.group_access[access.group_id] = access
        self.calendar_tool = GoogleCalendarTool(credentials_path)
        self.attendee_store = AttendeeStore()
        self.group_calendar_store = GroupCalendarStore()
        self.register_tool(self.calendar_tool)

    def initialize(self):
        """Initialize the calendar skill."""
        self.calendar_tool.initialize()
        logger.info(f"CalendarSkill initialized with timezone: {self.timezone}")

    def get_group_access(self, chat_id: int) -> Optional[GroupCalendarAccess]:
        """Get group-specific calendar access settings."""
        return self.group_access.get(chat_id)

    def get_calendar_id_for_chat(self, chat_id: int) -> str:
        """Get the calendar ID for a specific chat.

        Priority: group_access (static config) → group_calendar_store (dynamic) → default.
        """
        access = self.get_group_access(chat_id)
        if access:
            return access.calendar_id
        stored = self.group_calendar_store.get_calendar_id(chat_id)
        if stored:
            return stored
        return self.default_calendar_id

    def check_group_permission(self, chat_id: int, action: str) -> bool:
        """Check if a group has permission for an action."""
        access = self.get_group_access(chat_id)
        if not access:
            # Groups with a dynamically provisioned calendar also get full access
            if self.group_calendar_store.has_group(chat_id):
                return True
            return True

        if action == "read":
            return access.permissions.can_read
        elif action == "write":
            return access.permissions.can_write
        elif action == "delete":
            return access.permissions.can_delete
        return False

    async def ensure_group_calendar(self, group_id: int, group_title: str) -> str:
        """Ensure a secondary Google Calendar exists for *group_id*.

        - If already registered in the store, return that calendar_id.
        - Otherwise create a new secondary calendar via the API, persist the
          mapping, and return the new calendar_id.
        """
        # 1. Already stored?
        existing = self.group_calendar_store.get_calendar_id(group_id)
        if existing:
            logger.info(f"ensure_group_calendar: group {group_id} already has calendar {existing}")
            return existing

        # 2. Create a new secondary calendar
        calendar_name = f"{group_title} ({group_id})"
        try:
            cal = await self.calendar_tool.execute(
                "create_calendar",
                summary=calendar_name,
                timezone=self.timezone,
            )
            new_id: str = cal["id"]
        except Exception as e:
            logger.error(f"ensure_group_calendar: failed to create calendar for group {group_id}: {e}")
            raise

        # 3. Persist
        self.group_calendar_store.register(group_id, new_id, title=group_title)
        logger.info(f"ensure_group_calendar: created & stored calendar {new_id} for group {group_id} ({group_title})")
        return new_id

    async def handle(self, user_id: int, text: str, **context) -> str:
        """Handle calendar-related requests."""
        chat_id = context.get("chat_id", user_id)
        calendar_id = self.get_calendar_id_for_chat(chat_id)
        text_lower = text.lower()

        if any(
            kw in text_lower
            for kw in [
                "查看",
                "列出",
                "顯示",
                "list",
                "show",
                "upcoming",
                "今天",
                "today",
            ]
        ):
            if not self.check_group_permission(chat_id, "read"):
                return "❌ 此群組沒有權限查看行事曆"
            if not await self.check_permission(user_id, "read"):
                return "❌ 你沒有權限查看行事曆"
            return await self.get_upcoming_events(calendar_id=calendar_id)

        elif any(kw in text_lower for kw in ["新增", "建立", "創建", "add", "create"]):
            if not self.check_group_permission(chat_id, "write"):
                return "❌ 此群組沒有權限新增行程"
            if not await self.check_permission(user_id, "write"):
                return "❌ 你沒有權限新增行程"
            return await self._handle_create_event(text)

        elif any(
            kw in text_lower for kw in ["刪除", "取消", "delete", "cancel", "remove"]
        ):
            if not self.check_group_permission(chat_id, "delete"):
                return "❌ 此群組沒有權限刪除行程"
            if not await self.check_permission(user_id, "delete"):
                return "❌ 你沒有權限刪除行程（需要管理員權限）"
            return await self._handle_delete_event(text)

        else:
            return await self.get_upcoming_events(calendar_id=calendar_id)

    async def get_upcoming_events(
        self, days: int = 7, max_results: int = 10, calendar_id: str = None
    ) -> str:
        """Get upcoming events formatted as text."""
        if calendar_id is None:
            calendar_id = self.default_calendar_id
        try:
            events = await self.calendar_tool.execute(
                "list_events",
                max_results=max_results,
                calendar_id=calendar_id,
            )
            return self._format_events(events)
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            return f"❌ 無法取得行事曆資料：{e}"

    async def create_event(
        self,
        summary: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        description: str = "",
        location: str = "",
        attendees: Optional[list[dict]] = None,
        calendar_id: str = None,
    ) -> str:
        """Create a new calendar event.

        attendees: list of {user_id: int, full_name: str} dicts (Telegram users).
        """
        if end_time is None:
            end_time = start_time + timedelta(hours=1)
        if calendar_id is None:
            calendar_id = self.default_calendar_id

        event_body = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": self.timezone,
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": self.timezone,
            },
        }

        try:
            result = await self.calendar_tool.execute(
                "insert_event",
                event_body=event_body,
                calendar_id=calendar_id,
            )

            event_id = result.get("id", "")

            # Persist Telegram attendee info locally
            if attendees and event_id:
                self.attendee_store.save(event_id, attendees)

            # Build plain-text confirmation (no HTML – will be sent as regular markdown)
            attendee_str = ""
            if attendees:
                names = "、".join(a.get("full_name", "未知") for a in attendees)
                attendee_str = f"\n👥 參與者：{names}"

            return (
                f"✅ 已建立行程：**{result.get('summary')}**\n"
                f"📍 地點：{location}"
                f"{attendee_str}\n"
                f"🔗 {result.get('htmlLink', '')}"
            )
        except Exception as e:
            logger.error(f"Failed to create event: {e}")
            return f"❌ 無法建立行程：{e}"

    async def delete_event(self, event_id: str, calendar_id: str = None) -> str:
        """Delete a calendar event."""
        if calendar_id is None:
            calendar_id = self.default_calendar_id
        try:
            success = await self.calendar_tool.execute(
                "delete_event",
                event_id=event_id,
                calendar_id=calendar_id,
            )
            if success:
                self.attendee_store.delete(event_id)
                return f"✅ 已刪除行程"
            return "❌ 刪除行程失敗"
        except Exception as e:
            logger.error(f"Failed to delete event: {e}")
            return f"❌ 無法刪除行程：{e}"

    async def _handle_create_event(self, text: str) -> str:
        """Parse text and create event."""
        return (
            "📅 要新增行程，請使用以下格式：\n\n"
            "`/calendar add [標題] [開始時間] [結束時間]`\n\n"
            "例如：`/calendar add 開會 2024-01-15T14:00 2024-01-15T15:00`"
        )

    async def _handle_delete_event(self, text: str) -> str:
        """Parse text and delete event."""
        return "📅 要刪除行程，請使用以下格式：\n\n`/calendar delete [event_id]`"

    def _format_events(self, events: list[dict]) -> str:
        """Format events list to readable text."""
        if not events:
            return "📅 沒有即將到來的行程"

        lines = ["📅 **即將到來的行程：**\n"]
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            if "T" in start:
                dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
                start_str = dt.strftime("%m/%d %H:%M")
            else:
                start_str = start

            summary = event.get("summary", "（無標題）")
            event_id = event.get("id", "")
            lines.append(f"• **{start_str}** - {summary} [ID: `{event_id}`]")

        return "\n".join(lines)

    async def get_help(self) -> str:
        """Return help text for calendar skill."""
        return """📅 **行事曆技能**

**查看行程：**
• `@bot 查看行事曆`
• `@bot 今天有什麼行程`
• `@bot 顯示會議`

**新增行程：**
• `/calendar add [標題] [開始時間] [結束時間]`

**刪除行程：** (需要管理員權限)
• `/calendar delete [event_id]`
"""
