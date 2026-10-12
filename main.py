from bot import bot

import handlers.start
import handlers.referral
import handlers.statistics
import handlers.links
import handlers.admin
import handlers.broadcast
import handlers.backup

import handlers.redeem


if __name__ == "__main__":
    print("👣 Bot is starting...")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
