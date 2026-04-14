"""APScheduler-based calendar reminder system."""

from __future__ import annotations

import html as _html
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from pyrogram import enums

if TYPE_CHECKING:
    from pyrogram import Client

    from bot.skills.calendar.skill import CalendarSkill


class CalendarReminderScheduler:
    """Sends 1-hour-before event reminders and a daily 8 AM summary."""

    def __init__(
        self,
        client: "Client",
        calendar_skill: "CalendarSkill",
        owner_id: int,
        timezone: str = "Asia/Taipei",
        notify_owner: bool = True,
    ) -> None:
        self.client = client
        self.calendar_skill = calendar_skill
        self.owner_id = owner_id
        self.tz = ZoneInfo(timezone)
        self.notify_owner = notify_owner

        # Track reminded event IDs within the current day to avoid duplicates
        self._reminded_events: set[str] = set()

        self.scheduler = AsyncIOScheduler(timezone=self.tz)
        self._register_jobs()

    # ------------------------------------------------------------------ #
    # Setup                                                                #
    # ------------------------------------------------------------------ #

    def _register_jobs(self) -> None:
        # 1-hour reminder check every 5 minutes
        self.scheduler.add_job(
            self.check_upcoming_reminders,
            trigger=IntervalTrigger(minutes=5),
            id="event_reminder_check",
            name="1-hour event reminder check",
            replace_existing=True,
        )
        # Daily summary at 08:00
        self.scheduler.add_job(
            self.send_daily_summary,
            trigger=CronTrigger(hour=8, minute=0, timezone=self.tz),
            id="daily_summary",
            name="Daily calendar summary",
            replace_existing=True,
        )
        # Clear reminded cache at midnight
        self.scheduler.add_job(
            self._clear_reminded_cache,
            trigger=CronTrigger(hour=0, minute=1, timezone=self.tz),
            id="clear_reminded_cache",
            name="Clear reminded events cache",
            replace_existing=True,
        )

    def start(self) -> None:
        self.scheduler.start()
        logger.info("CalendarReminderScheduler started")

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("CalendarReminderScheduler stopped")

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _chat_calendar_pairs(self) -> list[tuple[int, str]]:
        """Return [(chat_id, calendar_id)] for all notification targets."""
        pairs: list[tuple[int, str]] = []
        if self.notify_owner and self.owner_id:
            pairs.append((self.owner_id, self.calendar_skill.default_calendar_id))
        for group_id, access in self.calendar_skill.group_access.items():
            pairs.append((group_id, access.calendar_id))
        return pairs

    @staticmethod
    def _mention_parts(attendees: list[dict]) -> list[str]:
        """Build HTML mention strings for attendees."""
        parts = []
        for a in attendees:
            uid = a.get("user_id")
            name = _html.escape(a.get("full_name", "未知"))
            parts.append(f'<a href="tg://user?id={uid}">{name}</a>' if uid else name)
        return parts

    # ------------------------------------------------------------------ #
    # Jobs                                                                 #
    # ------------------------------------------------------------------ #

    async def check_upcoming_reminders(self) -> None:
        """Send reminders for events starting in ~1 hour."""
        now = datetime.now(self.tz)
        window_start = now + timedelta(minutes=55)
        window_end = now + timedelta(minutes=65)

        for chat_id, calendar_id in self._chat_calendar_pairs():
            try:
                events = await self.calendar_skill.calendar_tool.execute(
                    "list_events",
                    calendar_id=calendar_id,
                    time_min=window_start,
                    time_max=window_end,
                    max_results=10,
                )
                for event in events:
                    event_id = event.get("id", "")
                    if event_id and event_id not in self._reminded_events:
                        self._reminded_events.add(event_id)
                        msg = self._fmt_reminder(event)
                        await self.client.send_message(
                            chat_id, msg, parse_mode=enums.ParseMode.HTML
                        )
                        logger.info(f"Reminder sent: event={event_id} chat={chat_id}")
            except Exception as exc:
                logger.error(f"Reminder check error for chat {chat_id}: {exc}")

    async def send_daily_summary(self) -> None:
        """Send today's event list at 8 AM."""
        now = datetime.now(self.tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

        for chat_id, calendar_id in self._chat_calendar_pairs():
            try:
                events = await self.calendar_skill.calendar_tool.execute(
                    "list_events",
                    calendar_id=calendar_id,
                    time_min=today_start,
                    time_max=today_end,
                    max_results=20,
                )
                msg = self._fmt_daily(events, now)
                await self.client.send_message(
                    chat_id, msg, parse_mode=enums.ParseMode.HTML
                )
                logger.info(f"Daily summary sent: chat={chat_id} events={len(events)}")
            except Exception as exc:
                logger.error(f"Daily summary error for chat {chat_id}: {exc}")

    async def _clear_reminded_cache(self) -> None:
        self._reminded_events.clear()
        logger.debug("Reminded events cache cleared")

    # ------------------------------------------------------------------ #
    # Formatters                                                           #
    # ------------------------------------------------------------------ #

    def _fmt_reminder(self, event: dict) -> str:
        """HTML reminder message for a single event (1 hour before)."""
        summary = _html.escape(event.get("summary", "（無標題）"))
        start_raw = event["start"].get("dateTime", event["start"].get("date", ""))
        location = event.get("location", "")

        if "T" in start_raw:
            dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            start_str = dt.astimezone(self.tz).strftime("%H:%M")
        else:
            start_str = "全天"

        lines = [
            "⏰ <b>行程提醒（1 小時後開始）</b>",
            "",
            f"📌 <b>{summary}</b>",
            f"🕐 開始時間：{start_str}",
        ]
        if location:
            lines.append(f"📍 地點：{_html.escape(location)}")

        event_id = event.get("id", "")
        attendees = self.calendar_skill.attendee_store.get(event_id)
        if attendees:
            lines.append("👥 參與者：" + "、".join(self._mention_parts(attendees)))

        desc = (event.get("description") or "").strip()
        if desc:
            short = desc[:100] + "…" if len(desc) > 100 else desc
            lines.append(f"📝 備註：{_html.escape(short)}")

        return "\n".join(lines)

    def _fmt_daily(self, events: list[dict], date: datetime) -> str:
        """HTML daily summary message."""
        date_str = date.strftime("%Y年%m月%d日")
        weekday = "一二三四五六日"[date.weekday()]

        if not events:
            return (
                f"📅 <b>{date_str}（週{weekday}）行程彙整</b>\n\n"
                "今天沒有安排行程，祝你有個愉快的一天！ 🌟"
            )

        lines = [
            f"📅 <b>{date_str}（週{weekday}）行程彙整</b>",
            f"共有 {len(events)} 個行程：",
            "",
        ]

        for idx, event in enumerate(events, 1):
            summary = _html.escape(event.get("summary", "（無標題）"))
            start_raw = event["start"].get("dateTime", event["start"].get("date", ""))
            end_raw = event["end"].get("dateTime", event["end"].get("date", ""))
            location = event.get("location", "")

            if "T" in start_raw:
                dt_s = datetime.fromisoformat(
                    start_raw.replace("Z", "+00:00")
                ).astimezone(self.tz)
                start_str = dt_s.strftime("%H:%M")
            else:
                start_str = "全天"

            if end_raw and "T" in end_raw:
                dt_e = datetime.fromisoformat(
                    end_raw.replace("Z", "+00:00")
                ).astimezone(self.tz)
                time_str = f"{start_str} – {dt_e.strftime('%H:%M')}"
            else:
                time_str = start_str

            block = f"{idx}. <b>{summary}</b>\n   🕐 {time_str}"
            if location:
                block += f"\n   📍 {_html.escape(location)}"

            event_id = event.get("id", "")
            attendees = self.calendar_skill.attendee_store.get(event_id)
            if attendees:
                block += "\n   👥 " + "、".join(self._mention_parts(attendees))

            lines.append(block)

        return "\n".join(lines)
