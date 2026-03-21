from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from loguru import logger

from bot.core.base_tool import BaseTool

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarTool(BaseTool):
    """Tool for Google Calendar API operations."""

    name = "google_calendar"
    description = "Google Calendar API operations"

    def __init__(self, credentials_path: str, token_path: str = "token.json"):
        super().__init__()
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.service = None

    def initialize(self) -> None:
        """Authenticate with Google Calendar API."""
        creds = None

        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_path, "w") as token:
                token.write(creds.to_json())

        self.service = build("calendar", "v3", credentials=creds)
        self._initialized = True
        logger.info("Google Calendar Tool initialized")

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
        }

        if action not in actions:
            raise ValueError(f"Unknown action: {action}")

        return await actions[action](**kwargs)

    async def _list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        max_results: int = 10,
    ) -> list[dict]:
        """List events from calendar."""
        if time_min is None:
            time_min = datetime.utcnow()

        events_result = (
            self.service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat() + "Z",
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

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

    async def _delete_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> bool:
        """Delete an event."""
        try:
            self.service.events().delete(
                calendarId=calendar_id, eventId=event_id
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to delete event {event_id}: {e}")
            return False
