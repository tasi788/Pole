"""Local JSON store for Telegram attendee data linked to calendar events."""

import json
from pathlib import Path

from loguru import logger


class AttendeeStore:
    """Persists {user_id, full_name} lists keyed by Google Calendar event_id."""

    def __init__(self, storage_path: str = "data/calendar_attendees.json"):
        self.storage_path = Path(storage_path)
        self._data: dict[str, list[dict]] = {}
        self._load()

    # ---------- private ----------

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.debug(f"AttendeeStore: loaded {len(self._data)} event records")
            except Exception as exc:
                logger.error(f"AttendeeStore: failed to load – {exc}")

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.error(f"AttendeeStore: failed to save – {exc}")

    # ---------- public ----------

    def save(self, event_id: str, attendees: list[dict]) -> None:
        """Save attendees for event_id. Each dict: {user_id: int, full_name: str}"""
        if not attendees:
            return
        self._data[event_id] = attendees
        self._save()

    def get(self, event_id: str) -> list[dict]:
        """Return attendee list for event_id, or empty list."""
        return self._data.get(event_id, [])

    def delete(self, event_id: str) -> None:
        """Remove attendees when an event is deleted."""
        if event_id in self._data:
            del self._data[event_id]
            self._save()
