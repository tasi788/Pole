from pyrogram import Client, filters
from pyrogram.types import Message


@Client.on_message(filters.command("ping"))
async def ping_handler(_, message: Message):
    await message.reply_text("🏓 Pong!")
