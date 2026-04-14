from loguru import logger as log
from pyrogram import Client

from bot.config import load_config
from bot.logger import setup_logger


def create_bot() -> Client:
    """Create and configure the Pyrogram bot client."""
    config = load_config()

    setup_logger(
        level=config.logging.level,
        rotation=config.logging.rotation,
        retention=config.logging.retention,
    )

    from bot.plugins.mention import init_skills

    init_skills(
        owner_id=config.bot.owner_id,
        calendar_config=config.google_calendar,
        ai_config=config.ai,
    )
    log.info("Skills initialized")

    bot = Client(
        name="pole_bot",
        api_id=config.bot.api_id,
        api_hash=config.bot.api_hash,
        bot_token=config.bot.bot_token,
        plugins=dict(root="bot.plugins"),
    )

    @bot.on_start()
    async def on_startup(client: Client):
        client.me = await client.get_me()
        log.info(
            f"Bot started: {client.me.first_name} (@{client.me.username}) [ID: {client.me.id}]"
        )

        # Start calendar reminder scheduler
        from bot.plugins.mention import create_reminder_scheduler

        create_reminder_scheduler(client)

    return bot
