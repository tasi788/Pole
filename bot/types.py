from typing import Optional
from pydantic import BaseModel


class BotConfig(BaseModel):
    api_id: int
    api_hash: str
    bot_token: str
    owner_id: Optional[int] = None


class LoggingConfig(BaseModel):
    level: str = "DEBUG"
    rotation: str = "10 MB"
    retention: str = "7 days"


class CalendarPermission(BaseModel):
    calendar_id: str = "primary"
    can_read: bool = True
    can_write: bool = False
    can_delete: bool = False


class GroupCalendarAccess(BaseModel):
    group_id: int
    calendar_id: str
    permissions: CalendarPermission = CalendarPermission()


class GoogleCalendarConfig(BaseModel):
    credentials_path: str = "service_account.json"
    default_calendar_id: str = "primary"
    group_access: list[GroupCalendarAccess] = []


class AIPersona(BaseModel):
    name: str = "助手"
    personality: str = ""
    tone: str = ""
    background: str = ""
    rules: list[str] = []


class AIConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: str
    model: str = "gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.7
    persona: AIPersona = AIPersona()


class Config(BaseModel):
    bot: BotConfig
    logging: LoggingConfig = LoggingConfig()
    google_calendar: Optional[GoogleCalendarConfig] = None
    ai: Optional[AIConfig] = None
