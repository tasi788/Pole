from typing import Optional
from pyrogram import Client, filters
from pyrogram.types import Message
from loguru import logger

from bot.skills.calendar import CalendarSkill
from bot.skills.ai import AISkill
from bot.core.permissions import PermissionManager
from bot.types import AIConfig, GoogleCalendarConfig

permission_manager: PermissionManager | None = None
calendar_skill: CalendarSkill | None = None
ai_skill: AISkill | None = None


def init_skills(
    owner_id: Optional[int] = None,
    calendar_config: Optional[GoogleCalendarConfig] = None,
    ai_config: Optional[AIConfig] = None,
):
    """Initialize all skills with credentials."""
    global calendar_skill, ai_skill, permission_manager

    permission_manager = PermissionManager()
    if owner_id:
        permission_manager.set_owner(owner_id)

    if calendar_config:
        calendar_skill = CalendarSkill(
            credentials_path=calendar_config.credentials_path,
            token_path=calendar_config.token_path,
            default_calendar_id=calendar_config.default_calendar_id,
            group_access=calendar_config.group_access,
            permission_manager=permission_manager,
        )
        calendar_skill.initialize()
        logger.info("Calendar skill initialized")

    if ai_config:
        ai_skill = AISkill(
            api_key=ai_config.api_key,
            base_url=ai_config.base_url,
            model=ai_config.model,
            max_tokens=ai_config.max_tokens,
            temperature=ai_config.temperature,
            calendar_skill=calendar_skill,
            permission_manager=permission_manager,
        )
        ai_skill.initialize()
        logger.info("AI skill initialized")


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


@Client.on_message(mention_or_reply_bot)
async def handle_mention(client: Client, message: Message):
    """Handle messages that mention or reply to the bot."""
    text = message.text or ""
    user_id = message.from_user.id
    logger.info(f"Bot triggered by user {user_id}: {text[:50]}...")

    bot_username = client.me.username
    clean_text = text.replace(f"@{bot_username}", "").strip() if bot_username else text

    chat_id = message.chat.id

    if ai_skill:
        response = await ai_skill.handle(user_id, clean_text, chat_id=chat_id)
        await message.reply_text(response)
    elif calendar_skill and calendar_skill.has_keyword(text):
        response = await calendar_skill.handle(user_id, text, chat_id=chat_id)
        await message.reply_text(response)
    else:
        await message.reply_text("你好！有什麼我可以幫忙的嗎？\n\n提示：你可以問我關於「行事曆」的問題。")
