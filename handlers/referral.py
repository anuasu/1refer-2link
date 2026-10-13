from urllib.parse import quote

from telebot import types

from bot import bot

from config import (
    GROUP_INVITE_LINK,
    CHANNEL_INVITE_LINK,
    REFERRAL_REWARD,
)

from database import (
    get_user,
    get_user_stats,
)

from handlers.start import (
    check_membership,
    process_verification,
)


# =========================================================
# REFERRAL JOIN KEYBOARD
# =========================================================

def referral_join_keyboard():
    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📢 Join Group",
            url=GROUP_INVITE_LINK
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "📣 Join Channel",
            url=CHANNEL_INVITE_LINK
        )
    )

    keyboard.row(
        types.InlineKeyboardButton(
            "✅ Check Membership",
            callback_data="check_join"
        )
    )

    return keyboard


# =========================================================
# SHOW REFERRAL INFORMATION
# =========================================================

def show_referral_info(message):
    user_id = message.from_user.id

    # -----------------------------------------
    # CHECK USER REGISTRATION
    # -----------------------------------------

    user = get_user(user_id)

    if not user:
        bot.reply_to(
            message,
            "Please register your account first by using /start."
        )
        return

    # -----------------------------------------
    # CHECK GROUP AND CHANNEL MEMBERSHIP
    # -----------------------------------------

    if not check_membership(user_id):
        bot.send_message(
            message.chat.id,
            (
                "🔐 <b>Verification Required</b>\n\n"
                "To use Refer &amp; Earn, please join both "
                "our private group and private channel.\n\n"
                "After joining both, tap "
                "<b>Check Membership</b>."
            ),
            reply_markup=referral_join_keyboard(),
            parse_mode="HTML"
        )
        return

    # -----------------------------------------
    # COMPLETE VERIFICATION IF REQUIRED
    # -----------------------------------------

    if not user.get("is_verified"):
        result = process_verification(user_id)

        if not result or not result.get("success"):
            bot.send_message(
                message.chat.id,
                "❌ Verification failed. Please try again."
            )
            return

    # -----------------------------------------
    # GET UPDATED USER STATS
    # -----------------------------------------

    stats = get_user_stats(user_id)

    if not stats:
        bot.send_message(
            message.chat.id,
            "❌ Unable to load your referral statistics. Please try again."
        )
        return

    # -----------------------------------------
    # GENERATE REFERRAL LINK
    # -----------------------------------------

    bot_username = bot.get_me().username

    referral_link = (
        f"https://t.me/{bot_username}?start={user_id}"
    )

    share_url = (
        "https://t.me/share/url"
        f"?url={quote(referral_link, safe='')}"
        f"&text={quote('Join this bot using my referral link!')}"
    )

    # -----------------------------------------
    # REFERRAL INFORMATION
    # -----------------------------------------

    text = (
        "👥 <b>REFER &amp; EARN</b>\n\n"
        "Share your referral link with your friends!\n\n"
        f"🎁 Earn <b>+{REFERRAL_REWARD} Coins</b> "
        "for every successful referral.\n\n"
        "📌 A referral becomes successful when a new user "
        "joins both the group and channel and completes "
        "verification.\n\n"
        "🔗 <b>Your Referral Link:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"👤 Successful Referrals: "
        f"<b>{stats.get('referral_count', 0)}</b>\n"
        f"🪙 Total Coins Earned: "
        f"<b>{stats.get('total_coins_earned', 0)}</b>\n"
        f"💰 Current Balance: "
        f"<b>{stats.get('coins_balance', 0)}</b>"
    )

    # -----------------------------------------
    # SHARE BUTTON
    # -----------------------------------------

    keyboard = types.InlineKeyboardMarkup()

    keyboard.row(
        types.InlineKeyboardButton(
            "📤 Share Referral Link",
            url=share_url
        )
    )

    # -----------------------------------------
    # SEND REFERRAL PAGE
    # -----------------------------------------

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# =========================================================
# REFERRAL COMMAND
# =========================================================

@bot.message_handler(commands=["referral"])
def referral_command(message):
    show_referral_info(message)


# =========================================================
# REFERRAL BUTTON
# =========================================================

@bot.message_handler(
    func=lambda message: (
        message.text is not None
        and message.text.strip() == "👥 Refer & Earn"
    )
)
def referral_button(message):
    show_referral_info(message)
