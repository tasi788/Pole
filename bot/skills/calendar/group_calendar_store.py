"""Persistent store for group_id → calendar_id mapping.

Storage file: data/group_calendars.json
Schema:
{
    "<group_id (str)>": {
        "calendar_id": "...",
        "title": "群組名稱",
        "created_at": "ISO8601"
    },
    ...
}
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

_DEFAULT_PATH = Path("data/group_calendars.json")


class GroupCalendarStore:
    """Read/write mapping of Telegram group_id → Google Calendar ID."""

    def __init__(self, path: Path = _DEFAULT_PATH):
        self._path = path
        self._data: dict[str, dict] = {}
        self._load()

    # ── I/O ─────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.debug(f"GroupCalendarStore loaded {len(self._data)} entries from {self._path}")
            except Exception as e:
                logger.error(f"GroupCalendarStore: failed to load {self._path}: {e}")
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"GroupCalendarStore: failed to save {self._path}: {e}")

    # ── Public API ───────────────────────────────────────────────────────────

    def get_calendar_id(self, group_id: int) -> Optional[str]:
        """Return the calendar_id for *group_id*, or None if not registered."""
        entry = self._data.get(str(group_id))
        return entry["calendar_id"] if entry else None

    def has_group(self, group_id: int) -> bool:
        """Return True if *group_id* already has a registered calendar."""
        return str(group_id) in self._data

    def register(self, group_id: int, calendar_id: str, title: str = "") -> None:
        """Persist a group → calendar mapping."""
        self._data[str(group_id)] = {
            "calendar_id": calendar_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
        }
        self._save()
        logger.info(f"GroupCalendarStore: registered group {group_id} → {calendar_id}")

    def all_entries(self) -> dict[str, dict]:
        """Return a copy of all stored entries."""
        return dict(self._data)
