from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from loguru import logger

from bot.core.base_tool import BaseTool

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarTool(BaseTool):
    """Tool for Google Calendar API operations."""

    name = "google_calendar"
    description = "Google Calendar API operations"

    def __init__(self, credentials_path: str):
        super().__init__()
        self.credentials_path = Path(credentials_path)
        self.service = None

    def initialize(self) -> None:
        """Authenticate with Google Calendar API using Service Account."""
        creds = Credentials.from_service_account_file(
            str(self.credentials_path), scopes=SCOPES
        )
        self.service = build("calendar", "v3", credentials=creds)
        self._initialized = True
        logger.info("Google Calendar Tool initialized (service account)")

    async def execute(self, action: str, **kwargs) -> Any:
        """Execute a calendar action."""
        if not self._initialized:
            raise RuntimeError("Tool not initialized. Call initialize() first.")

        self._log_action(action, **kwargs)

        actions = {
            "list_events": self._list_events,
            "get_event": self._get_event,
            "insert_event": self._insert_event,
            "update_event": self._update_event,
            "delete_event": self._delete_event,
            "list_calendars": self._list_calendars,
            "create_calendar": self._create_calendar,
        }

        if action not in actions:
            raise ValueError(f"Unknown action: {action}")

        return await actions[action](**kwargs)

    async def _list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10,
    ) -> list[dict]:
        """List events from calendar."""
        from datetime import timezone as _tz_utc

        def _to_rfc3339(dt: datetime) -> str:
            if dt.tzinfo is None:
                return dt.isoformat() + "Z"
            return dt.astimezone(_tz_utc.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if time_min is None:
            from datetime import timezone as _tz

            time_min = datetime.now(_tz.utc)

        query_params: dict = dict(
            calendarId=calendar_id,
            timeMin=_to_rfc3339(time_min),
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        if time_max is not None:
            query_params["timeMax"] = _to_rfc3339(time_max)

        events_result = self.service.events().list(**query_params).execute()
        return events_result.get("items", [])

    async def _get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Optional[dict]:
        """Get a specific event."""
        try:
            return (
                self.service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except Exception as e:
            logger.error(f"Failed to get event {event_id}: {e}")
            return None

    async def _insert_event(
        self, event_body: dict, calendar_id: str = "primary"
    ) -> dict:
        """Insert a new event."""
        return (
            self.service.events()
            .insert(calendarId=calendar_id, body=event_body)
            .execute()
        )

    async def _update_event(
        self, event_id: str, event_body: dict, calendar_id: str = "primary"
    ) -> dict:
        """Update an existing event."""
        return (
            self.service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=event_body)
            .execute()
        )

    async def _delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Delete an event."""
        try:
            self.service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to delete event {event_id}: {e}")
            return False

    async def _list_calendars(self) -> list[dict]:
        """List all calendars accessible by the service account."""
        result = self.service.calendarList().list().execute()
        return result.get("items", [])

    async def _create_calendar(self, summary: str, timezone: str = "Asia/Taipei") -> dict:
        """Create a new secondary calendar and return the calendar resource."""
        body = {
            "summary": summary,
            "timeZone": timezone,
        }
        calendar = self.service.calendars().insert(body=body).execute()
        logger.info(f"Created new calendar: {calendar.get('id')} ({summary})")
        return calendar
