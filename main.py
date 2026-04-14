from loguru import logger

from bot import create_bot


def main():
    """Main entry point for the bot."""
    bot = create_bot()
    logger.info("Bot is starting...")

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Bot crashed with error: {e}")
        raise
    finally:
        from bot.plugins.mention import reminder_scheduler

        if reminder_scheduler is not None:
            reminder_scheduler.stop()


if __name__ == "__main__":
    main()
