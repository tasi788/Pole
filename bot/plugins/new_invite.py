from pyrogram import Client, filters
from pyrogram.types import ChatMemberUpdated
from pyrogram.enums import ChatMemberStatus, ChatType
from loguru import logger
from typing import Optional

from bot.types import NotificationConfig

# Global notification configuration
_notification_config: Optional[NotificationConfig] = None

def init_notification(config: Optional[NotificationConfig] = None):
    """Initialize notification settings."""
    global _notification_config
    _notification_config = config
    if config:
        logger.info(f"Notification plugin initialized: target_chat={config.invite_target_chat_id}, thread={config.invite_target_thread_id}")

@Client.on_chat_member_updated()
async def handle_new_group_notification(client: Client, update: ChatMemberUpdated):
    """Notify when the bot is added to a new group."""
    if _notification_config is None or _notification_config.invite_target_chat_id is None:
        return

    # Only care about the bot itself being added
    bot_id = client.me.id if (hasattr(client, "me") and client.me) else None
    if bot_id is None:
        return

    new_member = update.new_chat_member
    if new_member is None or new_member.user is None:
        return
    if new_member.user.id != bot_id:
        return

    # Check that the new status is "member" or "administrator" or "owner" (i.e. joined)
    joined_statuses = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER}
    if new_member.status not in joined_statuses:
        return

    # Ignore private chats
    chat = update.chat
    if chat is None or chat.type == ChatType.PRIVATE:
        return

    group_id = chat.id
    group_title = chat.title or f"group_{group_id}"
    username = f"(@{chat.username})" if chat.username else ""

    logger.info(f"New group joined: {group_title} ({group_id}). Sending notification...")

    try:
        msg = (
            f"🔔 **機器人被加入新群組**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👥 **群組名稱**: `{group_title}`\n"
            f"🆔 **群組 ID**: `{group_id}`\n"
            f"🔗 **群組連結**: {username if username else '無公開連結'}\n"
            f"🕒 **時間**: `{update.date}`"
        )
        
        await client.send_message(
            chat_id=_notification_config.invite_target_chat_id,
            text=msg,
            message_thread_id=_notification_config.invite_target_thread_id
        )
        logger.info("Notification sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send invite notification: {e}")
