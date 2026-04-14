import html as _html
from typing import Optional

from loguru import logger
from pyrogram import Client, enums, filters
from pyrogram.types import Message

from bot.core.permissions import PermissionManager
from bot.core.user_profiles import UserProfileManager
from bot.skills.ai import AISkill
from bot.skills.calendar import CalendarSkill
from bot.skills.calendar.reminder import CalendarReminderScheduler
from bot.types import AIConfig, GoogleCalendarConfig

permission_manager: PermissionManager | None = None
calendar_skill: CalendarSkill | None = None
ai_skill: AISkill | None = None
user_profile_manager: UserProfileManager | None = None
reminder_scheduler: CalendarReminderScheduler | None = None
_owner_id: int | None = None
_calendar_timezone: str = "Asia/Taipei"
_notify_owner: bool = True


def init_skills(
    owner_id: Optional[int] = None,
    calendar_config: Optional[GoogleCalendarConfig] = None,
    ai_config: Optional[AIConfig] = None,
):
    """Initialize all skills with credentials."""
    global \
        calendar_skill, \
        ai_skill, \
        permission_manager, \
        user_profile_manager, \
        _owner_id, \
        _calendar_timezone, \
        _notify_owner

    _owner_id = owner_id

    user_profile_manager = UserProfileManager()
    logger.info("User profile manager initialized")

    permission_manager = PermissionManager()
    if owner_id:
        permission_manager.set_owner(owner_id)

    if calendar_config:
        calendar_skill = CalendarSkill(
            credentials_path=calendar_config.credentials_path,
            timezone=calendar_config.timezone,
            default_calendar_id=calendar_config.default_calendar_id,
            group_access=calendar_config.group_access,
            permission_manager=permission_manager,
        )
        calendar_skill.initialize()
        _calendar_timezone = calendar_config.timezone
        _notify_owner = calendar_config.notify_owner
        logger.info("Calendar skill initialized")

    if ai_config:
        persona = ai_config.persona.model_dump() if ai_config.persona else {}
        ai_skill = AISkill(
            api_key=ai_config.api_key,
            base_url=ai_config.base_url,
            model=ai_config.model,
            max_tokens=ai_config.max_tokens,
            temperature=ai_config.temperature,
            persona=persona,
            calendar_skill=calendar_skill,
            user_profile_manager=user_profile_manager,
            permission_manager=permission_manager,
        )
        ai_skill.initialize()
        logger.info("AI skill initialized")


def create_reminder_scheduler(client) -> CalendarReminderScheduler | None:
    """Create and start the calendar reminder scheduler (call after bot starts)."""
    global reminder_scheduler
    if calendar_skill is None:
        logger.warning("CalendarSkill not available – reminder scheduler skipped")
        return None
    if _owner_id is None:
        logger.warning("owner_id not set – reminder scheduler skipped")
        return None

    reminder_scheduler = CalendarReminderScheduler(
        client=client,
        calendar_skill=calendar_skill,
        owner_id=_owner_id,
        timezone=_calendar_timezone,
        notify_owner=_notify_owner,
    )
    reminder_scheduler.start()
    logger.info("CalendarReminderScheduler created and started")
    return reminder_scheduler


async def mention_or_reply_filter(_, client: Client, message: Message) -> bool:
    """Filter for messages that mention or reply to the bot."""
    if not message.text:
        return False

    if not hasattr(client, "me") or not client.me:
        return False

    if message.reply_to_message and message.reply_to_message.from_user:
        if message.reply_to_message.from_user.id == client.me.id:
            return True

    bot_username = client.me.username
    if bot_username and f"@{bot_username}" in message.text:
        return True

    return False


mention_or_reply_bot = filters.create(mention_or_reply_filter)


async def _extract_tagged_users(client, message) -> list[dict]:
    """Extract Telegram user info from message entities (mentions)."""
    from pyrogram import enums as _enums

    tagged: list[dict] = []
    seen_ids: set[int] = set()

    if not message.entities:
        return tagged

    bot_id = client.me.id if (hasattr(client, "me") and client.me) else None
    text: str = message.text or ""

    for entity in message.entities:
        user_obj = None

        if entity.type == _enums.MessageEntityType.TEXT_MENTION:
            # User tagged without a public username – entity carries the User object
            if entity.user:
                user_obj = entity.user

        elif entity.type == _enums.MessageEntityType.MENTION:
            # @username mention – resolve to User object via API
            mention_slice = text[entity.offset : entity.offset + entity.length]
            username = mention_slice.lstrip("@")
            if username:
                try:
                    user_obj = await client.get_users(username)
                except Exception as exc:
                    logger.warning(f"Could not resolve @{username}: {exc}")
                    continue

        if user_obj is None:
            continue
        if user_obj.id == bot_id:
            continue  # skip the bot itself
        if user_obj.id in seen_ids:
            continue  # deduplicate

        seen_ids.add(user_obj.id)
        first = user_obj.first_name or ""
        last = user_obj.last_name or ""
        full_name = f"{first} {last}".strip() or f"uid:{user_obj.id}"

        tagged.append({"user_id": user_obj.id, "full_name": full_name})

    return tagged


@Client.on_message(mention_or_reply_bot)
async def handle_mention(client: Client, message: Message):
    """Handle messages that mention or reply to the bot."""
    text = message.text or ""
    user = message.from_user
    user_id = user.id
    logger.info(f"Bot triggered by user {user_id}: {text[:50]}...")

    bot_username = client.me.username
    clean_text = text.replace(f"@{bot_username}", "").strip() if bot_username else text
    tagged_users = await _extract_tagged_users(client, message)

    chat_id = message.chat.id

    user_name = user.first_name or ""
    if user.last_name:
        user_name += f" {user.last_name}"
    user_username = user.username or ""

    user_info = {
        "user_id": user_id,
        "name": user_name,
        "username": user_username,
    }

    chat_info = {
        "chat_id": message.chat.id,
        "chat_title": message.chat.title or message.chat.first_name or "私人對話",
    }

    user_profile_text = ""
    if user_profile_manager:
        profile = user_profile_manager.get_or_create_profile(
            user_id=user_id,
            name=user_name,
            username=user_username,
        )
        user_profile_manager.increment_interaction(user_id)
        user_profile_text = profile.to_prompt()

    if ai_skill:
        response = await ai_skill.handle(
            user_id,
            clean_text,
            chat_id=chat_id,
            user_info=user_info,
            chat_info=chat_info,
            user_profile_text=user_profile_text,
            tagged_users=tagged_users,
        )
        await message.reply_text(response)
    elif calendar_skill and calendar_skill.has_keyword(text):
        response = await calendar_skill.handle(user_id, text, chat_id=chat_id)
        await message.reply_text(response)
    else:
        await message.reply_text(
            "你好！有什麼我可以幫忙的嗎？\n\n提示：你可以問我關於「行事曆」的問題。"
        )
