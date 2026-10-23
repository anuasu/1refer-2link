from bot import bot
from database import claim_daily_bonus


DAILY_BONUS_AMOUNT = 10


def handle_daily_bonus(chat_id, user_id):
    """
    Claim the daily bonus for a registered user.

    The database controls the India-time calendar date and prevents
    duplicate claims, including after bot restarts.
    """
    try:
        result = claim_daily_bonus(user_id)
    except Exception as error:
        print(f"Daily bonus error for user {user_id}: {error}")
        bot.send_message(
            chat_id,
            "⚠️ Daily Bonus abhi claim nahi ho paaya. Please thodi der baad try karo."
        )
        return

    if not result.get("success"):
        reason = result.get("reason")

        if reason == "already_claimed":
            balance = result.get("balance", 0)
            bot.send_message(
                chat_id,
                (
                    "🎁 <b>Daily Bonus Already Claimed!</b>\n\n"
                    "Bhai, aaj ka +10 coins bonus tum pehle hi claim kar chuke ho. 💓\n\n"
                    f"🪙 <b>Current Balance:</b> {balance} coins\n"
                    "⏰ Next bonus India time ke mutabik midnight ke baad available hoga."
                ),
                parse_mode="HTML",
            )
            return

        if reason == "user_not_found":
            bot.send_message(
                chat_id,
                "❌ Pehle /start karke bot mein register karo, phir Daily Bonus claim kar sakte ho."
            )
            return

        bot.send_message(
            chat_id,
            "❌ Daily Bonus claim nahi ho paaya. Please dobara try karo."
        )
        return

    reward = result.get("reward", DAILY_BONUS_AMOUNT)
    balance = result.get("balance", 0)

    bot.send_message(
        chat_id,
        (
            "🎉 <b>Daily Bonus Claimed Successfully!</b>\n\n"
            f"🎁 <b>Reward:</b> +{reward} coins\n"
            f"🪙 <b>Current Balance:</b> {balance} coins\n\n"
            "💓 Kal India time ke mutabik midnight ke baad phir claim karna!"
        ),
        parse_mode="HTML",
    )


@bot.message_handler(commands=["dailybonus", "daily_bonus"])
def daily_bonus_command(message):
    if message.chat.type != "private":
        return

    handle_daily_bonus(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
    )


@bot.message_handler(
    func=lambda message: (
        message.text is not None
        and message.text.strip() == "🎁 Daily Bonus"
    )
)
def daily_bonus_button(message):
    if message.chat.type != "private":
        return

    handle_daily_bonus(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
  )
  
