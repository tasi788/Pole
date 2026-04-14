import html as _html
from typing import Optional

from loguru import logger
from pyrogram import Client, enums, filters
from pyrogram.types import Message
import re
from pyrogram import enums as _enums

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


async def _extract_tagged_users(client, message) -> tuple[list[dict], dict[str, int]]:
    """Extract Telegram user info from message entities AND raw text @mentions.

    Returns:
        (tagged_users, username_map)
        - tagged_users: list of {user_id, full_name}
        - username_map: dict mapping resolved_username_lower -> user_id
    """
    tagged: list[dict] = []
    seen_ids: set[int] = set()
    seen_usernames: set[str] = set()  # populated ONLY after successful resolution
    username_map: dict[str, int] = {}  # username_lower -> user_id (for text injection)

    bot_id = client.me.id if (hasattr(client, "me") and client.me) else None
    bot_username = (client.me.username or "").lower() if (hasattr(client, "me") and client.me) else ""
    text: str = message.text or ""

    async def _resolve_username(username: str, source: str) -> None:
        """Resolve a @username string and append to tagged list if valid."""
        uname_lower = username.lower()
        if uname_lower in seen_usernames:
            logger.debug(f"@{username} already resolved, skipping ({source})")
            return
        if uname_lower == bot_username:
            return
        try:
            user_obj = await client.get_users(username)
        except Exception as exc:
            # Do NOT add to seen_usernames here - let the other pass retry
            logger.warning(f"Could not resolve @{username} ({source}): {exc}")
            return

        if user_obj is None:
            logger.warning(f"get_users(@{username}) returned None ({source})")
            return

        # Mark as seen regardless (bot or duplicate)
        seen_usernames.add(uname_lower)
        if user_obj.username:
            seen_usernames.add(user_obj.username.lower())
            username_map[user_obj.username.lower()] = user_obj.id
        username_map[uname_lower] = user_obj.id

        if user_obj.id == bot_id or user_obj.id in seen_ids:
            return

        seen_ids.add(user_obj.id)
        first = user_obj.first_name or ""
        last = user_obj.last_name or ""
        full_name = f"{first} {last}".strip() or f"uid:{user_obj.id}"
        tagged.append({"user_id": user_obj.id, "full_name": full_name})
        logger.info(f"Resolved @{username} ({source}) -> uid:{user_obj.id} ({full_name})")

    # -- Pass 1: Telegram entities --------------------------------------------
    entity_list = message.entities or []
    logger.debug(f"_extract_tagged_users: {len(entity_list)} entities, text={repr(text[:60])}")

    for entity in entity_list:
        if entity.type == _enums.MessageEntityType.TEXT_MENTION:
            # No public username - entity carries the User object directly
            user_obj = entity.user
            if user_obj is None or user_obj.id == bot_id or user_obj.id in seen_ids:
                continue
            seen_ids.add(user_obj.id)
            if user_obj.username:
                seen_usernames.add(user_obj.username.lower())
                username_map[user_obj.username.lower()] = user_obj.id
            first = user_obj.first_name or ""
            last = user_obj.last_name or ""
            full_name = f"{first} {last}".strip() or f"uid:{user_obj.id}"
            tagged.append({"user_id": user_obj.id, "full_name": full_name})
            logger.info(f"TEXT_MENTION -> uid:{user_obj.id} ({full_name})")

        elif entity.type == _enums.MessageEntityType.MENTION:
            mention_slice = text[entity.offset : entity.offset + entity.length]
            username = mention_slice.lstrip("@")
            logger.debug(f"MENTION entity offset={entity.offset} -> '{mention_slice}'")
            if username:
                await _resolve_username(username, "entity")

    # -- Pass 2: regex fallback for plain-text @username ----------------------
    for match in re.finditer(r"@([A-Za-z0-9_]{3,})", text):
        username = match.group(1)
        if username.lower() in seen_usernames:
            continue
        logger.debug(f"regex found unresolved @{username}, trying get_users")
        await _resolve_username(username, "regex")

    logger.debug(f"_extract_tagged_users result: tagged={tagged}, username_map={username_map}")
    return tagged, username_map



@Client.on_message(mention_or_reply_bot)
async def handle_mention(client: Client, message: Message):
    """Handle messages that mention or reply to the bot."""
    text = message.text or ""
    user = message.from_user
    user_id = user.id
    logger.info(f"Bot triggered by user {user_id}: {text[:50]}...")

    bot_username = client.me.username
    clean_text = text.replace(f"@{bot_username}", "").strip() if bot_username else text
    tagged_users, username_map = await _extract_tagged_users(client, message)

    # Inject resolved user IDs directly into clean_text so the AI always has them
    # e.g. "@stu5016" -> "@stu5016 [id:14738514]"
    if username_map:
        def _inject_id(match: re.Match) -> str:
            uname = match.group(1)
            uid = username_map.get(uname.lower())
            if uid and uname.lower() != (bot_username or "").lower():
                return f"@{uname} [id:{uid}]"
            return match.group(0)
        clean_text = re.sub(r"@([A-Za-z0-9_]{3,})", _inject_id, clean_text)
        logger.debug(f"clean_text after ID injection: {clean_text[:120]}")

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


@Client.on_chat_member_updated()
async def handle_bot_added(client: Client, update):
    """Triggered when the bot's membership status changes in any chat.

    When the bot is added to a group / supergroup, automatically provision
    a secondary Google Calendar for that chat if one does not yet exist.
    """
    from pyrogram.enums import ChatMemberStatus
    from pyrogram.types import ChatMemberUpdated

    update: ChatMemberUpdated  # type annotation for IDE

    # Only care about the bot itself being added
    bot_id = client.me.id if (hasattr(client, "me") and client.me) else None
    if bot_id is None:
        return

    new_member = update.new_chat_member
    if new_member is None or new_member.user is None:
        return
    if new_member.user.id != bot_id:
        return

    # Check that the new status is "member" or "administrator" (i.e. joined)
    joined_statuses = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
    if new_member.status not in joined_statuses:
        return

    # Ignore private chats
    chat = update.chat
    if chat is None:
        return
    from pyrogram.enums import ChatType
    if chat.type == ChatType.PRIVATE:
        return

    group_id = chat.id
    group_title = chat.title or f"group_{group_id}"

    logger.info(f"Bot was added to group '{group_title}' ({group_id}), provisioning calendar...")

    if calendar_skill is None:
        logger.warning("calendar_skill not available – skipping calendar provisioning")
        return

    try:
        calendar_id = await calendar_skill.ensure_group_calendar(group_id, group_title)
        await client.send_message(
            group_id,
            f"📅 已為此群組建立專屬行事曆！\n"
            f"📌 行事曆 ID：`{calendar_id}`\n"
            f"可以直接 @我 來新增、查詢或刪除行程。",
        )
    except Exception as e:
        logger.error(f"Failed to provision calendar for group {group_id}: {e}")
        try:
            await client.send_message(
                group_id,
                f"⚠️ 無法自動建立行事曆，請聯絡機器人管理員。\n原因：{e}"
            )
        except Exception:
            pass
