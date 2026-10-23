from bot import bot
from database import claim_daily_bonus


DAILY_BONUS_AMOUNT = 10


def handle_daily_bonus(chat_id, user_id):
    """
    Process a daily bonus claim for a registered user.

    The database uses the India-time calendar date to manage eligibility
    and prevent duplicate claims, including after bot restarts.
    """
    try:
        result = claim_daily_bonus(user_id)
    except Exception as error:
        print(f"Daily Bonus Error for user {user_id}: {error}")
        bot.send_message(
            chat_id,
            "⚠️ <b>Daily Bonus Temporarily Unavailable</b>\n\n"
            "Your bonus could not be claimed at this time. "
            "Please try again shortly.",
            parse_mode="HTML",
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
                    "You have already claimed today's daily bonus of "
                    "<b>+10 coins</b>. 💎\n\n"
                    f"🪙 <b>Current Balance:</b> {balance} coins\n\n"
                    "⏰ Your next daily bonus will be available after "
                    "midnight (India Standard Time)."
                ),
                parse_mode="HTML",
            )
            return

        if reason == "user_not_found":
            bot.send_message(
                chat_id,
                (
                    "❌ <b>Registration Required</b>\n\n"
                    "Please use /start to register your account "
                    "before claiming the Daily Bonus."
                ),
                parse_mode="HTML",
            )
            return

        bot.send_message(
            chat_id,
            (
                "❌ <b>Daily Bonus Claim Failed</b>\n\n"
                "We could not process your request. Please try again."
            ),
            parse_mode="HTML",
        )
        return

    reward = result.get("reward", DAILY_BONUS_AMOUNT)
    balance = result.get("balance", 0)

    bot.send_message(
        chat_id,
        (
            "🎉 <b>Daily Bonus Claimed Successfully!</b>\n\n"
            f"🎁 <b>Reward Received:</b> +{reward} coins\n"
            f"🪙 <b>Current Balance:</b> {balance} coins\n\n"
            "💎 Return tomorrow after midnight (India Standard Time) "
            "to claim your next daily reward!"
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
