import telebot
from config import BOT_TOKEN

if not BOT_TOKEN or BOT_TOKEN == "PASTE_BOT_TOKEN_HERE":
    raise ValueError("Please set your Telegram bot token in config.py")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


def get_bot_username():
    bot_info = bot.get_me()
    return bot_info.username
